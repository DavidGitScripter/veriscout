"""v14 (12.11.2026): M1 Datenbanken, M2 Nachrecherche, M3 Schreibvarianten, M5 Fortbestand,
Input ohne Freitextfeld. Beide Arme identisch."""
import json
import sys

import pytest

import evidence_resolver as er
import follow_up as fu
from compare_architectures import ExperimentBudget
from core import Candidate, Config, Source

sys.path.insert(0, __import__("os").path.dirname(__file__))
import test_p0_end_to_end_comparison as e2e  # noqa: E402
from test_p0_end_to_end_comparison import offline_documents  # noqa: E402,F401  (Fixture)


# ---------------------------------------------------------------- M1
@pytest.mark.parametrize("url,blocked", [
    ("https://www.crunchbase.com/organization/assemblio", True),
    ("https://de.linkedin.com/company/x", True),
    ("https://app.dealroom.co/companies/sprayvision", True),
    ("https://www.northdata.de/Optocycle", True),
    ("https://www.evi.gv.at/f/663933y", False),
    ("https://www.optocycle.com/impressum", False),
    ("https://notcrunchbase.com.example.org/x", False),
])
def test_m1_paid_databases_are_recognised(url, blocked):
    assert er.is_blocked_source(url) is blocked


def test_m1_blocked_source_is_never_fetched_and_never_counts(monkeypatch):
    monkeypatch.setattr(er.EvidenceResolver, "_fetch", lambda self, url: pytest.fail("abgerufen"))
    s = Source(url="https://www.crunchbase.com/organization/a", excerpt="Gegruendet 2021 in Berlin, B2B Software.",
               citation_verified=True, supports=["founded"])
    er.EvidenceResolver().resolve_source(s)
    assert s.resolved_status == er.BLOCKED_STATUS and s.excerpt_verified is False


def test_m1_rule_is_in_prompt_of_both_arms_and_all_stages():
    from agents import ScoutingAgent, VerificationAgent
    from baselines import SelfReviewSingleAgent
    for text in (ScoutingAgent.SYSTEM, VerificationAgent.SYSTEM, SelfReviewSingleAgent.REVIEW_SYSTEM,
                 fu.follow_up_system("sas2"), fu.follow_up_system("mas")):
        assert "QUELLEN (v14)" in text and "Crunchbase" in text
        assert "Zitiere nur URLs, die in deinen eigenen Suchergebnissen" in text


# ---------------------------------------------------------------- M3
def test_m3_spelling_variants_match():
    page = "Wir verwerten Bau­schutt und Beton. Die Recy-\ncling-Anlage arbeitet ﬂexibel und rund um die Uhr."
    t = er._normalise_claim(page)
    assert er._normalise_claim("Wir verwerten Bauschutt und Beton") in t
    assert er._normalise_claim("Die Recycling-Anlage arbeitet flexibel und rund um die Uhr") in t
    assert er._normalise_claim("„Wir verwerten Bauschutt“ – und Beton") in t


def test_m3_paraphrase_and_composed_parts_still_fail():
    page = er._normalise_claim("Status Eingetragen. Firmenbuchnummer 663933y. Adresse Werk-VI-Strasse 46. "
                               "Eintragungsdatum 08.10.2025. Wir sortieren Bauschutt mit Kameras.")
    assert er.excerpt_match(er._normalise_claim("Status Eingetragen Firmenbuchnummer 663933y Eintragungsdatum 08.10.2025"), page) == ""
    assert er.excerpt_match(er._normalise_claim("Unsere Kameras sortieren den Bauschutt automatisch"), page) == ""


# ---------------------------------------------------------------- M5 / Input
def test_m5_active_only_with_checked_imprint():
    c = Candidate(name="A GmbH", description="x", operating_status="unknown")
    er.apply_operating_rule(c)
    assert c.operating_status == "unknown"
    c.impressum = {"url": "https://a.example/impressum", "company_name_found": True, "register": ""}
    er.apply_operating_rule(c)
    assert c.operating_status == "active" and c.operating_status_basis.startswith("Regel M5")
    for status in ("acquired", "insolvent", "ceased"):
        n = Candidate(name="A GmbH", description="x", operating_status=status)
        n.impressum = dict(c.impressum)
        er.apply_operating_rule(n)
        assert n.operating_status == status


def test_input_supported_without_free_text_field():
    from evidence_matrix import EvidenceStatus, _input_stream_cell
    c = Candidate(name="A", description="x", input_stream="")
    manifest = [{"field": "input_stream", "stance": "support", "basis": "direct", "claim_id": "1",
                 "source_id": "s", "excerpt": "Bei uns fallen jaehrlich viele Tonnen Bauschutt an."}]
    assert _input_stream_cell(c, manifest).status == EvidenceStatus.SUPPORTED


# ---------------------------------------------------------------- M2
def _decision(state="enthaltung", index=78, blocking=("input_stream", "relational_chain"), contra=(), reasons=()):
    return {"decision_state": state, "best_score": index,
            "candidate": {"evidence_matrix": {"blocking_dimensions": list(blocking), "contradictions": list(contra)},
                          "verification_reasons": list(reasons)}}


def test_m2_trigger_rule():
    # v15 (N3): Index >= 44 und hoechstens vier offene Dimensionen.
    assert fu.qualifies(_decision())[0]
    assert fu.qualifies(_decision(index=44))[0]
    assert not fu.qualifies(_decision(index=43))[0]
    assert fu.qualifies(_decision(blocking=("target_process", "input_stream", "output_application", "startup_status")))[0]
    assert not fu.qualifies(_decision(blocking=("target_process", "input_stream", "output_application",
                                                "startup_status", "transformation")))[0]
    assert fu.qualifies(_decision(blocking=("target_process", "input_stream", "output_application",
                                            "startup_status", "relational_chain")))[0]
    assert not fu.qualifies(_decision(contra=("startup_status",)))[0]
    assert not fu.qualifies(_decision(reasons=("Ausschluss: Scale-up, kein Startup",)))[0]
    assert not fu.qualifies(_decision(state="empfehlung"))[0]
    assert not fu.qualifies(_decision(state="ablehnung"))[0]
    assert fu.open_dimensions(_decision(blocking=("startup_status", "output_application", "target_process"))) == \
        ["target_process", "output_application", "startup_status"]


def test_m2_same_instructions_for_both_arms_only_role_differs():
    from review_contract import MAS_REVIEW_ROLE, SAS_REVIEW_ROLE
    sas, mas = fu.follow_up_system("sas2"), fu.follow_up_system("mas")
    assert sas.replace(SAS_REVIEW_ROLE, "") == mas.replace(MAS_REVIEW_ROLE, "")
    assert "hoechstens drei Websuchen" in sas


def test_m2_budget_reserve_and_worst_case():
    b = ExperimentBudget()
    limits = b.resource_limits()
    assert limits.max_model_calls == b.max_model_calls + 1
    assert limits.max_input_tokens == b.max_input_tokens + Config.FOLLOW_UP_MAX_INPUT_TOKENS
    assert limits.max_resolver_fetches == b.max_resolver_fetches + Config.FOLLOW_UP_MAX_FETCHES
    assert b.arm_max_cost_usd == pytest.approx(b.max_cost_usd + Config.FOLLOW_UP_MAX_COST_USD)
    # Reserve deckt den schlechtesten Fall der Nachrecherche fuer beide Modelle.
    for model in ("gpt-6.1-sol", "claude-sonnet-5-5"):
        pin, pout = Config.PRICES[model]
        worst = (Config.FOLLOW_UP_MAX_INPUT_TOKENS * pin
                 + (Config.FOLLOW_UP_MAX_OUTPUT_TOKENS + Config.FOLLOW_UP_MAX_REASONING_TOKENS) * pout) / 1e6 \
            + Config.FOLLOW_UP_MAX_TOOL_CALLS * Config.WEB_SEARCH_PRICE
        assert worst <= Config.FOLLOW_UP_MAX_COST_USD + 1e-9


class _LLM:
    def __init__(self, citations):
        self.last_citations = citations

    def ground_sources(self, sources):
        from core import LLMClient
        return LLMClient.ground_sources(self, sources)

    @staticmethod
    def _normalise_url(url):
        from core import LLMClient
        return LLMClient._normalise_url(url)


def test_m2_merge_adds_only_grounded_unblocked_evidence_and_never_replaces():
    c = Candidate(name="A GmbH", description="x", website="https://a.example", target_actor_name="Ziel AG",
                  sources=[Source(url="https://a.example/p", source_id="s1", excerpt="alt")],
                  evidence_claims=[{"claim_id": "c1", "field": "startup_capability", "stance": "unknown",
                                    "source_id": "s1", "excerpt": "alt", "claim_text": "alt"}])
    entry = {"founded": 2021, "claims": [
        {"field": "input_stream", "claim_text": "Ziel AG verarbeitet Bauschutt", "source_id": "x1",
         "excerpt": "Wir verarbeiten jaehrlich viele Tonnen Bauschutt aus eigenen Baustellen."},
        {"field": "output_application", "claim_text": "erfunden", "source_id": "x2",
         "excerpt": "Diese Quelle wurde von der Websuche nie geliefert und zaehlt nicht."},
        {"field": "founded_is_no_field", "claim_text": "x", "source_id": "x1", "excerpt": "Wir verarbeiten jaehrlich viele Tonnen."},
        {"field": "startup_status", "claim_text": "DB", "source_id": "x3", "excerpt": "Gegruendet 2021 in Berlin als B2B-Startup fuer Software."}],
        "sources": [{"source_id": "x1", "url": "https://ziel.example/prozess", "subject_type": "target_organization",
                     "subject_name": "Ziel AG", "excerpt": "Wir verarbeiten"},
                    {"source_id": "x2", "url": "https://nie-gesucht.example/x", "subject_type": "candidate_startup"},
                    {"source_id": "x3", "url": "https://www.crunchbase.com/organization/a"}]}
    report = fu.merge(c, entry, _LLM([{"url": "https://ziel.example/prozess", "origin": "web_search_source"},
                                      {"url": "https://www.crunchbase.com/organization/a", "origin": "web_search_source"}]))
    assert report["sources_grounded"] == 1 and report["sources_blocked"] == 1 and report["claims_added"] == 1
    assert [s.url for s in c.sources] == ["https://a.example/p", "https://ziel.example/prozess"]
    assert c.evidence_claims[0] == {"claim_id": "c1", "field": "startup_capability", "stance": "unknown",
                                    "source_id": "s1", "excerpt": "alt", "claim_text": "alt"}
    added = c.evidence_claims[-1]
    assert added["field"] == "input_stream" and added["subject_type"] == "target_organization"
    assert added["origin"] == "follow_up" and c.founded == 2021


def test_m2_follow_up_closes_missing_input_end_to_end(offline_documents, monkeypatch):
    """Ohne Mechanismusbeleg Enthaltung; die Nachrecherche liefert ihn mit bestaetigtem
    Auszug nach, danach Empfehlung, in beiden Armen gleich."""
    monkeypatch.setattr(e2e, "_stage1", e2e._derived_stage1(False))
    monkeypatch.setitem(e2e.DOCUMENTS, e2e.MECHANISM_URL, (
        "<html><body><p>Bei der Aufbereitung von Bauschutt in Brech- und Siebanlagen "
        "fallen feinkoernige Brechsande als Reststrom an.</p></body></html>"))
    original = e2e.ScriptedLLM.complete
    seen = []

    def patched(self, model, system, user, **kwargs):
        purpose = kwargs.get("purpose", "")
        if not purpose.startswith("follow_up"):
            return original(self, model, system, user, **kwargs)
        seen.append((purpose, user.split("Offene Dimensionen je Kandidat:\n", 1)[1]))
        text = original(self, model, system, user, **kwargs)  # bucht Nutzung wie ein echter Aufruf
        items = json.loads(user.split("Offene Dimensionen je Kandidat:\n", 1)[1])
        self.last_citations = [{"url": e2e.MECHANISM_URL, "title": "Fachwissen", "origin": "web_search_source"}]
        return json.dumps([{"candidate_id": item["candidate_id"], "founded": None, "claims": [{
            "field": "input_stream_mechanism", "claim_text": "Bauschuttaufbereitung erzeugt feinkoernige Brechsande",
            "source_id": "f1", "excerpt": "Bei der Aufbereitung von Bauschutt in Brech- und Siebanlagen "
                                          "fallen feinkoernige Brechsande als Reststrom an"}],
            "sources": [{"source_id": "f1", "url": e2e.MECHANISM_URL, "title": "Fachwissen", "source_type": "press",
                         "subject_type": "relation", "subject_name": "Bauschuttaufbereitung",
                         "excerpt": "Bei der Aufbereitung von Bauschutt"}]} for item in items])

    monkeypatch.setattr(e2e.ScriptedLLM, "complete", patched)
    result = e2e._runner(e2e._task()).run_pair(e2e._task())
    assert sorted(p for p, _ in seen) == ["follow_up_mas", "follow_up_sas2"]
    assert seen[0][1] == seen[1][1]  # identische Eingabe beider Arme
    for arm in result["arms"]:
        assert arm["decision_states"] == ["empfehlung"], arm["architecture_internal"]
        info = arm["discovery_trace"]["output"]["follow_up"]
        assert info["triggered"] and info["candidates"][0]["state_before"] == "enthaltung"
        assert info["candidates"][0]["state_after"] == "empfehlung"
        cells = {c["dimension"]: c for c in arm["decisions"][0]["candidate"]["evidence_matrix"]["cells"]}
        assert cells["input_stream"]["basis"] == "derived"
        assert arm["result_status"] != "technical_error"


