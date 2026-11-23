"""Bewertet gespeicherte Laeufe mit dem aktuellen Regelkern neu, ohne API-Kosten.

Die Modellantworten (Stufenartefakte nach der Pruefstufe) bleiben unveraendert.
Neu ausgefuehrt werden nur Quellenabruf, Entitaetspruefung, Evidenzmatrix und
Entscheidung. Das Ergebnis wird als eigener, ausdruecklich gekennzeichneter
Lauf gespeichert; die Originaldatei bleibt unveraendert.

    .venv/bin/python scripts/reevaluate_run.py artifacts/runs/run-probe-XXXX.json
"""
from __future__ import annotations

import datetime
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compare_architectures import (PairedArchitectureRunner,  # noqa: E402
                                   annotation_package, assignment_manifest,
                                   operator_view)
from core import Config  # noqa: E402
from memory import FeedbackMemory, MemoryStore  # noqa: E402
from pipeline import Pipeline  # noqa: E402
from resource_budget import ResourceBroker  # noqa: E402
from review_contract import _rebind_subjects, candidate_from_dict  # noqa: E402


def reevaluate(record: dict) -> dict:
    pair = deepcopy(record["internal_pair"])
    runner = PairedArchitectureRunner(live=False)
    for arm in pair["arms"]:
        output = (arm.get("discovery_trace") or {}).get("output") or {}
        artifacts = output.get("stage_artifacts") or {}
        # M2: Nach einer Nachrecherche ist deren Zwischenstand fuehrend.
        post = artifacts.get("post_follow_up") or artifacts.get("post_architecture_review") or []
        broker = ResourceBroker(runner.budget.resource_limits())
        pipeline = Pipeline(live=False, memory=FeedbackMemory(MemoryStore(read_only=True)),
                            resource_broker=broker, audit_write=False)
        pipeline.last_opportunity_plan = output.get("opportunity_plan") or {}
        task = pair.get("task") or {}
        if task.get("organization_id") and task.get("organization_name"):
            # Wie Pipeline.run im Live-Pfad: Zielorganisation task-lokal binden,
            # sonst bleibt die Match-Liste leer und jede Empfehlung entfaellt.
            pipeline.kb.bind_task_organization(
                task["organization_id"], task["organization_name"],
                public_url="", search_field=dict(task.get("search_field") or {}))
        candidates = [candidate_from_dict(item) for item in post]
        for candidate in candidates:  # wie apply_review im aktuellen Stand
            _rebind_subjects(candidate, candidate.sources, candidate.evidence_claims)
        pipeline.resolver.resolve_candidates(
            candidates, max_fetches_total=runner.budget.max_resolver_fetches)
        target = (pair.get("task") or {}).get("organization_id", "")
        decisions = [pipeline.scout(c, use_guardrail=True, use_memory=False,
                                    target_actor_id=target).to_dict()
                     for c in candidates]
        # Modellstufen waren gueltig, wenn beide Stufen abgeschlossen sind.
        model_ok = all(str(u.get("status")) == "completed" for u in arm.get("usage") or [])
        arm["decisions"] = decisions
        arm["decision_states"] = [d.get("decision_state") for d in decisions]
        arm["positive_candidate_ids"] = [
            (d.get("candidate") or {}).get("candidate_id") for d in decisions
            if d.get("decision_state") == "empfehlung"]
        arm["result_status"] = runner._status_from_decisions(decisions, not model_ok)
        if model_ok:
            # Der fruehere Stufenfehler entstand allein aus dem Quellenabruf und
            # gilt nach der Neubewertung nicht mehr.
            usage = arm.setdefault("resource_usage", {})
            usage["failure_reasons"] = [
                reason for reason in usage.get("failure_reasons") or []
                if reason != "architecture_stage_failure"]
            usage["technical_failure"] = bool(usage["failure_reasons"])
        arm["primary_analysis_eligible"] = arm["result_status"] in {"completed", "abstention"}
        arm["primary_exclusion_reason"] = "" if arm["primary_analysis_eligible"] else arm["result_status"]
        arm["reevaluation"] = {
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "rule_version": Config.VERSION,
            "note": "Deterministische Neubewertung gespeicherter Modellantworten; keine API-Aufrufe.",
            "original_result_status": record["internal_pair"]["arms"][pair["arms"].index(arm)]["result_status"],
            "resolver_fetches": broker.summary()["resolver_fetches"],
        }
    return pair


def main() -> int:
    for path in sys.argv[1:]:
        source = Path(path)
        record = json.loads(source.read_text(encoding="utf-8"))
        if "internal_pair" not in record and record.get("internal_pairs"):
            record["internal_pair"] = record["internal_pairs"][0]
        pair = reevaluate(record)
        run_id = source.stem + "-neubewertet"
        created = datetime.datetime.now(datetime.timezone.utc).isoformat()
        view = operator_view([pair], run_id=run_id, created_at=created)
        view["reevaluated_from"] = source.stem
        out = {"operator_view": view,
               "blind_pairs": [{"blind_annotation": annotation_package(pair)}],
               "assignment_manifests": [assignment_manifest(pair)],
               "internal_pair": pair}
        (source.parent / f"{run_id}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        for arm in pair["arms"]:
            print(json.dumps({"run": run_id, "arm": arm["architecture_internal"],
                              "status": arm["result_status"],
                              "states": arm["decision_states"],
                              "was": arm["reevaluation"]["original_result_status"],
                              "candidates": [d["candidate"]["name"] for d in arm["decisions"]],
                              "reasons": [d.get("decision_state_reason") for d in arm["decisions"]]},
                             ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
