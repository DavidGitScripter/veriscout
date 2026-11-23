"""Pipedrive-Bereich der Oberflaeche: lesend, Live nur bewusst, Studienlaeufe gesperrt."""
import json
import pathlib

import pytest
import release
import server
from crm_pipedrive import PipedriveAdapter
from scripts.start_live_review import development_environment, pipedrive_live_flag

ROOT = pathlib.Path(__file__).resolve().parents[1]


class _LiveAdapter(PipedriveAdapter):
    """Adapter, der sich wie live verhaelt, aber jeden Netzzugriff verbietet."""

    def __init__(self):
        super().__init__(dry_run=True)
        self.dry_run = False
        self.writes = []

    def _api(self, method, path, **kwargs):  # pragma: no cover - darf nie laufen
        self.writes.append((method, path))
        raise AssertionError(f"Netzzugriff im Test: {method} {path}")


def _study_record():
    decision = {"decision_state": "empfehlung", "candidate": {
        "candidate_id": "cand-1", "name": "Stein GmbH", "website": "https://stein-start.de"}}
    return {"run_set": "studie",
            "operator_view": {"run_id": "run-rel", "run_set": "studie",
                              "task": {"organization_name": "Beispiel AG"}},
            "internal_pairs": [{"pair_id": "pair-rel", "arms": [
                {"architecture_internal": "mas", "decisions": [decision]}]}]}


def test_pipedrive_live_is_off_by_default_and_only_on_explicit_request(tmp_path):
    assert development_environment(tmp_path)["PIPEDRIVE_LIVE"] == "0"
    assert pipedrive_live_flag(False) == "0"
    assert pipedrive_live_flag(True) == "1"


def test_study_runs_never_reach_crm_even_when_live(tmp_path, monkeypatch):
    adapter = _LiveAdapter()
    monkeypatch.setattr(server, "_adapter", adapter)
    monkeypatch.setattr(server, "LIVE_CRM", True)
    monkeypatch.setattr(server, "RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(server, "RELEASE_LOG", str(tmp_path / "release_log.jsonl"))
    record = _study_record()
    (tmp_path / "run-rel.json").write_text(json.dumps(record), encoding="utf-8")
    pair, _arm, decision = release.find_decision(record, 0, "mas", "cand-1")
    req = server.ReleaseReq(run_id="run-rel", pair_index=0, architecture="mas",
                            candidate_id="cand-1", action="crm", confirm=True,
                            decision_sha256=release.decision_fingerprint(
                                "run-rel", pair, "mas", decision))
    assert server.comparison_release(req).status_code == 403
    assert server.comparison_release_preview(req).status_code == 403
    assert adapter.writes == []


def test_crm_status_is_read_only_and_hides_the_token(monkeypatch):
    adapter = PipedriveAdapter(dry_run=True)
    adapter.orgs = {1: {"id": 1, "name": "Stein GmbH"}}
    monkeypatch.setattr(server, "_adapter", adapter)
    monkeypatch.setattr(server, "LIVE_CRM", False)
    monkeypatch.setattr(server.Config, "PIPEDRIVE_API_TOKEN", "secret-token-never-shown")
    monkeypatch.setenv("PIPEDRIVE_LIVE", "0")
    status = server.comparison_crm_status()
    assert status["mode"] == "dry-run"
    assert status["token_configured"] is True
    assert status["study_runs_locked"] is True
    assert [o["name"] for o in status["organizations"]] == ["Stein GmbH"]
    assert "--pipedrive-live" in status["hint"]
    assert "secret-token-never-shown" not in json.dumps(status)


def test_crm_status_route_needs_operator_and_is_get_only():
    routes = {(r.path, tuple(sorted(r.methods))) for r in server.app.routes
              if getattr(r, "path", "") == "/api/comparison/crm"}
    assert routes == {("/api/comparison/crm", ("GET",))}
    from fastapi.testclient import TestClient
    client = TestClient(server.app)
    assert client.get("/api/comparison/crm").status_code == 401


@pytest.mark.parametrize("file_id", ["keyFile", "ratingFiles"])
def test_file_inputs_keep_ids_inside_accessible_dropzones(file_id):
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert f'data-dropzone="{file_id}"' in html
    assert f'id="{file_id}" type="file"' in html
    assert f'aria-labelledby="{file_id}Label"' in html
    assert f'data-dz-clear="{file_id}"' in html
