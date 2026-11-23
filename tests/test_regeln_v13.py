"""v13 (12.11.2026, David): Sonnet-Suchwerkzeug, QG3, Wiederholversuch, Input-Pruefung."""
import urllib.error

import pytest

import evidence_resolver as er
import llm_anthropic
from core import Candidate, Config, Decision, Source
from quality_gates import QualityGateEvaluator


def test_v13_prompt_version_and_shared_input_check():
    from baselines import SelfReviewSingleAgent
    from agents import VerificationAgent
    assert Config.PROMPT_CONTRACT_VERSION.startswith("public-push-pull-sas2-mas-v1") and "FESTE PRUEFFRAGE" in __import__("review_contract").REVIEW_ROLE_COMMON
    sentence = "FESTE PRUEFFRAGE ZUM INPUT (v13)"
    # beide Arme gleich: dieselbe Pruefregel in der zweiten Stufe
    assert sentence in SelfReviewSingleAgent.REVIEW_SYSTEM and sentence in VerificationAgent.SYSTEM
    assert "input_stream_mechanism" in SelfReviewSingleAgent.REVIEW_SYSTEM


def test_sonnet_uses_older_search_tool_and_records_it():
    assert llm_anthropic.WEB_SEARCH_TOOL_VERSION == "web_search_20250305"
    import inspect
    assert "WEB_SEARCH_TOOL_VERSION" in inspect.getsource(llm_anthropic.complete)
    import scripts.run_study as rs  # noqa: F401
    cfg = rs.effective_config(["claude-sonnet-5-5", "gpt-6.1-sol"])
    assert cfg["web_search_tool"] == {"claude-sonnet-5-5": "web_search_20250305",
                                      "gpt-6.1-sol": "openai_web_search"}


def _src(url, supports, confirmed):
    return Source(url=url, source_type="official", supports=supports, excerpt="Auszug mit genug Text dazu.",
                  subject_type="candidate_startup", subject_name="A GmbH",
                  citation_verified=True, resolved_status="resolved" if confirmed else "resolved",
                  excerpt_verified=confirmed)


def _decision(sources, cells):
    c = Candidate(name="A GmbH", description="x", discovery_mode="live", website="https://a.example",
                  sources=sources)
    c.evidence_matrix = {"cells": [{"dimension": d, "status": s} for d, s in cells.items()],
                         "decision_state": "fully_supported"}
    c.verification_status = "verified_startup"
    return Decision(candidate=c, matches=[])


def _qg3(decision):
    return next(g for g in QualityGateEvaluator().evaluate(decision) if g.gate_id == "QG3_NATIVE_SOURCE_PROVENANCE")


def test_qg3_unconfirmed_source_superseded_when_claim_otherwise_confirmed():
    gate = _qg3(_decision([_src("https://a.example/p", ["product"], True),
                           _src("https://presse.example/i", ["founded"], False)],
                          {"startup_status": "supported", "startup_capability": "supported"}))
    assert gate.passed
    assert gate.evidence["unconfirmed_superseded"] == [{"url": "https://presse.example/i", "supports": ["founded"]}]


def test_qg3_unconfirmed_source_blocks_when_claim_not_otherwise_confirmed():
    gate = _qg3(_decision([_src("https://a.example/p", ["product"], True),
                           _src("https://presse.example/i", ["founded"], False)],
                          {"startup_status": "partial", "startup_capability": "supported"}))
    assert not gate.passed and gate.evidence["blocking_unconfirmed"] == ["https://presse.example/i"]
    # ohne jede bestaetigte Quelle nie bestanden
    assert not _qg3(_decision([_src("https://presse.example/i", ["founded"], False)],
                              {"startup_status": "supported"})).passed


class _Opener:
    def __init__(self, errors):
        self.errors = list(errors); self.calls = 0

    def open(self, request, timeout=None):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


@pytest.mark.parametrize("error,retried", [
    (urllib.error.URLError(TimeoutError("timed out")), True),
    (TimeoutError("timed out"), True),
    (urllib.error.HTTPError("u", 429, "Too Many", {}, None), True),
    (urllib.error.HTTPError("u", 403, "Forbidden", {}, None), False),
    (urllib.error.HTTPError("u", 404, "Not Found", {}, None), False),
    (urllib.error.HTTPError("u", 401, "Unauthorized", {}, None), False),
])
def test_exactly_one_retry_only_for_timeout_connection_and_429(monkeypatch, error, retried):
    monkeypatch.setattr(er.time, "sleep", lambda s: None)
    opener = _Opener([error])
    if retried:
        assert er._open_with_one_retry(opener, None, 1) == "ok" and opener.calls == 2
    else:
        with pytest.raises(type(error)):
            er._open_with_one_retry(opener, None, 1)
        assert opener.calls == 1
    # nie mehr als ein Wiederholversuch
    twice = _Opener([urllib.error.URLError(TimeoutError("t")), urllib.error.URLError(TimeoutError("t"))])
    with pytest.raises(urllib.error.URLError):
        er._open_with_one_retry(twice, None, 1)
    assert twice.calls == 2


def test_source_tls_context_verifies_strictly():
    import ssl
    from http_security import source_tls_context
    ctx = source_tls_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True
