"""Explizite Quality Gates fuer die sechs festgestellten Schwachstellen."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from core import Recommendation
from entity_verifier import is_independent_source


# Zuordnung der supports-Kennzeichen zu den Matrixdimensionen (fuer QG3).
SUPPORT_DIMENSIONS = {
    "identity": "identity", "founded": "startup_status", "product": "startup_capability",
    "target_identity": "target_identity", "target_process": "target_process",
    "process": "target_process", "input_stream": "input_stream",
    "transformation": "transformation", "output_application": "output_application",
}


def _confirmed(source) -> bool:
    return bool(source.citation_verified and source.resolved_status == "resolved"
                and source.excerpt_verified)


@dataclass(frozen=True)
class QualityGateResult:
    gate_id: str
    passed: bool
    blocking: bool
    rationale: str
    evidence: dict

    def to_dict(self) -> dict:
        return asdict(self)


class QualityGateEvaluator:
    def evaluate(self, decision) -> list[QualityGateResult]:
        candidate = decision.candidate
        mode = candidate.discovery_mode
        sources = list(candidate.sources or [])
        live = mode == "live"
        matrix = candidate.evidence_matrix or {}

        official = [source for source in sources
                    if source.source_type == "official"
                    and source.resolved_status == "resolved"
                    and source.excerpt_verified]
        independent = [source for source in sources
                       if source.source_type in {"register", "press", "database", "public_body"}
                       and source.resolved_status == "resolved"
                       and source.excerpt_verified
                       and any(is_independent_source(primary, source)
                               for primary in official)]
        # R2 (11.11.2026): Ein geprueftes Impressum mit Firmenname und
        # Registermerkmal ersetzt die unabhaengige Quelle.
        impressum = dict(getattr(candidate, "impressum", None) or {})
        impressum_ok = bool(impressum.get("company_name_found") and impressum.get("register"))
        qg1_pass = (not live) or bool((official or impressum_ok) and (independent or impressum_ok))

        qg2_pass = (mode == "synthetic" or
                    candidate.verification_status == "verified_startup")

        # M1: gesperrte Bezahl-/Login-Datenbanken zaehlen nicht als Quelle.
        relevant_sources = [source for source in sources if source.supports
                            and getattr(source, "resolved_status", "") != "blocked_paid_database"]
        # QG3 (12.11.2026, David): Eine nicht bestaetigte Quelle sperrt nur, wenn
        # die Aussage, die sie stuetzen soll, nicht schon bestaetigt belegt ist
        # (bestaetigte Quelle mit demselben Kennzeichen oder belegte Matrixzelle).
        # Sie zaehlt nie als Beleg, bleibt sichtbar und wird protokolliert.
        confirmed = [source for source in relevant_sources if _confirmed(source)]
        cell_status = {str(cell.get("dimension")): str(cell.get("status"))
                       for cell in matrix.get("cells") or []}

        def covered(tag: str) -> bool:
            tag = str(tag).strip().lower()
            if any(tag in {str(t).strip().lower() for t in s.supports} for s in confirmed):
                return True
            dimension = SUPPORT_DIMENSIONS.get(tag)
            return bool(dimension) and cell_status.get(dimension) == "supported"

        unconfirmed = [source for source in relevant_sources if not _confirmed(source)]
        blocking_unconfirmed = [s for s in unconfirmed if not all(covered(t) for t in s.supports)]
        superseded_unconfirmed = [s for s in unconfirmed if s not in blocking_unconfirmed]
        qg3_pass = (not live) or (bool(confirmed) and not blocking_unconfirmed)

        qg4_pass = (mode == "synthetic" or
                    matrix.get("decision_state") == "fully_supported")

        qg5_pass = (not decision.confidence_is_calibrated
                    and float(decision.confidence or 0.0) == 0.0)

        qg6_pass = not (
            decision.recommendation != Recommendation.PILOT
            or decision.abstained
            or (mode in {"live", "curated"} and not qg4_pass)
        )

        return [
            QualityGateResult(
                "QG1_INDEPENDENT_EVIDENCE", qg1_pass, True,
                ("Direkt aufgeloeste offizielle und unabhaengige Quelle bzw. geprueftes Impressum vorhanden."
                 if qg1_pass else
                 "Ein zweiter Modellaufruf ersetzt keine modellunabhaengige Quellenpruefung."),
                {"official_resolved": len(official),
                 "independent_resolved": len(independent),
                 "impressum_register": impressum.get("register", "")},
            ),
            QualityGateResult(
                "QG2_FAIL_CLOSED_VERIFICATION", qg2_pass, True,
                ("Verifikationsstatus ist positiv oder Fall ist klar synthetisch markiert."
                 if qg2_pass else
                 "Fehlende Verifikationswerte wurden nicht positiv uebernommen."),
                {"verification_status": candidate.verification_status,
                 "reasons": candidate.verification_reasons},
            ),
            QualityGateResult(
                "QG3_NATIVE_SOURCE_PROVENANCE", qg3_pass, True,
                ("Entscheidungsquellen stammen aus nativen Toolmetadaten und wurden aufgeloest."
                 if qg3_pass else
                 "Mindestens eine entscheidungsrelevante Quelle ist nur modellgeneriert oder unbestaetigt."),
                {"relevant_sources": len(relevant_sources),
                 "blocking_unconfirmed": [s.url for s in blocking_unconfirmed],
                 # Protokollierte Abweichung: unbestaetigt, aber anderweitig belegt.
                 "unconfirmed_superseded": [{"url": s.url, "supports": list(s.supports)}
                                            for s in superseded_unconfirmed]},
            ),
            QualityGateResult(
                "QG4_RELATIONAL_EVIDENCE", qg4_pass, True,
                ("Alle Pflichtdimensionen der Beziehung sind gestuetzt."
                 if qg4_pass else
                 "Keyword-Naehe ersetzt keine vollstaendige relationale Evidenzkette."),
                {"coverage": matrix.get("evidence_coverage", 0.0),
                 "blocking_dimensions": matrix.get("blocking_dimensions", [])},
            ),
            QualityGateResult(
                "QG5_NO_UNCALIBRATED_CONFIDENCE", qg5_pass, True,
                ("Es wird keine unkalibrierte Wahrscheinlichkeit ausgegeben."
                 if qg5_pass else
                 "Konfidenz darf erst mit separatem Kalibrationsartefakt als Wahrscheinlichkeit erscheinen."),
                {"confidence": decision.confidence,
                 "calibrated": decision.confidence_is_calibrated},
            ),
            QualityGateResult(
                "QG6_EXTERNAL_ACTION_BOUNDARY", qg6_pass, True,
                ("Kandidat ist fachlich fuer einen menschlich freizugebenden Pilot-Vorschlag berechtigt."
                 if qg6_pass else
                 "CRM und Outreach bleiben bei Beobachtung, Enthaltung oder Evidenzmangel gesperrt."),
                {"recommendation": decision.recommendation.value,
                 "abstained": decision.abstained},
            ),
        ]

    @staticmethod
    def operationally_eligible(results: list[QualityGateResult]) -> bool:
        return all(result.passed for result in results if result.blocking)
