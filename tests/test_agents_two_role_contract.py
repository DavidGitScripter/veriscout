import json
from types import SimpleNamespace

from agents import DecisionFormatter, ScoutingAgent
from core import ActorMatch, Config, Recommendation
from experiment_protocol import (PublicSearchField, PublicSearchTaskInput,
                                 stable_organization_id)
from pipeline import Pipeline


def _match(score: int, sufficient: bool) -> ActorMatch:
    return ActorMatch(
        actor_id="organization-1", actor_name="Test Organization", score=score,
        sufficient=sufficient, critical_assessment="", rationale="",
        fit="spezifisch",
    )


def test_live_decision_uses_categorical_evidence_not_numeric_thresholds():
    formatter = DecisionFormatter()
    supported = SimpleNamespace(
        decision_state="fully_supported", evidence_coverage=1.0)
    incomplete = SimpleNamespace(
        decision_state="incomplete", evidence_coverage=0.75)
    contradictory = SimpleNamespace(
        decision_state="contradictory", evidence_coverage=0.875)
    assert formatter.run([_match(1, True)], False, supported)[0][0] == Recommendation.PILOT
    assert formatter.run([_match(100, True)], True, supported)[0][0] == Recommendation.REJECT
    assert formatter.run([_match(100, True)], False, incomplete)[0][0] == Recommendation.REJECT
    assert formatter.run([_match(100, True)], False, contradictory)[0][0] == Recommendation.REJECT


def test_scouting_contract_is_public_only_and_configuration_driven():
    prompt = ScoutingAgent.SYSTEM
    assert "VeriScout" in prompt
    assert Config.APPLICATION_NAME not in prompt
    assert "keine Belege anderer Organisationen" in prompt
    assert "genau eine Zielorganisation" in prompt
    assert "Scouting liefert ROHFUNDE" in prompt
    assert "Discovery liefert" not in prompt


def test_strict_json_contract_does_not_rescue_truncated_objects():
    try:
        ScoutingAgent._strict_array('[{"name":"abgeschnitten"}')
    except (json.JSONDecodeError, ValueError):
        pass
    else:
        raise AssertionError("Ein abgeschnittener Modellvertrag muss scheitern.")


def test_free_search_prompt_does_not_enter_evidence_manifest():
    name = "Demo Manufacturing"
    organization_id = stable_organization_id(name)
    task = PublicSearchTaskInput(
        task_id="prompt-only-test",
        organization_id=organization_id,
        organization_name=name,
        search_field=PublicSearchField.from_prompt(
            "Find startups for a publicly discoverable process."),
        dataset_split="pilot",
    )
    pipeline = Pipeline(live=False, audit_write=False)
    pipeline.discover("", n=0, architecture="mas", task_input=task)
    sources = pipeline.last_opportunity_plan["public_sources"]
    assert sources == []

    # Die Suchfeldquelle bleibt Kontext und wird nicht in einen konkreten
    # Prozessbeleg umgedeutet.
    from core import Candidate
    candidate = Candidate(
        name="Offline Candidate", description="Test", discovery_mode="synthetic",
        target_actor_id=organization_id,
    )
    matrix = pipeline.matrix_builder.build(candidate, target_sources=sources)
    assert not any(item["field"] == "public_search_field"
                   for item in matrix.claim_manifest)
    assert matrix.cell("target_process").status.value == "missing"


def test_task_sources_from_another_organization_fail_closed_in_pipeline():
    packet = {
        "organization_id": "demo_manufacturing",
        "organization_name": "Demo Manufacturing",
        "organization_public_url": "https://example.org/demo-manufacturing/about",
        "shared_prompt": "Identischer oeffentlicher Auftrag",
        "search_field": {
            "theme_id": "field-1", "title": "Feld", "description": "Beschreibung",
            "source": {
                "classification": "public",
                "url": "https://example.org/demo-manufacturing/field",
                "excerpt": "Ein ausreichend langer oeffentlicher Belegauszug.",
                "retrieved_at": "2026-08-24",
            },
        },
        "public_source_package": [{
            "organization_id": "other_organization", "classification": "public",
            "url": "https://example.net/other/source",
        }],
    }
    try:
        Pipeline(live=False, audit_write=False).discover(
            "", n=0, architecture="mas", task_input=packet)
    except ValueError as error:
        assert "anderen Organisation" in str(error)
    else:
        raise AssertionError("Fremde Organisationsquelle muss blockiert werden.")
