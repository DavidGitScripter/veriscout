"""Kanonischer public-only Aufgabenvertrag fuer Architekturvergleiche.

Der Eingabevertrag enthaelt bewusst noch keine Organisations- oder Prozessbelege:
SAS und MAS erhalten denselben Organisationsnamen und denselben freien
Suchauftrag. Oeffentliche Quellen, Belegauszuege und relationale Claims sind
Ergebnisse der jeweiligen Recherche und werden erst danach technisch aufgeloest
und fail-closed bewertet. Ein optionaler Domainhinweis dient ausschliesslich der
Identitaetsaufloesung und gilt niemals als Evidenz.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import datetime
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit


def _normalise_text(value) -> str:
    return " ".join(str(value or "").split())


def _public_url(value: str) -> bool:
    try:
        parsed = urlsplit(str(value or "").strip())
        host = str(parsed.hostname or "").strip().lower().rstrip(".")
        if (parsed.scheme not in {"http", "https"} or not host
                or parsed.username or parsed.password):
            return False
        if host in {"localhost", "localhost.localdomain"} or host.endswith(
                (".local", ".internal", ".localhost", ".example",
                 ".invalid", ".test")):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return bool("." in host and re.fullmatch(
                r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", host))
    except Exception:
        return False


def normalise_domain_hint(value: str) -> str:
    """Normalisiert einen optionalen oeffentlichen Domainhinweis.

    Der Rueckgabewert ist nur ein Identifikationshinweis. Er wird nicht als
    Quelle, Abrufnachweis oder Beleg in die Evidenzmatrix uebernommen.
    """
    raw = _normalise_text(value).casefold().rstrip("/")
    if not raw:
        return ""
    candidate = raw if "://" in raw else "https://" + raw
    parsed = urlsplit(candidate)
    host = str(parsed.hostname or "").strip().lower().rstrip(".")
    if not host or parsed.username or parsed.password:
        raise ValueError("organization_domain_hint ist keine gueltige Domain.")
    if not _public_url("https://" + host):
        raise ValueError(
            "organization_domain_hint muss eine oeffentlich erreichbare Domain sein.")
    return host


def stable_organization_id(name: str, domain_hint: str = "") -> str:
    """Erzeugt eine stabile, nicht vom Nutzer zu pflegende Organisations-ID."""
    clean_name = _normalise_text(name)
    if not clean_name:
        raise ValueError("organization_name fehlt.")
    domain = normalise_domain_hint(domain_hint)
    slug = re.sub(r"[^a-z0-9]+", "-", clean_name.casefold()).strip("-")
    slug = slug[:36] or "organization"
    digest = hashlib.sha256(
        f"{clean_name.casefold()}|{domain}".encode("utf-8")
    ).hexdigest()[:12]
    return f"org-{slug}-{digest}"


def _iso_date(value: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(_normalise_text(value))
    except ValueError:
        return None


def _iso_time(value: str) -> datetime.datetime | None:
    try:
        parsed = datetime.datetime.fromisoformat(
            _normalise_text(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(datetime.timezone.utc)


@dataclass(frozen=True)
class PublicSearchField:
    """Interne Darstellung genau eines freien, vorab fixierten Suchauftrags.

    ``source`` bleibt nur fuer alte Offline-Fixtures lesbar. Im regulaeren
    Pilot-/Live-Vertrag ist es leer, weil der Nutzer keine Belege vorgeben muss.
    """

    theme_id: str
    title: str
    description: str
    source: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict | None) -> "PublicSearchField":
        value = dict(value or {})
        source = value.get("source")
        if isinstance(source, str):
            source = {"label": source}
        return cls(
            theme_id=_normalise_text(
                value.get("field_id") or value.get("theme_id") or value.get("id")),
            title=_normalise_text(value.get("title") or value.get("themengebiet")),
            description=_normalise_text(
                value.get("description") or value.get("beschreibung")),
            source=deepcopy(source or {}),
        )

    @classmethod
    def from_prompt(cls, prompt: str) -> "PublicSearchField":
        value = _normalise_text(prompt)
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
        return cls(
            theme_id=f"prompt-{digest}",
            title="Freier Startup-Suchauftrag",
            description=value,
            source={},
        )

    def readiness_issues(self) -> list[str]:
        issues = []
        if not _normalise_text(self.description):
            issues.append("search_prompt_missing")
        return issues

    def validate(self, strict: bool = True) -> None:
        missing = [name for name, value in (
            ("theme_id", self.theme_id), ("title", self.title),
            ("description", self.description),
        ) if not value]
        if missing:
            raise ValueError(
                "Public-only Suchfeld unvollstaendig: " + ", ".join(missing))
        if strict and self.readiness_issues():
            raise ValueError(
                "Der konfirmatorische Suchauftrag ist unvollstaendig: "
                + ", ".join(self.readiness_issues()))


SEARCH_MODES = {"push", "pull"}


@dataclass(frozen=True)
class PublicSearchTaskInput:
    """Unveraenderlicher Input, der beiden Versuchsarmen bytegleich vorliegt."""

    task_id: str
    organization_id: str
    organization_name: str
    search_field: PublicSearchField
    organization_domain_hint: str = ""
    public_source_package: tuple[dict, ...] = ()
    task_group_id: str = ""
    dataset_split: str = "test"
    event_time: str = ""
    strict_public_only: bool = True
    # Auftragsart aus dem Anwendungskontext (Kap. 5.2): PUSH erschliesst eine
    # Kooperationsmoeglichkeit aus oeffentlich erkennbaren Taetigkeiten, ohne
    # dass die Organisation einen Bedarf benannt hat. PULL konkretisiert ein von
    # der Organisation selbst oeffentlich benanntes Suchfeld (search_area).
    search_mode: str = "push"
    search_area: str = ""

    def validate(self) -> None:
        if not _normalise_text(self.task_id):
            raise ValueError("task_id fehlt.")
        if not _normalise_text(self.organization_id):
            raise ValueError("organization_id fehlt.")
        if not _normalise_text(self.organization_name):
            raise ValueError("organization_name fehlt.")
        if self.search_mode not in SEARCH_MODES:
            raise ValueError("search_mode muss push oder pull sein.")
        area = _normalise_text(self.search_area)
        if self.search_mode == "pull" and not 3 <= len(area) <= 160:
            raise ValueError(
                "Ein PULL-Auftrag braucht ein von der Organisation benanntes "
                "Suchfeld (3 bis 160 Zeichen).")
        if self.search_mode == "push" and area:
            raise ValueError("Ein PUSH-Auftrag hat kein vorgegebenes Suchfeld.")
        self.search_field.validate(strict=self.strict_public_only)
        domain_hint = normalise_domain_hint(self.organization_domain_hint)
        if (self.strict_public_only and self.organization_id !=
                stable_organization_id(self.organization_name, domain_hint)):
            raise ValueError(
                "organization_id muss technisch aus Name und Domainhinweis erzeugt werden.")
        if self.dataset_split not in {
                "train", "development", "validation", "test", "holdout", "pilot"}:
            raise ValueError(
                "dataset_split muss development, validation, test, holdout oder pilot sein.")
        event_time = _iso_time(self.event_time)
        if self.event_time and event_time is None:
            raise ValueError("event_time ist kein ISO-8601-Zeitpunkt mit Zeitzone.")
        if (self.strict_public_only and event_time
                and event_time > datetime.datetime.now(datetime.timezone.utc)):
            raise ValueError("event_time darf nicht in der Zukunft liegen.")
        if self.strict_public_only and self.public_source_package:
            raise ValueError(
                "Eingabequellen sind im Pilot-/Live-Vertrag nicht zulaessig; "
                "Quellen und Belegauszuege muessen Rechercheergebnisse sein.")
        for source in self.public_source_package:
            if not isinstance(source, dict):
                raise ValueError("Jede Quelle im public_source_package muss ein Objekt sein.")
            classification = _normalise_text(
                source.get("classification") or source.get("datenklassifikation")
                or "public").casefold()
            if self.strict_public_only and classification not in {
                    "public", "oeffentlich"}:
                raise ValueError("Nichtoeffentliche Quelle im Aufgabenpaket.")
            source_organization = _normalise_text(
                source.get("organization_id") or source.get("actor_id"))
            if source_organization and source_organization != self.organization_id:
                raise ValueError(
                    "Das Quellenpaket darf keine Belege einer anderen Organisation enthalten.")
            url = _normalise_text(source.get("url"))
            if self.strict_public_only and url and not _public_url(url):
                raise ValueError("Quellenpaket enthaelt keine oeffentliche HTTP(S)-URL.")

    def readiness(self) -> dict:
        issues = self.search_field.readiness_issues()
        try:
            self.validate()
        except ValueError as error:
            if str(error) not in issues:
                issues.append(str(error))
        return {
            "status": "ready" if not issues else "draft_not_ready",
            "issues": issues,
            "confirmatory": not issues,
        }

    def source_snapshot(self) -> list[dict]:
        """Legacy-Snapshot optionaler Offline-Eingabequellen.

        Fuer Pilot-/Live-Auftraege ist diese Liste definitionsgemaess leer.
        Ergebnisquellen werden spaeter kandidatenseitig aufgeloest und in der
        Evidenzmatrix protokolliert.
        """
        values = []
        for source in self.public_source_package:
            item = deepcopy(source)
            item.setdefault("organization_id", self.organization_id)
            url = _normalise_text(item.get("url"))
            hostname = urlsplit(url).hostname if _public_url(url) else ""
            item.setdefault("source_family", str(hostname or "").casefold())
            evidence_payload = {
                "url": url,
                "retrieved_at": _normalise_text(item.get("retrieved_at")),
                "evidence": item.get("evidence") or [],
            }
            raw = json.dumps(evidence_payload, ensure_ascii=False,
                             sort_keys=True, separators=(",", ":"))
            item.setdefault(
                "excerpt_snapshot_sha256",
                hashlib.sha256(raw.encode("utf-8")).hexdigest())
            item.setdefault(
                "snapshot_scope",
                "legacy_offline_input")
            values.append(item)
        return sorted(values, key=lambda item: (
            _normalise_text(item.get("document_id") or item.get("source_id")),
            _normalise_text(item.get("url")),
        ))

    def prompt(self) -> str:
        """Identischer fachlicher User-Prompt fuer SAS und MAS.

        Rollenprompts duerfen die jeweilige Architektur implementieren. Der
        Suchauftrag selbst bleibt jedoch identisch und wird gehasht.
        """
        self.validate()
        domain_line = (
            "Optionaler Domainhinweis zur Identitaetsaufloesung: "
            f"{normalise_domain_hint(self.organization_domain_hint)} "
            "(nur Hinweis, kein Beleg)\n"
            if self.organization_domain_hint else ""
        )
        if self.search_mode == "pull":
            mode_block = (
                "Auftragsart PULL: Die Zielorganisation hat oeffentlich selbst "
                "ein Suchfeld benannt: \"" + _normalise_text(self.search_area)
                + "\". Belege zuerst mit einer oeffentlichen Quelle der "
                "Zielorganisation, dass sie dieses Suchfeld selbst benennt. "
                "Suche danach nur Startups fuer dieses Suchfeld. Ist das Suchfeld "
                "oeffentlich nicht belegbar, nenne das unter "
                "unresolved_requirements.\n\n")
        else:
            mode_block = (
                "Auftragsart PUSH: Die Zielorganisation hat keinen Bedarf "
                "benannt. Erschliesse moegliche Anknuepfungspunkte aus ihren "
                "oeffentlich erkennbaren Taetigkeiten.\n\n")
        return (
            f"PUBLIC-ONLY {self.search_mode.upper()}-SUCHAUFTRAG\n"
            f"Auftrags-ID: {self.task_id}\n"
            f"Zielorganisation: {self.organization_name} ({self.organization_id})\n"
            + domain_line
            + "Freier, vorab fixierter Startup-Suchauftrag:\n"
            + self.search_field.description + "\n\n"
            + mode_block +
            "Arbeite ausschliesslich mit oeffentlich zugaenglichen Informationen. "
            "Die Zielorganisation ist vorgegeben und muss nicht erneut belegt "
            "werden. Gibt es gleichnamige Organisationen, nutze den Domainhinweis "
            "oder die Organisation, die zum Suchauftrag passt, und nenne die "
            "Unsicherheit unter unresolved_requirements. "
            "Scanne die Zielorganisation danach selbst aus "
            "oeffentlichen Primaerquellen. Die dabei gefundenen Quellen und kurzen "
            "Belegauszuege sind Ergebnis der Recherche, nicht Nutzereingabe. "
            "Rekonstruiere nur solche Prozesse, Inputs und Outputs als Fakten, die "
            "durch konkrete, spaeter technisch aufloesbare Ergebnisbelege gestuetzt werden. "
            "Alles andere bleibt unknown oder eine ausdruecklich bezeichnete "
            "Hypothese und darf keine positive Empfehlung tragen. Suche danach "
            "Startups, deren oeffentlich belegte Faehigkeit an einen ebenfalls "
            "oeffentlich belegten Teil dieses Suchauftrags anknuepft und die Organisation "
            "nachhaltiger und/oder effizienter machen kann. Eine erwartete "
            "Profitabilitaetswirkung ist nur als zu pruefende Wirkungshypothese "
            "zulaessig. Erfinde keine Prozesse, Unternehmen, Quellen oder "
            "Wirkungswerte. Branchennaehe allein ist kein qualifizierter Treffer."
        )

    def canonical_dict(self) -> dict:
        self.validate()
        return {
            "task_id": self.task_id,
            "organization_id": self.organization_id,
            "organization_name": self.organization_name,
            "organization_domain_hint": normalise_domain_hint(
                self.organization_domain_hint),
            "search_prompt": self.search_field.description,
            "search_field": asdict(self.search_field),
            "public_source_package": self.source_snapshot(),
            "task_group_id": self.task_group_id or self.task_id,
            "dataset_split": self.dataset_split,
            "event_time": self.event_time,
            "strict_public_only": self.strict_public_only,
            "search_mode": self.search_mode,
            "search_area": _normalise_text(self.search_area),
            "shared_prompt": self.prompt(),
        }

    def prompt_hash(self) -> str:
        return "prompt-" + hashlib.sha256(
            self.prompt().encode("utf-8")).hexdigest()[:20]

    def input_hash(self) -> str:
        raw = json.dumps(self.canonical_dict(), ensure_ascii=False,
                         sort_keys=True, separators=(",", ":"))
        return "task-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def legacy_public_task(*, task_id: str, organization_id: str,
                       organization_name: str,
                       query: str = "", task_group_id: str = "") -> PublicSearchTaskInput:
    """Abwaertskompatibler Offline-Vertrag; fuer Live-Studien nicht zulaessig."""
    description = _normalise_text(query) or "Allgemeiner oeffentlicher Entwicklungsscan"
    return PublicSearchTaskInput(
        task_id=task_id,
        organization_id=organization_id,
        organization_name=organization_name or organization_id,
        search_field=PublicSearchField(
            theme_id="legacy-offline",
            title="Nicht praeregistrierter Offline-Kompatibilitaetslauf",
            description=description,
            source={"classification": "public", "label": "legacy-offline"},
        ),
        public_source_package=(),
        task_group_id=task_group_id or task_id,
        strict_public_only=False,
    )
