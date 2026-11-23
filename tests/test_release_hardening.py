import json

from compare_architectures import _blind_code
from experiment_protocol import (
    PublicSearchField,
    PublicSearchTaskInput,
    _public_url,
    normalise_domain_hint,
    stable_organization_id,
)
from memory import FeedbackMemory, MemoryStore
from resource_budget import ResourceBroker, ResourceLimits


def _task(split="pilot", event_time="", sources=(), domain_hint=""):
    name = "Runtime Organization"
    return PublicSearchTaskInput(
        task_id="hardening-task",
        organization_id=stable_organization_id(name, domain_hint),
        organization_name=name,
        organization_domain_hint=domain_hint,
        search_field=PublicSearchField.from_prompt(
            "Find startups for a publicly discoverable operational field."),
        public_source_package=tuple(sources),
        dataset_split=split,
        event_time=event_time,
    )


def test_blind_codes_are_random_and_not_derived_from_pair_or_architecture():
    first = _blind_code()
    second = _blind_code()
    assert first.startswith("arm-")
    assert second.startswith("arm-")
    assert first != second
    assert "sas" not in first and "mas" not in first


def test_public_url_rejects_local_private_and_reserved_test_hosts():
    assert _public_url("https://example.org/public") is True
    assert _public_url("http://127.0.0.1/internal") is False
    assert _public_url("http://192.168.1.10/internal") is False
    assert _public_url("https://organization.example/process") is False
    assert _public_url("http://localhost:8000") is False


def test_user_supplied_evidence_is_rejected_for_pilot():
    task = _task(sources=({
        "classification": "public",
        "url": "https://example.org/public-process",
    },))
    try:
        task.validate()
    except ValueError as error:
        assert "Eingabequellen" in str(error)
    else:
        raise AssertionError("Nutzerbelege duerfen keinen Live-Lauf vorstrukturieren.")


def test_holdout_accepts_no_input_source_and_optional_event_time():
    task = _task(split="holdout")
    task.validate()
    assert task.source_snapshot() == []


def test_future_event_time_is_rejected_when_supplied():
    try:
        _task(event_time="2999-01-01T12:00:00+00:00").validate()
    except ValueError as error:
        assert "Zukunft" in str(error)
    else:
        raise AssertionError("Zukuenftiger Ereigniszeitpunkt muss scheitern.")


def test_domain_hint_is_optional_but_must_be_public_when_present():
    _task().validate()
    assert normalise_domain_hint("https://runtime-industries.com/about") == (
        "runtime-industries.com")
    try:
        _task(domain_hint="localhost").validate()
    except ValueError as error:
        assert "oeffentlich erreichbare Domain" in str(error)
    else:
        raise AssertionError("Lokaler Domainhinweis muss scheitern.")


def test_generated_organization_id_is_stable_and_domain_sensitive():
    first = stable_organization_id("Runtime   Organization")
    second = stable_organization_id("runtime organization")
    with_domain = stable_organization_id(
        "Runtime Organization", "runtime-industries.com")
    assert first == second
    assert first.startswith("org-runtime-organization-")
    assert with_domain != first


def test_memory_time_filter_compares_utc_instants_not_iso_strings():
    records = [
        {
            "memory_id": "future-by-offset",
            "organization_id": "runtime-organization",
            "description": "material recovery",
            "dataset_split": "train",
            "status": "active",
            "event_time": "2026-08-29T23:00:00+00:00",
            "outcome": "useful",
        },
        {
            "memory_id": "past",
            "organization_id": "runtime-organization",
            "description": "material recovery",
            "dataset_split": "train",
            "status": "active",
            "event_time": "2026-08-29T21:00:00+00:00",
            "outcome": "useful",
        },
    ]
    memory = FeedbackMemory(MemoryStore(records=records, read_only=True))
    result = memory.retrieve(
        "runtime-organization", "material recovery",
        evaluation_context={
            "task_group_id": "other-task",
            "event_time": "2026-08-30T00:00:00+02:00",
        })
    assert [item["memory_id"] for item in result] == ["past"]


def test_unknown_model_price_blocks_resource_authorization():
    broker = ResourceBroker(ResourceLimits(
        max_input_tokens=1000,
        max_output_tokens=1000,
        max_reasoning_tokens=1000,
        max_web_calls=2,
        max_model_calls=2,
        max_resolver_fetches=2,
        max_cost_usd=10.0,
    ))
    allowed, reason = broker.authorize_model_call(
        estimated_input_tokens=10,
        max_output_tokens=10,
        max_web_calls=0,
        model="unpriced-model",
    )
    assert allowed is False
    assert reason == "unknown_model_price"
    assert broker.summary()["technical_failure"] is True


def test_public_source_schema_uses_neutral_document_prefix():
    with open("data/public/profile_sources.schema.json", encoding="utf-8") as handle:
        schema = json.load(handle)
    pattern = schema["properties"]["documents"]["items"]["properties"][
        "document_id"]["pattern"]
    assert pattern.startswith("^SRC-")
    assert "GTH" not in pattern
