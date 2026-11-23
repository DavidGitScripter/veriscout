"""Fallblatt je Aufgabe: Referenzmaterial fuer die Bewertenden.

Das Fallblatt beschreibt die Zielorganisation aus oeffentlichen Quellen
(Kap. 7, Abschnitt "Referenzurteile": erwarteter Zustand, relevante Evidenz,
Ausschlusskriterien und Unsicherheiten werden festgelegt, bevor das System
den Fall bearbeitet).

Es ist Referenzmaterial und darf die Architekturen nie erreichen: Es wird
weder in den Suchauftrag noch in einen Prompt uebernommen, sondern getrennt
in der Laufdatei verwahrt und nur ins Blindpaket fuer die Bewertenden
gegeben. Der Fingerabdruck bindet den Stand vor dem Lauf.
"""
from __future__ import annotations

import hashlib
import json
from urllib.parse import urlparse

CASE_SHEET_SCHEMA_VERSION = "veriscout-case-sheet-v1"
MAX_TEXT = 2000
MAX_ITEMS = 12


def _text(value: object, limit: int = MAX_TEXT) -> str:
    return " ".join(str(value or "").split())[:limit]


def _public_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _lines(value: object) -> list[str]:
    if isinstance(value, str):
        items = value.splitlines()
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = []
    return [_text(item, 600) for item in items if _text(item, 600)][:MAX_ITEMS]


def _processes(value: object) -> list[dict]:
    """Prozesse als Liste {text, source_url}; Textform "Prozess | URL" je Zeile."""
    rows = []
    if isinstance(value, str):
        raw = []
        for line in value.splitlines():
            text, _, url = line.partition("|")
            raw.append({"text": text, "source_url": url})
    elif isinstance(value, (list, tuple)):
        raw = list(value)
    else:
        raw = []
    for item in raw:
        if isinstance(item, str):
            text, _, url = item.partition("|")
            item = {"text": text, "source_url": url}
        if not isinstance(item, dict):
            continue
        text = _text(item.get("text"), 600)
        url = _text(item.get("source_url"), 500)
        if not text:
            continue
        if url and not _public_url(url):
            raise ValueError("Fallblatt: Prozessquelle muss eine oeffentliche "
                             "http(s)-Adresse sein.")
        rows.append({"text": text, "source_url": url})
    return rows[:MAX_ITEMS]


def normalise_case_sheet(value: object) -> dict | None:
    """Prueft und normalisiert ein Fallblatt; None, wenn keines angegeben ist."""
    if value in (None, "", {}):
        return None
    if not isinstance(value, dict):
        raise ValueError("Fallblatt muss ein Objekt sein.")
    sheet = {
        "schema_version": CASE_SHEET_SCHEMA_VERSION,
        "organization_name": _text(value.get("organization_name"), 200),
        "website": _text(value.get("website"), 300),
        "industry": _text(value.get("industry"), 200),
        "profile": _text(value.get("profile")),
        "processes": _processes(value.get("processes")),
        "need": _text(value.get("need")),
        "search_area": _text(value.get("search_area"), 300),
        "exclusion_criteria": _lines(value.get("exclusion_criteria")),
        "uncertainties": _lines(value.get("uncertainties")),
        "author": _text(value.get("author"), 120),
        "created_at": _text(value.get("created_at"), 40),
        # Zusicherung der verfassenden Person, nur oeffentliche Quellen und
        # kein Wissen aus vertraulicher Scouting-Taetigkeit zu verwenden.
        "public_sources_only": bool(value.get("public_sources_only", False)),
    }
    if sheet["website"] and not _public_url(sheet["website"]):
        raise ValueError("Fallblatt: Website muss eine http(s)-Adresse sein.")
    if not (sheet["profile"] or sheet["processes"]):
        raise ValueError("Fallblatt braucht mindestens Kurzprofil oder einen "
                         "belegten Prozess.")
    if not sheet["public_sources_only"]:
        raise ValueError("Fallblatt: Bitte bestaetigen, dass nur oeffentliche "
                         "Quellen verwendet wurden.")
    return sheet


def case_sheet_hash(sheet: dict | None) -> str:
    if not sheet:
        return ""
    raw = json.dumps(sheet, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return "casesheet-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def case_sheet_text(sheet: dict | None) -> str:
    """Lesbare Textfassung, z. B. fuer Tests auf Prompt-Freiheit."""
    if not sheet:
        return ""
    parts = [sheet.get("organization_name", ""), sheet.get("industry", ""),
             sheet.get("profile", ""), sheet.get("need", ""),
             sheet.get("search_area", "")]
    parts += [item["text"] for item in sheet.get("processes") or []]
    parts += list(sheet.get("exclusion_criteria") or [])
    parts += list(sheet.get("uncertainties") or [])
    return "\n".join(part for part in parts if part)
