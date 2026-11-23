"""Bewertung durch ein Panel von zehn Personen (docs/BEWERTUNGSPROTOKOLL_ENTWURF.md).

Ablauf:
1. ``build_panel`` zieht aus den Laufdateien die Faelle (je Aufgabe und Startup
   einer), teilt sie in Unternehmensbloecken auf die Bewertenden auf (jeder Fall
   dreifach, gleiche Last je Person) und erzeugt
   - den Schluessel fuer die Versuchsleitung (Zuordnung zu Paar, Arm, Modell,
     Systemurteil, Referenzwerte fuer die Gueltigkeitspruefung) und
   - die Bogendaten fuer die Bewertenden (verblindet, ohne Systemurteil).
2. Jede Person exportiert eine JSON-Datei. ``evaluate_panel`` fuehrt die Urteile
   ohne Einigung nach der Mehrheitsregel zusammen und berechnet die Kennzahlen.

Alle Zufallsschritte haengen nur vom Startwert ab; Ziehung und Zuteilung werden
mit SHA-256 festgehalten.
"""
from __future__ import annotations

import datetime
import hashlib
import itertools
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from case_sheet import case_sheet_hash
from evaluation_analysis import krippendorff_alpha_nominal
from rating_sheet import (_candidate_id, _entity_groups, _json_for_html,
                          _packages, _record_role, _short)

PANEL_KEY_SCHEMA = "veriscout-panel-key-v1"
PANEL_RATINGS_SCHEMA = "veriscout-panel-ratings-v1"
PANEL_DEFAULTS = {"raters": 10, "cases_per_rater": 12, "ratings_per_case": 3,
                  "max_organizations_per_rater": 6}
QUESTIONS = ("f1", "f2", "f3", "f4", "f5")
CHAIN_LINKS = ("process", "input", "capability", "result")
ANSWERS = {"yes", "no", "na"}
HIT, NO_HIT, NOT_ASSESSABLE = "hit", "no_hit", "not_assessable"
DISPUTED = "disputed"

CODEBOOK = {
    "f1": {"label": "Existenz und Fortbestand",
           "question": "Gibt es dieses Startup unter diesem Namen und dieser Website, mit eigenem Angebot, und ist es weder übernommen noch insolvent oder eingestellt?",
           "help": "Prüfe Website und Impressum, bei Bedarf ein Register. Nicht beurteilbar, wenn du das in etwa einer Minute nicht klären kannst."},
    "f2": {"label": "Beleg",
           "question": "Steht der markierte Auszug auf der verlinkten Seite, und trägt er die markierte Aussage?",
           "help": "Öffne den Beleg. Der Link springt, wenn der Browser es unterstützt, direkt zur Stelle. Ja nur, wenn der Auszug dort steht und der Satz ‚Laut dieser Quelle gilt: [Aussage]‘ stimmt. Ob die Aussage in der Welt wahr ist, musst du nicht prüfen."},
    "f3": {"label": "Kette",
           "question": "Führt der Weg vom belegten Prozess des Unternehmens über den Input und die Fähigkeit des Startups zu einem nutzbaren Ergebnis?",
           "help": "Grundlage sind die vier Zeilen der Kette und das Unternehmensprofil. Bei Nein wähle das Glied, an dem es scheitert. Begründe immer in einem Satz. Abgeleitete Glieder sind Schlussfolgerungen des Systems. Beurteile, ob sie plausibel sind."},
    "f4": {"label": "Ausschlusskriterium",
           "question": "Greift eines der Ausschlusskriterien des Unternehmens?",
           "help": "Die Kriterien stehen direkt unter der Frage. Bei Ja wähle das Kriterium aus."},
    "f5": {"label": "Übertreibung",
           "question": "Behauptet die Darstellung mehr, als die Belege hergeben?",
           "help": "Ja, wenn Aussagen weiter gehen als die Auszüge, zum Beispiel wenn nur thematische Nähe besteht, aber eine Lösung behauptet wird, oder ein Nutzen ohne Grundlage versprochen wird."},
}
CHAIN_LABELS = {"process": "Prozess", "input": "Input", "capability": "Fähigkeit",
                "result": "Ergebnis"}
RULES = [
    "Arbeite allein. Sprich mit niemandem über die Fälle, auch nicht mit anderen Bewertenden.",
    "Du erfährst nicht, welches System einen Fall geliefert hat und wie es geurteilt hat. Versuche nicht, das zu erraten.",
    "Du darfst im Web recherchieren, aber keine KI-Chatbots für deine Urteile nutzen.",
    "Grundlage ist, was öffentlich belegbar ist. Internes Wissen über die Unternehmen wird nicht vorausgesetzt.",
    "Nicht beurteilbar ist eine gültige Antwort. Begründung: ein Satz bei Frage 3 immer, sonst bei jeder Antwort gegen das Startup (Nein bei Frage 1 oder 2, Ja bei Frage 4 oder 5) und bei jedem ‚nicht beurteilbar‘.",
]


def _sha(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- Faelle
def _arm_architectures(record: dict) -> dict[tuple[str, str], str]:
    mapping = {}
    manifests = record.get("assignment_manifests") or []
    if isinstance(manifests, dict):
        manifests = list(manifests.values())
    for manifest in manifests:
        for item in manifest.get("assignments") or []:
            mapping[(str(manifest.get("pair_id") or ""), str(item.get("blind_arm_id") or ""))] = (
                str(item.get("architecture") or ""))
    return mapping


def _operator_candidates(record: dict) -> dict[tuple[str, str, str], dict]:
    view = record.get("operator_view") or {}
    result = {}
    for pair in view.get("pairs") or []:
        for arm in pair.get("arms") or []:
            for candidate in arm.get("candidates") or []:
                result[(str(pair.get("pair_id") or ""), str(arm.get("architecture") or ""),
                        str(candidate.get("candidate_id") or ""))] = candidate
    return result


def _excerpt_verified(source: dict, operator_source: dict | None) -> bool | None:
    mode = (operator_source or {}).get("excerpt_match_mode") or source.get("excerpt_match_mode")
    if mode:
        return True
    if source.get("verified_excerpt_hashes"):
        return True
    status = (operator_source or {}).get("resolved_status") or source.get("resolved_status") or ""
    if status == "resolved":
        return False
    return None


CHAIN_ROWS = {"process": ("target_process",), "input": ("input_stream",),
              "capability": ("startup_capability", "transformation"),
              "result": ("output_application",)}


CHAIN_PART_LABELS = {"startup_capability": "Fähigkeit", "transformation": "Wirkung"}


def _cell_basis(cell: dict | None) -> str:
    if not cell or cell.get("status") != "supported":
        return "ohne Beleg"
    return "abgeleitet" if cell.get("basis") == "derived" else "belegt"


def _chain_basis(view_candidate: dict) -> dict:
    """R5: je Kettenzeile 'belegt', 'abgeleitet' oder 'ohne Beleg' (kein Gesamturteil).

    Fasst eine Zeile zwei Glieder mit unterschiedlicher Grundlage zusammen, werden sie
    getrennt genannt, z. B. 'Fähigkeit belegt · Wirkung abgeleitet'.
    """
    cells = {str(cell.get("dimension")): cell for cell in view_candidate.get("matrix") or []}
    result = {}
    for row, dims in CHAIN_ROWS.items():
        labels = [_cell_basis(cells.get(d)) for d in dims]
        if len(set(labels)) == 1:
            result[row] = labels[0]
        else:
            result[row] = " · ".join(f"{CHAIN_PART_LABELS.get(d, d)} {label}"
                                     for d, label in zip(dims, labels))
    return result


def _impressum_link(view_candidate: dict) -> dict:
    """Impressum fuer F1, nur wenn der Resolver es mit Firmenname gefunden hat."""
    imp = dict(view_candidate.get("impressum") or {})
    url = str(imp.get("url") or "")
    if not url.startswith(("https://", "http://")) or not imp.get("company_name_found"):
        return {}
    return {"url": url, "register": str(imp.get("register") or "")}


def _marked_claim(claims: list[dict]) -> dict | None:
    """Die Aussage fuer F2: Kernaussage zur Faehigkeit des Startups."""
    usable = [c for c in claims if c.get("excerpt") and c.get("source_id")]
    for field in ("startup_capability", "transformation", "output_application"):
        for claim in usable:
            if claim.get("field") == field:
                return claim
    startup = [c for c in usable if c.get("subject_type") == "candidate_startup"]
    return (startup or usable or [None])[0]


def collect_cases(records: list[dict], *, include_stability: bool = False) -> tuple[dict, list[dict]]:
    """Alle Vorkommen und daraus die Faelle (Aufgabe x Startup)."""
    tasks: dict[str, dict] = {}
    occurrences: list[dict] = []
    for record in records:
        if not include_stability and _record_role(record) != "primary":
            continue
        view = record.get("operator_view") or {}
        view_task = view.get("task") or {}
        reference = record.get("reference") or {}
        architectures = _arm_architectures(record)
        operator = _operator_candidates(record)
        model = str(view.get("model") or "")
        for package in _packages(record):
            task_id = str(package.get("task_id") or "")
            pair_id = str(package.get("pair_id") or "")
            if not task_id or not pair_id:
                continue
            sheet = package.get("case_sheet") or reference.get("case_sheet")
            tasks.setdefault(task_id, {
                "task_id": task_id,
                "organization_name": package.get("organization_name") or view_task.get("organization_name") or "",
                "website": package.get("organization_domain_hint") or view_task.get("organization_domain_hint") or "",
                "search_prompt": package.get("search_prompt") or view_task.get("search_prompt") or "",
                "case_sheet": sheet or None,
                "case_sheet_sha256": case_sheet_hash(sheet) if sheet else "",
            })
            for arm in package.get("arms") or []:
                blind_arm_id = str(arm.get("blind_arm_id") or "")
                architecture = architectures.get((pair_id, blind_arm_id), "")
                for rank, decision in enumerate(arm.get("decisions") or [], start=1):
                    candidate = decision.get("candidate") or {}
                    candidate_id = _candidate_id(candidate)
                    view_candidate = operator.get((pair_id, architecture, candidate_id)) or {}
                    view_sources = {str(s.get("source_id")): s for s in view_candidate.get("sources") or []}
                    claims = list(candidate.get("claims_for_annotation") or [])
                    sources = [dict(s) for s in candidate.get("sources") or []]
                    for source in sources:
                        # Quellenabgleich: Fundseite anzeigen, wenn sie von der zitierten abweicht.
                        relocation = (view_sources.get(str(source.get("source_id"))) or {}).get("relocation") or {}
                        if relocation.get("verified_url") and relocation.get("verified_url") != source.get("url"):
                            source["verified_url"] = relocation["verified_url"]
                    marked = _marked_claim(claims)
                    marked_source = next((s for s in sources if marked and s.get("source_id") == marked.get("source_id")), None)
                    occurrences.append({
                        "occurrence_id": _short("O", pair_id, blind_arm_id, candidate_id),
                        "task_id": task_id, "pair_id": pair_id, "blind_arm_id": blind_arm_id,
                        "architecture": architecture, "model": model,
                        "run_id": str(view.get("run_id") or ""),
                        "candidate_id": candidate_id, "candidate_rank": rank,
                        "decision_state": str(view_candidate.get("decision_state") or ""),
                        "recommended": view_candidate.get("decision_state") == "empfehlung",
                        "operating_status": str(view_candidate.get("operating_status") or ""),
                        "name": candidate.get("name") or "",
                        "website": candidate.get("website") or candidate.get("official_url") or "",
                        "claims": claims, "sources": sources,
                        "marked_claim_id": (marked or {}).get("claim_id", ""),
                        "chain_basis": _chain_basis(view_candidate),
                        "impressum": _impressum_link(view_candidate),
                        "marked_excerpt_verified": (_excerpt_verified(marked_source, view_sources.get(str(marked_source.get("source_id"))))
                                                    if marked_source else None),
                    })
    groups = _entity_groups([(o["task_id"], {"name": o["name"], "website": o["website"]})
                             for o in occurrences])
    cases: dict[str, dict] = {}
    for index, occurrence in enumerate(occurrences):
        case_id = _short("C", occurrence["task_id"], groups[index])
        occurrence["case_id"] = case_id
        cases.setdefault(case_id, {"case_id": case_id, "task_id": occurrence["task_id"],
                                   "occurrences": []})["occurrences"].append(occurrence)
    return tasks, sorted(cases.values(), key=lambda c: c["case_id"])


def _representation(case: dict, rng: random.Random) -> dict:
    recommended = [o for o in case["occurrences"] if o["recommended"]]
    pool = sorted(recommended or case["occurrences"], key=lambda o: o["occurrence_id"])
    return pool[rng.randrange(len(pool))]


def _stratified(cases: list[dict], k: int, stratum, rng: random.Random) -> list[dict]:
    """k Faelle, gleichmaessig reihum ueber die Schichten (zufaellige Reihenfolge)."""
    if k <= 0:
        return []
    buckets: dict = defaultdict(list)
    for case in cases:
        buckets[stratum(case)].append(case)
    keys = sorted(buckets, key=repr)
    rng.shuffle(keys)
    for key in keys:
        rng.shuffle(buckets[key])
    chosen = []
    while len(chosen) < k and any(buckets.values()):
        for key in keys:
            if buckets[key] and len(chosen) < k:
                chosen.append(buckets[key].pop())
    return chosen


def select_cases(cases: list[dict], total: int, rng: random.Random) -> tuple[list[dict], dict]:
    for case in cases:
        case["representation"] = _representation(case, rng)
        case["recommended"] = any(o["recommended"] for o in case["occurrences"])
    recommended = [c for c in cases if c["recommended"]]
    rest = [c for c in cases if not c["recommended"]]
    stratum_rec = lambda c: (c["representation"]["architecture"], c["representation"]["model"])
    stratum_rest = lambda c: (c["representation"]["architecture"], c["representation"]["model"],
                              c["representation"]["decision_state"])
    if len(recommended) > total:
        stage1 = _stratified(recommended, total, stratum_rec, rng)
    else:
        stage1 = list(recommended)
    stage2 = _stratified(rest, total - len(stage1), stratum_rest, rng)
    weights = {}
    for name, population, sample, stratum in (("empfohlen", recommended, stage1, stratum_rec),
                                              ("nicht_empfohlen", rest, stage2, stratum_rest)):
        pop = Counter(stratum(c) for c in population)
        got = Counter(stratum(c) for c in sample)
        weights[name] = [{"stratum": list(key), "population": pop[key], "sample": got.get(key, 0),
                          "weight": (pop[key] / got[key]) if got.get(key) else None}
                         for key in sorted(pop, key=repr)]
    return stage1 + stage2, weights


# ---------------------------------------------------------------- Zuteilung
def _blocks(cases: list[dict], limit: int) -> list[list[dict]]:
    by_task = defaultdict(list)
    for case in cases:
        by_task[case["task_id"]].append(case)
    blocks = []
    for task_id in sorted(by_task):
        items = sorted(by_task[task_id], key=lambda c: c["case_id"])
        for start in range(0, len(items), limit):
            blocks.append(items[start:start + limit])
    return blocks


def assign_cases(cases: list[dict], *, raters: int, per_rater: int, overlap: int,
                 max_orgs: int, rng: random.Random, attempts: int = 200) -> dict[str, list[str]]:
    """Jeder Block an ``overlap`` Personen; Last je Person hoechstens ``per_rater``.

    Bei genau raters*per_rater Bewertungen erhaelt jede Person genau per_rater Faelle.
    Gesucht wird mit zufaelligen Neustarts; die Loesung haengt nur vom Startwert ab.
    """
    ids = [f"P{index:02d}" for index in range(1, raters + 1)]
    if len(cases) * overlap > raters * per_rater:
        raise ValueError("Zu viele Fälle für Zahl und Last der Bewertenden.")
    if overlap > raters:
        raise ValueError("Mehr Bewertungen je Fall als Bewertende.")
    blocks = _blocks(cases, per_rater)
    exact = len(cases) * overlap == raters * per_rater
    copies = [index for index in range(len(blocks)) for _ in range(overlap)]
    # Bei weniger Faellen: Last moeglichst gleich (Abstand hoechstens 1, sonst Blockgroesse).
    spread = [1]
    for attempt in range(attempts):
        if attempt == attempts // 2:
            spread[0] = max((len(b) for b in blocks), default=1)
        order = sorted(copies, key=lambda i: (-len(blocks[i]), rng.random()))
        load = [0] * raters
        members: list[set] = [set() for _ in range(raters)]
        budget = [20000]

        def place(position: int) -> bool:
            # Tiefensuche mit Ruecksetzen: jede Kopie eines Blocks an eine andere Person.
            if position == len(order):
                if exact:
                    return all(value == per_rater for value in load)
                return max(load) - min(load) <= spread[0]
            budget[0] -= 1
            if budget[0] < 0:
                return False
            index = order[position]
            size = len(blocks[index])
            tried = set()
            candidates = list(range(raters))
            rng.shuffle(candidates)
            candidates.sort(key=lambda r: load[r])
            for r in candidates:
                signature = (load[r], len(members[r]))
                if (index in members[r] or load[r] + size > per_rater
                        or len(members[r]) >= max_orgs or signature in tried):
                    continue
                tried.add(signature)
                load[r] += size
                members[r].add(index)
                if place(position + 1):
                    return True
                load[r] -= size
                members[r].discard(index)
            return False

        if not place(0):
            continue
        assigned = {ids[r]: [c["case_id"] for i in sorted(members[r]) for c in blocks[i]]
                    for r in range(raters)}
        sets = [frozenset(v) for v in assigned.values() if v]
        # Bei mehr Personen als Bewertungen je Fall darf kein Paar alle Faelle teilen.
        if raters > overlap and any(x == y for x, y in itertools.combinations(sets, 2)):
            continue
        for r in ids:
            rng.shuffle(assigned[r])
        return assigned
    raise ValueError("Keine gültige Zuteilung gefunden; Fallzahl oder Grenzen prüfen.")


def assign_balanced(cases: list[dict], *, raters: int, per_rater: int, overlap: int,
                    max_orgs: int, rng: random.Random) -> tuple[dict, int, int]:
    """Zuteilung mit den Vorgaben; wenn unmoeglich, zuerst die Unternehmensgrenze und dann
    die Last je Person schrittweise erhoehen. Die tatsaechlichen Werte gehen in den Schluessel."""
    largest = max((sum(1 for c in cases if c["task_id"] == t) for t in {c["task_id"] for c in cases}), default=1)
    for load in range(per_rater, per_rater + largest + 1):
        for org_limit in range(max_orgs, load + 1):
            try:
                return (assign_cases(cases, raters=raters, per_rater=load, overlap=overlap,
                                     max_orgs=org_limit, rng=rng, attempts=60), load, org_limit)
            except ValueError:
                continue
    raise ValueError("Keine gültige Zuteilung gefunden; Fallzahl oder Grenzen prüfen.")


def _ordered_for_rater(case_ids: list[str], case_by_id: dict, rng: random.Random) -> list[str]:
    """Unternehmen in zufaelliger Reihenfolge, Faelle je Unternehmen zufaellig."""
    by_task = defaultdict(list)
    for cid in case_ids:
        by_task[case_by_id[cid]["task_id"]].append(cid)
    tasks = sorted(by_task)
    rng.shuffle(tasks)
    ordered = []
    for task_id in tasks:
        items = sorted(by_task[task_id])
        rng.shuffle(items)
        ordered.extend(items)
    return ordered


# ---------------------------------------------------------------- Panel
def build_panel(records: list[dict], *, seed: str, purpose: str = "studie",
                raters: int = PANEL_DEFAULTS["raters"],
                cases_per_rater: int = PANEL_DEFAULTS["cases_per_rater"],
                ratings_per_case: int = PANEL_DEFAULTS["ratings_per_case"],
                max_organizations_per_rater: int = PANEL_DEFAULTS["max_organizations_per_rater"],
                include_stability: bool = False, practice_path=None) -> tuple[dict, dict]:
    if purpose not in {"studie", "schulung"}:
        raise ValueError("purpose muss studie oder schulung sein.")
    if not str(seed or "").strip():
        raise ValueError("Ein Startwert ist erforderlich.")
    rng = random.Random(f"veriscout-panel|{seed}")
    tasks, cases = collect_cases(records, include_stability=include_stability)
    if not cases:
        raise ValueError("Die ausgewählten Läufe enthalten keine Kandidaten zum Bewerten.")
    capacity = raters * cases_per_rater // ratings_per_case
    sample, weights = select_cases(cases, min(capacity, len(cases)), rng)
    case_by_id = {c["case_id"]: c for c in sample}
    exact_total = len(sample) * ratings_per_case
    per_rater = cases_per_rater if exact_total == raters * cases_per_rater else math.ceil(exact_total / raters)
    assignment, per_rater, org_limit = assign_balanced(
        sample, raters=raters, per_rater=per_rater, overlap=ratings_per_case,
        max_orgs=max_organizations_per_rater, rng=rng)
    assignment = {r: _ordered_for_rater(ids, case_by_id, rng) for r, ids in assignment.items()}
    created = datetime.datetime.now(datetime.timezone.utc).isoformat()
    draw = {"seed": seed, "purpose": purpose, "cases": sorted(case_by_id),
            "representations": {cid: c["representation"]["occurrence_id"] for cid, c in sorted(case_by_id.items())}}
    panel_id = "panel-" + _sha({"draw": draw, "assignment": assignment})[7:23]
    params = {"raters": raters, "cases_per_rater": cases_per_rater,
              "cases_per_rater_max_used": per_rater, "ratings_per_case": ratings_per_case,
              "max_organizations_per_rater": max_organizations_per_rater,
              "max_organizations_per_rater_used": org_limit}
    key = {
        "schema_version": PANEL_KEY_SCHEMA, "panel_id": panel_id, "purpose": purpose,
        "created_at": created, "parameters": params, "seed": seed,
        "draw_sha256": _sha(draw), "assignment_sha256": _sha(assignment),
        "marked_claim_rule": ("Feste Regel vor jeder Bewertung, unabhängig vom Systemurteil: erste Aussage "
                              "mit Auszug und Quelle zum Feld startup_capability, sonst transformation, "
                              "sonst output_application, sonst die erste Aussage über das Startup, sonst "
                              "die erste Aussage mit Auszug."),
        "assignment": assignment, "stratum_weights": weights,
        "population": {"cases": len(cases), "recommended_cases": sum(c["recommended"] for c in cases)},
        "tasks": [{k: v for k, v in t.items() if k != "case_sheet"} for _, t in sorted(tasks.items())],
        "cases": [{
            "case_id": c["case_id"], "task_id": c["task_id"], "recommended": c["recommended"],
            "representation": {k: c["representation"][k] for k in (
                "occurrence_id", "pair_id", "blind_arm_id", "architecture", "model", "run_id",
                "candidate_id", "decision_state", "operating_status", "marked_claim_id",
                "marked_excerpt_verified")},
            "occurrences": [{k: o[k] for k in ("occurrence_id", "pair_id", "blind_arm_id", "architecture",
                                                "model", "candidate_id", "decision_state", "recommended")}
                            for o in c["occurrences"]],
        } for c in sorted(sample, key=lambda c: c["case_id"])],
        "arms": sorted({(o["pair_id"], o["blind_arm_id"], o["architecture"], o["model"])
                        for c in cases for o in c["occurrences"]}),
        "verdict_words_in_text": sorted(
            c["case_id"] for c in sample
            if any(re.search(r"\b(empfehlung|empfohlen|ablehnung|abgelehnt|enthaltung)\b", str(cl.get("claim_text") or ""), re.I)
                   for cl in c["representation"]["claims"])),
        "unsampled_recommended_cases": sorted(c["case_id"] for c in cases
                                              if c["recommended"] and c["case_id"] not in case_by_id),
    }
    sheet = {
        "panel_id": panel_id, "purpose": purpose, "created_at": created,
        "codebook": CODEBOOK, "chain_labels": CHAIN_LABELS, "rules": RULES,
        "raters": {r: ids for r, ids in sorted(assignment.items())},
        "tasks": {t["task_id"]: {"task_ref": _short("T", t["task_id"]),
                                 "organization_name": t["organization_name"], "website": t["website"],
                                 "search_prompt": t["search_prompt"], "case_sheet": t["case_sheet"]}
                  for t in tasks.values() if any(c["task_id"] == t["task_id"] for c in sample)},
        "cases": {c["case_id"]: {
            "task_id": c["task_id"], "name": c["representation"]["name"],
            "website": c["representation"]["website"],
            "claims": [{k: cl.get(k) for k in ("claim_id", "claim_text", "field", "source_id", "excerpt")}
                       for cl in c["representation"]["claims"]],
            "sources": [{k: s.get(k) for k in ("source_id", "url", "title", "verified_url") if s.get(k) is not None}
                        for s in c["representation"]["sources"]],
            "marked_claim_id": c["representation"]["marked_claim_id"],
            "chain_basis": c["representation"].get("chain_basis") or {},
            "impressum": c["representation"].get("impressum") or {},
        } for c in sample},
    }
    practice = load_practice(practice_path)
    sheet["practice"] = practice
    key["practice"] = {"counted": False, "case_ids": [p["practice_id"] for p in practice],
                       "sha256": _sha(practice) if practice else ""}
    # Aufgabenkennungen gelten nur intern; im Bogen steht die neutrale Referenz.
    ref = {tid: info["task_ref"] for tid, info in sheet["tasks"].items()}
    sheet["tasks"] = {ref[tid]: info for tid, info in sheet["tasks"].items()}
    for case in sheet["cases"].values():
        case["task_id"] = ref[case["task_id"]]
    return key, sheet


# ---------------------------------------------------------------- Uebungsfaelle
# Uebungsfaelle stehen vor den eigenen Faellen im Bogen. Sie zaehlen nicht, werden
# nicht exportiert und nicht ausgewertet. Inhalt und Musterloesung liegen in einer
# eigenen Datei, damit sie ohne Codeaenderung getauscht werden koennen.
PRACTICE_SCHEMA = "veriscout-practice-cases-v1"
DEFAULT_PRACTICE_PATH = Path(__file__).resolve().parent / "studie" / "uebungsfaelle.json"
_CASE_FIELDS = ("name", "website", "claims", "sources", "marked_claim_id", "chain_basis", "impressum")
_TASK_FIELDS = ("organization_name", "website", "search_prompt", "case_sheet")


def load_practice(path=None) -> list[dict]:
    """Liest die Uebungsfaelle. Fehlt die Datei, gibt es keine Uebung (leere Liste)."""
    target = Path(path) if path else DEFAULT_PRACTICE_PATH
    if not target.is_file():
        return []
    data = json.loads(target.read_text(encoding="utf-8"))
    if data.get("schema_version") != PRACTICE_SCHEMA:
        raise ValueError("Unbekanntes Format der Übungsdatei.")
    out = []
    for index, item in enumerate(data.get("cases") or [], start=1):
        case = dict(item.get("case") or {})
        task = dict(item.get("task") or {})
        if not case.get("name") or not task.get("organization_name"):
            raise ValueError(f"Übungsfall {index}: Name oder Unternehmen fehlt.")
        solution = {}
        for q in QUESTIONS:
            entry = (item.get("solution") or {}).get(q) or {}
            answer = entry.get("answer")
            if answer is not None and (answer not in ANSWERS or (q == "f5" and answer == "na")):
                raise ValueError(f"Übungsfall {index}: ungültige Musterantwort bei {q.upper()}.")
            solution[q] = {"answer": answer, "reason": str(entry.get("reason") or "")}
        link = (item.get("solution") or {}).get("f3_link")
        if link and link not in CHAIN_LINKS:
            raise ValueError(f"Übungsfall {index}: ungültiges Glied bei F3.")
        out.append({
            "practice_id": f"U{index}",
            "status": str(data.get("status") or item.get("status") or "entwurf"),
            "task": {k: task.get(k) for k in _TASK_FIELDS},
            "case": {k: case.get(k) for k in _CASE_FIELDS},
            "solution": {**solution, "f3_link": link or ""},
        })
    return out


def practice_case_from_record(record: dict, *, architecture: str, candidate_name: str) -> dict:
    """Fallinhalt eines gespeicherten Laufs, genau so, wie der Bogen ihn zeigen wuerde."""
    tasks, cases = collect_cases([record], include_stability=True)
    wanted = candidate_name.strip().lower()
    for case in cases:
        for occ in case["occurrences"]:
            if occ["architecture"] == architecture and occ["name"].strip().lower() == wanted:
                task = tasks[occ["task_id"]]
                return {
                    "origin": {"run_id": occ["run_id"], "architecture": architecture,
                               "model": occ["model"], "decision_state": occ["decision_state"]},
                    "task": {k: task.get(k) for k in _TASK_FIELDS},
                    "case": {
                        "name": occ["name"], "website": occ["website"],
                        "claims": [{k: cl.get(k) for k in ("claim_id", "claim_text", "field", "source_id", "excerpt")}
                                   for cl in occ["claims"]],
                        "sources": [{k: s.get(k) for k in ("source_id", "url", "title")} for s in occ["sources"]],
                        "marked_claim_id": occ["marked_claim_id"],
                        "chain_basis": occ.get("chain_basis") or {},
                        "impressum": occ.get("impressum") or {},
                    },
                }
    raise ValueError(f"Kandidat {candidate_name!r} ({architecture}) nicht im Lauf gefunden.")


def render_panel_html(sheet: dict) -> str:
    from rating_panel_template import TEMPLATE
    return TEMPLATE.replace("__PANEL_DATA__", _json_for_html(sheet))


# ---------------------------------------------------------------- Auswertung
def rater_verdict(answer: dict) -> str:
    values = {q: answer.get(q) for q in ("f1", "f2", "f3", "f4")}
    if any(values[q] == "no" for q in ("f1", "f2", "f3")) or values["f4"] == "yes":
        return NO_HIT
    if all(values[q] == "yes" for q in ("f1", "f2", "f3")) and values["f4"] == "no":
        return HIT
    return NOT_ASSESSABLE


def combine(verdicts: list[str]) -> str:
    fixed = [v for v in verdicts if v in (HIT, NO_HIT)]
    if len(fixed) <= 1:
        return NOT_ASSESSABLE
    hits, misses = fixed.count(HIT), fixed.count(NO_HIT)
    if hits == misses:
        return DISPUTED
    return HIT if hits > misses else NO_HIT


def needs_reason(question: str, value) -> bool:
    """Begruendung bei jeder Antwort, die gegen das Startup spricht, und bei nicht beurteilbar.

    F1 bis F3: nein oder nicht beurteilbar; F4 (Ausschluss greift) und F5 (Schoenfaerberei):
    ja oder nicht beurteilbar; F3 immer.
    """
    if question == "f3":
        return value in ANSWERS
    if question in ("f4", "f5"):
        return value in ("yes", "na")
    return value in ("no", "na")


def validate_rating(key: dict, rating: dict) -> tuple[str, dict, list[str]]:
    if rating.get("schema_version") != PANEL_RATINGS_SCHEMA:
        raise ValueError("Unbekanntes Format der Bewertungsdatei.")
    if rating.get("panel_id") != key.get("panel_id"):
        raise ValueError("Die Bewertungsdatei gehört zu einem anderen Bogen.")
    rater = str(rating.get("rater_id") or "")
    if rater not in key.get("assignment", {}):
        raise ValueError(f"Unbekanntes Kürzel: {rater!r}.")
    problems = []
    answers = rating.get("answers") or {}
    clean = {}
    for case_id in key["assignment"][rater]:
        answer = answers.get(case_id) or {}
        reasons = answer.get("reasons") or {}
        missing = [q for q in QUESTIONS if answer.get(q) not in ANSWERS
                   or (q == "f5" and answer.get(q) == "na")]
        missing += [f"Begründung {q.upper()}" for q in QUESTIONS
                    if needs_reason(q, answer.get(q)) and not str(reasons.get(q) or "").strip()]
        if answer.get("f3") == "no" and answer.get("f3_link") not in CHAIN_LINKS:
            missing.append("gescheitertes Glied F3")
        if answer.get("f3") in ANSWERS and not str(reasons.get("f3") or "").strip() \
                and "Begründung F3" not in missing:
            missing.append("Begründung F3")
        if missing:
            problems.append(f"{case_id}: {', '.join(missing)}")
        if answer:
            clean[case_id] = answer
    return rater, clean, problems


def _wilson(successes: int, n: int, z: float = 1.959964) -> list[float] | None:
    if n == 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def _alpha(units: list[list]) -> float | None:
    return krippendorff_alpha_nominal(units, missing=("na",))


def _pairwise(per_case: dict[str, dict[str, str]]) -> float | None:
    agree = total = 0
    for values in per_case.values():
        fixed = [v for v in values.values() if v in ("yes", "no")]
        for a, b in itertools.combinations(fixed, 2):
            total += 1
            agree += a == b
    return agree / total if total else None


def _bootstrap(case_ids: list[str], stat, rng: random.Random, draws: int) -> list[float] | None:
    values = []
    for _ in range(draws):
        sample = [case_ids[rng.randrange(len(case_ids))] for _ in case_ids]
        value = stat(sample)
        if value is not None:
            values.append(value)
    if len(values) < draws * 0.5:
        return None
    values.sort()
    return [round(values[int(0.025 * len(values))], 4), round(values[int(0.975 * len(values)) - 1], 4)]


def evaluate_panel(key: dict, ratings: list[dict], *, bootstrap_draws: int = 2000) -> dict:
    if key.get("schema_version") != PANEL_KEY_SCHEMA:
        raise ValueError("Unbekanntes Format des Bewertungsschlüssels.")
    tables, completeness = {}, {}
    for rating in ratings:
        rater, answers, problems = validate_rating(key, rating)
        if rater in tables:
            raise ValueError(f"Bewertung {rater} doppelt geladen.")
        tables[rater] = answers
        assigned = key["assignment"][rater]
        completeness[rater] = {"assigned": len(assigned), "answered": sum(1 for c in assigned if c in answers),
                               "problems": problems}
    raters_by_case = defaultdict(list)
    for rater, ids in key["assignment"].items():
        for cid in ids:
            raters_by_case[cid].append(rater)
    cases = []
    for case in key["cases"]:
        cid = case["case_id"]
        per_rater = {r: tables[r][cid] for r in raters_by_case[cid] if r in tables and cid in tables[r]}
        verdicts = {r: rater_verdict(a) for r, a in per_rater.items()}
        cases.append({"case_id": cid, "task_id": case["task_id"], "recommended": case["recommended"],
                      "architecture": case["representation"]["architecture"],
                      "model": case["representation"]["model"],
                      "verdicts": verdicts, "result": combine(list(verdicts.values())),
                      "unanimous": len(verdicts) >= 2 and len(set(verdicts.values())) == 1,
                      "answers": per_rater})
    by_case = {c["case_id"]: c for c in cases}

    # Qualified-Hit je Arm: mindestens ein empfohlenes Startup ist Treffer.
    occurrence_case = {}
    for case in key["cases"]:
        for occ in case["occurrences"]:
            occurrence_case[(occ["pair_id"], occ["blind_arm_id"], occ["candidate_id"])] = (case["case_id"], occ["recommended"])
    arms = []
    for pair_id, blind_arm_id, architecture, model in key["arms"]:
        recommended = [cid for (p, a, _), (cid, rec) in occurrence_case.items()
                       if p == pair_id and a == blind_arm_id and rec]
        results = [by_case[cid]["result"] for cid in recommended if cid in by_case]
        arms.append({
            "pair_id": pair_id, "blind_arm_id": blind_arm_id, "architecture": architecture, "model": model,
            "recommended_cases": len(recommended), "recommended_rated": len(results),
            "hit_primary": int(HIT in results),
            "hit_lenient": int(any(r in (HIT, DISPUTED, NOT_ASSESSABLE) for r in results)),
        })

    rng = random.Random(f"veriscout-panel-bootstrap|{key.get('seed')}")
    case_ids = [c["case_id"] for c in cases]
    question_stats = {}
    for q in QUESTIONS:
        per_case = {c["case_id"]: {r: a.get(q) for r, a in c["answers"].items()} for c in cases}
        units = lambda ids: [list(per_case[i].values()) for i in ids]
        all_answers = [v for values in per_case.values() for v in values.values()]
        question_stats[q] = {
            "alpha": _alpha(units(case_ids)),
            "alpha_ci95": _bootstrap(case_ids, lambda ids: _alpha(units(ids)), rng, bootstrap_draws) if case_ids else None,
            "pairwise_agreement": _pairwise(per_case),
            "pairwise_ci95": _bootstrap(case_ids, lambda ids: _pairwise({i: per_case[i] for i in ids}), rng, bootstrap_draws) if case_ids else None,
            "not_assessable_share": (all_answers.count("na") / len(all_answers)) if all_answers else None,
        }

    def majority(case, q):
        fixed = [a.get(q) for a in case["answers"].values() if a.get(q) in ("yes", "no")]
        if not fixed or fixed.count("yes") == fixed.count("no"):
            return None
        return fixed.count("yes") > fixed.count("no")

    key_cases = {c["case_id"]: c for c in key["cases"]}
    f2_pairs = [(majority(c, "f2"), key_cases[c["case_id"]]["representation"]["marked_excerpt_verified"]) for c in cases]
    f2_pairs = [(a, b) for a, b in f2_pairs if a is not None and b is not None]
    status_ref = {"active": True, "acquired": False, "insolvent": False, "ceased": False}
    f1_pairs = [(majority(c, "f1"), status_ref.get(key_cases[c["case_id"]]["representation"]["operating_status"])) for c in cases]
    f1_pairs = [(a, b) for a, b in f1_pairs if a is not None and b is not None]
    validity = {}
    for name, pairs in (("f2_vs_excerpt_verified", f2_pairs), ("f1_vs_operating_status", f1_pairs)):
        agree = sum(a == b for a, b in pairs)
        validity[name] = {"n": len(pairs), "agreement": (agree / len(pairs)) if pairs else None,
                          "ci95_wilson": _wilson(agree, len(pairs))}
    links = Counter(a.get("f3_link") for c in cases for a in c["answers"].values() if a.get("f3") == "no")
    results = Counter(c["result"] for c in cases)
    return {
        "panel_id": key["panel_id"], "parameters": key["parameters"],
        "completeness": completeness,
        "cases": [{k: v for k, v in c.items() if k != "answers"} for c in cases],
        "result_counts": dict(results),
        "unanimous_share": (sum(c["unanimous"] for c in cases) / len(cases)) if cases else None,
        "arms": arms,
        "qualified_hit_rate": {
            variant: {f"{arch}|{model}": (sum(a[field] for a in arms if (a["architecture"], a["model"]) == (arch, model))
                                          / max(1, sum(1 for a in arms if (a["architecture"], a["model"]) == (arch, model))))
                      for arch, model in sorted({(a["architecture"], a["model"]) for a in arms})}
            for variant, field in (("primary", "hit_primary"), ("lenient", "hit_lenient"))},
        "questions": question_stats, "validity": validity,
        "f3_failed_links": {CHAIN_LABELS.get(k, str(k)): v for k, v in links.items()},
        "unsampled_recommended_cases": key.get("unsampled_recommended_cases", []),
        "stratum_weights": key.get("stratum_weights"),
    }
