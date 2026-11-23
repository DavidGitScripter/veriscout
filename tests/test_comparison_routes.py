import os

import server
from compare_architectures import ExperimentBudget
from study_controls import StudyBudgetLedger


class _Request:
    def __init__(self, token: str = ""):
        self.headers = {"X-ScoutRef-Token": token} if token else {}


def _comparison_request(**overrides):
    values = {
        "organization_name": "Runtime Organization",
        "organization_domain_hint": "runtime-industries.com",
        "search_prompt": (
            "Find startups that can improve publicly documented material "
            "recovery processes of the organization."
        ),
        "dataset_split": "pilot",
    }
    values.update(overrides)
    return server.ComparisonReq(**values)


def test_comparison_preview_is_free_without_user_supplied_evidence():
    result = server.comparison_preview(_comparison_request())
    assert result["paid_calls"] == 0
    assert result["status"] == "ready"
    assert result["readiness"]["confirmatory"] is True
    assert result["input_evidence_count"] == 0
    assert result["output_evidence_status"] == "not_run"


def test_external_organization_accepts_name_and_free_search_prompt():
    result = server.comparison_preview(_comparison_request())
    assert result["paid_calls"] == 0
    assert result["status"] == "ready"
    assert result["task"]["organization_id"].startswith("org-runtime-organization-")
    assert result["task"]["organization_domain_hint"] == "runtime-industries.com"
    assert "material recovery" in result["task"]["search_prompt"]
    assert result["task"]["public_source_package"] == []


def test_comparison_config_is_organization_neutral_and_declares_output_evidence():
    result = server.comparison_config()
    assert result["supports_external_organization"] is True
    assert result["supports_custom_field"] is True
    assert result["actors"] == []
    assert result["public_search_fields"] == []
    assert result["memory_modes"] == ["off", "frozen", "both"]
    assert result["input_contract"]["required"] == [
        "organization_name", "search_prompt"]
    assert "organization_domain_hint" in result["input_contract"]["optional"]
    assert result["evidence_policy"]["origin"] == "SAS-/MAS-Rechercheoutput"


def test_user_cannot_override_generated_organization_id():
    result = server.comparison_preview(_comparison_request(
        organization_id="manually-selected-id"))
    assert result.status_code == 400


def test_paid_comparison_requires_operator_and_server_enable_flag():
    old_live = server.LIVE_EVAL_ENABLED
    old_token = server.OPERATOR_TOKEN
    try:
        server.LIVE_EVAL_ENABLED = False
        server.OPERATOR_TOKEN = "test-operator-token"
        unauthorized = server.comparison_run(
            _comparison_request(confirm_live=True), _Request())
        assert unauthorized.status_code == 401
        disabled = server.comparison_run(
            _comparison_request(confirm_live=True),
            _Request("test-operator-token"))
        assert disabled.status_code == 403
    finally:
        server.LIVE_EVAL_ENABLED = old_live
        server.OPERATOR_TOKEN = old_token


def test_completed_route_separates_blind_package_and_manifest_without_calls(tmp_path):
    old_runner = server.PairedArchitectureRunner
    old_live = server.LIVE_EVAL_ENABLED
    old_token = server.OPERATOR_TOKEN
    old_key = os.environ.get("OPENAI_API_KEY")
    old_save = server._save_unblinding_records
    old_budget = server.STUDY_BUDGET
    old_plan_root = server.STUDY_PLAN_ROOT

    class StubRunner:
        calls = 0

        def __init__(self, live=False, memory_records=None):
            assert live is True
            self.budget = ExperimentBudget()

        def run_pair(self, task, memory_enabled=False):
            StubRunner.calls += 1
            return {
                "pair_id": "pair-test",
                "task": task.public_input(strict=True).canonical_dict(),
                "order": ["sas2", "mas"],
                "arms": [
                    {"blind_arm_id": "arm-a", "architecture_internal": "sas2",
                     "usage_totals": {}, "budget_violation": False,
                     "decisions": []},
                    {"blind_arm_id": "arm-b", "architecture_internal": "mas",
                     "usage_totals": {}, "budget_violation": False,
                     "decisions": []},
                ],
                "annotation_contract": {"blind": True},
            }

    try:
        server.PairedArchitectureRunner = StubRunner
        server.LIVE_EVAL_ENABLED = True
        server.OPERATOR_TOKEN = "test-operator-token"
        server._save_unblinding_records = lambda: None
        server.STUDY_BUDGET = StudyBudgetLedger(
            str(tmp_path / "budget.json"), 8.0)
        server.STUDY_PLAN_ROOT = str(tmp_path / "plans")
        server.RUN_CACHE.clear()
        server.UNBLINDING_RECORDS.clear()
        os.environ["OPENAI_API_KEY"] = "test-key-not-used"
        result = server.comparison_run(
            _comparison_request(
                confirm_live=True,
                idempotency_key="route-test-idempotency-0001"),
            _Request("test-operator-token"))
        assert result["status"] == "completed"
        assert result["pairs"][0]["blind_annotation"]["arms"][0].get(
            "architecture_internal") is None
        assert "unblinding_manifest" not in result
        assert result["unblinding"]["status"] == "locked"
        assert result["run_bundle_manifest"]["task_input_hash"].startswith(
            "task-")
        replay = server.comparison_run(
            _comparison_request(
                confirm_live=True,
                idempotency_key="route-test-idempotency-0001"),
            _Request("test-operator-token"))
        assert replay["run_id"] == result["run_id"]
        assert StubRunner.calls == 1
        unblinded = server.comparison_unblind(
            server.UnblindReq(
                run_id=result["run_id"],
                annotation_commitment_sha256="b" * 64,
                confirm_annotations_locked=True),
            _Request("test-operator-token"))
        assert unblinded["unblinding_manifest"][0]["assignments"][0][
            "architecture"] == "sas2"
    finally:
        server.PairedArchitectureRunner = old_runner
        server.LIVE_EVAL_ENABLED = old_live
        server.OPERATOR_TOKEN = old_token
        server._save_unblinding_records = old_save
        server.STUDY_BUDGET = old_budget
        server.STUDY_PLAN_ROOT = old_plan_root
        if old_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = old_key
