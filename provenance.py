"""
provenance.py — deterministischer Audit-/Provenance-Recorder.

Macht jede Entscheidung nachvollziehbar: Belegt, worauf die Bewertung beruht
(Quellen je Kandidat), dokumentiert das Retrieval, haelt das Guardrail-Verdikt
fest, warnt bei veraltetem Datenstand und schreibt ein Entscheidungs-Log.
Adressiert damit die Verifikations-Fehlerklasse aus der MAST-Taxonomie.
"""
from __future__ import annotations

import json
import datetime
import os
from core import Config


def _months_since(vintage: str) -> int:
    try:
        y, m = map(int, vintage.split("-")[:2])
        now = datetime.date.today()
        return (now.year - y) * 12 + (now.month - m)
    except Exception:
        return 0


class AuditRecorder:
    def run(self, decision, kb, write_log: bool = False) -> dict:
        c = decision.candidate
        vintage = kb.data_vintage()
        months = _months_since(vintage)
        audit = {
            "lauf_id": c.run_id,
            "kandidat": c.name,
            "datenklasse": "synthetisch/oeffentlich",
            "quellen": [{"dokument_id": getattr(s, "document_id", ""),
                         "url": s.url, "titel": s.title,
                         "typ": getattr(s, "source_type", "unknown"),
                         "stuetzt": getattr(s, "supports", []),
                         "belegauszug": getattr(s, "excerpt", ""),
                         "native_toolquelle": getattr(s, "citation_verified", False),
                         "citation_origin": getattr(s, "citation_origin", ""),
                         "resolved_status": getattr(s, "resolved_status", ""),
                         "resolved_url": getattr(s, "resolved_url", ""),
                         "http_status": getattr(s, "http_status", 0),
                         "content_hash": getattr(s, "content_hash", ""),
                         "belegauszug_bestaetigt": getattr(s, "excerpt_verified", False)}
                        for s in c.sources],
            "evidenzstatus": c.verification_status,
            "evidenz_ok": c.verification_status == "verified_startup",
            "evidenzgruende": c.verification_reasons,
            "zielorganisation": c.target_actor_id,
            "opportunity_id": c.opportunity_id,
            "relationale_evidenzmatrix": c.evidence_matrix,
            "quality_gates": decision.quality_gates,
            "operativ_freigabefaehig": decision.operationally_eligible,
            "modellnutzung": c.model_usage,
            "retrieval": [{"akteur": m.actor_name, "score": m.score,
                           "begruendung": m.rationale} for m in decision.matches],
            "guardrail": {"abstention": decision.abstained,
                          "grund": decision.abstain_reason,
                          "ausschluss": decision.matches[0].exclusions
                                        if decision.matches else []},
            "datenstand": vintage,
            "datenstand_warnung": (months > Config.VINTAGE_WARN_MONTHS),
            "config": {"schwelle": Config.THRESHOLD_SUFFICIENT,
                       "pilot_min": Config.PILOT_MIN,
                       "modell": Config.MODEL,
                       "reasoning_effort": Config.REASONING_EFFORT,
                       "confidence_kalibriert": decision.confidence_is_calibrated},
        }
        if write_log:
            os.makedirs(os.path.dirname(Config.AUDIT_LOG), mode=0o700,
                        exist_ok=True)
            with open(Config.AUDIT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(audit, ensure_ascii=False) + "\n")
            try:
                os.chmod(Config.AUDIT_LOG, 0o600)
            except OSError:
                pass
        return audit


AuditAgent = AuditRecorder
