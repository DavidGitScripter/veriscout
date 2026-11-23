"""Kleine, transparente Wissensbasis des Referenzmodells.

Die Datei ``actors.json`` enthaelt nur optionale Demo- oder Instanzdaten. Eine
produktive Zielorganisation wird fuer einen Vergleich ausschliesslich aus dem
kanonischen Aufgabenvertrag gebunden. Dieser Kontext lebt nur in der aktuellen
``KnowledgeBase``-Instanz und wird weder in ``actors.json`` geschrieben noch in
einen spaeteren Auftrag uebernommen.
"""
from __future__ import annotations

import json
from core import Config, tokenize, overlap_count


class KnowledgeBase:
    def __init__(self, path: str = None):
        path = path or Config.ACTORS_PATH
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.meta = data.get("meta", {})
        self.actors = data["actors"]
        self._by_id = {a["id"]: a for a in self.actors}
        # Trigger-Tokens je Akteur vorberechnen
        self._trigger_tokens = {}
        for a in self.actors:
            toks = set()
            for trig in a.get("scouting_triggers", []):
                toks |= tokenize(trig)
            for s in a.get("sectors", []):
                toks |= tokenize(s)
            self._trigger_tokens[a["id"]] = toks
        self._task_actor: dict | None = None
        self._task_trigger_tokens: set = set()

    def bind_task_organization(
            self, organization_id: str, organization_name: str, *,
            public_url: str = "", search_field: dict | None = None) -> dict:
        """Bindet genau eine nicht persistente Zielorganisation.

        Nur explizit uebergebene, oeffentliche Auftragsdaten werden verwendet.
        Insbesondere werden keine gespeicherten Branchen, Prozesse oder
        Suchfelder anhand einer gleichlautenden ID beigemischt. So erhalten SAS
        und MAS bei getrennten Pipeline-Instanzen denselben task-lokalen Kontext.
        """
        organization_id = str(organization_id or "").strip()
        organization_name = str(organization_name or "").strip()
        if not organization_id or not organization_name:
            raise ValueError(
                "Task-lokaler Organisationskontext braucht ID und Name.")

        field = dict(search_field or {})
        trigger_values = [
            field.get("title") or field.get("themengebiet") or "",
            field.get("description") or field.get("beschreibung") or "",
        ]
        trigger_tokens = set()
        for value in trigger_values:
            trigger_tokens |= tokenize(str(value or ""))

        self._task_actor = {
            "id": organization_id,
            "name": organization_name,
            "rolle": "Task-lokale Zielorganisation",
            "public_url": str(public_url or "").strip(),
            "sectors": [],
            "scouting_triggers": [
                value for value in trigger_values if str(value or "").strip()
            ],
            "kerngeschaeft": "",
            "scope": "task_local",
        }
        self._task_trigger_tokens = trigger_tokens
        return dict(self._task_actor)

    def clear_task_organization(self) -> None:
        """Entfernt den Laufzeitkontext vor dem naechsten Auftrag."""
        self._task_actor = None
        self._task_trigger_tokens = set()

    def _active_actors(self) -> list[dict]:
        if not self._task_actor:
            return list(self.actors)
        task_id = self._task_actor["id"]
        # Der Auftragskontext hat bei einer ID-Kollision Vorrang. Dadurch kann
        # kein gespeichertes Profil unbemerkt in den Vergleich einfließen.
        return [a for a in self.actors if a.get("id") != task_id] + [
            self._task_actor]

    def get(self, actor_id: str) -> dict:
        if self._task_actor and actor_id == self._task_actor.get("id"):
            return self._task_actor
        return self._by_id[actor_id]

    def all_ids(self) -> list:
        return [a["id"] for a in self._active_actors()]

    def trigger_tokens(self, actor_id: str) -> set:
        if self._task_actor and actor_id == self._task_actor.get("id"):
            return set(self._task_trigger_tokens)
        return self._trigger_tokens.get(actor_id, set())

    def retrieve(self, text: str, top_k: int = 5) -> list:
        """RAG-lite: Akteure nach Trigger-Ueberlappung mit dem Text ranken.
        top_k=None -> ALLE Akteure (auch ohne Trigger-Treffer), fuer das
        vollstaendige Matching gegen alle optionalen Demo-Entitaeten."""
        cand = tokenize(text)
        scored = []
        for a in self._active_actors():
            actor_tokens = self.trigger_tokens(a["id"])
            ov = overlap_count(cand, actor_tokens)
            if top_k is None or ov > 0:
                scored.append((a["id"], ov, sorted(cand & actor_tokens)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored if top_k is None else scored[:top_k]

    def data_vintage(self) -> str:
        return self.meta.get("letzte_verifizierung", Config.DATA_VINTAGE)
