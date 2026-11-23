import json

from compare_architectures import ComparisonTask, PairedArchitectureRunner
from core import Candidate, Config
from experiment_protocol import (PublicSearchField, PublicSearchTaskInput,
                                 stable_organization_id)
from knowledge_base import KnowledgeBase
from pipeline import Pipeline


def _field(field_id: str = "field-runtime") -> dict:
    return {
        "field_id": field_id,
        "title": "Public material recovery",
        "description": (
            "A publicly documented material-recovery field of the organization."
        ),
        "source": {
            "classification": "public",
            "url": "https://example.org/runtime/process",
            "excerpt": (
                "The organization publicly documents material recovery in its "
                "production process."
            ),
            "retrieved_at": "2026-08-29",
            "review_status": "verified",
            "reviewer_id": "reviewer-test",
            "reviewed_at": "2026-08-29T10:00:00+00:00",
        },
    }


def _task(organization_name: str = "Runtime Organization") -> PublicSearchTaskInput:
    organization_id = stable_organization_id(organization_name)
    return PublicSearchTaskInput(
        task_id=f"task-{organization_id}",
        organization_id=organization_id,
        organization_name=organization_name,
        search_field=PublicSearchField.from_prompt(
            "Find startups for public material-recovery processes."),
        public_source_package=(),
        dataset_split="pilot",
    )


def test_task_organization_is_ephemeral_and_overrides_id_collisions():
    kb = KnowledgeBase()
    stored = dict(kb.get("demo_manufacturing"))

    kb.bind_task_organization(
        "demo_manufacturing", "Runtime Name",
        public_url="https://example.org/runtime/about",
        search_field=_field(),
    )

    active = kb.get("demo_manufacturing")
    assert active["name"] == "Runtime Name"
    assert active["scope"] == "task_local"
    assert active["sectors"] == []
    assert "Industry & Manufacturing" not in active.get("scouting_triggers", [])

    kb.clear_task_organization()
    assert kb.get("demo_manufacturing") == stored


def test_pipeline_uses_external_organization_from_canonical_contract():
    task = _task()
    assert task.organization_id not in KnowledgeBase().all_ids()

    pipeline = Pipeline(live=False, audit_write=False)
    seed = Candidate(
        name="Synthetic Runtime Candidate",
        description="Material recovery technology",
        discovery_mode="synthetic",
        verification_status="synthetic_case",
        problem_fit=True,
    )
    candidates, trace = pipeline.discover(
        "", n=1, seed_pool=[seed], architecture="sas2", task_input=task)

    assert candidates[0].target_actor_id == task.organization_id
    assert pipeline.kb.get(task.organization_id)["name"] == "Runtime Organization"
    plan = pipeline.last_opportunity_plan
    assert plan["target_organization_id"] == task.organization_id
    assert plan["organization_domain_hint"] == ""
    assert plan["public_search_fields"] == [task.canonical_dict()["search_field"]]
    assert plan["public_sources"] == []
    assert trace["output"]["opportunity_plan"] == plan

    decision = pipeline.scout(
        candidates[0], use_memory=False,
        target_actor_id=task.organization_id)
    assert [match.actor_id for match in decision.matches] == [
        task.organization_id]
    assert decision.matches[0].actor_name == "Runtime Organization"


def test_next_task_replaces_previous_runtime_organization():
    pipeline = Pipeline(live=False, audit_write=False)
    first = _task("One")
    second = _task("Two")
    pipeline.discover("", n=0, architecture="sas2", task_input=first)
    assert pipeline.kb.get(first.organization_id)["name"] == "One"

    pipeline.discover("", n=0, architecture="sas2", task_input=second)
    assert pipeline.kb.get(second.organization_id)["name"] == "Two"
    try:
        pipeline.kb.get(first.organization_id)
    except KeyError:
        pass
    else:
        raise AssertionError("Ein Laufzeitprofil darf nicht in den Folgeauftrag gelangen.")


def test_paired_arms_receive_same_external_task_without_persistence():
    with open(Config.ACTORS_PATH, encoding="utf-8") as handle:
        before = json.load(handle)

    public_task = _task()
    comparison_task = ComparisonTask(
        task_id=public_task.task_id,
        organization_id=public_task.organization_id,
        organization_name=public_task.organization_name,
        search_prompt=public_task.search_field.description,
        dataset_split=public_task.dataset_split,
        event_time=public_task.event_time,
    )
    result = PairedArchitectureRunner(live=False).run_pair(comparison_task)

    assert {arm["architecture_internal"] for arm in result["arms"]} == {
        "sas2", "mas"}
    assert len({arm["task_input_hash"] for arm in result["arms"]}) == 1
    assert len({arm["prompt_hash"] for arm in result["arms"]}) == 1
    assert all(not arm["technical_failure"] for arm in result["arms"])
    assert all(
        arm["discovery_trace"]["output"]["opportunity_plan"][
            "target_organization_id"] == public_task.organization_id
        for arm in result["arms"]
    )

    with open(Config.ACTORS_PATH, encoding="utf-8") as handle:
        after = json.load(handle)
    assert after == before
    assert all(actor["id"] != public_task.organization_id for actor in after["actors"])


def test_foreign_organization_source_fails_closed():
    packet = _task().canonical_dict()
    packet["public_source_package"] = [{
        "organization_id": "another_organization",
        "classification": "public",
        "url": "https://example.net/other/source",
    }]
    try:
        Pipeline(live=False, audit_write=False).discover(
            "", n=0, architecture="mas", task_input=packet)
    except ValueError as error:
        assert "anderen Organisation" in str(error)
    else:
        raise AssertionError("Fremde Organisationsquellen muessen blockiert werden.")
