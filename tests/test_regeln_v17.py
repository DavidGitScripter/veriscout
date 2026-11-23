"""v17 (12.11.2026, David): Suchbudget ausschoepfen, bevor leer geantwortet wird; beide Arme gleich."""
import inspect

from core import Config


def test_v17_version():
    assert Config.PROMPT_CONTRACT_VERSION == "public-push-pull-sas2-mas-v17-suchbudget-2026-11-12"


def test_v17_search_rule_in_stage_one_of_both_arms():
    import agents
    import baselines
    from agents import ScoutingAgent
    rule = ("Ein leeres Array ist erst zulaessig, wenn du in dieser Stufe mindestens fuenf "
            "Websuchen ausgefuehrt hast (bei einem Budget von sechs)")
    assert rule in ScoutingAgent.SYSTEM
    assert "mindestens drei unterschiedlichen Websuchen" not in ScoutingAgent.SYSTEM
    # SAS-2-Recherche und MAS-Scouting nutzen denselben Systemprompt der Stufe 1.
    assert "system=ScoutingAgent.SYSTEM" in inspect.getsource(baselines.SelfReviewSingleAgent.run)
    assert "system=self.SYSTEM" in inspect.getsource(agents.ScoutingAgent)
    # Budget der Stufe 1 traegt die fuenf Suchen.
    from compare_architectures import ExperimentBudget
    stages = ExperimentBudget().stage_allocation()
    assert stages["stage_1"]["max_tool_calls"] >= 6


def test_dach_rule_in_stage_one_prompt():
    from agents import ScoutingAgent
    assert "Nur Startups mit Sitz in Deutschland, Oesterreich oder der Schweiz" in ScoutingAgent.SYSTEM


def _relocated_candidate(reason, verified_url):
    from core import Candidate, Source
    src = Source(url="https://www.kreislauf-technik.de/ueber-uns", source_type="official", supports=["identity", "product"],
                 excerpt="Die Kreislauf Technik GmbH sortiert Bauschutt mit Kameras und KI.", citation_verified=True,
                 resolved_status="resolved", excerpt_verified=True, resolved_url=verified_url,
                 subject_type="candidate_startup", subject_name="Kreislauf Technik GmbH",
                 relocation={"cited_url": "https://www.kreislauf-technik.de/ueber-uns", "verified_url": verified_url, "reason": reason})
    return Candidate(name="Kreislauf Technik GmbH", description="x", website="https://www.kreislauf-technik.de",
                     company_type="startup", founded=2022, discovery_mode="live", sources=[src])


def test_found_page_on_other_domain_is_not_an_official_source():
    from entity_verifier import EntityVerifier
    other = EntityVerifier().verify(_relocated_candidate("auszug_nicht_auf_zitierter_seite_andere_domain",
                                                         "https://presse.example/artikel"))
    assert "keine identitaetsgleiche offizielle Quelle" in other.reasons
    same = EntityVerifier().verify(_relocated_candidate("auszug_nicht_auf_zitierter_seite_gleiche_domain",
                                                        "https://www.kreislauf-technik.de/team"))
    assert "keine identitaetsgleiche offizielle Quelle" not in same.reasons


def test_rating_sheet_shows_found_page():
    from rating_panel_template import TEMPLATE
    assert "Der Satz steht nicht auf der genannten Seite, sondern hier" in TEMPLATE
    assert "s.verified_url" in TEMPLATE


@__import__("pytest").mark.parametrize("dimension", ["startup_capability", "transformation", "output_application"])
def test_v17_confirmed_quote_suffices_for_dims_6_to_8(dimension):
    from evidence_matrix import EvidenceStatus, _cell_from_manifest
    support = [{"field": dimension, "stance": "support", "claim_id": "1", "source_id": "s",
                "excerpt": "Ein wortgleich bestaetigter Satz des Startups zur Dimension."}]
    assert _cell_from_manifest(dimension, "x", False, support, "?").status == EvidenceStatus.SUPPORTED
    unknown = [dict(support[0], stance="unknown")]
    assert _cell_from_manifest(dimension, "x", False, unknown, "?").status != EvidenceStatus.SUPPORTED
    assert _cell_from_manifest(dimension, "x", False, [], "?").status == EvidenceStatus.MISSING


def test_v17_r4_unchanged_without_target_process():
    # Wirkung/Ergebnis bleiben ohne belegten Zielprozess hoechstens "teilweise".
    import evidence_matrix as em
    src = __import__("inspect").getsource(em.EvidenceMatrixBuilder.build)
    assert "Zielprozess belegen, damit Wirkung und Ergebnis die Kette tragen." in src
