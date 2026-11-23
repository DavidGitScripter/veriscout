from pathlib import Path
"""P0-Nachweise: realistischer Positivpfad, Stufenbudget und Auswertung.

Die Tests verwenden ein Stub-Sprachmodell und gespeicherte Dokumenttexte.
Sie belegen, dass ein vollstaendig belegter Kandidat in BEIDEN Armen die
gesamte Kette bis zu einer positiven Entscheidung durchlaufen kann. Sie
sagen nichts ueber reale Trefferquoten aus.
"""
import json
import sys

import pytest

import evidence_resolver
from compare_architectures import (ComparisonTask, ExperimentBudget,
                                   PairedArchitectureRunner, assignment_manifest)
from core import Candidate, Config, LLMClient, Source
from evaluation_analysis import (annotation_template, cluster_bootstrap_interval,
                                 paired_metrics, paired_permutation_pvalue)
from evidence_resolver import _normalise_claim, excerpt_match
from memory import FeedbackMemory, MemoryStore
from pipeline import Pipeline
from resource_budget import ResourceBroker, ResourceLimits
from review_contract import apply_review, review_checklist

ORG = "Max Wild GmbH"
STARTUP = "MinerAlpha GmbH"
TARGET_URL = "https://www.maxwild.com/recycling"
OFFICIAL_URL = "https://www.mineralpha.de/produkt"
PRESS_URL = "https://www.startup-magazin-sued.de/mineralpha-gruendung"

DOCUMENTS = {
    TARGET_URL: (
        "<html><body><h1>Recycling</h1><p>Die Max Wild GmbH mit Sitz in Berkheim "
        "ist ein Familienunternehmen fuer Tiefbau, Abbruch und Recycling.</p>"
        "<p>Wir bereiten Bauschutt aus dem Tiefbau in eigenen Anlagen zu "
        "zertifizierten Recyclingbaustoffen auf.</p><p>Angenommen werden "
        "mineralische Bauabfaelle aus Abbruch und Tiefbau, etwa Beton und "
        "Ziegelbruch.</p></body></html>"),
    OFFICIAL_URL: (
        "<html><body><h1>MinerAlpha</h1><p>Die MinerAlpha GmbH entwickelt eine "
        "sensorgestuetzte Sortieranlage fuer mineralische Bauabfaelle.</p>"
        "<p>Unser Nahinfrarot-Sortierer trennt Beton, Ziegel und Gips "
        "sortenrein in Echtzeit.</p><p>Die sortenreinen Fraktionen werden als "
        "hochwertige Gesteinskoernung im Betonbau wiederverwendet.</p>"
        "</body></html>"),
    PRESS_URL: (
        "<html><body><p>Die MinerAlpha GmbH wurde 2021 in Ulm gegruendet und "
        "entwickelt Sortiertechnik fuer Bauabfaelle.</p></body></html>"),
    # R2 (11.11.2026): Impressum fuer Existenz und Sitz in DACH.
    "https://www.mineralpha.de/impressum": (
        "<html><body><h1>Impressum</h1><p>MinerAlpha GmbH, Donaustrasse 1, 89073 Ulm, "
        "Deutschland. Registergericht: Amtsgericht Ulm, HRB 765432.</p></body></html>"),
}


def _target_id(task: ComparisonTask) -> str:
    return task.public_input(strict=True).organization_id


def _stage1(target_id: str) -> str:
    def claim(cid, field, text, sid, excerpt, subject):
        item = {"claim_id": cid, "claim_text": text, "field": field,
                "source_id": sid, "excerpt": excerpt, "stance": "support"}
        if subject == "target":
            item.update(subject_type="target_organization",
                        subject_id=target_id, subject_name=ORG)
        else:
            item.update(subject_type="candidate_startup", subject_name=STARTUP)
        return item

    return json.dumps([{
        "name": STARTUP,
        "description": "Sensorgestuetzte Sortieranlage fuer mineralische Bauabfaelle",
        "founded": 2021, "region": "DE", "employees": None,
        "funding_stage": "", "company_type": "startup",
        "is_service_provider": False, "problem_fit": True,
        "website": "https://www.mineralpha.de", "sectors": ["Recycling"],
        "process_stage": "Aufbereitung von Bauschutt zu Recyclingbaustoffen",
        "input_stream": "Mineralische Bauabfaelle aus Abbruch und Tiefbau",
        "transformation": "Nahinfrarot-Sortierung nach Materialart",
        "output_application": "Sortenreine Gesteinskoernung fuer den Betonbau",
        "unresolved_requirements": [],
        "sources": [
            {"source_id": "s1", "url": TARGET_URL, "title": "Recycling",
             "source_type": "official", "subject_type": "target_organization",
             "subject_id": target_id, "subject_name": ORG,
             "excerpt": "Wir bereiten Bauschutt aus dem Tiefbau in eigenen Anlagen zu zertifizierten Recyclingbaustoffen auf",
             "supports": ["target_identity", "target_process"]},
            {"source_id": "s2", "url": OFFICIAL_URL, "title": "Produkt",
             "source_type": "official", "subject_type": "candidate_startup",
             "subject_name": STARTUP,
             "excerpt": "Die MinerAlpha GmbH entwickelt eine sensorgestuetzte Sortieranlage fuer mineralische Bauabfaelle",
             "supports": ["identity", "product"]},
            {"source_id": "s3", "url": PRESS_URL, "title": "Gruendung",
             "source_type": "press", "publisher": "Startup-Magazin Sued",
             "subject_type": "candidate_startup", "subject_name": STARTUP,
             "excerpt": "Die MinerAlpha GmbH wurde 2021 in Ulm gegruendet",
             "supports": ["identity", "founded"]},
        ],
        "evidence_claims": [
            claim("c1", "identity", "MinerAlpha ist ein reales Unternehmen", "s2",
                  "Die MinerAlpha GmbH entwickelt eine sensorgestuetzte Sortieranlage fuer mineralische Bauabfaelle", "startup"),
            claim("c2", "startup_status", "Startup, gegruendet 2021", "s3",
                  "Die MinerAlpha GmbH wurde 2021 in Ulm gegruendet", "startup"),
            claim("c3", "target_identity", "Max Wild GmbH in Berkheim", "s1",
                  "Die Max Wild GmbH mit Sitz in Berkheim ist ein Familienunternehmen fuer Tiefbau, Abbruch und Recycling", "target"),
            claim("c4", "target_process", "Aufbereitung von Bauschutt", "s1",
                  "Wir bereiten Bauschutt aus dem Tiefbau in eigenen Anlagen zu zertifizierten Recyclingbaustoffen auf", "target"),
            claim("c5", "input_stream", "Mineralische Bauabfaelle", "s1",
                  "Angenommen werden mineralische Bauabfaelle aus Abbruch und Tiefbau, etwa Beton und Ziegelbruch", "target"),
            claim("c6", "startup_capability", "Sensorgestuetzte Sortieranlage", "s2",
                  "Die MinerAlpha GmbH entwickelt eine sensorgestuetzte Sortieranlage fuer mineralische Bauabfaelle", "startup"),
            claim("c7", "transformation", "Nahinfrarot-Sortierung", "s2",
                  "Unser Nahinfrarot-Sortierer trennt Beton, Ziegel und Gips sortenrein in Echtzeit", "startup"),
            claim("c8", "output_application", "Gesteinskoernung fuer Betonbau", "s2",
                  "Die sortenreinen Fraktionen werden als hochwertige Gesteinskoernung im Betonbau wiederverwendet", "startup"),
        ],
    }], ensure_ascii=False)


def _review(user: str, *, with_sources: bool, target_id: str) -> str:
    marker = ("Zu pruefende Rohfunde:\n" if "Zu pruefende Rohfunde:\n" in user
              else "Pruefliste (identisch zum Vergleichsarm):\n")
    checklist = json.loads(user.split(marker, 1)[1])
    stage1 = {item["claim_id"]: item
              for item in json.loads(_stage1(target_id))[0]["evidence_claims"]}
    entries = []
    for entry in checklist:
        claims = []
        for item in entry["claims_to_verify"]:
            original = stage1.get(item["claim_id"])
            if original is None:
                continue
            claims.append({"claim_id": item["claim_id"], "stance": "support",
                           "source_id": original["source_id"],
                           "excerpt": original["excerpt"]})
        sources = []
        if with_sources:
            for source in json.loads(_stage1(target_id))[0]["sources"]:
                source = dict(source)
                source.pop("supports", None)
                sources.append(source)
        entries.append({
            "candidate_id": entry["candidate_id"], "verdict": "keep",
            "exists": True, "entity_type": "startup",
            "official_url": "https://www.mineralpha.de", "founded": 2021,
            "problem_fit": True, "operating_status": "active", "claims": claims, "sources": sources,
            "unresolved_requirements": []})
    return json.dumps(entries, ensure_ascii=False)


class ScriptedLLM(LLMClient):
    """Echter LLMClient (Grounding, Ledger, Broker), nur ohne Netzwerk."""

    def __init__(self, target_id: str, stage1_web_calls: int = 3):
        super().__init__(live=True)
        self.target_id = target_id
        self.stage1_web_calls = stage1_web_calls
        self.purposes = []

    def available(self):
        return True

    def complete(self, model, system, user, max_tokens=1024, tools=None,
                 max_tool_calls=None, purpose="", reasoning_effort=None):
        self.purposes.append(purpose)
        if self.resource_broker:
            allowed, reason = self.resource_broker.authorize_model_call(
                estimated_input_tokens=2000, max_output_tokens=int(max_tokens),
                max_web_calls=int(max_tool_calls or 0) if tools else 0,
                model=model, purpose=purpose)
            if not allowed:
                self.last_usage = {"status": "technical_failure", "purpose": purpose}
                self.usage_records.append(dict(self.last_usage))
                return ""
        citations = [{"url": url, "title": "", "origin": "web_search_source"}
                     for url in DOCUMENTS]
        if purpose.startswith(("sas2_research", "mas_scouting")):
            text, calls = _stage1(self.target_id), self.stage1_web_calls
        elif purpose == "mas_verification":
            text, calls = _review(user, with_sources=True,
                                  target_id=self.target_id), 3
        elif purpose == "sas2_self_review":
            text, calls, citations = _review(user, with_sources=False,
                                             target_id=self.target_id), 2, []
        elif purpose.startswith("follow_up"):
            # M2: Nachrecherche findet hier nichts (leeres Ergebnis).
            text, calls, citations = "[]", 1, []
        else:
            raise AssertionError(purpose)
        record = {"purpose": purpose, "status": "completed",
                  "model_requested": model, "model_returned": model,
                  "input_tokens": 30000, "cached_input_tokens": 0,
                  "output_tokens": 2500, "reasoning_tokens": 800,
                  "tool_calls": calls}
        self.last_usage = record
        self.last_citations = citations
        self.usage_records.append(record)
        if self.resource_broker:
            self.resource_broker.record_model_usage(record)
        return text


@pytest.fixture
def offline_documents(monkeypatch):
    def fake_fetch(self, url):
        if url in self.cache:
            return dict(self.cache[url])
        if self.resource_broker:
            allowed, reason = self.resource_broker.begin_resolver_fetch()
            if not allowed:
                return {"status": "not_checked_budget", "error": reason}
        raw = DOCUMENTS.get(url)
        if raw is None:
            result = {"status": "technical_error", "error": "HTTPError"}
        else:
            text = evidence_resolver._plain_text(raw.encode("utf-8"), "text/html")
            result = {"status": "resolved", "http_status": 200,
                      "resolved_url": url, "content_type": "text/html",
                      "content_hash": url, "text": text,
                      "text_hash": url}
        self.cache[url] = result
        return dict(result)
    monkeypatch.setattr(evidence_resolver.EvidenceResolver, "_fetch", fake_fetch)


def _runner(task: ComparisonTask, stage1_web_calls: int = 3):
    target_id = _target_id(task)

    class Runner(PairedArchitectureRunner):
        def _pipeline(self, broker):
            return Pipeline(
                live=True, memory=FeedbackMemory(MemoryStore(read_only=True)),
                llm=ScriptedLLM(target_id, stage1_web_calls),
                resource_broker=broker, audit_write=False,
                reasoning_effort=self.budget.reasoning_effort)

    return Runner(budget=ExperimentBudget(), live=True)


def _task() -> ComparisonTask:
    return ComparisonTask(
        task_id="p0-positive", organization_name=ORG,
        search_prompt=("Suche ein reales B2B-Startup, dessen Produkt die "
                       "oeffentlich belegte Aufbereitung mineralischer "
                       "Baustoffe der Zielorganisation effizienter machen koennte."),
        dataset_split="development")


# --- T1: Positivpfad in beiden Armen -------------------------------------

def test_fully_supported_candidate_reaches_positive_decision_in_both_arms(
        offline_documents):
    result = _runner(_task()).run_pair(_task())
    arms = {arm["architecture_internal"]: arm for arm in result["arms"]}
    for architecture in ("sas2", "mas"):
        arm = arms[architecture]
        assert arm["result_status"] == "completed", (
            architecture, arm["resource_usage"]["failure_reasons"],
            [d.get("evaluation_status") for d in arm["decisions"]])
        decision = arm["decisions"][0]
        matrix = decision["candidate"]["evidence_matrix"]
        assert matrix["decision_state"] == "fully_supported", matrix["blocking_dimensions"]
        assert decision["candidate"]["verification_status"] == "verified_startup"
        assert decision["recommendation"] == "Pilot"
    # Beide Arme verbrauchen genau zwei Modellaufrufe.
    assert all(arm["resource_usage"]["model_calls"] == 2 for arm in arms.values())


def test_unsupported_review_blocks_positive_decision(offline_documents, monkeypatch):
    """Ohne gestuetzte Claims der Pruefstufe darf kein Arm 'Pilot' liefern."""
    original = ScriptedLLM.complete

    def denying(self, model, system, user, **kwargs):
        text = original(self, model, system, user, **kwargs)
        if kwargs.get("purpose") in {"mas_verification", "sas2_self_review"}:
            data = json.loads(text)
            for entry in data:
                for claim in entry["claims"]:
                    claim["stance"] = "unknown"
            text = json.dumps(data)
        return text

    monkeypatch.setattr(ScriptedLLM, "complete", denying)
    result = _runner(_task()).run_pair(_task())
    for arm in result["arms"]:
        assert arm["result_status"] == "abstention"
        assert all(d["recommendation"] != "Pilot" for d in arm["decisions"])


# --- T2: Reservierte zweite Stufe ----------------------------------------

def test_stage_one_tool_overrun_does_not_block_reserved_second_stage(
        offline_documents):
    # Der Anbieter liefert in Stufe 1 eine Websuche mehr als zugeteilt (7 > 6).
    result = _runner(_task(), stage1_web_calls=7).run_pair(_task())
    for arm in result["arms"]:
        assert arm["resource_usage"]["model_calls"] == 2
        assert "provider_tool_overrun:stage_1" in arm["protocol_deviations"]
        assert arm["result_status"] == "completed"
        assert not arm["budget_violation"]


def test_strict_overrun_policy_restores_fail_closed_behaviour(
        offline_documents, monkeypatch):
    monkeypatch.setattr(Config, "EVAL_WEB_OVERRUN_POLICY", "fail")
    result = _runner(_task(), stage1_web_calls=7).run_pair(_task())
    for arm in result["arms"]:
        assert arm["result_status"] == "technical_error"


def test_stage_allocation_is_identical_and_sums_to_arm_budget():
    budget = ExperimentBudget()
    allocation = budget.stage_allocation()
    # Seit v14 (M2) gehoert die feste Nachrecherche als stage_3 dazu.
    limits = budget.resource_limits()
    assert sum(v["max_tool_calls"] for v in allocation.values()) == limits.max_web_calls
    assert sum(v["max_output_tokens"] for v in allocation.values()) == limits.max_output_tokens
    assert allocation["stage_1"] == allocation["stage_1"] and "stage_3" in allocation
    broker = ResourceBroker(budget.resource_limits())
    broker.reserve_stages(allocation)
    with pytest.raises(ValueError):
        broker.reserve_stages({"stage_1": {"max_output_tokens": 10**9,
                                           "max_tool_calls": 0}})


def test_default_budget_covers_observed_pilot_consumption():
    """Pilot 5.9.: bis 32.776 Input- und 6.000 Ausgabetokens je Aufruf."""
    budget = ExperimentBudget()
    assert budget.max_input_tokens >= 2 * 32_776
    assert budget.max_output_tokens // 2 >= 6_000
    price_in, price_out = Config.PRICES[budget.model]
    worst_case = (budget.max_input_tokens / 1e6 * price_in
                  + budget.max_output_tokens / 1e6 * price_out
                  + budget.max_tool_calls * Config.WEB_SEARCH_PRICE)
    # 12.11.2026 (Budgetprofil main-calibrated-2026-11-12, Entscheidung DS):
    # 12.000 Ausgabe-Tokens je Stufe bei unveraendertem Deckel 0,75 USD. Die
    # rechnerische Obergrenze (alle Grenzen gleichzeitig voll) wird offen
    # ausgewiesen: 0,76 USD, also 0,01 USD ueber dem Deckel.
    assert round(worst_case, 4) == 0.76
    # (a) Beobachteter Hoechstverbrauch im Vorlauf studie-2026-11-12-3ef90a4e
    # (18 Arme): teuerster Arm 0,534 USD, groesste Eingabe 161.825 Tokens.
    # Selbst diese Eingabe mit voll ausgeschoepfter neuer Ausgabegrenze und
    # allen Suchen liegt klar unter dem Deckel.
    observed_input = 161_825
    observed_projection = (observed_input / 1e6 * price_in
                           + budget.max_output_tokens / 1e6 * price_out
                           + budget.max_tool_calls * Config.WEB_SEARCH_PRICE)
    assert 0.534 < budget.max_cost_usd and observed_projection <= budget.max_cost_usd - 0.05
    # (c) Die Paar-Reserve im Stoppcheck je Modell deckt die wahre Obergrenze
    # eines Paars inklusive Nachrecherche: 2 Arme x (0,76 + Nachrecherche).
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import run_study
    follow_up_worst = (Config.FOLLOW_UP_MAX_INPUT_TOKENS / 1e6 * price_in
                       + (Config.FOLLOW_UP_MAX_OUTPUT_TOKENS + Config.FOLLOW_UP_MAX_REASONING_TOKENS)
                       / 1e6 * price_out
                       + Config.FOLLOW_UP_MAX_TOOL_CALLS * Config.WEB_SEARCH_PRICE)
    true_pair_worst = 2 * (worst_case + follow_up_worst)
    pair_reserve = round(budget.arm_max_cost_usd * 2, 4) + run_study.PAIR_OVERRUN_MARGIN_USD
    assert true_pair_worst <= pair_reserve
    # (b) Der Laufzeit-Stopp bei 0,75 USD je Arm (1,00 mit Nachrecherche)
    # bleibt und greift: siehe test_cost_guard_fails_closed_when_worst_case_exceeds_cap.
    assert budget.max_cost_usd == 0.75 and budget.arm_max_cost_usd == 1.0


def test_cost_guard_fails_closed_when_worst_case_exceeds_cap():
    """Die Kostenbremse laesst keinen Aufruf zu, dessen Hochrechnung den Deckel uebersteigt."""
    from resource_budget import ResourceBroker
    budget = ExperimentBudget()
    broker = ResourceBroker(budget.resource_limits())
    broker.reserve_stages(budget.stage_allocation())
    allowed, reason = broker.authorize_model_call(
        estimated_input_tokens=budget.max_input_tokens,
        max_output_tokens=10_000, max_web_calls=6,
        model=budget.model, purpose="sas2_research")
    assert allowed  # realistischer erster Aufruf passt
    broker.cost_usd = budget.arm_max_cost_usd - 0.05
    allowed, reason = broker.authorize_model_call(
        estimated_input_tokens=50_000, max_output_tokens=1_000, max_web_calls=0,
        model=budget.model, purpose="sas2_self_review")
    assert not allowed and reason == "projected_cost_budget_exhausted"


def test_main_budget_profile_2026_11_12():
    from core import Config
    budget = ExperimentBudget()
    assert Config.BUDGET_PROFILE_VERSION == "main-calibrated-2026-11-12"
    stages = budget.stage_allocation()
    assert stages["stage_1"]["max_output_tokens"] == 12_000
    assert stages["stage_2"]["max_output_tokens"] == 12_000
    assert stages["stage_3"]["max_output_tokens"] == 4_000
    assert budget.max_output_tokens == 24_000
    # unveraendert: Eingabe, Denk-Tokens, Tool-Aufrufe, Abrufe, Aufwand, Kosten
    assert budget.max_input_tokens == 200_000
    assert budget.max_tool_calls == 12 and budget.max_cost_usd == 0.75
    assert budget.reasoning_effort == "low"
    assert budget.arm_max_cost_usd == 1.0


# --- P0-3: kompakter Pruefvertrag ----------------------------------------

def test_compact_review_never_inherits_unsupported_stage_one_fields():
    candidate = Candidate(
        name=STARTUP, description="Behauptete Faehigkeit", discovery_mode="live",
        transformation="Behaupteter Mechanismus", website="https://www.mineralpha.de",
        evidence_claims=[
            {"claim_id": "c6", "field": "startup_capability", "claim_text": "x",
             "source_id": "s2", "excerpt": "a" * 30, "stance": "support",
             "subject_type": "candidate_startup", "subject_name": STARTUP},
            {"claim_id": "c7", "field": "transformation", "claim_text": "y",
             "source_id": "s2", "excerpt": "b" * 30, "stance": "support",
             "subject_type": "candidate_startup", "subject_name": STARTUP}])
    checklist = review_checklist(candidate)
    apply_review(candidate, checklist, {
        "candidate_id": checklist["candidate_id"], "verdict": "keep",
        "exists": True, "entity_type": "startup",
        "claims": [{"claim_id": "c6", "stance": "support", "source_id": "v1",
                    "excerpt": "Belegter Auszug zur Faehigkeit"},
                   # support ohne vorhandene Quelle wird zu unknown
                   {"claim_id": "c7", "stance": "support", "source_id": "missing",
                    "excerpt": "irgendetwas"}],
        "sources": [{"source_id": "v1", "url": OFFICIAL_URL,
                     "subject_type": "candidate_startup", "subject_name": STARTUP}],
    }, keep_stage1_sources=False)
    assert candidate.description == "Behauptete Faehigkeit"
    assert candidate.transformation == ""
    stances = {c["claim_id"]: c["stance"] for c in candidate.evidence_claims}
    assert stances == {"c6": "support", "c7": "unknown"}
    assert candidate.sources[0].supports == ["product"]


def test_drop_verdict_fails_closed():
    candidate = Candidate(name=STARTUP, description="x", discovery_mode="live",
                          website="https://www.mineralpha.de")
    checklist = review_checklist(candidate)
    apply_review(candidate, checklist, {"candidate_id": checklist["candidate_id"],
                                        "verdict": "drop"}, keep_stage1_sources=True)
    assert candidate.description == "" and candidate.sources == []


def test_both_review_stages_share_rules_and_output_contract():
    from agents import VerificationAgent
    from baselines import SelfReviewSingleAgent
    from review_contract import REVIEW_OUTPUT_SPEC, REVIEW_ROLE_COMMON
    for system in (VerificationAgent.SYSTEM, SelfReviewSingleAgent.REVIEW_SYSTEM):
        assert REVIEW_ROLE_COMMON in system and REVIEW_OUTPUT_SPEC in system


# --- T7: unscharfer Auszugsabgleich --------------------------------------

def test_fuzzy_excerpt_accepts_formatting_drift_but_not_shuffled_keywords():
    document = _normalise_claim(
        "Unser Nahinfrarot-Sortierer trennt Beton, Ziegel und Gips sortenrein "
        "in Echtzeit. Weitere Informationen folgen.")
    assert excerpt_match(_normalise_claim(
        "Unser Nahinfrarot-Sortierer trennt Beton, Ziegel und Gips sortenrein in Echtzeit"),
        document) == "exact"
    assert excerpt_match(_normalise_claim(
        "Unser Nahinfrarot Sortierer trennt Beton Ziegel Gips sortenrein in Echtzeit"),
        document) == "fuzzy"
    assert excerpt_match(_normalise_claim(
        "Echtzeit Gips Ziegel Beton trennt sortenrein Sortierer Nahinfrarot unser"),
        document) == ""
    assert excerpt_match(_normalise_claim(
        "Unser Verfahren recycelt Kunststoffverpackungen chemisch zu neuem Granulat"),
        document) == ""


def test_exact_mode_keeps_previous_strict_behaviour(monkeypatch):
    monkeypatch.setattr(Config, "EXCERPT_MATCH_MODE", "exact")
    document = _normalise_claim("Unser Nahinfrarot-Sortierer trennt Beton, Ziegel und Gips")
    assert excerpt_match(_normalise_claim(
        "Unser Nahinfrarot Sortierer trennt Beton Ziegel und Gips"), document) == "exact"
    assert excerpt_match(_normalise_claim(
        "Unser Sortierer trennt Beton Ziegel und Gips"), document) == ""


# --- T3/T4/T5/T6: Auswertung ---------------------------------------------

def _manifest(pair, task, sas_status, mas_status, sas_ids=(), mas_ids=()):
    def arm(arch, status, ids):
        return {"architecture": arch, "blind_arm_id": f"{pair}-{arch}",
                "returned_candidates": len(ids),
                "expected_candidate_ids": list(ids), "result_status": status,
                "primary_analysis_eligible": status in {"completed", "abstention"}}
    return {"schema_version": "venture-scout-assignment-v2", "pair_id": pair,
            "task_id": task, "assignments": [arm("sas2", sas_status, sas_ids),
                                             arm("mas", mas_status, mas_ids)]}


def _rows(pair, task, arch, cid, qualified):
    row = {"schema_version": "venture-scout-annotation-v1", "pair_id": pair,
           "task_id": task, "blind_arm_id": f"{pair}-{arch}",
           "candidate_id": cid, "candidate_rank": 1, "adjudication": {},
           "qualified": qualified, "valid_entity": True,
           "relation_correct": qualified, "claim_support_complete": qualified,
           "over_match": not qualified}
    return [dict(row, rater_id="rater-1"), dict(row, rater_id="rater-2")]


def test_itt_counts_technical_failures_as_zero_and_keeps_pair():
    manifests = [_manifest("p1", "t1", "technical_error", "completed",
                           mas_ids=["c-1"])]
    rows = _rows("p1", "t1", "mas", "c-1", True)
    result = paired_metrics(rows, manifests)
    itt = result["primary_itt"]
    assert result["primary_estimand"].startswith("itt")
    assert itt["assigned_pairs"] == 1
    assert itt["mean_success"] == {"sas2": 0.0, "mas": 1.0}
    assert itt["task_differences_mas_minus_sas"]["t1"]["qualified_hit_at_5"] == 1.0
    # Sekundaeranalyse schliesst dasselbe Paar weiterhin aus.
    assert result["excluded_pair_count"] == 1 and result["paired_runs"] == 0


def test_all_replicates_success_differs_from_mean_success():
    manifests, rows = [], []
    for index, hit in enumerate((True, True, False), start=1):
        pair = f"r{index}"
        manifests.append(_manifest(pair, "t1", "completed", "completed",
                                   ["s"], ["m"]))
        rows += _rows(pair, "t1", "sas2", "s", hit)
        rows += _rows(pair, "t1", "mas", "m", True)
    itt = paired_metrics(rows, manifests)["primary_itt"]
    assert itt["mean_success"]["sas2"] == pytest.approx(2 / 3)
    assert itt["all_replicates_success"] == {"sas2": 0.0, "mas": 1.0}
    assert itt["task_sign_tally"] == {"mas_better": 1, "equal": 0, "sas2_better": 0}


def test_permutation_and_bootstrap_on_known_values():
    zeros = {f"t{i}": {"m": 0.0} for i in range(5)}
    assert paired_permutation_pvalue(zeros, "m")["p_value"] == 1.0
    positive = {f"t{i}": {"m": 1.0} for i in range(5)}
    assert paired_permutation_pvalue(positive, "m")["p_value"] == pytest.approx(1 / 32)
    interval = cluster_bootstrap_interval(positive, "m", resamples=500)
    assert interval["estimate"] == 1.0 and interval["ci95"] == [1.0, 1.0]


# --- Stand 16.10.2026: Zielzustaende, Sensitivitaeten, Bayes, H3 ------------

def test_positive_run_reports_unified_state_mechanics_and_sensitivities(
        offline_documents):
    result = _runner(_task()).run_pair(_task())
    for arm in result["arms"]:
        assert arm["decision_states"] == ["empfehlung"]
        assert arm["positive_candidate_ids"]
        assert arm["review_mechanics"]["claims_stage_1"] == 8
        assert arm["review_mechanics"]["claims_supported_stage_2"] == 8
        assert arm["sensitivity"]["exact_excerpt"]["result_status"] == "completed"
    mas = [a for a in result["arms"] if a["architecture_internal"] == "mas"][0]
    assert mas["sensitivity"]["mas_scout_sources"]["positive_candidate_ids"]
    manifest = assignment_manifest(result)
    assert all("positive_candidate_ids" in item for item in manifest["assignments"])


def test_unsupported_review_yields_abstention_state(offline_documents, monkeypatch):
    original = ScriptedLLM.complete

    def denying(self, model, system, user, **kwargs):
        text = original(self, model, system, user, **kwargs)
        if kwargs.get("purpose") in {"mas_verification", "sas2_self_review"}:
            data = json.loads(text)
            for entry in data:
                for claim in entry["claims"]:
                    claim["stance"] = "unknown"
            text = json.dumps(data)
        return text

    monkeypatch.setattr(ScriptedLLM, "complete", denying)
    result = _runner(_task()).run_pair(_task())
    mas = [a for a in result["arms"] if a["architecture_internal"] == "mas"][0]
    assert mas["decision_states"] == ["enthaltung"]
    # Sensitivitaet: Scout-Quellen zaehlen, wenn der Verifier nicht widerlegt.
    assert mas["sensitivity"]["mas_scout_sources"]["decision_states"] == ["empfehlung"]


def test_contradiction_yields_rejection_state(offline_documents, monkeypatch):
    original = ScriptedLLM.complete

    def contradicting(self, model, system, user, **kwargs):
        text = original(self, model, system, user, **kwargs)
        if kwargs.get("purpose") in {"mas_verification", "sas2_self_review"}:
            data = json.loads(text)
            for entry in data:
                entry["claims"][6]["stance"] = "contradict"  # transformation
            text = json.dumps(data)
        return text

    monkeypatch.setattr(ScriptedLLM, "complete", contradicting)
    result = _runner(_task()).run_pair(_task())
    for arm in result["arms"]:
        assert arm["decision_states"] == ["ablehnung"]
        assert arm["review_mechanics"]["claims_contradicted_stage_2"] == 1


def _manifest_v3(pair, task, sas, mas):
    def arm(arch, spec):
        status, ids, positives = spec
        return {"architecture": arch, "blind_arm_id": f"{pair}-{arch}",
                "returned_candidates": len(ids), "expected_candidate_ids": ids,
                "result_status": status,
                "primary_analysis_eligible": status in {"completed", "abstention"},
                "positive_candidate_ids": positives}
    return {"schema_version": "venture-scout-assignment-v2", "pair_id": pair,
            "task_id": task, "assignments": [arm("sas2", sas), arm("mas", mas)]}


def test_abstention_with_qualified_candidate_scores_zero():
    manifests = [_manifest_v3("p1", "t1", ("abstention", ["s"], []),
                              ("completed", ["m"], ["m"]))]
    rows = _rows("p1", "t1", "sas2", "s", True) + _rows("p1", "t1", "mas", "m", True)
    itt = paired_metrics(rows, manifests)["primary_itt"]
    assert itt["mean_success"] == {"sas2": 0.0, "mas": 1.0}
    assert itt["positive_ids_source"] == "system_recommendations"
    assert itt["precision_of_recommendations"] == {"sas2": None, "mas": 1.0}


def test_bayesian_interval_widens_for_few_tasks_and_detects_clear_effect():
    from evaluation_analysis import bayesian_paired_difference
    small = {"task_successes": {"t1": {"sas2": [0, 1], "mas": [1, 1]}}}
    wide = bayesian_paired_difference(small, draws=4000)
    assert wide["difference_mas_minus_sas"]["ci95"][0] < 0
    assert wide["h1_supported"] is False
    many = {"task_successes": {f"t{i}": {"sas2": [0, 3], "mas": [3, 3]}
                               for i in range(12)},
            "precision_counts": {f"t{i}": {"sas2": [1, 3], "mas": [3, 3]}
                                 for i in range(12)}}
    clear = bayesian_paired_difference(many, draws=4000)
    assert clear["difference_mas_minus_sas"]["ci95"][0] > 0.3
    assert clear["h1_supported"] is True
    assert clear["h2_noninferior"] is True
    assert clear["ni_margin_precision"] == pytest.approx(-0.10)


def test_strict_web_sensitivity_counts_overrun_arm_as_zero():
    manifest = _manifest_v3("p1", "t1", ("completed", ["s"], ["s"]),
                            ("completed", ["m"], ["m"]))
    manifest["assignments"][1]["protocol_deviations"] = ["provider_tool_overrun:stage_1"]
    rows = _rows("p1", "t1", "sas2", "s", True) + _rows("p1", "t1", "mas", "m", True)
    itt = paired_metrics(rows, [manifest])["primary_itt"]
    assert itt["mean_success"]["mas"] == 1.0
    assert itt["sensitivity"]["strict_web"]["mean_success"]["mas"] == 0.0


def test_blind_package_order_is_shuffled():
    from compare_architectures import annotation_package
    result = {"pair_id": "p", "task": {"task_id": "t"},
              "arms": [{"blind_arm_id": "first", "decisions": []},
                       {"blind_arm_id": "second", "decisions": []}]}
    orders = {tuple(arm["blind_arm_id"] for arm in annotation_package(result)["arms"])
              for _ in range(60)}
    assert len(orders) == 2


# --- PUSH/PULL (Kap. 5.2, 6.1) --------------------------------------------

def test_push_and_pull_produce_distinct_identical_for_both_arms_prompts():
    from experiment_protocol import PublicSearchField, PublicSearchTaskInput, stable_organization_id
    org_id = stable_organization_id("Max Wild GmbH")
    base = dict(task_id="t", organization_id=org_id, organization_name="Max Wild GmbH",
                search_field=PublicSearchField.from_prompt(
                    "Suche ein reales B2B-Startup fuer die Aufbereitung mineralischer Baustoffe."))
    push = PublicSearchTaskInput(**base)
    pull = PublicSearchTaskInput(**base, search_mode="pull",
                                 search_area="Recycling mineralischer Baustoffe im Tiefbau")
    assert push.prompt().startswith("PUBLIC-ONLY PUSH-SUCHAUFTRAG")
    assert "Auftragsart PUSH" in push.prompt()
    assert pull.prompt().startswith("PUBLIC-ONLY PULL-SUCHAUFTRAG")
    assert "Recycling mineralischer Baustoffe im Tiefbau" in pull.prompt()
    assert push.input_hash() != pull.input_hash()
    with pytest.raises(ValueError):
        PublicSearchTaskInput(**base, search_mode="pull").validate()
    with pytest.raises(ValueError):
        PublicSearchTaskInput(**base, search_mode="push", search_area="x y z").validate()


def test_pull_task_reaches_both_arms_unchanged(offline_documents):
    task = ComparisonTask(
        task_id="p0-pull", organization_name=ORG,
        search_prompt=("Suche ein reales B2B-Startup, dessen Produkt die "
                       "oeffentlich belegte Aufbereitung mineralischer "
                       "Baustoffe der Zielorganisation effizienter machen koennte."),
        dataset_split="development", search_mode="pull",
        search_area="Recycling mineralischer Baustoffe")
    result = _runner(task).run_pair(task)
    assert result["task"]["search_mode"] == "pull"
    assert result["task"]["search_area"] == "Recycling mineralischer Baustoffe"
    assert {arm["prompt_hash"] for arm in result["arms"]} == {result["prompt_hash"]}


# --- Fortbestand des Startups (16./18.10.2026) -----------------------------

ACQUISITION_URL = "https://www.bauwirtschaft-news.de/mineralpha-uebernommen"


def test_acquired_startup_is_rejected_in_both_arms(offline_documents, monkeypatch):
    DOCUMENTS[ACQUISITION_URL] = ("<html><body><p>Die MinerAlpha GmbH wurde im Juni "
                                  "2026 vollstaendig von einem Baustoffkonzern "
                                  "uebernommen und als Geschaeftsbereich integriert."
                                  "</p></body></html>")
    original = ScriptedLLM.complete

    def acquired(self, model, system, user, **kwargs):
        text = original(self, model, system, user, **kwargs)
        if kwargs.get("purpose") in {"mas_verification", "sas2_self_review"}:
            data = json.loads(text)
            for entry in data:
                entry["operating_status"] = "acquired"
                entry["operating_evidence"] = {
                    "source_id": "s4",
                    "excerpt": "Die MinerAlpha GmbH wurde im Juni 2026 vollstaendig "
                               "von einem Baustoffkonzern uebernommen"}
                entry["sources"].append({
                    "source_id": "s4", "url": ACQUISITION_URL, "title": "Uebernahme",
                    "source_type": "press", "subject_type": "candidate_startup",
                    "subject_name": STARTUP})
            text = json.dumps(data)
            self.last_citations = list(self.last_citations) + [
                {"url": ACQUISITION_URL, "title": "", "origin": "web_search_source"}]
        return text

    monkeypatch.setattr(ScriptedLLM, "complete", acquired)
    try:
        result = _runner(_task()).run_pair(_task())
    finally:
        DOCUMENTS.pop(ACQUISITION_URL, None)
    for arm in result["arms"]:
        assert arm["decision_states"] == ["ablehnung"], arm["architecture_internal"]


def _with_operating_status(monkeypatch, status):
    original = ScriptedLLM.complete

    def patched(self, model, system, user, **kwargs):
        text = original(self, model, system, user, **kwargs)
        if kwargs.get("purpose") in {"mas_verification", "sas2_self_review"}:
            data = json.loads(text)
            for entry in data:
                entry["operating_status"] = status
            text = json.dumps(data)
        return text

    monkeypatch.setattr(ScriptedLLM, "complete", patched)


def test_unknown_operating_status_becomes_active_only_by_rule_m5(offline_documents, monkeypatch):
    # M5 (12.11.2026): Website erreichbar, Impressum mit Firmenname geprueft,
    # kein Gegenbeleg -> Fortbestand aktiv, mit kenntlicher Herkunft.
    _with_operating_status(monkeypatch, "unknown")
    result = _runner(_task()).run_pair(_task())
    for arm in result["arms"]:
        assert arm["decision_states"] == ["empfehlung"]
        candidate = arm["decisions"][0]["candidate"]
        assert candidate["operating_status"] == "active"
        assert candidate["operating_status_basis"].startswith("Regel M5")


def test_unknown_operating_status_without_imprint_blocks(offline_documents, monkeypatch):
    _with_operating_status(monkeypatch, "unknown")
    monkeypatch.delitem(DOCUMENTS, "https://www.mineralpha.de/impressum")
    result = _runner(_task()).run_pair(_task())
    for arm in result["arms"]:
        assert arm["decision_states"] != ["empfehlung"]


def test_negative_operating_status_is_never_overwritten(offline_documents, monkeypatch):
    from evidence_resolver import apply_operating_rule
    from core import Candidate
    c = Candidate(name="A", description="x", operating_status="insolvent")
    c.impressum = {"url": "https://a.example/impressum", "company_name_found": True, "register": "HRB 1"}
    apply_operating_rule(c)
    assert c.operating_status == "insolvent"


# --- Abgeleiteter Inputstrom (19.10.2026) ---------------------------------

MECHANISM_URL = "https://www.baustoff-fachwissen.de/aufbereitung-bauschutt"


def _derived_stage1(with_mechanism: bool):
    original = _stage1

    def build(target_id: str) -> str:
        data = json.loads(original(target_id))
        entry = data[0]
        for claim in entry["evidence_claims"]:
            if claim["claim_id"] == "c5":
                # Praemisse: belegter Prozessschritt statt direkt benanntem Strom.
                claim.update(basis="derived", source_id="s1",
                             claim_text="Bei der Aufbereitung von Bauschutt entsteht ein Reststrom",
                             excerpt="Wir bereiten Bauschutt aus dem Tiefbau in eigenen Anlagen "
                                     "zu zertifizierten Recyclingbaustoffen auf")
        if with_mechanism:
            entry["sources"].append({
                "source_id": "s5", "url": MECHANISM_URL, "title": "Fachwissen",
                "source_type": "press", "subject_type": "relation",
                "subject_name": "Bauschuttaufbereitung",
                "excerpt": "Bei der Aufbereitung von Bauschutt in Brech- und Siebanlagen "
                           "fallen feinkoernige Brechsande als Reststrom an"})
            entry["evidence_claims"].append({
                "claim_id": "c9", "field": "input_stream_mechanism", "basis": "derived",
                "claim_text": "Bauschuttaufbereitung erzeugt feinkoernige Brechsande",
                "source_id": "s5", "stance": "support",
                "excerpt": "Bei der Aufbereitung von Bauschutt in Brech- und Siebanlagen "
                           "fallen feinkoernige Brechsande als Reststrom an",
                "subject_type": "relation", "subject_name": "Bauschuttaufbereitung"})
        return json.dumps(data, ensure_ascii=False)
    return build


@pytest.mark.parametrize("with_mechanism, expected", [
    (True, "empfehlung"), (False, "enthaltung")])
def test_derived_input_stream_needs_process_and_mechanism_evidence(
        offline_documents, monkeypatch, with_mechanism, expected):
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "_stage1", _derived_stage1(with_mechanism))
    monkeypatch.setitem(DOCUMENTS, MECHANISM_URL, (
        "<html><body><p>Bei der Aufbereitung von Bauschutt in Brech- und "
        "Siebanlagen fallen feinkoernige Brechsande als Reststrom an.</p>"
        "</body></html>"))
    result = _runner(_task()).run_pair(_task())
    for arm in result["arms"]:
        assert arm["decision_states"] == [expected], arm["architecture_internal"]
        cells = {cell["dimension"]: cell for cell in
                 arm["decisions"][0]["candidate"]["evidence_matrix"]["cells"]}
        if with_mechanism:
            assert cells["input_stream"]["basis"] == "derived"
            assert "abgeleitet" in arm["decisions"][0]["decision_state_reason"]
        else:
            assert cells["input_stream"]["status"] != "supported"


# --- Unterseiten derselben Website (20.10.2026) ------------------------------

def test_excerpt_is_found_on_same_site_subpage(monkeypatch):
    from evidence_resolver import EvidenceResolver, _same_site_links
    home = "https://www.example-startup.de/"
    links = _same_site_links(
        '<a href="/ueber-uns">Ueber</a><a href="https://other.org/x">X</a>'
        '<a href="/bild.png">B</a><a href="/technologie#a">T</a>', home)
    assert links == ["https://www.example-startup.de/ueber-uns",
                     "https://www.example-startup.de/technologie"]
    resolver = EvidenceResolver()
    resolver.cache[home] = {"status": "resolved", "text": "Willkommen", "links": links}
    pages = {"https://www.example-startup.de/ueber-uns": "Wir sind ein Team.",
             "https://www.example-startup.de/technologie":
                 "Unser Verfahren trennt Keramik und Naturstein sortenrein fuer neue Baustoffe."}

    def fetch(self, url):
        result = {"status": "resolved", "text": pages.get(url, "")}
        self.cache[url] = result
        return dict(result)

    monkeypatch.setattr(EvidenceResolver, "_fetch", fetch)
    found = resolver._subpage_match(
        home, "Unser Verfahren trennt Keramik und Naturstein sortenrein fuer neue Baustoffe")
    assert found == "https://www.example-startup.de/technologie"
    assert resolver._subpage_match(home, "Ein Satz, der auf keiner Unterseite der Website steht") == ""
