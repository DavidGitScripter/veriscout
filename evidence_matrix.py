"""Relationale Evidenzmatrix fuer Startup--Zielorganisations-Beziehungen.

Die Matrix bewertet nicht, ob ein Startup allgemein interessant klingt. Sie
prueft, ob eine konkrete Beziehung aus Zielprozess, Input, Anbieterfaehigkeit,
Transformationsmechanismus und nutzbarem Output durch Aussageevidenz getragen
wird. Ein fehlendes Glied blockiert im Live-Pfad eine positive Empfehlung.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import Enum
from urllib.parse import urlsplit
from evidence_resolver import _normalise_claim

from evidence_subjects import (
    expected_subject,
    normalise_subject_type,
    subject_binding,
    subject_matches,
)


class EvidenceStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    CONTRADICTED = "contradicted"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class EvidenceCell:
    dimension: str
    claim: str
    status: EvidenceStatus
    source_ids: list[str] = field(default_factory=list)
    excerpts: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    # direct = unmittelbar belegt; derived = aus belegtem Prozessschritt und
    # Fachbeleg abgeleitet (nur Inputstrom, siehe _input_stream_cell).
    basis: str = "direct"

    def to_dict(self) -> dict:
        value = asdict(self)
        value["status"] = self.status.value
        return value


@dataclass
class RelationalEvidenceMatrix:
    relation_id: str
    candidate_id: str
    target_actor_id: str
    opportunity_id: str
    cells: list[EvidenceCell]
    required_dimensions: list[str]
    blocking_dimensions: list[str]
    contradictions: list[str]
    evidence_coverage: float
    decision_state: str
    development_only: bool = False
    claim_manifest: list[dict] = field(default_factory=list)

    def cell(self, dimension: str) -> EvidenceCell | None:
        return next((item for item in self.cells if item.dimension == dimension), None)

    def to_dict(self) -> dict:
        return {
            "relation_id": self.relation_id,
            "candidate_id": self.candidate_id,
            "target_actor_id": self.target_actor_id,
            "opportunity_id": self.opportunity_id,
            "cells": [item.to_dict() for item in self.cells],
            "required_dimensions": list(self.required_dimensions),
            "blocking_dimensions": list(self.blocking_dimensions),
            "contradictions": list(self.contradictions),
            "evidence_coverage": self.evidence_coverage,
            "decision_state": self.decision_state,
            "development_only": self.development_only,
            "claim_manifest": [dict(item) for item in self.claim_manifest],
        }


REQUIRED_DIMENSIONS = [
    "identity",
    "startup_status",
    "target_identity",
    "target_process",
    "input_stream",
    "startup_capability",
    "transformation",
    "output_application",
    "relational_chain",
]


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "|".join(str(part or "").strip().casefold() for part in parts)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _source_id(source) -> str:
    explicit = (getattr(source, "document_id", "") or
                getattr(source, "source_id", ""))
    if explicit:
        return str(explicit)
    return _stable_id("src", getattr(source, "url", ""))


CLAIM_STANCES = {"support", "contradict", "unknown"}
CLAIM_FIELDS = {
    "identity", "startup_status", "target_identity", "target_process", "input_stream",
    "startup_capability", "transformation", "output_application",
    "public_search_field",
    "relational_chain",
    # Fachbeleg fuer einen abgeleiteten Inputstrom: Eine allgemeine oeffentliche
    # Quelle belegt, dass der belegte Prozessschritt diesen Reststrom erzeugt.
    "input_stream_mechanism",
}
SUPPORT_TO_FIELD = {
    "identity": "identity",
    "founded": "startup_status",
    "product": "startup_capability",
    "target_identity": "target_identity",
    "target_process": "target_process",
    "process": "target_process",
    "input_stream": "input_stream",
    "transformation": "transformation",
    "output_application": "output_application",
    "public_search_field": "public_search_field",
}


def stable_candidate_id(candidate) -> str:
    """Ein Handoff-Schluessel ohne Lauf- oder Architekturinformation."""
    existing = str(getattr(candidate, "candidate_id", "") or "").strip()
    if existing:
        return existing
    value = (getattr(candidate, "official_url", "")
             or getattr(candidate, "website", "")
             or getattr(candidate, "name", ""))
    result = _stable_id("cand", value)
    try:
        candidate.candidate_id = result
    except Exception:
        pass
    return result


def _claim_text(candidate, field_name: str) -> str:
    values = {
        "identity": f"{getattr(candidate, 'name', '')} ist eine reale Entitaet",
        "startup_status": (
            f"Unternehmenstyp {getattr(candidate, 'company_type', 'unknown')}; "
            f"Gruendung {getattr(candidate, 'founded', None)}"),
        "target_identity": "Die Zielorganisation ist eindeutig identifiziert",
        "target_process": str(getattr(candidate, "process_stage", "") or ""),
        "input_stream": str(getattr(candidate, "input_stream", "") or ""),
        "startup_capability": str(getattr(candidate, "description", "") or ""),
        "transformation": str(getattr(candidate, "transformation", "") or ""),
        "output_application": str(getattr(candidate, "output_application", "") or ""),
    }
    return values.get(field_name, "") or field_name


def build_claim_manifest(candidate, target_sources: list[dict] | None = None) -> list[dict]:
    """Normalisiert Ziel- und Startup-Evidenz in denselben atomaren Vertrag.

    `supports` bleibt als Altformat lesbar, wird aber sofort in konkrete Claims
    ueberfuehrt. Widersprueche sind erstklassige Datensaetze und werden niemals
    durch einen positiven Claim ueberschrieben.
    """
    mode = str(getattr(candidate, "discovery_mode", "") or "manual")
    live = mode == "live"
    candidate_id = stable_candidate_id(candidate)
    candidate_name = str(getattr(candidate, "name", "") or "").strip()
    target_id = str(getattr(candidate, "target_actor_id", "") or "").strip()
    target_name = str(getattr(candidate, "target_actor_name", "") or "").strip()
    opportunity_id = str(getattr(candidate, "opportunity_id", "") or "").strip()
    relation_id = _stable_id("rel", candidate_id, target_id, opportunity_id)
    relation_name = " :: ".join(value for value in (target_name, candidate_name) if value)

    sources = list(getattr(candidate, "sources", None) or [])
    source_map = {_source_id(source): source for source in sources}
    for source in sources:
        source_map.setdefault(str(getattr(source, "url", "") or ""), source)
        if getattr(source, "source_id", ""):
            source_map.setdefault(str(source.source_id), source)
    records: list[dict] = []

    def canonical_subject(field_name: str) -> tuple[str, str, str]:
        required = expected_subject(field_name)
        if required == "candidate_startup":
            return required, candidate_id, candidate_name
        if required == "target_organization":
            return required, target_id, target_name
        if required == "relation":
            return required, relation_id, relation_name
        return "", "", ""

    def add(*, claim_id: str = "", claim_text: str, field_name: str,
            source_id: str, excerpt: str, stance: str,
            subject_type: str = "", subject_id: str = "",
            subject_name: str = "", source=None, basis: str = "direct",
            source_valid: bool = True) -> None:
        field_name = str(field_name or "").strip().lower()
        stance = str(stance or "unknown").strip().lower()
        if stance not in CLAIM_STANCES:
            stance = "unknown"
        if field_name not in CLAIM_FIELDS:
            return
        claim_text = " ".join(str(claim_text or "").split())
        excerpt = " ".join(str(excerpt or "").split())
        source_id = str(source_id or "").strip()
        if not claim_text:
            return
        if live and source is not None and not isinstance(source, dict):
            normalised = _normalise_claim(excerpt)
            digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()
            verified = set(getattr(source, "verified_excerpt_hashes", []) or [])
            # Rueckwaertskompatibel fuer denselben technisch geprueften Auszug;
            # ein anderer Claimtext erbt dessen Verifikation ausdruecklich nicht.
            same_excerpt = (getattr(source, "excerpt_verified", False)
                            and normalised == _normalise_claim(source.excerpt))
            source_valid = bool(source_valid and len(normalised) >= 20
                                and (digest in verified or same_excerpt))

        required_type, required_id, required_name = canonical_subject(field_name)
        subject_type = normalise_subject_type(subject_type)
        subject_id = str(subject_id or "").strip()
        subject_name = str(subject_name or "").strip()
        # Nur Korpus-/Legacyobjekte duerfen aus dem Feldvertrag migriert werden.
        # Im Live-Pfad waere dieselbe Ergaenzung eine unbelegte Inferenz.
        if not live and required_type and not subject_type:
            subject_type, subject_id, subject_name = (
                required_type, required_id, required_name)

        claim_record = {
            "subject_type": subject_type,
            "subject_id": subject_id,
            "subject_name": subject_name,
        }
        binding_valid = True
        if required_type:
            binding_valid = subject_matches(
                claim_record, subject_type=required_type,
                subject_id=required_id, subject_name=required_name,
                strict=live)
            if source is not None:
                binding_valid = binding_valid and subject_matches(
                    source, subject_type=required_type,
                    subject_id=required_id, subject_name=required_name,
                    strict=live)

        # Ein technisch ungepruefter oder semantisch falsch gebundener
        # Live-Beleg bleibt auditierbar, kann aber weder bestaetigen noch
        # widerlegen. Das erzwingt unknown/partial statt Cross-Subject-Spoofing.
        if (live and not source_valid) or not binding_valid:
            stance = "unknown"
        final_id = str(claim_id or "").strip() or _stable_id(
            "claim", field_name, claim_text, source_id, excerpt,
            subject_type, subject_id, subject_name)
        records.append({
            "claim_id": final_id,
            "claim_text": claim_text,
            "field": field_name,
            "source_id": source_id,
            "excerpt": excerpt,
            "stance": stance,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "subject_name": subject_name,
            "binding_status": "valid" if binding_valid else "invalid_or_missing",
            "basis": "derived" if str(basis or "") == "derived" else "direct",
        })

    # Bevorzugtes explizites Format aus Scout bzw. Verifier.
    for item in list(getattr(candidate, "evidence_claims", None) or []):
        if not isinstance(item, dict):
            continue
        sid = str(item.get("source_id") or item.get("source_url") or "").strip()
        source = source_map.get(sid)
        add(
            claim_id=item.get("claim_id", ""),
            claim_text=item.get("claim_text", ""),
            field_name=item.get("field", ""),
            source_id=_source_id(source) if source else sid,
            excerpt=item.get("excerpt") or (getattr(source, "excerpt", "") if source else ""),
            stance=item.get("stance", "unknown"),
            subject_type=item.get("subject_type", ""),
            subject_id=item.get("subject_id", ""),
            subject_name=item.get("subject_name", ""),
            source=source,
            source_valid=bool(source and _valid_source(source, live)),
            basis=item.get("basis", "direct"),
        )

    # Altformat wird einmalig atomisiert; identische Claims werden spaeter
    # dedupliziert. `contradict:<field>` ist als Migrationsformat erlaubt.
    for source in sources:
        valid = _valid_source(source, live)
        for raw in _claims(source):
            stance = "contradict" if raw.startswith("contradict:") else "support"
            tag = raw.split(":", 1)[1] if ":" in raw else raw
            field_name = SUPPORT_TO_FIELD.get(tag)
            if not field_name:
                continue
            if live and field_name in {
                    "target_process", "input_stream", "transformation",
                    "output_application"}:
                # Live-Relationsaussagen brauchen den atomaren Claimvertrag;
                # ein pauschales supports-Tag ist semantisch nicht eindeutig.
                continue
            add(
                claim_text=_claim_text(candidate, field_name),
                field_name=field_name,
                source_id=_source_id(source),
                excerpt=str(getattr(source, "excerpt", "") or ""),
                stance=stance,
                subject_type=getattr(source, "subject_type", ""),
                subject_id=getattr(source, "subject_id", ""),
                subject_name=getattr(source, "subject_name", ""),
                source=source,
                source_valid=valid,
            )

    # Oeffentliche Organisationsquellen werden nie aus einer anderen Organisation
    # uebernommen. Der Taskvertrag prueft die Zugehoerigkeit bereits vorher.
    for document in target_sources or []:
        document_id = str(document.get("document_id") or document.get("source_id")
                          or _stable_id("src", document.get("url", "")))
        document_url = str(document.get("url") or "").strip()
        public_document = bool(document_url and len(document_url) > 8)
        for evidence in document.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            excerpt = " ".join(str(evidence.get("excerpt") or "").split())
            placeholder = excerpt.casefold().startswith("vor abgabe")
            raw_field = str(evidence.get("field") or evidence.get("profile_field")
                            or "").strip().casefold()
            field_name = SUPPORT_TO_FIELD.get(raw_field)
            if not field_name and any(token in raw_field for token in (
                    "prozess", "bearbeitung", "fertigung", "material", "wasser")):
                field_name = "target_process"
            if not field_name or placeholder or len(excerpt) < 20:
                continue
            add(
                claim_id=evidence.get("claim_id", ""),
                claim_text=evidence.get("claim_text") or excerpt,
                field_name=field_name,
                source_id=document_id,
                excerpt=excerpt,
                stance=evidence.get("stance", "support"),
                subject_type=evidence.get("subject_type", ""),
                subject_id=evidence.get("subject_id", ""),
                subject_name=evidence.get("subject_name", ""),
                source=document,
                source_valid=public_document,
            )

    dedup = {}
    for item in records:
        key = (item["claim_id"], item["source_id"], item["stance"],
               item["subject_type"], item["subject_id"], item["subject_name"])
        dedup[key] = item
    return sorted(dedup.values(), key=lambda item: (
        item["field"], item["claim_id"], item["source_id"], item["stance"]))


def _valid_source(source, live: bool) -> bool:
    url = str(getattr(source, "url", "") or "").strip()
    excerpt = str(getattr(source, "excerpt", "") or "").strip()
    try:
        parsed = urlsplit(url)
        valid_url = parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    except Exception:
        valid_url = False
    if not valid_url or len(excerpt) < 20:
        return False
    # Im Live-Pfad zaehlt nur eine URL, die die API als tatsaechlich verwendete
    # Webquelle ausweist. Ein vom Modell lediglich erzeugter URL-String reicht
    # nicht. Kuratierte und synthetische Faelle werden getrennt gekennzeichnet.
    return (not live) or bool(
        getattr(source, "citation_verified", False)
        and getattr(source, "resolved_status", "") == "resolved"
        and getattr(source, "excerpt_verified", False))


def _claims(source) -> set[str]:
    return {str(item).strip().lower() for item in
            (getattr(source, "supports", None) or []) if str(item).strip()}


def _matching_sources(sources: list, required: set[str], live: bool,
                      require_all: bool = False) -> list:
    result = []
    for source in sources:
        if not _valid_source(source, live):
            continue
        claims = _claims(source)
        hit = required <= claims if require_all else bool(required & claims)
        if hit:
            result.append(source)
    return result


def _impressum_supports_identity(candidate, impressum: dict) -> bool:
    from entity_verifier import _same_site, _valid_http_url
    url = str(impressum.get("url") or "")
    website = str(getattr(candidate, "official_url", "") or getattr(candidate, "website", "") or "")
    return bool(impressum.get("company_name_found") and impressum.get("register")
                and _valid_http_url(url) and website and _same_site(website, url))


# v17 (12.11.2026, David "Ja, ueberall gleich"): Fuer Faehigkeit (6), Wirkung (7)
# und Ergebnis (8) genuegt wie bei Zielprozess und Input eine gestuetzte,
# wortgleich bestaetigte Aussage; das Freitextfeld (description, transformation,
# output_application) ist nur eine Modellzusammenfassung und wird nicht mehr
# zusaetzlich verlangt. R4 und alle Tore bleiben unveraendert.
FIELD_OPTIONAL_DIMENSIONS = {"startup_capability", "transformation", "output_application"}


def _cell_from_manifest(dimension: str, claim: str, value_present: bool,
                        manifest: list[dict], open_question: str) -> EvidenceCell:
    records = [item for item in manifest if item.get("field") == dimension]
    supports = [item for item in records if item.get("stance") == "support"]
    if dimension in FIELD_OPTIONAL_DIMENSIONS and supports:
        value_present = True
    contradictions = [item for item in records
                      if item.get("stance") == "contradict"]
    if contradictions:
        status = EvidenceStatus.CONTRADICTED
    elif value_present and supports:
        status = EvidenceStatus.SUPPORTED
    elif value_present or supports:
        status = EvidenceStatus.PARTIAL
    else:
        status = EvidenceStatus.MISSING
    return EvidenceCell(
        dimension=dimension,
        claim=claim,
        status=status,
        source_ids=sorted({str(item.get("source_id") or "")
                           for item in supports + contradictions
                           if item.get("source_id")}),
        excerpts=[str(item.get("excerpt") or "")
                  for item in supports + contradictions if item.get("excerpt")],
        open_questions=[] if status == EvidenceStatus.SUPPORTED else [open_question],
        claim_ids=sorted({str(item.get("claim_id") or "")
                          for item in records if item.get("claim_id")}),
    )


def _input_stream_cell(candidate, manifest: list[dict],
                       process_supported: bool = False) -> EvidenceCell:
    """Inputstrom direkt belegt oder nachvollziehbar abgeleitet.

    Direkt: Eine Quelle der Zielorganisation nennt den Strom selbst.
    Abgeleitet (basis=derived): Eine Quelle der Zielorganisation belegt den
    Prozessschritt (Praemisse), UND eine weitere oeffentliche Fachquelle belegt,
    dass dieser Prozessschritt den Reststrom erzeugt (input_stream_mechanism).
    Beide Auszuege muessen technisch wiedergefunden werden. Die Ableitung
    bleibt im Bericht als solche sichtbar; Menge und Beschaffenheit sind
    offene Fragen. Ein Gegenbeleg hat immer Vorrang.
    """
    value = str(getattr(candidate, "input_stream", "") or "").strip()
    records = [item for item in manifest if item.get("field") == "input_stream"]
    direct = [item for item in records if item.get("stance") == "support"
              and item.get("basis") != "derived"]
    premises = [item for item in records if item.get("stance") == "support"
                and item.get("basis") == "derived"]
    mechanisms = [item for item in manifest
                  if item.get("field") == "input_stream_mechanism"
                  and item.get("stance") == "support"]
    contradictions = [item for item in records if item.get("stance") == "contradict"]
    question = "Input, Material-, Daten- oder Ressourcenstrom konkret belegen."
    basis = "direct"
    if contradictions:
        status = EvidenceStatus.CONTRADICTED
    # 12.11.2026: Ein bestaetigter Auszug genuegt; das Freitextfeld input_stream
    # wird nicht mehr zusaetzlich verlangt.
    elif direct:
        status = EvidenceStatus.SUPPORTED
    # R4 (11.11.2026): Die Praemisse kann auch der belegte Zielprozess (Glied 4)
    # sein; der Mechanismusbeleg darf aus einer Fach- oder Startup-Quelle stammen,
    # die belegt, dass das Produkt genau diese Art Input verarbeitet.
    elif (premises or process_supported) and mechanisms:
        status = EvidenceStatus.SUPPORTED
        basis = "derived"
        question = ("Abgeleiteter Reststrom: Menge, Zusammensetzung und "
                    "Verfuegbarkeit im Erstgespraech bestaetigen.")
    elif value or direct or premises:
        status = EvidenceStatus.PARTIAL
    else:
        status = EvidenceStatus.MISSING
    used = direct + premises + mechanisms + contradictions
    return EvidenceCell(
        dimension="input_stream",
        claim=value or "Input- oder Ressourcenstrom",
        status=status,
        source_ids=sorted({str(item.get("source_id") or "") for item in used
                           if item.get("source_id")}),
        excerpts=[str(item.get("excerpt") or "") for item in used if item.get("excerpt")],
        open_questions=([] if status == EvidenceStatus.SUPPORTED and basis == "direct"
                        else [question]),
        claim_ids=sorted({str(item.get("claim_id") or "") for item in records + mechanisms
                          if item.get("claim_id")}),
        basis=basis,
    )


def _target_process_cell(candidate, manifest: list[dict]) -> EvidenceCell:
    # v16 (12.11.2026, von David freigegeben): Wie beim Input genuegt ein
    # wortgleich bestaetigter Prozessauszug; das Freitextfeld process_stage
    # wird nicht mehr zusaetzlich verlangt.
    value = str(getattr(candidate, "process_stage", "") or "").strip()
    confirmed = any(item.get("field") == "target_process" and item.get("stance") == "support"
                    for item in manifest)
    return _cell_from_manifest(
        "target_process",
        value or "Betroffener Prozessschritt der Zielorganisation",
        bool(value) or confirmed, manifest,
        "Welcher oeffentlich belegte Prozessschritt ist konkret betroffen?",
    )


class EvidenceMatrixBuilder:
    """Erzeugt eine normalisierte Matrix und eine fail-closed Entscheidung."""

    def build(self, candidate, target_sources: list[dict] | None = None
              ) -> RelationalEvidenceMatrix:
        mode = str(getattr(candidate, "discovery_mode", "") or "manual")
        live = mode == "live"
        synthetic = mode == "synthetic"
        sources = list(getattr(candidate, "sources", None) or [])
        manifest = build_claim_manifest(candidate, target_sources or [])
        candidate.evidence_claims = [dict(item) for item in manifest]
        candidate.candidate_id = stable_candidate_id(candidate)

        identity = _cell_from_manifest(
            "identity", f"{candidate.name} ist eine reale, eindeutig identifizierte Entitaet",
            bool(getattr(candidate, "official_url", "") or getattr(candidate, "website", "")),
            manifest,
            "Offizielle Identitaetsquelle und unabhaengigen Existenzbeleg ergaenzen.")
        # R2 (11.11.2026): Ein deterministisch abgerufenes Impressum der eigenen
        # Website mit Firmenname und Registermerkmal belegt die Identitaet.
        impressum = dict(getattr(candidate, "impressum", None) or {})
        if (identity.status in {EvidenceStatus.MISSING, EvidenceStatus.PARTIAL}
                and _impressum_supports_identity(candidate, impressum)):
            identity.status = EvidenceStatus.SUPPORTED
            identity.source_ids = sorted(set(identity.source_ids) | {"impressum"})
            identity.excerpts = list(identity.excerpts) + [
                str(impressum.get("excerpt") or impressum.get("register") or "")]
            identity.open_questions = []
        status_value_present = (
            getattr(candidate, "company_type", "") in {"startup", "scaleup", "spin_off"}
            and getattr(candidate, "founded", None) is not None
            # Fortbestand: Live-Kandidaten brauchen das Urteil "active" der
            # Pruefstufe (eigenstaendig, nicht uebernommen, nicht eingestellt).
            and (getattr(candidate, "discovery_mode", "") != "live"
                 or getattr(candidate, "operating_status", "") == "active"))
        startup_status = _cell_from_manifest(
            "startup_status",
            f"Unternehmenstyp {getattr(candidate, 'company_type', 'unknown')}; "
            f"Gruendung {getattr(candidate, 'founded', None)}",
            status_value_present,
            manifest,
            "Gruendungsjahr und Unternehmenstyp unabhaengig belegen.")
        # R3 (11.11.2026): Gruendungsjahr aus jeder geprueften Quelle ueber das
        # Startup, auch aus einem bestaetigten Register- oder Firmenbucheintrag.
        if (startup_status.status in {EvidenceStatus.MISSING, EvidenceStatus.PARTIAL}
                and status_value_present):
            from entity_verifier import founding_source
            source = founding_source(candidate)
            if source is not None:
                startup_status.status = EvidenceStatus.SUPPORTED
                sid = str(getattr(source, "source_id", "") or getattr(source, "url", ""))
                startup_status.source_ids = sorted(set(startup_status.source_ids) | {sid})
                startup_status.excerpts = list(startup_status.excerpts) + [
                    str(getattr(source, "excerpt", "") or "")]
                startup_status.open_questions = []
        target_identity = _cell_from_manifest(
            "target_identity",
            "Die Zielorganisation ist eindeutig durch eine oeffentliche Quelle identifiziert",
            any(item.get("field") == "target_identity" and
                item.get("stance") == "support" for item in manifest),
            manifest,
            "Zielorganisation eindeutig aufloesen und mit Rechercheoutput belegen.")
        unresolved = " ".join(str(item or "") for item in
                              (getattr(candidate, "unresolved_requirements", None)
                               or [])).casefold()
        ambiguous = any(marker in unresolved for marker in (
            "ambig", "mehrdeutig", "nicht eindeutig", "identity unresolved"))
        given_name = str(getattr(candidate, "target_actor_name", "") or "").strip()
        if live and given_name:
            # Seit 20.10.2026: Die Zielorganisation gibt die ausfuehrende Person
            # vor (Name, optional Website). Ihre Identitaet ist Auftragsbestand-
            # teil und wird nicht erneut belegt. Prozess- und Inputbelege muessen
            # weiterhin aus Quellen dieser Organisation stammen.
            target_identity.status = EvidenceStatus.SUPPORTED
            target_identity.basis = "given"
            target_identity.claim = f"Vom Nutzer vorgegeben: {given_name}"
            target_identity.open_questions = ([
                "Namensgleiche Organisationen moeglich; Website des Unternehmens "
                "im Auftrag angeben."] if ambiguous else [])
        elif ambiguous:
            target_identity.status = EvidenceStatus.CONTRADICTED
            target_identity.open_questions = [
                "Die Zielorganisation blieb in der Recherche mehrdeutig."]
        target_process = _target_process_cell(candidate, manifest)
        process_supported = target_process.status == EvidenceStatus.SUPPORTED
        input_stream = _input_stream_cell(candidate, manifest, process_supported)
        capability = _cell_from_manifest(
            "startup_capability", str(getattr(candidate, "description", "") or
                                      "Produktfaehigkeit des Startups"),
            bool(str(getattr(candidate, "description", "") or "").strip()),
            manifest,
            "Produktfaehigkeit durch eine offizielle Startup-Quelle belegen.")
        transformation = _cell_from_manifest(
            "transformation", str(getattr(candidate, "transformation", "") or
                                  "Technischer Transformationsmechanismus"),
            bool(str(getattr(candidate, "transformation", "") or "").strip()),
            manifest,
            "Technischen Mechanismus auf Aussageebene belegen.")
        output = _cell_from_manifest(
            "output_application", str(getattr(candidate, "output_application", "") or
                                      "Nutzbarer Output und Anwendung"),
            bool(str(getattr(candidate, "output_application", "") or "").strip()),
            manifest,
            "Nutzbaren Output und konkrete Anschlussanwendung belegen.")

        # R4 (11.11.2026): Wirkung (7) und Ergebnis (8) belegt das Startup fuer sein
        # Produkt; sie tragen die Kette nur, wenn der Zielprozess (4) belegt ist.
        # Die Uebertragung auf die Zielorganisation ist abgeleitet und eine
        # offene Frage fuer das Erstgespraech.
        for cell in (transformation, output):
            if cell.status == EvidenceStatus.SUPPORTED:
                if process_supported:
                    cell.basis = "derived"
                    cell.open_questions = [
                        "Abgeleitet: Uebertragung auf die Zielorganisation im "
                        "Erstgespraech pruefen."]
                else:
                    cell.status = EvidenceStatus.PARTIAL
                    cell.open_questions = [
                        "Zielprozess belegen, damit Wirkung und Ergebnis die Kette tragen."]
        relation_components = [target_process, input_stream, capability,
                               transformation, output]
        relation_supported = all(
            item.status == EvidenceStatus.SUPPORTED for item in relation_components)
        relation_fields = {item.dimension for item in relation_components}
        supported_subject_types = {
            item.get("subject_type") for item in manifest
            if item.get("field") in relation_fields
            and item.get("stance") == "support"
            and item.get("binding_status") == "valid"
        }
        both_subject_sides = {
            "target_organization", "candidate_startup"
        } <= supported_subject_types
        relation_ids = sorted({sid for item in relation_components
                               for sid in item.source_ids})
        relation = EvidenceCell(
            dimension="relational_chain",
            claim=(f"{target_process.claim} -> {input_stream.claim} -> "
                   f"{transformation.claim} -> {output.claim}"),
            status=(EvidenceStatus.CONTRADICTED if any(
                        item.status == EvidenceStatus.CONTRADICTED
                        for item in relation_components)
                    else EvidenceStatus.SUPPORTED if relation_supported and both_subject_sides
                    else EvidenceStatus.PARTIAL if any(
                        item.status != EvidenceStatus.MISSING for item in relation_components)
                    else EvidenceStatus.MISSING),
            source_ids=relation_ids,
            excerpts=[],
            open_questions=[] if relation_supported and both_subject_sides else [
                "Die vollständige Beziehung muss durch Ziel- und Startup-Evidenz getragen sein."
            ],
            claim_ids=sorted({claim_id for item in relation_components
                              for claim_id in item.claim_ids}),
        )

        cells = [identity, startup_status, target_identity, target_process, input_stream,
                 capability, transformation, output, relation]
        contradictions = [item.dimension for item in cells
                          if item.status == EvidenceStatus.CONTRADICTED]
        blocking = [item.dimension for item in cells
                    if item.dimension in REQUIRED_DIMENSIONS and
                    item.status != EvidenceStatus.SUPPORTED]
        supported = sum(item.status == EvidenceStatus.SUPPORTED for item in cells
                        if item.dimension in REQUIRED_DIMENSIONS)
        coverage = round(supported / len(REQUIRED_DIMENSIONS), 3)

        # Synthetische Entwicklungsfaelle pruefen nur den deterministischen
        # Kontrollfluss. Sie werden nie als reale Evidenz ausgegeben und duerfen
        # bestehende Regressionstests nicht in Live-Wirksamkeitsnachweise
        # umdeuten.
        if synthetic:
            decision_state = "development_only"
            blocking = []
        elif contradictions:
            decision_state = "contradictory"
        elif blocking:
            decision_state = "incomplete"
        else:
            decision_state = "fully_supported"

        candidate_id = stable_candidate_id(candidate)
        relation_id = _stable_id(
            "rel", candidate_id, getattr(candidate, "target_actor_id", ""),
            getattr(candidate, "opportunity_id", ""))
        return RelationalEvidenceMatrix(
            relation_id=relation_id,
            candidate_id=candidate_id,
            target_actor_id=str(getattr(candidate, "target_actor_id", "") or ""),
            opportunity_id=str(getattr(candidate, "opportunity_id", "") or ""),
            cells=cells,
            required_dimensions=list(REQUIRED_DIMENSIONS),
            blocking_dimensions=blocking,
            contradictions=contradictions,
            evidence_coverage=coverage,
            decision_state=decision_state,
            development_only=synthetic,
            claim_manifest=manifest,
        )
