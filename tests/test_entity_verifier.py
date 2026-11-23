from core import Candidate, Source
from agents import VerificationAgent
from entity_verifier import EntityVerifier


def source(url, kind, supports, excerpt, native=False, subject_name=""):
    return Source(url=url, source_type=kind, supports=supports, excerpt=excerpt,
                  subject_type="candidate_startup" if subject_name else "",
                  subject_name=subject_name,
                  citation_verified=native,
                  citation_origin="output_annotation" if native else "",
                  resolved_status="resolved" if native else "not_checked",
                  resolved_url=url if native else "",
                  http_status=200 if native else 0,
                  content_hash=("test-hash-" + url) if native else "",
                  excerpt_verified=native)


def with_dach_impressum(candidate, url=""):
    """R1/R2 (11.11.2026): Sitz und Existenz ueber ein geprueftes Impressum."""
    candidate.impressum = {"url": url or candidate.website, "company_name_found": True,
                           "register": "Amtsgericht Muenchen HRB 123456", "country": "DE"}
    return candidate


def test_nonexistent_candidate_is_not_verified():
    candidate = Candidate(
        name="Erfundenes Startup",
        description="Plausibel klingende Kreislaufloesung",
        founded=2025,
        company_type="startup",
        discovery_mode="live",
        website="https://nicht-existent.invalid",
        sources=[source("https://nicht-existent.invalid", "official",
                        ["identity", "product"], "Behaupteter Beleg ohne reale Domain")],
    )
    result = EntityVerifier().verify(candidate)
    assert result.status == "needs_evidence"
    assert result.official_url == ""


def test_joint_venture_is_never_relabelled_as_startup():
    candidate = Candidate(
        name="Corporate Mobility JV",
        description="Gemeinsames Fahrzeugprojekt zweier Konzerne",
        founded=2025,
        company_type="joint_venture",
        discovery_mode="live",
        website="https://mobility-jv.de",
        sources=[
            source("https://mobility-jv.de", "official", ["identity", "product"],
                   "Das Gemeinschaftsunternehmen entwickelt autonome Transportfahrzeuge."),
            source("https://register.example.org/mobility-jv", "register",
                   ["identity", "founded"],
                   "Registerauszug bezeichnet die Gesellschaft als Joint Venture."),
        ],
    )
    result = EntityVerifier().verify(candidate)
    assert result.status == "not_a_startup"


def test_source_labels_without_claim_binding_do_not_verify():
    candidate = Candidate(
        name="Unbelegte Labels GmbH",
        description="Behauptet eine industrielle Kreislaufloesung",
        founded=2025,
        company_type="startup",
        discovery_mode="live",
        website="https://unbelegte-labels.de",
        sources=[
            source("https://unbelegte-labels.de", "official", ["identity"],
                   "Die Unbelegte Labels GmbH stellt sich als Unternehmen vor.",
                   True, "Unbelegte Labels GmbH"),
            source("https://startup-register.de/unbelegte-labels", "register",
                   ["identity", "founded"],
                   "Die Unbelegte Labels GmbH wurde 2025 gegruendet.", True,
                   "Unbelegte Labels GmbH"),
            source("https://presseportal.de/unbelegte-labels", "press", ["product"],
                   "Eine Pressemeldung behauptet eine industrielle Kreislaufloesung.",
                   True, "Unbelegte Labels GmbH"),
        ],
    )
    result = EntityVerifier().verify(candidate)
    assert result.status == "needs_evidence"
    assert "Produktfaehigkeit nicht durch die offizielle Quelle belegt" in result.reasons


def test_verification_result_replaces_unverified_discovery_website():
    candidate = Candidate(
        name="Real Mineral GmbH",
        description="Verarbeitet mineralische Reststoffe",
        website="https://halluzinierte-domain.de",
        official_url="https://halluzinierte-domain.de",
        company_type="unknown",
        discovery_mode="live",
    )
    VerificationAgent()._merge(candidate, {
        "exists": True,
        "entity_type": "startup",
        "official_url": "https://real-mineral.de",
        "founded": 2025,
        "sources": [
            {"url": "https://real-mineral.de/technologie", "source_type": "Official",
             "subject_type": "candidate_startup", "subject_name": "Real Mineral GmbH",
             "supports": ["identity", "product"],
             "excerpt": "Die Real Mineral GmbH verarbeitet mineralische Reststoffe."},
            {"url": "https://startup-register.de/real-mineral", "source_type": "register",
             "subject_type": "candidate_startup", "subject_name": "Real Mineral GmbH",
             "supports": ["identity", "founded"],
             "excerpt": "Die Real Mineral GmbH wurde im Jahr 2025 gegruendet."},
        ],
    })
    for item in candidate.sources:
        item.citation_verified = True
        item.citation_origin = "output_annotation"
        item.resolved_status = "resolved"
        item.resolved_url = item.url
        item.http_status = 200
        item.content_hash = "test-hash-" + item.url
        item.excerpt_verified = True
    with_dach_impressum(candidate, "https://real-mineral.de/impressum")
    result = EntityVerifier().verify(candidate)
    assert candidate.website == "https://real-mineral.de"
    assert result.official_url == "https://real-mineral.de"
    assert result.status == "verified_startup"


def test_claim_level_primary_and_independent_evidence_can_verify():
    candidate = Candidate(
        name="Mineral Loop GmbH",
        description="Verwertet feine mineralische Reststoffe in Bauprodukten",
        founded=2025,
        company_type="startup",
        discovery_mode="live",
        website="https://mineral-loop.de",
        sources=[
            source("https://mineral-loop.de/technology", "official",
                   ["identity", "product", "process"],
                   "Mineral Loop verarbeitet mineralische Feinfraktionen zu Bauprodukten.",
                   True, "Mineral Loop GmbH"),
            source("https://startup-register.de/mineral-loop", "register",
                   ["identity", "founded"],
                   "Die Mineral Loop GmbH wurde im Jahr 2025 in München gegründet.",
                   True, "Mineral Loop GmbH"),
        ],
    )
    with_dach_impressum(candidate)
    result = EntityVerifier().verify(candidate)
    assert result.status == "verified_startup"
    assert result.independent_source_url.endswith("/mineral-loop")


def test_live_verifier_replaces_scout_sources_with_independent_review_sources():
    candidate = Candidate(
        name="Curated Mineral GmbH",
        description="Mineralisches Kreislaufprodukt",
        founded=2025,
        company_type="startup",
        discovery_mode="live",
        website="https://curated-mineral.de",
        sources=[
            source("https://curated-mineral.de", "official",
                   ["identity", "product", "process"],
                   "Curated Mineral verarbeitet mineralische Reststoffe zu Bauprodukten."),
            source("https://fraunhofer.de/curated-mineral", "public_body",
                   ["identity", "founded"],
                   "Die Curated Mineral GmbH wurde im Jahr 2025 gegruendet."),
        ],
    )
    VerificationAgent()._merge(candidate, {
        "exists": True,
        "entity_type": "startup",
        "official_url": "https://curated-mineral.de",
        "founded": 2025,
        "sources": [
            {"url": "https://curated-mineral.de", "source_type": "official",
             "subject_type": "candidate_startup", "subject_name": "Curated Mineral GmbH",
             "supports": ["identity", "product"],
             "excerpt": "Curated Mineral entwickelt ein Bauprodukt."},
            {"url": "https://fraunhofer.de/curated-mineral", "source_type": "public_body",
             "subject_type": "candidate_startup", "subject_name": "Curated Mineral GmbH",
             "supports": ["identity", "founded"],
             "excerpt": "Fraunhofer beschreibt die Gruendung des Unternehmens im Jahr 2025."},
        ],
    })
    for item in candidate.sources:
        item.citation_verified = True
        item.resolved_status = "resolved"
        item.excerpt_verified = True
    with_dach_impressum(candidate)
    result = EntityVerifier().verify(candidate)
    assert result.status == "verified_startup"
    assert any(source.source_type == "public_body" and "founded" in source.supports
               for source in candidate.sources)
    assert all("process" not in source.supports for source in candidate.sources)
