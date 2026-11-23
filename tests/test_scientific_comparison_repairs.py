import json

from agents import ScoutingAgent, VerificationAgent
from compare_architectures import (ComparisonTask, ExperimentBudget,
                                   PairedArchitectureRunner,
                                   annotation_package)
from core import Candidate, Source
from evidence_matrix import EvidenceMatrixBuilder, EvidenceStatus
from experiment_protocol import (PublicSearchField, PublicSearchTaskInput,
                                 stable_organization_id)
from knowledge_base import KnowledgeBase
from memory import FeedbackMemory, MemoryStore
from resource_budget import ResourceBroker, ResourceLimits
from entity_verifier import EntityVerifier, is_independent_source


def ready_field():
    return {
        "theme_id": "p-test",
        "title": "Oeffentliches Testfeld",
        "description": "Ein oeffentlich sichtbares Suchfeld der Organisation.",
        "source": {
            "classification": "public",
            "url": "https://example.org/demo-manufacturing/public-field",
            "excerpt": "Die Organisation beschreibt dieses Suchfeld oeffentlich auf ihrer Website.",
            "retrieved_at": "2026-08-24",
            "review_status": "verified",
            "reviewer_id": "reviewer-test",
            "reviewed_at": "2026-08-24T10:00:00+00:00",
            "archived_content_sha256": "a" * 64,
        },
    }


def ready_task():
    name = "Demo Manufacturing"
    return ComparisonTask(
        task_id="public-only-test",
        organization_id=stable_organization_id(name),
        organization_name=name,
        search_prompt=(
            "Find startups that improve a publicly discoverable process of "
            "the target organization."),
        task_group_id="public-only-test",
        dataset_split="test",
    )


def test_public_only_prompt_and_total_budget_are_identical_for_sas2_and_mas():
    budget = ExperimentBudget(max_output_tokens=1200, max_tool_calls=4)
    result = PairedArchitectureRunner(budget=budget, live=False).run_pair(ready_task())
    assert {arm["architecture_internal"] for arm in result["arms"]} == {"sas2", "mas"}
    assert len({arm["prompt_hash"] for arm in result["arms"]}) == 1
    assert len({arm["task_input_hash"] for arm in result["arms"]}) == 1
    assert all(arm["budget"] == result["arms"][0]["budget"]
               for arm in result["arms"])
    assert result["primary_contrast"] == "sas2_self_review_vs_mas"


def test_experiment_reasoning_level_controls_the_actual_client_default():
    budget = ExperimentBudget(reasoning_effort="medium")
    runner = PairedArchitectureRunner(budget=budget, live=False)
    broker = ResourceBroker(budget.resource_limits())
    pipeline = runner._pipeline(broker)
    assert pipeline.llm.reasoning_effort == "medium"


def test_confirmatory_task_requires_prompt_but_not_input_source():
    name = "Demo Manufacturing"
    task = PublicSearchTaskInput(
        task_id="ready-without-input-evidence",
        organization_id=stable_organization_id(name),
        organization_name=name,
        search_field=PublicSearchField.from_prompt("Beschreibung"),
        strict_public_only=True)
    task.validate()
    assert task.source_snapshot() == []

    invalid = PublicSearchTaskInput(
        task_id="not-ready", organization_id=stable_organization_id(name),
        organization_name=name,
        search_field=PublicSearchField(
            theme_id="prompt-empty", title="Freier Suchauftrag", description=""),
        strict_public_only=True)
    try:
        invalid.validate()
    except ValueError as error:
        assert "description" in str(error) or "search_prompt" in str(error)
    else:
        raise AssertionError("Leerer Suchprompt darf keinen Live-Lauf starten.")


def test_public_package_rejects_user_supplied_input_evidence():
    name = "Demo Manufacturing"
    organization_id = stable_organization_id(name)
    task = PublicSearchTaskInput(
        task_id="input-evidence", organization_id=organization_id,
        organization_name=name,
        search_field=PublicSearchField.from_prompt("Find suitable startups."),
        public_source_package=({
            "organization_id": "other_organization", "classification": "public",
            "url": "https://example.org/other-organization",
        },),
    )
    try:
        task.validate()
    except ValueError as error:
        assert "Eingabequellen" in str(error)
    else:
        raise AssertionError("Eingabequellen muessen im Live-Vertrag blockiert werden.")


def test_claim_manifest_preserves_contradiction_and_blocks_relation():
    candidate = Candidate(
        name="Contradicted Startup", description="Verwertet Reststoffe",
        founded=2025, company_type="startup", discovery_mode="manual",
        official_url="https://startup.example", target_actor_id="demo_manufacturing",
        process_stage="Oeffentlicher Prozess", input_stream="Reststoff",
        transformation="Aufbereitung", output_application="Baustoff",
        sources=[Source(
            url="https://example.org/startup/evidence",
            excerpt="Die Quelle enthaelt eine konkrete und ausreichend lange Aussage.",
            supports=["identity", "founded", "product", "input_stream",
                      "transformation", "output_application"],
        )],
        evidence_claims=[{
            "claim_id": "claim-contradiction",
            "claim_text": "Das Startup verarbeitet diesen Inputstrom nicht.",
            "field": "input_stream",
            "source_url": "https://example.org/startup/evidence",
            "excerpt": "Die Quelle widerspricht der behaupteten Verarbeitung ausdruecklich.",
            "stance": "contradict",
        }],
    )
    matrix = EvidenceMatrixBuilder().build(candidate, [{
        "document_id": "organization-1", "url": "https://example.net/organization/process",
        "evidence": [{"field": "target_process",
                      "excerpt": "Der Prozess ist auf der Organisationswebsite oeffentlich beschrieben."}],
    }])
    assert matrix.cell("input_stream").status == EvidenceStatus.CONTRADICTED
    assert "input_stream" in matrix.contradictions
    assert matrix.decision_state == "contradictory"
    assert any(item["claim_id"] == "claim-contradiction"
               for item in matrix.claim_manifest)


def test_hard_candidate_cap_applies_to_offline_scouting():
    candidates = [Candidate(name=f"Candidate {index}", description="Testfeld")
                  for index in range(8)]
    hits, _ = ScoutingAgent(KnowledgeBase(), llm=None).run(
        "Testfeld", n=3, seed_pool=candidates)
    assert len(hits) == 3


def test_resource_broker_counts_all_dimensions_and_fails_closed():
    broker = ResourceBroker(ResourceLimits(
        max_input_tokens=100, max_output_tokens=50,
        max_reasoning_tokens=10, max_web_calls=2, max_model_calls=1,
        max_resolver_fetches=1, max_cost_usd=1.0))
    allowed, _ = broker.authorize_model_call(
        estimated_input_tokens=20, max_output_tokens=50, max_web_calls=2)
    assert allowed
    broker.record_model_usage({
        "status": "completed", "model_requested": "gpt-5.6-terra",
        "model_returned": "gpt-5.6-terra", "input_tokens": 40,
        "cached_input_tokens": 5, "output_tokens": 20,
        "reasoning_tokens": 4, "tool_calls": 2,
    }, latency_ms=10)
    assert broker.begin_resolver_fetch()[0] is True
    assert broker.begin_resolver_fetch()[0] is False
    summary = broker.summary()
    assert summary["model_calls"] == 1
    assert summary["web_calls"] == 2
    assert summary["resolver_fetches"] == 1
    assert summary["technical_failure"] is False
    assert summary["resolver_budget_exhausted"] is True


def test_resource_broker_blocks_a_call_whose_declared_maximum_exceeds_cost_cap():
    broker = ResourceBroker(ResourceLimits(
        max_input_tokens=10_000, max_output_tokens=10_000,
        max_reasoning_tokens=10_000, max_web_calls=10, max_model_calls=2,
        max_resolver_fetches=2, max_cost_usd=0.01))
    allowed, reason = broker.authorize_model_call(
        estimated_input_tokens=100, max_output_tokens=1_000,
        max_web_calls=0, model="gpt-5.6-terra")
    assert allowed is False
    assert reason == "projected_cost_budget_exhausted"


def test_syndicated_copy_is_not_counted_as_independent_evidence():
    official = Source(
        url="https://example.org/startup/about", source_type="official",
        publisher="Startup GmbH", supports=["identity", "product"],
        resolved_status="resolved", excerpt_verified=True,
        text_hash="same-normalised-body", excerpt_hash="same-excerpt")
    mirror = Source(
        url="https://example.net/news/press-release", source_type="press",
        publisher="News Portal", supports=["identity", "founded"],
        resolved_status="resolved", excerpt_verified=True,
        text_hash="same-normalised-body", excerpt_hash="same-excerpt")
    assert is_independent_source(official, mirror) is False
    candidate = Candidate(
        name="Copied Release Startup", founded=2025,
        company_type="startup", discovery_mode="manual",
        website="https://startup.example", sources=[official, mirror])
    result = EntityVerifier().verify(candidate)
    assert result.status == "needs_evidence"
    assert result.independent_source_url == ""


def test_distinct_source_family_and_content_can_corrobate_identity():
    official = Source(
        url="https://example.org/startup/about", source_type="official",
        publisher="Startup GmbH", supports=["identity", "product"],
        text_hash="official-body", excerpt_hash="official-excerpt")
    register = Source(
        url="https://example.net/register/company/1", source_type="register",
        publisher="Public Register", supports=["identity", "founded"],
        text_hash="register-body", excerpt_hash="register-excerpt")
    assert is_independent_source(official, register) is True


def test_memory_evaluation_uses_train_only_and_excludes_same_task():
    memory = FeedbackMemory(MemoryStore(records=[
        {"actor_id": "demo_manufacturing", "description": "Oeffentliches Testfeld",
         "dataset_split": "train", "task_group_id": "other-task",
         "event_time": "2026-01-01", "outcome": "useful"},
        {"actor_id": "demo_manufacturing", "description": "Oeffentliches Testfeld",
         "dataset_split": "train", "task_group_id": "current-task",
         "event_time": "2026-01-01", "outcome": "useful"},
        {"actor_id": "demo_manufacturing", "description": "Oeffentliches Testfeld",
         "dataset_split": "test", "task_group_id": "other-test",
         "event_time": "2026-01-01", "outcome": "useful"},
    ], read_only=True))
    context = memory.context(
        "demo_manufacturing", "Oeffentliches Testfeld",
        evaluation_context={"task_group_id": "current-task",
                            "event_time": "2026-08-24"})
    assert [item["task_group_id"] for item in context["retrieved"]] == ["other-task"]
    assert context["train_only"] is True


def test_verifier_handoff_uses_candidate_id_claims_and_no_scout_rationale():
    class StubLLM:
        requested_live = True

        def __init__(self):
            self.last_usage = {}
            self.user = ""
            self.last_citations = []

        def available(self):
            return True

        def complete(self, **kwargs):
            self.user = kwargs["user"]
            payload = json.loads(self.user.split("Zu pruefende Rohfunde:\n", 1)[1])
            candidate_id = payload[0]["candidate_id"]
            self.last_usage = {"status": "completed"}
            return json.dumps([{
                "candidate_id": candidate_id, "name": "Stable Candidate",
                "exists": False, "entity_type": "unknown", "sources": [],
                "claims": [],
            }])

        def cost_estimate(self):
            return {}

        def ground_sources(self, sources):
            return sources

    llm = StubLLM()
    candidate = Candidate(
        name="Stable Candidate", description="Scout-Rationale-Geheimtext",
        website="https://stable.example", discovery_mode="live",
        evidence_claims=[{
            "claim_text": "Oeffentliche Faehigkeit", "field": "startup_capability",
            "source_id": "src-1", "excerpt": "Ein ausreichend langer Belegauszug.",
            "stance": "support",
        }])
    VerificationAgent(llm=llm).run([candidate], "IDENTISCHER AUFTRAG")
    handoff = json.loads(llm.user.split("Zu pruefende Rohfunde:\n", 1)[1])[0]
    assert handoff["candidate_id"].startswith("cand-")
    assert "claims_to_verify" in handoff
    assert "Scout-Rationale-Geheimtext" not in llm.user
    assert "memory" not in llm.user.casefold()


def test_blind_package_removes_scores_recommendations_and_system_status():
    result = {
        "pair_id": "pair-1",
        "task": {"task_id": "task-1", "organization_id": "demo_manufacturing",
                 "search_field": ready_field()},
        "annotation_contract": {"blind": True},
        "arms": [{
            "blind_arm_id": "arm-x",
            "decisions": [{
                "best_score": 99, "recommendation": "Pilot",
                "abstained": False, "operationally_eligible": True,
                "candidate": {
                    "name": "Blind Startup", "verification_status": "verified_startup",
                    "problem_fit": True,
                    "sources": [{"url": "https://blind.example",
                                 "supports": ["identity"], "excerpt": "Beleg"}],
                    "evidence_matrix": {"decision_state": "eligible",
                                        "evidence_coverage": 1.0,
                                        "claim_manifest": [{
                                            "claim_id": "c1", "claim_text": "Aussage",
                                            "field": "identity", "source_id": "s1",
                                            "excerpt": "Beleg", "stance": "support"}]},
                },
            }],
        }],
    }
    blind = annotation_package(result)
    encoded = json.dumps(blind)
    for forbidden in ("best_score", "recommendation", "abstained",
                      "operationally_eligible", "verification_status",
                      "decision_state", "evidence_coverage", "stance"):
        assert forbidden not in encoded
