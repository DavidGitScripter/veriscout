"""Hauptlauf-Reihenfolge und Obergrenzen je Anbieter (12.11.2026)."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_study  # noqa: E402
from test_variante_a import _plan_files  # noqa: E402


def _plan(tmp_path, replicates=2, per_model="gpt-6.1-sol=28,claude-sonnet-5-5=26", total=0.0, n=6):
    args = _plan_files(tmp_path, n=n)
    args.stability, args.replicates, args.modes = 0, replicates, "push"
    args.max_total_usd, args.max_usd_per_model = total, per_model
    assert run_study.make_plan(args) == 0
    return run_study.load_plan(tmp_path / "plan.json")


def test_plan_stores_limits_per_model_and_total(tmp_path):
    plan = _plan(tmp_path)
    assert plan["max_usd_per_model"] == {"gpt-6.1-sol": 28.0, "claude-sonnet-5-5": 26.0}
    assert plan["max_total_usd"] == 54.0
    assert plan["max_pair_cost_usd"] == 2.0


def test_plan_without_any_limit_is_refused(tmp_path):
    args = _plan_files(tmp_path)
    args.stability, args.max_total_usd, args.max_usd_per_model = 0, 0.0, ""
    assert run_study.make_plan(args) == 2


def test_schedule_first_all_first_runs_interleaved_then_second_runs(tmp_path):
    plan = _plan(tmp_path, n=6)  # 6 Firmen x 2 Modelle x 2 Laeufe = 24 Paare
    order = run_study.schedule(plan)
    assert len(order) == 24 and len({p["entry_id"] for p in order}) == 24
    reps = [p["replicate_index"] for p in order]
    assert reps == [1] * 12 + [2] * 12  # erst alle ersten Laeufe
    for block in (order[:12], order[12:]):
        models = [p["model"] for p in block]
        assert all(models[i] != models[i + 1] for i in range(len(models) - 1))  # abwechselnd
        assert Counter(models) == {"gpt-6.1-sol": 6, "claude-sonnet-5-5": 6}
        assert Counter((p["task_key"], p["model"]) for p in block).most_common(1)[0][1] == 1
    assert order == run_study.schedule(plan)  # deterministisch
    # AB/BA-Wechsel je Firma und Modell bleibt erhalten
    by = {}
    for p in order:
        by.setdefault((p["task_key"], p["model"]), []).append(tuple(p["order"]))
    assert all(len(set(v)) == 2 for v in by.values())


def test_budget_check_includes_worst_case_and_margin():
    assert run_study.budget_allows_pair(23.5, 2.0, 26.0)
    assert not run_study.budget_allows_pair(23.6, 2.0, 26.0)


def test_run_all_stops_only_the_exhausted_model(tmp_path, monkeypatch, capsys):
    plan = _plan(tmp_path, n=6, per_model="gpt-6.1-sol=28,claude-sonnet-5-5=5")
    plan_path = tmp_path / "plan.json"
    ledger_file = run_study.ledger_path(plan_path, plan)
    calls = []

    def fake_call(command):
        entry = command[command.index("--only") + 1]
        calls.append(entry)
        ledger = run_study.load_ledger(ledger_file)
        ledger["entries"][entry] = {"status": "done", "cost_usd": 1.0, "attempt": 1}
        ledger_file.write_text(json.dumps(ledger), encoding="utf-8")
        return 0

    monkeypatch.setattr(run_study, "runner_call", fake_call)
    code = run_study.run_all(argparse.Namespace(plan=str(plan_path), max_total_usd=0.0, confirm_paid=True))
    assert code == 3
    owner = run_study.model_of_entry(plan)
    ran = Counter(owner[e] for e in calls)
    # Sonnet: 5 USD Grenze, je Paar 1 USD; Start nur, wenn bisher + 2,0 + 0,5 <= 5 -> 3 Paare.
    assert ran["claude-sonnet-5-5"] == 3 and ran["gpt-6.1-sol"] == 12  # Sol laeuft vollstaendig weiter
    out = capsys.readouterr().out
    assert '"status": "budget_stop"' in out and "claude-sonnet-5-5" in out


def test_run_all_without_confirmation_only_shows_order(tmp_path, monkeypatch, capsys):
    _plan(tmp_path, n=6)
    monkeypatch.setattr(run_study, "runner_call", lambda c: (_ for _ in ()).throw(AssertionError("kein Lauf")))
    assert run_study.run_all(argparse.Namespace(plan=str(tmp_path / "plan.json"), max_total_usd=0.0,
                                                confirm_paid=False)) == 0
    assert '"pairs": 24' in capsys.readouterr().out
