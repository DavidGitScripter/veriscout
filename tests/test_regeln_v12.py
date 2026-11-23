"""Regeln v12 vom 11.11.2026: R1 Region, R2 Impressum, R3 Gruendung/Alter, R4 Kette."""
import pytest

import evidence_resolver
from core import Candidate, Config
from entity_verifier import EntityVerifier, reference_year
from test_entity_verifier import source


def _startup(founded=2022, impressum=None, extra_sources=()):
    candidate = Candidate(
        name="Kreislauf Technik GmbH", description="Sortiert mineralische Reststoffe",
        founded=founded, company_type="startup", discovery_mode="live",
        website="https://kreislauf-technik.de",
        sources=[source("https://kreislauf-technik.de/produkt", "official", ["identity", "product"],
                        f"Die Kreislauf Technik GmbH wurde {founded} gegründet und sortiert Bauschutt.",
                        True, "Kreislauf Technik GmbH"), *extra_sources])
    if impressum is not None:
        candidate.impressum = impressum
    return candidate


def _imp(country="DE", register="Amtsgericht Stuttgart HRB 783981"):
    return {"url": "https://kreislauf-technik.de/impressum", "company_name_found": True,
            "register": register, "country": country}


@pytest.mark.parametrize("text,country", [
    ("Kreislauf Technik GmbH, Hauptstr. 1, 72072 Tübingen. Registergericht: Amtsgericht Stuttgart, HRB 783981", "DE"),
    ("Kreislauf Technik GmbH, 1010 Wien. Firmenbuchnummer FN 123456a, Handelsgericht Wien", "AT"),
    ("Kreislauf Technik AG, 8000 Zürich, UID CHE-123.456.789", "CH"),
])
def test_r2_parse_impressum_finds_register_and_country(text, country):
    parsed = evidence_resolver.parse_impressum(text, "Kreislauf Technik GmbH")
    assert parsed["company_name_found"] and parsed["register"] and parsed["country"] == country


def test_r2_parse_impressum_marks_foreign_seat():
    parsed = evidence_resolver.parse_impressum(
        "Kreislauf Technik Ltd, 10 Downing Street, London, United Kingdom", "Kreislauf Technik Ltd")
    assert parsed["country"] == "outside_dach" and not parsed["register"]


def test_r2_impressum_replaces_independent_source():
    result = EntityVerifier().verify(_startup(impressum=_imp()))
    assert result.status == "verified_startup", result.reasons


def test_r2_without_impressum_independent_source_is_still_required():
    result = EntityVerifier().verify(_startup())
    assert "kein unabhaengiger Existenz- oder Gruendungsbeleg" in result.reasons


def test_r1_seat_not_evidenced_is_abstention_not_exclusion():
    result = EntityVerifier().verify(_startup(impressum={**_imp(), "country": ""}))
    assert "Sitz in Deutschland, Oesterreich oder der Schweiz nicht belegt" in result.reasons
    assert result.status == "needs_evidence"


def test_r1_seat_outside_dach_is_exclusion():
    result = EntityVerifier().verify(_startup(impressum=_imp(country="outside_dach")))
    assert any(r.startswith("Ausschluss: Sitz nicht in") for r in result.reasons)
    assert result.status == "not_a_startup"


def test_r1_foreign_seat_in_own_imprint_without_register_is_exclusion():
    # ArcNC-Fall: eigenes Imprint nennt Belgien, kein DACH-Registermerkmal.
    result = EntityVerifier().verify(_startup(impressum=_imp(country="outside_dach", register="")))
    assert any(r.startswith("Ausschluss: Sitz nicht in") for r in result.reasons)
    assert result.status == "not_a_startup"


def test_r1_foreign_seat_on_other_site_is_not_exclusion():
    imp = {**_imp(country="outside_dach", register=""), "url": "https://andere-seite.example/imprint"}
    result = EntityVerifier().verify(_startup(impressum=imp))
    assert not any(r.startswith("Ausschluss: Sitz") for r in result.reasons)
    assert "Sitz in Deutschland, Oesterreich oder der Schweiz nicht belegt" in result.reasons


def test_r1_dach_word_without_register_is_not_enough():
    result = EntityVerifier().verify(_startup(impressum=_imp(country="DE", register="")))
    assert "Sitz in Deutschland, Oesterreich oder der Schweiz nicht belegt" in result.reasons


def test_r3_older_than_ten_years_is_excluded_and_founding_from_own_site_counts():
    year = reference_year()
    ok = EntityVerifier().verify(_startup(founded=year - 10, impressum=_imp()))
    assert ok.status == "verified_startup", ok.reasons
    old = EntityVerifier().verify(_startup(founded=year - 11, impressum=_imp()))
    assert "Ausschluss: aelter als zehn Jahre (kein Startup mehr)" in old.reasons


def test_r3_scaleup_is_excluded():
    candidate = _startup(impressum=_imp())
    candidate.company_type = "scaleup"
    result = EntityVerifier().verify(candidate)
    assert "Ausschluss: Scale-up, kein Startup" in result.reasons


def test_r1_r3_exclusion_leads_to_rejection_state():
    from pipeline import Pipeline
    candidate = _startup(impressum=_imp(country="outside_dach"))
    EntityVerifier().verify(candidate)
    state, reason = Pipeline._decision_state(candidate, type("M", (), {"contradictions": []})(),
                                              type("D", (), {"evaluation_status": "abstention"})())
    assert state == "ablehnung" and "Sitz nicht in" in reason


def test_r2_qg1_accepts_impressum():
    from quality_gates import QualityGateEvaluator
    from core import Recommendation
    candidate = _startup(impressum=_imp())
    decision = type("D", (), {"candidate": candidate, "confidence": 0.0, "confidence_is_calibrated": False,
                              "recommendation": list(Recommendation)[0], "abstained": True})()
    gates = {g.gate_id: g for g in QualityGateEvaluator().evaluate(decision)}
    assert gates["QG1_INDEPENDENT_EVIDENCE"].passed


def test_r2_resolver_fetches_impressum_within_budget(monkeypatch):
    calls = []

    def fake_fetch(self, url):
        calls.append(url)
        if url.endswith("/impressum"):
            return {"status": "resolved", "resolved_url": url,
                    "text": "Kreislauf Technik GmbH, 72072 Tübingen. Amtsgericht Stuttgart HRB 783981"}
        return {"status": "technical_error"}
    monkeypatch.setattr(evidence_resolver.EvidenceResolver, "_fetch", fake_fetch)
    candidate = _startup()
    candidate.sources = []
    evidence_resolver.EvidenceResolver().resolve_candidates([candidate], max_fetches_total=2)
    assert candidate.impressum["register"] and candidate.impressum["country"] == "DE"
    assert len(calls) <= 2
    candidate2 = _startup(); candidate2.sources = []
    calls.clear()
    evidence_resolver.EvidenceResolver().resolve_candidates([candidate2], max_fetches_total=0)
    assert calls == [] and not candidate2.impressum


def test_v12_prompt_rules():
    from agents import ScoutingAgent
    assert "Nur Startups mit Sitz in Deutschland, Oesterreich oder der Schweiz" in ScoutingAgent.SYSTEM
    assert "mehr als zehn Jahre alt" in ScoutingAgent.SYSTEM
    assert "-v17-" in Config.PROMPT_CONTRACT_VERSION


# --- R4 Kette -------------------------------------------------------------
import copy
from test_evidence_matrix import native_source
from evidence_matrix import EvidenceMatrixBuilder

_TECH = "https://mineral-loop.de/technology"
_EXCERPT = "Mineral Loop bereitet mineralische Reststoffe auf und bindet sie zu Formsteinen."


def _chain_case(with_process=True, with_target_input=False, with_startup_input=True):
    claims = [
        {"claim_text": "Aufbereitung und Bindung zu einem Formstein", "field": "transformation",
         "source_url": _TECH, "excerpt": _EXCERPT, "stance": "support",
         "subject_type": "candidate_startup", "subject_name": "Mineral Loop GmbH"},
        {"claim_text": "Baustoff fuer den Hausbau", "field": "output_application",
         "source_url": _TECH, "excerpt": _EXCERPT, "stance": "support",
         "subject_type": "candidate_startup", "subject_name": "Mineral Loop GmbH"},
    ]
    if with_startup_input:
        claims.append({"claim_text": "Das Produkt verarbeitet mineralische Bearbeitungsreste",
                       "field": "input_stream_mechanism", "source_url": _TECH, "excerpt": _EXCERPT,
                       "stance": "support", "subject_type": "candidate_startup",
                       "subject_name": "Mineral Loop GmbH"})
    candidate = Candidate(
        name="Mineral Loop GmbH", description="Verarbeitet mineralische Reststoffe", founded=2025,
        company_type="startup", discovery_mode="live", operating_status="active",
        verification_status="verified_startup", official_url="https://mineral-loop.de",
        target_actor_id="demo_manufacturing", opportunity_id="opp-1",
        process_stage="Wasserstrahlbearbeitung", input_stream="mineralischer Bearbeitungsrest",
        transformation="Aufbereitung und Bindung zu einem Formstein",
        output_application="Baustoff fuer den Hausbau", evidence_claims=claims,
        sources=[native_source(_TECH, "official", ["identity", "product"], _EXCERPT,
                               subject_name="Mineral Loop GmbH"),
                 native_source("https://register.example.org/mineral-loop", "register",
                               ["identity", "founded"],
                               "Die Mineral Loop GmbH wurde im Jahr 2025 als Gesellschaft eingetragen.",
                               subject_name="Mineral Loop GmbH")])
    evidence = [{"field": "target_identity", "claim_text": "Die Zielorganisation ist eindeutig identifiziert.",
                 "excerpt": "Die offizielle Website weist die Zielorganisation eindeutig aus.",
                 "subject_type": "target_organization", "subject_id": "demo_manufacturing"}]
    if with_process:
        evidence.append({"profile_field": "Wasserstrahlbearbeitung Prozess",
                         "excerpt": "Die Zielorganisation beschreibt diesen Bearbeitungsschritt öffentlich.",
                         "subject_type": "target_organization", "subject_id": "demo_manufacturing"})
    if with_target_input:
        evidence.append({"field": "input_stream", "claim_text": "mineralischer Bearbeitungsrest",
                         "excerpt": "Die Zielorganisation nennt mineralische Bearbeitungsreste als Inputstrom.",
                         "subject_type": "target_organization", "subject_id": "demo_manufacturing"})
    target = [{"document_id": "SYN-DEMO-001", "url": "https://demo-manufacturing.example/process",
               "evidence": evidence, "subject_type": "target_organization",
               "subject_id": "demo_manufacturing"}]
    return EvidenceMatrixBuilder().build(candidate, target)


def _cells(matrix):
    return {cell.dimension: cell for cell in matrix.cells}


def test_r4_input_derived_from_process_and_startup_source():
    matrix = _chain_case(with_process=True, with_target_input=False, with_startup_input=True)
    cells = _cells(matrix)
    assert cells["input_stream"].status.value == "supported" and cells["input_stream"].basis == "derived"
    assert cells["transformation"].basis == "derived" and cells["output_application"].basis == "derived"
    assert matrix.decision_state == "fully_supported"


def test_r4_without_target_process_chain_stays_open():
    matrix = _chain_case(with_process=False, with_target_input=False, with_startup_input=True)
    cells = _cells(matrix)
    assert cells["input_stream"].status.value != "supported"
    assert cells["transformation"].status.value == "partial"
    assert matrix.decision_state == "incomplete"


def test_r4_without_input_evidence_input_stays_open():
    matrix = _chain_case(with_process=True, with_target_input=False, with_startup_input=False)
    assert _cells(matrix)["input_stream"].status.value != "supported"
    assert matrix.decision_state == "incomplete"


# --- R5 Darstellung ---------------------------------------------------------
def test_r5_recommendation_names_derived_links():
    from pipeline import Pipeline
    matrix = _chain_case(with_process=True, with_target_input=False, with_startup_input=True)
    cand = type("C", (), {"verification_reasons": [], "company_type": "startup"})()
    decision = type("D", (), {"evaluation_status": "completed", "abstained": False,
                              "operationally_eligible": True})()
    state, reason = Pipeline._decision_state(cand, matrix, decision)
    assert state == "empfehlung"
    assert reason.startswith("Empfehlung; Input, Wirkung und Ergebnis abgeleitet")


def test_r5_chain_basis_for_rating_sheet():
    import rating_panel as rp
    view = {"matrix": [{"dimension": "target_process", "status": "supported", "basis": "direct"},
                       {"dimension": "input_stream", "status": "supported", "basis": "derived"},
                       {"dimension": "startup_capability", "status": "supported", "basis": "direct"},
                       {"dimension": "transformation", "status": "supported", "basis": "derived"},
                       {"dimension": "output_application", "status": "partial", "basis": "direct"}]}
    assert rp._chain_basis(view) == {"process": "belegt", "input": "abgeleitet",
                                     "capability": "Fähigkeit belegt · Wirkung abgeleitet",
                                     "result": "ohne Beleg"}
    assert "Abgeleitete Glieder sind Schlussfolgerungen des Systems" in rp.CODEBOOK["f3"]["help"]


def test_r2_impressum_supports_identity_cell_in_matrix():
    from evidence_matrix import EvidenceMatrixBuilder, EvidenceStatus
    def bare(impressum):
        candidate = _startup(impressum=impressum)
        candidate.sources = []  # kein Modellbeleg fuer die Identitaet
        return next(c for c in EvidenceMatrixBuilder().build(candidate).cells if c.dimension == "identity")
    cell = bare({**_imp(), "excerpt": "Kreislauf Technik GmbH, Amtsgericht Stuttgart HRB 783981"})
    assert cell.status == EvidenceStatus.SUPPORTED and "impressum" in cell.source_ids
    cell = bare({**_imp(), "url": "https://andere-seite.example/impressum"})
    assert cell.status != EvidenceStatus.SUPPORTED
    cell = bare({**_imp(), "register": ""})
    assert cell.status != EvidenceStatus.SUPPORTED


def _register_startup(founded, excerpt, verified=True):
    candidate = Candidate(
        name="Kreislauf Technik GmbH", description="Sortiert mineralische Reststoffe",
        founded=founded, company_type="startup", discovery_mode="live",
        website="https://kreislauf-technik.de", operating_status="active",
        sources=[source("https://kreislauf-technik.de/produkt", "official", ["identity", "product"],
                        "Die Kreislauf Technik GmbH sortiert Bauschutt mit Kameras.", True,
                        "Kreislauf Technik GmbH"),
                 source("https://www.evi.gv.at/f/663933y", "register", [], excerpt, verified,
                        "Kreislauf Technik GmbH")])
    candidate.impressum = _imp()
    return candidate


def test_r3_register_entry_counts_as_founding_evidence():
    from evidence_matrix import EvidenceMatrixBuilder, EvidenceStatus
    candidate = _register_startup(2025, "Eingetragen im Firmenbuch am 08.10.2025")
    result = EntityVerifier().verify(candidate)
    assert not any("Gruendungsjahr" in r for r in result.reasons), result.reasons
    cell = next(c for c in EvidenceMatrixBuilder().build(candidate).cells if c.dimension == "startup_status")
    assert cell.status == EvidenceStatus.SUPPORTED and cell.open_questions == []
    for text in ("Date of incorporation: 3 March 2025", "Registered in 2025 at Companies House",
                 "Eintragung ins Handelsregister 2025"):
        assert not any("Gruendungsjahr" in r for r in EntityVerifier().verify(_register_startup(2025, text)).reasons), text


def test_r3_register_entry_unverified_or_other_year_does_not_count():
    unverified = _register_startup(2025, "Eingetragen im Firmenbuch am 08.10.2025", verified=False)
    assert "Gruendungsjahr keiner Quelle auf Aussageebene zugeordnet" in EntityVerifier().verify(unverified).reasons \
        or "Gruendungsjahr nicht belegt" in EntityVerifier().verify(unverified).reasons
    other = _register_startup(2025, "Eingetragen im Firmenbuch am 08.10.2023")
    assert any("Gruendungsjahr" in r for r in EntityVerifier().verify(other).reasons)


def test_r3_age_limit_applies_to_register_entry():
    old = _register_startup(2012, "Eingetragen im Handelsregister am 01.02.2012")
    result = EntityVerifier().verify(old)
    assert "Ausschluss: aelter als zehn Jahre (kein Startup mehr)" in result.reasons
    assert result.status == "not_a_startup"


def test_r3_imprint_with_registration_date_counts():
    candidate = _register_startup(2025, "kein Datum hier")
    candidate.impressum = {**_imp(), "excerpt": "Kreislauf Technik GmbH, HRB 783981, eingetragen am 08.10.2025"}
    assert not any("Gruendungsjahr" in r for r in EntityVerifier().verify(candidate).reasons)
