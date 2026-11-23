"""Freigabe: Bindung an die Entscheidungsversion, belegte Adresse, kein Versand."""
import json
import pathlib

import release
import server


def _record(run_set="probe", state="empfehlung"):
    decision = {"decision_state": state, "candidate": {
        "candidate_id": "cand-1", "name": "Stein GmbH", "website": "https://www.stein-start.de",
        "evidence_matrix": {"claim_manifest": [
            {"field": "target_process", "claim_text": "Firma schneidet Naturstein.", "stance": "support"},
            {"field": "startup_capability", "claim_text": "Stein GmbH verwertet Schleifschlamm.", "stance": "support"}]}}}
    return {"run_set": run_set,
            "operator_view": {"run_id": "run-rel", "run_set": run_set,
                              "task": {"organization_name": "Beispiel AG"}},
            "internal_pairs": [{"pair_id": "pair-rel", "arms": [
                {"architecture_internal": "mas", "decisions": [decision]}]}]}


def _setup(tmp_path, monkeypatch, record):
    monkeypatch.setattr(server, "RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(server, "RELEASE_LOG", str(tmp_path / "release_log.jsonl"))
    (tmp_path / "run-rel.json").write_text(json.dumps(record), encoding="utf-8")
    return server.ReleaseReq(run_id="run-rel", pair_index=0, architecture="mas",
                             candidate_id="cand-1")


def _fingerprint(record):
    pair, _arm, decision = release.find_decision(record, 0, "mas", "cand-1")
    return release.decision_fingerprint("run-rel", pair, "mas", decision)


def test_contact_email_comes_only_from_the_startup_website():
    pages = {
        "https://stein-start.de/": {"status": "resolved", "text": "Willkommen. Partner: max@gmail.com",
                                    "links": ["https://stein-start.de/impressum"]},
        "https://stein-start.de/impressum": {"status": "resolved",
                                             "text": "Kontakt: info [at] stein-start [dot] de, jobs@stein-start.de"},
    }
    calls = []

    def fetch(url):
        calls.append(url)
        return pages.get(url, {"status": "technical_error"})

    result = release.find_contact_email("https://www.stein-start.de", fetch)
    assert result["email"] == "info@stein-start.de"
    assert result["source_url"] == "https://stein-start.de/impressum"
    assert "max@gmail.com" not in json.dumps(result)
    assert all(url.startswith("https://stein-start.de") for url in calls)
    nothing = release.find_contact_email("https://stein-start.de", lambda url: {"status": "resolved", "text": "kein Kontakt"})
    assert nothing["email"] == ""


def test_release_is_bound_to_the_exact_decision_version(tmp_path, monkeypatch):
    record = _record()
    req = _setup(tmp_path, monkeypatch, record)
    req.action, req.confirm = "crm", True
    req.decision_sha256 = "decision-veraltet"
    assert server.comparison_release(req).status_code == 409
    req.decision_sha256 = _fingerprint(record)
    result = server.comparison_release(req)
    assert result["result"]["modus"] == "dry-run"
    assert result["result"]["operation"] in {"created", "updated"}
    log = (tmp_path / "release_log.jsonl").read_text(encoding="utf-8")
    assert req.decision_sha256 in log


def test_email_is_only_a_draft_and_needs_confirmation(tmp_path, monkeypatch):
    record = _record()
    req = _setup(tmp_path, monkeypatch, record)
    req.action, req.decision_sha256 = "email_draft", _fingerprint(record)
    req.email_to, req.subject, req.body = "info@stein-start.de", "Anfrage", "Text"
    assert server.comparison_release(req).status_code == 403  # nicht bestaetigt
    req.confirm = True
    result = server.comparison_release(req)
    assert result["result"]["mailto"].startswith("mailto:info@stein-start.de?")
    source = pathlib.Path(release.__file__).read_text(encoding="utf-8")
    assert "smtplib" not in source and "sendmail" not in source


def test_release_is_locked_for_study_runs_and_non_recommendations(tmp_path, monkeypatch):
    req = _setup(tmp_path, monkeypatch, _record(run_set="studie"))
    req.action, req.confirm = "crm", True
    assert server.comparison_release(req).status_code == 403
    assert server.comparison_release_preview(req).status_code == 403
    record = _record(state="enthaltung")
    req = _setup(tmp_path, monkeypatch, record)
    req.action, req.confirm, req.decision_sha256 = "crm", True, _fingerprint(record)
    assert server.comparison_release(req).status_code == 403


def test_draft_text_uses_evidenced_claims_and_no_guessed_address():
    _pair, _arm, decision = release.find_decision(_record(), 0, "mas", "cand-1")
    draft = release.email_draft(decision, "Beispiel AG", "D. S.")
    assert "Schleifschlamm" in draft["body"] and "Beispiel AG" in draft["subject"]
    assert "@" not in draft["body"]
