import json

import pytest

from study_controls import (HoldoutRegistry, StudyBudgetLedger,
                            build_balanced_plan, save_frozen_plan)


def _plan(repetitions=4, memory_states=None):
    return build_balanced_plan(
        study_id="study-test-v1",
        task_rows=[{"task_id": "task-a",
                    "task_input_hash": "task-" + "a" * 40}],
        repetitions=repetitions,
        memory_states=memory_states or [False],
        allocation_seed="precommitted-seed",
    )


def test_plan_is_counterbalanced_and_reproducible_ignoring_timestamp():
    first = _plan()
    second = _plan()
    first_orders = [tuple(item["order"]) for item in first["plan"]]
    second_orders = [tuple(item["order"]) for item in second["plan"]]
    assert first_orders == second_orders
    assert first_orders.count(("sas2", "mas")) == 2
    assert first_orders.count(("mas", "sas2")) == 2
    assert first["manifest_hash"] == second["manifest_hash"]
    assert [item["replicate_index"] for item in first["plan"]] == [1, 2, 3, 4]


def test_frozen_plan_cannot_be_overwritten(tmp_path):
    path = tmp_path / "plan.json"
    plan = _plan()
    save_frozen_plan(str(path), plan)
    save_frozen_plan(str(path), plan)
    changed = dict(plan)
    changed["allocation_seed"] = "changed"
    with pytest.raises(RuntimeError):
        save_frozen_plan(str(path), changed)


def test_budget_ledger_reserves_before_spend_and_keeps_reserve_on_uncertainty(
        tmp_path):
    ledger = StudyBudgetLedger(str(tmp_path / "budget.json"), 1.0)
    ledger.reserve("run-1", 0.6)
    assert ledger.snapshot()["remaining_unreserved_usd"] == pytest.approx(0.4)
    with pytest.raises(RuntimeError):
        ledger.reserve("run-2", 0.5)
    ledger.settle("run-1", 0.2)
    assert ledger.snapshot()["spent_usd"] == pytest.approx(0.2)
    ledger.reserve("run-3", 0.5)
    ledger.settle("run-3", 0.0, uncertain=True)
    assert ledger.snapshot()["spent_usd"] == pytest.approx(0.7)


def test_holdout_registry_requires_manifest_and_allows_execution_only_once(
        tmp_path):
    manifest = _plan(repetitions=1)
    manifest_path = tmp_path / "holdout.json"
    execution_path = tmp_path / "executions.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    registry = HoldoutRegistry(str(manifest_path), str(execution_path))
    assignments = registry.assignments(
        study_id="study-test-v1",
        task_input_hash="task-" + "a" * 40,
        repetitions=1,
        memory_states=[False],
        event_time="2026-08-31T10:00:00+00:00",
    )
    registry.claim(assignments)
    with pytest.raises(RuntimeError):
        registry.claim(assignments)

