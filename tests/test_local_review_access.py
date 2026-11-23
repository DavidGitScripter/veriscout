import os
from pathlib import Path

import pytest
import server
from scripts.start_live_review import development_environment, operator_secret


def test_readiness_names_missing_gates_without_secrets(monkeypatch):
    monkeypatch.setattr(server, "LIVE_EVAL_ENABLED", False)
    monkeypatch.setattr(server, "OPERATOR_TOKEN", "")
    monkeypatch.setenv("OPENAI_API_KEY", "never-show-this-key")
    config = server.comparison_config()
    assert config["live_enabled"] is False
    assert {item["code"] for item in config["live_blockers"]} == {
        "server_disabled", "operator_missing"}
    assert "never-show-this-key" not in repr(config)


def test_readiness_opens_only_when_all_gates_exist(monkeypatch):
    monkeypatch.setattr(server, "LIVE_EVAL_ENABLED", True)
    monkeypatch.setattr(server, "OPERATOR_TOKEN", "private-test-operator")
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-api")
    config = server.comparison_config()
    assert config["live_enabled"] is True
    assert config["live_blockers"] == []
    assert "private-test" not in repr(config)


def test_development_profile_is_bounded_and_disables_external_writes(tmp_path):
    config = development_environment(tmp_path)
    # Seit 18.10.2026 wie das Hauptprofil (drei Kandidaten), damit eigene
    # Testlaeufe dieselben Bedingungen wie die Studie haben.
    assert config["SCOUTREF_EVAL_MAX_CANDIDATES"] == "3"
    assert config["SCOUTREF_EVAL_MAX_MODEL_CALLS"] == "2"
    assert float(config["SCOUTREF_STUDY_BUDGET_USD"]) <= 10.0
    assert config["SCOUTREF_RUN_MAX_COST_USD"] == "1.50"
    assert config["SCOUTREF_ENABLE_LEGACY_API"] == "0"
    assert config["PIPEDRIVE_LIVE"] == "0"
    assert Path(config["SCOUTREF_STUDY_BUDGET_LEDGER"]).parent == tmp_path / "runtime"
    assert "OPENAI_API_KEY" not in config


def test_operator_key_is_private_and_retained(tmp_path):
    path = tmp_path / "operator.txt"
    first = operator_secret(path)
    assert len(first) >= 32
    assert operator_secret(path) == first
    assert path.stat().st_mode & 0o777 == 0o600


def test_operator_key_rejects_symlinks_and_public_files(tmp_path):
    path = tmp_path / "operator.txt"
    operator_secret(path)
    link = tmp_path / "link.txt"
    link.symlink_to(path)
    with pytest.raises(OSError):
        operator_secret(link)
    path.chmod(0o644)
    with pytest.raises(RuntimeError):
        operator_secret(path)


@pytest.mark.parametrize("changes", [
    {"dataset_split": "holdout"}, {"repetitions": 2}, {"memory_mode": "both"},
])
def test_development_mode_never_runs_a_main_study(monkeypatch, changes):
    monkeypatch.setattr(server, "LOCAL_REVIEW_MODE", True)
    monkeypatch.setattr(server, "LIVE_EVAL_ENABLED", True)
    monkeypatch.setattr(server, "OPERATOR_TOKEN", "private-test-operator")
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-api")
    request = type("Request", (), {"headers": {
        "X-VentureScout-Token": "private-test-operator"}})()
    values = dict(organization_name="Example", search_prompt="Public recycling research task",
                  confirm_live=True, dataset_split="pilot", repetitions=1, memory_mode="off")
    values.update(changes)
    result = server.comparison_run(server.ComparisonReq(**values), request)
    assert result.status_code == 422



def test_local_operator_key_only_for_same_origin_local_mode(monkeypatch):
    import server

    class Req:
        def __init__(self, host, origin=""):
            self.headers = {"host": host, "origin": origin}

    monkeypatch.setattr(server, "OPERATOR_TOKEN", "private-test-operator")
    monkeypatch.setattr(server, "LOCAL_REVIEW_MODE", False)
    assert server.local_operator(Req("127.0.0.1:8000")).status_code == 403
    monkeypatch.setattr(server, "LOCAL_REVIEW_MODE", True)
    assert server.local_operator(Req("127.0.0.1:8000"))["operator_token"] == "private-test-operator"
    # Fremde Webseite im selben Browser oder fremder Host: abgewiesen.
    assert server.local_operator(Req("127.0.0.1:8000", "https://evil.example.org")).status_code == 403
    assert server.local_operator(Req("attacker.example.org")).status_code == 403
