"""Portable task instances and a formative transfer protocol, without API calls.

An instance changes the research question's application, not the experimental
policy. Hashes detect changes, they do not authenticate a participant or prove
the correctness of a search result. No credentials or company lists are stored.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

SCHEMA_VERSION = "venturescout.workspace.v1"
PROTOCOL_VERSION = "transfer-2026-09-24.v1"
MAX_BYTES = 16384
FIELDS = {"schema_version", "name", "organization_name", "search_prompt", "event_time"}
RECEIPT_FIELDS = {"workspace", "workspace_sha256", "policy_sha256", "release_sha256"}


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).hexdigest()


def validate_workspace(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("Projektdatei hat fehlende oder unbekannte Felder. Keine Zugangsdaten oder Ergebnisdaten importieren.")
    if value["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Diese Version der Projektdatei wird nicht unterstützt.")
    limits = {"name": (2, 100), "organization_name": (2, 160),
              "search_prompt": (30, 2000), "event_time": (20, 40)}
    result = {"schema_version": SCHEMA_VERSION}
    for key, (minimum, maximum) in limits.items():
        raw = value[key]
        if not isinstance(raw, str):
            raise ValueError(f"{key} muss Text enthalten.")
        text = raw.strip()
        if not minimum <= len(text) <= maximum:
            raise ValueError(f"{key}: Erforderlich sind {minimum} bis {maximum} Zeichen.")
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text):
            raise ValueError("Steuerzeichen sind nicht zulässig.")
        # This is a precaution, not a classifier for all confidential text.
        if re.search(r"\bsk-[A-Za-z0-9_-]{16,}|-----BEGIN .*PRIVATE KEY-----", text):
            raise ValueError("Möglicher Zugangsschlüssel erkannt. Nur öffentliche Angaben verwenden.")
        result[key] = text
    try:
        event = datetime.fromisoformat(result["event_time"].replace("Z", "+00:00"))
        if event.utcoffset() is None:
            raise ValueError()
    except ValueError:
        raise ValueError("Auftragszeitpunkt benötigt Datum, Uhrzeit und Zeitzone.") from None
    result["event_time"] = event.astimezone(timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")
    return result


def unpack_workspace(value: object) -> tuple[dict, dict]:
    """Accept a new task or an exported receipt. Never accept policy overrides."""
    if isinstance(value, dict) and "workspace" in value:
        if set(value) != RECEIPT_FIELDS:
            raise ValueError("Ungültiges Exportformat oder zusätzliche Felder.")
        for field in RECEIPT_FIELDS - {"workspace"}:
            if not isinstance(value[field], str) or not re.fullmatch(r"[a-f0-9]{64}", value[field]):
                raise ValueError("Ungültiger Fingerabdruck in der Projektdatei.")
        workspace = validate_workspace(value["workspace"])
        if digest(workspace) != value["workspace_sha256"]:
            raise ValueError("Projektinhalt wurde nach dem Export verändert. Als neuen Auftrag anlegen.")
        return workspace, {key: value[key] for key in RECEIPT_FIELDS - {"workspace"}}
    return validate_workspace(value), {}


def request_for_workspace(workspace: dict) -> dict:
    clean = validate_workspace(workspace)
    return {"organization_name": clean["organization_name"],
            "search_prompt": clean["search_prompt"], "event_time": clean["event_time"],
            "dataset_split": "pilot", "memory_mode": "off", "repetitions": 1,
            "baseline": "sas2", "confirm_live": False}


def protocol() -> dict:
    return {
        "version": PROTOCOL_VERSION,
        "purpose": "Formative Einzelfallprüfung von Instanziierung, Portabilität und Modellverständnis",
        "paid_calls": 0,
        "tasks": [
            {"id": "T1", "title": "Modell verstehen", "minutes": 8,
             "instruction": "Erkläre mit eigenen Worten die beiden Recherchewege. Nenne veränderbare Eingaben und Regeln, die unverändert bleiben müssen.",
             "criterion": "Organisation und Suchziel als Variation erkannt. Gleicher Input, Evidenzprüfung und menschliche Entscheidung als Kontrollkern erkannt."},
            {"id": "T2", "title": "Ersten Fall einrichten", "minutes": 12,
             "instruction": "Wähle eine reale Organisation aus einer dir zugänglichen Branche. Formuliere aus öffentlichen Informationen einen eigenen Suchauftrag. Prüfe die kostenlose Vorschau und exportiere das Projekt.",
             "criterion": "Valider Auftrag ohne Codeänderung. Keine internen Prozessdaten. Export und Auftrag-Fingerabdruck dokumentiert."},
            {"id": "T3", "title": "Zweiten Kontext übertragen", "minutes": 12,
             "instruction": "Wähle Neues Projekt und richte eine zweite Organisation aus einer anderen Branche ein. Verwende einen eigenen Suchauftrag. Prüfe, ob Inhalte des ersten Falls zurückbleiben.",
             "criterion": "Zweiter eigenständiger Auftrag. Erster Fall nicht überschrieben oder als Kontext übernommen. Gleiche Kontrollregeln."},
            {"id": "T4", "title": "Ersten Fall wiederherstellen", "minutes": 8,
             "instruction": "Öffne einen neuen Browser-Tab. Importiere dort die zuvor exportierte Datei des ersten Falls. Vergleiche Projekt-Fingerabdruck, kanonischen Auftrag und Auftragszeitpunkt mit dem Export.",
             "criterion": "Unveränderter Projekt-Fingerabdruck und Auftrag nach Import. Keine erneute Programmierung oder Quelleingabe."},
            {"id": "T5", "title": "Fehlerfall erkennen", "minutes": 5,
             "instruction": "Lade die bereitgestellte ungültige Testdatei herunter und versuche sie zu importieren. Beschreibe die Meldung und prüfe, ob der bisherige Auftrag unverändert bleibt.",
             "criterion": "Import wird verständlich abgewiesen. Aktueller Auftrag und feste Qualitätsregeln bleiben unverändert."},
            {"id": "T6", "title": "Modellgrenzen erklären", "minutes": 10,
             "instruction": "Nutze den Modellleitfaden. Erkläre, was bei fehlenden Belegen geschieht, wer über eine Kooperation entscheidet und welche fachlichen Fragen ein Discovery-Call klären muss. Ordne den eigenen neuen Anwendungsfall dem Modell zu.",
             "criterion": "Enthaltung und technischer Fehler unterschieden. Belegter Suchtreffer nicht mit bestätigter Kooperation verwechselt. Fehlende Domänenkenntnis ausdrücklich benannt."},
        ],
        "outcomes": ["independent", "assisted", "blocked", "not_observed"],
        "limitations": [
            "Ein Teilnehmer und zwei Kontexte erlauben keine statistische Generalisierung.",
            "UI/UX-Expertise ersetzt kein Fachurteil über industrielle Kooperationen.",
            "Browserereignisse und Beobachterurteile sind getrennte Nachweise, keine manipulationssichere Messung.",
            "Zeitziele sind vorläufige projektspezifische Prüfkriterien, keine Literatur-Grenzwerte.",
        ],
    }
