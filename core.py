"""
core.py — Konfiguration, Enums, Datentypen, Text-Utilities, optionaler LLM-Client.

Dieses Modul bildet die gemeinsame Grundlage des Referenzmodells. Es enthaelt KEINE
Geschaeftslogik der Agenten, sondern nur die geteilten Bausteine:
- zentrale Konfiguration; numerische Grenzwerte gelten nur fuer synthetische
  Entwicklungsfaelle, waehrend Live-Urteile kategorial evidenzbasiert sind
- Enums fuer Empfehlung und Autonomiestufe
- Datenklassen fuer Kandidat, Akteur-Match und Entscheidung
- deterministische Text-Hilfsfunktionen (auch ohne LLM nutzbar)
- ein duenner LLM-Client, der Offline- und angeforderten Live-Betrieb trennt
"""
from __future__ import annotations

import datetime
import hashlib
import os
import re
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
import socket
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from http_security import verified_tls_context


# ===========================================================================
# .env-Lader (ohne Zusatz-Paket): liest eine lokale .env-Datei in die Umgebung.
# Geheimnisse (z.B. PIPEDRIVE_API_TOKEN) gehoeren in diese .env-Datei, NICHT in
# den Code. Die .env ist per .gitignore ausgeschlossen und darf nie geteilt
# oder committet werden. Bereits gesetzte Umgebungsvariablen haben Vorrang.
# ===========================================================================
_DOTENV_UEBERSCHRIEBEN = []


def _load_dotenv():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                # Explizit gesetzte Laufzeitvariablen haben Vorrang. Das ist vor
                # allem fuer sichere Test- und Trockenlaeufe wichtig: Ein
                # PIPEDRIVE_LIVE=0 der aufrufenden Umgebung darf nicht durch
                # einen alten Wert aus der lokalen .env reaktiviert werden.
                if key in os.environ and os.environ[key] != val:
                    _DOTENV_UEBERSCHRIEBEN.append(key)
                    continue
                os.environ[key] = val
    except Exception:
        pass


_load_dotenv()


# ===========================================================================
# Konfiguration
# ===========================================================================
class Config:
    VERSION = "v20-veriscout (2026-10-20)"
    # --- Vorab eingefrorene Entscheidungsregel ---------------------------
    # 61 stammt aus formativen Entwicklungslaeufen. Der Wert ist weder eine
    # Wahrscheinlichkeit noch extern kalibriert. Im Live-Pfad ist er nur eine
    # notwendige Vorbedingung; eine positive Empfehlung verlangt zusaetzlich
    # die vollstaendige relationale Evidenzkette und alle Quality Gates.
    THRESHOLD_SUFFICIENT = 61
    THRESHOLD_RUBRIC_VERSION = "equal-required-evidence-v1"
    PILOT_MIN = 76
    OBSERVE_MIN = 41

    # --- Ausschlusskriterien (aus ehrlichkeitsschwelle.md) ---
    MAX_EMPLOYEES = 500            # > 500 MA -> kein Startup mehr
    FOUNDED_MIN_YEAR = 2021        # vor 2021 gegruendet -> "zu alt"
    COMPANY_MAX_AGE = 10           # aelter als 10 Jahre -> falscher Unternehmenstyp
    MAX_DISTANCE_KM = 500          # > 500 km ohne starkes Argument -> Geo-Ausschluss

    # --- Organisationsneutrale Anwendungsinstanz ---
    # Konkrete Organisationen werden ausschliesslich per Instanzkonfiguration
    # oder Laufzeitvariable angegeben. Der Referenzmodellkern enthaelt keine
    # Kunden-, Partner- oder Organisationsstammdaten.
    APPLICATION_NAME = os.environ.get(
        "SCOUTREF_APPLICATION_NAME", "Public Scouting Lab")
    APPLICATION_LOCATION = os.environ.get("SCOUTREF_APPLICATION_LOCATION", "")
    PREFERRED_REGIONS = tuple(
        item.strip() for item in
        os.environ.get("SCOUTREF_PREFERRED_REGIONS", "").split(",")
        if item.strip())

    # --- Geo ---
    GEO_BONUS_KM = 50              # < 50 km -> regionaler Bonus
    GEO_BONUS_POINTS = 6

    # --- GPT-Modelle und kontrollierbare Versuchsbudgets (Live-Pfad) ---
    # Fuer den primaeren SAS--MAS-Vergleich ist dasselbe Modell zwingend. Terra
    # ist der aktuelle Kosten-/Qualitaetskompromiss der GPT-5.6-Familie. Die API
    # liefert den tatsaechlich verwendeten Modellbezeichner je Lauf zurueck; er
    # wird zusammen mit Tokens, Werkzeugaufrufen und Zeitstempel protokolliert.
    # 19.10.2026 auf Wunsch von David von gpt-5.6-terra auf gpt-6.1-sol
    # umgestellt: gleiche Preisklasse (2 / 10 statt 2 / 12 USD je 1 Mio.
    # Tokens), neueres Modell. Fruehere Laeufe mit terra bleiben als
    # Entwicklungsdaten gekennzeichnet (Modellkennung im Laufprotokoll).
    MODEL = os.environ.get("SCOUTREF_OPENAI_MODEL", "gpt-6.1-sol")
    MODEL_SCOUT = os.environ.get("SCOUTREF_SCOUT_MODEL", MODEL)
    MODEL_VERIFY = os.environ.get("SCOUTREF_VERIFY_MODEL", MODEL)
    MODEL_SAS = os.environ.get("SCOUTREF_SAS_MODEL", MODEL)
    MODEL_OUTREACH = os.environ.get("SCOUTREF_OUTREACH_MODEL", MODEL)
    # v16 = v15 + Prozessfeld-Regel (von David am 12.11.2026 freigegeben).
    # v17 (12.11.2026, David): Suchbudget der Stufe ausschoepfen (5 von 6), bevor leer geantwortet wird.
    PROMPT_CONTRACT_VERSION = "public-push-pull-sas2-mas-v17-suchbudget-2026-11-12"
    API_CONTRACT = "openai-responses-v1"
    PRICE_VINTAGE = "2026-08-31"
    # Rueckwaertskompatible Namen fuer UI und bestehende Skripte.
    MODEL_DISCOVERY = MODEL_SCOUT
    MODEL_JUDGE = MODEL_VERIFY
    MODEL_PREFILTER = MODEL
    REASONING_EFFORT = os.environ.get("SCOUTREF_REASONING_EFFORT", "low")
    # Kalibriert aus den Entwicklungspaaren vom 5. September 2026: Ein
    # einzelner Responses-Aufruf mit Websuche verbrauchte 27.736 bis 32.776
    # Eingabetokens (Websuchinhalte zaehlen als Input) und 3.907 bis 6.000
    # Ausgabetokens. Die frueheren Standardwerte (20k Input, 4k Output) waren
    # damit fuer jeden Live-Lauf zu knapp. Die Werte sind Protokollparameter,
    # keine Optimalwerte; jede Studie friert sie vor dem ersten Lauf ein.
    # 16.10.2026: Eingabegrenze nach den Probelaeufen auf 160.000 angehoben
    # (Claude Sonnet 5.5 benoetigte bis 130.109 Eingabetokens je Arm; GPT bis
    # 82.089). Freigegeben von David fuer den Hauptlauf, fuer alle Modelle gleich.
    # 19.10.2026: Nach Davids eigenem Lauf (CB-Tec) auf 12 Websuchen (6 je
    # Stufe) und 200.000 Eingabetokens erhoeht, Kostenrahmen 0,75 USD je Arm.
    # 12.11.2026 (Hauptlauf, nach Vorlauf studie-2026-11-12-3ef90a4e): Ausgabe
    # je Stufe 8.000 -> 12.000 (Arm 16.000 -> 24.000), weil 2 von 8 Sonnet-Armen
    # an der Stufengrenze abbrachen (max_tokens), 0 von 10 Sol-Armen. Fuer alle
    # Modelle und beide Arme gleich; alle anderen Werte unveraendert. Freigabe DS.
    BUDGET_PROFILE_VERSION = "main-calibrated-2026-11-12"
    # M2 (12.11.2026): feste Nachrecherche als dritter Schritt in beiden Armen.
    # Eigene Reserve oben auf dem Basisprofil; bewusst nicht per Umgebung
    # veraenderbar, damit beide Arme und alle Laeufe dieselbe Reserve haben.
    FOLLOW_UP_ENABLED = True
    # N3 (12.11.2026): Ausloeser erweitert (vorher Index >= 56, hoechstens 3 offen).
    FOLLOW_UP_MIN_INDEX = 44
    FOLLOW_UP_MAX_OPEN_DIMENSIONS = 4
    FOLLOW_UP_MAX_INPUT_TOKENS = 80_000
    FOLLOW_UP_MAX_OUTPUT_TOKENS = 4_000
    FOLLOW_UP_MAX_REASONING_TOKENS = 2_000
    FOLLOW_UP_MAX_TOOL_CALLS = 3
    FOLLOW_UP_MAX_FETCHES = 6
    FOLLOW_UP_MAX_COST_USD = 0.25
    PRODUCT_NAME = "VeriScout"
    EVAL_TOTAL_MAX_OUTPUT_TOKENS = int(
        os.environ.get("SCOUTREF_EVAL_MAX_OUTPUT_TOKENS", "24000"))
    EVAL_TOTAL_MAX_TOOL_CALLS = int(
        os.environ.get("SCOUTREF_EVAL_MAX_TOOL_CALLS", "12"))
    EVAL_MAX_INPUT_TOKENS = int(
        os.environ.get("SCOUTREF_EVAL_MAX_INPUT_TOKENS", "200000"))
    EVAL_MAX_REASONING_TOKENS = int(
        os.environ.get("SCOUTREF_EVAL_MAX_REASONING_TOKENS", "8000"))
    EVAL_MAX_MODEL_CALLS = int(
        os.environ.get("SCOUTREF_EVAL_MAX_MODEL_CALLS", "2"))
    EVAL_MAX_RESOLVER_FETCHES = int(
        os.environ.get("SCOUTREF_EVAL_MAX_RESOLVER_FETCHES", "24"))
    EVAL_MAX_COST_USD = float(
        os.environ.get("SCOUTREF_EVAL_MAX_COST_USD", "0.75"))
    EVAL_MAX_CANDIDATES = int(
        os.environ.get("SCOUTREF_EVAL_MAX_CANDIDATES", "3"))
    WEB_SEARCH_MAX_USES = int(
        os.environ.get("SCOUTREF_WEB_SEARCH_MAX_USES", "5"))
    # Der Anbieter haelt max_tool_calls nicht immer exakt ein (Pilot 5.9.:
    # 4 statt 3 Websuchen im ersten Schritt). "report" protokolliert eine
    # solche Ueberschreitung als Protokollabweichung je Stufe, ohne die
    # reservierte zweite Stufe zu blockieren; Geldkosten bleiben hart begrenzt.
    # "fail" stellt das fruehere strikte Verhalten fuer Sensitivitaetslaeufe her.
    # Auszugsabgleich des Resolvers. "fuzzy" akzeptiert zusaetzlich zu exakten
    # Treffern einen Auszug, dessen Woerter zu mindestens EXCERPT_FUZZY_MIN_RATIO
    # in derselben Reihenfolge in einem Fenster des Dokuments vorkommen
    # (Satzzeichen, Zeilenumbrueche, kleine Auslassungen). "exact" ist der
    # fruehere strenge Modus fuer Sensitivitaetsanalysen.
    EXCERPT_MATCH_MODE = os.environ.get(
        "SCOUTREF_EXCERPT_MATCH_MODE", "fuzzy").strip().lower()
    EXCERPT_FUZZY_MIN_RATIO = float(
        os.environ.get("SCOUTREF_EXCERPT_FUZZY_MIN_RATIO", "0.9"))
    EXCERPT_FUZZY_MIN_WORDS = int(
        os.environ.get("SCOUTREF_EXCERPT_FUZZY_MIN_WORDS", "6"))
    # Vorab festzulegende Entscheidungsgrenzen des Architekturvergleichs
    # (Kap. 5.5 und 7.3.2). Vor dem Hauptlauf einfrieren.
    EVAL_NI_MARGIN_PRECISION = float(
        os.environ.get("SCOUTREF_EVAL_NI_MARGIN_PRECISION", "-0.10"))
    EVAL_MIN_IMPROVEMENT = float(
        os.environ.get("SCOUTREF_EVAL_MIN_IMPROVEMENT", "0.10"))
    EVAL_WEB_OVERRUN_POLICY = os.environ.get(
        "SCOUTREF_EVAL_WEB_OVERRUN_POLICY", "report").strip().lower()
    DISCOVERY_WAVES = int(
        os.environ.get("SCOUTREF_DISCOVERY_WAVES", "1"))  # Suchwellen

    # Preise USD pro Million Tokens. Die Werte dienen nur der Laufanzeige und
    # koennen per Umgebung aktualisiert werden; fuer die Auswertung werden die
    # Roh-Tokens und Werkzeugaufrufe als fuehrende Messwerte gespeichert.
    PRICES = {
        "gpt-5.6-sol": (4.0, 20.0),
        "gpt-5.6": (4.0, 20.0),
        "gpt-5.6-terra": (2.0, 12.0),
        # OpenAI-Preisseite, abgerufen 16.10.2026 (Thread Modellwahl).
        "gpt-6.1-sol": (2.0, 10.0),
        "gpt-5.6-luna": (0.2, 1.2),
        # Anthropic, Preisstand 16.10.2026 (USD je 1 Mio. Tokens); Websuche wie
        # bei OpenAI 10 USD je 1.000 Suchen.
        "claude-sonnet-5-5": (2.0, 10.0),
    }
    WEB_SEARCH_PRICE = 0.01  # USD je Suche
    OPENAI_RESPONSES_URL = os.environ.get(
        "OPENAI_RESPONSES_URL", "https://api.openai.com/v1/responses")
    OPENAI_TIMEOUT_SECONDS = int(
        os.environ.get("SCOUTREF_OPENAI_TIMEOUT_SECONDS", "180"))
    AUDIT_WRITE = os.environ.get("SCOUTREF_AUDIT_WRITE", "1") == "1"

    # --- Datenstand / Provenance ---
    DATA_VINTAGE = "2026-05"
    VINTAGE_WARN_MONTHS = 6
    PROFILE_REVIEW_DAYS = int(
        os.environ.get("SCOUTREF_PROFILE_REVIEW_DAYS", "180"))
    PROFILE_STALE_DAYS = int(
        os.environ.get("SCOUTREF_PROFILE_STALE_DAYS", "270"))
    PROFILE_SOURCES_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "public",
        "profile_sources.json")
    CANDIDATE_REGISTRY_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "development",
        "candidate_registry.json")

    # --- Pipedrive (Live-Pfad, optional) ---
    # Token NICHT im Code: per Umgebungsvariable setzen.
    # Unternehmens-Domain ohne Versionssuffix. Der Adapter akzeptiert aus
    # Rueckwaertskompatibilitaet auch alte Werte mit /v1, /api/v1 oder /api/v2
    # und entfernt das Suffix, bevor er den jeweiligen Endpunkt zusammensetzt.
    PIPEDRIVE_API_BASE = os.environ.get("PIPEDRIVE_API_BASE", "https://api.pipedrive.com")
    PIPEDRIVE_API_TOKEN = os.environ.get("PIPEDRIVE_API_TOKEN", "")
    PIPEDRIVE_PIPELINE = os.environ.get(
        "PIPEDRIVE_PIPELINE", "ScoutRef Scouting")
    PIPEDRIVE_STAGE = os.environ.get("PIPEDRIVE_STAGE", "Vorqualifiziert")
    # Abstand der Rueckfragen an Pipedrive im Echtzeit-Strom.
    #
    # Drei Sekunden waren ein Konstruktionsfehler. Selbst die guenstigeren
    # Listenabfragen der API v2 verbrauchen im Dauertakt unnoetig Kontingent.
    #
    # Bei 60 Sekunden sind es 1.200 Punkte je Stunde. Zusammen mit der Pause bei
    # verdecktem Fenster und der Obergrenze weiter unten bleibt der Verbrauch
    # damit im Rahmen. Fuer die Bestaetigung eines gerade angelegten Eintrags
    # ist eine Minute schnell genug.
    PIPEDRIVE_POLL_SECONDS = int(os.environ.get("PIPEDRIVE_POLL_SECONDS", "60"))

    # Obergrenze dessen, was der Echtzeit-Strom je Sitzung verbrauchen darf.
    # Danach schaltet er sich ab und sagt es. Die eigentliche Arbeit, also
    # Suchen, Pruefen und Freigeben, bleibt davon unberuehrt.
    PIPEDRIVE_STREAM_PUNKTE = int(os.environ.get("PIPEDRIVE_STREAM_PUNKTE", "4000"))
    # Anzeigename der zustaendigen Person fuer das Organisationsfeld 'Zustaendig'.
    # Muss exakt einer Option dieses Felds in Pipedrive entsprechen.
    PIPEDRIVE_OWNER = os.environ.get("PIPEDRIVE_OWNER", "")

    # --- Anschreiben und Outlook ---
    # Der Absendername steht in der Signatur des Anschreibens. Das Absenderkonto
    # selbst waehlt bewusst Outlook, damit das System keine Postfachwahl trifft.
    ABSENDER = os.environ.get("SCOUTREF_SENDER_NAME", "")
    ABSENDER_ROLLE = os.environ.get(
        "SCOUTREF_SENDER_ROLE", "Startup Scouting")
    ABSENDER_ORG = os.environ.get("SCOUTREF_SENDER_ORGANIZATION", "")

    # --- Pfade ---
    BASE = os.path.dirname(os.path.abspath(__file__))
    RUNTIME_ROOT = os.environ.get(
        "SCOUTREF_RUNTIME_ROOT", os.path.join(BASE, "runtime"))
    os.makedirs(RUNTIME_ROOT, mode=0o700, exist_ok=True)
    try:
        os.chmod(RUNTIME_ROOT, 0o700)
    except OSError:
        pass
    DATA_ROOT = os.path.join(BASE, "data")
    PUBLIC_DATA_ROOT = os.path.join(DATA_ROOT, "public")
    DEVELOPMENT_DATA_ROOT = os.path.join(DATA_ROOT, "development")
    CONFIG_ROOT = os.path.join(BASE, "config")
    ACTORS_PATH = os.path.join(PUBLIC_DATA_ROOT, "actors.json")
    PUBLIC_THEMES_PATH = os.path.join(PUBLIC_DATA_ROOT, "themes_public.json")
    PIPEDRIVE_MANIFEST_PATH = os.path.join(
        CONFIG_ROOT, "pipedrive_field_manifest.json")
    MEMORY_PATH = os.path.join(RUNTIME_ROOT, "memory_store.json")
    AUDIT_LOG = os.path.join(RUNTIME_ROOT, "audit_log.jsonl")
    OUTREACH_TEMPLATE = os.path.join(BASE, "templates", "anschreiben_template.txt")
    SEED_CORPUS = os.path.join(DEVELOPMENT_DATA_ROOT, "seed_corpus.jsonl")


# ===========================================================================
# Enums
# ===========================================================================
class Recommendation(str, Enum):
    PILOT = "Pilot"          # geeignet fuer Pilotgespraech
    OBSERVE = "beobachten"   # Beobachtungs-Notiz, kein Newsletter-Treffer
    REJECT = "abgelehnt"     # kein ausreichender Match


class Autonomy(str, Enum):
    PROPOSE = "propose"   # nur Vorschlag, alles manuell
    DRAFT = "draft"       # Entwuerfe erzeugen (CRM-Eintrag, Anschreiben) — kein Versand
    ACT = "act"           # reserviert; im Referenzmodell NIE Versand (HITL bleibt Pflicht)


# ===========================================================================
# Datentypen
# ===========================================================================
@dataclass
class Source:
    """Herkunftsnachweis eines Fakts (Provenance)."""
    url: str = ""
    title: str = ""
    note: str = ""
    source_type: str = "unknown"  # official | register | press | database | social
    publisher: str = ""
    published_at: str = ""
    retrieved_at: str = ""
    excerpt: str = ""
    supports: list = field(default_factory=list)
    document_id: str = ""
    source_id: str = ""
    # Semantische Subjektbindung. Eine technisch aufloesbare URL darf nur fuer
    # Aussagen ueber genau dieses Subjekt zaehlen. Im Live-Pfad ist mindestens
    # subject_id oder subject_name neben dem subject_type verpflichtend.
    subject_type: str = ""  # target_organization | candidate_startup | relation
    subject_id: str = ""
    subject_name: str = ""
    # True bedeutet im Live-Pfad: Die URL wurde aus den strukturierten
    # Citation-/Web-Search-Metadaten der Responses API uebernommen. Ein im
    # Modelltext lediglich behaupteter Link setzt dieses Feld nie.
    citation_verified: bool = False
    citation_origin: str = ""  # output_annotation | web_search_source | curated
    resolved_status: str = "not_checked"  # resolved | blocked | technical_error | not_checked | not_checked_budget
    resolved_url: str = ""
    resolved_at: str = ""
    http_status: int = 0
    content_hash: str = ""
    # Quellenunabhaengigkeit wird nicht allein aus verschiedenen URLs
    # abgeleitet. Domain/Familie sowie normalisierte Inhaltsfingerabdruecke
    # helfen, Spiegelungen und syndizierte Pressetexte nicht doppelt zu zaehlen.
    canonical_domain: str = ""
    source_family: str = ""
    text_hash: str = ""
    excerpt_hash: str = ""
    excerpt_verified: bool = False
    # Ausschliesslich vom Resolver berechnet, niemals aus Modell-JSON uebernommen.
    verified_excerpt_hashes: list[str] = field(default_factory=list)
    # exact | fuzzy | "" (nicht gefunden); text_status z. B. pdf_not_parsed.
    excerpt_match_mode: str = ""
    # Unterseite derselben Website, auf der der Auszug gefunden wurde
    matched_subpage_url: str = ""
    text_status: str = ""
    # Kurzer Textausschnitt (normalisiert, hoechstens 600 Zeichen) der Stelle,
    # an der der Resolver den Auszug fand. Er haelt den Stand zum Abrufzeitpunkt
    # fest, damit eine spaetere menschliche Pruefung auch dann nachvollziehbar
    # bleibt, wenn sich die Seite inzwischen geaendert hat.
    matched_context: str = ""
    # N1 (12.11.2026): Quellenabgleich. Wurde der wortgleiche Auszug nicht auf
    # der zitierten, sondern auf einer anderen abgerufenen Seite gefunden, steht
    # hier {"cited_url", "verified_url", "reason"}.
    relocation: dict = field(default_factory=dict)


@dataclass
class Candidate:
    """Ein gescoutetes Startup (Discovery-Output, danach angereichert)."""
    name: str
    description: str = ""
    founded: Optional[int] = None
    region: str = ""              # z.B. "DE", "AT", "CH", "EU", "US"
    location_class: str = ""      # Regional / Bayern / DACH / EU / Ausserhalb
    distance_km: Optional[int] = None
    employees: Optional[int] = None
    funding_stage: str = ""       # Pre-Seed / Seed / Series A ...
    # Sicherheitsgerichteter Standard: Ein Webfund ist nicht automatisch ein
    # Startup. Erst die Verifikationsstufe darf diesen Status setzen.
    company_type: str = "unknown" # startup / scaleup / joint_venture / projekt / ...
    is_service_provider: bool = False
    sectors: list = field(default_factory=list)   # frei konfigurierbare Sektoren
    # Website als Identitaetshilfe; Kontaktfelder sind optionale spaetere
    # Anreicherungen und kein Pflichtteil des kompakten Recherchevertrags.
    website: str = ""
    linkedin: str = ""
    ceo: str = ""                 # Name der Geschaeftsfuehrung
    standort: str = ""            # Ort, so konkret wie oeffentlich auffindbar
    sources: list = field(default_factory=list)    # list[Source]
    steckbrief: dict = field(default_factory=dict)  # Discovery-Recherche (Team, USP, Kunden ...)
    # Identitaet und Evidenz. Im Live-Pfad blockiert ein anderer Status als
    # "verified_startup" jede positive Empfehlung.
    discovery_mode: str = "manual"  # live | synthetic | manual
    verification_status: str = "needs_evidence"
    verification_reasons: list = field(default_factory=list)
    official_url: str = ""
    independent_source_url: str = ""
    last_activity_date: str = ""
    # PUSH-Kontext: Die Ziel-ID bleibt durch die gesamte Pipeline erhalten.
    target_actor_id: str = ""
    target_actor_name: str = ""
    run_id: str = ""
    # Stabiler Schluessel fuer Scout--Verifier-Handoffs. Er wird aus der
    # normalisierten offiziellen URL bzw. ersatzweise dem Namen abgeleitet und
    # darf im Verifikationspass nicht ueber eine Namensheuristik ersetzt werden.
    candidate_id: str = ""
    opportunity_id: str = ""
    opportunity_hypothesis: str = ""
    process_stage: str = ""
    input_stream: str = ""
    transformation: str = ""
    output_application: str = ""
    unresolved_requirements: list = field(default_factory=list)
    # Fortbestand laut Pruefstufe: active | acquired | insolvent | ceased | unknown.
    # Nur "active" erlaubt eine gestuetzte Dimension Unternehmenstyp und Gruendung.
    operating_status: str = ""
    # R2 (11.11.2026): deterministisch abgerufenes Impressum der offiziellen
    # Website: url, company_name_found, register, country, excerpt.
    impressum: dict = field(default_factory=dict)
    # M5 (12.11.2026): Herkunft des Fortbestandsurteils (Modell oder Regel).
    operating_status_basis: str = ""
    evidence_claims: list = field(default_factory=list)
    evidence_matrix: dict = field(default_factory=dict)
    model_usage: list = field(default_factory=list)
    # optionales Ground-Truth-Feld fuer die Evaluation (nur im Korpus gesetzt):
    problem_fit: Optional[bool] = None  # loest es das KONKRETE Problem? (semantisch)


@dataclass
class ActorMatch:
    actor_id: str
    actor_name: str
    score: int
    sufficient: bool
    critical_assessment: str = ""    # Skepsis ZUERST (vor dem Score)
    rationale: str = ""
    exclusions: list = field(default_factory=list)  # ausgeloeste Ausschlusskriterien
    fit: str = "kein"                # spezifisch | thematisch | generell | kein


@dataclass
class Decision:
    candidate: Candidate
    matches: list = field(default_factory=list)       # list[ActorMatch]
    best_actor_id: Optional[str] = None
    best_score: int = 0
    recommendation: Recommendation = Recommendation.REJECT
    confidence: float = 0.0
    confidence_is_calibrated: bool = False
    evidence_coverage: float = 0.0
    evidence_grade: str = "nicht_ausreichend"
    quality_gates: list = field(default_factory=list)
    operationally_eligible: bool = False
    # Explizit getrennt, damit technische oder budgetbedingt ungepruefte Faelle
    # in der Evaluation nie als fachliche Enthaltung gezaehlt werden.
    evaluation_status: str = "abstention"  # completed | abstention | not_checked_budget | technical_error
    abstained: bool = False
    abstain_reason: str = ""
    # Einheitlicher fachlicher Zielzustand (Kap. 5, FA6; Kap. 6, Abb. Entscheidungswege):
    # empfehlung | ablehnung | enthaltung | technischer_fehler
    decision_state: str = "enthaltung"
    decision_state_reason: str = ""
    trace: list = field(default_factory=list)         # Agenten-Trace (Transparenz)
    audit: dict = field(default_factory=dict)
    memory: dict = field(default_factory=dict)
    general_fit: list = field(default_factory=list)   # Akteure mit generellem Fit

    def to_dict(self) -> dict:
        d = asdict(self)
        d["recommendation"] = self.recommendation.value
        return d


# ===========================================================================
# Text-Utilities (deterministisch, ohne LLM)
# ===========================================================================
_UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                         "Ä": "ae", "Ö": "oe", "Ü": "ue"})

STOPWORDS = {
    "und", "oder", "der", "die", "das", "ein", "eine", "einen", "fuer", "mit",
    "von", "im", "in", "auf", "zu", "zur", "zum", "den", "dem", "des", "ist",
    "sind", "wir", "sie", "es", "auch", "als", "aus", "bei", "an", "the", "and",
    "for", "of", "to", "a", "is", "are", "we", "kein", "nicht", "statt", "ohne",
}


def normalize(text: str) -> str:
    text = (text or "").lower().translate(_UMLAUT)
    return re.sub(r"[^a-z0-9 ]+", " ", text)


def tokenize(text: str) -> set:
    toks = normalize(text).split()
    return {t for t in toks if len(t) > 2 and t not in STOPWORDS}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def overlap_count(a: set, b: set) -> int:
    return len(a & b)


# ===========================================================================
# LLM-Client (optional; Offline-Modus oder expliziter Live-Modus)
# ===========================================================================
# Wiederholung bei voruebergehender Ueberlastung des Anbieters, fuer beide
# Anbieter gleich: Das Anthropic-SDK wiederholt mit max_retries=2, der
# OpenAI-Pfad ebenso hoechstens zweimal. Wiederholt werden nur Antworten, die
# keine Verarbeitung belegen (429, 500, 502, 503, 504) und Verbindungsfehler
# vor einer Antwort. Eine Zeitueberschreitung wird NICHT wiederholt, weil der
# Anbieter die Anfrage dann moeglicherweise schon bearbeitet und berechnet.
TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}
MAX_TRANSPORT_RETRIES = 2


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _transient_retry_delay(error: Exception, retries: int):
    if retries >= MAX_TRANSPORT_RETRIES:
        return None
    if isinstance(error, urllib.error.HTTPError):
        if int(getattr(error, "code", 0) or 0) not in TRANSIENT_HTTP_CODES:
            return None
        header = ""
        try:
            header = str((error.headers or {}).get("Retry-After") or "")
        except Exception:
            header = ""
        try:
            return min(30.0, max(1.0, float(header)))
        except ValueError:
            return 5.0 * (retries + 1)
    if isinstance(error, urllib.error.URLError):
        reason = getattr(error, "reason", None)
        if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason):
            return None
        return 5.0 * (retries + 1)
    return None


class LLMClient:
    """
    Duenner, SDK-unabhaengiger Wrapper um die OpenAI Responses API.

    Ein bewusst offline gestarteter Lauf arbeitet deterministisch. Wurde
    dagegen Live-Betrieb angefordert, fuehrt ein fehlender OPENAI_API_KEY zu
    einem kontrollierten Fehler und niemals zu einem stillen Trockenlauf.
    Jeder Live-Aufruf protokolliert angefordertes und tatsaechliches Budget,
    Modell, Tokens, Werkzeugaufrufe und strukturierte Webquellen. Nur diese
    strukturierten Quellen duerfen spaeter Live-Evidenz werden.
    """
    def __init__(self, live: bool = False, resource_broker=None,
                 reasoning_effort: Optional[str] = None):
        # Anbieter folgt der konfigurierten Modellkennung (claude-* = Anthropic).
        self.provider = ("anthropic" if str(Config.MODEL).startswith("claude-")
                         else "openai")
        self.api_key = os.environ.get(
            "ANTHROPIC_API_KEY" if self.provider == "anthropic"
            else "OPENAI_API_KEY", "").strip()
        self.requested_live = bool(live)
        self.live = bool(self.requested_live and self.api_key)
        self.last_usage = None
        self.last_citations = []
        self.last_error = ""
        self.usage_records = []
        self.resource_broker = resource_broker
        self.reasoning_effort = reasoning_effort or Config.REASONING_EFFORT

    def attach_resource_broker(self, resource_broker) -> None:
        self.resource_broker = resource_broker

    def set_reasoning_effort(self, reasoning_effort: str | None) -> None:
        self.reasoning_effort = reasoning_effort or Config.REASONING_EFFORT

    def available(self) -> bool:
        return self.live and bool(self.api_key)

    def live_configuration_error(self) -> str:
        if self.requested_live and not self.api_key:
            return ("ANTHROPIC_API_KEY" if self.provider == "anthropic"
                    else "OPENAI_API_KEY") + " fehlt fuer den angeforderten Live-Lauf"
        return ""

    @staticmethod
    def _normalise_url(url: str) -> str:
        try:
            parsed = urllib.parse.urlsplit(str(url or "").strip())
            host = (parsed.hostname or "").lower()
            if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
                return ""
            # Queryparameter koennen die Dokumentidentitaet bestimmen (z. B.
            # ?document=17). Auch verschiedene Pfade werden nicht vereinigt.
            port = f":{parsed.port}" if parsed.port else ""
            return urllib.parse.urlunsplit((parsed.scheme.lower(), host + port,
                                           parsed.path or "/", parsed.query, ""))
        except Exception:
            return ""

    @staticmethod
    def _extract_text_and_citations(response: dict) -> tuple[str, list, int]:
        parts, citations, tool_calls = [], [], 0
        for item in response.get("output", []) or []:
            item_type = item.get("type", "") if isinstance(item, dict) else ""
            if item_type == "web_search_call":
                tool_calls += 1
                action = item.get("action") or {}
                for source in action.get("sources", []) or []:
                    if not isinstance(source, dict) or not source.get("url"):
                        continue
                    citations.append({
                        "url": source.get("url", ""),
                        "title": source.get("title", ""),
                        "origin": "web_search_source",
                    })
            if item_type != "message":
                continue
            for content in item.get("content", []) or []:
                if not isinstance(content, dict) or content.get("type") != "output_text":
                    continue
                text = content.get("text")
                if isinstance(text, str):
                    parts.append(text)
                for annotation in content.get("annotations", []) or []:
                    if not isinstance(annotation, dict):
                        continue
                    if annotation.get("type") == "url_citation" and annotation.get("url"):
                        citations.append({
                            "url": annotation.get("url", ""),
                            "title": annotation.get("title", ""),
                            "origin": "output_annotation",
                        })
        dedup = {}
        for citation in citations:
            key = LLMClient._normalise_url(citation.get("url", ""))
            if not key:
                continue
            current = dedup.get(key)
            if current is None or citation.get("origin") == "output_annotation":
                dedup[key] = citation
        return "".join(parts), list(dedup.values()), tool_calls

    @staticmethod
    def _extract_search_log(response: dict) -> list:
        """Nur Protokoll: jede web_search_call-Aktion unveraendert (ohne Quellenliste)
        plus deren Treffer als Titel und URL. Aendert weder Anfrage noch Auswertung."""
        log = []
        for item in response.get("output", []) or []:
            if not isinstance(item, dict) or item.get("type") != "web_search_call":
                continue
            action = dict(item.get("action") or {})
            sources = action.pop("sources", None) or []
            log.append({"id": item.get("id", ""), "status": item.get("status", ""),
                        "action": action,
                        "results": [{"title": src.get("title", ""), "url": src.get("url", "")}
                                    for src in sources if isinstance(src, dict)]})
        return log

    def _record_failure(self, model: str, purpose: str, max_tokens: int,
                        max_tool_calls: int, error: Exception,
                        latency_ms: float = 0.0,
                        record_broker: bool = True,
                        request_metadata: dict | None = None) -> None:
        self.last_error = f"{type(error).__name__}: {error}"
        record = {
            "call_id": str(uuid.uuid4()),
            "response_id": "",
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "purpose": purpose,
            "status": "technical_failure",
            "error_type": type(error).__name__,
            "model_requested": model,
            "model_returned": "",
            "max_output_tokens": max_tokens,
            "max_tool_calls": max_tool_calls,
            "reasoning_effort": self.reasoning_effort,
            "input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "cached_input_tokens": 0,
            "tool_calls": 0,
            "source_count": 0,
        }
        record.update(dict(request_metadata or {}))
        self.last_usage = record
        self.last_citations = []
        self.usage_records.append(record)
        if self.resource_broker and record_broker:
            self.resource_broker.record_model_usage(record, latency_ms=latency_ms)

    def complete(self, model: str, system: str, user: str,
                 max_tokens: int = 1024, tools: Optional[list] = None,
                 max_tool_calls: Optional[int] = None, purpose: str = "",
                 reasoning_effort: Optional[str] = None) -> str:
        if not self.available():
            # Aufrufer entscheiden anhand von requested_live, ob ein expliziter
            # Offline-Pfad zulaessig ist. Ein angeforderter Live-Lauf darf nie
            # unbemerkt zu einer Heuristik werden.
            return ""

        tool_budget = max(0, int(max_tool_calls if max_tool_calls is not None
                                 else Config.WEB_SEARCH_MAX_USES))
        started = time.perf_counter()
        effective_reasoning = reasoning_effort or self.reasoning_effort
        if str(model).startswith("claude-"):
            return self._complete_anthropic(
                model=model, system=system, user=user, max_tokens=max_tokens,
                tools=tools, tool_budget=tool_budget, purpose=purpose,
                effort=effective_reasoning, started=started)
        payload = {
            "model": model,
            "instructions": system,
            "input": user,
            "max_output_tokens": int(max_tokens),
            "reasoning": {"effort": effective_reasoning},
            "store": False,
        }
        if tools:
            # Die bisherigen Aufrufer geben lediglich an, dass Websuche erlaubt
            # ist. Provider-spezifische Toolnamen werden hier bewusst nicht
            # weitergereicht.
            payload["tools"] = [{"type": "web_search",
                                 "search_context_size": "medium"}]
            payload["max_tool_calls"] = tool_budget
            payload["include"] = ["web_search_call.action.sources"]
        request_metadata = {
            "api_contract": Config.API_CONTRACT,
            "api_endpoint": Config.OPENAI_RESPONSES_URL,
            "prompt_contract_version": Config.PROMPT_CONTRACT_VERSION,
            "system_prompt_sha256": "sha256-" + hashlib.sha256(
                str(system or "").encode("utf-8")).hexdigest(),
            "user_prompt_sha256": "sha256-" + hashlib.sha256(
                str(user or "").encode("utf-8")).hexdigest(),
            "request_payload_sha256": "sha256-" + hashlib.sha256(
                json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")).hexdigest(),
            "web_search_context_size": "medium" if tools else "none",
            "web_search_tool_version": "openai_web_search" if tools else "none",
        }
        if self.resource_broker:
            estimated = self.resource_broker.estimate_input_tokens(system, user)
            allowed, reason = self.resource_broker.authorize_model_call(
                estimated_input_tokens=estimated,
                max_output_tokens=int(max_tokens),
                max_web_calls=tool_budget if tools else 0,
                model=model,
                purpose=purpose,
            )
            if not allowed:
                self._record_failure(
                    model, purpose, max_tokens, tool_budget,
                    RuntimeError(reason), latency_ms=0.0,
                    record_broker=False, request_metadata=request_metadata)
                return ""

        request = urllib.request.Request(
            Config.OPENAI_RESPONSES_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        retries = 0
        while True:
            try:
                with urllib.request.urlopen(
                        request, timeout=Config.OPENAI_TIMEOUT_SECONDS,
                        context=verified_tls_context()) as response:
                    data = json.loads(response.read().decode("utf-8"))
                break
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                    ValueError, OSError) as error:
                delay = _transient_retry_delay(error, retries)
                if delay is None:
                    request_metadata["transport_retries"] = retries
                    self._record_failure(
                        model, purpose, max_tokens, tool_budget, error,
                        latency_ms=(time.perf_counter() - started) * 1000,
                        request_metadata=request_metadata)
                    return ""
                retries += 1
                _sleep(delay)
        request_metadata["transport_retries"] = retries

        text, citations, tool_calls = self._extract_text_and_citations(data)
        usage = data.get("usage") or {}
        input_details = usage.get("input_tokens_details") or {}
        output_details = usage.get("output_tokens_details") or {}
        record = {
            "call_id": str(uuid.uuid4()),
            "response_id": data.get("id", ""),
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "purpose": purpose,
            "status": data.get("status", "completed"),
            "incomplete_reason": (data.get("incomplete_details") or {}).get("reason", ""),
            "model_requested": model,
            "model_returned": data.get("model", model),
            "max_output_tokens": int(max_tokens),
            "max_tool_calls": tool_budget if tools else 0,
            "reasoning_effort": effective_reasoning,
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "reasoning_tokens": int(output_details.get("reasoning_tokens") or 0),
            "cached_input_tokens": int(input_details.get("cached_tokens") or 0),
            "tool_calls": tool_calls,
            "source_count": len(citations),
            "search_log": self._extract_search_log(data),
        }
        record.update(request_metadata)
        self.last_usage = record
        self.last_citations = citations
        self.last_error = ""
        self.usage_records.append(record)
        if self.resource_broker:
            self.resource_broker.record_model_usage(
                record, latency_ms=(time.perf_counter() - started) * 1000)
        return text

    def _complete_anthropic(self, *, model: str, system: str, user: str,
                            max_tokens: int, tools, tool_budget: int,
                            purpose: str, effort: str, started: float) -> str:
        """Gleicher Aufrufvertrag wie der OpenAI-Pfad, Anbieter Anthropic."""
        import llm_anthropic
        request_metadata = {
            "api_contract": llm_anthropic.API_CONTRACT,
            "api_endpoint": llm_anthropic.ANTHROPIC_API_URL + "/v1/messages",
            "prompt_contract_version": Config.PROMPT_CONTRACT_VERSION,
            "system_prompt_sha256": "sha256-" + hashlib.sha256(
                str(system or "").encode("utf-8")).hexdigest(),
            "user_prompt_sha256": "sha256-" + hashlib.sha256(
                str(user or "").encode("utf-8")).hexdigest(),
            "request_payload_sha256": "sha256-" + hashlib.sha256(json.dumps({
                "model": model, "system": system, "user": user,
                "max_tokens": int(max_tokens), "effort": effort,
                "web_search_max_uses": tool_budget if tools else 0,
            }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
            "web_search_context_size": "anthropic_web_search" if tools else "none",
            "web_search_tool_version": llm_anthropic.WEB_SEARCH_TOOL_VERSION if tools else "none",
        }
        if self.resource_broker:
            estimated = self.resource_broker.estimate_input_tokens(system, user)
            allowed, reason = self.resource_broker.authorize_model_call(
                estimated_input_tokens=estimated,
                max_output_tokens=int(max_tokens),
                max_web_calls=tool_budget if tools else 0,
                model=model, purpose=purpose)
            if not allowed:
                self._record_failure(
                    model, purpose, max_tokens, tool_budget,
                    RuntimeError(reason), latency_ms=0.0,
                    record_broker=False, request_metadata=request_metadata)
                return ""
        try:
            result = llm_anthropic.complete(
                api_key=self.api_key, model=model, system=system, user=user,
                max_tokens=int(max_tokens), effort=effort,
                tool_budget=tool_budget, use_web=bool(tools),
                timeout=float(Config.OPENAI_TIMEOUT_SECONDS))
        except Exception as error:  # Netzwerk-, API- oder Paketfehler
            self._record_failure(
                model, purpose, max_tokens, tool_budget, error,
                latency_ms=(time.perf_counter() - started) * 1000,
                request_metadata=request_metadata)
            return ""
        record = {
            "call_id": str(uuid.uuid4()),
            "response_id": result["response_id"],
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "purpose": purpose,
            "status": result["status"],
            "incomplete_reason": result["incomplete_reason"],
            "model_requested": model,
            "model_returned": result["model_returned"],
            "max_output_tokens": int(max_tokens),
            "max_tool_calls": tool_budget if tools else 0,
            "reasoning_effort": effort,
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "reasoning_tokens": 0,
            "cached_input_tokens": result["cached_input_tokens"],
            "tool_calls": result["tool_calls"],
            "source_count": len(result["citations"]),
            "search_log": result.get("search_log", []),
        }
        record.update(request_metadata)
        self.last_usage = record
        self.last_citations = result["citations"]
        self.last_error = ""
        self.usage_records.append(record)
        if self.resource_broker:
            self.resource_broker.record_model_usage(
                record, latency_ms=(time.perf_counter() - started) * 1000)
        return result["text"]

    def ground_sources(self, sources: list) -> list:
        """Markiert nur durch strukturierte API-Metadaten belegte URLs.

        Nicht belegte modellgenerierte Quellen werden im Live-Pfad verworfen.
        Die Funktion veraendert die uebergebenen Source-Objekte nicht ausserhalb
        der zurueckgegebenen Liste.
        """
        by_url = {self._normalise_url(item.get("url", "")): item
                  for item in (self.last_citations or [])
                  if self._normalise_url(item.get("url", ""))}
        grounded = []
        for source in sources or []:
            citation = by_url.get(self._normalise_url(getattr(source, "url", "")))
            if not citation:
                continue
            source.citation_verified = True
            source.citation_origin = citation.get("origin", "")
            if not getattr(source, "title", ""):
                source.title = citation.get("title", "")
            grounded.append(source)
        return grounded

    def usage_ledger(self) -> list[dict]:
        return [dict(record) for record in self.usage_records]

    def cost_estimate(self) -> dict:
        """Grobe Kosten-Schaetzung des letzten Aufrufs in USD (nur Anzeige)."""
        u = getattr(self, "last_usage", None)
        if not u:
            return {}
        model = u.get("model_returned") or u.get("model_requested") or ""
        pin, pout = Config.PRICES.get(model, Config.PRICES.get(
            u.get("model_requested", ""), (0.0, 0.0)))
        usd = (u["input_tokens"] / 1e6 * pin + u["output_tokens"] / 1e6 * pout
               + u["tool_calls"] * Config.WEB_SEARCH_PRICE)
        return {"tokens_in": u["input_tokens"], "tokens_out": u["output_tokens"],
                "reasoning_tokens": u.get("reasoning_tokens", 0),
                "websuchen": u["tool_calls"], "modell": model,
                "kosten_usd_ca": round(usd, 4),
                "budget_output": u.get("max_output_tokens", 0),
                "budget_tools": u.get("max_tool_calls", 0),
                "status": u.get("status", "")}
