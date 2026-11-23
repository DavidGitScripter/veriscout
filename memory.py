"""
memory.py — versionierter Feedback-Memory-Service.

KEIN Modell-Training, sondern retrieval-gestuetzter Zugriff auf versionierte
menschliche Vergleichsurteile. Die Faelle werden als Kontext sichtbar gemacht,
veraendern ohne eigene Kalibration aber weder Score noch Schwelle und gelten
nie als Sachbeleg. Persistenz als schlichtes JSON; die datenschutzrechtliche
Zulaessigkeit haengt weiterhin von Inhalt, Zweck und Aufbewahrung ab.
"""
from __future__ import annotations

import json
import os
import hashlib
import datetime
from core import Config, tokenize, jaccard

SIM_THRESHOLD = 0.16      # Aehnlichkeit, ab der ein frueheres Negativ zaehlt


def _utc_time(value: str) -> datetime.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


class MemoryStore:
    def __init__(self, path: str = None, read_only: bool = False,
                 records: list | None = None):
        self.path = path or Config.MEMORY_PATH
        self.read_only = read_only
        self.data = {"records": list(records or [])}
        if records is None and os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                pass

    def save(self):
        if self.read_only:
            raise RuntimeError("Der Memory-Snapshot ist im Evaluationslauf schreibgeschuetzt.")
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, mode=0o700, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def add(self, rec: dict):
        if self.read_only:
            raise RuntimeError("Der Memory-Snapshot ist im Evaluationslauf schreibgeschuetzt.")
        self.data["records"].append(rec)
        self.save()

    def records(self):
        return self.data["records"]

    def clear(self):
        if self.read_only:
            raise RuntimeError("Der Memory-Snapshot ist im Evaluationslauf schreibgeschuetzt.")
        self.data = {"records": []}
        self.save()

    def snapshot_id(self) -> str:
        raw = json.dumps(self.records(), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
        return "mem-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class FeedbackMemory:
    """Ruft menschlich bewertete Vergleichsfaelle ab.

    Der Service ist kein autonomer Agent und kein Modelltraining. Im
    Vergleichsexperiment wird derselbe schreibgeschuetzte Snapshot beiden
    Architekturen bereitgestellt. Er aendert weder Score noch Schwelle doppelt;
    eine spaetere entscheidungswirksame Regel braucht eine eigene Kalibration.
    """
    def __init__(self, store: MemoryStore = None):
        self.store = store or MemoryStore()

    def record(self, actor_id: str, description: str, label: bool,
               score: int, outcome: str, reviewer_id: str = "",
               decision_id: str = "", source_run_id: str = "",
               task_group_id: str = "", relation_id: str = "",
               candidate_id: str = "", dataset_split: str = "train",
               event_time: str = "", source_family: str = "human-review",
               provenance: str = "", valid_from: str = "",
               valid_to: str = "", supersedes: str = "",
               status: str = "active", write_action: str = "new",
               experiment_scope: str = "organization_local"):
        """Speichert ein zurechenbares Feedbackereignis.

        Leere Identitaets-/Entscheidungsfelder bleiben fuer alte lokale Daten
        technisch zulaessig, werden im Audit aber sichtbar und duerfen nicht in
        eine Wirksamkeitsevaluation eingehen.
        """
        if outcome not in {"useful", "not_useful"}:
            raise ValueError("outcome muss 'useful' oder 'not_useful' sein")
        self.store.add({
            "event_version": 1,
            "memory_id": "mem-" + hashlib.sha256(
                f"{actor_id}|{description}|{decision_id}|{source_run_id}".encode(
                    "utf-8")).hexdigest()[:20],
            "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "reviewer_id": str(reviewer_id or ""),
            "decision_id": str(decision_id or ""),
            "source_run_id": str(source_run_id or ""),
            "task_group_id": str(task_group_id or ""),
            "relation_id": str(relation_id or ""),
            "candidate_id": str(candidate_id or ""),
            "dataset_split": str(dataset_split or "train"),
            "event_time": str(event_time or ""),
            "config_version": Config.VERSION,
            "actor_id": actor_id,
            "organization_id": actor_id,
            "description": description,
            "label": bool(label),
            "score": int(score),
            "outcome": outcome,
            "source_family": str(source_family or "human-review"),
            "provenance": str(provenance or ""),
            "valid_from": str(valid_from or event_time or ""),
            "valid_to": str(valid_to or ""),
            "supersedes": str(supersedes or ""),
            "status": str(status or "active"),
            "write_action": str(write_action or "new"),
            "experiment_scope": str(experiment_scope or "organization_local"),
        })

    def retrieve(self, actor_id: str, description: str, limit: int = 3,
                 evaluation_context: dict | None = None) -> list[dict]:
        query = tokenize(description)
        ranked = []
        evaluation_context = dict(evaluation_context or {})
        strict = bool(evaluation_context)
        excluded_task = str(evaluation_context.get("task_group_id") or "")
        excluded_relation = str(evaluation_context.get("relation_id") or "")
        excluded_candidate = str(evaluation_context.get("candidate_id") or "")
        current_event_time = str(evaluation_context.get("event_time") or "")
        current_time = _utc_time(current_event_time)
        if strict and current_event_time and current_time is None:
            return []
        for record in self.store.records():
            record_actor = str(
                record.get("organization_id") or record.get("actor_id") or "")
            if record_actor not in {actor_id, "*"}:
                continue
            if str(record.get("status") or "active") != "active":
                continue
            if strict:
                # Konfirmatorische Evaluation verwendet ausschliesslich den
                # eingefrorenen Trainingssnapshot. Legacy-Datensaetze ohne
                # Splitkennzeichnung werden fail-closed ausgeschlossen.
                if record.get("dataset_split") != "train":
                    continue
                if excluded_task and record.get("task_group_id") == excluded_task:
                    continue
                if excluded_relation and record.get("relation_id") == excluded_relation:
                    continue
                if excluded_candidate and record.get("candidate_id") == excluded_candidate:
                    continue
                record_time_raw = str(record.get("event_time") or
                                      record.get("recorded_at") or "")
                valid_from_raw = str(record.get("valid_from") or "")
                valid_to_raw = str(record.get("valid_to") or "")
                record_time = _utc_time(record_time_raw)
                valid_from = _utc_time(valid_from_raw)
                valid_to = _utc_time(valid_to_raw)
                if record_time_raw and record_time is None:
                    continue
                if valid_from_raw and valid_from is None:
                    continue
                if valid_to_raw and valid_to is None:
                    continue
                if current_time and record_time and record_time >= current_time:
                    continue
                if current_time and valid_from and valid_from > current_time:
                    continue
                if current_time and valid_to and valid_to <= current_time:
                    continue
            global_procedural = str(record.get("scope") or "") == "global_procedural"
            similarity = (1.0 if global_procedural else
                          jaccard(query, tokenize(record.get("description", ""))))
            if not global_procedural and similarity < SIM_THRESHOLD:
                continue
            item = dict(record)
            item["similarity"] = round(similarity, 3)
            ranked.append(item)
        ranked.sort(key=lambda item: item["similarity"], reverse=True)
        return ranked[:max(0, int(limit))]

    def context(self, actor_id: str, description: str, limit: int = 3,
                evaluation_context: dict | None = None) -> dict:
        records = self.retrieve(
            actor_id, description, limit=limit,
            evaluation_context=evaluation_context)
        return {
            "snapshot_id": self.store.snapshot_id(),
            "read_only": bool(self.store.read_only),
            "retrieved": records,
            "evaluation_filter": dict(evaluation_context or {}),
            "train_only": bool(evaluation_context),
            "hinweis": (
                "Fruehere Urteile sind Vergleichsfaelle, keine Wahrheit und keine "
                "eigenstaendige positive Evidenz."
            ),
        }

    def threshold_delta(self, actor_id: str) -> int:
        """Kompatibilitaetsmethode: ohne Kalibration keine Schwellenverschiebung."""
        return 0

    def score_adjustment(self, actor_id: str, description: str) -> tuple:
        """Kompatibilitaetsmethode: Abruf ja, unkalibrierte Scoreaenderung nein."""
        records = self.retrieve(actor_id, description, limit=1)
        if not records:
            return 0, 0.0, ""
        best = records[0]
        return 0, best["similarity"], best.get("description", "")[:60]

    def effective_threshold(self, actor_id: str) -> int:
        return Config.THRESHOLD_SUFFICIENT

    def stats(self) -> dict:
        recs = self.store.records()
        by_actor = {}
        for r in recs:
            actor_id = str(r.get("organization_id") or r.get("actor_id") or "")
            outcome = str(r.get("outcome") or "")
            by_actor.setdefault(actor_id, {"useful": 0, "not_useful": 0})
            if outcome in by_actor[actor_id]:
                by_actor[actor_id][outcome] += 1
        return {"feedback_gesamt": len(recs), "je_akteur": by_actor,
                "snapshot_id": self.store.snapshot_id(),
                "read_only": bool(self.store.read_only),
                "schwellen": {aid: self.effective_threshold(aid) for aid in by_actor}}


# Bestehende Imports bleiben lauffaehig; wissenschaftlich wird die Komponente
# fortan als FeedbackMemory-Service und nicht als autonomer Agent bezeichnet.
MemoryAgent = FeedbackMemory
