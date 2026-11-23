import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from agents import PolicyGate, RelationEvaluationService
from core import Candidate, Config, LLMClient, Source
from evidence_matrix import EvidenceMatrixBuilder
from evidence_resolver import EvidenceResolver
from evaluation_analysis import paired_metrics
from knowledge_base import KnowledgeBase
from resource_budget import ResourceBroker, ResourceLimits
from study_controls import (HoldoutRegistry, StudyBudgetLedger,
                            build_balanced_plan)


class RecordingResolver(EvidenceResolver):
    def __init__(self):
        super().__init__()
        self.seen = []

    def resolve_source(self, source):
        self.seen.append(source.source_id)
        source.resolved_status = "resolved"
        source.resolved_url = source.url
        source.excerpt_verified = True
        return source


def _candidate(name, prefix):
    return Candidate(
        name=name,
        sources=[Source(
            source_id=f"{prefix}-{index}",
            url=f"https://{prefix}.example.org/{index}",
            excerpt="Ein ausreichend langer und konkreter Belegauszug.",
            citation_verified=True,
        ) for index in (1, 2)],
    )


def test_shared_resolver_uses_candidate_round_robin_and_marks_remainder():
    candidates = [_candidate("A", "a"), _candidate("B", "b")]
    resolver = RecordingResolver()
    result = resolver.resolve_candidates(candidates, max_fetches_total=3)
    assert resolver.seen == ["a-1", "b-1", "a-2"]
    assert candidates[1].sources[1].resolved_status == "not_checked_budget"
    assert result["not_checked_budget"] == 1
    assert result["technical_errors"] == 0
    # Der gleiche gemeinsame Algorithmus liefert fuer beide Architekturpfade
    # dieselbe Rang-/Quellenallokation.
    second = RecordingResolver()
    second.resolve_candidates(deepcopy([_candidate("A", "a"),
                                        _candidate("B", "b")]),
                              max_fetches_total=3)
    assert second.seen == resolver.seen


def test_threshold_61_is_necessary_but_incomplete_matrix_still_blocks():
    kb = KnowledgeBase()
    service = RelationEvaluationService(kb)
    gate = PolicyGate(kb)
    candidate = Candidate(
        name="Threshold Startup", discovery_mode="live",
        verification_status="verified_startup",
        company_type="startup", target_actor_id="demo_manufacturing")
    retrieved = [("demo_manufacturing", 0, [])]

    below = SimpleNamespace(
        decision_state="fully_supported", evidence_coverage=0.60,
        contradictions=[], blocking_dimensions=[])
    matches, _ = service.run(candidate, retrieved, "demo_manufacturing", below)
    assert matches[0].score == 60
    assert gate.run(candidate, matches, evidence_matrix=below)[0][0] is True

    at_cutoff = SimpleNamespace(
        decision_state="fully_supported", evidence_coverage=0.61,
        contradictions=[], blocking_dimensions=[])
    matches, _ = service.run(
        candidate, retrieved, "demo_manufacturing", at_cutoff)
    assert matches[0].score == Config.THRESHOLD_SUFFICIENT
    assert gate.run(candidate, matches, evidence_matrix=at_cutoff)[0][0] is False

    incomplete = SimpleNamespace(
        decision_state="incomplete", evidence_coverage=0.99,
        contradictions=[], blocking_dimensions=["relational_chain"])
    matches, _ = service.run(candidate, retrieved, "demo_manufacturing", incomplete)
    assert matches[0].score == 99
    assert gate.run(candidate, matches, evidence_matrix=incomplete)[0][0] is True


def test_two_startup_sources_cannot_spoof_target_side_of_relation():
    startup_name = "Wrong Subject GmbH"
    candidate = Candidate(
        name=startup_name, description="Verarbeitet Reststoffe", founded=2025,
        company_type="startup", discovery_mode="live",
        official_url="https://wrong-subject.example.org",
        target_actor_id="target-org", process_stage="Zielprozess",
        input_stream="Zielreststoff", transformation="Aufbereitung",
        output_application="Baustoff",
        sources=[Source(
            url=f"https://wrong-subject.example.org/{index}",
            source_type="official" if index == 1 else "register",
            supports=["identity", "product", "founded", "target_identity",
                      "target_process", "input_stream", "transformation",
                      "output_application"],
            excerpt="Die Startup-Quelle behauptet alle Felder der Beziehung.",
            subject_type="candidate_startup", subject_name=startup_name,
            citation_verified=True, resolved_status="resolved",
            excerpt_verified=True,
        ) for index in (1, 2)],
    )
    matrix = EvidenceMatrixBuilder().build(candidate, target_sources=[])
    assert matrix.cell("target_identity").status.value == "missing"
    assert matrix.cell("target_process").status.value != "supported"
    assert matrix.decision_state == "incomplete"


def _manifest(tmp_path, *, repetitions=2, memory_states=None):
    manifest = build_balanced_plan(
        study_id="holdout-study-v1",
        task_rows=[{"task_id": "task-a", "task_input_hash": "task-hash-a"}],
        repetitions=repetitions,
        memory_states=memory_states or [False],
        allocation_seed="frozen-seed",
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest, path


def test_holdout_rejects_tampered_manifest_and_selective_subset(tmp_path):
    manifest, path = _manifest(tmp_path, repetitions=2)
    registry = HoldoutRegistry(str(path), str(tmp_path / "executions.json"))
    with pytest.raises(ValueError, match="Teilmenge"):
        registry.assignments(
            study_id="holdout-study-v1", task_input_hash="task-hash-a",
            repetitions=1, memory_states=[False],
            event_time="2026-08-31T10:00:00+00:00")

    manifest["plan"][0]["order"] = ["mas", "mas"]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="veraendert"):
        registry.assignments(
            study_id="holdout-study-v1", task_input_hash="task-hash-a",
            repetitions=2, memory_states=[False],
            event_time="2026-08-31T10:00:00+00:00")


def test_budget_ledger_blocks_settled_reuse_and_records_real_overrun(tmp_path):
    ledger = StudyBudgetLedger(str(tmp_path / "budget.json"), 1.0)
    ledger.reserve("run-1", 0.2)
    result = ledger.settle("run-1", 0.35)
    assert result["charged_to_local_cap_usd"] == pytest.approx(0.35)
    assert result["reservation_overrun_usd"] == pytest.approx(0.15)
    assert ledger.snapshot()["spent_usd"] == pytest.approx(0.35)
    with pytest.raises(RuntimeError, match="Abgeschlossene"):
        ledger.reserve("run-1", 0.2)


def test_budget_ledger_rejects_changed_limit(tmp_path):
    path = tmp_path / "budget.json"
    StudyBudgetLedger(str(path), 1.0).reserve("run-1", 0.1)
    with pytest.raises(RuntimeError, match="stimmt nicht"):
        StudyBudgetLedger(str(path), 0.5).snapshot()


def _assignment(arm_id, architecture, status, eligible, candidate_ids=None):
    candidate_ids = list(candidate_ids or [])
    return {
        "blind_arm_id": arm_id, "architecture": architecture,
        "expected_candidate_ids": candidate_ids,
        "returned_candidates": len(candidate_ids),
        "result_status": status, "primary_analysis_eligible": eligible,
        "primary_exclusion_reason": "test" if not eligible else "",
    }


def test_valid_empty_arm_is_zero_but_technical_pair_is_excluded():
    manifests = [{
        "schema_version": "venture-scout-assignment-v2",
        "pair_id": "pair-valid", "task_id": "task-a",
        "assignments": [
            _assignment("a", "sas2", "abstention", True),
            _assignment("b", "mas", "abstention", True),
        ],
    }, {
        "schema_version": "venture-scout-assignment-v2",
        "pair_id": "pair-error", "task_id": "task-a",
        "assignments": [
            _assignment("c", "sas2", "technical_error", False),
            _assignment("d", "mas", "completed", True),
        ],
    }]
    result = paired_metrics([], manifests)
    assert result["paired_runs"] == 1
    assert result["excluded_pair_count"] == 1
    assert len(result["arm_metrics"]) == 2
    assert all(item["qualified_hit_at_5"] == 0
               for item in result["arm_metrics"])


def test_missing_annotation_cannot_masquerade_as_valid_empty_arm():
    manifests = [{
        "schema_version": "venture-scout-assignment-v2",
        "pair_id": "pair-missing", "task_id": "task-a",
        "assignments": [
            _assignment("a", "sas2", "completed", True, ["candidate-1"]),
            _assignment("b", "mas", "abstention", True),
        ],
    }]
    with pytest.raises(ValueError, match="Kandidatenmenge"):
        paired_metrics([], manifests)


def test_blocked_call_still_records_prompt_model_and_api_hashes():
    broker = ResourceBroker(ResourceLimits(
        max_input_tokens=0, max_output_tokens=10,
        max_reasoning_tokens=10, max_web_calls=0, max_model_calls=0,
        max_resolver_fetches=0, max_cost_usd=0.0))
    client = LLMClient(live=False, resource_broker=broker)
    # Aktivierung nur bis zum lokalen Preflight; der Broker blockiert sicher vor
    # jedem Netzwerkzugriff.
    client.live = True
    client.api_key = "not-used"
    assert client.complete(
        model=Config.MODEL, system="system", user="user",
        max_tokens=10, max_tool_calls=0, purpose="hash-test") == ""
    record = client.last_usage
    assert record["status"] == "technical_failure"
    assert record["system_prompt_sha256"].startswith("sha256-")
    assert record["user_prompt_sha256"].startswith("sha256-")
    assert record["request_payload_sha256"].startswith("sha256-")
    assert record["api_contract"] == Config.API_CONTRACT
    assert record["model_requested"] == Config.MODEL
