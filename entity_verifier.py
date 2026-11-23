"""Deterministische Identitaets- und Evidenzpruefung fuer Webfunde.

Die Websuche darf Kandidaten vorschlagen, aber nicht selbst ihren Status
festlegen. Dieses Modul prueft deshalb ausschliesslich strukturierte, spaeter
auditierbare Signale. Ein unvollstaendiger Webfund wird nicht positiv bewertet,
sondern erhaelt ``needs_evidence``.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from urllib.parse import urlparse
import re

from evidence_subjects import subject_matches


# R3 (11.11.2026): Scale-up entfaellt als zulaessiger Typ; Startups und
# Ausgruendungen bis hoechstens zehn Jahre nach Gruendung.
ALLOWED_ENTITY_TYPES = {"startup", "spin_off"}
DACH_COUNTRIES = {"DE", "AT", "CH"}
MAX_STARTUP_AGE_YEARS = 10
EXCLUSION_PREFIX = "Ausschluss: "


def reference_year() -> int:
    """Stichtagsjahr der Altersgrenze: Jahr des Datenstands (Config.DATA_VINTAGE)."""
    try:
        from core import Config
        return int(str(Config.DATA_VINTAGE).split("-", 1)[0])
    except Exception:  # pragma: no cover - nur ohne core
        import datetime
        return datetime.date.today().year


# R3 (11.11.2026, David): Auch ein bestaetigter Register- oder Firmenbucheintrag
# belegt das Gruendungsjahr ("eingetragen", "Eintragung", "registered", "incorporated").
_FOUNDED_WORDS = re.compile(
    r"gegr[üu]nde|gr[üu]ndung|founded|established|spin[- ]?off|spin[- ]?out|ausgr[üu]nd"
    r"|eingetragen|eintragung|registered|incorporated|incorporation", re.I)


def verified_candidate_sources(candidate) -> list:
    """Quellen ueber das Startup, im Live-Pfad nur abgerufen und mit gefundenem Auszug."""
    live_mode = getattr(candidate, "discovery_mode", "") == "live"
    result = []
    for s in getattr(candidate, "sources", None) or []:
        if not _valid_http_url(getattr(s, "url", "")):
            continue
        if not subject_matches(s, subject_type="candidate_startup",
                               subject_id=str(getattr(candidate, "candidate_id", "") or ""),
                               subject_name=str(getattr(candidate, "name", "") or ""),
                               strict=live_mode):
            continue
        if live_mode and not (bool(getattr(s, "citation_verified", False))
                              and getattr(s, "resolved_status", "") == "resolved"
                              and bool(getattr(s, "excerpt_verified", False))):
            continue
        result.append(s)
    return result


def founding_source(candidate, sources=None):
    """R3: erste gepruefte Quelle, deren Auszug das Gruendungsjahr mit Gruendungs- oder
    Registerwort nennt; sonst None."""
    founded = getattr(candidate, "founded", None)
    if not founded:
        return None
    for source in (verified_candidate_sources(candidate) if sources is None else sources):
        text = str(getattr(source, "excerpt", "") or "")
        if str(founded) in text and _FOUNDED_WORDS.search(text):
            return source
    # Gepruefte Impressumseite (R2) mit Eintragungsdatum im Auszug.
    imp = dict(getattr(candidate, "impressum", None) or {})
    text = str(imp.get("excerpt") or "")
    if (imp.get("company_name_found") and imp.get("register") and _valid_http_url(imp.get("url", ""))
            and str(founded) in text and _FOUNDED_WORDS.search(text)):
        from types import SimpleNamespace
        return SimpleNamespace(source_id="impressum", url=imp["url"], excerpt=text)
    return None
BLOCKED_ENTITY_TYPES = {
    "joint_venture", "corporate_division", "initiative", "research_project",
    "project", "product", "association", "established_company", "service_provider",
    "non_existing",
}
SOCIAL_OR_SEARCH_HOSTS = {
    "linkedin.com", "www.linkedin.com", "google.com", "www.google.com",
    "bing.com", "www.bing.com", "facebook.com", "www.facebook.com",
    "instagram.com", "www.instagram.com", "x.com", "www.x.com",
}
INVALID_SUFFIXES = (".example", ".invalid", ".test", ".localhost")


def _host(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower().rstrip(".")
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _valid_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        host = _host(url)
        return (parsed.scheme in {"http", "https"} and bool(host)
                and not host.endswith(INVALID_SUFFIXES))
    except Exception:
        return False


def _same_site(a: str, b: str) -> bool:
    ha, hb = _host(a), _host(b)
    return bool(ha and hb and (ha == hb or ha.endswith("." + hb) or hb.endswith("." + ha)))


def source_family(source) -> str:
    """Konservative Quellenfamilie fuer Unabhaengigkeitspruefungen.

    Ein expliziter Publisher/Familienwert ist fuehrend. Fehlt er, wird die
    kanonische Domain verwendet. Der Wert belegt keine redaktionelle
    Unabhaengigkeit; er kann nur offensichtliche Gleichheit ausschliessen.
    """
    explicit = (getattr(source, "source_family", "") or
                getattr(source, "publisher", "") or "")
    normalised = re.sub(r"[^a-z0-9]+", "-", explicit.casefold()).strip("-")
    return normalised or getattr(source, "canonical_domain", "") or _host(
        getattr(source, "resolved_url", "") or getattr(source, "url", ""))


def _page_url(source) -> str:
    """Seite, auf der der Auszug technisch gefunden wurde (Fundseite), sonst die zitierte URL."""
    return str(getattr(source, "resolved_url", "") or getattr(source, "url", "") or "")


def is_independent_source(official_source, other_source) -> bool:
    """Schliesst gleiche Sites, Publisher und duplizierte Inhalte aus."""
    if official_source is None or other_source is None:
        return False
    official_url = (getattr(official_source, "resolved_url", "") or
                    getattr(official_source, "url", ""))
    other_url = (getattr(other_source, "resolved_url", "") or
                 getattr(other_source, "url", ""))
    if not official_url or not other_url or _same_site(official_url, other_url):
        return False
    family_a, family_b = source_family(official_source), source_family(other_source)
    if family_a and family_b and family_a == family_b:
        return False
    # Volltext-, Rohdokument- und Auszugfingerabdruecke werden getrennt
    # verglichen. Ein identisch uebernommener Pressetext zaehlt nicht als
    # unabhaengige Bestaetigung, auch wenn er auf einer anderen Domain steht.
    for attribute in ("text_hash", "content_hash", "excerpt_hash"):
        value_a = str(getattr(official_source, attribute, "") or "")
        value_b = str(getattr(other_source, attribute, "") or "")
        if value_a and value_b and value_a == value_b:
            return False
    return True


@dataclass
class VerificationResult:
    status: str
    entity_type: str
    official_url: str
    independent_source_url: str
    reasons: list
    checks: dict

    def to_dict(self) -> dict:
        return asdict(self)


class EntityVerifier:
    """Fail-closed-Pruefung ohne Netzwerkzugriff.

    Erreichbarkeit wird bewusst nicht aus einem einzelnen HTTP-Status abgeleitet:
    Anti-Bot-Schutz und zeitweise Fehler waeren sonst falsche Ausschlussgruende.
    Stattdessen sind eine offizielle Quelle, ein unabhaengiger Beleg und
    Behauptung-zu-Quelle-Zuordnungen Pflicht. Die URLs koennen in einem
    separaten Integrationslauf zusaetzlich technisch aufgeloest werden.
    """

    def verify(self, candidate) -> VerificationResult:
        # Synthetische Entwicklungsfaelle bleiben als solche lauffaehig, sind
        # aber ausdruecklich kein Nachweis der Live-Qualitaet.
        if getattr(candidate, "discovery_mode", "") == "synthetic":
            result = VerificationResult(
                status="synthetic_case",
                entity_type=(getattr(candidate, "company_type", "") or "unknown"),
                official_url="",
                independent_source_url="",
                reasons=["synthetischer Entwicklungsfall; keine reale Existenzpruefung"],
                checks={"synthetic": True},
            )
            candidate.verification_status = result.status
            candidate.verification_reasons = list(result.reasons)
            return result

        entity_type = (getattr(candidate, "company_type", "") or "unknown").strip().lower()
        aliases = {
            "joint venture": "joint_venture", "jv": "joint_venture",
            "corporate": "corporate_division", "division": "corporate_division",
            "research": "research_project", "forschungsprojekt": "research_project",
            "spin-off": "spin_off", "spinoff": "spin_off",
            "established": "established_company", "etabliert": "established_company",
            "dienstleister": "service_provider",
        }
        entity_type = aliases.get(entity_type, entity_type)

        live_mode = getattr(candidate, "discovery_mode", "") == "live"
        all_sources = [s for s in (getattr(candidate, "sources", None) or [])
                       if _valid_http_url(getattr(s, "url", ""))]
        candidate_sources = [s for s in all_sources if subject_matches(
            s, subject_type="candidate_startup",
            subject_id=str(getattr(candidate, "candidate_id", "") or ""),
            subject_name=str(getattr(candidate, "name", "") or ""),
            strict=live_mode,
        )]
        sources = [s for s in candidate_sources if (
            not live_mode or (
                bool(getattr(s, "citation_verified", False))
                and getattr(s, "resolved_status", "") == "resolved"
                and bool(getattr(s, "excerpt_verified", False))
            )
        )]
        # Der getrennte Verifikationspass ist fuehrend. Eine nur in der
        # Discovery behauptete Website darf eine spaeter belegte offizielle URL
        # nicht ueberschreiben.
        website = (getattr(candidate, "official_url", "") or
                   getattr(candidate, "website", "") or "").strip()
        official = ""
        official_source = None
        if _valid_http_url(website):
            for source in sources:
                claims = {str(x).strip().lower()
                          for x in (getattr(source, "supports", None) or [])}
                # 12.11.2026: Massgeblich ist die Seite, auf der der Auszug steht
                # (nach Quellenabgleich die Fundseite), wie in is_independent_source.
                page = _page_url(source)
                host = _host(page)
                if ("identity" in claims and host not in SOCIAL_OR_SEARCH_HOSTS
                        and _same_site(website, page)):
                    official = website
                    official_source = source
                    break
        if not official:
            for source in sources:
                claims = {str(x).strip().lower()
                          for x in (getattr(source, "supports", None) or [])}
                relocated_elsewhere = str((getattr(source, "relocation", None) or {}).get("reason", "")).endswith("_andere_domain")
                if (source.source_type == "official" and "identity" in claims and not relocated_elsewhere
                        and _host(_page_url(source)) not in SOCIAL_OR_SEARCH_HOSTS):
                    official = _page_url(source)
                    official_source = source
                    break

        independent = ""
        for source in sources:
            host = _host(_page_url(source))
            independent_kind = source.source_type in {"register", "press", "database", "public_body"}
            claims = {str(x).strip().lower()
                      for x in (getattr(source, "supports", None) or [])}
            identity_evidence = bool({"identity", "founded"} & claims)
            if (host not in SOCIAL_OR_SEARCH_HOSTS
                    and is_independent_source(official_source, source)
                    and independent_kind and identity_evidence):
                independent = source.url
                break

        supported_claims = set()
        excerpts = 0
        for source in sources:
            supported_claims.update(str(x).strip().lower()
                                    for x in (getattr(source, "supports", None) or []) if str(x).strip())
            if len((getattr(source, "excerpt", "") or "").strip()) >= 20:
                excerpts += 1

        # R2: Impressum der offiziellen Website mit Firmenname und Registermerkmal
        # belegt Identitaet und Existenz; eine unabhaengige Quelle ist dann nicht noetig.
        impressum = dict(getattr(candidate, "impressum", None) or {})
        impressum_ok = bool(impressum.get("company_name_found") and impressum.get("register")
                            and _valid_http_url(impressum.get("url", ""))
                            and (not website or _same_site(website, impressum.get("url", ""))))
        if impressum_ok:
            official = official or website or impressum["url"]
            independent = independent or impressum["url"]
            supported_claims.add("identity")
            excerpts += 1  # der Impressumsauszug ist ein technisch gefundener Beleg
        # R3: Gruendungsjahr aus jeder abgerufenen Quelle mit gefundenem Auszug.
        founded = getattr(candidate, "founded", None)
        founded_evidenced = "founded" in supported_claims
        if founded and not founded_evidenced:
            founded_evidenced = founding_source(candidate, sources) is not None

        reasons = []
        blocked = entity_type in BLOCKED_ENTITY_TYPES
        if entity_type == "scaleup":
            reasons.append(EXCLUSION_PREFIX + "Scale-up, kein Startup")
        elif entity_type not in ALLOWED_ENTITY_TYPES:
            reasons.append("Unternehmenstyp nicht als Startup oder Ausgruendung belegt")
        if blocked:
            reasons.append(f"Unternehmenstyp '{entity_type}' ist im Startup-Modus ausgeschlossen")
        if not official:
            reasons.append("keine identitaetsgleiche offizielle Quelle")
        if not independent:
            reasons.append("kein unabhaengiger Existenz- oder Gruendungsbeleg")
        if founded is None:
            reasons.append("Gruendungsjahr nicht belegt")
        elif not founded_evidenced:
            reasons.append("Gruendungsjahr keiner Quelle auf Aussageebene zugeordnet")
        elif int(founded) < reference_year() - MAX_STARTUP_AGE_YEARS:
            reasons.append(EXCLUSION_PREFIX + "aelter als zehn Jahre (kein Startup mehr)")
        # R1: nur Sitz in Deutschland, Oesterreich oder der Schweiz.
        # Ein belegter Sitz ausserhalb DACH im eigenen Impressum (Firmenname
        # gefunden, gleiche Website) schliesst auch ohne Registermerkmal aus.
        # Ein DACH-Sitz gilt nur mit geprueftem Impressum (R2) als belegt.
        impressum_own = bool(impressum.get("company_name_found")
                             and _valid_http_url(impressum.get("url", ""))
                             and (not website or _same_site(website, impressum.get("url", ""))))
        raw_country = str(impressum.get("country") or "").upper()
        if impressum_ok:
            country = raw_country
        elif impressum_own and raw_country == "OUTSIDE_DACH":
            country = raw_country
        else:
            country = ""
        if country == "OUTSIDE_DACH" or (country and country not in DACH_COUNTRIES):
            reasons.append(EXCLUSION_PREFIX + "Sitz nicht in Deutschland, Oesterreich oder der Schweiz")
        elif country not in DACH_COUNTRIES:
            reasons.append("Sitz in Deutschland, Oesterreich oder der Schweiz nicht belegt")
        if not ({"identity", "product"} <= supported_claims):
            reasons.append("Identitaet und Produktfaehigkeit nicht beide auf Aussageebene belegt")
        official_claims = {
            str(x).strip().lower()
            for x in (getattr(official_source, "supports", None) or [])
        }
        # K1 (11.11.2026): Die Produktfaehigkeit darf auf jeder Seite derselben
        # offiziellen Website belegt sein, nicht nur auf der Identitaetsseite.
        # "Dieselbe Website" wie oben (_same_site); im Live-Modus enthaelt
        # ``sources`` nur abgerufene Quellen mit gefundenem Auszug.
        if official and "product" not in official_claims:
            for source in sources:
                claims = {str(x).strip().lower()
                          for x in (getattr(source, "supports", None) or [])}
                if ("product" in claims and _host(source.url) not in SOCIAL_OR_SEARCH_HOSTS
                        and _same_site(official, source.url)):
                    official_claims.add("product")
                    break
        if official and "product" not in official_claims:
            reasons.append("Produktfaehigkeit nicht durch die offizielle Quelle belegt")
        if excerpts < 2:
            reasons.append("weniger als zwei konkrete Belegauszuege")

        if blocked or any(reason.startswith(EXCLUSION_PREFIX) for reason in reasons):
            status = "not_a_startup"
        elif not reasons:
            status = "verified_startup"
        else:
            status = "needs_evidence"

        result = VerificationResult(
            status=status,
            entity_type=entity_type,
            official_url=official,
            independent_source_url=independent,
            reasons=reasons,
            checks={
                "valid_sources": len(sources),
                "submitted_sources": len(all_sources),
                "candidate_bound_sources": len(candidate_sources),
                "subject_rejected_sources": len(all_sources) - len(candidate_sources),
                "native_resolved_sources": len(sources) if live_mode else None,
                "unique_domains": len({_host(s.url) for s in sources}),
                "unique_source_families": len({source_family(s) for s in sources
                                               if source_family(s)}),
                "supported_claims": sorted(supported_claims),
                "evidence_excerpts": excerpts,
            },
        )
        candidate.company_type = entity_type
        candidate.verification_status = status
        candidate.verification_reasons = list(reasons)
        candidate.official_url = official
        candidate.independent_source_url = independent
        return result
