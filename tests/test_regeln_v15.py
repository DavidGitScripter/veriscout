"""v15 (12.11.2026): N1 Quellenabgleich, N2 Wortlaut-Hilfe, N3 erweiterter Ausloeser."""
import pytest

import evidence_resolver as er
import follow_up as fu
from core import Candidate, Config, Source
from resource_budget import ResourceBroker, ResourceLimits

SENTENCE = "Wir bereiten Bauschutt aus dem Tiefbau in eigenen Anlagen zu Recyclingbaustoffen auf."


def _resolver(pages, broker=None):
    resolver = er.EvidenceResolver(resource_broker=broker)
    calls = []

    def fetch(self, url):
        if url in self.cache:
            return dict(self.cache[url])
        if self.resource_broker:
            allowed, reason = self.resource_broker.begin_resolver_fetch()
            if not allowed:
                return {"status": "not_checked_budget", "error": reason}
        calls.append(url)
        if url in pages:
            code, text = pages[url]
            result = ({"status": "resolved", "http_status": 200, "resolved_url": url, "text": text}
                      if code == 200 else {"status": "technical_error", "http_status": code})
        else:
            result = {"status": "technical_error", "http_status": 404}
        self.cache[url] = result
        return dict(result)

    return resolver, fetch, calls


def _source(url, excerpt=SENTENCE):
    return Source(url=url, excerpt=excerpt, citation_verified=True, source_id="s1",
                  subject_type="target_organization", subject_name="Ziel AG")


def test_n1_excerpt_found_on_other_page_same_domain_first(monkeypatch):
    resolver, fetch, _ = _resolver({
        "https://ziel.example/news": (200, "Aktuelles ohne den Satz."),
        "https://ziel.example/leistungen": (200, "Leistungen. " + SENTENCE),
        "https://presse.example/artikel": (200, "Bericht. " + SENTENCE)})
    monkeypatch.setattr(er.EvidenceResolver, "_fetch", fetch)
    resolver._fetch("https://presse.example/artikel")
    resolver._fetch("https://ziel.example/leistungen")
    s = resolver.resolve_source(_source("https://ziel.example/news"))
    assert s.excerpt_verified and s.excerpt_match_mode == "relocated"
    assert s.relocation == {"cited_url": "https://ziel.example/news",
                            "verified_url": "https://ziel.example/leistungen",
                            "reason": "auszug_nicht_auf_zitierter_seite_gleiche_domain"}
    assert s.resolved_status == "resolved" and s.resolved_url == "https://ziel.example/leistungen"


def test_n1_other_domain_when_same_domain_has_nothing(monkeypatch):
    resolver, fetch, _ = _resolver({"https://ziel.example/news": (200, "Aktuelles."),
                                    "https://presse.example/artikel": (200, "Bericht. " + SENTENCE)})
    monkeypatch.setattr(er.EvidenceResolver, "_fetch", fetch)
    resolver._fetch("https://presse.example/artikel")
    s = resolver.resolve_source(_source("https://ziel.example/news"))
    assert s.excerpt_verified and s.relocation["reason"].endswith("_andere_domain")


def test_n1_404_replacement_fetch_within_budget(monkeypatch):
    broker = ResourceBroker(ResourceLimits(max_input_tokens=1, max_output_tokens=1, max_reasoning_tokens=1,
                                           max_web_calls=1, max_model_calls=1, max_resolver_fetches=3,
                                           max_cost_usd=1.0))
    resolver, fetch, calls = _resolver({"https://ziel.example/": (200, "Start. " + SENTENCE)}, broker)
    monkeypatch.setattr(er.EvidenceResolver, "_fetch", fetch)
    s = resolver.resolve_source(_source("https://ziel.example/unternehmen/news/alt"))
    assert s.excerpt_verified and s.relocation["reason"] == "abruf_gescheitert_404_ersatzabruf"
    assert calls == ["https://ziel.example/unternehmen/news/alt", "https://ziel.example/"]
    assert broker.summary()["resolver_fetches"] == 2  # Ersatzabruf zaehlt ins Budget


def test_n1_replacement_fetches_at_most_two_and_stop_at_budget(monkeypatch):
    broker = ResourceBroker(ResourceLimits(max_input_tokens=1, max_output_tokens=1, max_reasoning_tokens=1,
                                           max_web_calls=1, max_model_calls=1, max_resolver_fetches=2,
                                           max_cost_usd=1.0))
    resolver, fetch, calls = _resolver({}, broker)
    monkeypatch.setattr(er.EvidenceResolver, "_fetch", fetch)
    s = resolver.resolve_source(_source("https://ziel.example/en/produkte"))
    assert not s.excerpt_verified and not s.relocation
    assert len(calls) <= 2 and broker.summary()["resolver_fetches"] <= 2
    assert er._replacement_urls("https://ziel.example/en/produkte") == [
        "https://ziel.example/", "https://ziel.example/de/produkte"]


def test_n1_paraphrase_is_never_confirmed_anywhere(monkeypatch):
    resolver, fetch, _ = _resolver({"https://ziel.example/news": (200, "Aktuelles."),
                                    "https://ziel.example/leistungen": (200, SENTENCE)})
    monkeypatch.setattr(er.EvidenceResolver, "_fetch", fetch)
    resolver._fetch("https://ziel.example/leistungen")
    s = resolver.resolve_source(_source("https://ziel.example/news",
                                        "Unsere Anlagen verarbeiten Bauschutt aus dem Tiefbau zu Baustoffen."))
    assert not s.excerpt_verified and s.relocation == {}


def test_n1_blocked_database_is_never_replaced_or_used(monkeypatch):
    resolver, fetch, calls = _resolver({"https://www.crunchbase.com/organization/a": (200, SENTENCE),
                                        "https://ziel.example/news": (200, "Aktuelles.")})
    monkeypatch.setattr(er.EvidenceResolver, "_fetch", fetch)
    s = resolver.resolve_source(_source("https://www.crunchbase.com/organization/b"))
    assert s.resolved_status == er.BLOCKED_STATUS and not s.relocation and calls == []
    resolver.cache["https://www.crunchbase.com/organization/a"] = {"status": "resolved", "text": SENTENCE}
    s2 = resolver.resolve_source(_source("https://ziel.example/news"))
    assert not s2.excerpt_verified  # Sperrdatenbank dient nie als Fundseite


def test_n1_no_relocation_after_403(monkeypatch):
    resolver, fetch, calls = _resolver({"https://ziel.example/geschuetzt": (403, ""),
                                        "https://ziel.example/leistungen": (200, SENTENCE)})
    monkeypatch.setattr(er.EvidenceResolver, "_fetch", fetch)
    resolver._fetch("https://ziel.example/leistungen")
    s = resolver.resolve_source(_source("https://ziel.example/geschuetzt"))
    assert not s.excerpt_verified and not s.relocation


# ---------------------------------------------------------------- N2
def test_n2_similar_section_is_deterministic_and_bounded():
    text = ("Erster Satz ohne Bezug. " * 20 + "Unsere modernen Maschinen verwerten viele Arten von Bauabfall "
            "(etwa Beton, Bauschutt oder Asphalt) und sind flexibel einsetzbar. " + "Letzter Satz. " * 20)
    section = fu.similar_section("Unsere Maschinen verwerten Bauabfall wie Beton, Bauschutt oder Asphalt", text)
    assert "verwerten viele Arten von Bauabfall" in section and len(section) <= fu.HINT_MAX_CHARS
    assert section == fu.similar_section("Unsere Maschinen verwerten Bauabfall wie Beton, Bauschutt oder Asphalt", text)
    assert fu.similar_section("voellig anderes Thema", "Kein passender Text hier.") == ""


def test_n2_hints_only_for_fetched_unconfirmed_sources():
    c = Candidate(name="A", description="x", sources=[
        Source(url="https://a.example/1", source_id="a", excerpt="Wir verwerten Bauabfall flexibel.",
               resolved_status="resolved", excerpt_verified=False),
        Source(url="https://a.example/2", source_id="b", excerpt="Bestaetigter Satz hier.",
               resolved_status="resolved", excerpt_verified=True),
        Source(url="https://a.example/3", source_id="c", excerpt="Seite nicht erreichbar.",
               resolved_status="technical_error")])
    cache = {"https://a.example/1": {"text": "Wir verwerten viele Arten von Bauabfall flexibel und mobil."},
             "https://a.example/2": {"text": "Bestaetigter Satz hier."}}
    hints = fu.wording_hints(c, cache)
    assert [h["source_id"] for h in hints] == ["a"] and "Bauabfall" in hints[0]["seitenabschnitt"]


def test_n2_instruction_in_both_arms_and_hint_reaches_prompt():
    for arch in ("sas2", "mas"):
        assert "Zitiere daraus woertlich oder verwirf die Aussage" in fu.follow_up_system(arch)
    c = Candidate(name="A", description="x", candidate_id="cand-1", target_actor_name="Ziel AG")
    prompt = fu.follow_up_user("Auftrag", [(c, ["target_process"])],
                               {"cand-1": [{"source_id": "a", "url": "https://a.example/1",
                                            "bisheriger_auszug": "x", "seitenabschnitt": "Originalsatz."}]})
    assert '"wortlaut_hilfe"' in prompt and "Originalsatz." in prompt


def test_n2_new_quote_on_known_url_gets_own_source_and_keeps_provenance():
    old = Source(url="https://ziel.example/p", source_id="s1", excerpt="paraphrasiert", citation_verified=True,
                 citation_origin="web_search_source", subject_type="target_organization", subject_name="Ziel AG")
    c = Candidate(name="A GmbH", description="x", target_actor_name="Ziel AG", sources=[old], evidence_claims=[])

    class NoCitations:
        last_citations = []

        @staticmethod
        def _normalise_url(url):
            return url

    report = fu.merge(c, {"claims": [{"field": "target_process", "claim_text": "Prozess",
                                      "source_id": "s1", "excerpt": "Wir verwerten viele Arten von Bauabfall flexibel."}],
                          "sources": []}, NoCitations())
    assert report["claims_added"] == 1 and len(c.sources) == 2
    new = c.sources[-1]
    assert new.url == old.url and new.excerpt == "Wir verwerten viele Arten von Bauabfall flexibel."
    assert new.citation_verified and new.source_id == c.evidence_claims[-1]["source_id"]
    assert c.sources[0] is old and old.excerpt == "paraphrasiert"  # nichts ersetzt


def test_n2_unknown_url_without_search_provenance_is_dropped():
    c = Candidate(name="A GmbH", description="x", target_actor_name="Ziel AG", sources=[], evidence_claims=[])

    class NoCitations:
        last_citations = []

        @staticmethod
        def _normalise_url(url):
            return url

    report = fu.merge(c, {"claims": [{"field": "target_process", "claim_text": "P", "source_id": "q",
                                      "excerpt": "Ein Satz, den die Suche nie geliefert hat, zaehlt nicht."}],
                          "sources": [{"source_id": "q", "url": "https://erfunden.example/x"}]}, NoCitations())
    assert report["claims_added"] == 0 and c.sources == []


# ---------------------------------------------------------------- N3
def test_n3_trigger_thresholds_and_unchanged_reserve():
    assert Config.FOLLOW_UP_MIN_INDEX == 44 and Config.FOLLOW_UP_MAX_OPEN_DIMENSIONS == 4
    assert Config.FOLLOW_UP_MAX_COST_USD == pytest.approx(0.25)
    from compare_architectures import ExperimentBudget
    assert ExperimentBudget().arm_max_cost_usd * 2 == pytest.approx(2.0)


def test_v15_prompt_version():
    assert Config.PROMPT_CONTRACT_VERSION in {"public-push-pull-sas2-mas-v15-quellenabgleich-2026-11-12",
                                              "public-push-pull-sas2-mas-v16-prozessfeld-2026-11-12",
                                              "public-push-pull-sas2-mas-v17-suchbudget-2026-11-12"}


def test_v16_confirmed_process_quote_suffices_without_free_text_field():
    from evidence_matrix import EvidenceStatus, _target_process_cell
    c = Candidate(name="A", description="x", process_stage="")
    supported = [{"field": "target_process", "stance": "support", "claim_id": "1", "source_id": "s",
                  "excerpt": "Im Castverfahren extrudieren wir Hart- und Weichfolien."}]
    assert _target_process_cell(c, supported).status == EvidenceStatus.SUPPORTED
    unknown = [dict(supported[0], stance="unknown")]
    assert _target_process_cell(c, unknown).status != EvidenceStatus.SUPPORTED  # unbestaetigt zaehlt nicht
    assert _target_process_cell(c, []).status == EvidenceStatus.MISSING
