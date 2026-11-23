"""Lokale VeriScout-API fuer den kontrollierten SAS--MAS-Vergleich.

Die organisationsneutrale Vergleichsoberflaeche ist der Standardpfad. Alte CRM-
und Outreach-Endpunkte bleiben fuer lokale Demonstrationen vorhanden, sind aber
ohne expliziten Legacy-Schalter nicht ueber HTTP erreichbar.
"""
from __future__ import annotations

import os
import re
import json
import asyncio
import uuid
import hashlib
import secrets
import threading
import tempfile
import inspect
import urllib.parse
import platform
import sys
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from core import Candidate, Autonomy, Recommendation, Source, Config
from pipeline import Pipeline
from crm_pipedrive import PipedriveAdapter, PIPELINE_NAME, CRMAuthError
from evaluate import load_corpus, run_eval, run_ablation
from compare_architectures import operator_view
from evaluation_analysis import bayesian_paired_difference, paired_metrics
from case_sheet import case_sheet_hash, normalise_case_sheet
from evidence_resolver import EvidenceResolver
import release
from rating_sheet import (build_rating_key, merge_ratings,
                          render_rating_sheet_html)
from compare_architectures import (ComparisonTask, ExperimentBudget,
                                   PairedArchitectureRunner,
                                   annotation_package, assignment_manifest)
from experiment_protocol import stable_organization_id
from memory import MemoryStore
from study_controls import (HoldoutRegistry, StudyBudgetLedger,
                            build_balanced_plan, save_frozen_plan)
import outlook_mac
import store
import reuse

app = FastAPI(title="VeriScout — Evidence-led startup intelligence")


# ---------------------------------------------------------------------------
# Vollstaendige Fehlerdetails bleiben im Serverprotokoll. An den Browser gehen
# weder Stacktrace noch interne Pfade oder Geheimnisse.
# ---------------------------------------------------------------------------
import traceback as _tb
import logging as _log

_log.basicConfig(level=_log.INFO)


@app.exception_handler(Exception)
async def _fehler_sichtbar(request, exc):
    spur = _tb.format_exc()
    error_id = f"err-{uuid.uuid4().hex[:12]}"
    _log.error("%s bei %s %s\n%s", error_id, request.method,
               request.url.path, spur)
    return JSONResponse(
        {"error": "Interner Fehler. Details stehen nur im Serverprotokoll.",
         "error_id": error_id},
        status_code=500)

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")), name="static")

# Live-CRM nur, wenn ein Token gesetzt UND der Live-Modus ausdruecklich aktiviert ist
# (so schreibt ein blosser Token nicht versehentlich in echtes Pipedrive):
LIVE_CRM = bool(Config.PIPEDRIVE_API_TOKEN) and os.environ.get("PIPEDRIVE_LIVE") == "1"
_adapter = PipedriveAdapter(dry_run=not LIVE_CRM)
PIPE = Pipeline(live=bool(os.environ.get("OPENAI_API_KEY")), adapter=_adapter)
SEED = {c.name: c for c, _ in load_corpus()}


def _startdiagnose():
    """Beim Start sichtbar machen, welche CRM-Instanz mit welchem Token
    angesprochen wird. Ohne das bleibt eine falsche Konfiguration unbemerkt,
    bis der erste Schreibversuch scheitert."""
    tok = Config.PIPEDRIVE_API_TOKEN
    # Niemals auch nur Teilstrings eines Geheimnisses protokollieren.
    maske = "gesetzt" if tok else "fehlt"
    print("-" * 66)
    print(f"  CRM-Ziel     : {Config.PIPEDRIVE_API_BASE}")
    print(f"  Token        : {maske}")
    print(f"  Schreibmodus : {'LIVE' if LIVE_CRM else 'Trockenlauf'}")
    from core import _DOTENV_UEBERSCHRIEBEN
    if _DOTENV_UEBERSCHRIEBEN:
        print(f"  Hinweis      : Shell-Variablen haben .env-Werte uebersteuert: "
              f"{', '.join(_DOTENV_UEBERSCHRIEBEN)}")
    print("  Feldpruefung : python3 pipedrive_selfcheck.py")
    print("-" * 66)


_startdiagnose()
DECISIONS = {}   # name -> Decision (Session-Cache fuer HITL)
BASE = os.path.dirname(os.path.abspath(__file__))
_INSTANCE_SETTING = os.environ.get(
    "SCOUTREF_INSTANCE_PATH", os.path.join("config", "instance.default.json"))
INSTANCE_PATH = (_INSTANCE_SETTING if os.path.isabs(_INSTANCE_SETTING)
                 else os.path.join(BASE, _INSTANCE_SETTING))
_MEMORY_SETTING = os.environ.get(
    "SCOUTREF_MEMORY_SNAPSHOT",
    os.path.join("data", "evaluation", "frozen_memory.json"))
MEMORY_SNAPSHOT_PATH = (_MEMORY_SETTING if os.path.isabs(_MEMORY_SETTING)
                        else os.path.join(BASE, _MEMORY_SETTING))
LEGACY_API_ENABLED = os.environ.get("SCOUTREF_ENABLE_LEGACY_API") == "1"
LIVE_EVAL_ENABLED = os.environ.get("SCOUTREF_EVAL_LIVE_ENABLED") == "1"
LOCAL_REVIEW_MODE = os.environ.get("SCOUTREF_LOCAL_REVIEW_MODE") == "1"
TRANSFER_REVIEW_MODE = os.environ.get("SCOUTREF_TRANSFER_REVIEW_MODE") == "1"
OPERATOR_TOKEN = os.environ.get("SCOUTREF_OPERATOR_TOKEN", "")
RUN_MAX_COST_USD = float(os.environ.get("SCOUTREF_RUN_MAX_COST_USD", "2.50"))
# Das lokale Studienlimit ist absichtlich kleiner als das genannte Guthaben.
# Acht US-Dollar lassen bei 10 EUR auch bei Wechselkurs-, Such- und
# Fehlversuchen eine Sicherheitsreserve. Das Ledger ist eine zusaetzliche
# Sperre und ersetzt nicht das Abrechnungslimit im OpenAI-Konto.
STUDY_BUDGET_USD = float(os.environ.get(
    "SCOUTREF_STUDY_BUDGET_USD", "8.00"))
RUN_LOCK = threading.Lock()
RUN_CACHE: dict[str, dict] = {}
UNBLINDING_RECORDS: dict[str, dict] = {}
MAX_CACHED_RUNS = 50
_UNBLINDING_SETTING = os.environ.get(
    "SCOUTREF_UNBLINDING_STORE",
    os.path.join(Config.RUNTIME_ROOT, "unblinding_records.json"))
UNBLINDING_STORE_PATH = (
    _UNBLINDING_SETTING if os.path.isabs(_UNBLINDING_SETTING)
    else os.path.join(BASE, _UNBLINDING_SETTING))
_STUDY_BUDGET_SETTING = os.environ.get(
    "SCOUTREF_STUDY_BUDGET_LEDGER",
    os.path.join(Config.RUNTIME_ROOT, "study_budget_ledger.json"))
STUDY_BUDGET_LEDGER_PATH = (
    _STUDY_BUDGET_SETTING if os.path.isabs(_STUDY_BUDGET_SETTING)
    else os.path.join(BASE, _STUDY_BUDGET_SETTING))
STUDY_PLAN_ROOT = os.path.join(Config.RUNTIME_ROOT, "study_plans")
HOLDOUT_MANIFEST_PATH = os.environ.get("SCOUTREF_HOLDOUT_MANIFEST", "")
HOLDOUT_EXECUTION_PATH = os.environ.get(
    "SCOUTREF_HOLDOUT_EXECUTIONS",
    os.path.join(Config.RUNTIME_ROOT, "holdout_executions.json"))
STUDY_BUDGET = StudyBudgetLedger(
    STUDY_BUDGET_LEDGER_PATH, STUDY_BUDGET_USD)
HOLDOUT_REGISTRY = HoldoutRegistry(
    HOLDOUT_MANIFEST_PATH, HOLDOUT_EXECUTION_PATH)


def _operator_authorized(request: Request | None) -> bool:
    if not OPERATOR_TOKEN or request is None:
        return False
    # Die alten Header bleiben fuer bestehende lokale Testskripte kompatibel.
    supplied = str(
        request.headers.get("X-VeriScout-Token")
        or request.headers.get("X-VentureScout-Token")
        or request.headers.get("X-VentureFold-Token")
        or request.headers.get("X-ScoutRef-Token")
        or "")
    return bool(supplied) and secrets.compare_digest(supplied, OPERATOR_TOKEN)


@app.middleware("http")
async def _api_boundary(request: Request, call_next):
    path = request.url.path
    safe_paths = {
        "/api/comparison/config", "/api/comparison/preview",
        "/api/comparison/workspace/validate", "/api/comparison/reuse/protocol",
        "/healthz", "/api/comparison/local-operator",
    }
    if path.startswith("/api/"):
        legacy = not path.startswith("/api/comparison/")
        if legacy and path not in safe_paths and not LEGACY_API_ENABLED:
            return JSONResponse(
                {"error": "Legacy-Schnittstelle ist standardmaessig deaktiviert."},
                status_code=404)
        # Gespeicherte Laeufe ansehen und auswerten ist lesend und kostenfrei.
        read_only_runs = (request.method == "GET"
                          and path.startswith("/api/comparison/runs"))
        # Auswertung, Bewertungsbogen und Zusammenfuehrung sind kostenfrei
        # und arbeiten nur mit lokal gespeicherten Laufdateien.
        analysis = (request.method == "POST" and path in {
            "/api/comparison/analyze", "/api/comparison/rating-sheet",
            "/api/comparison/ratings/merge", "/api/comparison/panel",
            "/api/comparison/panel/evaluate"})
        if (path not in safe_paths and not read_only_runs and not analysis
                and not _operator_authorized(request)):
            return JSONResponse(
                {"error": "Operator-Authentifizierung erforderlich."},
                status_code=401)
    return await call_next(request)


def _load_json(path: str, fallback: dict) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else fallback
    except Exception:
        return fallback


def _load_unblinding_records() -> None:
    """Laedt private Entblindungsdaten ohne sie an die UI auszugeben.

    Ein Neustart darf die Zuordnung der bereits bezahlten Blindlaeufe nicht
    vernichten. Korrupte oder strukturell falsche Dateien werden deshalb nicht
    still als valide behandelt; der Server startet mit leerem Speicher und
    protokolliert den Befund.
    """
    if not os.path.exists(UNBLINDING_STORE_PATH):
        return
    value = _load_json(UNBLINDING_STORE_PATH, {})
    valid = {
        str(run_id): record for run_id, record in value.items()
        if str(run_id).startswith("run-") and isinstance(record, dict)
    }
    if value and not valid:
        _log.error("Entblindungsspeicher ist strukturell ungueltig: %s",
                   UNBLINDING_STORE_PATH)
        return
    UNBLINDING_RECORDS.update(valid)
    for record in valid.values():
        cache_key = str(record.get("cache_key") or "")
        response = record.get("blind_response")
        request_fingerprint = str(record.get("request_fingerprint") or "")
        if (re.fullmatch(r"[0-9a-f]{64}", cache_key)
                and isinstance(response, dict) and request_fingerprint):
            RUN_CACHE[cache_key] = {
                "request_fingerprint": request_fingerprint,
                "response": response,
            }
    while len(UNBLINDING_RECORDS) > MAX_CACHED_RUNS:
        UNBLINDING_RECORDS.pop(next(iter(UNBLINDING_RECORDS)))
    while len(RUN_CACHE) > MAX_CACHED_RUNS:
        RUN_CACHE.pop(next(iter(RUN_CACHE)))


def _save_unblinding_records() -> None:
    """Schreibt Entblindungsdaten atomar und nur fuer den lokalen Benutzer."""
    directory = os.path.dirname(UNBLINDING_STORE_PATH)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=directory,
                prefix=".unblinding-", suffix=".tmp", delete=False) as handle:
            temp_path = handle.name
            json.dump(UNBLINDING_RECORDS, handle, ensure_ascii=False,
                      sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, UNBLINDING_STORE_PATH)
        os.chmod(UNBLINDING_STORE_PATH, 0o600)
    except Exception:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        raise


_load_unblinding_records()


def _canonical_hash(value: object, prefix: str) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return f"{prefix}-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _instance_config() -> dict:
    try:
        with open(INSTANCE_PATH, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("VeriScout-Instanzkonfiguration ist nicht lesbar.") from error
    if not isinstance(value, dict):
        raise RuntimeError("VeriScout-Instanzkonfiguration muss ein Objekt sein.")
    required = {
        "schema_version", "instance_id", "name", "organizations",
        "search_fields", "features", "evidence_dimensions",
    }
    missing = sorted(required - set(value))
    if missing:
        raise RuntimeError(
            "VeriScout-Instanzkonfiguration unvollstaendig: " + ", ".join(missing))
    if value.get("organizations") != [] or value.get("search_fields") != []:
        raise RuntimeError(
            "Die generische VeriScout-Instanz darf keine Organisations- oder "
            "Suchfeldstammliste enthalten.")
    if (not isinstance(value.get("features"), dict)
            or not all(isinstance(item, bool)
                       for item in value["features"].values())):
        raise RuntimeError("Alle VeriScout-Feature-Schalter muessen boolesch sein.")
    expected_dimensions = {
        "identity", "startup_status", "target_identity", "target_process", "input_stream",
        "startup_capability", "transformation", "output_application",
        "relational_chain",
    }
    if set(value.get("evidence_dimensions") or []) != expected_dimensions:
        raise RuntimeError("Evidenzdimensionen der Instanz sind ungueltig.")
    return value


def _frozen_memory_records() -> list[dict]:
    value = _load_json(MEMORY_SNAPSHOT_PATH, {"records": []})
    records = value.get("records") or []
    return [dict(item) for item in records if isinstance(item, dict)]


def _code_hash() -> str:
    digest = hashlib.sha256()
    files = []
    for root, directories, filenames in os.walk(BASE):
        directories[:] = [item for item in directories if item not in {
            ".git", ".pytest_cache", "__pycache__", "artifacts", "runtime",
            "tests", ".idea", ".venv", "venv", "node_modules",
        }]
        for filename in filenames:
            path = os.path.join(root, filename)
            relative = os.path.relpath(path, BASE)
            include = filename.endswith(".py") or filename == "requirements.txt"
            include = include or (
                filename.endswith(".json") and relative.startswith((
                    "config" + os.sep, "data" + os.sep + "evaluation" + os.sep)))
            if include:
                files.append((relative, path))
    for relative, path in sorted(files):
        digest.update(relative.encode("utf-8"))
        with open(path, "rb") as handle:
            digest.update(handle.read())
    return "release-" + digest.hexdigest()[:24]

# --- Datenrestriktion -------------------------------------------------------
# Das System arbeitet ausschliesslich mit oeffentlich ableitbaren Suchfeldern.
# Die frueher genutzte interne Themenliste, abgeleitet aus einer vertraulichen
# Aufstellung realer Organisationen, ist aus diesem Ordner entfernt worden
# und wird auch nicht mehr referenziert. Die Randbedingung RB1 der Arbeit wird
# damit nicht nur zur Laufzeit eingehalten, sondern schon dadurch, dass die
# vertraulichen Daten im Projekt gar nicht vorliegen.
THEMES_PATH = Config.PUBLIC_THEMES_PATH

# Feldnamen, die ausschliesslich in der internen Aufstellung vorkamen. Taucht
# eines davon in einem Eintrag auf, stammt der Eintrag nicht aus einer
# oeffentlichen Quelle und wird verworfen.
_INTERNE_FELDER = ("prio", "ist", "soll", "notizen", "stand")


def _load_themes() -> dict:
    try:
        with open(THEMES_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"meta": {"datenklassifikation": "oeffentlich"}, "themen": []}

    def oeffentlich(t: dict) -> bool:
        if t.get("typ", "oeffentlich") != "oeffentlich":
            return False
        # Ein Eintrag mit gefuelltem Internfeld waere ein Ueberbleibsel der
        # alten Liste. Ein solcher Eintrag wird nicht ausgeliefert.
        return not any(str(t.get(f) or "").strip() for f in _INTERNE_FELDER)

    verworfen = [t for t in data.get("themen", []) if not oeffentlich(t)]
    if verworfen:
        print(f"  Datenrestriktion: {len(verworfen)} Eintrag/Eintraege mit "
              f"internen Feldern wurden nicht geladen.")
    data["themen"] = [t for t in data.get("themen", []) if oeffentlich(t)]
    return data


def _save_themes(data: dict) -> None:
    with open(THEMES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


class ScoutReq(BaseModel):
    name: str | None = None
    description: str | None = None
    use_guardrail: bool = True
    use_memory: bool = True


class QualifyReq(BaseModel):
    name: str
    approved: bool = False
    autonomy: str = "draft"
    # Nach der Freigabe unmittelbar einen Entwurf in Outlook anlegen. Der
    # Versand bleibt davon unberuehrt und erfolgt niemals durch das System.
    outlook: bool = True
    outlook_oeffnen: bool = False


class FeedbackReq(BaseModel):
    actor_id: str
    description: str
    outcome: str   # useful | not_useful
    score: int = 0
    label: bool = False


class RunReq(BaseModel):
    query: str = ""
    theme_id: str | None = None
    actor_id: str | None = None
    push_mode: bool = False
    n: int = 6
    waves: int = 1
    use_guardrail: bool = True
    use_memory: bool = False


class ComparisonReq(BaseModel):
    actor_id: str | None = None
    theme_id: str | None = None
    organization_id: str | None = None
    organization_name: str | None = None
    organization_domain_hint: str | None = None
    search_prompt: str | None = None
    search_field: dict | None = None
    dataset_split: str = "pilot"
    event_time: str | None = None
    repetitions: int = 1
    memory_mode: str = "off"  # off | frozen | both; on bleibt Legacy-Alias
    baseline: str = "sas2"
    confirm_live: bool = False
    custom_title: str | None = None
    custom_description: str | None = None
    # push | pull; bei pull das von der Organisation benannte Suchfeld
    search_mode: str = "push"
    search_area: str | None = None
    # True = Studienlauf fuer die Masterarbeit (getrennt gespeichert und gelistet)
    study_run: bool = False
    # Fallblatt fuer die Bewertenden. Referenzmaterial: geht nie an SAS-2/MAS.
    case_sheet: dict | None = None
    idempotency_key: str | None = None
    # Fuer Holdout verpflichtend; Pilotlaeufe erhalten sonst eine stabile,
    # aus dem Task-Hash abgeleitete Studien-ID.
    study_id: str | None = None
    allocation_seed: str | None = None


class UnblindReq(BaseModel):
    run_id: str
    annotation_commitment_sha256: str
    confirm_annotations_locked: bool = False


class ThemeAddReq(BaseModel):
    typ: str = "Organisation"
    unternehmen: str
    themengebiet: str
    beschreibung: str = ""
    prio: int | None = None
    notizen: str = ""


@app.get("/", response_class=HTMLResponse)
def index():
    p = os.path.join(BASE, "static", "index.html")
    if not os.path.exists(p):
        return HTMLResponse("<h1>index.html fehlt</h1>")
    html = open(p, encoding="utf-8").read()
    # Cache-Busting automatisch: Die Version der eingebundenen Dateien wird aus
    # deren Aenderungszeit gebildet. Eine feste Nummer im Markup veraltet sonst
    # unbemerkt, und der Browser liefert weiter alten Code aus.
    for datei in ("app.js", "app.css"):
        pfad = os.path.join(BASE, "static", datei)
        if os.path.exists(pfad):
            stempel = int(os.path.getmtime(pfad))
            html = re.sub(rf"(/static/{re.escape(datei)})(\?v=[^\"']*)?",
                          rf"\1?v={stempel}", html)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


def _reuse_policy() -> dict:
    return {"threshold": Config.THRESHOLD_SUFFICIENT,
            "budget": asdict(ExperimentBudget()), "baseline": "sas2",
            "evidence_dimensions": _instance_config()["evidence_dimensions"],
            "dataset_split": "pilot", "memory_mode": "off", "repetitions": 1,
            "crm_write": False, "outreach_write": False,
            "protocol_version": reuse.PROTOCOL_VERSION}


def _reuse_release_hash() -> str:
    # A UI study needs its interface and instructions bound as well as Python.
    files = ["reuse.py", "server.py", "static/index.html", "static/app.js",
             "static/app.css",
             "docs/MARC_TRANSFERTEST.md", "docs/REFERENCE_MODEL_CARD.md"]
    hashes = {}
    for name in files:
        path = os.path.join(BASE, name)
        if os.path.isfile(path):
            with open(path, "rb") as handle:
                hashes[name] = hashlib.sha256(handle.read()).hexdigest()
    return reuse.digest({"code": _code_hash(), "interface": hashes})


@app.get("/api/comparison/reuse/protocol")
def reuse_protocol():
    return {**reuse.protocol(), "policy": _reuse_policy(),
            "policy_sha256": reuse.digest(_reuse_policy()),
            "release_sha256": _reuse_release_hash()}


def validate_workspace_payload(value: object) -> dict:
    workspace, previous = reuse.unpack_workspace(value)
    task, packet = _comparison_task(
        ComparisonReq(**reuse.request_for_workspace(workspace)), strict=True)
    policy = _reuse_policy()
    policy_hash, release_hash = reuse.digest(policy), _reuse_release_hash()
    warnings = []
    if previous and previous["policy_sha256"] != policy_hash:
        warnings.append("Serverregeln haben sich seit dem Export geändert. Kein identisches Experiment. Neue Version dokumentieren.")
    if previous and previous["release_sha256"] != release_hash:
        warnings.append("Programmstand hat sich seit dem Export geändert. Den Transfer mit dieser Version neu dokumentieren.")
    return {"status": "valid", "paid_calls": 0, "warnings": warnings,
            "receipt": {"workspace": workspace, "workspace_sha256": reuse.digest(workspace),
                        "policy_sha256": policy_hash, "release_sha256": release_hash},
            "policy": policy, "task": packet.canonical_dict(),
            "prompt_hash": packet.prompt_hash(), "task_input_hash": packet.input_hash(),
            "live_started": False}


@app.post("/api/comparison/workspace/validate")
async def workspace_validate(request: Request):
    # Stateless and cost-free. Does not replace the running instance or memory.
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > reuse.MAX_BYTES:
            return JSONResponse({"error": "Projektdatei ist größer als 16 KB."}, status_code=413)
        chunks.append(chunk)
    try:
        value = json.loads(b"".join(chunks))
        return validate_workspace_payload(value)
    except (ValueError, TypeError, UnicodeDecodeError):
        # Do not echo arbitrary payload text or credentials in validation errors.
        return JSONResponse({"error": "Ungültige Projektdatei. Prüfe Version, Pflichtfelder, Fingerabdruck und einen nicht zukünftigen Zeitpunkt mit Zeitzone. Der aktuelle Auftrag bleibt erhalten."}, status_code=400)


@app.get("/api/actors")
def actors():
    return [{"id": a["id"], "name": a["name"], "rolle": a.get("rolle", ""),
             "standort": a.get("standort", ""), "sectors": a.get("sectors", [])}
            for a in PIPE.kb.actors]


def _comparison_task(req: ComparisonReq, *, strict: bool) -> tuple[ComparisonTask, object]:
    organization_name = str(req.organization_name or "").strip()
    organization_domain_hint = str(
        req.organization_domain_hint or "").strip()

    # Legacy-Instanzen bleiben nur bei ausdruecklich aktiviertem Feature Flag
    # lesbar. Die generische Auslieferung enthaelt keine Organisationsliste.
    legacy_id = str(req.actor_id or "").strip()
    if LEGACY_API_ENABLED and legacy_id and not organization_name:
        try:
            actor = PIPE.kb.get(legacy_id)
            organization_name = str(actor.get("name") or legacy_id)
        except Exception:
            pass
    if not organization_name:
        raise ValueError("organization_name ist erforderlich.")
    organization_id = stable_organization_id(
        organization_name, organization_domain_hint)
    supplied_id = str(req.organization_id or "").strip()
    if supplied_id and supplied_id != organization_id:
        raise ValueError(
            "organization_id wird technisch erzeugt und darf nicht vorgegeben werden.")

    field_value = dict(req.search_field or {})
    search_prompt = str(
        req.search_prompt or field_value.get("description")
        or req.custom_description or "").strip()
    if not search_prompt:
        raise ValueError("search_prompt ist erforderlich.")
    search_mode = str(req.search_mode or "push").strip().lower()
    search_area = " ".join(str(req.search_area or "").split())
    # PUSH behaelt die bisherige Auftragskennung; PULL bindet das Suchfeld ein.
    digest_source = (search_prompt if search_mode == "push"
                     else f"{search_prompt}|pull|{search_area}")
    prompt_digest = hashlib.sha256(
        digest_source.encode("utf-8")).hexdigest()[:12]
    task = ComparisonTask(
        task_id=f"{organization_id}-prompt-{prompt_digest}",
        organization_id=organization_id,
        organization_name=organization_name,
        organization_domain_hint=organization_domain_hint,
        search_prompt=search_prompt,
        public_source_package=(),
        task_group_id=f"{organization_id}-prompt-{prompt_digest}",
        dataset_split=str(req.dataset_split or "pilot"),
        event_time=str(req.event_time or ""),
        search_mode=search_mode,
        search_area=search_area,
    )
    return task, task.public_input(strict=strict)


@app.get("/api/comparison/config")
def comparison_config():
    instance = _instance_config()
    memory_records = _frozen_memory_records()
    memory_store = MemoryStore(records=memory_records, read_only=True)
    live_ready = bool(
        LIVE_EVAL_ENABLED and os.environ.get("OPENAI_API_KEY")
        and OPERATOR_TOKEN)
    blockers = []
    if not LIVE_EVAL_ENABLED:
        blockers.append({"code": "server_disabled", "message":
            "Die serverseitige Freigabe für kostenpflichtige Läufe fehlt."})
    if not os.environ.get("OPENAI_API_KEY"):
        blockers.append({"code": "api_key_missing", "message":
            "Es ist kein OpenAI-API-Schlüssel konfiguriert."})
    if not OPERATOR_TOKEN:
        blockers.append({"code": "operator_missing", "message":
            "Der lokale Bedienerschlüssel ist noch nicht eingerichtet."})
    return {
        "version": Config.VERSION,
        "brand": Config.PRODUCT_NAME,
        "analysis_parameters": {
            "ni_margin_precision": Config.EVAL_NI_MARGIN_PRECISION,
            "min_improvement": Config.EVAL_MIN_IMPROVEMENT,
            "web_overrun_policy": Config.EVAL_WEB_OVERRUN_POLICY,
            "excerpt_match_mode": Config.EXCERPT_MATCH_MODE,
            "budget_profile": Config.BUDGET_PROFILE_VERSION,
        },
        "live_enabled": live_ready,
        "live_blockers": blockers,
        "run_profile": ("transfer_review" if TRANSFER_REVIEW_MODE else
                        "local_development" if LOCAL_REVIEW_MODE else "standard"),
        "profile_notice": (
            "Entwicklungsmodus: ein gepaartes Pilotexperiment, maximal ein "
            "Kandidat je Arm, ohne Memory. Kein Abschlusstest der Hauptstudie."
            if LOCAL_REVIEW_MODE else ""),
        "api_key_configured": bool(os.environ.get("OPENAI_API_KEY")),
        "operator_auth_configured": bool(OPERATOR_TOKEN),
        "default_budget": asdict(ExperimentBudget()),
        "study_budget": STUDY_BUDGET.snapshot(),
        "instance": {
            "instance_id": instance.get("instance_id", "scoutref-default"),
            "name": instance.get("name", "VeriScout Default"),
            "schema_version": instance.get("schema_version", ""),
            "config_hash": _canonical_hash(instance, "instance"),
        },
        "actors": [],
        "public_search_fields": [],
        "supports_external_organization": True,
        "supports_custom_field": True,
        "capabilities": {
            "external_organization": True,
            "custom_search_field": True,
            "legacy_api": LEGACY_API_ENABLED,
            "crm_write": LIVE_CRM,
            "outreach_write": False,
        },
        "input_contract": {
            "required": ["organization_name", "search_prompt"],
            "optional": [
                "organization_domain_hint", "event_time", "dataset_split"],
            "generated": ["organization_id", "task_id"],
            "forbidden_as_input_evidence": [
                "organization_public_url", "source_url", "source_excerpt",
                "source_review_status", "source_reviewer_id"],
        },
        "evidence_policy": {
            "origin": "SAS-/MAS-Rechercheoutput",
            "resolution": "URL-Aufloesung und Belegpruefung nach der Recherche",
            "positive_decision": (
                "fail-closed bei ambiger Organisationsidentitaet oder fehlender "
                "Output-Evidenz"),
        },
        "memory": {
            "snapshot_id": memory_store.snapshot_id(),
            "record_count": len(memory_records),
            "read_only": True,
        },
        "memory_modes": ["off", "frozen", "both"],
        "primary_baseline": "sas2",
        "primary_contrast": "sas2_self_review_vs_mas",
        "safety": (
            "Live-Vergleiche brauchen confirm_live, Operator-Authentifizierung "
            "und SCOUTREF_EVAL_LIVE_ENABLED=1."),
    }


@app.post("/api/comparison/preview")
def comparison_preview(req: ComparisonReq):
    try:
        task, packet = _comparison_task(req, strict=False)
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=400)
    try:
        strict_packet = task.public_input(strict=True)
        readiness = strict_packet.readiness()
    except ValueError as error:
        readiness = {
            "status": "draft_not_ready",
            "issues": [str(error)],
            "confirmatory": False,
        }
    return {
        "status": readiness["status"],
        "readiness": readiness,
        "task": packet.canonical_dict(),
        "prompt_hash": packet.prompt_hash(),
        "task_input_hash": packet.input_hash(),
        "input_evidence_count": 0,
        "output_evidence_status": "not_run",
        "primary_contrast": "sas2_self_review_vs_mas",
        "paid_calls": 0,
        "note": "Preview erzeugt keine API-Kosten.",
    }


def _planned_assignments(req: ComparisonReq, packet,
                         memory_states: list[bool]) -> tuple[str, dict, list[dict]]:
    """Laedt oder friert den kostenfreien Ausfuehrungsplan vor API-Aufrufen ein."""
    requested_study = str(req.study_id or "").strip()
    holdout = str(req.dataset_split or "").strip().casefold() == "holdout"
    if holdout and not requested_study:
        raise ValueError("Holdout-Laeufe brauchen eine vorab festgelegte study_id.")
    study_id = requested_study or (
        "pilot-" + packet.input_hash().split("-", 1)[-1][:16])
    if not re.fullmatch(r"[A-Za-z0-9._:-]{6,120}", study_id):
        raise ValueError("study_id enthaelt unzulaessige Zeichen oder ist zu kurz.")
    if holdout:
        assignments = HOLDOUT_REGISTRY.assignments(
            study_id=study_id,
            task_input_hash=packet.input_hash(),
            repetitions=int(req.repetitions),
            memory_states=memory_states,
            event_time=str(req.event_time or ""),
        )
        return study_id, {"manifest_hash": "external-holdout"}, assignments

    seed = str(req.allocation_seed or "").strip() or hashlib.sha256(
        ("allocation|" + study_id).encode("utf-8")).hexdigest()[:24]
    path = os.path.join(STUDY_PLAN_ROOT, study_id + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
        plan = list(manifest.get("plan") or [])
        matching = [item for item in plan
                    if item.get("task_input_hash") == packet.input_hash()
                    and bool(item.get("memory_enabled")) in set(memory_states)
                    and int(item.get("replicate_index") or 0)
                    <= int(req.repetitions)]
        if (str(manifest.get("study_id") or "") != study_id
                or str(manifest.get("allocation_seed") or "") != seed
                or len(matching) != int(req.repetitions) * len(memory_states)):
            raise ValueError(
                "Der Studienname ist bereits mit einem anderen Plan belegt. "
                "Fuer Aenderungen eine neue study_id verwenden.")
        return study_id, manifest, sorted(
            matching, key=lambda item: int(item["block_index"]))

    manifest = build_balanced_plan(
        study_id=study_id,
        task_rows=[{"task_id": packet.task_id,
                    "task_input_hash": packet.input_hash()}],
        repetitions=int(req.repetitions),
        memory_states=memory_states,
        allocation_seed=seed,
    )
    save_frozen_plan(path, manifest)
    return study_id, manifest, list(manifest["plan"])


def _finalize_comparison_run(*, packet, runner, memory_records,
                             blind_pairs: list, internal_pairs: list,
                             manifests: list, request_fingerprint: str,
                             cache_key: str, study_id: str = "",
                             study_manifest_hash: str = "",
                             run_set: str = "probe",
                             reference: dict | None = None) -> dict:
    """Erzeugt und registriert die getrennten Studienartefakte unter Lock."""
    instance = _instance_config()
    model_calls = [
        {key: record.get(key) for key in (
            "call_id", "response_id", "timestamp_utc", "purpose", "status",
            "model_requested", "model_returned", "reasoning_effort",
            "system_prompt_sha256", "user_prompt_sha256",
            "request_payload_sha256", "api_contract", "api_endpoint",
            "max_output_tokens", "max_tool_calls",
            "web_search_context_size", "input_tokens", "output_tokens",
            "reasoning_tokens", "cached_input_tokens", "tool_calls")}
        for pair in internal_pairs for arm in pair.get("arms", [])
        for record in arm.get("usage", [])
    ]
    price_manifest = {
        "vintage": Config.PRICE_VINTAGE,
        "token_prices_usd_per_million": Config.PRICES,
        "web_search_price_usd": Config.WEB_SEARCH_PRICE,
    }
    arm_validity = [{
        "pair_id": pair.get("pair_id"),
        "blind_arm_id": arm.get("blind_arm_id"),
        "result_status": arm.get("result_status"),
        "primary_analysis_eligible": bool(
            arm.get("primary_analysis_eligible")),
        "primary_exclusion_reason": arm.get("primary_exclusion_reason", ""),
        "budget_violation": bool(arm.get("budget_violation")),
        "stage_artifact_hashes": deepcopy(
            arm.get("stage_artifact_hashes") or {}),
    } for pair in internal_pairs for arm in pair.get("arms", [])]
    run_bundle_manifest = {
        "schema_version": "venture-scout-run-bundle-v2",
        "code_hash": _code_hash(),
        "instance_hash": _canonical_hash(instance, "instance"),
        "study_id": study_id,
        "study_manifest_hash": study_manifest_hash,
        "task_input_hash": packet.input_hash(),
        "prompt_hash": packet.prompt_hash(),
        "input_evidence_count": 0,
        "evidence_origin": "architecture_output",
        "memory_snapshot": MemoryStore(
            records=memory_records, read_only=True).snapshot_id(),
        "budget_hash": _canonical_hash(asdict(runner.budget), "budget"),
        "budget": asdict(runner.budget),
        "models": {
            "sas": Config.MODEL_SAS,
            "scouting": Config.MODEL_SCOUT,
            "verification": Config.MODEL_VERIFY,
        },
        "reasoning_effort": runner.budget.reasoning_effort,
        "api_contract": Config.API_CONTRACT,
        "api_endpoint": Config.OPENAI_RESPONSES_URL,
        "prompt_contract_version": Config.PROMPT_CONTRACT_VERSION,
        "model_calls": model_calls,
        "price_manifest": price_manifest,
        "price_manifest_hash": _canonical_hash(price_manifest, "prices"),
        "decision_rule": {
            "threshold": Config.THRESHOLD_SUFFICIENT,
            "role": "necessary_not_sufficient",
            "rubric_version": Config.THRESHOLD_RUBRIC_VERSION,
            "evidence_coverage_definition": (
                "number of supported required relational dimensions divided "
                "by the fixed number of required dimensions; equal weights"),
            "positive_requires": (
                "threshold_and_fully_supported_and_all_quality_gates"),
        },
        "runtime": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "arm_validity": arm_validity,
    }
    run_bundle_manifest["manifest_hash"] = _canonical_hash(
        run_bundle_manifest, "run-bundle")
    run_id = "run-" + uuid.uuid4().hex
    response = {
        "status": "completed",
        "run_id": run_id,
        "task_input_hash": packet.input_hash(),
        "prompt_hash": packet.prompt_hash(),
        "pairs": blind_pairs,
        "annotation_contract": {
            "blind": True,
            "system_judgments_removed": True,
            "assignment_withheld": True,
        },
        "unblinding": {
            "status": "locked",
            "requirement": "finalisierte Annotationen per SHA-256 binden",
        },
        "run_bundle_manifest": run_bundle_manifest,
        "primary_analysis_ready": bool(arm_validity) and all(
            item["primary_analysis_eligible"] for item in arm_validity),
    }
    created_at = datetime.now(timezone.utc).isoformat()
    view = operator_view(internal_pairs, run_id=run_id, created_at=created_at)
    response["operator_view"] = view
    view["run_set"] = run_set
    _save_run_record(run_id, {
        "run_set": run_set,
        "operator_view": view,
        "blind_pairs": blind_pairs,
        "assignment_manifests": manifests,
        "run_bundle_manifest": run_bundle_manifest,
        # Vollstaendige interne Daten fuer kostenfreie Neubewertung und Nachweis.
        "internal_pairs": internal_pairs,
        # Referenzmaterial (Fallblatt), getrennt von den Architekturdaten.
        "reference": deepcopy(reference or {}),
    })
    UNBLINDING_RECORDS[run_id] = {
        "request_fingerprint": request_fingerprint,
        "cache_key": cache_key,
        "blind_response": response,
        "internal_pairs": internal_pairs,
        "assignment_manifests": manifests,
        "run_bundle_manifest": run_bundle_manifest,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "unblinded_at": "",
        "annotation_commitment_sha256": "",
    }
    RUN_CACHE[cache_key] = {
        "request_fingerprint": request_fingerprint,
        "response": response,
    }
    while len(RUN_CACHE) > MAX_CACHED_RUNS:
        RUN_CACHE.pop(next(iter(RUN_CACHE)))
    while len(UNBLINDING_RECORDS) > MAX_CACHED_RUNS:
        UNBLINDING_RECORDS.pop(next(iter(UNBLINDING_RECORDS)))
    _save_unblinding_records()
    return response


@app.post("/api/comparison/run")
def comparison_run(req: ComparisonReq, request: Request = None):
    if not _operator_authorized(request):
        return JSONResponse(
            {"error": "Operator-Authentifizierung erforderlich."},
            status_code=401)
    if not req.confirm_live:
        return JSONResponse(
            {"error": "Live-Lauf nicht bestaetigt (confirm_live=false)."},
            status_code=403)
    if not LIVE_EVAL_ENABLED:
        return JSONResponse(
            {"error": "Live-Evaluation ist serverseitig gesperrt."},
            status_code=403)
    if not os.environ.get("OPENAI_API_KEY"):
        return JSONResponse({"error": "API-Schluessel fehlt."}, status_code=503)
    if LOCAL_REVIEW_MODE and (
        req.dataset_split not in {"pilot", "development"}
        or req.repetitions != 1 or req.memory_mode != "off"
    ):
        return JSONResponse({"error":
            "Der lokale Entwicklungsmodus erlaubt nur einen gepaarten "
            "Pilotlauf ohne Memory. Für eine Hauptstudie ist eine eigene "
            "eingefrorene Konfiguration erforderlich."}, status_code=422)
    if not 1 <= int(req.repetitions) <= 10:
        return JSONResponse(
            {"error": "repetitions muss zwischen 1 und 10 liegen."},
            status_code=400)
    if req.memory_mode not in {"off", "frozen", "both", "on"}:
        return JSONResponse(
            {"error": "memory_mode muss off, frozen oder both sein."},
            status_code=400)
    if req.baseline != "sas2":
        return JSONResponse(
            {"error": "Der konfirmatorische Primaervergleich verwendet sas2."},
            status_code=400)
    idempotency_key = str(req.idempotency_key or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{20,160}", idempotency_key):
        return JSONResponse(
            {"error": "Ein gueltiger idempotency_key ist erforderlich."},
            status_code=400)
    request_payload = (req.model_dump() if hasattr(req, "model_dump")
                       else req.dict())
    request_fingerprint = _canonical_hash(request_payload, "request")
    cache_key = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    cached = RUN_CACHE.get(cache_key)
    if cached:
        if cached["request_fingerprint"] != request_fingerprint:
            return JSONResponse(
                {"error": "idempotency_key wurde bereits fuer einen anderen "
                          "Auftrag verwendet."}, status_code=409)
        return cached["response"]
    try:
        task, packet = _comparison_task(req, strict=True)
    except ValueError as error:
        return JSONResponse(
            {"error": "Auftrag ist nicht konfirmatorisch bereit: " + str(error)},
            status_code=422)
    try:
        case_sheet = normalise_case_sheet(req.case_sheet)
    except ValueError as error:
        return JSONResponse({"error": str(error)}, status_code=422)
    memory_states = ([False, True] if req.memory_mode == "both"
                     else [req.memory_mode in {"frozen", "on"}])
    memory_records = _frozen_memory_records()
    if req.memory_mode in {"frozen", "both", "on"} and not memory_records:
        return JSONResponse(
            {"error": "Frozen Memory ist aktiviert, aber der Snapshot ist leer."},
            status_code=422)
    runner = PairedArchitectureRunner(
        live=True, memory_records=memory_records)
    try:
        study_id, study_manifest, planned = _planned_assignments(
            req, packet, memory_states)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as error:
        return JSONResponse(
            {"error": "Studienplan ist nicht ausfuehrbar: " + str(error)},
            status_code=422)
    projected_max_cost = (
        runner.budget.arm_max_cost_usd * 2 * int(req.repetitions)
        * len(memory_states))
    if projected_max_cost > RUN_MAX_COST_USD:
        return JSONResponse(
            {"error": "Der angeforderte Lauf ueberschreitet den serverseitigen "
                      "Gesamtkostenstopp.",
             "projected_max_cost_usd": round(projected_max_cost, 4),
             "run_max_cost_usd": RUN_MAX_COST_USD}, status_code=422)
    if not RUN_LOCK.acquire(blocking=False):
        return JSONResponse(
            {"error": "Ein kostenpflichtiger Vergleich laeuft bereits."},
            status_code=409)
    internal_pairs = []
    blind_pairs = []
    manifests = []
    reservation_id = "comparison-" + cache_key
    reservation_active = False
    settled = False
    try:
        # Nach Lock erneut pruefen, damit zwei zeitgleiche identische Requests
        # nicht beide Kosten ausloesen.
        cached = RUN_CACHE.get(cache_key)
        if cached:
            if cached["request_fingerprint"] != request_fingerprint:
                return JSONResponse(
                    {"error": "idempotency_key wurde bereits fuer einen anderen "
                          "Auftrag verwendet."}, status_code=409)
            return cached["response"]
        try:
            STUDY_BUDGET.reserve(
                reservation_id, projected_max_cost,
                metadata={
                    "study_id": study_id,
                    "task_input_hash": packet.input_hash(),
                    "pairs": len(planned),
                    "model": runner.budget.model,
                    "price_vintage": "2026-08-31",
                })
            reservation_active = True
        except RuntimeError as error:
            return JSONResponse(
                {"error": str(error), "study_budget": STUDY_BUDGET.snapshot()},
                status_code=422)
        if str(req.dataset_split or "").casefold() == "holdout":
            # Die Reservierung im Holdout-Ledger erfolgt unmittelbar vor dem
            # ersten API-Aufruf. Auch ein technischer Fehler bleibt erhalten
            # und darf nicht unter neuer ID selektiv ersetzt werden.
            HOLDOUT_REGISTRY.claim(planned)
        for assignment in planned:
            run_parameters = inspect.signature(runner.run_pair).parameters
            run_kwargs = {
                "memory_enabled": bool(assignment.get("memory_enabled")),
            }
            if "planned_assignment" in run_parameters:
                run_kwargs["planned_assignment"] = assignment
            result = runner.run_pair(task, **run_kwargs)
            internal_pairs.append(result)
            if str(req.dataset_split or "").casefold() == "holdout":
                HOLDOUT_REGISTRY.finalize(
                    assignment,
                    result_status=(
                        "technical_error" if any(
                            arm.get("result_status") == "technical_error"
                            for arm in result.get("arms", []))
                        else "not_checked_budget" if any(
                            arm.get("result_status") == "not_checked_budget"
                            for arm in result.get("arms", []))
                        else "completed"),
                    result_hash=_canonical_hash(result, "sha256"),
                )
            package = annotation_package(result)
            if case_sheet:
                package["case_sheet"] = case_sheet
                package["case_sheet_sha256"] = case_sheet_hash(case_sheet)
            blind_pairs.append({"blind_annotation": package})
            manifest = assignment_manifest(result)
            manifest["model"] = runner.budget.model
            manifest["study_role"] = "primary"
            manifests.append(manifest)
        actual_cost = round(sum(
            float((arm.get("resource_usage") or {}).get("cost_usd") or 0.0)
            for pair in internal_pairs for arm in pair.get("arms", [])
        ), 6)
        STUDY_BUDGET.settle(reservation_id, actual_cost)
        settled = True
        response = _finalize_comparison_run(
            packet=packet, runner=runner, memory_records=memory_records,
            blind_pairs=blind_pairs, internal_pairs=internal_pairs,
            manifests=manifests, request_fingerprint=request_fingerprint,
            cache_key=cache_key, study_id=study_id,
            study_manifest_hash=str(study_manifest.get("manifest_hash") or ""),
            run_set=("studie" if req.study_run else "probe"),
            reference=({"case_sheet": case_sheet,
                        "case_sheet_sha256": case_sheet_hash(case_sheet)}
                       if case_sheet else {}))
        response["study"] = {
            "study_id": study_id,
            "manifest_hash": study_manifest.get("manifest_hash"),
            "planned_pairs": len(planned),
            "actual_cost_usd": actual_cost,
            "local_budget": STUDY_BUDGET.snapshot(),
        }
        _save_unblinding_records()
        return response
    finally:
        if reservation_active and not settled:
            observed = round(sum(
                float((arm.get("resource_usage") or {}).get("cost_usd") or 0.0)
                for pair in internal_pairs for arm in pair.get("arms", [])
            ), 6)
            # Bei abgebrochenen Providerantworten kann lokale Nutzung fehlen.
            # Deshalb bleibt konservativ der reservierte Hoechstbetrag belastet.
            try:
                STUDY_BUDGET.settle(
                    reservation_id, observed, uncertain=True)
            except Exception:
                _log.exception("Studienbudget konnte nicht finalisiert werden")
        RUN_LOCK.release()


@app.get("/api/comparison/local-operator")
def local_operator(request: Request):
    """Gibt den Bedienerschluessel nur im lokalen Einzelplatzmodus an die
    eigene Oberflaeche aus.

    Der Schluessel schuetzt weiterhin davor, dass eine fremde Webseite im
    selben Browser einen bezahlten Lauf ausloest: Der Browser liefert diese
    Antwort nur an Seiten derselben Herkunft (127.0.0.1/localhost) aus, und
    Anfragen mit fremdem Host oder Origin werden abgewiesen. Im normalen
    Betrieb (kein lokaler Modus) bleibt der Endpunkt gesperrt.
    """
    host = str(request.headers.get("host") or "").split(":")[0].lower()
    origin = str(request.headers.get("origin") or "")
    origin_host = (origin.split("://", 1)[-1].split(":")[0].lower()
                   if origin else host)
    local = {"127.0.0.1", "localhost"}
    if (not LOCAL_REVIEW_MODE or not OPERATOR_TOKEN
            or host not in local or origin_host not in local):
        return JSONResponse({"error": "Nur im lokalen Live-Modus verfuegbar."},
                            status_code=403)
    return {"operator_token": OPERATOR_TOKEN}


RUNS_DIR = os.environ.get("SCOUTREF_RUNS_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "artifacts", "runs")


def _save_run_record(run_id: str, record: dict) -> None:
    """Speichert einen Lauf lokal, damit er ohne API-Kosten erneut gezeigt
    werden kann. Die Datei enthaelt keine Zugangsdaten."""
    try:
        os.makedirs(RUNS_DIR, exist_ok=True)
        path = os.path.join(RUNS_DIR, f"{run_id}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=1)
    except OSError:
        _log.exception("Laufdatei konnte nicht gespeichert werden")


@app.get("/api/comparison/runs")
def comparison_runs():
    rows = []
    if os.path.isdir(RUNS_DIR):
        for name in sorted(os.listdir(RUNS_DIR), reverse=True):
            if not re.fullmatch(r"[A-Za-z0-9._-]+\.json", name):
                continue
            try:
                with open(os.path.join(RUNS_DIR, name), encoding="utf-8") as handle:
                    view = json.load(handle).get("operator_view") or {}
            except (OSError, ValueError):
                continue
            arms = [arm for pair in view.get("pairs") or [] for arm in pair.get("arms") or []]
            with open(os.path.join(RUNS_DIR, name), "rb") as handle:
                file_sha256 = hashlib.sha256(handle.read()).hexdigest()
            rows.append({
                "run_set": view.get("run_set") or "probe",
                "file_sha256": file_sha256,
                "run_id": view.get("run_id") or name[:-5],
                "created_at": view.get("created_at", ""),
                "organization_name": (view.get("task") or {}).get("organization_name", ""),
                "model": view.get("model", ""),
                "reevaluated": bool(view.get("reevaluated_from")),
                "pairs": len(view.get("pairs") or []),
                "cost_usd": round(sum(float((arm.get("resources") or {}).get("cost_usd") or 0)
                                      for arm in arms), 4),
                "states": {arm.get("architecture"): arm.get("result_status") for arm in arms},
            })
    rows.sort(key=lambda row: row["created_at"], reverse=True)
    return {"runs": rows}


@app.get("/api/comparison/runs/{run_id}")
def comparison_run_record(run_id: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]{4,120}", run_id or ""):
        return JSONResponse({"error": "Ungueltige Lauf-ID."}, status_code=400)
    path = os.path.join(RUNS_DIR, f"{run_id}.json")
    if not os.path.isfile(path):
        return JSONResponse({"error": "Lauf nicht gefunden."}, status_code=404)
    with open(path, encoding="utf-8") as handle:
        record = json.load(handle)
    _attach_source_locations(record)
    return record


def _attach_source_locations(record: dict) -> None:
    """Nur fuer die Anzeige: tatsaechlich abgerufene Adresse und Fundstellen-
    Kontext aus den internen Quelldaten an die Bedieneransicht haengen.

    Die Laufdatei bleibt unveraendert (es wird nichts geschrieben), Entscheidungen
    und Bewertungsdaten werden nicht beruehrt. Alte Laeufe ohne Kontext erhalten
    nur die abgerufene Adresse.
    """
    internal = record.get("internal_pairs")
    if internal is None:
        internal = [record["internal_pair"]] if isinstance(record.get("internal_pair"), dict) else []
    lookup = {}
    for pair in internal or []:
        for arm in pair.get("arms") or []:
            architecture = arm.get("architecture_internal")
            for decision in arm.get("decisions") or []:
                candidate = decision.get("candidate") or {}
                for source in candidate.get("sources") or []:
                    key = (pair.get("pair_id"), architecture,
                           candidate.get("candidate_id"), source.get("source_id"))
                    lookup[key] = source
    view = record.get("operator_view") or {}
    for pair in view.get("pairs") or []:
        for arm in pair.get("arms") or []:
            for candidate in arm.get("candidates") or []:
                for source in candidate.get("sources") or []:
                    raw = lookup.get((pair.get("pair_id"), arm.get("architecture"),
                                      candidate.get("candidate_id"), source.get("source_id")))
                    if not raw:
                        continue
                    source.setdefault("resolved_url", raw.get("resolved_url") or "")
                    source.setdefault("matched_context", raw.get("matched_context") or "")


class AnalyzeReq(BaseModel):
    annotations: list
    manifests: list


@app.post("/api/comparison/analyze")
def comparison_analyze(req: AnalyzeReq):
    """Kostenfreie Auswertung finaler Annotationen gegen die Zuordnungsdateien."""
    try:
        metrics = paired_metrics(list(req.annotations), list(req.manifests))
        bayes = bayesian_paired_difference(metrics["primary_itt"])
        # Sekundaer: je Modell und je Unternehmensgruppe (Variante A).
        bayes_by_model = {name: bayesian_paired_difference(block)
                          for name, block in metrics["by_model"].items()}
        bayes_by_stratum = {name: bayesian_paired_difference(block)
                            for name, block in metrics["by_stratum"].items()}
    except (ValueError, KeyError, TypeError) as error:
        return JSONResponse({"error": str(error)}, status_code=422)
    return {"metrics": metrics, "bayes": bayes,
            "bayes_by_model": bayes_by_model,
            "bayes_by_stratum": bayes_by_stratum}


def _load_run_records(scope: str, run_id: str = "") -> list[dict]:
    """Laedt Laufdateien fuer Bewertung und Auswertung (ohne Neubewertungen).

    Neubewertete Laufdateien enthalten dieselben Paare wie ihr Original und
    wuerden sonst doppelt bewertet.
    """
    records = []
    if scope == "run":
        if not re.fullmatch(r"[A-Za-z0-9._-]{4,120}", run_id or ""):
            raise ValueError("Ungueltige Lauf-ID.")
        names = [f"{run_id}.json"]
    elif scope in {"studie", "probe"}:
        names = sorted(os.listdir(RUNS_DIR)) if os.path.isdir(RUNS_DIR) else []
    else:
        raise ValueError("scope muss studie, probe oder run sein.")
    for name in names:
        if not re.fullmatch(r"[A-Za-z0-9._-]+\.json", name):
            continue
        path = os.path.join(RUNS_DIR, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
        view = record.get("operator_view") or {}
        if scope != "run" and (
                (record.get("run_set") or view.get("run_set") or "probe") != scope
                or view.get("reevaluated_from")):
            continue
        records.append(record)
    if not records:
        raise ValueError("Keine passenden Laufdateien gefunden.")
    # Wiederholte Oberflaechenlaeufe derselben Aufgabe tragen dieselbe Paar-ID.
    # Fuer Bewertung und Auswertung wird sie dann um die Lauf-ID ergaenzt,
    # in Bogen und Zuordnungsdatei gleich; die Laufdateien bleiben unveraendert.
    counts: dict[str, int] = {}
    for record in records:
        for manifest in record.get("assignment_manifests") or []:
            pair_id = str(manifest.get("pair_id") or "")
            counts[pair_id] = counts.get(pair_id, 0) + 1
    for record in records:
        run_id = str((record.get("operator_view") or {}).get("run_id") or "")
        for manifest in record.get("assignment_manifests") or []:
            if counts.get(str(manifest.get("pair_id") or ""), 0) > 1:
                manifest["pair_id"] = f"{manifest['pair_id']}@{run_id}"
        for pair in record.get("blind_pairs") or []:
            package = pair.get("blind_annotation") or pair
            if counts.get(str(package.get("pair_id") or ""), 0) > 1:
                package["pair_id"] = f"{package['pair_id']}@{run_id}"
    return records


def _record_manifests(record: dict) -> list[dict]:
    """Zuordnungsdateien mit Modell, Rolle und Gruppe fuer die Auswertung."""
    view = record.get("operator_view") or {}
    study = record.get("study") or {}
    out = []
    for manifest in record.get("assignment_manifests") or []:
        item = deepcopy(manifest)
        item.setdefault("model", study.get("model") or view.get("model") or "")
        item.setdefault("study_role", study.get("role") or "primary")
        item.setdefault("stratum", study.get("stratum") or "")
        out.append(item)
    return out


class RatingSheetReq(BaseModel):
    scope: str = "studie"
    run_id: str = ""
    purpose: str = "studie"
    include_stability: bool = False


@app.post("/api/comparison/rating-sheet")
def comparison_rating_sheet(req: RatingSheetReq):
    """Erzeugt Offline-Bewertungsbogen, Schluessel und Zuordnungsdatei."""
    try:
        records = _load_run_records(req.scope, req.run_id)
        key, sheet = build_rating_key(records, purpose=req.purpose,
                                      include_stability=req.include_stability)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        return JSONResponse({"error": str(error)}, status_code=422)
    return {"sheet_id": key["sheet_id"], "counts": key["counts"], "key": key,
            "html": render_rating_sheet_html(sheet),
            "manifests": [item for record in records
                          for item in _record_manifests(record)],
            "runs": len(records)}


class PanelReq(BaseModel):
    scope: str = "studie"
    run_id: str = ""
    purpose: str = "studie"
    seed: str = ""
    raters: int = 10
    cases_per_rater: int = 12
    ratings_per_case: int = 3
    max_organizations_per_rater: int = 6
    include_stability: bool = False


@app.post("/api/comparison/panel")
def comparison_panel(req: PanelReq):
    """Bewertungspanel (10 Personen, 3 je Fall): Ziehung, Zuteilung, Bogen, Schluessel."""
    import rating_panel
    if not (1 <= req.ratings_per_case <= req.raters <= 30) or not (1 <= req.cases_per_rater <= 60):
        return JSONResponse({"error": "Ungültige Panelgröße."}, status_code=422)
    try:
        records = _load_run_records(req.scope, req.run_id)
        key, sheet = rating_panel.build_panel(
            records, seed=req.seed, purpose=req.purpose, raters=req.raters,
            cases_per_rater=req.cases_per_rater, ratings_per_case=req.ratings_per_case,
            max_organizations_per_rater=req.max_organizations_per_rater,
            include_stability=req.include_stability)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        return JSONResponse({"error": str(error)}, status_code=422)
    return {"panel_id": key["panel_id"], "key": key, "html": rating_panel.render_panel_html(sheet),
            "counts": {"cases": len(key["cases"]), "population": key["population"],
                       "raters": len(key["assignment"]),
                       "unsampled_recommended": len(key["unsampled_recommended_cases"]),
                       "verdict_words": len(key.get("verdict_words_in_text", [])),
                       "cases_per_rater_max": key["parameters"].get("cases_per_rater_max_used"),
                       "orgs_per_rater_max": key["parameters"].get("max_organizations_per_rater_used")},
            "runs": len(records)}


class PanelEvalReq(BaseModel):
    key: dict
    ratings: list


@app.post("/api/comparison/panel/evaluate")
def comparison_panel_evaluate(req: PanelEvalReq):
    """Fuehrt Panelbewertungen ohne Einigung zusammen (Mehrheitsregel) und rechnet Kennzahlen."""
    import rating_panel
    try:
        return rating_panel.evaluate_panel(req.key, req.ratings)
    except (ValueError, KeyError, TypeError) as error:
        return JSONResponse({"error": str(error)}, status_code=422)


class ReleaseReq(BaseModel):
    run_id: str
    pair_index: int = 0
    architecture: str
    candidate_id: str
    decision_sha256: str = ""
    action: str = ""
    confirm: bool = False
    email_to: str = ""
    subject: str = ""
    body: str = ""


RELEASE_LOG = os.path.join(Config.RUNTIME_ROOT, "release_log.jsonl")


def _release_context(req: ReleaseReq) -> tuple[dict, dict, dict, str]:
    record = _load_run_records("run", req.run_id)[0]
    if (record.get("run_set") or (record.get("operator_view") or {}).get("run_set")) == "studie":
        raise PermissionError("Studienläufe bleiben unverändert; Freigaben sind dort gesperrt.")
    pair, _arm, decision = release.find_decision(
        record, req.pair_index, req.architecture, req.candidate_id)
    fingerprint = release.decision_fingerprint(req.run_id, pair, req.architecture, decision)
    return record, pair, decision, fingerprint


@app.post("/api/comparison/release/preview")
def comparison_release_preview(req: ReleaseReq):
    """Bereitet CRM-Eintrag und E-Mail-Entwurf vor. Schreibt und sendet nichts."""
    try:
        record, _pair, decision, fingerprint = _release_context(req)
    except PermissionError as error:
        return JSONResponse({"error": str(error)}, status_code=403)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        return JSONResponse({"error": str(error)}, status_code=422)
    candidate = decision.get("candidate") or {}
    organization = ((record.get("operator_view") or {}).get("task") or {}).get(
        "organization_name", "")
    website = candidate.get("official_url") or candidate.get("website") or ""
    contact = release.find_contact_email(website, EvidenceResolver()._fetch)
    draft = release.email_draft(decision, organization, Config.ABSENDER,
                                Config.ABSENDER_ORG)
    outlook_ok, outlook_reason = outlook_mac.verfuegbar()
    return {"decision_sha256": fingerprint,
            "eligible": decision.get("decision_state") == "empfehlung",
            "decision_state": decision.get("decision_state"),
            "startup": candidate.get("name"), "website": website,
            "organization": organization,
            "crm_mode": "live" if LIVE_CRM else "dry-run",
            "contact": contact, "draft": draft,
            "outlook_available": outlook_ok, "outlook_reason": outlook_reason}


@app.post("/api/comparison/release")
def comparison_release(req: ReleaseReq):
    """Fuehrt eine einzelne, ausdruecklich bestaetigte Freigabe aus."""
    if req.action not in release.RELEASE_ACTIONS:
        return JSONResponse({"error": "Unbekannte Freigabeaktion."}, status_code=400)
    if not req.confirm:
        return JSONResponse({"error": "Freigabe nicht bestätigt."}, status_code=403)
    try:
        record, _pair, decision, fingerprint = _release_context(req)
    except PermissionError as error:
        return JSONResponse({"error": str(error)}, status_code=403)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        return JSONResponse({"error": str(error)}, status_code=422)
    if decision.get("decision_state") != "empfehlung":
        return JSONResponse({"error": "Nur eine Empfehlung kann freigegeben werden."},
                            status_code=403)
    if not secrets.compare_digest(req.decision_sha256 or "", fingerprint):
        return JSONResponse({"error": "Die Entscheidung hat sich seit der Anzeige "
                                      "geändert. Bitte neu laden und erneut prüfen.",
                             "decision_sha256": fingerprint}, status_code=409)
    organization = ((record.get("operator_view") or {}).get("task") or {}).get(
        "organization_name", "")
    to = req.email_to.strip()
    if req.action != "crm" and to and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", to):
        return JSONResponse({"error": "Empfängeradresse ist ungültig."}, status_code=400)
    if req.action == "crm":
        try:
            result = release.crm_transfer(_adapter, decision, organization,
                                          fingerprint, req.run_id)
        except Exception as error:
            result = {"status": "fehler", "grund": str(error)[:200]}
    elif req.action == "email_draft":
        # Kein Versand durch das System: Das Mailprogramm oeffnet den Entwurf,
        # die freigebende Person prueft ihn und sendet selbst.
        result = {"status": "entwurf", "mailto": release.mailto_link(
            to, req.subject, req.body)}
    else:
        try:
            result = outlook_mac.entwurf_erstellen(
                to=to, subject=req.subject, body=req.body, oeffnen=True)
        except outlook_mac.OutlookNichtVerfuegbar as error:
            result = {"status": "nicht_verfuegbar", "grund": str(error)}
        except Exception as error:
            result = {"status": "fehler", "grund": str(error)[:200]}
    release.audit(RELEASE_LOG, {
        "action": req.action, "run_id": req.run_id, "pair_index": req.pair_index,
        "architecture": req.architecture, "candidate_id": req.candidate_id,
        "decision_sha256": fingerprint, "email_to": to if req.action != "crm" else "",
        "result_status": (result or {}).get("status") or (result or {}).get("operation")
        or (result or {}).get("modus")})
    return {"action": req.action, "decision_sha256": fingerprint, "result": result}


@app.get("/api/comparison/crm")
def comparison_crm_status(limit: int = 10):
    """Lesender Pipedrive-Status fuer die Oberflaeche.

    Schreibt nie. Zeigt Modus, Konfiguration (ohne Geheimnisse) und die
    zuletzt angelegten Organisationen. Im Trockenlauf stammen diese aus dem
    Speicher dieses Serverprozesses, live aus einer lesenden GET-Abfrage.
    Studienlaeufe bleiben unabhaengig davon gesperrt (siehe _release_context).
    """
    limit = max(1, min(int(limit or 10), 25))
    token_configured = bool(Config.PIPEDRIVE_API_TOKEN)
    live_requested = os.environ.get("PIPEDRIVE_LIVE") == "1"
    host = urllib.parse.urlparse(_adapter.base).hostname or ""
    organizations, error = [], ""
    try:
        organizations = _adapter.list_organizations(limit=limit)
    except CRMAuthError as exc:
        error = f"Anmeldung bei Pipedrive fehlgeschlagen: {str(exc)[:160]}"
    except Exception as exc:  # Status darf die Oberflaeche nie blockieren.
        error = f"Pipedrive nicht erreichbar: {str(exc)[:160]}"
    if not LIVE_CRM:
        if not token_configured:
            hint = "Kein PIPEDRIVE_API_TOKEN in .env. Es wird nichts nach Pipedrive geschrieben."
        elif not live_requested:
            hint = ("Token vorhanden, Live-Modus aus. Start mit "
                    "scripts/start_live_review.py --pipedrive-live schaltet ihn bewusst ein.")
        else:
            hint = "Trockenlauf."
    else:
        hint = "Live: Freigaben aus Probe- und Demoläufen werden nach Pipedrive geschrieben."
    return {"mode": "live" if LIVE_CRM else "dry-run",
            "token_configured": token_configured,
            "live_requested": live_requested,
            "api_host": host,
            "pipeline": PIPELINE_NAME,
            "stage": Config.PIPEDRIVE_STAGE,
            "study_runs_locked": True,
            "auth_error": error or getattr(_adapter, "auth_error", ""),
            "organizations": organizations,
            "hint": hint}


class MergeReq(BaseModel):
    key: dict
    ratings: list
    adjudications: dict | None = None


@app.post("/api/comparison/ratings/merge")
def comparison_ratings_merge(req: MergeReq):
    """Gleicht zwei Bewertungen ab und erzeugt nach Einigung die finale Datei."""
    try:
        return merge_ratings(req.key, list(req.ratings), req.adjudications or {})
    except (ValueError, KeyError, TypeError) as error:
        return JSONResponse({"error": str(error)}, status_code=422)


@app.post("/api/comparison/unblind")
def comparison_unblind(req: UnblindReq, request: Request = None):
    """Entblindet erst nach kryptografischer Bindung finaler Annotationen."""
    if not _operator_authorized(request):
        return JSONResponse(
            {"error": "Operator-Authentifizierung erforderlich."},
            status_code=401)
    if not req.confirm_annotations_locked:
        return JSONResponse(
            {"error": "Die finalen Annotationen wurden nicht bestaetigt."},
            status_code=403)
    commitment = str(req.annotation_commitment_sha256 or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", commitment):
        return JSONResponse(
            {"error": "annotation_commitment_sha256 muss ein SHA-256-Wert sein."},
            status_code=400)
    record = UNBLINDING_RECORDS.get(str(req.run_id or "").strip())
    if not record:
        return JSONResponse(
            {"error": "Run-ID ist nicht vorhanden oder nicht mehr im "
                      "serverseitigen Entblindungsspeicher."}, status_code=404)
    existing = record.get("annotation_commitment_sha256") or ""
    if existing and existing != commitment:
        return JSONResponse(
            {"error": "Dieser Lauf wurde bereits an einen anderen "
                      "Annotationsstand gebunden."}, status_code=409)
    if not existing:
        record["annotation_commitment_sha256"] = commitment
        record["unblinded_at"] = datetime.now(timezone.utc).isoformat()
        _save_unblinding_records()
    return {
        "status": "unblinded",
        "run_id": req.run_id,
        "annotation_commitment_sha256": commitment,
        "unblinded_at": record["unblinded_at"],
        "pairs": record["internal_pairs"],
        "unblinding_manifest": record["assignment_manifests"],
        "run_bundle_manifest": record["run_bundle_manifest"],
    }


@app.get("/api/seed")
def seed():
    return [{"name": c.name, "description": c.description,
             "founded": c.founded, "region": c.region} for c in SEED.values()]


@app.post("/api/discover")
def discover(req: ScoutReq):
    cands, tr = PIPE.discover(req.description or "", n=8, seed_pool=list(SEED.values()))
    return {"trace": tr, "candidates": [c.name for c in cands]}


def _steckbrief_payload(dec, fields: dict = None) -> dict:
    """Baut die Steckbrief-Zeilen aus Discovery-Daten (fields=None) oder aus
    einer Tiefen-Recherche (fields gesetzt). Inkl. Pipedrive-Dubletten-Check."""
    c = dec.candidate
    best = dec.matches[0] if dec.matches else None
    try:
        found = PIPE.adapter.find_organization(c.name)
    except Exception:
        found = None
    pd_text = ("Bereits in Pipedrive (Org #{})".format(found["id"]) if found
               else "Nicht in Pipedrive gefunden.")
    sb = dict(c.steckbrief or {})
    f = fields or {}
    def pick(key, alt=""):
        return str(f.get(key) or sb.get(key) or alt or
                   "nicht oeffentlich ersichtlich")
    titel = {"Pilot": "Top-Treffer / Pilotgespraech priorisieren",
             "beobachten": "Beobachten / strategische Notiz",
             "abgelehnt": "Kein ausreichender Match"}[dec.recommendation.value]

    # Eignung: Recherchebegruendung + deterministische
    # Pipeline-Begruendung — auch und gerade im Negativfall.
    llm_eignung = str(f.get("eignung") or sb.get("eignung") or "").strip()
    rec = dec.recommendation.value
    if rec == "Pilot" and best:
        pipe_grund = ("{}; Skepsis: {}; Score {} >= 61".format(
            best.rationale, best.critical_assessment, best.score))
        eignung = ("GEEIGNET. " + (llm_eignung + " " if llm_eignung else "")
                   + "[Pipeline: " + pipe_grund + "]")
    elif rec == "beobachten":
        grund = dec.abstain_reason or (best.critical_assessment if best else "")
        eignung = ("NUR BEOBACHTEN. Grund: " + grund + "."
                   + (" Einordnung der Recherche: " + llm_eignung if llm_eignung else ""))
    else:
        grund = dec.abstain_reason or (best.critical_assessment if best else
                                       "kein thematischer Bezug")
        eignung = ("NICHT AUSREICHEND. Grund: " + grund + "."
                   + (" Einordnung der Recherche: " + llm_eignung if llm_eignung else ""))

    rows = [
        ("Teamgroesse", pick("teamgroesse",
                             "{} (Discovery)".format(c.employees) if c.employees else "")),
        ("Standort", pick("standort", c.region)),
        ("Gruendungsjahr", str(f.get("gruendungsjahr") or
                               sb.get("gruendung_detail") or
                               c.founded or "unbekannt")),
        ("Loesung", str(f.get("loesung") or sb.get("loesung_detail") or
                        c.description)),
        ("USP", pick("usp", best.rationale if best else "")),
        ("Markterfolge / Kunden", pick("kunden") if not f else
            str(f.get("markterfolge") or pick("kunden"))),
        ("Eignung für den Anwendungsfall", eignung),
        ("Pipedrive", pd_text),
        ("Anwendungsbereich", (c.sectors or ["—"])[0]),
        ("Finanzierungsphase", str(f.get("finanzierungsphase") or
                                   sb.get("finanzierung_detail") or
                                   c.funding_stage or "unbekannt")),
        ("Standort-Klasse", c.location_class or c.region or "—"),
        ("Bester Akteur", "{} (Score {})".format(best.actor_name, best.score)
                          if best else "—"),
        ("Weitere thematische Bezüge", ", ".join(
            "{} ({})".format(g["akteur"], g["typ"]) for g in dec.general_fit) or
            "kein weiterer Bezug erkennbar"),
    ]
    return {"name": c.name, "titel": titel,
            "empfehlung": dec.recommendation.value, "zeilen": rows,
            "pipedrive_gefunden": bool(found)}


@app.post("/api/run")
def run(req: RunReq):
    """Kombinierter Lauf: Discovery (Prompt oder Themengebiet) + Bewertung aller
    Kandidaten. Bei theme_id gehen ausschliesslich oeffentlich ableitbare
    Angaben in die Suchanfrage ein, naemlich Themengebiet, Beschreibung und die
    aus oeffentlichen Unternehmensdarstellungen gewonnenen Suchanlaesse des
    Akteurs. Interne Ist- oder Soll-Angaben werden nicht verarbeitet."""
    query = (req.query or "").strip()
    # Eine globale, nicht personenbezogene Lauf-ID entsteht vor Discovery und
    # wird durch Kandidat, Auditlog und spaeter den Pipedrive-Vorgang getragen.
    # So bleibt auch ein abgebrochener oder trefferloser Lauf nachvollziehbar.
    run_uid = "run-{}-{}".format(
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        uuid.uuid4().hex[:10])
    themes_data = _load_themes()["themen"]
    theme = None
    if req.theme_id:
        theme = next((t for t in themes_data
                      if t["id"] == req.theme_id), None)
    target_actor_id = (req.actor_id or (theme.get("actor_id") if theme else "") or "").strip()
    if theme:
        parts = [theme["themengebiet"], theme.get("beschreibung", "")]
        try:
            actor = PIPE.kb.get(theme["actor_id"]) if theme.get("actor_id") else None
            if actor:
                parts.append(" ".join(actor.get("scouting_triggers", [])[:8]))
        except Exception:
            pass
        query = (query + " " + " ".join(p for p in parts if p)).strip()
    if not query and not (req.push_mode and target_actor_id):
        return JSONResponse({"error": "Prompt eingeben oder Themengebiet waehlen"},
                            status_code=400)
    cands, tr = PIPE.discover(query, n=req.n, seed_pool=list(SEED.values()),
                              waves=req.waves, target_actor_id=target_actor_id,
                              push_mode=req.push_mode, themes=themes_data)
    effective_query = tr.get("query") or query
    decisions = []
    for c in cands:
        c.run_id = run_uid
        dec = PIPE.scout(c, use_guardrail=req.use_guardrail,
                         use_memory=req.use_memory,
                         target_actor_id=target_actor_id)
        DECISIONS[c.name] = dec
        d = dec.to_dict()
        d["steckbrief"] = _steckbrief_payload(dec)   # sofort mitliefern
        decisions.append(d)
    # Protokoll: Lauf und verworfene Kandidaten dauerhaft festhalten, damit
    # spaeter nachvollziehbar bleibt, was mit welcher Konfiguration geprueft
    # und was aus welchem Grund abgelehnt wurde.
    try:
        empfohlen = sum(1 for d in decisions if d.get("recommendation") == "Pilot")
        kosten = (tr.get("output") or {}).get("kosten_usd_ca")
        lauf_id = store.lauf_speichern({
            "lauf_uid": run_uid,
            "suchauftrag": effective_query[:500],
            "akteur": (PIPE.kb.get(target_actor_id)["name"] if target_actor_id else ""),
            "suchfeld": theme["themengebiet"] if theme else "",
            "wellen": req.waves, "guardrail": 1 if req.use_guardrail else 0,
            "gefunden": len(decisions), "empfohlen": empfohlen,
            "verworfen": len(decisions) - empfohlen,
            "kosten_usd": kosten,
            "modus": "live" if PIPE.llm.available() else "trockenlauf"})
        for d in decisions:
            if d.get("recommendation") == "Pilot":
                continue
            m = (d.get("matches") or [{}])[0]
            store.verworfen_speichern({
                "lauf_id": lauf_id,
                "name": d["candidate"]["name"],
                "akteur": m.get("actor_name", ""),
                "score": d.get("best_score"),
                "schwelle": Config.SCHWELLE if hasattr(Config, "SCHWELLE") else 61,
                "grund": d.get("recommendation", "abgelehnt"),
                "skepsis": m.get("critical_assessment", ""),
                "beschreibung": d["candidate"].get("description", "")[:400]})
    except Exception:
        pass  # Protokoll darf den Lauf nie blockieren
    return {"run_id": run_uid, "discovery": tr, "query": effective_query,
            "theme": {"id": theme["id"], "themengebiet": theme["themengebiet"],
                      "unternehmen": theme["unternehmen"]} if theme else None,
            "target_actor_id": target_actor_id,
            "opportunity_plan": PIPE.last_opportunity_plan,
            "decisions": decisions}


# --- Themengebiete (aus der Excel; erweiterbar ueber das Dashboard) ----------
@app.get("/api/themes")
def themes():
    return _load_themes()


@app.post("/api/themes/add")
def themes_add(req: ThemeAddReq):
    if not req.unternehmen.strip() or not req.themengebiet.strip():
        return JSONResponse({"error": "Unternehmen und Themengebiet sind Pflicht"},
                            status_code=400)
    data = _load_themes()
    # Duplikat-Schutz (gleiches Unternehmen + Themengebiet)
    for t in data["themen"]:
        if t["unternehmen"].strip().lower() == req.unternehmen.strip().lower() and \
           t["themengebiet"].strip().lower() == req.themengebiet.strip().lower():
            return JSONResponse({"error": "Dieses Themengebiet existiert bereits"},
                                status_code=409)
    # actor_id aus der Wissensbasis aufloesen (per Namens-Aehnlichkeit)
    aid = ""
    low = req.unternehmen.strip().lower()
    for a in PIPE.kb.actors:
        if a["name"].strip().lower() in low or low in a["name"].strip().lower() \
           or a["id"].replace("_", " ") in low.replace("-", " "):
            aid = a["id"]
            break
    nid = f"p{len(data['themen']) + 1:03d}"
    # Datenrestriktion: ueber das Dashboard ergaenzte Themen gelten als
    # oeffentlich. Felder fuer interne Bewertungen (ist/soll/prio) entfallen
    # bewusst, damit keine vertraulichen Inhalte erfasst werden koennen.
    theme = {"id": nid, "typ": "oeffentlich", "unternehmen": req.unternehmen.strip(),
             "actor_id": aid, "themengebiet": req.themengebiet.strip(),
             "beschreibung": req.beschreibung.strip(),
             "quelle": "ueber Dashboard ergaenzt"}
    data["themen"].append(theme)
    data.setdefault("meta", {})["anzahl"] = len(data["themen"])
    _save_themes(data)
    return {"status": "hinzugefuegt", "theme": theme}


class SteckbriefReq(BaseModel):
    name: str


@app.post("/api/steckbrief")
def steckbrief(req: SteckbriefReq):
    """Tiefen-Nachrecherche on-demand (Kostenkontrolle: nur per Klick). Live:
    zusaetzliche Websuche zu Team/Standort/USP/Kunden; sonst Discovery-Daten."""
    dec = DECISIONS.get(req.name)
    if not dec:
        return JSONResponse({"error": "Kandidat zuerst scouten"}, status_code=400)
    c = dec.candidate
    fields, cost = {}, {}
    if PIPE.llm.available():
        raw = PIPE.llm.complete(
            model=Config.MODEL_DISCOVERY,
            system=("Recherchiere das Unternehmen per Websuche und antworte NUR "
                    "mit einem JSON-Objekt (keine Zaeune, kein Text) mit den "
                    "Feldern: teamgroesse, standort, gruendungsjahr, loesung, "
                    "usp, markterfolge, finanzierungsphase. Ehrlich bleiben: "
                    "Unbekanntes als 'nicht oeffentlich ersichtlich' markieren; "
                    "keine Zahlen erfinden."),
            user=f"Unternehmen: {c.name}. Kontext: {c.description[:300]}",
            tools=[{"type": "web_search"}],
            max_tool_calls=3,
            max_tokens=1200,
            purpose="non_decision_steckbrief")
        cost = PIPE.llm.cost_estimate()
        try:
            txt = raw[raw.find("{"):raw.rfind("}") + 1]
            fields = json.loads(txt) if txt else {}
        except Exception:
            fields = {}
    payload = _steckbrief_payload(dec, fields)
    payload["kosten"] = cost
    payload["quellen"] = list(PIPE.llm.last_citations or [])
    payload["hinweis_evidenz"] = (
        "Die Nachrecherche veraendert weder Evidenzmatrix noch Entscheidung. "
        "Entscheidungsrelevante Claims muessen den Verifikationspfad durchlaufen."
    )
    return payload


@app.get("/api/themes/skill-markdown")
def themes_markdown():
    """Rendert die oeffentlichen Suchfelder als Markdown. Enthaelt bewusst
    keine internen Bewertungen, damit der Export die Datenrestriktion wahrt."""
    data = _load_themes()
    by_company = {}
    for t in data["themen"]:
        by_company.setdefault(t["unternehmen"], []).append(t)
    lines = ["# Oeffentliche Suchfelder je Akteur",
             f"\nStand: {data.get('meta', {}).get('stand', '')} — "
             f"{len(data['themen'])} Suchfelder. Grundlage: oeffentlich "
             "zugaengliche Unternehmensdarstellungen.\n"]
    for comp in sorted(by_company):
        lines.append(f"\n## {comp}")
        for t in sorted(by_company[comp], key=lambda x: x["themengebiet"]):
            lines.append(f"- **{t['themengebiet']}**"
                         + (f": {t['beschreibung']}" if t.get("beschreibung") else ""))
    md = "\n".join(lines) + "\n"
    return {"markdown": md, "dateiname": "suchfelder_oeffentlich.md"}


@app.post("/api/scout")
def scout(req: ScoutReq):
    if req.name and req.name in SEED:
        c = SEED[req.name]
    else:
        c = Candidate(name=req.name or "Freier Kandidat",
                      description=req.description or "")
    dec = PIPE.scout(c, use_guardrail=req.use_guardrail, use_memory=req.use_memory)
    DECISIONS[c.name] = dec
    return dec.to_dict()


@app.post("/api/qualify")
def qualify(req: QualifyReq):
    dec = DECISIONS.get(req.name)
    if not dec:
        return JSONResponse({"error": "Kandidat zuerst scouten"}, status_code=400)
    crm = PIPE.qualify(dec, autonomy=Autonomy(req.autonomy),
                       human_approved=req.approved)
    return crm


@app.post("/api/outreach")
def outreach(req: QualifyReq):
    dec = DECISIONS.get(req.name)
    if not dec:
        return JSONResponse({"error": "Kandidat zuerst scouten"}, status_code=400)
    if not req.approved:
        return JSONResponse(
            {"error": "Serverseitige Freigabe fehlt; kein CRM-Schreibvorgang"},
            status_code=403)
    try:
        crm = PIPE.qualify(dec, autonomy=Autonomy(req.autonomy),
                           human_approved=req.approved)
    except CRMAuthError as e:
        return JSONResponse(
            {"error": str(e),
             "hinweis": "In der .env muessen PIPEDRIVE_API_BASE und "
                        "PIPEDRIVE_API_TOKEN aus demselben Konto stammen. "
                        "Pruefung: python3 pipedrive_selfcheck.py"},
            status_code=502)
    except Exception as e:
        return JSONResponse({"error": f"CRM-Eintrag fehlgeschlagen: {e}"},
                            status_code=502)
    draft = PIPE.draft_outreach(dec, crm)
    # Freigegebene Treffer dauerhaft ablegen, damit sie einen Neustart
    # ueberleben und im Verlauf nachvollziehbar bleiben.
    eintrag = None
    try:
        c = dec.candidate
        best = dec.matches[0] if dec.matches else None
        eintrag = store.speichern({
            "name": c.name,
            "akteur_id": best.actor_id if best else "",
            "akteur": best.actor_name if best else "",
            "score": dec.best_score,
            "fit": best.fit if best else "",
            "beschreibung": c.description,
            "sektor": (c.sectors or [""])[0],
            "phase": c.funding_stage,
            "region": c.location_class or c.region,
            "gruendungsjahr": c.founded,
            "begruendung": best.rationale if best else "",
            "skepsis": best.critical_assessment if best else "",
            "quellen": [{"titel": getattr(s, "title", ""),
                         "url": getattr(s, "url", "")} for s in (c.sources or [])],
            "crm_status": crm.get("status", ""),
            "crm_org_id": str(crm.get("org_id", "")),
            "kontakt_email": draft.get("to", "") if isinstance(draft, dict) else "",
            "freigegeben_von": Config.PIPEDRIVE_OWNER or "Dashboard",
        })
    except Exception as e:
        eintrag = {"fehler": f"Ablage fehlgeschlagen: {e}"}

    # Uebergabe an Outlook direkt im Anschluss an die Freigabe. Sie ist bewusst
    # der letzte Schritt und darf nichts blockieren: Schlaegt sie fehl, etwa
    # weil das System kein macOS ist oder die Automatisierungsrechte fehlen,
    # bleiben CRM-Eintrag und Ablage trotzdem bestehen und der Entwurf laesst
    # sich weiterhin von Hand uebergeben.
    outlook = None
    if req.outlook and isinstance(draft, dict) and draft.get("body"):
        try:
            outlook = outlook_mac.entwurf_erstellen(
                to=draft.get("to", ""), subject=draft.get("subject", ""),
                body=draft.get("body", ""), bcc=draft.get("bcc", ""),
                oeffnen=bool(req.outlook_oeffnen))
        except outlook_mac.OutlookNichtVerfuegbar as e:
            outlook = {"status": "nicht_verfuegbar", "grund": str(e)}
        except Exception as e:
            outlook = {"status": "fehler", "grund": str(e)}
        if isinstance(eintrag, dict) and eintrag.get("id") and outlook:
            try:
                store.aktualisieren(eintrag["id"], {"outreach_status":
                    "entwurf_in_outlook"
                    if outlook.get("status") == "entwurf_in_outlook" else "offen"})
            except Exception:
                pass

    return {"crm": crm, "draft": draft, "ablage": eintrag, "outlook": outlook}


class OutlookReq(BaseModel):
    name: str
    to: str = ""
    subject: str = ""
    body: str = ""
    bcc: str = ""
    oeffnen: bool = False


@app.post("/api/outreach/outlook")
def outreach_outlook(req: OutlookReq):
    """Uebergibt den Entwurf an Outlook. Es wird NICHT gesendet, sondern nur
    ein Entwurf angelegt. Der Versand bleibt eine bewusste Handlung."""
    try:
        res = outlook_mac.entwurf_erstellen(
            to=req.to, subject=req.subject, body=req.body, bcc=req.bcc,
            oeffnen=req.oeffnen)
    except outlook_mac.OutlookNichtVerfuegbar as e:
        return JSONResponse({"error": str(e)}, status_code=503)
    except Exception as e:
        return JSONResponse({"error": f"Uebergabe fehlgeschlagen: {e}"},
                            status_code=500)
    return res


@app.get("/api/outlook/status")
def outlook_status():
    ok, grund = outlook_mac.verfuegbar()
    return {"verfuegbar": ok, "grund": grund}


class AblageUpdate(BaseModel):
    status: str | None = None
    notiz: str | None = None
    outreach_status: str | None = None
    kontakt_email: str | None = None


@app.get("/api/vorqualifiziert")
def vq_liste(status: str = "", akteur_id: str = "", suche: str = ""):
    return {"eintraege": store.liste(status=status, akteur_id=akteur_id,
                                     suche=suche),
            "kennzahlen": store.kennzahlen()}


@app.patch("/api/vorqualifiziert/{eintrag_id}")
def vq_aendern(eintrag_id: int, req: AblageUpdate):
    felder = {k: v for k, v in req.model_dump().items() if v is not None}
    try:
        return store.aktualisieren(eintrag_id, felder)
    except (ValueError, KeyError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.delete("/api/vorqualifiziert/{eintrag_id}")
def vq_loeschen(eintrag_id: int):
    store.loeschen(eintrag_id)
    return {"status": "geloescht", "id": eintrag_id}


@app.get("/api/protokoll")
def protokoll(suche: str = ""):
    return {"laeufe": store.laeufe(limit=50),
            "verworfen": store.verworfene(suche=suche),
            "kennzahlen": store.protokoll_kennzahlen()}


@app.get("/api/board")
def board():
    try:
        return PIPE.adapter.board()
    except Exception as e:
        return JSONResponse({"_fehler": f"CRM nicht abrufbar: {e}"},
                            status_code=200)


# --- Pipedrive: Status, Live-Organisationen, Echtzeit-Stream -----------------
@app.get("/api/pipedrive/status")
def pipedrive_status():
    return {"modus": "live" if not PIPE.adapter.dry_run else "dry-run",
            "pipeline": PIPELINE_NAME, "stage": Config.PIPEDRIVE_STAGE,
            "poll_sekunden": Config.PIPEDRIVE_POLL_SECONDS}


@app.get("/api/status")
def status():
    """Beide Modi getrennt: KI-Suche (Discovery) und CRM (Pipedrive)."""
    crm_fehler = getattr(PIPE.adapter, "auth_error", "")
    return {"version": Config.VERSION,
            "crm_fehler": crm_fehler,
            "discovery": "live" if PIPE.llm.available() else "dry-run",
            "crm": "live" if not PIPE.adapter.dry_run else "dry-run",
            "hinweis_discovery": "" if PIPE.llm.available() else
                "OPENAI_API_KEY in .env setzen fuer echte KI-Suche",
            "hinweis_crm": "" if not PIPE.adapter.dry_run else
                "PIPEDRIVE_API_TOKEN + PIPEDRIVE_LIVE=1 in .env setzen",
            "ablage": store.zustand()}


@app.get("/healthz")
def healthz():
    """Lebenszeichen fuer die Container-Plattform. Azure Container Apps ruft
    diesen Pfad auf, um zu entscheiden, ob eine Instanz Verkehr bekommt.
    Der Aufruf prueft die Datenbank mit, denn eine Anwendung ohne erreichbare
    Ablage ist nicht betriebsbereit."""
    try:
        store.init()
        return {"status": "ok", "version": Config.VERSION}
    except Exception:
        error_id = f"health-{uuid.uuid4().hex[:12]}"
        _log.exception("%s: Healthcheck fehlgeschlagen", error_id)
        return JSONResponse(
            {"status": "error", "error_id": error_id}, status_code=503)


@app.get("/api/orgs")
def orgs(limit: int = 25):
    """Organisationen zuruecklesen (live aus Pipedrive oder Dry-Run-Speicher)."""
    try:
        return {"organisationen": PIPE.adapter.list_organizations(limit=limit)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/orgs/stream")
async def orgs_stream(request: Request):
    """
    Server-Sent-Events-Strom: pollt die Organisationen alle N Sekunden und pusht
    den Stand ans Dashboard. So 'erkennt' das Board in Echtzeit, sobald eine neue
    Organisation in Pipedrive auftaucht. (Produktiv-Alternative: Pipedrive-Webhook
    -> sofortiger Push; siehe /api/pipedrive/webhook und README.)
    """
    async def event_gen():
        from crm_pipedrive import CRMRateLimitError
        seen = set()
        first = True
        takt = Config.PIPEDRIVE_POLL_SECONDS
        fehler = 0
        verbraucht = 0
        while True:
            if await request.is_disconnected():
                break
            if verbraucht >= Config.PIPEDRIVE_STREAM_PUNKTE:
                # Selbstbegrenzung. Der Abgleich ist Bequemlichkeit, das
                # Tagesbudget wird fuer das Anlegen von Datensaetzen gebraucht.
                yield ("event: error\ndata: " + json.dumps(
                    {"error": "Der CRM-Abgleich wurde nach rund "
                              f"{verbraucht} Punkten ausgesetzt, damit das "
                              "Tagesbudget für Einträge frei bleibt. "
                              "Seite neu laden startet ihn wieder.",
                     "endgueltig": True}) + "\n\n")
                break
            try:
                orgs_now = await asyncio.to_thread(PIPE.adapter.list_organizations, 25)
                fehler = 0
                takt = Config.PIPEDRIVE_POLL_SECONDS
                verbraucht += 20   # Punktkosten einer Listenabfrage
            except CRMRateLimitError as e:
                # Beim aufgebrauchten Tagesbudget hat weiteres Fragen keinen
                # Zweck. Der Strom endet und sagt, warum.
                yield ("event: error\ndata: " +
                       json.dumps({"error": str(e), "endgueltig": e.tagesbudget}) +
                       "\n\n")
                if e.tagesbudget:
                    break
                takt = min(takt * 2, 300)
                await asyncio.sleep(takt)
                continue
            except Exception as e:
                # Nach fuenf erfolglosen Anlaeufen wird aufgegeben, statt das
                # Kontingent mit einer aussichtslosen Schleife zu verbrauchen.
                fehler += 1
                yield ("event: error\ndata: " +
                       json.dumps({"error": str(e), "endgueltig": fehler >= 5}) + "\n\n")
                if fehler >= 5:
                    break
                takt = min(takt * 2, 300)
                await asyncio.sleep(takt)
                continue
            ids = {o["id"] for o in orgs_now}
            new_ids = [] if first else [i for i in ids if i not in seen]
            seen = ids
            first = False
            payload = {"organisationen": orgs_now, "neu": new_ids,
                       "kontingent": getattr(PIPE.adapter, "kontingent", {}),
                       "verbrauch": getattr(PIPE.adapter, "verbrauch", {}),
                       "strom_punkte": verbraucht}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            await asyncio.sleep(takt)
    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.post("/api/pipedrive/webhook")
async def pipedrive_webhook(request: Request):
    """
    Optionaler Webhook-Empfaenger fuer den Produktivbetrieb: Pipedrive ruft diese
    URL bei 'added.organization' auf -> echter Sub-Sekunden-Push (statt Polling).
    Fuer eine lokale Demo nicht noetig (localhost ist von aussen nicht erreichbar;
    es braeuchte einen Tunnel wie ngrok). Hier nur quittiert.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    return {"status": "empfangen", "event": body.get("event", "")}


@app.get("/api/evaluate")
def evaluate(guardrail: bool = True):
    return run_eval(PIPE, use_guardrail=guardrail)


@app.get("/api/ablation")
def ablation():
    return run_ablation(PIPE)


@app.post("/api/feedback")
def feedback(req: FeedbackReq):
    PIPE.memory.record(req.actor_id, req.description, req.label, req.score, req.outcome)
    return PIPE.memory.stats()


@app.get("/api/memory")
def memory():
    return PIPE.memory.stats()


@app.post("/api/memory/clear")
def memory_clear():
    PIPE.memory.store.clear()
    return {"status": "geleert"}
