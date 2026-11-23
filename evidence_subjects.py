"""Gemeinsamer Vertrag fuer die Subjektbindung von Quellen und Claims.

Eine technisch gueltige Quelle ist noch kein Beleg fuer das richtige Subjekt.
Im Live-Pfad muss deshalb jede Quelle und jeder atomare Claim explizit an die
Zielorganisation, das Kandidaten-Startup oder die konkrete Relation gebunden
sein. Fehlende oder widerspruechliche Bindungen werden niemals erraten.
"""
from __future__ import annotations

import re


SUBJECT_TYPES = {
    "target_organization",
    "candidate_startup",
    "relation",
}

FIELD_SUBJECT_TYPE = {
    "target_identity": "target_organization",
    "target_process": "target_organization",
    "input_stream": "target_organization",
    "identity": "candidate_startup",
    "startup_status": "candidate_startup",
    "startup_capability": "candidate_startup",
    "transformation": "candidate_startup",
    "output_application": "candidate_startup",
    "relational_chain": "relation",
    "public_search_field": "target_organization",
}


def _value(record, name: str) -> str:
    if isinstance(record, dict):
        return str(record.get(name) or "").strip()
    return str(getattr(record, name, "") or "").strip()


def normalise_subject_type(value: str) -> str:
    value = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "target": "target_organization",
        "target_org": "target_organization",
        "organization": "target_organization",
        "organisation": "target_organization",
        "candidate": "candidate_startup",
        "startup": "candidate_startup",
    }
    return aliases.get(value, value)


def normalise_subject_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def expected_subject(field_name: str) -> str:
    return FIELD_SUBJECT_TYPE.get(str(field_name or "").strip().casefold(), "")


def subject_binding(record) -> tuple[str, str, str]:
    return (
        normalise_subject_type(_value(record, "subject_type")),
        _value(record, "subject_id"),
        _value(record, "subject_name"),
    )


def subject_matches(record, *, subject_type: str, subject_id: str = "",
                    subject_name: str = "", strict: bool = True) -> bool:
    """Prueft Typ und Identitaet einer Bindung konservativ.

    Sind ID und Name beide angegeben, muessen auch beide zum kanonischen
    Subjekt passen. Damit kann ein korrekter Name keine fremde ID verdecken.
    Im nicht-strikten Modus bleiben alte, noch ungebundene Test-/Korpusobjekte
    lesbar; eine explizit falsche Bindung wird dennoch stets abgelehnt.
    """
    actual_type, actual_id, actual_name = subject_binding(record)
    required_type = normalise_subject_type(subject_type)
    if actual_type:
        if actual_type not in SUBJECT_TYPES or actual_type != required_type:
            return False
    elif strict:
        return False

    if not actual_id and not actual_name:
        return not strict

    checks: list[bool] = []
    if actual_id:
        checks.append(bool(subject_id) and
                      normalise_subject_key(actual_id) == normalise_subject_key(subject_id))
    if actual_name:
        checks.append(bool(subject_name) and
                      normalise_subject_key(actual_name) == normalise_subject_key(subject_name))
    return bool(checks) and all(checks)


def subjects_compatible(left, right) -> bool:
    """Prueft, ob zwei explizite Bindungen dasselbe Subjekt bezeichnen."""
    left_type, left_id, left_name = subject_binding(left)
    right_type, right_id, right_name = subject_binding(right)
    if not left_type or not right_type or left_type != right_type:
        return False
    comparisons: list[bool] = []
    if left_id and right_id:
        comparisons.append(normalise_subject_key(left_id) == normalise_subject_key(right_id))
    if left_name and right_name:
        comparisons.append(normalise_subject_key(left_name) == normalise_subject_key(right_name))
    # Unterschiedliche Darstellungsformen (ID auf einer, Name auf der anderen
    # Seite) werden ueber die kanonische Erwartungspruefung des Aufrufers
    # verbunden. Ohne irgendeine direkt vergleichbare Angabe ist die Paarung
    # hier allein noch nicht bestaetigt.
    return bool(comparisons) and all(comparisons)
