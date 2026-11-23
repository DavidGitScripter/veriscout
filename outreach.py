"""
outreach.py — begrenzt autonomer Outreach-Agent (Entwurf, KEIN Versand).

Erstellt aus einer Vorlage mit Platzhaltern ein fertiges Anschreiben fuer ein
vorqualifiziertes Startup. Recherchiert (Live: GPT + Websuche; Dry-Run:
Heuristik) eine Kontaktadresse und uebernimmt die BCC-Adresse aus der im CRM
angelegten Organisation. Der Agent VERSENDET NICHT — er erzeugt einen Entwurf mit
Status 'entwurf_wartet_auf_freigabe'. Der Versand bleibt verpflichtend manuell
(Human-in-the-Loop).
"""
from __future__ import annotations

import os
import re
from core import Config, Recommendation

DEFAULT_TEMPLATE = (
    "Betreff: Rechercheimpuls fuer {{akteur}}\n\n"
    "Hallo {{kontakt_name}},\n\n"
    "im Rahmen eines oeffentlich belegten Startup-Scoutings ist uns "
    "{{startup}} aufgefallen — speziell mit Blick auf {{use_case}}.\n\n"
    "Fuer die Zielorganisation {{akteur}} sehen wir hier einen konkreten "
    "Anknuepfungspunkt. Haetten Sie Interesse an einem kurzen Kennenlern-Gespraech?\n\n"
    "Herzliche Gruesse\n{{absender}}\n"
)


def _slug_domain(name: str) -> str:
    base = re.sub(r"\b(gmbh|ag|se|kg|ug|co|und|the)\b", "", name.lower())
    base = re.sub(r"[^a-z0-9]+", "", base)
    return f"{base}.com" if base else "example.com"


class OutreachAgent:
    def __init__(self, llm=None, absender: str = ""):
        self.llm = llm
        # Der Absendername steht in der Signatur und laesst sich ueber die
        # Umgebung setzen, damit er nicht im Quelltext festhaengt.
        self.absender = absender or Config.ABSENDER

    def _template(self) -> str:
        try:
            if os.path.exists(Config.OUTREACH_TEMPLATE):
                with open(Config.OUTREACH_TEMPLATE, encoding="utf-8") as f:
                    return f.read()
        except Exception:
            pass
        return DEFAULT_TEMPLATE

    def _find_email(self, startup: str) -> tuple:
        """Kontaktadresse ermitteln.

        Nur eine tatsaechlich recherchierte Adresse wird zurueckgegeben. Laesst
        sie sich nicht belegen, liefert die Methode eine leere Zeichenkette und
        den Grund. Eine aus dem Firmennamen abgeleitete Adresse waere zwar
        plausibel, sie sieht beim fluechtigen Lesen aber wie eine gepruefte
        Angabe aus und wuerde die Ehrlichkeitsschwelle an genau der Stelle
        unterlaufen, an der eine Nachricht das Haus verlaesst.
        """
        if self.llm and self.llm.available():
            raw = self.llm.complete(
                model=Config.MODEL_OUTREACH,
                system="Finde die offizielle Kontakt- oder Presse-E-Mail-Adresse "
                       "des Unternehmens. Antworte NUR mit der Adresse oder mit "
                       "'unbekannt'. Rate nicht.",
                user=f"Unternehmen: {startup}",
                tools=[{"type": "web_search"}],
                max_tool_calls=2,
                max_tokens=200,
                purpose="outreach_contact_research").strip()
            m = re.search(r"[\w.\-]+@[\w.\-]+\.\w+", raw)
            sources = [item.get("url", "") for item in
                       (self.llm.last_citations or []) if item.get("url")]
            if m and sources:
                return (m.group(0),
                        "durch native Webquelle recherchiert; vor Versand pruefen",
                        sources)
            return "", "keine nativ belegte Adresse auffindbar", sources
        # Trockenlauf: Es findet keine Recherche statt, also gibt es auch keine
        # Adresse. Der Vorschlag dient nur der Anzeige und wird nicht gesetzt.
        return ("", (f"Trockenlauf, keine Recherche. Naheliegend waere "
                     f"info@{_slug_domain(startup)}, das ist aber unbelegt."), [])

    def run(self, decision, crm_result: dict, use_case: str = "") -> dict:
        if decision.recommendation != Recommendation.PILOT or decision.abstained:
            return {"status": "kein_entwurf",
                    "grund": "Keine Aussenwirkung bei Beobachtung oder Evidenzmangel."}
        c = decision.candidate
        if c.discovery_mode in {"live", "curated"}:
            matrix = c.evidence_matrix or {}
            if (matrix.get("decision_state") != "eligible"
                    or matrix.get("blocking_dimensions")):
                return {"status": "kein_entwurf",
                        "grund": "Relationale Evidenzmatrix nicht vollstaendig."}
        best = decision.matches[0] if decision.matches else None
        akteur = best.actor_name if best else "—"
        if not use_case:
            use_case = (best.rationale if best else "") or "die Zusammenarbeit"
        # Platzhalter ersetzen
        text = self._template()
        repl = {
            "{{startup}}": c.name,
            "{{akteur}}": akteur,
            "{{use_case}}": use_case,
            "{{absender}}": self.absender,
            "{{kontakt_name}}": "Gruenderteam",
        }
        for k, v in repl.items():
            text = text.replace(k, v)
        subject = ""
        if text.lower().startswith("betreff:"):
            line, _, rest = text.partition("\n")
            subject = line.split(":", 1)[1].strip()
            text = rest.lstrip("\n")
        # Kontaktadresse und BCC. Die BCC-Adresse ist die Ablage-Adresse der im
        # CRM angelegten Organisation, damit der Schriftwechsel dort auftaucht.
        to_email, email_quelle, email_quellen = self._find_email(c.name)
        bcc = (crm_result.get("bcc_dropbox")
               or (crm_result.get("org") or {}).get("bcc_dropbox", "")
               if isinstance(crm_result.get("org"), dict)
               else crm_result.get("bcc_dropbox", "")) or ""
        unresolved = [p for p in re.findall(r"{{.*?}}", text)]
        return {
            "status": "entwurf_wartet_auf_freigabe",
            "startup": c.name,
            "to": to_email,
            "to_quelle": email_quelle,
            "to_quellen": email_quellen,
            "adresse_belegt": bool(to_email),
            "bcc": bcc,
            "subject": subject,
            "body": text,
            "offene_platzhalter": unresolved,
            "hinweis": "Kein automatischer Versand. Der Entwurf wartet auf Sie.",
        }
