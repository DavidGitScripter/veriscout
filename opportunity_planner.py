"""Generischer PUSH-Auftrag aus genau einem oeffentlichen Suchfeld.

Der Planer enthaelt bewusst keine unternehmensspezifischen Prozessannahmen,
keine vorgegebenen Innovationshypothesen und keine kuratierten Startup-Treffer.
Die ausgewaehlte Organisation wird im Live-Lauf aus oeffentlichen Quellen gescannt;
unbelegte Prozesse bleiben unknown bzw. klar gekennzeichnete Hypothesen.
"""
from __future__ import annotations

import hashlib
import json
import re

from core import Config


class OpportunityPlanner:
    def __init__(self, kb):
        self.kb = kb

    def _profile_sources(self, actor_id: str) -> list[dict]:
        """Liefert nur Dokumente derselben Zielorganisation."""
        actor = self.kb.get(actor_id)
        normalise = lambda value: re.sub(
            r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
        accepted = {
            normalise(actor_id),
            normalise(actor_id.replace("_", " ")),
            normalise(actor.get("name", "")),
        }
        try:
            with open(Config.PROFILE_SOURCES_PATH, encoding="utf-8") as handle:
                documents = json.load(handle).get("documents", [])
        except Exception:
            return []
        result = []
        for document in documents:
            organization = normalise(
                document.get("organization_id")
                or document.get("organization_name")
                or document.get("member_company"))
            if organization not in accepted:
                continue
            result.append({
                "document_id": document.get("document_id", ""),
                "organization_id": actor_id,
                "subject_type": "target_organization",
                "subject_id": actor_id,
                "subject_name": actor.get("name", ""),
                "classification": "public",
                "title": document.get("title", ""),
                "publisher": document.get("publisher", ""),
                "url": document.get("url", ""),
                "published_at": document.get("published_at"),
                "retrieved_at": document.get("retrieved_at", ""),
                "status": document.get("status", ""),
                "evidence": [{
                    **dict(evidence),
                    "subject_type": "target_organization",
                    "subject_id": actor_id,
                    "subject_name": actor.get("name", ""),
                } for evidence in (document.get("evidence", []) or [])
                    if isinstance(evidence, dict)],
            })
        return result

    @staticmethod
    def _id(actor_id: str, theme_id: str, title: str) -> str:
        digest = hashlib.sha256(
            f"{actor_id}|{theme_id}|{title}".encode("utf-8")).hexdigest()[:10]
        return f"opp-{actor_id}-{digest}"

    @staticmethod
    def _public_fields(actor_id: str, themes: list | None) -> list[dict]:
        fields = []
        for theme in themes or []:
            if theme.get("actor_id") != actor_id:
                continue
            if str(theme.get("typ") or "oeffentlich").casefold() not in {
                    "oeffentlich", "public"}:
                continue
            fields.append({
                "theme_id": str(theme.get("theme_id") or theme.get("id") or ""),
                "title": str(theme.get("title") or theme.get("themengebiet") or ""),
                "description": str(theme.get("description") or
                                   theme.get("beschreibung") or ""),
                "source": {
                    "classification": "public",
                    "label": str(theme.get("quelle") or ""),
                    "url": str(theme.get("source_url") or ""),
                    "excerpt": str(theme.get("source_excerpt") or ""),
                    "retrieved_at": str(theme.get("source_retrieved_at") or ""),
                },
            })
        return fields

    def seed_candidates(self, actor_id: str, plan: dict) -> list:
        """Keine Vorbefuellung im neuen PUSH-Protokoll."""
        return []

    @staticmethod
    def build_task_plan(*, organization_id: str, organization_name: str,
                        organization_domain_hint: str, search_field: dict,
                        public_sources: list[dict]) -> dict:
        """Erzeugt einen Plan allein aus dem eingefrorenen Aufgabenvertrag.

        Diese Methode liest bewusst weder ``actors.json`` noch einen
        organisationsspezifischen Themenkatalog. Sie ist damit der gemeinsame
        Planungskontext fuer beide Architekturen im gepaarten Vergleich.
        """
        return {
            "mode": "public_only_comparison",
            "target_organization_id": organization_id,
            # Alias bleibt fuer die bestehende Urteilspipeline intern erhalten.
            "target_actor_id": organization_id,
            "organization_name": organization_name,
            "organization_domain_hint": organization_domain_hint,
            "public_search_fields": [dict(search_field or {})],
            "public_sources": [dict(source) for source in public_sources],
            "opportunities": [],
            "curated_leads": [],
            "boundary": (
                "public-only; nicht belegte Prozesse bleiben unknown oder "
                "ausdruecklich gekennzeichnete Hypothesen"
            ),
        }

    def build(self, actor_id: str, themes: list | None = None) -> dict:
        actor = self.kb.get(actor_id)
        fields = self._public_fields(actor_id, themes)
        opportunities = [{
            "id": self._id(actor_id, field["theme_id"], field["title"]),
            "lens": field["theme_id"],
            "title": field["title"],
            "hypothesis": (
                "Zu pruefen ist, welcher oeffentlich belegte Prozess des "
                "Zielorganisation innerhalb dieses Suchfelds durch die oeffentlich "
                "belegte Faehigkeit eines Startups nachhaltiger und/oder "
                "effizienter werden kann. Eine Profitabilitaetswirkung bleibt "
                "bis zu ihrer Messung eine Wirkungshypothese."
            ),
            "required_evidence": [
                "konkreter oeffentlicher Beleg des Organisationsprozesses",
                "konkreter oeffentlicher Beleg der Startup-Faehigkeit",
                "belegte oder offen zu pruefende technische Schnittstelle",
                "klar getrennte Fakten, Widersprueche und Unknowns",
            ],
            "search_terms": [],
            "status": "public_field_to_scan",
        } for field in fields]
        return {
            "mode": "push_public_only",
            "target_actor_id": actor_id,
            "organization_name": actor["name"],
            # Diese Kurzbeschreibung ist nur Orientierung und kein Prozessbeleg.
            "public_core_business": actor.get("kerngeschaeft", ""),
            "public_search_fields": fields,
            "public_sources": self._profile_sources(actor_id),
            "curated_leads": [],
            "opportunities": opportunities,
            "boundary": (
                "Nur oeffentliche Angaben derselben Zielorganisation verwenden. "
                "Prozesse ohne konkreten Beleg als unknown oder Hypothese markieren."
            ),
        }

    def build_prompt(self, actor_id: str,
                     themes: list | None = None) -> tuple[str, dict]:
        plan = self.build(actor_id, themes)
        fields = plan["public_search_fields"]
        if len(fields) != 1:
            raise ValueError(
                "PUSH-Suche braucht exakt ein oeffentliches Suchfeld fuer die Zielorganisation.")
        field = fields[0]
        source_lines = []
        for source in plan["public_sources"]:
            source_lines.append(
                f"- {source['document_id']} | {source['title']} | {source['url']} | "
                "Nur konkrete, nicht als Platzhalter markierte Auszuege sind Fakten.")
        sources = "\n".join(source_lines) or "- keine eingefrorene Ausgangsquelle"
        prompt = (
            f"PUBLIC-ONLY PUSH-Suche fuer {plan['organization_name']} "
            f"(verbindliche Ziel-ID: {actor_id}).\n"
            "Exakt ein vorab festgelegtes Suchfeld:\n"
            f"- {field['theme_id']} | {field['title']}: {field['description']}\n"
            f"Quellenhinweis zum Suchfeld: {json.dumps(field['source'], ensure_ascii=False)}\n\n"
            "Oeffentliches Ausgangsquellenpaket derselben Zielorganisation:\n" + sources + "\n\n"
            "Scanne die Zielorganisation zuerst selbst aus oeffentlichen Primaerquellen. "
            "Nutze einen Prozess, Input oder Output nur dann als Fakt, wenn ein "
            "konkreter Belegauszug ihn stuetzt. Alles andere bleibt unknown oder "
            "eine klar bezeichnete Hypothese. Suche anschliessend reale B2B-Startups, "
            "deren oeffentlich belegte Faehigkeit an den belegten Teil des "
            "Suchfelds anknuepft. Branchennaehe allein reicht nicht. Nachhaltigkeits-, "
            "Effizienz- und Profitabilitaetswirkungen sind ohne Messung keine Fakten."
        )
        return prompt, plan
