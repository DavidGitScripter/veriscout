from core import Candidate, Source
from evidence_matrix import EvidenceMatrixBuilder


def native_source(url, kind, supports, excerpt, *, subject_type="candidate_startup",
                  subject_id="", subject_name=""):
    return Source(
        url=url, source_type=kind, supports=supports, excerpt=excerpt,
        subject_type=subject_type, subject_id=subject_id,
        subject_name=subject_name,
        citation_verified=True, citation_origin="output_annotation",
        resolved_status="resolved", resolved_url=url, http_status=200,
        content_hash="hash", excerpt_verified=True,
    )


def test_complete_relational_chain_is_eligible_only_with_target_and_startup_evidence():
    candidate = Candidate(
        name="Mineral Loop GmbH", description="Verarbeitet mineralische Reststoffe",
        founded=2025, company_type="startup", discovery_mode="live", operating_status="active",
        verification_status="verified_startup", official_url="https://mineral-loop.de",
        target_actor_id="demo_manufacturing", opportunity_id="opp-1",
        process_stage="Wasserstrahlbearbeitung",
        input_stream="mineralischer Bearbeitungsrest",
        transformation="Aufbereitung und Bindung zu einem Formstein",
        output_application="Baustoff fuer den Hausbau",
        evidence_claims=[
            {"claim_text": "Aufbereitung und Bindung zu einem Formstein",
             "field": "transformation",
             "source_url": "https://mineral-loop.de/technology",
             "excerpt": "Mineral Loop bereitet mineralische Reststoffe auf und bindet sie zu Formsteinen.",
             "stance": "support", "subject_type": "candidate_startup",
             "subject_name": "Mineral Loop GmbH"},
            {"claim_text": "Baustoff fuer den Hausbau", "field": "output_application",
             "source_url": "https://mineral-loop.de/technology",
             "excerpt": "Mineral Loop bereitet mineralische Reststoffe auf und bindet sie zu Formsteinen.",
             "stance": "support", "subject_type": "candidate_startup",
             "subject_name": "Mineral Loop GmbH"},
        ],
        sources=[
            native_source(
                "https://mineral-loop.de/technology", "official",
                ["identity", "product", "input_stream", "transformation",
                 "output_application"],
                "Mineral Loop bereitet mineralische Reststoffe auf und bindet sie zu Formsteinen.",
                subject_name="Mineral Loop GmbH"),
            native_source(
                "https://register.example.org/mineral-loop", "register",
                ["identity", "founded"],
                "Die Mineral Loop GmbH wurde im Jahr 2025 als Gesellschaft eingetragen.",
                subject_name="Mineral Loop GmbH"),
        ],
    )
    target_sources = [{
        "document_id": "SYN-DEMO-001", "url": "https://demo-manufacturing.example/process",
        "evidence": [
            {"field": "target_identity",
             "claim_text": "Die Zielorganisation ist eindeutig identifiziert.",
             "excerpt": "Die offizielle Website weist die Zielorganisation eindeutig aus.",
             "subject_type": "target_organization",
             "subject_id": "demo_manufacturing"},
            {"profile_field": "Wasserstrahlbearbeitung Prozess",
             "excerpt": "Die Zielorganisation beschreibt diesen Bearbeitungsschritt öffentlich.",
             "subject_type": "target_organization",
             "subject_id": "demo_manufacturing"},
            {"field": "input_stream",
             "claim_text": "mineralischer Bearbeitungsrest",
             "excerpt": "Die Zielorganisation nennt mineralische Bearbeitungsreste als Inputstrom.",
             "subject_type": "target_organization",
             "subject_id": "demo_manufacturing"},
        ],
        "subject_type": "target_organization",
        "subject_id": "demo_manufacturing",
    }]
    matrix = EvidenceMatrixBuilder().build(candidate, target_sources)
    assert matrix.decision_state == "fully_supported"
    assert matrix.evidence_coverage == 1.0
    assert not matrix.blocking_dimensions


def test_keyword_and_filled_fields_do_not_replace_missing_native_claim_sources():
    candidate = Candidate(
        name="Plausible Loop", description="Kreislaufwirtschaft Baustoff Reststoff",
        founded=2025, company_type="startup", discovery_mode="live", operating_status="active",
        verification_status="verified_startup", official_url="https://plausible-loop.de",
        target_actor_id="demo_manufacturing", process_stage="Öffentlicher Testprozess",
        input_stream="mineralischer Teststoffstrom", transformation="Aufbereitung",
        output_application="Ziegel",
        sources=[Source(url="https://plausible-loop.de", source_type="official",
                        supports=["identity", "product", "transformation"],
                        excerpt="Plausible Loop behauptet die Verwertung mineralischer Reststoffe.")],
    )
    matrix = EvidenceMatrixBuilder().build(candidate, [])
    assert matrix.decision_state == "incomplete"
    assert "target_process" in matrix.blocking_dimensions
    assert "relational_chain" in matrix.blocking_dimensions


def test_missing_target_identity_output_evidence_blocks_live_recommendation():
    candidate = Candidate(
        name="Grounded Startup", description="Verarbeitet Reststoffe",
        founded=2025, company_type="startup", discovery_mode="live", operating_status="active",
        verification_status="verified_startup", official_url="https://grounded-startup.de",
        target_actor_id="target-org", process_stage="Oeffentlicher Prozess",
        input_stream="Reststoff", transformation="Aufbereitung",
        output_application="Baustoff",
        sources=[native_source(
            "https://grounded-startup.de", "official",
            ["identity", "product"],
            "Grounded Startup bietet eine Technologie zur Aufbereitung von Reststoffen an.",
            subject_name="Grounded Startup")],
    )
    matrix = EvidenceMatrixBuilder().build(candidate, target_sources=[])
    assert matrix.decision_state == "incomplete"
    assert matrix.cell("target_identity").status.value == "missing"
    assert "target_identity" in matrix.blocking_dimensions


def test_ambiguous_target_identity_contradicts_even_a_positive_claim():
    candidate = Candidate(
        name="Grounded Startup", description="Verarbeitet Reststoffe",
        founded=2025, company_type="startup", discovery_mode="live", operating_status="active",
        verification_status="verified_startup", official_url="https://grounded-startup.de",
        target_actor_id="target-org",
        unresolved_requirements=["Target identity ambiguous between two companies"],
        evidence_claims=[{
            "claim_text": "Target organization identity",
            "field": "target_identity",
            "source_url": "https://target-industries.com/about",
            "excerpt": "The official page identifies Target Industries as the named organization.",
            "stance": "support",
        }],
        sources=[native_source(
            "https://target-industries.com/about", "official",
            ["target_identity"],
            "The official page identifies Target Industries as the named organization.",
            subject_type="target_organization", subject_id="target-org")],
    )
    matrix = EvidenceMatrixBuilder().build(candidate, target_sources=[])
    assert matrix.cell("target_identity").status.value == "contradicted"
    assert "target_identity" in matrix.contradictions
    assert matrix.decision_state == "contradictory"
