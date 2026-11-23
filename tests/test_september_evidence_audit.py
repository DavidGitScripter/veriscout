"""Regressionsfaelle aus dem Literatur-/Codeabgleich, keine Qualitaetsmessung."""
from agents import ScoutingAgent, VerificationAgent
from baselines import SelfReviewSingleAgent
from core import Candidate, LLMClient, Source
from evidence_matrix import build_claim_manifest
from evidence_resolver import EvidenceResolver
from knowledge_base import KnowledgeBase
from resource_budget import ResourceBroker, ResourceLimits
from evaluation_analysis import paired_metrics


def test_document_query_parameters_are_not_discarded_for_grounding():
    normalise = LLMClient._normalise_url
    assert normalise("https://example.org/doc?id=1") != normalise("https://example.org/doc?id=2")
    assert normalise("https://example.org/doc?id=1#page2") == normalise("https://example.org/doc?id=1")
    assert normalise("https://user:password@example.org/doc") == ""
    assert normalise("javascript:alert(1)") == ""


def _source(url="https://example.org/product", source_id="s1"):
    return Source(url=url, source_id=source_id,
                  excerpt="The company produces building materials from mineral waste.",
                  citation_verified=True, subject_type="candidate_startup",
                  subject_name="Example Startup")


def test_distinct_claim_excerpt_does_not_inherit_source_verification():
    source = _source()
    source.resolved_status = "resolved"
    source.excerpt_verified = True
    candidate = Candidate(name="Example Startup", discovery_mode="live", sources=[source],
        evidence_claims=[dict(claim_id="c1", claim_text="Accepts all hazardous sludge.",
            field="startup_capability", source_id="s1",
            excerpt="We accept every hazardous sludge with no technical constraints.",
            stance="support", subject_type="candidate_startup", subject_name="Example Startup")])
    record = build_claim_manifest(candidate)[0]
    assert record["stance"] == "unknown"


def test_resolver_verifies_additional_real_claim_excerpt_from_same_document():
    source = _source()
    extra = "Our product is a mineral building block for indoor applications."
    resolver = EvidenceResolver()
    resolver.cache[source.url] = {"status": "resolved", "text": source.excerpt + " " + extra}
    candidate = Candidate(name="Example Startup", discovery_mode="live", sources=[source],
        evidence_claims=[dict(claim_id="c1", claim_text="Produces building blocks.",
            field="startup_capability", source_id="s1", excerpt=extra,
            stance="support", subject_type="candidate_startup", subject_name="Example Startup")])
    result = resolver.resolve_candidates([candidate], max_fetches_total=0)
    assert result["checked"] == 0
    assert len(source.verified_excerpt_hashes) == 2
    assert build_claim_manifest(candidate)[0]["stance"] == "support"


def test_document_budget_counts_unique_urls_not_duplicate_claim_records():
    class LocalResolver(EvidenceResolver):
        def _fetch(self, url):
            self.cache.setdefault(url, {"status": "resolved", "text": _source().excerpt})
            return dict(self.cache[url])
    sources = [_source(source_id="one"), _source(source_id="duplicate"),
               _source("https://example.org/second", "two"),
               _source("https://example.org/third", "three")]
    result = LocalResolver().resolve_candidates([Candidate(name="Example Startup", sources=sources)], 2)
    assert result["checked"] == 2
    assert [s.resolved_status for s in sources] == ["resolved"] * 3 + ["not_checked_budget"]


def test_failure_is_sticky_for_subsequent_paid_model_calls():
    broker = ResourceBroker(ResourceLimits(10000, 10000, 10000, 5, 2, 5, 1.0))
    broker.mark_failure("provider_timeout")
    assert broker.authorize_model_call(estimated_input_tokens=1,
        max_output_tokens=1, max_web_calls=0) == (False, "prior_resource_failure")


def test_verifier_does_not_inherit_unverified_capability_narrative():
    candidate = Candidate(name="Example Startup", discovery_mode="live",
        description="Claims to recycle any hazardous material.",
        steckbrief={"usp": "Unsupported marketing claim"}, is_service_provider=True,
        evidence_claims=[{"claim_text": "Unverified old claim"}])
    VerificationAgent()._merge(candidate, {"exists": True, "claims": []})
    assert candidate.description == ""
    assert candidate.evidence_claims == []
    assert candidate.steckbrief == {}
    VerificationAgent()._merge(candidate, {"exists": True,
        "description": "Manufactures mineral building materials.", "entity_type": "startup"})
    assert candidate.description == "Manufactures mineral building materials."
    assert candidate.is_service_provider is False


def test_sas2_first_pass_has_identical_scout_instructions_and_retains_native_sources():
    class FakeLLM:
        def __init__(self):
            self.calls = []
            self.last_usage = {}
            self.last_citations = []
        def available(self): return True
        def complete(self, **kwargs):
            self.calls.append(kwargs)
            self.last_usage = {"status": "completed"}
            self.last_citations = ([{"url": "https://example.org/first"}]
                                   if len(self.calls) == 1 else [])
            return "[]"
        def usage_ledger(self): return []
        def cost_estimate(self): return {}
    llm = FakeLLM()
    SelfReviewSingleAgent(KnowledgeBase(), llm).run("Public search", n=1, defer_resolution=True)
    assert llm.calls[0]["system"] == ScoutingAgent.SYSTEM
    assert llm.last_citations == [{"url": "https://example.org/first"}]


def test_excluded_pair_remains_visible_in_all_assigned_operational_outcomes():
    manifest = {"schema_version": "venture-scout-assignment-v2",
        "pair_id": "pair1", "task_id": "task1", "assignments": [
            {"architecture": "sas2", "blind_arm_id": "a", "returned_candidates": 0,
             "expected_candidate_ids": [], "result_status": "technical_error"},
            {"architecture": "mas", "blind_arm_id": "b", "returned_candidates": 0,
             "expected_candidate_ids": [], "result_status": "abstention"}]}
    result = paired_metrics([], [manifest])
    assert result["excluded_pair_count"] == 1
    assert result["paired_runs"] == 0
    outcomes = result["operational_outcomes_all_assigned"]
    assert outcomes["sas2"]["assigned_runs"] == outcomes["mas"]["assigned_runs"] == 1
    assert outcomes["sas2"]["status_counts"]["technical_error"] == 1
