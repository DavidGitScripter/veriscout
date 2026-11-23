"""Korrekturen K1 bis K3 vom 11.11.2026 (je einzeln ruecknehmbar)."""
from core import Candidate, Config
from agents import ScoutingAgent
from entity_verifier import EntityVerifier
from test_entity_verifier import source

REASON = "Produktfaehigkeit nicht durch die offizielle Quelle belegt"


def _candidate(product_url):
    return Candidate(
        name="Calc GmbH", description="Software fuer Oekobilanzen im Holzbau", founded=2017,
        company_type="startup", discovery_mode="live", website="https://calc.de",
        sources=[
            source("https://calc.de/ueber-uns", "official", ["identity"],
                   "Calc ist ein Münchner Softwareunternehmen für nachhaltiges Bauen.", True, "Calc GmbH"),
            source(product_url, "official", ["product"],
                   "Mit Calc berechnen Planer die Ökobilanz eines Gebäudes in frühen Phasen.", True, "Calc GmbH"),
            source("https://uni-beispiel.de/gruendung-calc", "public_body", ["identity", "founded"],
                   "Die Calc GmbH wurde 2017 als Ausgründung gegründet.", True, "Calc GmbH"),
        ])


def test_k1_product_on_other_page_of_official_site_counts():
    candidate = _candidate("https://calc.de/software")
    candidate.impressum = {"url": "https://calc.de/impressum", "company_name_found": True,
                           "register": "Amtsgericht Muenchen HRB 1", "country": "DE"}
    result = EntityVerifier().verify(candidate)
    assert REASON not in result.reasons
    assert result.status == "verified_startup"


def test_k1_product_only_on_foreign_site_stays_unproven():
    result = EntityVerifier().verify(_candidate("https://fremde-seite.de/calc-software"))
    assert REASON in result.reasons
    assert result.status != "verified_startup"


def test_k2_empty_array_with_preamble_is_valid_empty_result():
    raw = "Die Recherche hat keinen belegten Treffer ergeben. Ich liefere deshalb ein leeres Array.\n\n[]"
    assert ScoutingAgent._empty_array_preamble(raw).startswith("Die Recherche")
    assert ScoutingAgent._empty_array_preamble("Kein Treffer.\n```json\n[]\n```") == "Kein Treffer."
    # Nicht leere Arrays mit Vortext und reiner Text bleiben Vertragsfehler.
    assert ScoutingAgent._empty_array_preamble('Hier: [{"name": "x"}]') is None
    assert ScoutingAgent._empty_array_preamble("Nur Text ohne Array") is None
    assert ScoutingAgent._empty_array_preamble("[]") is None  # kein Vortext: normaler Pfad


def test_k2_records_preamble_and_deviation():
    class Broker:
        def __init__(self): self.protocol_deviations = []
        def _deviation(self, reason): self.protocol_deviations.append(reason)
    class LLM:
        def __init__(self): self.last_usage = {}; self.resource_broker = Broker()
    llm, copy = LLM(), {}
    ScoutingAgent._note_empty_preamble(llm, "Kein Treffer.", copy)
    assert llm.last_usage["empty_array_preamble"] == copy["empty_array_preamble"] == "Kein Treffer."
    assert llm.resource_broker.protocol_deviations == ["empty_array_with_preamble"]


def test_k3_prompt_requires_three_startup_searches_and_v11():
    # v17: verschaerft auf "Suchbudget ausschoepfen, mindestens fuenf Websuchen".
    assert "mindestens fuenf Websuchen ausgefuehrt hast" in ScoutingAgent.SYSTEM
    assert "Fuelle NIEMALS auf" in ScoutingAgent.SYSTEM
    assert "-v17-" in Config.PROMPT_CONTRACT_VERSION
    import inspect
    import baselines
    # SAS-2 nutzt fuer den Rechercheschritt denselben Systemprompt wie die MAS-Scoutingrolle.
    assert "system=ScoutingAgent.SYSTEM" in inspect.getsource(baselines.SelfReviewSingleAgent)
