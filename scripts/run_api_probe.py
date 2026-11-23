"""Bezahlter Probelauf: wenige gepaarte SAS-2/MAS-Vergleiche mit echter API.

Zweck: technische Pruefung vor der Hauptstudie (Entwicklungsdaten, kein
Holdout). Jeder Lauf wird unter artifacts/runs/ gespeichert und kann in der
Oberflaeche ohne erneute API-Kosten geoeffnet werden.

Aufruf (Kosten entstehen!):
    .venv/bin/python scripts/run_api_probe.py --confirm-paid --pairs 5
Ohne --confirm-paid wird nur der Plan angezeigt.

Eingangspruefung eines Modells fuer die Hauptstudie (vorab festgelegt, fuer
jedes Modell gleich): drei Paare auf den Probeaufgaben. Bestanden, wenn
(1) kein Arm technisch scheitert, (2) mindestens eine Quelle mit eigener
Quellenangabe des Anbieters abgerufen und ihr Auszug gefunden wird und
(3) mindestens ein Arm einen Kandidaten liefert.
    .venv/bin/python scripts/run_api_probe.py --model claude-sonnet-5-5 \
        --pairs 3 --entry-check --confirm-paid
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Modellwahl muss vor dem Import der Konfiguration feststehen. Fuer den
# Architekturvergleich nutzen SAS-2, Scouting und Verifikation dieselbe Kennung.
if "--model" in sys.argv:
    import os
    os.environ["SCOUTREF_OPENAI_MODEL"] = sys.argv[sys.argv.index("--model") + 1]

from compare_architectures import (ComparisonTask, PairedArchitectureRunner,  # noqa: E402
                                   annotation_package, assignment_manifest,
                                   operator_view)
from core import Config  # noqa: E402

# Entwicklungsaufgaben: oeffentlich bekannte mittelstaendische Unternehmen.
# Sie gehoeren NICHT zur spaeteren Holdout-Menge.
# Gleicher Wortlaut wie die feste Studienvorlage (scripts/run_study.py,
# PUSH_TEMPLATE), damit die Generalprobe genau den Studienauftrag testet.
PUSH_TEMPLATE = (
    "Suche ein reales, aktives B2B-Startup, dessen Produkt einen oeffentlich belegten "
    "Prozess von {name} nachhaltiger oder effizienter machen koennte. "
    "Ermittle den konkreten Zielprozess zuerst aus oeffentlichen Quellen. "
    "Ob ein passendes Startup-Unternehmen existiert, ist offen; ein leeres "
    "Ergebnis ist zulaessig.")
TASKS = [
    ("probe-max-wild", "Max Wild GmbH", PUSH_TEMPLATE.format(name="Max Wild GmbH")),
    ("probe-baufritz", "Baufritz GmbH & Co. KG", PUSH_TEMPLATE.format(name="Baufritz GmbH & Co. KG")),
    ("probe-goldhofer", "Goldhofer AG", PUSH_TEMPLATE.format(name="Goldhofer AG")),
    ("probe-suedpack", "Südpack Verpackungen GmbH & Co. KG", PUSH_TEMPLATE.format(name="Südpack Verpackungen GmbH & Co. KG")),
    ("probe-dachser", "Dachser SE", PUSH_TEMPLATE.format(name="Dachser SE")),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=int, default=5)
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--max-total-usd", type=float, default=6.5)
    parser.add_argument("--only", default="", help="kommagetrennte task_ids")
    parser.add_argument("--model", default="", help="z. B. claude-sonnet-5-5")
    parser.add_argument("--run-set", default="probe", choices=["probe", "studie"],
                        help="studie = Lauf fuer die Masterarbeit (getrennt gelistet)")
    parser.add_argument("--entry-check", action="store_true",
                        help="Eingangspruefung des Modells nach festem Kriterium auswerten")
    args = parser.parse_args()

    tasks = TASKS[:max(1, min(args.pairs, len(TASKS)))]
    if args.only:
        wanted = {item.strip() for item in args.only.split(",")}
        tasks = [task for task in TASKS if task[0] in wanted]
    runner = PairedArchitectureRunner(live=True)
    worst = runner.budget.arm_max_cost_usd * 2 * len(tasks)  # inkl. Nachrecherche (M2)
    print(json.dumps({"model": runner.budget.model, "pairs": len(tasks),
                      "worst_case_usd": round(worst, 2),
                      "budget_profile": Config.BUDGET_PROFILE_VERSION,
                      "tasks": [task[0] for task in tasks]}, ensure_ascii=False))
    if worst > args.max_total_usd:
        print("Abbruch: Worst-Case-Kosten ueber --max-total-usd.")
        return 2
    if not args.confirm_paid:
        print("Nur Plan angezeigt. Mit --confirm-paid ausfuehren.")
        return 0

    runs_dir = ROOT / "artifacts" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    total = 0.0
    results = []
    for index, (task_id, name, prompt) in enumerate(tasks):
        task = ComparisonTask(
            task_id=task_id, organization_name=name, search_prompt=prompt,
            dataset_split="development",
            event_time=datetime.datetime.now(datetime.timezone.utc).isoformat())
        public = task.public_input(strict=True)
        # Ausgeglichene Reihenfolge ueber die Probelaeufe (AB/BA im Wechsel).
        assignment = {
            "task_id": task_id, "task_input_hash": public.input_hash(),
            "memory_enabled": False,
            "order": ["sas2", "mas"] if index % 2 == 0 else ["mas", "sas2"],
            "study_id": f"api-probe-2026-10-16-{runner.budget.model}",
            "execution_id": f"exec-probe-{task_id}",
            "randomization_algorithm_version": "probe_alternating_ab_ba",
        }
        result = runner.run_pair(task, planned_assignment=assignment)
        results.append(result)
        run_id = "run-probe-" + uuid.uuid4().hex[:12]
        created = datetime.datetime.now(datetime.timezone.utc).isoformat()
        view = operator_view([result], run_id=run_id, created_at=created)
        view["run_set"] = args.run_set
        record = {
            "run_set": args.run_set,
            "operator_view": view,
            "blind_pairs": [{"blind_annotation": annotation_package(result)}],
            "assignment_manifests": [assignment_manifest(result)],
            "internal_pair": result,
        }
        (runs_dir / f"{run_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        for arm in result["arms"]:
            usage = arm["resource_usage"]
            total += float(usage.get("cost_usd") or 0)
            print(json.dumps({
                "run_id": run_id, "task": task_id,
                "arm": arm["architecture_internal"],
                "status": arm["result_status"],
                "states": arm.get("decision_states"),
                "failure": usage.get("failure_reasons"),
                "deviations": arm.get("protocol_deviations"),
                "tokens_in": usage.get("input_tokens"),
                "tokens_out": usage.get("output_tokens"),
                "web": usage.get("web_calls"),
                "fetches": usage.get("resolver_fetches"),
                "cost_usd": usage.get("cost_usd"),
                "seconds": round((usage.get("wall_latency_ms") or 0) / 1000, 1),
                "candidates": [d["candidate"].get("name") for d in arm["decisions"]],
            }, ensure_ascii=False), flush=True)
        print(json.dumps({"cumulative_cost_usd": round(total, 4)}), flush=True)
        if total > args.max_total_usd:
            print("Kostenstopp erreicht.")
            break
    if args.entry_check:
        verdict = entry_check(results)
        verdict["model"] = runner.budget.model
        print(json.dumps({"entry_check": verdict}, ensure_ascii=False, indent=1))
    return 0


def entry_check(results: list[dict]) -> dict:
    """Vorab festgelegtes Eingangskriterium, fuer jedes Modell identisch."""
    arms = [arm for result in results for arm in result.get("arms", [])]
    technical = sum(arm.get("result_status") == "technical_error" for arm in arms)
    verified_sources = sum(
        1 for arm in arms for decision in arm.get("decisions") or []
        for source in (decision.get("candidate") or {}).get("sources") or []
        if source.get("citation_verified") and source.get("resolved_status") == "resolved"
        and source.get("excerpt_verified"))
    arms_with_candidates = sum(bool(arm.get("decisions")) for arm in arms)
    criteria = {
        "no_technical_error": technical == 0,
        "native_citation_resolved": verified_sources > 0,
        "candidate_found": arms_with_candidates > 0,
    }
    return {"pairs": len(results), "technical_error_arms": technical,
            "verified_sources": verified_sources,
            "arms_with_candidates": arms_with_candidates,
            "criteria": criteria, "passed": all(criteria.values()) and len(results) >= 3}


if __name__ == "__main__":
    raise SystemExit(main())
