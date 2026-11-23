"""Hauptstudie Variante A: SAS-2 gegen MAS mit zwei Modellfamilien.

Ablauf
------
1. Plan einfrieren (kostenlos):
       .venv/bin/python scripts/run_study.py plan \
           --tasks studie/aufgaben.csv --case-sheets studie/fallblaetter.json \
           --seed <frei gewaehlter Text> --out studie/plan.json
   Jede Aufgabe laeuft einmal mit jedem Modell (gekreuzt). Zusaetzlich
   wiederholt eine zufaellig gezogene Teilmenge den Lauf mit dem ersten
   Modell (Stabilitaet). PUSH/PULL wird, wo nicht vorgegeben, je Gruppe
   ausgeglichen zufaellig zugeteilt; die Reihenfolge SAS-2/MAS je Modell
   ausgeglichen (AB/BA). Der Plan erhaelt einen Fingerabdruck und laesst sich
   nicht ueberschreiben.

2. Laeufe ausfuehren (Kosten entstehen, nur mit --confirm-paid):
       .venv/bin/python scripts/run_study.py run-all --plan studie/plan.json --confirm-paid
   Reihenfolge (12.11.2026): erst alle Paare des ersten Laufs, dann alle des
   zweiten Laufs (bei --replicates 2), dann Stabilitaet. Innerhalb eines Laufs
   wechseln die Modelle Paar fuer Paar ab; die Firmenreihenfolge je Modell und
   das Startmodell folgen dem Seed. Greift der Stopp, fehlen so nur einzelne
   spaete Paare, nie ein ganzes Modell oder ein Firmenblock.
   Vor jedem Paar wird geprueft, ob bisherige Kosten + Hoechstkosten des Paars
   + Sicherheitsaufschlag (PAIR_OVERRUN_MARGIN_USD) die Grenze einhalten. Sonst
   endet der Lauf mit Status budget_stop und der Liste der nicht gelaufenen
   Paare. Die Grenze wird beim Einfrieren mit --max-total-usd festgelegt
   (Pflicht). Abgebrochene Paare werden mit Hoechstkosten verbucht.
   Ein erneuter Aufruf setzt fort: Ein Paar, das ohne Ergebnis abgebrochen
   ist (Netz, Ruhezustand, Strg+C), wird einmal vollstaendig neu gestartet;
   der Abbruch bleibt im Kostenbuch. Technische Fehler innerhalb eines
   abgeschlossenen Paars werden nicht wiederholt (Erfolgswert 0).
   Auf dem Mac den Ruhezustand verhindern: "caffeinate -i" voranstellen.

3. Stand ansehen:
       .venv/bin/python scripts/run_study.py status --plan studie/plan.json

Das Fallblatt geht nie an die Architekturen; es steht nur in der Laufdatei
unter "reference" und im Blindpaket fuer die Bewertenden.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import os
import random
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Modellwahl muss vor dem Import der Konfiguration feststehen.
if "--model" in sys.argv:
    os.environ["SCOUTREF_OPENAI_MODEL"] = sys.argv[sys.argv.index("--model") + 1]

from case_sheet import case_sheet_hash, normalise_case_sheet  # noqa: E402
from compare_architectures import (ComparisonTask, ExperimentBudget,  # noqa: E402
                                   PairedArchitectureRunner,
                                   annotation_package, assignment_manifest,
                                   operator_view)
from core import Config  # noqa: E402
from experiment_protocol import stable_organization_id  # noqa: E402

PLAN_SCHEMA = "veriscout-study-plan-v1"
DEFAULT_MODELS = ("gpt-6.1-sol", "claude-sonnet-5-5")
DEFAULT_LIMIT_USD = 90.0
GROUPS = {"gt_hub", "extern"}
# Alle Module, die der Studienlauf laedt (Test prueft die Vollstaendigkeit),
# dazu die Daten- und Konfigurationsdateien, die Entscheidungen beeinflussen.
CODE_FILES = (
    "agents.py", "baselines.py", "case_sheet.py", "compare_architectures.py",
    "core.py", "crm_pipedrive.py", "entity_verifier.py", "evidence_matrix.py",
    "evidence_resolver.py", "evidence_subjects.py", "experiment_protocol.py",
    "http_security.py", "knowledge_base.py", "llm_anthropic.py", "memory.py",
    "opportunity_planner.py", "outreach.py", "pipeline.py", "provenance.py",
    "quality_gates.py", "resource_budget.py", "review_contract.py",
    # 12.11.2026: alle Module des Studienpfads (Import-Verfolgung im Test
    # tests/test_code_fingerprint.py), einschliesslich Nachrecherche und Bewertungsbogen.
    "follow_up.py", "evaluation_analysis.py", "rating_panel.py", "rating_panel_template.py",
    "rating_sheet.py", "rating_sheet_template.py",
    "scripts/run_study.py",
    "data/public/actors.json", "data/public/profile_sources.json",
    "data/public/themes_public.json", "data/evaluation/frozen_memory.json",
    "config/instance.default.json", "requirements.txt",
)
# Werte des Budgetprofils "main-calibrated-2026-11-12" (bis 12.11.: "pilot-calibrated-2026-10-19"
# mit 16.000 Ausgabe-Tokens je Arm), wie in der Arbeit
# beschrieben. Weicht die Umgebung (z. B. ein alter Eintrag in .env) davon ab,
# wird kein Plan angelegt.
PROFILE_VALUES = {
    "max_input_tokens": 200_000, "max_output_tokens": 24_000,
    "max_reasoning_tokens": 8_000, "max_tool_calls": 12, "max_model_calls": 2,
    "max_resolver_fetches": 24, "max_cost_usd": 0.75, "max_candidates": 3,
    "reasoning_effort": "low",
}
# Ein durch Abbruch (Netz, Ruhezustand, Strg+C) unvollstaendiges Paar wird
# hoechstens so oft insgesamt gestartet; jeder Abbruch zaehlt mit Hoechstkosten.
MAX_ATTEMPTS = 2
# Feste Vorlagen: Der Suchauftrag entsteht aus Unternehmen, Auftragsart und
# Suchfeld. So formuliert die Versuchsleitung keine unterschiedlich leichten
# Auftraege.
PUSH_TEMPLATE = (
    "Suche ein reales, aktives B2B-Startup, dessen Produkt einen oeffentlich belegten "
    "Prozess von {name} nachhaltiger oder effizienter machen koennte. "
    "Ermittle den konkreten Zielprozess zuerst aus oeffentlichen Quellen. "
    "Ob ein passendes Startup-Unternehmen existiert, ist offen; ein leeres "
    "Ergebnis ist zulaessig.")
PULL_TEMPLATE = (
    "Suche ein reales B2B-Startup, dessen Produkt im Suchfeld \"{area}\" einen "
    "oeffentlich belegten Prozess von {name} nachhaltiger oder effizienter "
    "machen koennte. Ermittle den konkreten Zielprozess zuerst aus "
    "oeffentlichen Quellen.")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def code_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in CODE_FILES:
        path = ROOT / name
        if path.is_file():
            digest.update(name.encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def effective_config(models: list[str]) -> dict:
    """Alle Laufzeitwerte, die das Ergebnis beeinflussen (auch aus .env).

    Der Plan friert sie ein; der Lauf bricht ab, wenn eine Umgebungsvariable
    sie seitdem veraendert hat. Budgetbezeichner allein reichen dafuer nicht.
    """
    import evidence_resolver
    budget = ExperimentBudget()
    return {
        "budget": {key: value for key, value in budget.__dict__.items() if key != "model"},
        "reasoning_effort": Config.REASONING_EFFORT,
        "excerpt_match_mode": Config.EXCERPT_MATCH_MODE,
        "excerpt_fuzzy_min_ratio": Config.EXCERPT_FUZZY_MIN_RATIO,
        "excerpt_fuzzy_min_words": Config.EXCERPT_FUZZY_MIN_WORDS,
        "web_overrun_policy": Config.EVAL_WEB_OVERRUN_POLICY,
        "web_search_max_uses": Config.WEB_SEARCH_MAX_USES,
        "web_search_price_usd": Config.WEB_SEARCH_PRICE,
        "discovery_waves": Config.DISCOVERY_WAVES,
        "threshold": Config.THRESHOLD_SUFFICIENT,
        "threshold_rubric": Config.THRESHOLD_RUBRIC_VERSION,
        "min_improvement": Config.EVAL_MIN_IMPROVEMENT,
        "ni_margin_precision": Config.EVAL_NI_MARGIN_PRECISION,
        "provider_timeout_seconds": Config.OPENAI_TIMEOUT_SECONDS,
        "openai_endpoint": Config.OPENAI_RESPONSES_URL,
        "prices": {model: list(Config.PRICES.get(model) or []) for model in models},
        # 12.11.2026: Suchwerkzeug je Modell (Sonnet: web_search_20250305).
        "follow_up": {key: getattr(Config, key) for key in (
            "FOLLOW_UP_ENABLED", "FOLLOW_UP_MIN_INDEX", "FOLLOW_UP_MAX_OPEN_DIMENSIONS",
            "FOLLOW_UP_MAX_INPUT_TOKENS", "FOLLOW_UP_MAX_OUTPUT_TOKENS",
            "FOLLOW_UP_MAX_REASONING_TOKENS", "FOLLOW_UP_MAX_TOOL_CALLS",
            "FOLLOW_UP_MAX_FETCHES", "FOLLOW_UP_MAX_COST_USD")},
        "web_search_tool": {model: (__import__("llm_anthropic").WEB_SEARCH_TOOL_VERSION
                                    if str(model).startswith("claude-") else "openai_web_search")
                            for model in models},
        "resolver": {name: getattr(evidence_resolver, name) for name in
                     ("DEFAULT_TIMEOUT", "MAX_DOCUMENT_BYTES", "SUBPAGE_LIMIT")
                     if hasattr(evidence_resolver, name)},
        "exclusion_rules": {"max_employees": Config.MAX_EMPLOYEES,
                            "founded_min_year": Config.FOUNDED_MIN_YEAR,
                            "company_max_age": Config.COMPANY_MAX_AGE,
                            "max_distance_km": Config.MAX_DISTANCE_KM},
    }


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return " ".join(text.replace(",", " ").split())


def read_tasks(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8-sig")
    dialect = csv.Sniffer().sniff(raw.splitlines()[0], delimiters=";,")
    rows = list(csv.DictReader(raw.splitlines(), dialect=dialect))
    required = {"task_key", "gruppe", "unternehmen", "website", "branche", "suchfeld"}
    if not rows or not required.issubset(rows[0].keys()):
        raise ValueError("Aufgabenliste braucht die Spalten: " + ", ".join(sorted(required))
                         + " (optional: search_mode).")
    tasks, keys, names = [], set(), set()
    for number, row in enumerate(rows, start=2):
        row = {key: str(value or "").strip() for key, value in row.items() if key}
        if row["task_key"].startswith("#"):
            continue
        problems = []
        if not row["task_key"] or row["task_key"] in keys:
            problems.append("task_key fehlt oder doppelt")
        if row["gruppe"] not in GROUPS:
            problems.append("gruppe muss gt_hub oder extern sein")
        if not row["unternehmen"] or _norm(row["unternehmen"]) in names:
            problems.append("Unternehmen fehlt oder kommt doppelt vor")
        if len(row["suchfeld"]) < 3:
            problems.append("suchfeld fehlt")
        mode = row.get("search_mode", "").lower()
        if mode not in {"", "push", "pull"}:
            problems.append("search_mode muss push, pull oder leer sein")
        if problems:
            raise ValueError(f"Zeile {number}: " + "; ".join(problems))
        keys.add(row["task_key"])
        names.add(_norm(row["unternehmen"]))
        tasks.append({**row, "search_mode": mode})
    if len(tasks) < 2:
        raise ValueError("Mindestens zwei Aufgaben noetig.")
    return tasks


def assign_modes(tasks: list[dict], rng: random.Random) -> None:
    """PUSH/PULL je Gruppe ausgeglichen zufaellig, wo nicht vorgegeben."""
    for group in sorted(GROUPS):
        open_rows = [task for task in tasks if task["gruppe"] == group and not task["search_mode"]]
        rng.shuffle(open_rows)
        fixed = [task["search_mode"] for task in tasks
                 if task["gruppe"] == group and task["search_mode"]]
        pull_needed = max(0, (len(open_rows) + len(fixed)) // 2 - fixed.count("pull"))
        for index, task in enumerate(open_rows):
            task["search_mode"] = "pull" if index < pull_needed else "push"
            task["mode_assigned"] = "random"


def build_task(task: dict, event_time: str) -> ComparisonTask:
    mode = task["search_mode"]
    prompt = (PULL_TEMPLATE.format(area=task["suchfeld"], name=task["unternehmen"])
              if mode == "pull" else PUSH_TEMPLATE.format(name=task["unternehmen"]))
    area = " ".join(task["suchfeld"].split()) if mode == "pull" else ""
    organization_id = stable_organization_id(task["unternehmen"], task["website"])
    # Dieselbe Kennung wie die Oberflaeche (server._comparison_task).
    digest_source = prompt if mode == "push" else f"{prompt}|pull|{area}"
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:12]
    task_id = f"{organization_id}-prompt-{digest}"
    return ComparisonTask(
        task_id=task_id, organization_id=organization_id,
        organization_name=task["unternehmen"],
        organization_domain_hint=task["website"], search_prompt=prompt,
        task_group_id=task_id, dataset_split="holdout", event_time=event_time,
        search_mode=mode, search_area=area)


def _short_model(model: str) -> str:
    return "sol" if "sol" in model else "sonnet" if "sonnet" in model else model[:12]


def make_plan(args) -> int:
    out = Path(args.out)
    if out.exists():
        print(f"Abbruch: {out} existiert bereits. Ein eingefrorener Plan wird nicht ueberschrieben.")
        return 2
    rng = random.Random(f"veriscout-study|{args.seed}")
    tasks = read_tasks(Path(args.tasks))
    sheets_raw = json.loads(Path(args.case_sheets).read_text(encoding="utf-8"))
    missing = [task["task_key"] for task in tasks if task["task_key"] not in sheets_raw]
    if missing:
        raise ValueError("Fallblatt fehlt fuer: " + ", ".join(missing))
    budget_now = ExperimentBudget().__dict__
    deviating = {key: (budget_now.get(key), value) for key, value in PROFILE_VALUES.items()
                 if budget_now.get(key) != value}
    if deviating:
        raise ValueError("Budget weicht vom Profil der Arbeit ab (aktuell, erwartet): "
                         + json.dumps(deviating, ensure_ascii=False)
                         + ". Eintraege SCOUTREF_EVAL_* bzw. SCOUTREF_REASONING_EFFORT in .env pruefen.")
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    for model in models:
        if model not in Config.PRICES:
            raise ValueError(f"Fuer {model} ist kein Preis hinterlegt.")
    if args.modes == "push":
        # Hauptlauf nur PUSH (Kap. 7.3.2): Budgets sind an PUSH kalibriert.
        for task in tasks:
            if task["search_mode"] == "pull":
                raise ValueError(f"{task['task_key']}: PULL vorgegeben, Plan ist nur PUSH.")
            task["search_mode"] = "push"
            task["mode_assigned"] = "fixed_push"
    else:
        assign_modes(tasks, rng)
    protocol = None
    if getattr(args, "protocol_file", ""):
        protocol_path = Path(args.protocol_file)
        protocol = {"name": protocol_path.name,
                    "sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest()}
    event_time = _now()
    case_sheets, task_rows = {}, []
    for task in tasks:
        sheet = normalise_case_sheet({
            **sheets_raw[task["task_key"]],
            "organization_name": task["unternehmen"], "website": task["website"],
            "industry": sheets_raw[task["task_key"]].get("industry") or task["branche"],
            "search_area": task["suchfeld"] if task["search_mode"] == "pull" else "",
        })
        case_sheets[task["task_key"]] = sheet
        comparison = build_task(task, event_time)
        public = comparison.public_input(strict=True)
        task_rows.append({
            "task_key": task["task_key"], "gruppe": task["gruppe"],
            "unternehmen": task["unternehmen"], "website": task["website"],
            "branche": task["branche"], "search_mode": task["search_mode"],
            "mode_assigned": task.get("mode_assigned", "given"),
            "search_area": comparison.search_area,
            "search_prompt": comparison.search_prompt,
            "task_id": comparison.task_id,
            "task_input_hash": public.input_hash(),
            "prompt_hash": public.prompt_hash(),
            "case_sheet_sha256": case_sheet_hash(sheet),
        })
    stability_keys = sorted(rng.sample([t["task_key"] for t in task_rows],
                                       min(args.stability, len(task_rows))))
    pairs = []
    replicates = max(1, int(getattr(args, "replicates", 1) or 1))
    all_keys = [t["task_key"] for t in task_rows]
    for phase, (model, role, keys) in enumerate(
            [(model, "primary", all_keys) for model in models]
            + [(models[0], "stability", stability_keys)], start=1):
        if not keys:
            continue
        reps = range(1, replicates + 1) if role == "primary" else [replicates + 1]
        group = [dict(task_key=key, model=model, role=role, phase=phase,
                      replicate_index=rep) for key in keys for rep in reps]
        rng.shuffle(group)
        if len(reps) > 1:
            # Mehrere Laeufe je Aufgabe und Modell: Reihenfolge innerhalb der
            # Aufgabe abwechselnd (AB/BA), Startreihenfolge je Aufgabe zufaellig.
            # So hebt sich ein Reihenfolgeeffekt schon je Aufgabe auf.
            starts = {key: rng.random() < 0.5 for key in sorted(set(keys))}
            for item in group:
                ab_first = starts[item["task_key"]] ^ (item["replicate_index"] % 2 == 0)
                item["order"] = ["sas2", "mas"] if ab_first else ["mas", "sas2"]
        else:
            # Ausgeglichene Reihenfolge je Modell und Rolle: Haelfte AB, Haelfte BA.
            half = len(group) // 2 + (rng.random() < 0.5 and len(group) % 2)
            for index, item in enumerate(group):
                item["order"] = ["sas2", "mas"] if index < half else ["mas", "sas2"]
        for item in group:
            item["entry_id"] = (f"{item['task_key']}-{_short_model(model)}-"
                                f"{role}-r{item['replicate_index']}")
        rng.shuffle(group)
        pairs.extend(group)
    study_id = "studie-" + datetime.date.today().isoformat() + "-" + _sha(
        [args.seed, [t["task_input_hash"] for t in task_rows], models])[:8]
    per_model_limits = parse_model_limits(getattr(args, "max_usd_per_model", ""), models)
    total_limit = float(getattr(args, "max_total_usd", 0.0) or 0.0) or round(sum(per_model_limits.values()), 2)
    if total_limit <= 0:
        print("Abbruch: --max-total-usd oder --max-usd-per-model angeben (Obergrenze legt David fest).")
        return 2
    budget = ExperimentBudget()
    plan = {
        "schema_version": PLAN_SCHEMA, "study_id": study_id, "created_at": _now(),
        "event_time": event_time, "seed": args.seed, "models": models,
        "max_total_usd": total_limit,
        "max_usd_per_model": per_model_limits,
        "max_pair_cost_usd": round(budget.arm_max_cost_usd * 2, 4),  # inkl. Nachrecherche (M2)
        "version": Config.VERSION,
        "prompt_contract_version": Config.PROMPT_CONTRACT_VERSION,
        "budget_profile": Config.BUDGET_PROFILE_VERSION,
        "budget": {key: value for key, value in budget.__dict__.items() if key != "model"},
        "code_fingerprint": code_fingerprint(),
        "effective_config": effective_config(models),
        # Bewertungsprotokoll (Fragen, Trefferregel, Strittig-Regel, Ziehung),
        # vor dem ersten Lauf mit Fingerabdruck festgehalten.
        "rating_protocol": protocol,
        "randomization": (("Alle Aufgaben PUSH" if args.modes == "push"
                           else "PUSH/PULL je Gruppe ausgeglichen")
                          + ("; Reihenfolge SAS-2/MAS je Aufgabe und Modell abwechselnd, "
                             "Start zufaellig" if replicates > 1 else
                             "; Reihenfolge SAS-2/MAS je Modell und Rolle ausgeglichen")
                          + "; Stabilitaetsaufgaben zufaellig"),
        "tasks": task_rows, "case_sheets": case_sheets,
        "stability_task_keys": stability_keys, "pairs": pairs,
    }
    plan["plan_sha256"] = _sha(plan)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    counts = {}
    for item in pairs:
        counts[f"{item['model']} {item['role']}"] = counts.get(f"{item['model']} {item['role']}", 0) + 1
    print(json.dumps({"plan": str(out), "plan_sha256": plan["plan_sha256"],
                      "study_id": study_id, "tasks": len(task_rows), "pairs": counts,
                      "push": sum(t["search_mode"] == "push" for t in task_rows),
                      "pull": sum(t["search_mode"] == "pull" for t in task_rows),
                      "worst_case_usd": round(len(pairs) * plan["max_pair_cost_usd"], 2),
                      "hard_stop_usd": plan["max_total_usd"],
                      "rating_protocol": protocol}, ensure_ascii=False, indent=1))
    if protocol is None:
        print("Hinweis: Kein Bewertungsprotokoll angegeben (--protocol-file). "
              "Fuer die Hauptstudie das Protokoll vor dem Einfrieren festlegen.")
    return 0


def load_plan(path: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    stored = plan.pop("plan_sha256", "")
    if plan.get("schema_version") != PLAN_SCHEMA or _sha(plan) != stored:
        raise ValueError("Plan ist veraendert oder hat ein unbekanntes Format.")
    plan["plan_sha256"] = stored
    return plan


def ledger_path(plan_path: Path, plan: dict) -> Path:
    return plan_path.parent / f"kosten-{plan['study_id']}.json"


def load_ledger(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"entries": {}}


def save_ledger(path: Path, ledger: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(path)


def parse_model_limits(text: str, models: list[str]) -> dict:
    """'gpt-6.1-sol=28,claude-sonnet-5-5=26' -> {modell: USD}; nur Modelle des Plans."""
    limits = {}
    for part in str(text or "").split(","):
        if not part.strip():
            continue
        name, _, value = part.partition("=")
        name = name.strip()
        if name not in models:
            raise SystemExit(f"Abbruch: Modell {name!r} gehoert nicht zum Plan.")
        limits[name] = round(float(value.replace(",", ".").strip()), 2)
    return limits


def model_of_entry(plan: dict) -> dict:
    return {p["entry_id"]: p["model"] for p in plan["pairs"]}


def spent(ledger: dict, plan: dict, model: str | None = None) -> float:
    """Abgeschlossene Paare mit tatsaechlichen, abgebrochene mit Hoechstkosten.
    Mit ``model`` nur die Paare dieses Modells (Anbieterobergrenze)."""
    owner = model_of_entry(plan) if model else {}
    total = 0.0
    for entry_id, entry in ledger["entries"].items():
        if model and owner.get(entry_id) != model:
            continue
        if entry.get("status") == "done":
            total += float(entry.get("cost_usd") or 0)
        elif entry.get("status") == "started":
            total += float(plan["max_pair_cost_usd"])
        # Frueher abgebrochene Versuche desselben Paars bleiben verbucht.
        total += float(plan["max_pair_cost_usd"]) * len(entry.get("aborted_attempts") or [])
    return round(total, 6)


def run_record(plan: dict, item: dict, task_row: dict, result: dict) -> tuple[str, dict]:
    sheet = plan["case_sheets"][item["task_key"]]
    run_id = f"run-studie-{item['entry_id']}-{result['pair_id'][-6:]}"
    created = _now()
    view = operator_view([result], run_id=run_id, created_at=created)
    view["run_set"] = "studie"
    package = annotation_package(result)
    package["case_sheet"] = sheet
    package["case_sheet_sha256"] = task_row["case_sheet_sha256"]
    manifest = assignment_manifest(result)
    manifest.update({"model": item["model"], "study_role": item["role"],
                     "stratum": task_row["gruppe"]})
    return run_id, {
        "run_set": "studie",
        "study": {"study_id": plan["study_id"], "plan_sha256": plan["plan_sha256"],
                  "entry_id": item["entry_id"], "task_key": item["task_key"],
                  "model": item["model"], "role": item["role"],
                  "stratum": task_row["gruppe"], "phase": item["phase"],
                  "attempt": int(item.get("attempt") or 1)},
        "operator_view": view,
        "blind_pairs": [{"blind_annotation": package}],
        "assignment_manifests": [manifest],
        "reference": {"case_sheet": sheet,
                      "case_sheet_sha256": task_row["case_sheet_sha256"]},
        "run_bundle_manifest": {
            "code_fingerprint": plan["code_fingerprint"],
            "prompt_contract_version": plan["prompt_contract_version"],
            "budget_profile": plan["budget_profile"], "model": item["model"],
            "version": plan["version"],
        },
        "internal_pairs": [result],
    }


def run_phase(args) -> int:
    plan_path = Path(args.plan)
    plan = load_plan(plan_path)
    model = Config.MODEL
    problems = []
    if plan["prompt_contract_version"] != Config.PROMPT_CONTRACT_VERSION:
        problems.append("Promptfassung")
    if plan["budget_profile"] != Config.BUDGET_PROFILE_VERSION:
        problems.append("Budgetprofil")
    if plan["code_fingerprint"] != code_fingerprint():
        problems.append("Programmcode")
    if model not in plan["models"]:
        problems.append(f"Modell {model} gehoert nicht zum Plan")
    frozen_config = plan.get("effective_config")
    if frozen_config is None:
        problems.append("Plan ohne eingefrorene Laufzeitwerte (alter Plan)")
    elif frozen_config != json.loads(json.dumps(effective_config(plan["models"]))):
        current = json.loads(json.dumps(effective_config(plan["models"])))
        changed = sorted(key for key in set(frozen_config) | set(current)
                         if frozen_config.get(key) != current.get(key))
        problems.append("Laufzeitwerte (" + ", ".join(changed) + ")")
    if problems:
        print("Abbruch: Seit dem Einfrieren geaendert: " + ", ".join(problems)
              + ". Fuer Aenderungen einen neuen Plan anlegen.")
        return 2
    limit = min(float(args.max_total_usd or plan["max_total_usd"]), plan["max_total_usd"])
    roles = {"primary", "stability"} if args.role == "all" else {args.role}
    todo = [item for item in plan["pairs"] if item["model"] == model and item["role"] in roles]
    only = {x.strip() for x in str(getattr(args, "only", "") or "").split(",") if x.strip()}
    if only:
        todo = [item for item in todo if item["entry_id"] in only]
    ledger_file = ledger_path(plan_path, plan)
    ledger = load_ledger(ledger_file)
    pending = []
    for item in todo:
        entry = ledger["entries"].get(item["entry_id"], {})
        if entry.get("status") == "done":
            continue
        if (entry.get("status") == "started"
                and int(entry.get("attempt") or 1) >= MAX_ATTEMPTS):
            continue  # bleibt als abgebrochen verbucht und wird berichtet
        pending.append(item)
    print(json.dumps({"model": model, "roles": sorted(roles), "pending_pairs": len(pending),
                      "spent_usd": spent(ledger, plan), "hard_stop_usd": limit},
                     ensure_ascii=False))
    if not args.confirm_paid:
        print("Nur Plan angezeigt. Mit --confirm-paid ausfuehren (Kosten entstehen).")
        return 0
    if not pending:
        return 0
    if model.startswith("claude-") and not os.environ.get("ANTHROPIC_API_KEY"):
        print("Abbruch: ANTHROPIC_API_KEY fehlt in der .env.")
        return 2
    if not model.startswith("claude-") and not os.environ.get("OPENAI_API_KEY"):
        print("Abbruch: OPENAI_API_KEY fehlt in der .env.")
        return 2
    lock = plan_path.parent / f".lauf-{plan['study_id']}.lock"
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f"Abbruch: Es laeuft bereits ein Studienlauf ({lock.name}).")
        return 2
    os.close(descriptor)
    runs_dir = Path(os.environ.get("SCOUTREF_RUNS_DIR") or ROOT / "artifacts" / "runs")
    runs_dir.mkdir(parents=True, exist_ok=True)
    tasks = {task["task_key"]: task for task in plan["tasks"]}
    runner = PairedArchitectureRunner(live=True)
    try:
        for item in pending:
            current = spent(ledger, plan)
            model_limit = (plan.get("max_usd_per_model") or {}).get(model)
            model_ok = model_limit is None or budget_allows_pair(
                spent(ledger, plan, model), plan["max_pair_cost_usd"], model_limit)
            if not (model_ok and budget_allows_pair(current, plan["max_pair_cost_usd"], limit)):
                print(json.dumps({"status": "budget_stop", "stop": "Kostengrenze", "spent_usd": current,
                                  "limit_usd": limit,
                                  "needed_usd": round(plan["max_pair_cost_usd"] + PAIR_OVERRUN_MARGIN_USD, 2)},
                                 ensure_ascii=False))
                return 3
            task_row = tasks[item["task_key"]]
            # Dieselbe Aufgabe wie beim Einfrieren; run_pair prueft den Hash.
            comparison = ComparisonTask(
                task_id=task_row["task_id"],
                organization_id=stable_organization_id(task_row["unternehmen"], task_row["website"]),
                organization_name=task_row["unternehmen"],
                organization_domain_hint=task_row["website"],
                search_prompt=task_row["search_prompt"], task_group_id=task_row["task_id"],
                dataset_split="holdout", event_time=plan["event_time"],
                search_mode=task_row["search_mode"], search_area=task_row["search_area"])
            assignment = {
                "task_id": task_row["task_id"], "task_input_hash": task_row["task_input_hash"],
                "memory_enabled": False, "order": item["order"],
                "study_id": plan["study_id"],
                "execution_id": f"exec-{plan['study_id']}-{item['entry_id']}",
                "replicate_index": item["replicate_index"],
                "block_index": plan["pairs"].index(item) + 1,
                "allocation_seed": plan["seed"],
                "randomization_algorithm_version": "veriscout-study-plan-v1",
            }
            previous = ledger["entries"].get(item["entry_id"], {})
            aborted = list(previous.get("aborted_attempts") or [])
            if previous.get("status") == "started":
                # Ein Abbruch ohne Ergebnis (Netz, Ruhezustand, Strg+C) wird
                # verbucht und das ganze Paar einmal neu gestartet.
                aborted.append({"started_at": previous.get("started_at", ""),
                                "attempt": int(previous.get("attempt") or 1),
                                "booked_usd": plan["max_pair_cost_usd"]})
            attempt = len(aborted) + 1
            assignment["attempt"] = attempt
            ledger["entries"][item["entry_id"]] = {"status": "started", "started_at": _now(),
                                                   "model": model, "attempt": attempt,
                                                   "aborted_attempts": aborted}
            save_ledger(ledger_file, ledger)
            result = runner.run_pair(comparison, planned_assignment=assignment)
            item = {**item, "attempt": attempt}
            try:
                run_id, record = run_record(plan, item, task_row, result)
            except Exception as error:  # Ergebnis nie verlieren, Kosten sind entstanden
                run_id = f"run-studie-{item['entry_id']}-roh"
                record = {"run_set": "studie", "record_error": type(error).__name__,
                          "study": {"study_id": plan["study_id"], "entry_id": item["entry_id"],
                                    "plan_sha256": plan["plan_sha256"], "attempt": attempt},
                          "internal_pairs": [result]}
            (runs_dir / f"{run_id}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
            cost = round(sum(float((arm.get("resource_usage") or {}).get("cost_usd") or 0)
                             for arm in result["arms"]), 6)
            ledger["entries"][item["entry_id"]] = {
                "status": "done", "cost_usd": cost, "run_id": run_id,
                "model": model, "finished_at": _now(), "attempt": attempt,
                "aborted_attempts": aborted,
                "states": {arm["architecture_internal"]: arm.get("result_status")
                           for arm in result["arms"]}}
            save_ledger(ledger_file, ledger)
            print(json.dumps({"entry": item["entry_id"], "run_id": run_id, "cost_usd": cost,
                              "spent_usd": spent(ledger, plan),
                              "states": ledger["entries"][item["entry_id"]]["states"]},
                             ensure_ascii=False), flush=True)
    finally:
        lock.unlink(missing_ok=True)
    return 0


# 12.11.2026: Sicherheitsaufschlag fuer den Stopp. Die Pruefung vor einem
# Modellaufruf schaetzt die Eingabe ohne die erst spaeter gelieferten
# Suchergebnisse; ein Paar kann seine Hoechstkosten daher knapp ueberschreiten.
# Mit dem Aufschlag startet kein Paar, das die Grenze reissen koennte.
PAIR_OVERRUN_MARGIN_USD = 0.50


def budget_allows_pair(spent_usd: float, max_pair_cost: float, limit_usd: float) -> bool:
    return spent_usd + max_pair_cost + PAIR_OVERRUN_MARGIN_USD <= limit_usd + 1e-9


def schedule(plan: dict) -> list[dict]:
    """Deterministische Abarbeitungsreihenfolge (12.11.2026).

    Erst alle Hauptpaare des ersten Laufs, dann des zweiten usw., zuletzt die
    Stabilitaetspaare. Innerhalb eines Laufs wechseln die Modelle Paar fuer
    Paar ab; die Reihenfolge je Modell ist die im Plan (nach Seed gemischt),
    das Startmodell haengt vom Seed ab. Die AB/BA-Reihenfolge der Arme bleibt
    die des Plans.
    """
    models = list(plan["models"])
    start = int(_sha([plan.get("seed"), "start-model"])[:8], 16) % max(1, len(models))
    models = models[start:] + models[:start]
    primary = [p for p in plan["pairs"] if p["role"] == "primary"]
    out = []
    for rep in sorted({p["replicate_index"] for p in primary}):
        lanes = [[p for p in primary if p["replicate_index"] == rep and p["model"] == m] for m in models]
        for index in range(max((len(lane) for lane in lanes), default=0)):
            for lane in lanes:
                if index < len(lane):
                    out.append(lane[index])
    out.extend(p for p in plan["pairs"] if p["role"] != "primary")
    return out


def runner_call(command: list[str]) -> int:
    """Ein Paar als eigener Prozess (in Tests ersetzbar)."""
    return subprocess.call(command)


def run_all(args) -> int:
    plan_path = Path(args.plan)
    plan = load_plan(plan_path)
    order = schedule(plan)
    limit = float(args.max_total_usd or plan["max_total_usd"])
    if not args.confirm_paid:
        print(json.dumps({"order": [p["entry_id"] for p in order], "pairs": len(order),
                          "max_pair_cost_usd": plan["max_pair_cost_usd"],
                          "pair_overrun_margin_usd": PAIR_OVERRUN_MARGIN_USD,
                          "hard_stop_usd": min(limit, plan["max_total_usd"])}, ensure_ascii=False, indent=1))
        print("Nur Reihenfolge angezeigt. Mit --confirm-paid ausfuehren (Kosten entstehen).")
        return 0
    total_limit = min(limit, plan["max_total_usd"])
    model_limits = dict(plan.get("max_usd_per_model") or {})
    stopped: dict[str, list[str]] = {}
    for position, item in enumerate(order, start=1):
        ledger = load_ledger(ledger_path(plan_path, plan))
        entry = ledger["entries"].get(item["entry_id"], {})
        if entry.get("status") == "done" or (
                entry.get("status") == "started" and int(entry.get("attempt") or 1) >= MAX_ATTEMPTS):
            continue
        model = item["model"]
        if model in stopped:
            stopped[model].append(item["entry_id"])
            continue
        model_limit = model_limits.get(model)
        if model_limit is not None and not budget_allows_pair(
                spent(ledger, plan, model), plan["max_pair_cost_usd"], model_limit):
            # Anbieterobergrenze erreicht: uebrige Paare dieses Modells entfallen,
            # das andere Modell laeuft weiter.
            stopped[model] = [item["entry_id"]]
            print(json.dumps({"status": "budget_stop", "model": model,
                              "spent_model_usd": spent(ledger, plan, model),
                              "limit_model_usd": model_limit}, ensure_ascii=False), flush=True)
            continue
        if not budget_allows_pair(spent(ledger, plan), plan["max_pair_cost_usd"], total_limit):
            remaining = [p["entry_id"] for p in order[position - 1:]
                         if ledger["entries"].get(p["entry_id"], {}).get("status") != "done"]
            print(json.dumps({"status": "budget_stop", "spent_usd": spent(ledger, plan),
                              "limit_usd": total_limit, "not_run": remaining}, ensure_ascii=False, indent=1), flush=True)
            return 3
        command = [sys.executable, str(Path(__file__).resolve()), "run", "--plan", args.plan,
                   "--model", model, "--role", item["role"], "--only", item["entry_id"],
                   "--max-total-usd", str(limit)]
        command.append("--confirm-paid")
        print(f"== Paar {position}/{len(order)}: {item['entry_id']}", flush=True)
        code = runner_call(command)
        if code == 3:
            stopped.setdefault(model, []).append(item["entry_id"])
            continue
        if code != 0:
            return code
    if stopped:
        print(json.dumps({"status": "budget_stop", "not_run": stopped}, ensure_ascii=False, indent=1))
        return 3
    return 0


def status(args) -> int:
    plan_path = Path(args.plan)
    plan = load_plan(plan_path)
    ledger = load_ledger(ledger_path(plan_path, plan))
    rows = {}
    for item in plan["pairs"]:
        key = f"{item['model']} · {item['role']}"
        state = ledger["entries"].get(item["entry_id"], {}).get("status", "offen")
        row = rows.setdefault(key, {"offen": 0, "started": 0, "done": 0, "abgebrochene_versuche": 0})
        row[state] += 1
        row["abgebrochene_versuche"] += len(
            ledger["entries"].get(item["entry_id"], {}).get("aborted_attempts") or [])
    print(json.dumps({"study_id": plan["study_id"], "phases": rows,
                      "spent_usd": spent(ledger, plan),
                      "hard_stop_usd": plan["max_total_usd"]}, ensure_ascii=False, indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--tasks", required=True)
    p.add_argument("--case-sheets", required=True)
    p.add_argument("--seed", required=True)
    p.add_argument("--out", default="studie/plan.json")
    p.add_argument("--models", default=",".join(DEFAULT_MODELS))
    p.add_argument("--modes", default="push", choices=["mixed", "push"],
                   help="push = alle Aufgaben PUSH; mixed = PUSH/PULL je Gruppe zur Haelfte")
    p.add_argument("--stability", type=int, default=10)
    p.add_argument("--replicates", type=int, default=1,
                   help="Hauptpaare je Aufgabe und Modell (Ersatzplan: 2)")
    # 12.11.2026: keine feste Vorgabe mehr; David legt die Obergrenzen fest.
    p.add_argument("--max-total-usd", type=float, default=0.0,
                   help="Gesamtobergrenze; ohne Angabe die Summe von --max-usd-per-model")
    p.add_argument("--max-usd-per-model", default="",
                   help="Obergrenze je Modell/Anbieter, z. B. gpt-6.1-sol=28,claude-sonnet-5-5=26")
    p.add_argument("--protocol-file", default="",
                   help="Bewertungsprotokoll, dessen SHA-256 in den Plan eingeht")
    r = sub.add_parser("run")
    r.add_argument("--plan", required=True)
    r.add_argument("--model", required=True)
    r.add_argument("--role", default="primary", choices=["primary", "stability", "all"])
    r.add_argument("--max-total-usd", type=float, default=0.0)
    r.add_argument("--confirm-paid", action="store_true")
    r.add_argument("--only", default="", help="kommagetrennte entry_ids (nur diese Paare)")
    a = sub.add_parser("run-all")
    a.add_argument("--plan", required=True)
    a.add_argument("--max-total-usd", type=float, default=0.0)
    a.add_argument("--confirm-paid", action="store_true")
    s = sub.add_parser("status")
    s.add_argument("--plan", required=True)
    args = parser.parse_args()
    try:
        return {"plan": make_plan, "run": run_phase, "run-all": run_all,
                "status": status}[args.command](args)
    except ValueError as error:
        print("Fehler: " + str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
