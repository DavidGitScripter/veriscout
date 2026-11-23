import asyncio
from copy import deepcopy
import json

import pytest
from starlette.requests import Request

import reuse
import server
from scripts.start_transfer_review import transfer_environment


def workspace(**changes):
    values = {"schema_version": reuse.SCHEMA_VERSION, "name": "Transferfall A",
              "organization_name": "Neutrales Testunternehmen",
              "search_prompt": "Finde reale Startups für einen öffentlich erkennbaren Prozess zur Wiederverwendung von Reststoffen.",
              "event_time": "2026-09-01T09:15:31.250+00:00"}
    values.update(changes)
    return values


def test_project_roundtrip_preserves_full_task_hash_and_time():
    first = server.validate_workspace_payload(workspace())
    second = server.validate_workspace_payload(json.loads(json.dumps(first["receipt"])))
    assert first == second
    assert first["task"]["public_source_package"] == []
    assert first["paid_calls"] == 0
    assert first["live_started"] is False


def test_project_name_is_not_model_input():
    first = server.validate_workspace_payload(workspace())
    second = server.validate_workspace_payload(workspace(name="Anderes Projektlabel"))
    assert first["receipt"]["workspace_sha256"] != second["receipt"]["workspace_sha256"]
    assert first["task"] == second["task"]
    assert first["task_input_hash"] == second["task_input_hash"]


def test_timezone_roundtrip_preserves_project_identity():
    first = reuse.validate_workspace(workspace(event_time="2026-09-01T11:15:31.250+02:00"))
    second = reuse.validate_workspace(workspace(event_time="2026-09-01T09:15:31.250Z"))
    assert first == second
    assert first["event_time"] == "2026-09-01T09:15:31.250Z"


def test_other_context_changes_task_but_not_experimental_policy():
    first = server.validate_workspace_payload(workspace())
    second = server.validate_workspace_payload(workspace(
        organization_name="Anderes Testunternehmen",
        search_prompt="Finde reale Startups zur Digitalisierung öffentlich beschriebener Planungsprozesse."))
    assert first["task_input_hash"] != second["task_input_hash"]
    assert first["task"]["organization_id"] != second["task"]["organization_id"]
    assert first["receipt"]["policy_sha256"] == second["receipt"]["policy_sha256"]
    assert first["policy"]["threshold"] == 61


@pytest.mark.parametrize("field,value", [
    ("threshold", 1), ("confirm_live", True), ("memory_mode", "frozen"),
    ("operator_token", "private-example"), ("api_key", "private-example"),
    ("public_source_package", []), ("dataset_split", "holdout"),
    ("budget", {"max_model_calls": 500}), ("results", []),
])
def test_import_rejects_extra_fields_and_policy_overrides(field, value):
    with pytest.raises(ValueError):
        server.validate_workspace_payload(workspace(**{field: value}))


@pytest.mark.parametrize("changes", [
    {"schema_version": "next-version"}, {"name": "x"},
    {"organization_name": ""}, {"organization_name": 55},
    {"organization_name": "x" * 161}, {"search_prompt": "zu kurz"},
    {"search_prompt": "x" * 2001}, {"event_time": "2026-09-01T10:00:00"},
    {"event_time": "2099-09-01T10:00:00+00:00"},
    {"search_prompt": "Teste Steuerzeichen in einem langen Prompt\x00"},
    {"search_prompt": "Der Schlüssel sk-" + "A" * 24 + " gehört nicht hierher"},
])
def test_invalid_project_is_rejected(changes):
    with pytest.raises(ValueError):
        server.validate_workspace_payload(workspace(**changes))


def test_tampered_export_rejected_but_version_changes_are_explicit():
    receipt = server.validate_workspace_payload(workspace())["receipt"]
    tampered = deepcopy(receipt)
    tampered["workspace"]["search_prompt"] += " Änderung"
    with pytest.raises(ValueError, match="verändert"):
        server.validate_workspace_payload(tampered)
    older = {**receipt, "policy_sha256": "0" * 64, "release_sha256": "0" * 64}
    result = server.validate_workspace_payload(older)
    assert len(result["warnings"]) == 2
    assert result["live_started"] is False


def test_receipt_rejects_unknown_fields_and_bad_hash():
    receipt = server.validate_workspace_payload(workspace())["receipt"]
    with pytest.raises(ValueError):
        reuse.unpack_workspace({**receipt, "credentials": "not-permitted"})
    with pytest.raises(ValueError):
        reuse.unpack_workspace({**receipt, "release_sha256": 12})


def test_no_global_context_mutation_or_provider_call(monkeypatch):
    before = deepcopy(server.PIPE.kb.actors)
    def forbidden(*args, **kwargs):
        raise AssertionError("A transfer validation must not construct a runner")
    monkeypatch.setattr(server, "PairedArchitectureRunner", forbidden)
    for number in range(5):
        result = server.validate_workspace_payload(workspace(organization_name=f"Testfirma {number}"))
        assert result["task"]["organization_name"] == f"Testfirma {number}"
    assert server.PIPE.kb.actors == before


def request_body(body):
    sent = False
    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}
    return Request({"type": "http", "method": "POST", "headers": []}, receive)


def test_http_parser_rejects_oversize_malformed_and_secret_payloads():
    for body, status in [(b"x" * (reuse.MAX_BYTES + 1), 413),
                         (b"not json", 400), (b'{"api_key":"private-secret"}', 400)]:
        result = asyncio.run(server.workspace_validate(request_body(body)))
        assert result.status_code == status
        assert b"private-secret" not in result.body


def test_http_parser_validates_a_real_export_without_operator():
    body = json.dumps(workspace()).encode()
    result = asyncio.run(server.workspace_validate(request_body(body)))
    assert result["status"] == "valid"
    assert result["paid_calls"] == 0


def test_protocol_never_labels_planned_tasks_as_completed():
    value = server.reuse_protocol()
    assert len(value["tasks"]) == 6
    assert len({task["id"] for task in value["tasks"]}) == 6
    assert value["paid_calls"] == 0
    assert "observations" not in value
    assert len(value["release_sha256"]) == 64
    assert value["policy"]["memory_mode"] == "off"


def test_offline_start_profile_disables_external_actions(tmp_path):
    values = transfer_environment(tmp_path)
    for key in ("SCOUTREF_EVAL_LIVE_ENABLED", "PIPEDRIVE_LIVE", "SCOUTREF_ENABLE_LEGACY_API"):
        assert values[key] == "0"
    assert values["OPENAI_API_KEY"] == ""
    assert values["SCOUTREF_OPERATOR_TOKEN"] == ""
    assert "transfer_review" in values["SCOUTREF_RUNTIME_ROOT"]


def test_code_hash_excludes_environment_and_tracks_relevant_source(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "BASE", str(tmp_path))
    (tmp_path / "unit.py").write_text("original", encoding="utf-8")
    ignored = tmp_path / ".venv"
    ignored.mkdir()
    original = server._code_hash()
    (ignored / "dependency.py").write_text("irrelevant", encoding="utf-8")
    assert server._code_hash() == original
    (tmp_path / "unit.py").write_text("changed", encoding="utf-8")
    assert server._code_hash() != original
