"""Verblindete Annotation und gepaarte, task-geclusterte Auswertung.

Die Funktionen arbeiten nur mit finalisierten menschlichen Urteilen und der
separaten Entblindungsdatei. Kandidaten oder Wiederholungen werden nicht als
unabhaengige Aufgaben ausgegeben. Es werden keine fehlenden Urteile imputiert.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
from collections import defaultdict


ANNOTATION_SCHEMA_VERSION = "venture-scout-annotation-v1"
# v2 (Kap. 7, Referenzurteile): je Kriterium ja, nein oder "nicht
# beurteilbar"; Startup-bezogene Kriterien werden je Aufgabe und Startup nur
# einmal beurteilt (entity_unit_id), darstellungsbezogene je Vorkommen.
ANNOTATION_SCHEMA_VERSION_V2 = "veriscout-annotation-v2"
ANNOTATION_SCHEMA_VERSIONS = {ANNOTATION_SCHEMA_VERSION, ANNOTATION_SCHEMA_VERSION_V2}
BOOLEAN_METRICS = (
    "qualified",
    "valid_entity",
    "relation_correct",
    "claim_support_complete",
    "over_match",
)
# Eigenschaften des Startups fuer diese Aufgabe, unabhaengig von der Darstellung.
ENTITY_METRICS = ("qualified", "valid_entity")
# Eigenschaften der konkreten Darstellung eines Systems (Aussagen, Kette).
OCCURRENCE_METRICS = ("relation_correct", "claim_support_complete", "over_match")
NOT_ASSESSABLE = "not_assessable"
DISPUTED = "disputed"
RATER_VALUES = (True, False, NOT_ASSESSABLE)
ADJUDICATION_VALUES = (True, False, NOT_ASSESSABLE, DISPUTED)


def _value_ok(value, allowed) -> bool:
    return any(value is item if isinstance(item, bool) else value == item
               for item in allowed)


def _yes(value) -> bool:
    """Nur ein ausdrueckliches Ja zaehlt; nicht beurteilbar und strittig nicht."""
    return value is True


def _occurrence_key(row: dict) -> tuple:
    return tuple(str(row.get(name) or "").strip() for name in (
        "pair_id", "task_id", "blind_arm_id", "candidate_id"))


def _unit_key(row: dict, metric: str) -> tuple:
    if metric in ENTITY_METRICS and row.get("entity_unit_id"):
        return ("entity", str(row.get("task_id") or ""),
                str(row["entity_unit_id"]))
    return ("occurrence",) + _occurrence_key(row)


def annotation_template(blind_packages: list[dict]) -> list[dict]:
    """Erzeugt leere, kandidatenweise Zeilen fuer zwei unabhaengige Rater."""
    rows = []
    for package in blind_packages:
        pair_id = str(package.get("pair_id") or "")
        task_id = str(package.get("task_id") or "")
        for arm in package.get("arms") or []:
            arm_id = str(arm.get("blind_arm_id") or "")
            for rank, decision in enumerate(arm.get("decisions") or [], start=1):
                candidate = decision.get("candidate") or {}
                candidate_id = str(candidate.get("candidate_id") or "")
                if not candidate_id:
                    candidate_id = "candidate-" + hashlib.sha256(
                        str(candidate.get("name") or "").casefold().encode("utf-8")
                    ).hexdigest()[:16]
                for rater_id in ("rater-1", "rater-2"):
                    row = {
                        "schema_version": ANNOTATION_SCHEMA_VERSION,
                        "pair_id": pair_id,
                        "task_id": task_id,
                        "blind_arm_id": arm_id,
                        "candidate_id": candidate_id,
                        "candidate_rank": rank,
                        "rater_id": rater_id,
                        "adjudication": {},
                    }
                    row.update({metric: None for metric in BOOLEAN_METRICS})
                    rows.append(row)
    return rows


def validate_annotations(rows: list[dict]) -> dict:
    """Prueft Doppelannotation, Werte, Rang, Einheiten und Adjudikation."""
    if not rows:
        raise ValueError("Annotationsdatei ist leer.")
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    seen = set()
    for row in rows:
        version = row.get("schema_version")
        if version not in ANNOTATION_SCHEMA_VERSIONS:
            raise ValueError("Unbekannte Annotationsschema-Version.")
        v2 = version == ANNOTATION_SCHEMA_VERSION_V2
        key = _occurrence_key(row)
        if not all(key):
            raise ValueError("Annotation ohne Pair-, Task-, Arm- oder Kandidaten-ID.")
        rank = int(row.get("candidate_rank") or 0)
        if not 1 <= rank <= 5:
            raise ValueError("candidate_rank muss zwischen 1 und 5 liegen.")
        rater_id = str(row.get("rater_id") or "").strip()
        unique = key + (rater_id,)
        if not rater_id or unique in seen:
            raise ValueError("Rater-ID fehlt oder Annotation ist doppelt.")
        seen.add(unique)
        if v2 and not str(row.get("entity_unit_id") or "").strip():
            raise ValueError("Annotation v2 braucht eine entity_unit_id.")
        for metric in BOOLEAN_METRICS:
            allowed = RATER_VALUES if v2 else (True, False)
            if not _value_ok(row.get(metric), allowed):
                raise ValueError(
                    f"{metric} muss final annotiert sein (ja, nein"
                    + (" oder nicht beurteilbar)." if v2 else ")."))
        adjudication = row.get("adjudication") or {}
        allowed = ADJUDICATION_VALUES if v2 else (True, False)
        if not isinstance(adjudication, dict) or any(
                name not in BOOLEAN_METRICS or not _value_ok(value, allowed)
                for name, value in adjudication.items()):
            raise ValueError("adjudication ist ungueltig.")
        grouped[key].append(dict(row))
    for key, values in grouped.items():
        raters = {item["rater_id"] for item in values}
        if len(values) != 2 or len(raters) != 2:
            raise ValueError(
                "Jeder Kandidat braucht genau zwei unabhaengige Rater: "
                + "/".join(key))
    units = _units(rows)
    for (metric, unit), by_rater in units.items():
        if len(by_rater) != 2:
            raise ValueError(f"Einheit {'/'.join(unit[1:])} braucht genau zwei Rater.")
        values = list(by_rater.values())
        if repr(values[0][0]) != repr(values[1][0]):
            adjudicated = {repr(item) for item in _adjudications(rows, metric, unit)}
            if len(adjudicated) != 1:
                raise ValueError(
                    f"Konflikt in {metric} ist nicht eindeutig adjudiziert.")
    entity_units = {unit for (metric, unit) in units if unit[0] == "entity"}
    return {"candidate_units": len(grouped), "rater_rows": len(rows),
            "entity_units": len(entity_units)}


def _units(rows: list[dict]) -> dict:
    """{(metric, unit): {rater_id: (value, row)}}; prueft Einheitlichkeit.

    Ein Startup-Kriterium wird je Aufgabe und Startup einmal beurteilt. Taucht
    das Startup mehrfach auf, muss jede bewertende Person ueberall denselben
    Wert tragen.
    """
    units: dict = defaultdict(dict)
    for row in rows:
        rater = str(row.get("rater_id") or "").strip()
        for metric in BOOLEAN_METRICS:
            unit = _unit_key(row, metric)
            value = row.get(metric)
            previous = units[(metric, unit)].get(rater)
            if previous is not None and repr(previous[0]) != repr(value):
                raise ValueError(
                    f"{metric}: unterschiedliche Urteile derselben Person fuer "
                    "dasselbe Startup in derselben Aufgabe.")
            units[(metric, unit)][rater] = (value, row)
    return units


def _adjudications(rows: list[dict], metric: str, unit: tuple) -> list:
    return [row["adjudication"][metric] for row in rows
            if _unit_key(row, metric) == unit
            and metric in (row.get("adjudication") or {})]


def _consensus(rows: list[dict]) -> tuple[list[dict], dict]:
    validate_annotations(rows)
    units = _units(rows)
    unit_values: dict = {}
    for (metric, unit), by_rater in units.items():
        values = [value for value, _ in by_rater.values()]
        if repr(values[0]) == repr(values[1]):
            unit_values[(metric, unit)] = values[0]
        else:
            unit_values[(metric, unit)] = _adjudications(rows, metric, unit)[0]
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[_occurrence_key(row)].append(row)
    consensus = []
    for key, values in grouped.items():
        result = {
            "pair_id": key[0], "task_id": key[1],
            "blind_arm_id": key[2], "candidate_id": key[3],
            "candidate_rank": int(values[0]["candidate_rank"]),
            "entity_unit_id": str(values[0].get("entity_unit_id") or ""),
        }
        for metric in BOOLEAN_METRICS:
            result[metric] = unit_values[(metric, _unit_key(values[0], metric))]
        consensus.append(result)
    agreement = {"alpha": {}, "kappa": {}, "units": {}, "not_assessable": {},
                 "disputed": {}}
    for metric in BOOLEAN_METRICS:
        metric_units = [(unit, by_rater) for (name, unit), by_rater in units.items()
                        if name == metric]
        ratings = [[value for value, _ in by_rater.values()]
                   for _, by_rater in metric_units]
        agreement["alpha"][metric] = krippendorff_alpha_nominal(
            ratings, missing=(NOT_ASSESSABLE,))
        boolean_pairs = [tuple(values) for values in ratings
                         if all(isinstance(value, bool) for value in values)]
        agreement["kappa"][metric] = (cohen_kappa(boolean_pairs)
                                      if len(boolean_pairs) == len(ratings)
                                      else None)
        agreement["units"][metric] = len(metric_units)
        agreement["not_assessable"][metric] = sum(
            unit_values[(metric, unit)] == NOT_ASSESSABLE for unit, _ in metric_units)
        agreement["disputed"][metric] = sum(
            unit_values[(metric, unit)] == DISPUTED for unit, _ in metric_units)
    return consensus, agreement


def krippendorff_alpha_nominal(units: list[list], *,
                               missing: tuple = ()) -> float | None:
    """Krippendorffs Alpha fuer nominale Daten mit fehlenden Werten.

    ``units`` enthaelt je Einheit die Werte aller Bewertenden; Werte in
    ``missing`` (hier: nicht beurteilbar) gelten als fehlend. Einheiten mit
    weniger als zwei Werten sind nicht paarbar (Krippendorff 2011, S. 1-4).
    Ohne Variation in den Daten ist Alpha nicht definiert (None).
    """
    coincidence: dict[tuple, float] = defaultdict(float)
    for values in units:
        present = [value for value in values
                   if value is not None and not any(
                       value == item and type(value) is type(item)
                       for item in missing)]
        m = len(present)
        if m < 2:
            continue
        for i, left in enumerate(present):
            for j, right in enumerate(present):
                if i != j:
                    coincidence[(repr(left), repr(right))] += 1.0 / (m - 1)
    totals: dict[str, float] = defaultdict(float)
    for (left, _), count in coincidence.items():
        totals[left] += count
    n = sum(totals.values())
    if n <= 1:
        return None
    observed = sum(count for (left, right), count in coincidence.items()
                   if left != right)
    expected = sum(totals[left] * totals[right]
                   for left in totals for right in totals if left != right)
    if expected == 0:
        return None
    return round(1.0 - (n - 1.0) * observed / expected, 6)


def cohen_kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(left == right for left, right in pairs) / n
    p_left = sum(left for left, _ in pairs) / n
    p_right = sum(right for _, right in pairs) / n
    expected = p_left * p_right + (1 - p_left) * (1 - p_right)
    if math.isclose(expected, 1.0):
        return 1.0 if math.isclose(observed, 1.0) else None
    return round((observed - expected) / (1 - expected), 6)


def _assignment_map(manifests: list[dict]) -> dict[tuple[str, str], dict]:
    mapping = {}
    for manifest in manifests:
        if manifest.get("schema_version") != "venture-scout-assignment-v2":
            raise ValueError(
                "Entblindungsmanifest braucht das auswertungssichere Schema v2.")
        pair_id = str(manifest.get("pair_id") or "")
        task_id = str(manifest.get("task_id") or "")
        manifest_assignments = list(manifest.get("assignments") or [])
        if (len(manifest_assignments) != 2
                or {str(item.get("architecture") or "")
                    for item in manifest_assignments} != {"sas2", "mas"}):
            raise ValueError(
                "Entblindungsmanifest braucht genau einen SAS-2- und einen MAS-Arm.")
        for item in manifest_assignments:
            key = (pair_id, str(item.get("blind_arm_id") or ""))
            architecture = str(item.get("architecture") or "")
            status = str(item.get("result_status") or "completed")
            expected_ids = [str(value or "").strip()
                            for value in item.get("expected_candidate_ids") or []]
            returned_candidates = item.get("returned_candidates")
            if (not all(key) or not task_id
                    or architecture not in {"sas2", "mas"}
                    or status not in {"completed", "abstention",
                                      "not_checked_budget", "technical_error"}
                    or not isinstance(returned_candidates, int)
                    or returned_candidates < 0
                    or returned_candidates != len(expected_ids)
                    or any(not value for value in expected_ids)
                    or len(expected_ids) != len(set(expected_ids))):
                raise ValueError("Entblindungsmanifest ist unvollstaendig.")
            record = {
                "task_id": task_id,
                "architecture": architecture,
                "expected_candidate_ids": tuple(expected_ids),
                "result_status": status,
                "primary_analysis_eligible": bool(item.get(
                    "primary_analysis_eligible",
                    status in {"completed", "abstention"})),
                "primary_exclusion_reason": str(
                    item.get("primary_exclusion_reason") or ""),
                # None = aelteres Manifest ohne Systementscheidung je Kandidat.
                "positive_candidate_ids": (
                    tuple(str(x) for x in item["positive_candidate_ids"])
                    if isinstance(item.get("positive_candidate_ids"), list)
                    else None),
                "protocol_deviations": tuple(
                    str(x) for x in item.get("protocol_deviations") or []),
                "sensitivity_positive_ids": {
                    name: tuple(str(x) for x in (value or {}).get(
                        "positive_candidate_ids") or [])
                    for name, value in (item.get("sensitivity") or {}).items()
                    if isinstance(value, dict)},
                "review_mechanics": tuple(sorted(
                    (str(k), int(v)) for k, v in
                    (item.get("review_mechanics") or {}).items())),
                # Hauptstudie (Variante A): Modell, Rolle des Paars und
                # Unternehmensgruppe fuer getrennte Auswertungen.
                "model": str(manifest.get("model") or ""),
                "study_role": str(manifest.get("study_role") or "primary"),
                "stratum": str(manifest.get("stratum") or ""),
            }
            if key in mapping and mapping[key] != record:
                raise ValueError("Widerspruechliche Armzuordnung.")
            mapping[key] = record
    return mapping


def _rate(items: list[dict], metric: str) -> float | None:
    """Anteil Ja unter den beurteilbaren Urteilen (ohne nicht beurteilbar/strittig)."""
    assessable = [item for item in items if isinstance(item[metric], bool)]
    if not assessable:
        return None
    return sum(item[metric] for item in assessable) / len(assessable)


def paired_metrics(rows: list[dict], manifests: list[dict]) -> dict:
    """Berechnet Kandidaten-, Pair- und task-level Metriken nach Entblindung."""
    if rows:
        consensus, agreement = _consensus(rows)
    else:
        consensus = []
        agreement = {"alpha": {metric: None for metric in BOOLEAN_METRICS},
                     "kappa": {metric: None for metric in BOOLEAN_METRICS},
                     "units": {}, "not_assessable": {}, "disputed": {}}
    assignments = _assignment_map(manifests)
    by_arm: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    pair_assignments: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for (pair_id, _), metadata in assignments.items():
        pair_assignments[(metadata["task_id"], pair_id)][
            metadata["architecture"]] = metadata
    for item in consensus:
        metadata = assignments.get((item["pair_id"], item["blind_arm_id"]))
        if not metadata:
            raise ValueError("Annotation besitzt keine getrennte Armzuordnung.")
        if item["task_id"] != metadata["task_id"]:
            raise ValueError("Annotation und Manifest widersprechen sich bei task_id.")
        by_arm[(item["task_id"], item["pair_id"],
                metadata["architecture"])].append(item)
    annotated_pairs = {pair_id for (_, pair_id, _) in by_arm}

    # Eine fehlende Annotation darf nicht wie ein valider leerer Systemoutput
    # behandelt werden. Die getrennte Zuordnungsdatei bindet deshalb vor der
    # Entblindung die exakte Kandidatenmenge jedes Arms. Stabilitaets-
    # wiederholungen muessen nicht bewertet sein (Auswertung ueber Endzustaende).
    for (pair_id, blind_arm_id), metadata in assignments.items():
        if not metadata["primary_analysis_eligible"]:
            continue
        if metadata["study_role"] != "primary" and pair_id not in annotated_pairs:
            continue
        observed = {
            item["candidate_id"] for item in
            by_arm.get((metadata["task_id"], pair_id,
                        metadata["architecture"]), [])
        }
        expected = set(metadata["expected_candidate_ids"])
        if observed != expected:
            raise ValueError(
                "Annotationsdatei und eingefrorene Kandidatenmenge stimmen "
                f"nicht ueberein: {pair_id}/{blind_arm_id}.")

    primary_assignments = {key: value for key, value in assignments.items()
                           if value["study_role"] == "primary"}
    if not primary_assignments:
        raise ValueError("Keine Paare mit der Rolle primary in den Zuordnungsdateien.")
    itt = _intention_to_treat(primary_assignments, by_arm)

    def subsets(field: str) -> dict:
        values = sorted({value[field] for value in primary_assignments.values()
                         if value[field]})
        if len(values) < 2:
            return {}
        return {value: _itt_block(
            {key: item for key, item in primary_assignments.items()
             if item[field] == value}, by_arm, variant="primary")
            for value in values}

    excluded_pairs = []
    analyzable_pairs = set()
    for pair_key, values in sorted(pair_assignments.items()):
        if set(values) != {"sas2", "mas"}:
            raise ValueError("Mindestens ein Pair besitzt nicht beide Architekturen.")
        if any(item["study_role"] != "primary" for item in values.values()):
            continue
        invalid = {architecture: metadata for architecture, metadata in values.items()
                   if not metadata["primary_analysis_eligible"]}
        if invalid:
            excluded_pairs.append({
                "task_id": pair_key[0], "pair_id": pair_key[1],
                "arms": {architecture: {
                    "result_status": metadata["result_status"],
                    "reason": metadata["primary_exclusion_reason"],
                } for architecture, metadata in invalid.items()},
            })
            continue
        analyzable_pairs.add(pair_key)
        # Ein valides leeres Ergebnis besitzt keine Kandidatenannotation, ist
        # aber fuer Qualified-Hit@5 ein korrektes Nullresultat.
        for architecture in ("sas2", "mas"):
            by_arm.setdefault((pair_key[0], pair_key[1], architecture), [])

    arm_rows = []
    for (task_id, pair_id, architecture), candidates in sorted(by_arm.items()):
        if (task_id, pair_id) not in analyzable_pairs:
            continue
        candidates = sorted(candidates, key=lambda item: item["candidate_rank"])
        top = [item for item in candidates if item["candidate_rank"] <= 5]
        qualified = [item for item in top if _yes(item["qualified"])]
        denominator = len(top)
        arm_rows.append({
            "task_id": task_id,
            "pair_id": pair_id,
            "architecture": architecture,
            "qualified_hit_at_5": int(bool(qualified)),
            "qualified_yield_at_5": len({item["candidate_id"]
                                         for item in qualified}) / 5.0,
            "valid_entity_rate": _rate(top, "valid_entity"),
            "relation_correct_rate": _rate(top, "relation_correct"),
            "claim_support_complete_rate": _rate(top, "claim_support_complete"),
            "over_match_rate": _rate(top, "over_match"),
            "precision_at_5": (len(qualified) / denominator
                               if denominator else None),
            "returned_candidates": len(top),
            "not_assessable_judgments": sum(
                item[metric] == NOT_ASSESSABLE for item in top
                for metric in BOOLEAN_METRICS),
            "disputed_judgments": sum(
                item[metric] == DISPUTED for item in top
                for metric in BOOLEAN_METRICS),
        })
    pair_groups: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for item in arm_rows:
        pair_groups[(item["task_id"], item["pair_id"])][item["architecture"]] = item
    incomplete = [key for key, value in pair_groups.items()
                  if set(value) != {"sas2", "mas"}]
    if incomplete:
        raise ValueError("Mindestens ein Pair besitzt nicht beide Architekturen.")

    metric_names = (
        "qualified_hit_at_5", "qualified_yield_at_5", "valid_entity_rate",
        "relation_correct_rate", "claim_support_complete_rate",
        "over_match_rate", "precision_at_5",
    )
    task_values: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list))
    for (task_id, _), values in pair_groups.items():
        for metric in metric_names:
            if (values["mas"][metric] is None
                    or values["sas2"][metric] is None):
                continue
            task_values[task_id][metric].append(
                float(values["mas"][metric]) - float(values["sas2"][metric]))
    task_differences = {
        task_id: {metric: sum(values) / len(values)
                  for metric, values in metrics.items()}
        for task_id, metrics in task_values.items()
    }
    return {
        "schema_version": "venture-scout-analysis-v4",
        # Primaer (Kap. 7.3.2): alle zugewiesenen Laeufe, technische Fehler,
        # nicht vollstaendig gepruefte Laeufe und Enthaltungen zaehlen als 0.
        # Bei mehreren Modellen: gepoolt ueber Modelle, Aufgabe als Einheit.
        "primary_estimand": "itt_qualified_hit_at_5_all_assigned_runs",
        "primary_itt": itt,
        "by_model": subsets("model"),
        "by_stratum": subsets("stratum"),
        "stability": _stability_summary(assignments),
        # Sekundaer: bedingte Qualitaet nur beidseitig gueltiger Paare.
        "quality_estimand": "conditional_on_both_arms_eligible",
        "operational_outcomes_all_assigned": {
            architecture: {
                "assigned_runs": sum(m["architecture"] == architecture
                                     for m in primary_assignments.values()),
                "status_counts": {
                    status: sum(m["architecture"] == architecture
                                and m["result_status"] == status
                                for m in primary_assignments.values())
                    for status in sorted({m["result_status"]
                                          for m in primary_assignments.values()})
                },
                "eligible_runs": sum(m["architecture"] == architecture
                                     and m["primary_analysis_eligible"]
                                     for m in primary_assignments.values()),
            } for architecture in ("sas2", "mas")
        },
        "independent_task_clusters": len(task_differences),
        "paired_runs": len(pair_groups),
        "excluded_pairs": excluded_pairs,
        "excluded_pair_count": len(excluded_pairs),
        # Kap. 7: Krippendorffs Alpha (nominal, nicht beurteilbar = fehlend).
        "interrater_alpha": agreement["alpha"],
        "interrater_kappa": agreement["kappa"],
        "agreement_units": agreement["units"],
        "not_assessable_units": agreement["not_assessable"],
        "disputed_units": agreement["disputed"],
        "arm_metrics": arm_rows,
        "task_differences_mas_minus_sas": task_differences,
    }


def _stability_summary(assignments: dict) -> dict:
    """Stabilitaet ueber Wiederholungen desselben Modells (Kap. 7: Endzustaende).

    Vergleicht je Aufgabe, Modell und Architektur die Wiederholungen: gleicher
    Ergebnisstatus und gleiche Antwort auf "gibt es eine Systemempfehlung".
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for (pair_id, _), metadata in assignments.items():
        groups[(metadata["task_id"], metadata["model"],
                metadata["architecture"])].append(metadata)
    result = {}
    for architecture in ("sas2", "mas"):
        repeated = [values for (task, model, arch), values in groups.items()
                    if arch == architecture and len(values) >= 2]
        if not repeated:
            continue
        same_status = sum(len({item["result_status"] for item in values}) == 1
                          for values in repeated)
        same_recommendation = sum(len({bool(item["positive_candidate_ids"])
                                       for item in values}) == 1
                                  for values in repeated)
        result[architecture] = {
            "tasks_with_repetitions": len(repeated),
            "same_result_status": same_status / len(repeated),
            "same_recommendation_presence": same_recommendation / len(repeated),
        }
    return result


def _arm_hit(metadata: dict, candidates: list[dict],
             positive_ids: tuple | None, disputed_as_hit: bool = False) -> int:
    """q = 1, wenn ein vom System empfohlener Kandidat fachlich qualifiziert ist.

    Enthaltungen, leere Ergebnisse, technische Fehler und nicht vollstaendig
    gepruefte Laeufe erhalten 0 (Kap. 7.3.2). Aeltere Manifeste ohne
    Systementscheidung je Kandidat fallen auf alle ausgegebenen Kandidaten
    zurueck; das wird im Ergebnis ausgewiesen.
    """
    if not metadata["primary_analysis_eligible"]:
        return 0
    top = [item for item in candidates if item["candidate_rank"] <= 5]
    if positive_ids is not None:
        top = [item for item in top if item["candidate_id"] in set(positive_ids)]
    return int(any(_counts_as_hit(item["qualified"], disputed_as_hit)
                   for item in top))


def _counts_as_hit(value, disputed_as_hit: bool = False) -> bool:
    """Primaer zaehlt nur Ja; die Sensitivitaet wertet strittige Faelle als Treffer."""
    return value is True or (disputed_as_hit and value == DISPUTED)


def _itt_block(assignments: dict, by_arm: dict, *, variant: str = "primary") -> dict:
    """Qualified-Hit@5 ueber alle zugewiesenen Laeufe (Fehler = 0).

    Varianten: ``primary``; ``strict_web`` (Arme mit Websuch-Ueberschreitung
    zaehlen als technischer Fehler); ``strict_budget`` (Arme mit budgetbedingt
    ungeprueften Quellen anderer Kandidaten zaehlen als unvollstaendig); ``exact_excerpt`` und
    ``mas_scout_sources`` (Systemempfehlungen der kostenfreien
    Sensitivitaetsauswertung desselben Laufs); ``disputed_as_hit``
    (strittig gebliebene Faelle zaehlen als Treffer, Kap. 7).
    """
    runs: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    pairs: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    status_by_arm: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    precision_counts: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0]))
    fallback = False
    for (pair_id, _), metadata in sorted(assignments.items()):
        architecture = metadata["architecture"]
        task_id = metadata["task_id"]
        positives = metadata.get("positive_candidate_ids")
        meta = dict(metadata)
        if variant == "strict_web" and any(
                str(item).startswith("provider_tool_overrun")
                for item in metadata.get("protocol_deviations") or ()):
            meta["primary_analysis_eligible"] = False
        elif variant == "strict_budget" and "resolver_budget_partial" in (
                metadata.get("protocol_deviations") or ()):
            # Strenge Lesart: jede budgetbedingt ungepruefte Quelle im Arm
            # macht den ganzen Arm unvollstaendig (Erfolg 0).
            meta["primary_analysis_eligible"] = False
        elif variant in {"exact_excerpt", "mas_scout_sources"}:
            sensitivity = metadata.get("sensitivity_positive_ids") or {}
            if variant in sensitivity:
                positives = sensitivity[variant]
        if positives is None:
            fallback = True
        candidates = by_arm.get((task_id, pair_id, architecture), [])
        hit = _arm_hit(meta, candidates, positives,
                       disputed_as_hit=variant == "disputed_as_hit")
        runs[task_id][architecture].append(hit)
        pairs[(task_id, pair_id)][architecture] = hit
        status_by_arm[architecture][metadata["result_status"]] += 1
        if meta["primary_analysis_eligible"] and positives is not None:
            positive_rows = [item for item in candidates
                             if item["candidate_id"] in set(positives)]
            counts = precision_counts[task_id][architecture]
            counts[0] += sum(_counts_as_hit(
                item["qualified"], variant == "disputed_as_hit")
                for item in positive_rows)
            counts[1] += len(positive_rows)
    for values in pairs.values():
        if set(values) != {"sas2", "mas"}:
            raise ValueError("Mindestens ein Pair besitzt nicht beide Architekturen.")

    def mean_success(architecture: str) -> float | None:
        values = [hit for task in runs.values() for hit in task[architecture]]
        return sum(values) / len(values) if values else None

    def all_replicates(architecture: str) -> float | None:
        tasks = [task[architecture] for task in runs.values() if task[architecture]]
        if not tasks:
            return None
        return sum(int(all(values)) for values in tasks) / len(tasks)

    def precision(architecture: str) -> float | None:
        tp = sum(task[architecture][0] for task in precision_counts.values())
        pos = sum(task[architecture][1] for task in precision_counts.values())
        return tp / pos if pos else None

    task_differences = {}
    task_successes = {}
    for task_id, values in sorted(runs.items()):
        diffs = [pair["mas"] - pair["sas2"]
                 for (task, _), pair in sorted(pairs.items()) if task == task_id]
        task_differences[task_id] = {"qualified_hit_at_5": sum(diffs) / len(diffs)}
        task_successes[task_id] = {
            arch: [sum(values[arch]), len(values[arch])] for arch in ("sas2", "mas")}
    signs = [value["qualified_hit_at_5"] for value in task_differences.values()]
    return {
        "variant": variant,
        "estimand": "qualified_hit_at_5_failure_as_zero",
        "positive_ids_source": ("returned_candidates_fallback" if fallback
                                else "system_recommendations"),
        "assigned_pairs": len(pairs),
        "task_clusters": len(runs),
        "status_counts": {arch: dict(counts)
                          for arch, counts in sorted(status_by_arm.items())},
        "mean_success": {arch: mean_success(arch) for arch in ("sas2", "mas")},
        "all_replicates_success": {arch: all_replicates(arch)
                                   for arch in ("sas2", "mas")},
        "precision_of_recommendations": {arch: precision(arch)
                                         for arch in ("sas2", "mas")},
        "task_successes": task_successes,
        "precision_counts": {task: {arch: list(counts[arch])
                                    for arch in ("sas2", "mas")}
                             for task, counts in sorted(precision_counts.items())},
        "task_differences_mas_minus_sas": task_differences,
        "task_sign_tally": {
            "mas_better": sum(value > 0 for value in signs),
            "equal": sum(value == 0 for value in signs),
            "sas2_better": sum(value < 0 for value in signs),
        },
    }


def _intention_to_treat(assignments: dict, by_arm: dict) -> dict:
    primary = _itt_block(assignments, by_arm, variant="primary")
    primary["sensitivity"] = {
        variant: {key: value for key, value in _itt_block(
            assignments, by_arm, variant=variant).items()
            if key in {"mean_success", "all_replicates_success",
                       "precision_of_recommendations", "task_sign_tally"}}
        for variant in ("strict_web", "strict_budget", "exact_excerpt",
                        "mas_scout_sources", "disputed_as_hit")}
    primary["review_mechanics"] = _mechanics_summary(assignments)
    return primary


def _mechanics_summary(assignments: dict) -> dict:
    """H3: Anteil verworfener Kandidaten und widerlegter Aussagen je Arm."""
    totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for metadata in assignments.values():
        for key, value in metadata.get("review_mechanics") or ():
            totals[metadata["architecture"]][key] += int(value)
    result = {}
    for arch in ("sas2", "mas"):
        item = dict(totals.get(arch, {}))
        candidates = item.get("candidates_stage_1", 0)
        claims = item.get("claims_stage_1", 0)
        result[arch] = {
            **item,
            "drop_rate": (item.get("candidates_dropped_stage_2", 0) / candidates
                          if candidates else None),
            "contradiction_rate": (item.get("claims_contradicted_stage_2", 0) / claims
                                   if claims else None),
            "non_confirmation_rate": (
                (item.get("claims_contradicted_stage_2", 0)
                 + item.get("claims_unconfirmed_stage_2", 0)) / claims
                if claims else None),
        }
    return result


def bayesian_paired_difference(itt: dict, *, draws: int = 20_000,
                               seed: int = 20261016,
                               min_improvement: float | None = None,
                               ni_margin: float | None = None) -> dict:
    """Bayesianisches Intervall der gepaarten Differenz MAS minus SAS-2.

    Verfahren: Bayesianisches Bootstrap ueber Aufgaben (Rubin 1981,
    Dirichlet(1,...,1)-Gewichte) kombiniert mit einer Beta-Posterior je
    Aufgabe und Architektur bei Gleichverteilungs-Prior (Beta(1,1)), wie von
    Bowyer et al. (2025) fuer kleine Evaluationen empfohlen. Wiederholungen
    einer Aufgabe gehen nur ueber deren Erfolgszahl ein und zaehlen damit
    nicht als unabhaengige neue Faelle.

    Zusaetzlich: Precision der Systemempfehlungen je Arm und die
    Nichtunterlegenheitspruefung (unteres 95-%-Limit der Differenz > Grenze).
    """
    from core import Config
    min_improvement = (Config.EVAL_MIN_IMPROVEMENT if min_improvement is None
                       else float(min_improvement))
    ni_margin = (Config.EVAL_NI_MARGIN_PRECISION if ni_margin is None
                 else float(ni_margin))
    tasks = sorted((itt.get("task_successes") or {}).items())
    if not tasks:
        raise ValueError("Keine Aufgaben fuer das bayesianische Intervall.")
    rng = random.Random(seed)
    deltas, mas_rates, sas_rates, precision_deltas = [], [], [], []
    precision_counts = itt.get("precision_counts") or {}
    for _ in range(int(draws)):
        raw = [rng.gammavariate(1.0, 1.0) for _ in tasks]
        total = sum(raw)
        weights = [value / total for value in raw]
        mas = sas = 0.0
        tp = {"sas2": 0.0, "mas": 0.0}
        pos = {"sas2": 0.0, "mas": 0.0}
        for weight, (task_id, arms) in zip(weights, tasks):
            s_mas, n_mas = arms["mas"]
            s_sas, n_sas = arms["sas2"]
            mas += weight * rng.betavariate(1 + s_mas, 1 + n_mas - s_mas)
            sas += weight * rng.betavariate(1 + s_sas, 1 + n_sas - s_sas)
            for arch in ("sas2", "mas"):
                counts = (precision_counts.get(task_id) or {}).get(arch) or [0, 0]
                # Gewichte summieren zu 1; mit der Aufgabenzahl skaliert
                # bleibt die Gesamtzahl beobachteter Empfehlungen erhalten.
                tp[arch] += weight * len(tasks) * counts[0]
                pos[arch] += weight * len(tasks) * counts[1]
        deltas.append(mas - sas)
        mas_rates.append(mas)
        sas_rates.append(sas)
        if pos["mas"] > 0 and pos["sas2"] > 0:
            precision_deltas.append(
                rng.betavariate(1 + tp["mas"], 1 + pos["mas"] - tp["mas"])
                - rng.betavariate(1 + tp["sas2"], 1 + pos["sas2"] - tp["sas2"]))

    def summary(values: list[float]) -> dict | None:
        if not values:
            return None
        ordered = sorted(values)
        n = len(ordered)
        return {"mean": round(sum(ordered) / n, 6),
                "ci95": [round(ordered[int(0.025 * (n - 1))], 6),
                         round(ordered[int(0.975 * (n - 1))], 6)]}

    delta = summary(deltas)
    precision_delta = summary(precision_deltas)
    noninferior = (None if precision_delta is None
                   else precision_delta["ci95"][0] > ni_margin)
    return {
        "method": ("bayesian_bootstrap_over_tasks_with_beta_uniform_prior"
                   " (Rubin 1981; Bowyer et al. 2025)"),
        "draws": int(draws),
        "seed": int(seed),
        "task_clusters": len(tasks),
        "success_rate": {"sas2": summary(sas_rates), "mas": summary(mas_rates)},
        "difference_mas_minus_sas": delta,
        "p_difference_gt_0": round(sum(value > 0 for value in deltas) / len(deltas), 6),
        "min_improvement": min_improvement,
        "p_difference_gt_min_improvement": round(
            sum(value > min_improvement for value in deltas) / len(deltas), 6),
        "h1_supported": bool(delta and delta["ci95"][0] > 0
                             and delta["mean"] >= min_improvement),
        "precision_difference_mas_minus_sas": precision_delta,
        "ni_margin_precision": ni_margin,
        "h2_noninferior": noninferior,
        "h2_note": (None if precision_delta is not None else
                    "In mindestens einem Arm gibt es keine Systemempfehlung; "
                    "Precision ist nicht definiert."),
    }


def cluster_bootstrap_interval(task_differences: dict[str, dict[str, float]],
                               metric: str, *, resamples: int = 10_000,
                               seed: int = 20260831) -> dict:
    values = [float(metrics[metric]) for _, metrics in
              sorted(task_differences.items())]
    if len(values) < 2:
        raise ValueError("Mindestens zwei unabhaengige Aufgabencluster noetig.")
    rng = random.Random(seed)
    estimates = []
    for _ in range(int(resamples)):
        sample = [values[rng.randrange(len(values))] for _ in values]
        estimates.append(sum(sample) / len(sample))
    estimates.sort()
    lower = estimates[max(0, int(0.025 * len(estimates)) - 1)]
    upper = estimates[min(len(estimates) - 1, int(0.975 * len(estimates)))]
    return {
        "metric": metric,
        "estimate": round(sum(values) / len(values), 6),
        "ci95": [round(lower, 6), round(upper, 6)],
        "clusters": len(values),
        "resamples": int(resamples),
        "seed": int(seed),
    }


def paired_permutation_pvalue(task_differences: dict[str, dict[str, float]],
                              metric: str, *, alternative: str = "greater",
                              seed: int = 20260831,
                              monte_carlo_draws: int = 100_000) -> dict:
    values = [float(metrics[metric]) for _, metrics in
              sorted(task_differences.items())]
    if not values:
        raise ValueError("Keine Task-Differenzen vorhanden.")
    if alternative not in {"greater", "less", "two-sided"}:
        raise ValueError("alternative ist ungueltig.")
    observed = sum(values) / len(values)

    def extreme(value: float) -> bool:
        if alternative == "greater":
            return value >= observed - 1e-15
        if alternative == "less":
            return value <= observed + 1e-15
        return abs(value) >= abs(observed) - 1e-15

    if len(values) <= 20:
        means = [sum(sign * value for sign, value in zip(signs, values)) / len(values)
                 for signs in itertools.product((-1, 1), repeat=len(values))]
        count = sum(extreme(value) for value in means)
        pvalue = count / len(means)
        method = "exact_sign_flip"
        draws = len(means)
    else:
        rng = random.Random(seed)
        count = 0
        for _ in range(int(monte_carlo_draws)):
            value = sum((1 if rng.random() < 0.5 else -1) * item
                        for item in values) / len(values)
            count += extreme(value)
        pvalue = (count + 1) / (int(monte_carlo_draws) + 1)
        method = "monte_carlo_sign_flip"
        draws = int(monte_carlo_draws)
    return {
        "metric": metric,
        "alternative": alternative,
        "observed_difference": round(observed, 6),
        "p_value": round(pvalue, 8),
        "method": method,
        "draws": draws,
    }


def analysis_digest(result: dict) -> str:
    raw = json.dumps(result, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return "analysis-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
