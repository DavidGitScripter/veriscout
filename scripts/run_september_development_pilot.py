"""Zwei budgetbegrenzte Entwicklungs-Pairs; keine Holdout-/CRM-Aktionen."""
from pathlib import Path
import datetime
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from compare_architectures import ComparisonTask, ExperimentBudget, PairedArchitectureRunner


def main():
    revision = "v2" if "--revision-v2" in sys.argv else "v1"
    output = ROOT.parent / "review_2026_09_05" / ("development_pilot" if revision == "v1" else "development_pilot_v2")
    output.mkdir(parents=True, exist_ok=True)
    tasks = [
        ("public-max-wild", "Max Wild GmbH", "maxwild.com",
         "Suche ein reales B2B-Startup, dessen Produkt einen oeffentlich belegten "
         "Prozess von Max Wild im Tiefbau oder bei der Aufbereitung mineralischer "
         "Baustoffe nachhaltiger oder effizienter machen koennte. Ermittle den "
         "konkreten Zielprozess zuerst aus oeffentlichen Quellen. Behaupte keine "
         "internen Reststoffmengen, Kosten oder bestehende Kooperation."),
        ("public-baufritz", "Baufritz GmbH & Co. KG", "baufritz.com",
         "Suche ein reales B2B-Startup, dessen Produkt einen oeffentlich belegten "
         "Prozess im Holzfertighausbau der Zielorganisation nachhaltiger oder "
         "effizienter machen koennte. Ermittle Prozess und moegliche Schnittstelle "
         "ausschliesslich aus oeffentlichen Quellen; unterstelle weder einen "
         "konkreten Abfallstrom noch technische Kompatibilitaet oder Preisvorteile."),
    ]
    budget = ExperimentBudget(max_output_tokens=8000, max_tool_calls=6,
        max_candidates=1, max_input_tokens=30000, max_reasoning_tokens=4000,
        max_model_calls=2, max_resolver_fetches=8, max_cost_usd=0.25)
    if revision == "v2":
        # Geaenderte Konfiguration ist eine NEUE Entwicklungsiteration,
        # niemals ein Ersatz fuer die fehlgeschlagenen v1-Ergebnisse.
        tasks = tasks[:1]
        budget = ExperimentBudget(max_output_tokens=12000, max_tool_calls=6,
            max_candidates=1, max_input_tokens=80000, max_reasoning_tokens=4000,
            max_model_calls=2, max_resolver_fetches=8, max_cost_usd=0.50)
    plan = {"purpose": "development_only", "max_pairs": 2,
            "nominal_total_cost_cap_usd": 1.0,
            "warning": "Estimated API ceiling, not a provider billing limit. No quality annotations.",
            "tasks": tasks, "memory_enabled": False, "revision": revision,
            "budget": budget.__dict__}
    plan_path = output / "plan.json"
    if plan_path.exists():
        raise SystemExit("Pilot bereits angelegt; kein unbeabsichtigter kostenpflichtiger Wiederholungslauf.")
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    runner = PairedArchitectureRunner(budget=budget, live=True)
    for index, (task_id, name, domain, prompt) in enumerate(tasks):
        task = ComparisonTask(task_id=task_id, organization_name=name,
            organization_domain_hint=domain, search_prompt=prompt,
            dataset_split="development",
            event_time=datetime.datetime.now(datetime.timezone.utc).isoformat())
        public = task.public_input(strict=True)
        assignment = {"task_id": task_id, "task_input_hash": public.input_hash(),
            "memory_enabled": False, "order": ["sas2", "mas"] if index == 0 else ["mas", "sas2"],
            "study_id": "development-audit-2026-09-05", "execution_id": "exec-dev-" + task_id,
            "randomization_algorithm_version": "development_counterbalanced_two_tasks"}
        result = runner.run_pair(task, planned_assignment=assignment)
        (output / (task_id + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2))
        for arm in result["arms"]:
            print(json.dumps({"task": task_id, "architecture": arm["architecture_internal"],
                "status": arm["result_status"], "resources": arm["resource_usage"],
                "candidate_names": [d.get("candidate", {}).get("name") for d in arm["decisions"]]},
                ensure_ascii=False), flush=True)
        if any(arm["technical_failure"] for arm in result["arms"]):
            print("Technischer Fehler: keine weiteren bezahlten Pairs.", flush=True)
            break


if __name__ == "__main__":
    main()
