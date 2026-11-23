"""Variante A: Fallblatt, Offline-Bewertung, Einigung, Auswertung und Studienplan."""
import argparse
import json
import os

import pytest

import server
from case_sheet import case_sheet_hash, normalise_case_sheet
from compare_architectures import (ComparisonTask, ExperimentBudget,
                                   annotation_package, assignment_manifest)
from evaluation_analysis import (NOT_ASSESSABLE,
                                 bayesian_paired_difference,
                                 krippendorff_alpha_nominal, paired_metrics)
from rating_sheet import (build_rating_key, merge_ratings,
                          render_rating_sheet_html)
from study_controls import StudyBudgetLedger

MARKER = "FALLBLATT-MARKER-7Q"
SHEET = {"profile": f"Kurzprofil {MARKER}", "public_sources_only": True,
         "processes": [{"text": "Schleifen", "source_url": "https://firma.example/p"}],
         "exclusion_criteria": ["reines Endkundenprodukt"]}


def _candidate(cid, name, website=""):
    return {
        "candidate_id": cid, "name": name, "website": website,
        "description": "Rohfund, keine verifizierte Empfehlung",
        "unresolved_requirements": ["input_stream"],
        "sources": [
            {"source_id": "s1", "url": f"https://{cid}.example/a", "excerpt": "Beleg eins",
             "excerpt_match_mode": "exact", "citation_verified": True},
            {"source_id": "s2", "url": f"https://{cid}.example/b", "excerpt": "Nur Schritt 1"},
        ],
        "evidence_matrix": {"claim_manifest": [{
            "claim_id": "c1", "claim_text": f"{name} bietet Verfahren X", "field": "identity",
            "source_id": "s1", "excerpt": "Beleg eins", "stance": "support"}]},
    }


def _arm(arch, code, candidates):
    return {
        "blind_arm_id": code, "architecture_internal": arch,
        "result_status": "completed" if candidates else "abstention",
        "primary_analysis_eligible": True,
        "positive_candidate_ids": [c["candidate_id"] for c in candidates],
        "decisions": [{"candidate": c} for c in candidates],
        "resource_usage": {"cost_usd": 0.4},
    }


def _task(name):
    return ComparisonTask(
        task_id=f"task-{name}", organization_name=name,
        search_prompt="Suche ein reales B2B-Startup fuer einen belegten Prozess.",
        dataset_split="holdout")


def _result(task_name, pair_id, sas, mas):
    task = _task(task_name)
    canonical = task.public_input(strict=False).canonical_dict()
    canonical["task_id"] = task.task_id
    return {"pair_id": pair_id, "task": canonical, "order": ["sas2", "mas"],
            "arms": [_arm("sas2", f"arm-{pair_id}-x", sas),
                     _arm("mas", f"arm-{pair_id}-y", mas)]}


def _record(result, model, role="primary", stratum="gt_hub", sheet=None):
    package = annotation_package(result)
    if sheet:
        package["case_sheet"] = sheet
    manifest = assignment_manifest(result)
    return {"run_set": "studie",
            "study": {"model": model, "role": role, "stratum": stratum},
            "operator_view": {"task": result["task"], "model": model},
            "blind_pairs": [{"blind_annotation": package}],
            "assignment_manifests": [manifest]}


def test_krippendorff_alpha_reproduces_published_nominal_example():
    # Krippendorff (2011), Beispiel mit vier Codierenden und fehlenden Werten.
    data = [[1, 1, None, 1], [2, 2, 3, 2], [3, 3, 3, 3], [3, 3, 3, 3],
            [2, 2, 2, 2], [1, 2, 3, 4], [4, 4, 4, 4], [1, 1, 2, 1],
            [2, 2, 2, 2], [None, 5, 5, 5], [None, None, 1, 1], [None, 3, None, None]]
    assert krippendorff_alpha_nominal(data) == pytest.approx(0.743, abs=0.001)
    assert krippendorff_alpha_nominal([[True, True], [True, True]]) is None
    assert krippendorff_alpha_nominal(
        [[True, NOT_ASSESSABLE], [True, True], [False, False]],
        missing=(NOT_ASSESSABLE,)) == 1.0


def test_blind_package_shows_only_claims_and_their_sources():
    result = _result("Firma", "pair-1", [_candidate("a", "Alpha")], [])
    package = annotation_package(result)
    encoded = json.dumps(package)
    assert "Rohfund" not in encoded and "unresolved_requirements" not in encoded
    assert "excerpt_match_mode" not in encoded and "citation_verified" not in encoded
    candidates = [d["candidate"] for arm in package["arms"] for d in arm["decisions"]]
    assert len(candidates) == 1
    assert [s["source_id"] for s in candidates[0]["sources"]] == ["s1"]
    assert set(candidates[0]) == {"candidate_id", "name", "sources", "claims_for_annotation"}


def test_case_sheet_is_stored_as_reference_and_never_given_to_the_architectures(tmp_path):
    seen_tasks = []

    class StubRunner:
        def __init__(self, live=False, memory_records=None):
            self.budget = ExperimentBudget()

        def run_pair(self, task, memory_enabled=False, planned_assignment=None):
            seen_tasks.append(task)
            canonical = task.public_input(strict=True).canonical_dict()
            return {"pair_id": "pair-cs", "task": canonical, "order": ["sas2", "mas"],
                    "arms": [_arm("sas2", "arm-a", []), _arm("mas", "arm-b", [])]}

    saved = {}
    old = (server.PairedArchitectureRunner, server.LIVE_EVAL_ENABLED, server.OPERATOR_TOKEN,
           server._save_unblinding_records, server.STUDY_BUDGET, server.STUDY_PLAN_ROOT,
           server._save_run_record, os.environ.get("OPENAI_API_KEY"))
    try:
        server.PairedArchitectureRunner = StubRunner
        server.LIVE_EVAL_ENABLED = True
        server.OPERATOR_TOKEN = "test-operator-token"
        server._save_unblinding_records = lambda: None
        server._save_run_record = lambda run_id, record: saved.update({run_id: record})
        server.STUDY_BUDGET = StudyBudgetLedger(str(tmp_path / "budget.json"), 8.0)
        server.STUDY_PLAN_ROOT = str(tmp_path / "plans")
        os.environ["OPENAI_API_KEY"] = "test-key-not-used"
        request = type("R", (), {"headers": {"X-VeriScout-Token": "test-operator-token"}})()
        base = dict(organization_name="Fallblatt GmbH",
                    search_prompt="Suche ein reales B2B-Startup fuer einen belegten Prozess.",
                    dataset_split="pilot", confirm_live=True)
        rejected = server.comparison_run(server.ComparisonReq(
            **base, idempotency_key="case-sheet-test-rejected-0001",
            case_sheet={"profile": "ohne Bestaetigung"}), request)
        assert rejected.status_code == 422 and not seen_tasks
        result = server.comparison_run(server.ComparisonReq(
            **base, idempotency_key="case-sheet-test-accepted-0001",
            case_sheet=SHEET), request)
        assert result["status"] == "completed"
        task = seen_tasks[0]
        assert MARKER not in json.dumps(task.__dict__, default=str)
        assert MARKER not in task.public_input(strict=True).prompt()
        record = saved[result["run_id"]]
        assert MARKER in record["reference"]["case_sheet"]["profile"]
        package = record["blind_pairs"][0]["blind_annotation"]
        assert package["case_sheet_sha256"] == case_sheet_hash(normalise_case_sheet(SHEET))
        assert record["assignment_manifests"][0]["model"] == ExperimentBudget().model
    finally:
        (server.PairedArchitectureRunner, server.LIVE_EVAL_ENABLED, server.OPERATOR_TOKEN,
         server._save_unblinding_records, server.STUDY_BUDGET, server.STUDY_PLAN_ROOT,
         server._save_run_record, key) = old
        if key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = key


def _scenario():
    sheet = normalise_case_sheet(SHEET)
    alpha = _candidate("alpha1", "Alpha GmbH", "https://www.alpha.example")
    alpha_no_site = _candidate("alpha2", "Alpha")
    beta = _candidate("beta", "Beta AG", "https://beta.example")
    gamma = _candidate("gamma", "Gamma", "https://gamma.example")
    results = [
        (_result("A", "pair-a-sol", [alpha], [dict(alpha, candidate_id="alpha3")]), "sol", "primary", "gt_hub"),
        (_result("A", "pair-a-son", [], [alpha_no_site]), "sonnet", "primary", "gt_hub"),
        (_result("B", "pair-b-sol", [beta], [gamma]), "sol", "primary", "extern"),
        (_result("B", "pair-b-son", [dict(beta, candidate_id="beta2")], []), "sonnet", "primary", "extern"),
        (_result("A", "pair-a-sol-r2", [dict(alpha, candidate_id="alpha4")], []), "sol", "stability", "gt_hub"),
    ]
    records = [_record(r, m, role, stratum, sheet) for r, m, role, stratum in results]
    return records


def _ratings(key, overrides):
    names = {e["entity_unit_id"]: e["name"] for e in key["entities"]}
    out = []
    for rater in ("R1", "R2"):
        entity = {}
        for unit, name in names.items():
            values = overrides.get((rater, name.split()[0]), ("yes", "yes"))
            entity[unit] = {"qualified": values[0], "valid_entity": values[1], "comment": ""}
        occurrence = {o["occurrence_unit_id"]: {"relation_correct": "yes",
                                                "claim_support_complete": "yes",
                                                "over_match": "no", "comment": ""}
                      for o in key["occurrences"]}
        out.append({"schema_version": "veriscout-ratings-v1", "sheet_id": key["sheet_id"],
                    "rater_id": rater, "entity_ratings": entity,
                    "occurrence_ratings": occurrence})
    return out


def test_rating_sheet_merges_duplicates_and_contains_no_architecture_hints():
    key, sheet = build_rating_key(_scenario())
    names = sorted(e["name"] for e in key["entities"])
    # Alpha mit und ohne Website ist ein Startup; Stabilitaetspaar ausgeschlossen.
    assert names == ["Alpha GmbH", "Beta AG", "Gamma"]
    alpha = next(e for e in key["entities"] if e["name"] == "Alpha GmbH")
    assert len(alpha["occurrence_unit_ids"]) == 3
    html = render_rating_sheet_html(sheet)
    for forbidden in ("sas2", "SAS-2", '"mas"', "blind_arm", "arm-pair", "pair-a-sol",
                      "Rohfund", "architecture"):
        assert forbidden not in html
    assert MARKER in html and "Nicht beurteilbar" in html
    again, _ = build_rating_key(_scenario())
    assert again["sheet_id"] == key["sheet_id"]


def test_merge_requires_documented_adjudication_then_analysis_runs():
    records = _scenario()
    key, _ = build_rating_key(records)
    ratings = _ratings(key, {("R1", "Beta"): ("no", "yes"), ("R2", "Beta"): ("no", "yes"),
                             ("R1", "Gamma"): ("yes", "yes"), ("R2", "Gamma"): ("na", "yes")})
    first = merge_ratings(key, ratings)
    assert first["status"] == "needs_adjudication"
    assert [(d["startup"], d["metric"]) for d in first["disagreements"]] == [("Gamma", "qualified")]
    unit = first["disagreements"][0]["unit_id"]
    missing_reason = merge_ratings(key, ratings, {f"{unit}|qualified": {"value": "disputed"}})
    assert missing_reason["status"] == "needs_adjudication"
    done = merge_ratings(key, ratings, {f"{unit}|qualified": {
        "value": "disputed", "reason": "Fachwissen zur Eignung fehlt beiden."}})
    assert done["status"] == "complete"
    rows = done["final"]["annotations"]
    assert len(rows) == 2 * len(key["occurrences"])
    manifests = [m for r in records for m in server._record_manifests(r)]
    metrics = paired_metrics(rows, manifests)
    itt = metrics["primary_itt"]
    assert itt["assigned_pairs"] == 4 and itt["task_clusters"] == 2
    assert itt["mean_success"] == {"sas2": 0.25, "mas": 0.5}
    assert itt["sensitivity"]["disputed_as_hit"]["mean_success"]["mas"] == 0.75
    assert set(metrics["by_model"]) == {"sol", "sonnet"}
    assert set(metrics["by_stratum"]) == {"gt_hub", "extern"}
    assert metrics["interrater_alpha"]["qualified"] == 1.0
    assert metrics["disputed_units"]["qualified"] == 1
    assert metrics["stability"]["sas2"]["tasks_with_repetitions"] == 1
    assert bayesian_paired_difference(itt, draws=500)["task_clusters"] == 2
    for block in metrics["by_model"].values():
        assert bayesian_paired_difference(block, draws=200)["task_clusters"] == 2


def test_not_assessable_is_never_a_hit():
    records = _scenario()
    key, _ = build_rating_key(records)
    overrides = {}
    for rater in ("R1", "R2"):
        overrides.update({(rater, "Alpha"): ("na", "yes"), (rater, "Beta"): ("no", "yes"),
                          (rater, "Gamma"): ("no", "yes")})
    ratings = _ratings(key, overrides)
    done = merge_ratings(key, ratings)
    assert done["status"] == "complete"
    rows = done["final"]["annotations"]
    assert all(row["qualified"] == NOT_ASSESSABLE for row in rows
               if row["entity_unit_id"] == next(
                   e["entity_unit_id"] for e in key["entities"] if e["name"] == "Alpha GmbH"))
    metrics = paired_metrics(rows, [m for r in records for m in server._record_manifests(r)])
    assert metrics["primary_itt"]["mean_success"] == {"sas2": 0.0, "mas": 0.0}
    assert metrics["not_assessable_units"]["qualified"] == 1
    assert all(row["disputed_judgments"] == 0 for row in metrics["arm_metrics"])
    assert metrics["disputed_units"]["qualified"] == 0


def test_rating_and_merge_endpoints_are_cost_free_and_open_locally(tmp_path, monkeypatch):
    records = _scenario()
    monkeypatch.setattr(server, "RUNS_DIR", str(tmp_path))
    for index, record in enumerate(records):
        (tmp_path / f"run-studie-{index}.json").write_text(json.dumps(record), encoding="utf-8")
    result = server.comparison_rating_sheet(server.RatingSheetReq(scope="studie"))
    assert result["counts"]["entities"] == 3 and result["runs"] == 5
    assert len(result["manifests"]) == 5
    assert {m["study_role"] for m in result["manifests"]} == {"primary", "stability"}
    merged = server.comparison_ratings_merge(server.MergeReq(
        key=result["key"], ratings=_ratings(result["key"], {})))
    assert merged["status"] == "complete"


# ---------- Studienplan ----------
import scripts.run_study as run_study  # noqa: E402


def _plan_files(tmp_path, n=6):
    rows = ["task_key;gruppe;unternehmen;website;branche;suchfeld;search_mode",
            "# Kommentar;;;;;;"]
    sheets = {}
    for i in range(1, n + 1):
        group = "gt_hub" if i <= n // 2 else "extern"
        rows.append(f"T{i};{group};Firma {i} GmbH;https://firma{i}-testdaten.de;Bau;Reststoffe {i};")
        sheets[f"T{i}"] = dict(SHEET)
    (tmp_path / "aufgaben.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (tmp_path / "fall.json").write_text(json.dumps(sheets), encoding="utf-8")
    return argparse.Namespace(tasks=str(tmp_path / "aufgaben.csv"),
                              case_sheets=str(tmp_path / "fall.json"), seed="s1",
                              out=str(tmp_path / "plan.json"),
                              models="gpt-6.1-sol,claude-sonnet-5-5", stability=2,
                              max_total_usd=3.0, modes="mixed", replicates=1)


def test_study_plan_is_balanced_frozen_and_tamper_evident(tmp_path):
    args = _plan_files(tmp_path)
    assert run_study.make_plan(args) == 0
    plan = run_study.load_plan(tmp_path / "plan.json")
    for group in ("gt_hub", "extern"):
        modes = [t["search_mode"] for t in plan["tasks"] if t["gruppe"] == group]
        assert sorted(modes) == ["pull", "push", "push"] or sorted(modes) == ["pull", "pull", "push"]
    primary = [p for p in plan["pairs"] if p["role"] == "primary"]
    assert len(primary) == 12 and len(plan["stability_task_keys"]) == 2
    for model in plan["models"]:
        orders = [tuple(p["order"]) for p in primary if p["model"] == model]
        assert orders.count(("sas2", "mas")) == 3
    assert all(MARKER not in t["search_prompt"] for t in plan["tasks"])
    assert run_study.make_plan(args) == 2  # kein Ueberschreiben
    raw = json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))
    raw["tasks"][0]["search_prompt"] += " leichter"
    (tmp_path / "plan.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        run_study.load_plan(tmp_path / "plan.json")


def test_study_run_respects_hard_cost_stop_and_resumes(tmp_path, monkeypatch):
    args = _plan_files(tmp_path)
    args.max_total_usd = 3.5  # 12.11.2026: Stopp mit 0,50 USD Sicherheitsaufschlag
    run_study.make_plan(args)
    calls = []

    class StubRunner:
        def __init__(self, live=False, memory_records=None):
            assert live is True
            self.budget = ExperimentBudget()

        def run_pair(self, task, planned_assignment=None):
            # Die zur Laufzeit gebaute Aufgabe muss exakt der eingefrorenen entsprechen.
            assert task.public_input(strict=True).input_hash() == planned_assignment["task_input_hash"]
            calls.append(planned_assignment["execution_id"])
            pair_id = planned_assignment["execution_id"].replace("exec-", "pair-", 1)
            canonical = task.public_input(strict=True).canonical_dict()
            return {"pair_id": pair_id, "task": canonical,
                    "order": planned_assignment["order"],
                    "arms": [_arm("sas2", "arm-x", [_candidate("z", "Zeta")]),
                             _arm("mas", "arm-y", [])]}

    runs_dir = tmp_path / "runs"
    monkeypatch.setenv("SCOUTREF_RUNS_DIR", str(runs_dir))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    monkeypatch.setattr(run_study, "PairedArchitectureRunner", StubRunner)
    run_args = argparse.Namespace(plan=str(tmp_path / "plan.json"), role="primary",
                                  max_total_usd=0.0, confirm_paid=True)
    assert run_study.run_phase(run_args) == 3  # Kostenstopp: 1,6 + 2,0 + 0,5 > 3,5
    assert len(calls) == 2
    plan = run_study.load_plan(tmp_path / "plan.json")
    ledger = run_study.load_ledger(run_study.ledger_path(tmp_path / "plan.json", plan))
    assert run_study.spent(ledger, plan) == pytest.approx(1.6)
    records = [json.loads(p.read_text(encoding="utf-8")) for p in runs_dir.glob("*.json")]
    assert len(records) == 2
    record = records[0]
    assert record["run_set"] == "studie" and record["study"]["role"] == "primary"
    assert MARKER in json.dumps(record["reference"])
    assert MARKER not in json.dumps(record["internal_pairs"])
    assert record["assignment_manifests"][0]["model"] == "gpt-6.1-sol"
    # Ein abgebrochenes Paar zaehlt mit Hoechstkosten.
    ledger["entries"]["x"] = {"status": "started"}
    assert run_study.spent(ledger, plan) == pytest.approx(1.6 + plan["max_pair_cost_usd"])


def test_repeated_interface_runs_with_same_pair_id_are_analyzable(tmp_path, monkeypatch):
    # Wiederholte Oberflaechenlaeufe derselben Aufgabe tragen dieselbe Paar-ID.
    monkeypatch.setattr(server, "RUNS_DIR", str(tmp_path))
    first = _record(_result("A", "pair-same", [_candidate("a1", "Alpha", "https://alpha.example")], []), "sol")
    second = _record(_result("A", "pair-same", [], [_candidate("a2", "Alpha", "https://alpha.example")]), "sol")
    for index, record in enumerate((first, second)):
        record["operator_view"]["run_id"] = f"run-{index}"
        (tmp_path / f"run-{index}.json").write_text(json.dumps(record), encoding="utf-8")
    sheet = server.comparison_rating_sheet(server.RatingSheetReq(scope="studie"))
    assert len({m["pair_id"] for m in sheet["manifests"]}) == 2
    merged = server.comparison_ratings_merge(server.MergeReq(
        key=sheet["key"], ratings=_ratings(sheet["key"], {})))
    analysis = server.comparison_analyze(server.AnalyzeReq(
        annotations=merged["final"]["annotations"], manifests=sheet["manifests"]))
    assert analysis["metrics"]["primary_itt"]["assigned_pairs"] == 2


def test_study_plan_can_be_push_only(tmp_path):
    args = _plan_files(tmp_path)
    args.modes = "push"
    assert run_study.make_plan(args) == 0
    plan = run_study.load_plan(tmp_path / "plan.json")
    assert {t["search_mode"] for t in plan["tasks"]} == {"push"}
    assert all(t["search_area"] == "" for t in plan["tasks"])
