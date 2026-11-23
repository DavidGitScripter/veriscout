from core import Candidate, Recommendation, Source
from agents import VerificationAgent
from evaluate import run_ablation
from pipeline import Pipeline


def test_missing_verifier_values_clear_live_discovery_claims_fail_closed():
    candidate = Candidate(
        name="Discovery Claim GmbH", description="Behauptete Loesung",
        founded=2025, employees=12, company_type="startup", region="DE",
        website="https://discovery-claim.de", official_url="https://discovery-claim.de",
        problem_fit=True, process_stage="Produktion", input_stream="Reststoff",
        transformation="Aufbereitung", output_application="Baustoff",
        discovery_mode="live",
        sources=[Source(url="https://discovery-claim.de")],
    )
    VerificationAgent()._merge(candidate, {
        "name": candidate.name, "exists": True, "entity_type": "unknown",
        "official_url": "", "founded": None, "employees": None,
        "problem_fit": None, "sources": [],
    })
    assert candidate.founded is None
    assert candidate.website == ""
    assert candidate.problem_fit is None
    assert candidate.process_stage == ""
    assert candidate.sources == []


def test_observe_can_never_create_crm_entry_or_outreach_draft():
    pipeline = Pipeline(live=False)
    candidate = Candidate(
        name="Synthetic Observation", description="Automatisierung Produktion",
        discovery_mode="synthetic", verification_status="synthetic_case",
        target_actor_id="demo_manufacturing",
    )
    decision = pipeline.scout(candidate, use_memory=False, target_actor_id="demo_manufacturing")
    decision.recommendation = Recommendation.OBSERVE
    decision.abstained = True
    decision.operationally_eligible = False
    crm = pipeline.qualify(decision, human_approved=True)
    outreach = pipeline.draft_outreach(decision, {})
    assert crm["status"] == "kein_eintrag"
    assert outreach["status"] == "kein_entwurf"


def test_no_probability_is_reported_without_calibration_artifact():
    pipeline = Pipeline(live=False)
    candidate = Candidate(
        name="Synthetic Calibration", description="Robotik Sensorik Produktion",
        discovery_mode="synthetic", verification_status="synthetic_case",
        target_actor_id="demo_manufacturing", problem_fit=True,
    )
    decision = pipeline.scout(candidate, use_memory=False, target_actor_id="demo_manufacturing")
    assert decision.confidence == 0.0
    assert decision.confidence_is_calibrated is False
    gate = next(item for item in decision.quality_gates
                if item["gate_id"] == "QG5_NO_UNCALIBRATED_CONFIDENCE")
    assert gate["passed"] is True


def test_legacy_synthetic_corpus_fails_closed_under_new_evidence_contract():
    result = run_ablation(Pipeline(live=False))
    for condition in ("mit_guardrail", "ohne_guardrail"):
        metrics = result[condition]
        assert metrics["n"] == 10
        assert metrics["tp"] == 0
        assert metrics["fp"] == 0
        assert metrics["fn"] == 5
        assert metrics["tn"] == 5
