from core import Candidate, Recommendation
from pipeline import Pipeline


def test_crm_dry_run_replay_is_idempotent_and_has_no_placeholder_person():
    pipeline = Pipeline(live=False)
    candidate = Candidate(
        name="Verified Mineral Startup",
        description="Automatisierung und Verwertung mineralischer Reststoffe",
        founded=2025,
        company_type="startup",
        discovery_mode="synthetic",
        verification_status="synthetic_case",
        problem_fit=True,
        sectors=["Circular Economy"],
        target_actor_id="demo_manufacturing",
        run_id="scoutref-test-run-001",
        ceo="",
    )
    decision = pipeline.scout(
        candidate, use_memory=False, target_actor_id="demo_manufacturing")
    # Dieser Test prueft ausschliesslich CRM-Idempotenz. Die fachliche
    # Berechtigung wird in separaten Evidenztests geprueft.
    decision.recommendation = Recommendation.PILOT
    decision.abstained = False
    decision.operationally_eligible = True

    first = pipeline.qualify(decision, human_approved=True)
    second = pipeline.qualify(decision, human_approved=True)

    assert first["status"] == "angelegt"
    assert second["status"] == "aktualisiert"
    assert first["org_id"] == second["org_id"]
    assert first["deal_id"] == second["deal_id"]
    assert first["person_id"] is None
    assert not pipeline.adapter.persons
    assert first["deal_felder"]["ScoutRef Lauf-ID"] == "scoutref-test-run-001"
    assert first["deal_felder"]["Zielorganisation"] == first["target_organization"]["id"]
    assert first["deal_felder"]["Freigegeben von"] == 1
    assert first["operationen"] == {
        "organisation": "created", "person": "none", "deal": "created"
    }
    assert second["operationen"] == {
        "organisation": "updated", "person": "none", "deal": "updated"
    }
