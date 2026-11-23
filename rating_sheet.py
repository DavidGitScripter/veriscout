"""Offline-Bewertungsbogen, Bewertungsschluessel und Zusammenfuehrung.

Ablauf (Kap. 7, Referenzurteile):
1. Aus den Blindpaketen der Studienlaeufe entsteht ein Bewertungsschluessel
   (bleibt bei der Versuchsleitung) und ein Bewertungsbogen als einzelne
   HTML-Datei, die ohne Server und ohne Internet im Browser laeuft.
2. Zwei Personen bewerten unabhaengig: je Kriterium ja, nein oder nicht
   beurteilbar. Startup-bezogene Kriterien (gueltig, pruefwuerdig) werden je
   Aufgabe und Startup einmal beurteilt, auch wenn das Startup in mehreren
   Laeufen vorkommt. Darstellungsbezogene Kriterien (Zusammenhang, Belege,
   Schoenfaerberei) werden je Darstellung beurteilt, weil jedes System
   andere Aussagen und Belege liefert.
3. Die Zusammenfuehrung zeigt Abweichungen, nimmt die dokumentierte Einigung
   auf und erzeugt die finale Bewertungsdatei fuer die Auswertung.

Der Bogen enthaelt weder Architekturbezeichnungen noch Arm-Kennungen; die
Zuordnung der Einheiten zu Paaren und Armen steht nur im Schluessel.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
from collections import defaultdict
from urllib.parse import urlparse

from case_sheet import case_sheet_hash
from evaluation_analysis import (ANNOTATION_SCHEMA_VERSION_V2, BOOLEAN_METRICS,
                                 DISPUTED, ENTITY_METRICS, NOT_ASSESSABLE,
                                 OCCURRENCE_METRICS, krippendorff_alpha_nominal)

KEY_SCHEMA_VERSION = "veriscout-rating-key-v1"
RATINGS_SCHEMA_VERSION = "veriscout-ratings-v1"
FINAL_SCHEMA_VERSION = "veriscout-final-annotations-v1"

CODEBOOK = {
    "valid_entity": {
        "label": "Startup gültig und aktiv",
        "question": "Gibt es dieses Startup wirklich, mit eigenem Angebot, und ist es zum Suchzeitpunkt aktiv?",
        "help": ("Ja, wenn das Unternehmen unter diesem Namen und dieser Website existiert, ein eigenes "
                 "Angebot hat und aktiv ist, also nicht übernommen, insolvent oder eingestellt. Prüfe "
                 "Website, Impressum oder ein Register. Nein, wenn es nicht existiert, nicht mehr aktiv "
                 "ist oder nur ein Forschungsprojekt ohne Angebot ist. Nicht beurteilbar, wenn du das "
                 "in etwa fünf Minuten nicht klären kannst."),
    },
    "qualified": {
        "label": "Prüfwürdige Kooperationsidee",
        "question": "Ist dieses Startup für diesen Suchauftrag eine prüfwürdige Kooperationsidee, die ein Erstgespräch rechtfertigt?",
        "help": ("Ja nur, wenn alle vier Bedingungen erfüllt sind: (1) das Startup ist gültig und aktiv, "
                 "(2) es gibt einen plausiblen Zusammenhang zu einem Prozess des Unternehmens aus dem "
                 "Fallblatt oder aus den Belegen, (3) die Kernaussagen über das Angebot des Startups sind "
                 "belegt, (4) kein Ausschlusskriterium aus dem Fallblatt greift. Beurteile das Startup "
                 "selbst, nicht die Qualität einer einzelnen Darstellung. Die wirtschaftliche "
                 "Tragfähigkeit musst du nicht beurteilen; sie wird im Erstgespräch geklärt."),
    },
    "relation_correct": {
        "label": "Zusammenhang stimmig",
        "question": "Ist die dargestellte Kette aus Prozess, Input oder Ressource, Fähigkeit des Startups und nutzbarem Ergebnis fachlich stimmig?",
        "help": ("Ja, wenn jedes Glied der Kette zu diesem Unternehmen und diesem Startup passt. Nein, "
                 "wenn ein Glied falsch ist oder die Glieder nicht zusammenpassen. Nicht beurteilbar, "
                 "wenn dafür Fachwissen nötig ist, das du nicht hast."),
    },
    "claim_support_complete": {
        "label": "Belege tragen die Aussagen",
        "question": "Ist jede Kernaussage dieser Darstellung durch den angegebenen Auszug gedeckt?",
        "help": ("Öffne mindestens eine Quelle je Darstellung. Ja, wenn die Kernaussagen durch die "
                 "Auszüge gedeckt sind und die Auszüge auf den verlinkten Seiten stehen. Nein, wenn eine "
                 "Kernaussage unbelegt ist, der Auszug etwas anderes sagt oder die Seite den Auszug nicht "
                 "enthält."),
    },
    "over_match": {
        "label": "Schönfärberei",
        "question": "Behauptet oder übertreibt die Darstellung einen Zusammenhang, den die Belege nicht hergeben?",
        "help": ("Ja (das ist ein Mangel), wenn nur thematische Nähe besteht, aber eine Lösung behauptet "
                 "wird, oder wenn ein Nutzen ohne Grundlage versprochen wird. Nein, wenn die Darstellung "
                 "bei dem bleibt, was belegt ist."),
    },
}

RULES = [
    "Arbeite allein und sprich dich bis zum Einigungsgespräch nicht mit der anderen bewertenden Person ab.",
    "Du erfährst nicht, von welchem System eine Darstellung stammt. Versuche nicht, das zu erraten.",
    "Du darfst im Web recherchieren, aber keine KI-Chatbots für deine Urteile nutzen.",
    "Grundlage ist, was öffentlich belegbar ist. Internes Wissen über das Unternehmen wird nicht vorausgesetzt.",
    "Nicht beurteilbar ist eine gültige Antwort. Nutze sie, wenn das Material oder dein Fachwissen nicht reicht, und begründe kurz.",
]

_LEGAL_FORMS = re.compile(
    r"\b(gmbh|ag|ug|se|kg|ohg|e\.?\s?k|e\.?\s?v|gbr|co|inc|ltd|llc|sas|sarl|bv|b\.v|"
    r"oy|ab|as|s\.?a|s\.?r\.?l|plc|limited|haftungsbeschraenkt|haftungsbeschränkt)\b\.?")


def _domain(candidate: dict) -> str:
    website = str(candidate.get("website") or candidate.get("official_url") or "").strip()
    if not website:
        return ""
    if "://" not in website:
        website = "https://" + website
    host = (urlparse(website).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _norm_name(candidate: dict) -> str:
    name = str(candidate.get("name") or "").casefold()
    name = _LEGAL_FORMS.sub(" ", name)
    return re.sub(r"[^0-9a-zäöüß]+", " ", name).strip()


def entity_key(candidate: dict) -> str:
    """Startup-Kennung: Website-Domain, sonst normalisierter Name."""
    domain = _domain(candidate)
    if domain:
        return "domain:" + domain
    return "name:" + (_norm_name(candidate) or "unbekannt")


def _entity_groups(items: list[tuple[str, dict]]) -> dict[int, str]:
    """Fasst Vorkommen je Aufgabe zusammen, die Domain oder Namen teilen.

    ``items`` sind (task_id, candidate); Rueckgabe: Index -> kanonischer
    Schluessel. Ein Kandidat ohne Website wird so demselben Startup
    zugeordnet wie ein gleichnamiger Kandidat mit Website.
    """
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen: dict[tuple, int] = {}
    for index, (task_id, candidate) in enumerate(items):
        for token in (("domain", _domain(candidate)), ("name", _norm_name(candidate))):
            if not token[1]:
                continue
            marker = (task_id,) + token
            if marker in seen:
                parent[find(index)] = find(seen[marker])
            else:
                seen[marker] = index
    members: dict[int, list[int]] = defaultdict(list)
    for index in range(len(items)):
        members[find(index)].append(index)
    result = {}
    for indices in members.values():
        canonical = sorted(entity_key(items[i][1]) for i in indices)[0]
        for i in indices:
            result[i] = canonical
    return result


def _candidate_id(candidate: dict) -> str:
    identifier = str(candidate.get("candidate_id") or "").strip()
    if identifier:
        return identifier
    return "candidate-" + hashlib.sha256(
        str(candidate.get("name") or "").casefold().encode("utf-8")).hexdigest()[:16]


def _short(prefix: str, *parts: str) -> str:
    raw = "|".join(parts).encode("utf-8")
    return f"{prefix}-" + hashlib.sha256(raw).hexdigest()[:12]


def _record_role(record: dict) -> str:
    return str((record.get("study") or {}).get("role") or "primary")


def _packages(record: dict) -> list[dict]:
    return [pair.get("blind_annotation") or pair
            for pair in record.get("blind_pairs") or []]


def build_rating_key(records: list[dict], *, purpose: str = "studie",
                     include_stability: bool = False) -> tuple[dict, dict]:
    """Erzeugt (Schluessel, Bogendaten) aus gespeicherten Laufdateien.

    Der Schluessel ordnet Einheiten Paaren, Armen und Kandidaten zu und bleibt
    bei der Versuchsleitung. Die Bogendaten enthalten nur Einheitenkennungen
    und das Material, das die Bewertenden sehen.
    """
    if purpose not in {"studie", "schulung"}:
        raise ValueError("purpose muss studie oder schulung sein.")
    tasks: dict[str, dict] = {}
    entities: dict[str, dict] = {}
    occurrences: list[dict] = []
    for record in records:
        if not include_stability and _record_role(record) != "primary":
            continue
        view_task = (record.get("operator_view") or {}).get("task") or {}
        reference = record.get("reference") or {}
        for package in _packages(record):
            task_id = str(package.get("task_id") or "")
            pair_id = str(package.get("pair_id") or "")
            if not task_id or not pair_id:
                continue
            sheet = package.get("case_sheet") or reference.get("case_sheet")
            task = tasks.setdefault(task_id, {
                "task_ref": _short("T", task_id),
                "organization_name": (package.get("organization_name")
                                      or view_task.get("organization_name") or ""),
                "website": (package.get("organization_domain_hint")
                            or view_task.get("organization_domain_hint") or ""),
                "search_prompt": (package.get("search_prompt")
                                  or (package.get("search_field") or {}).get("description")
                                  or view_task.get("search_prompt") or ""),
                "search_mode": package.get("search_mode") or view_task.get("search_mode") or "push",
                "search_area": package.get("search_area") or view_task.get("search_area") or "",
                "case_sheet": sheet or None,
                "case_sheet_sha256": case_sheet_hash(sheet) if sheet else "",
            })
            if sheet and task["case_sheet_sha256"] != case_sheet_hash(sheet):
                raise ValueError(f"Aufgabe {task_id}: unterschiedliche Fallblätter.")
            for arm in package.get("arms") or []:
                blind_arm_id = str(arm.get("blind_arm_id") or "")
                for rank, decision in enumerate(arm.get("decisions") or [], start=1):
                    candidate = decision.get("candidate") or {}
                    candidate_id = _candidate_id(candidate)
                    occurrences.append({
                        "occurrence_unit_id": _short(
                            "O", pair_id, blind_arm_id, candidate_id),
                        "task_id": task_id, "pair_id": pair_id,
                        "blind_arm_id": blind_arm_id,
                        "candidate_id": candidate_id, "candidate_rank": rank,
                        "name": candidate.get("name") or "",
                        # Bewertende sehen nur Name, Website, Aussagen und
                        # Belege. Freitexte des Systems (Beschreibung, Kette,
                        # Fortbestand) koennen Systemurteile enthalten.
                        "candidate": {key: candidate.get(key) for key in (
                            "name", "website", "claims_for_annotation", "sources")
                            if candidate.get(key) not in (None, "", [])},
                    })
    groups = _entity_groups([(item["task_id"], item["candidate"])
                             for item in occurrences])
    for index, item in enumerate(occurrences):
        ekey = groups[index]
        entity_id = _short("E", item["task_id"], ekey)
        item["entity_unit_id"] = entity_id
        entity = entities.setdefault(entity_id, {
            "entity_unit_id": entity_id, "task_id": item["task_id"],
            "entity_key": ekey, "name": item["name"],
            "website": item["candidate"].get("website") or "",
            "occurrence_unit_ids": [],
        })
        if not entity["website"] and item["candidate"].get("website"):
            entity["website"] = item["candidate"]["website"]
        entity["occurrence_unit_ids"].append(item["occurrence_unit_id"])
    if not occurrences:
        raise ValueError("Die ausgewählten Läufe enthalten keine Kandidaten zum Bewerten.")
    content = json.dumps({"purpose": purpose, "occurrences": sorted(
        (item["occurrence_unit_id"], item["entity_unit_id"]) for item in occurrences)},
        sort_keys=True)
    sheet_id = "sheet-" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    created = datetime.datetime.now(datetime.timezone.utc).isoformat()
    key = {
        "schema_version": KEY_SCHEMA_VERSION,
        "sheet_id": sheet_id, "purpose": purpose, "created_at": created,
        "include_stability": bool(include_stability),
        "tasks": [{"task_id": task_id, **{k: v for k, v in task.items()
                                         if k != "case_sheet"}}
                  for task_id, task in sorted(tasks.items())],
        "entities": sorted(entities.values(), key=lambda item: item["entity_unit_id"]),
        "occurrences": [{k: v for k, v in item.items() if k != "candidate"}
                        for item in occurrences],
        "counts": {"tasks": len(tasks), "entities": len(entities),
                   "occurrences": len(occurrences)},
    }
    by_entity = defaultdict(list)
    for item in occurrences:
        by_entity[item["entity_unit_id"]].append({
            "unit_id": item["occurrence_unit_id"], "candidate": item["candidate"]})
    sheet = {
        "sheet_id": sheet_id, "purpose": purpose, "created_at": created,
        "codebook": CODEBOOK, "rules": RULES,
        "entity_metrics": list(ENTITY_METRICS),
        "occurrence_metrics": list(OCCURRENCE_METRICS),
        "tasks": [{k: v for k, v in task.items() if k != "case_sheet_sha256"}
                  for _, task in sorted(tasks.items())],
        "entities": [{
            "unit_id": entity["entity_unit_id"],
            "task_ref": tasks[entity["task_id"]]["task_ref"],
            "name": entity["name"], "website": entity["website"],
            "occurrences": by_entity[entity["entity_unit_id"]],
        } for entity in sorted(entities.values(), key=lambda e: e["entity_unit_id"])],
    }
    return key, sheet


def _json_for_html(value: dict) -> str:
    raw = json.dumps(value, ensure_ascii=False)
    return raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render_rating_sheet_html(sheet: dict) -> str:
    """Eigenstaendige HTML-Datei: keine externen Ressourcen, keine Netzaufrufe."""
    from rating_sheet_template import TEMPLATE
    return TEMPLATE.replace("__SHEET_DATA__", _json_for_html(sheet))


_VALUE_MAP = {"yes": True, "no": False, "na": NOT_ASSESSABLE,
              True: True, False: False, NOT_ASSESSABLE: NOT_ASSESSABLE}
_ADJ_MAP = {**_VALUE_MAP, "disputed": DISPUTED, DISPUTED: DISPUTED}


def _value(raw, mapping=_VALUE_MAP):
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and raw in mapping:
        return mapping[raw]
    raise ValueError("Ungültiger Bewertungswert.")


def _rating_tables(key: dict, rating: dict) -> tuple[str, dict, dict]:
    if rating.get("schema_version") != RATINGS_SCHEMA_VERSION:
        raise ValueError("Bewertungsdatei hat ein unbekanntes Format.")
    if rating.get("sheet_id") != key.get("sheet_id"):
        raise ValueError("Bewertungsdatei gehört zu einem anderen Bewertungsbogen.")
    rater = str(rating.get("rater_id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,20}", rater):
        raise ValueError("Bewertungsdatei ohne gültiges Kürzel.")
    entity_ratings = rating.get("entity_ratings") or {}
    occurrence_ratings = rating.get("occurrence_ratings") or {}
    entities, occurrences = {}, {}
    for entity in key["entities"]:
        row = entity_ratings.get(entity["entity_unit_id"]) or {}
        try:
            entities[entity["entity_unit_id"]] = {
                metric: _value(row.get(metric)) for metric in ENTITY_METRICS}
        except ValueError:
            raise ValueError(f"{rater}: Bewertung für {entity['name']} ist unvollständig.")
        entities[entity["entity_unit_id"]]["comment"] = str(row.get("comment") or "")[:2000]
    for item in key["occurrences"]:
        row = occurrence_ratings.get(item["occurrence_unit_id"]) or {}
        try:
            occurrences[item["occurrence_unit_id"]] = {
                metric: _value(row.get(metric)) for metric in OCCURRENCE_METRICS}
        except ValueError:
            raise ValueError(f"{rater}: Bewertung einer Darstellung von {item['name']} ist unvollständig.")
        occurrences[item["occurrence_unit_id"]]["comment"] = str(row.get("comment") or "")[:2000]
    return rater, entities, occurrences


def merge_ratings(key: dict, ratings: list[dict],
                  adjudications: dict | None = None) -> dict:
    """Fuehrt zwei unabhaengige Bewertungen zusammen.

    Ohne vollstaendige Einigung liefert die Funktion die Abweichungen. Mit
    Einigung zu jeder Abweichung (Wert und Begruendung) entsteht die finale
    Bewertungsdatei im Schema der Auswertung.
    """
    if key.get("schema_version") != KEY_SCHEMA_VERSION:
        raise ValueError("Bewertungsschlüssel hat ein unbekanntes Format.")
    if len(ratings) != 2:
        raise ValueError("Es werden genau zwei Bewertungsdateien benötigt.")
    tables = [_rating_tables(key, rating) for rating in ratings]
    if tables[0][0] == tables[1][0]:
        raise ValueError("Beide Bewertungsdateien tragen dasselbe Kürzel.")
    names = {entity["entity_unit_id"]: entity for entity in key["entities"]}
    tasks = {task["task_id"]: task for task in key["tasks"]}
    disagreements, units = [], {metric: [] for metric in BOOLEAN_METRICS}
    for entity_id, entity in names.items():
        for metric in ENTITY_METRICS:
            values = [table[1][entity_id][metric] for table in tables]
            units[metric].append(values)
            if repr(values[0]) != repr(values[1]):
                disagreements.append({
                    "unit_id": entity_id, "metric": metric, "level": "startup",
                    "startup": entity["name"],
                    "organization": tasks.get(entity["task_id"], {}).get("organization_name", ""),
                    "values": {table[0]: values[i] for i, table in enumerate(tables)},
                    "comments": {table[0]: table[1][entity_id]["comment"] for table in tables},
                })
    for item in key["occurrences"]:
        unit_id = item["occurrence_unit_id"]
        for metric in OCCURRENCE_METRICS:
            values = [table[2][unit_id][metric] for table in tables]
            units[metric].append(values)
            if repr(values[0]) != repr(values[1]):
                disagreements.append({
                    "unit_id": unit_id, "metric": metric, "level": "darstellung",
                    "startup": item["name"],
                    "organization": tasks.get(item["task_id"], {}).get("organization_name", ""),
                    "values": {table[0]: values[i] for i, table in enumerate(tables)},
                    "comments": {table[0]: table[2][unit_id]["comment"] for table in tables},
                })
    alpha = {metric: krippendorff_alpha_nominal(values, missing=(NOT_ASSESSABLE,))
             for metric, values in units.items()}
    adjudications = adjudications or {}
    resolved, missing = {}, []
    for item in disagreements:
        entry = adjudications.get(f"{item['unit_id']}|{item['metric']}") or {}
        reason = " ".join(str(entry.get("reason") or "").split())
        try:
            value = _value(entry.get("value"), _ADJ_MAP)
        except ValueError:
            value = None
        if value is None or not reason:
            missing.append(item)
        else:
            resolved[(item["unit_id"], item["metric"])] = (value, reason[:2000])
    result = {
        "sheet_id": key["sheet_id"], "purpose": key.get("purpose"),
        "raters": [table[0] for table in tables],
        "alpha_before_adjudication": alpha,
        "disagreements": disagreements,
        "open_disagreements": len(missing),
        "status": "needs_adjudication" if missing else "complete",
    }
    if missing:
        return result
    rows = []
    for item in key["occurrences"]:
        for rater, entities, occurrences in tables:
            adjudication = {}
            for metric in ENTITY_METRICS:
                if (item["entity_unit_id"], metric) in resolved:
                    adjudication[metric] = resolved[(item["entity_unit_id"], metric)][0]
            for metric in OCCURRENCE_METRICS:
                if (item["occurrence_unit_id"], metric) in resolved:
                    adjudication[metric] = resolved[(item["occurrence_unit_id"], metric)][0]
            row = {
                "schema_version": ANNOTATION_SCHEMA_VERSION_V2,
                "pair_id": item["pair_id"], "task_id": item["task_id"],
                "blind_arm_id": item["blind_arm_id"],
                "candidate_id": item["candidate_id"],
                "candidate_rank": item["candidate_rank"],
                "entity_unit_id": item["entity_unit_id"],
                "rater_id": rater, "adjudication": adjudication,
            }
            row.update({metric: entities[item["entity_unit_id"]][metric]
                        for metric in ENTITY_METRICS})
            row.update({metric: occurrences[item["occurrence_unit_id"]][metric]
                        for metric in OCCURRENCE_METRICS})
            rows.append(row)
    result["final"] = {
        "schema_version": FINAL_SCHEMA_VERSION,
        "sheet_id": key["sheet_id"],
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "raters": result["raters"],
        "alpha_before_adjudication": alpha,
        "adjudication_log": [{
            "unit_id": unit_id, "metric": metric,
            "value": value, "reason": reason,
        } for (unit_id, metric), (value, reason) in sorted(
            resolved.items(), key=lambda item: (item[0][0], item[0][1]))],
        "annotations": rows,
    }
    return result
