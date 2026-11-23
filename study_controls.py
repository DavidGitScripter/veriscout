"""Vorabkontrollen fuer bezahlte, gepaarte SAS--MAS-Studien.

Das Modul trennt drei Dinge, die im Entwicklungsbetrieb leicht vermischt
werden: einen vor API-Aufrufen eingefrorenen Ausfuehrungsplan, eine technische
Holdout-Sperre und ein persistentes lokales Kostenlimit. Es kennt keine
fachlichen Resultate und kann deshalb weder eine guenstige Reihenfolge noch
eine nachtraegliche Stichprobe auswaehlen.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass

try:
    import fcntl
except ImportError:  # pragma: no cover - Forschungsserver ist Unix-basiert.
    fcntl = None


RANDOMIZATION_ALGORITHM_VERSION = "balanced-abba-v1"
STUDY_MANIFEST_SCHEMA_VERSION = "venture-scout-study-v1"


def _canonical_hash(value: object, prefix: str = "sha256") -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return f"{prefix}-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _atomic_json_write(path: str, value: dict) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".study-", suffix=".json", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2,
                      sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _process_file_lock(path: str):
    """Serialisiert Ledger-Aenderungen auch ueber Serverprozesse hinweg."""
    lock_path = os.path.abspath(path) + ".lock"
    os.makedirs(os.path.dirname(lock_path), mode=0o700, exist_ok=True)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


@dataclass(frozen=True)
class PlannedPair:
    study_id: str
    task_id: str
    task_input_hash: str
    replicate_index: int
    memory_enabled: bool
    block_index: int
    allocation_seed: str
    randomization_algorithm_version: str
    order: tuple[str, str]

    @property
    def execution_id(self) -> str:
        digest = _canonical_hash(asdict(self), "execution").split("-", 1)[1]
        return "exec-" + digest[:24]

    def to_dict(self) -> dict:
        value = asdict(self)
        value["order"] = list(self.order)
        value["execution_id"] = self.execution_id
        return value


def build_balanced_plan(*, study_id: str, task_rows: list[dict],
                        repetitions: int, memory_states: list[bool],
                        allocation_seed: str) -> dict:
    """Erzeugt eine deterministische AB/BA-Planung ohne Ergebniszugriff.

    Innerhalb jeder Aufgabe wechseln SAS--MAS und MAS--SAS. Der Startarm wird
    stabil aus Seed und Task-ID abgeleitet. Memory-Zustaende werden pro
    Replikation alternierend verschachtelt, damit Zeitdrift nicht vollstaendig
    mit Memory konfundiert ist.
    """
    study_id = str(study_id or "").strip()
    allocation_seed = str(allocation_seed or "").strip()
    if not study_id or not allocation_seed:
        raise ValueError("study_id und allocation_seed sind erforderlich.")
    if int(repetitions) <= 0:
        raise ValueError("repetitions muss positiv sein.")
    if not task_rows:
        raise ValueError("Mindestens eine Aufgabe ist erforderlich.")
    states = list(dict.fromkeys(bool(item) for item in memory_states))
    if not states:
        raise ValueError("Mindestens ein Memory-Zustand ist erforderlich.")

    planned: list[PlannedPair] = []
    block_index = 0
    for task in sorted(task_rows, key=lambda item: str(item.get("task_id") or "")):
        task_id = str(task.get("task_id") or "").strip()
        task_hash = str(task.get("task_input_hash") or "").strip()
        if not task_id or not task_hash:
            raise ValueError("Jede Aufgabe braucht task_id und task_input_hash.")
        for replicate_index in range(1, int(repetitions) + 1):
            ordered_states = list(states)
            if len(ordered_states) > 1 and replicate_index % 2 == 0:
                ordered_states.reverse()
            for state_index, memory_enabled in enumerate(ordered_states):
                # Ein einziger vorab bestimmter Startwert plus der globale
                # Blockindex erzeugt ueber alle Aufgaben hinweg exakt gleich
                # viele AB- und BA-Zuweisungen (bei ungerader Gesamtzahl mit
                # der unvermeidbaren Differenz eins).
                start_mas = int(hashlib.sha256(
                    f"{allocation_seed}|global-order".encode("utf-8")
                ).hexdigest(), 16) % 2
                parity = (block_index + start_mas) % 2
                order = ("mas", "sas2") if parity else ("sas2", "mas")
                planned.append(PlannedPair(
                    study_id=study_id,
                    task_id=task_id,
                    task_input_hash=task_hash,
                    replicate_index=replicate_index,
                    memory_enabled=memory_enabled,
                    block_index=block_index,
                    allocation_seed=allocation_seed,
                    randomization_algorithm_version=(
                        RANDOMIZATION_ALGORITHM_VERSION),
                    order=order,
                ))
                block_index += 1
    manifest = {
        "schema_version": STUDY_MANIFEST_SCHEMA_VERSION,
        "study_id": study_id,
        "allocation_seed": allocation_seed,
        "randomization_algorithm_version": RANDOMIZATION_ALGORITHM_VERSION,
        "created_at_utc": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
        "plan": [item.to_dict() for item in planned],
    }
    manifest["manifest_hash"] = _canonical_hash({
        key: value for key, value in manifest.items()
        if key not in {"created_at_utc", "manifest_hash"}
    }, "study")
    return manifest


def save_frozen_plan(path: str, manifest: dict) -> None:
    """Schreibt einen Plan genau einmal; abweichende Inhalte werden blockiert."""
    with _process_file_lock(path):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                existing = json.load(handle)
            # Zeitstempel duerfen bei zwei zeitgleichen, aber inhaltlich
            # identischen Erzeugungsversuchen abweichen. Fuehrend ist der Hash
            # des gesamten vorab festgelegten Plans.
            if (existing.get("manifest_hash") != manifest.get("manifest_hash")
                    or {key: value for key, value in existing.items()
                        if key != "created_at_utc"}
                    != {key: value for key, value in manifest.items()
                        if key != "created_at_utc"}):
                raise RuntimeError(
                    "Der Studienplan ist bereits eingefroren und darf nicht "
                    "ueberschrieben werden.")
            return
        _atomic_json_write(path, manifest)


class HoldoutRegistry:
    """Prueft Holdout-Auftraege gegen ein extern eingefrorenes Manifest."""

    def __init__(self, manifest_path: str, execution_path: str):
        self.manifest_path = str(manifest_path or "")
        self.execution_path = str(execution_path or "")
        self._lock = threading.Lock()

    def _manifest(self) -> dict:
        if not self.manifest_path or not os.path.exists(self.manifest_path):
            raise RuntimeError(
                "Holdout ist gesperrt: eingefrorenes Studienmanifest fehlt.")
        with open(self.manifest_path, encoding="utf-8") as handle:
            value = json.load(handle)
        if (not isinstance(value, dict)
                or value.get("schema_version") != STUDY_MANIFEST_SCHEMA_VERSION):
            raise RuntimeError("Holdout-Studienmanifest ist ungueltig.")
        expected_hash = _canonical_hash({
            key: item for key, item in value.items()
            if key not in {"created_at_utc", "manifest_hash"}
        }, "study")
        if str(value.get("manifest_hash") or "") != expected_hash:
            raise RuntimeError("Holdout-Studienmanifest wurde veraendert.")
        identifiers = []
        for raw in value.get("plan") or []:
            try:
                planned = PlannedPair(
                    study_id=str(raw["study_id"]),
                    task_id=str(raw["task_id"]),
                    task_input_hash=str(raw["task_input_hash"]),
                    replicate_index=int(raw["replicate_index"]),
                    memory_enabled=bool(raw["memory_enabled"]),
                    block_index=int(raw["block_index"]),
                    allocation_seed=str(raw["allocation_seed"]),
                    randomization_algorithm_version=str(
                        raw["randomization_algorithm_version"]),
                    order=tuple(raw["order"]),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeError(
                    "Holdout-Plan enthaelt ungueltige Zuweisungen.") from error
            if (planned.study_id != str(value.get("study_id") or "")
                    or planned.randomization_algorithm_version
                    != RANDOMIZATION_ALGORITHM_VERSION
                    or str(raw.get("execution_id") or "")
                    != planned.execution_id):
                raise RuntimeError("Holdout-Zuweisung ist nicht authentisch.")
            identifiers.append(planned.execution_id)
        if len(identifiers) != len(set(identifiers)):
            raise RuntimeError("Holdout-Plan enthaelt doppelte Execution-IDs.")
        return value

    def assignments(self, *, study_id: str, task_input_hash: str,
                    repetitions: int, memory_states: list[bool],
                    event_time: str) -> list[dict]:
        if not str(event_time or "").strip():
            raise ValueError("Holdout-Auftraege brauchen einen fixierten event_time.")
        manifest = self._manifest()
        if str(manifest.get("study_id") or "") != str(study_id or ""):
            raise ValueError("study_id stimmt nicht mit dem Holdout-Manifest ueberein.")
        requested_states = set(bool(item) for item in memory_states)
        task_assignments = [dict(item) for item in manifest.get("plan") or []
                            if str(item.get("task_input_hash") or "")
                            == task_input_hash]
        matches = [item for item in task_assignments
                   if bool(item.get("memory_enabled")) in requested_states
                   and int(item.get("replicate_index") or 0) <= int(repetitions)]
        expected = int(repetitions) * len(requested_states)
        if len(matches) != expected or len(task_assignments) != expected:
            raise ValueError(
                "Holdout-Auftraege muessen den fuer diese Aufgabe vollstaendig "
                "eingefrorenen Replikations- und Memory-Plan ausfuehren; eine "
                "selektive Teilmenge ist nicht zulaessig.")
        return sorted(matches, key=lambda item: int(item["block_index"]))

    def claim(self, assignments: list[dict]) -> None:
        """Reserviert jede Holdout-Ausfuehrung genau einmal vor dem API-Call."""
        with self._lock, _process_file_lock(self.execution_path):
            manifest = self._manifest()
            allowed = {str(item.get("execution_id") or "")
                       for item in manifest.get("plan") or []}
            ledger = {"executions": {}}
            if self.execution_path and os.path.exists(self.execution_path):
                with open(self.execution_path, encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, dict):
                    ledger = loaded
            executions = ledger.setdefault("executions", {})
            identifiers = [str(item.get("execution_id") or "")
                           for item in assignments]
            if not all(identifiers):
                raise ValueError("Holdout-Plan enthaelt leere execution_id.")
            if not set(identifiers) <= allowed:
                raise ValueError("Execution-ID ist nicht Teil des Holdout-Plans.")
            duplicates = [item for item in identifiers if item in executions]
            if duplicates:
                raise RuntimeError(
                    "Holdout-Ausfuehrung wurde bereits reserviert: "
                    + ", ".join(duplicates))
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            for identifier in identifiers:
                executions[identifier] = {"status": "reserved", "at": now}
            _atomic_json_write(self.execution_path, ledger)

    def finalize(self, assignment: dict, *, result_status: str,
                 result_hash: str) -> None:
        """Bindet die verbrauchte Execution-ID an ihren finalen Ausgang."""
        identifier = str(assignment.get("execution_id") or "")
        if not identifier or not str(result_hash or "").startswith("sha256-"):
            raise ValueError("Finalisierung braucht Execution-ID und Ergebnishash.")
        with self._lock, _process_file_lock(self.execution_path):
            with open(self.execution_path, encoding="utf-8") as handle:
                ledger = json.load(handle)
            record = (ledger.get("executions") or {}).get(identifier)
            if not record:
                raise RuntimeError("Holdout-Ausfuehrung wurde nicht reserviert.")
            if record.get("status") != "reserved":
                if (record.get("result_hash") == result_hash
                        and record.get("result_status") == result_status):
                    return
                raise RuntimeError("Holdout-Ausfuehrung ist bereits finalisiert.")
            record.update({
                "status": "consumed",
                "result_status": str(result_status or "technical_error"),
                "result_hash": result_hash,
                "completed_at": datetime.datetime.now(
                    datetime.timezone.utc).isoformat(),
            })
            _atomic_json_write(self.execution_path, ledger)


class StudyBudgetLedger:
    """Persistentes lokales Gesamtlimit mit Reservierung vor jedem Lauf."""

    def __init__(self, path: str, limit_usd: float):
        self.path = path
        self.limit_usd = round(float(limit_usd), 6)
        if self.limit_usd <= 0:
            raise ValueError("Studienbudget muss positiv sein.")
        self._lock = threading.Lock()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as handle:
                value = json.load(handle)
            if not isinstance(value, dict):
                raise RuntimeError("Studienbudget-Ledger ist ungueltig.")
            if (value.get("schema_version") != "study-budget-v1"
                    or value.get("currency") != "USD"):
                raise RuntimeError("Studienbudget-Ledger hat falsches Schema.")
            stored_limit = round(float(value.get("limit_usd") or 0.0), 6)
            if stored_limit != self.limit_usd:
                raise RuntimeError(
                    "Konfiguriertes Studienlimit stimmt nicht mit dem "
                    "eingefrorenen Ledger ueberein.")
            return value
        return {
            "schema_version": "study-budget-v1",
            "currency": "USD",
            "limit_usd": self.limit_usd,
            "spent_usd": 0.0,
            "reservations": {},
        }

    def snapshot(self) -> dict:
        with self._lock, _process_file_lock(self.path):
            value = self._load()
            reserved = sum(float(item.get("reserved_usd") or 0.0)
                           for item in value.get("reservations", {}).values()
                           if item.get("status") == "reserved")
            return {
                "limit_usd": float(value.get("limit_usd") or self.limit_usd),
                "spent_usd": round(float(value.get("spent_usd") or 0.0), 6),
                "reserved_usd": round(reserved, 6),
                "remaining_unreserved_usd": round(
                    float(value.get("limit_usd") or self.limit_usd)
                    - float(value.get("spent_usd") or 0.0) - reserved, 6),
            }

    def reserve(self, reservation_id: str, amount_usd: float,
                metadata: dict | None = None) -> dict:
        reservation_id = str(reservation_id or "").strip()
        amount = round(float(amount_usd), 6)
        if not reservation_id or amount <= 0:
            raise ValueError("Gueltige Reservierungs-ID und positiver Betrag noetig.")
        with self._lock, _process_file_lock(self.path):
            value = self._load()
            reservations = value.setdefault("reservations", {})
            if reservation_id in reservations:
                existing = reservations[reservation_id]
                if round(float(existing.get("reserved_usd") or 0.0), 6) != amount:
                    raise RuntimeError("Reservierungs-ID wurde fuer anderen Betrag genutzt.")
                if existing.get("status") != "reserved":
                    raise RuntimeError(
                        "Abgeschlossene Kostenreservierung darf keine neuen "
                        "API-Aufrufe autorisieren.")
                return dict(existing)
            reserved = sum(float(item.get("reserved_usd") or 0.0)
                           for item in reservations.values()
                           if item.get("status") == "reserved")
            available = float(value.get("limit_usd") or self.limit_usd) \
                - float(value.get("spent_usd") or 0.0) - reserved
            if amount > available + 1e-9:
                raise RuntimeError(
                    f"Studienbudget erschoepft: benoetigt ${amount:.2f}, "
                    f"frei ${max(0.0, available):.2f}.")
            record = {
                "status": "reserved",
                "reserved_usd": amount,
                "actual_usd": None,
                "created_at_utc": datetime.datetime.now(
                    datetime.timezone.utc).isoformat(),
                "metadata": dict(metadata or {}),
            }
            reservations[reservation_id] = record
            value["limit_usd"] = self.limit_usd
            _atomic_json_write(self.path, value)
            return dict(record)

    def settle(self, reservation_id: str, actual_usd: float,
               *, uncertain: bool = False) -> dict:
        with self._lock, _process_file_lock(self.path):
            value = self._load()
            record = value.get("reservations", {}).get(reservation_id)
            if not record:
                raise RuntimeError("Kostenreservierung fehlt.")
            if record.get("status") != "reserved":
                return dict(record)
            reserved = float(record.get("reserved_usd") or 0.0)
            actual = max(0.0, round(float(actual_usd), 6))
            # Ist der Providerverbrauch wider Erwarten hoeher als die
            # Reservierung, bleibt der reale Betrag fuehrend. Das Ledger darf
            # einen Kostenueberlauf nicht durch Abschneiden verbergen.
            charged = reserved if uncertain else actual
            record["status"] = "uncertain" if uncertain else "settled"
            record["actual_usd"] = actual
            record["charged_to_local_cap_usd"] = round(charged, 6)
            record["reservation_overrun_usd"] = round(
                max(0.0, actual - reserved), 6)
            record["settled_at_utc"] = datetime.datetime.now(
                datetime.timezone.utc).isoformat()
            value["spent_usd"] = round(
                float(value.get("spent_usd") or 0.0) + charged, 6)
            _atomic_json_write(self.path, value)
            return dict(record)
