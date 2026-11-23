from core import Candidate, Source, Recommendation
from pipeline import Pipeline


def test_push_plan_contains_no_prefilled_demo_manufacturing_process_hypotheses():
    pipeline = Pipeline(live=False)
    plan = pipeline.opportunity.build("demo_manufacturing", themes=[])
    assert plan["opportunities"] == []
    assert plan["curated_leads"] == []
    assert "unknown" in plan["boundary"]
    assert plan["public_sources"] == []


def test_selected_member_cannot_be_replaced_by_higher_keyword_score():
    pipeline = Pipeline(live=False)
    candidate = Candidate(
        name="Synthetic Circular Film",
        description="Mono-Material Folien chemisches Recycling biobasierte Compounds",
        founded=2025,
        company_type="startup",
        discovery_mode="synthetic",
        verification_status="synthetic_case",
        problem_fit=True,
        sectors=["Circular Economy"],
        sources=[Source(url="https://synthetic.example")],
        target_actor_id="demo_manufacturing",
    )
    decision = pipeline.scout(candidate, use_memory=False, target_actor_id="demo_manufacturing")
    assert decision.best_actor_id == "demo_manufacturing"
    assert all(not m.sufficient for m in decision.matches if m.actor_id != "demo_manufacturing")
    assert decision.recommendation != Recommendation.PILOT


def test_live_candidate_without_process_evidence_is_blocked():
    pipeline = Pipeline(live=False)
    candidate = Candidate(
        name="Mineral Loop GmbH",
        description="Verwertet mineralische Feinfraktionen",
        founded=2025,
        company_type="startup",
        discovery_mode="live",
        verification_status="verified_startup",
        problem_fit=None,
        sectors=["Circular Economy"],
        sources=[],
        target_actor_id="demo_manufacturing",
    )
    decision = pipeline.scout(candidate, use_memory=False, target_actor_id="demo_manufacturing")
    assert decision.abstained is True
    assert "Prozessbeziehung" in decision.abstain_reason


def test_verified_entity_without_source_bound_process_mechanism_is_blocked():
    pipeline = Pipeline(live=False)
    candidate = Candidate(
        name="Mineral Entity GmbH",
        description="Verwertet mineralische Feinfraktionen in Bauprodukten",
        founded=2025,
        company_type="startup",
        discovery_mode="live",
        problem_fit=True,
        website="https://mineral-entity.de",
        sources=[
                Source(url="https://mineral-entity.de/technology", source_type="official",
                       subject_type="candidate_startup",
                       subject_name="Mineral Entity GmbH",
                   supports=["identity", "product"],
                   excerpt="Mineral Entity entwickelt Bauprodukte aus mineralischen Reststoffen.",
                   citation_verified=True, citation_origin="output_annotation",
                   resolved_status="resolved", resolved_url="https://mineral-entity.de/technology",
                   http_status=200, content_hash="official-document-hash", excerpt_verified=True),
                Source(url="https://startup-register.de/mineral-entity", source_type="register",
                       subject_type="candidate_startup",
                       subject_name="Mineral Entity GmbH",
                   supports=["identity", "founded"],
                   excerpt="Die Mineral Entity GmbH wurde im Jahr 2025 gegründet.",
                   citation_verified=True, citation_origin="output_annotation",
                   resolved_status="resolved", resolved_url="https://startup-register.de/mineral-entity",
                   http_status=200, content_hash="register-document-hash", excerpt_verified=True),
        ],
        target_actor_id="demo_manufacturing",
    )
    # R1/R2 (11.11.2026): Sitz in DACH und Existenz ueber ein geprueftes Impressum.
    candidate.impressum = {"url": "https://mineral-entity.de/impressum", "company_name_found": True,
                           "register": "Amtsgericht Ulm HRB 1", "country": "DE"}
    decision = pipeline.scout(candidate, use_memory=False, target_actor_id="demo_manufacturing")
    assert decision.candidate.verification_status == "verified_startup"
    assert decision.abstained is True
    assert "Prozessmechanismus" in decision.abstain_reason


def test_invented_live_company_abstains_even_with_strong_keywords():
    pipeline = Pipeline(live=False)
    candidate = Candidate(
        name="Erfundene Mineral Loop GmbH",
        description=("Automatisierung Steinverarbeitung Robotik Materialpruefung "
                     "nachhaltige Materialien Fertigungseffizienz"),
        founded=2025,
        company_type="startup",
        discovery_mode="live",
        problem_fit=True,
        website="https://erfundene-mineral-loop.invalid",
        sources=[Source(
            url="https://erfundene-mineral-loop.invalid",
            source_type="official",
            supports=["identity", "founded", "product", "process"],
            excerpt="Eine nur behauptete Firma mit einer nur behaupteten Technologie.",
        )],
        target_actor_id="demo_manufacturing",
    )
    decision = pipeline.scout(candidate, use_memory=False, target_actor_id="demo_manufacturing")
    assert decision.abstained is True
    assert decision.recommendation != Recommendation.PILOT
    assert decision.candidate.verification_status == "needs_evidence"


def test_joint_venture_cannot_enter_pipeline_as_startup():
    pipeline = Pipeline(live=False)
    candidate = Candidate(
        name="Mineral Circularity Joint Venture",
        description=("Automatisierung Steinverarbeitung Robotik Materialpruefung "
                     "nachhaltige Materialien Fertigungseffizienz"),
        founded=2025,
        company_type="joint_venture",
        discovery_mode="live",
        problem_fit=True,
        website="https://mineral-circularity-jv.de",
        sources=[
            Source(
                url="https://mineral-circularity-jv.de/technology",
                source_type="official",
                supports=["identity", "founded", "product", "process"],
                excerpt=("Das Gemeinschaftsunternehmen entwickelt eine Anlage zur "
                         "Aufbereitung mineralischer Reststoffe."),
            ),
            Source(
                url="https://startup-register.de/mineral-circularity-jv",
                source_type="register",
                supports=["identity", "founded"],
                excerpt=("Der Registereintrag bezeichnet die Gesellschaft als "
                         "Gemeinschaftsunternehmen zweier Konzerne."),
            ),
        ],
        target_actor_id="demo_manufacturing",
    )
    decision = pipeline.scout(candidate, use_memory=False, target_actor_id="demo_manufacturing")
    assert decision.abstained is True
    assert decision.recommendation != Recommendation.PILOT
    assert decision.candidate.verification_status == "not_a_startup"


class _NegativeTargetMemory:
    def effective_threshold(self, actor_id):
        return 61

    def score_adjustment(self, actor_id, description):
        return -12, 0.8, "frueheres Zielorganisationsurteil"


def test_memory_adjustment_preserves_selected_member_binding():
    pipeline = Pipeline(live=False, memory=_NegativeTargetMemory())
    candidate = Candidate(
        name="Synthetic Circular Film",
        description="Mono-Material Folien chemisches Recycling biobasierte Compounds",
        founded=2025,
        company_type="startup",
        discovery_mode="synthetic",
        verification_status="synthetic_case",
        problem_fit=True,
        sectors=["Circular Economy"],
        sources=[Source(url="https://synthetic.example")],
        target_actor_id="demo_manufacturing",
    )
    decision = pipeline.scout(candidate, target_actor_id="demo_manufacturing")
    assert decision.best_actor_id == "demo_manufacturing"
    assert all(not m.sufficient for m in decision.matches if m.actor_id != "demo_manufacturing")


def test_target_binding_does_not_leak_between_discovery_runs():
    pipeline = Pipeline(live=False)
    seed = Candidate(
        name="Synthetic Seed",
        description="Automatisierung Steinverarbeitung",
        discovery_mode="synthetic",
        verification_status="synthetic_case",
    )
    targeted, _ = pipeline.discover(
        "Steinverarbeitung", seed_pool=[seed], target_actor_id="demo_manufacturing")
    general, _ = pipeline.discover(
        "Steinverarbeitung", seed_pool=[seed], target_actor_id="")
    assert targeted[0].target_actor_id == "demo_manufacturing"
    assert general[0].target_actor_id == ""
    assert seed.target_actor_id == ""


def test_push_requires_exactly_one_public_field_and_never_uses_curated_leads():
    pipeline = Pipeline(live=False)
    theme = {
        "id": "p042", "typ": "oeffentlich", "actor_id": "demo_manufacturing",
        "themengebiet": "Ressourceneffiziente Fertigung",
        "beschreibung": "Oeffentlich sichtbares Suchfeld.",
        "quelle": "oeffentliche Unternehmensdarstellung",
    }
    candidates, trace = pipeline.discover(
        "", n=3, target_actor_id="demo_manufacturing", push_mode=True, themes=[theme])
    assert trace["output"].get("kuratierte_rohhinweise", 0) == 0
    assert pipeline.last_opportunity_plan["public_search_fields"][0]["theme_id"] == "p042"
    assert pipeline.last_opportunity_plan["curated_leads"] == []
