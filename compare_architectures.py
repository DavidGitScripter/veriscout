"""Gepaarter, budgetkontrollierter SAS--MAS-Vergleich.

Das Modul erzeugt noch keine menschlichen Qualitaetsurteile. Es stellt sicher,
dass beide Architekturen dieselbe Aufgabe, dasselbe Modell, denselben
Feedback-Snapshot und dieselben Gesamtobergrenzen erhalten und exportiert ihre
Ergebnisse zur verblindeten Annotation.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import secrets
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field

from core import Config
from memory import FeedbackMemory, MemoryStore
from pipeline import Pipeline
from experiment_protocol import (PublicSearchField, PublicSearchTaskInput,
                                 legacy_public_task,
                                 stable_organization_id)
from knowledge_base import KnowledgeBase
from resource_budget import ResourceBroker, ResourceLimits
from evidence_resolver import EvidenceResolver
from review_contract import (candidate_from_dict, merge_scout_evidence,
                             review_mechanics)


@dataclass(frozen=True)
class ExperimentBudget:
    model: str = Config.MODEL
    reasoning_effort: str = Config.REASONING_EFFORT
    max_output_tokens: int = Config.EVAL_TOTAL_MAX_OUTPUT_TOKENS
    max_tool_calls: int = Config.EVAL_TOTAL_MAX_TOOL_CALLS
    max_candidates: int = Config.EVAL_MAX_CANDIDATES
    max_input_tokens: int = Config.EVAL_MAX_INPUT_TOKENS
    max_reasoning_tokens: int = Config.EVAL_MAX_REASONING_TOKENS
    max_model_calls: int = Config.EVAL_MAX_MODEL_CALLS
    max_resolver_fetches: int = Config.EVAL_MAX_RESOLVER_FETCHES
    max_cost_usd: float = Config.EVAL_MAX_COST_USD
    # M2: Reserve der Nachrecherche (0, wenn abgeschaltet), oben auf dem Basisprofil.
    follow_up_input_tokens: int = Config.FOLLOW_UP_MAX_INPUT_TOKENS if Config.FOLLOW_UP_ENABLED else 0
    follow_up_output_tokens: int = Config.FOLLOW_UP_MAX_OUTPUT_TOKENS if Config.FOLLOW_UP_ENABLED else 0
    follow_up_reasoning_tokens: int = Config.FOLLOW_UP_MAX_REASONING_TOKENS if Config.FOLLOW_UP_ENABLED else 0
    follow_up_tool_calls: int = Config.FOLLOW_UP_MAX_TOOL_CALLS if Config.FOLLOW_UP_ENABLED else 0
    follow_up_fetches: int = Config.FOLLOW_UP_MAX_FETCHES if Config.FOLLOW_UP_ENABLED else 0
    follow_up_cost_usd: float = Config.FOLLOW_UP_MAX_COST_USD if Config.FOLLOW_UP_ENABLED else 0.0

    @property
    def follow_up_enabled(self) -> bool:
        return self.follow_up_output_tokens > 0

    @property
    def arm_max_cost_usd(self) -> float:
        """Kostendeckel je Arm einschliesslich Nachrecherche (Worst Case)."""
        return round(self.max_cost_usd + self.follow_up_cost_usd, 4)

    def stage_allocation(self) -> dict:
        """Identische, harte Reservierung der Modellstufen fuer SAS-2 und MAS."""
        first_tokens = self.max_output_tokens // 2
        first_tools = self.max_tool_calls // 2
        stages = {
            "stage_1": {"max_output_tokens": first_tokens,
                        "max_tool_calls": first_tools},
            "stage_2": {"max_output_tokens": self.max_output_tokens - first_tokens,
                        "max_tool_calls": self.max_tool_calls - first_tools},
        }
        if self.follow_up_enabled:
            stages["stage_3"] = {"max_output_tokens": self.follow_up_output_tokens,
                                 "max_tool_calls": self.follow_up_tool_calls}
        return stages

    def mas_allocation(self) -> dict:
        scout_tokens = self.max_output_tokens // 2
        scout_tools = self.max_tool_calls // 2
        return {
            "scouting": {"max_output_tokens": scout_tokens,
                         "max_tool_calls": scout_tools},
            "verification": {
                "max_output_tokens": self.max_output_tokens - scout_tokens,
                "max_tool_calls": self.max_tool_calls - scout_tools,
            },
        }

    def validate(self) -> None:
        if not 1 <= self.max_candidates <= 20:
            raise ValueError("Die Kandidatenobergrenze muss zwischen 1 und 20 liegen.")
        if self.max_output_tokens <= 0 or self.max_tool_calls < 0:
            raise ValueError("Token- und Toolbudgets muessen nichtnegativ sein.")
        configured = {Config.MODEL_SAS, Config.MODEL_SCOUT, Config.MODEL_VERIFY}
        if configured != {self.model}:
            raise ValueError(
                "Primaervergleich ungueltig: SAS, Scouting und Verifikation "
                "muessen exakt dieselbe GPT-Modell-ID verwenden.")
        if self.model not in Config.PRICES:
            raise ValueError(
                "Primaervergleich ungueltig: Fuer die Modell-ID ist kein "
                "eingefrorener Preis hinterlegt.")
        self.resource_limits().validate()

    def resource_limits(self) -> ResourceLimits:
        extra_call = 1 if self.follow_up_enabled else 0
        return ResourceLimits(
            max_input_tokens=self.max_input_tokens + self.follow_up_input_tokens,
            max_output_tokens=self.max_output_tokens + self.follow_up_output_tokens,
            max_reasoning_tokens=self.max_reasoning_tokens + self.follow_up_reasoning_tokens,
            max_web_calls=self.max_tool_calls + self.follow_up_tool_calls,
            max_model_calls=self.max_model_calls + extra_call,
            max_resolver_fetches=self.max_resolver_fetches + self.follow_up_fetches,
            max_cost_usd=self.arm_max_cost_usd,
        )


@dataclass(frozen=True)
class ComparisonTask:
    task_id: str
    target_actor_id: str = ""
    query: str = ""
    push_mode: bool = True
    # Neuer konfirmatorischer Vertrag. `target_actor_id/query` bleiben fuer
    # bestehende Offline-Skripte lesbar, gelten aber nicht als studienbereit.
    organization_id: str = ""
    organization_name: str = ""
    organization_domain_hint: str = ""
    search_prompt: str = ""
    public_search_field: dict = field(default_factory=dict)
    public_source_package: tuple[dict, ...] = ()
    task_group_id: str = ""
    dataset_split: str = "test"
    event_time: str = ""
    search_mode: str = "push"
    search_area: str = ""

    def public_input(self, *, strict: bool = True) -> PublicSearchTaskInput:
        organization_name = self.organization_name.strip()
        if not organization_name:
            if strict:
                raise ValueError("ComparisonTask braucht organization_name.")
            try:
                legacy_id = (self.organization_id or self.target_actor_id).strip()
                organization_name = KnowledgeBase().get(legacy_id)["name"]
            except Exception:
                organization_name = (self.organization_id or
                                     self.target_actor_id).strip()
        if not organization_name:
            raise ValueError("ComparisonTask braucht organization_name.")
        generated_id = stable_organization_id(
            organization_name, self.organization_domain_hint)
        supplied_id = (self.organization_id or self.target_actor_id).strip()
        if strict and supplied_id and supplied_id != generated_id:
            raise ValueError(
                "organization_id wird technisch erzeugt und darf nicht abweichen.")
        organization_id = generated_id if strict else (supplied_id or generated_id)
        search_prompt = (self.search_prompt.strip() or
                         str(self.public_search_field.get("description") or "").strip() or
                         self.query.strip())
        if not search_prompt:
            if strict:
                raise ValueError("Konfirmatorischer Lauf braucht search_prompt.")
            return legacy_public_task(
                task_id=self.task_id, organization_id=organization_id,
                organization_name=organization_name, query=self.query,
                task_group_id=self.task_group_id)
        search_field = PublicSearchField.from_prompt(search_prompt)
        result = PublicSearchTaskInput(
            task_id=self.task_id,
            organization_id=organization_id,
            organization_name=organization_name,
            search_field=search_field,
            organization_domain_hint=self.organization_domain_hint,
            public_source_package=(tuple(deepcopy(
                list(self.public_source_package or ()))) if not strict else ()),
            task_group_id=self.task_group_id or self.task_id,
            dataset_split=self.dataset_split,
            event_time=self.event_time,
            strict_public_only=strict,
            search_mode=(self.search_mode or "push").strip().lower(),
            search_area=self.search_area,
        )
        result.validate()
        return result


def _blind_code() -> str:
    """Nicht ableitbarer Arm-Code; Zuordnung existiert nur im Manifest."""
    return "arm-" + secrets.token_hex(8)


def _usage_totals(records: list[dict]) -> dict:
    keys = ("input_tokens", "cached_input_tokens", "output_tokens",
            "reasoning_tokens", "tool_calls")
    totals = {key: sum(int(record.get(key) or 0) for record in records)
              for key in keys}
    totals["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    return totals


class PairedArchitectureRunner:
    def __init__(self, budget: ExperimentBudget | None = None,
                 memory_records: list[dict] | None = None,
                 live: bool = False):
        self.budget = budget or ExperimentBudget()
        self.budget.validate()
        self.memory_records = list(memory_records or [])
        self.live = live

    def _pipeline(self, broker: ResourceBroker) -> Pipeline:
        store = MemoryStore(records=self.memory_records, read_only=True)
        return Pipeline(
            live=self.live, memory=FeedbackMemory(store),
            resource_broker=broker, audit_write=False,
            reasoning_effort=self.budget.reasoning_effort)

    def _run_arm(self, task: ComparisonTask, architecture: str,
                 memory_enabled: bool, guardrail_enabled: bool,
                 pair_id: str, task_input: PublicSearchTaskInput,
                 memory_packet: dict) -> dict:
        broker = ResourceBroker(self.budget.resource_limits())
        broker.reserve_stages(self.budget.stage_allocation())
        # M2: Abrufreserve der Nachrecherche fuer die erste Belegpruefung sperren.
        broker.follow_up_fetch_reserve = self.budget.follow_up_fetches
        pipeline = self._pipeline(broker)
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        follow_up_info = {"enabled": self.budget.follow_up_enabled, "triggered": False,
                          "skipped_reason": "nicht erreicht", "candidates": []}
        try:
            candidates, discovery = pipeline.discover(
                task_input.prompt(),
                n=self.budget.max_candidates,
                target_actor_id=task_input.organization_id,
                push_mode=True,
                architecture=architecture,
                max_tokens=self.budget.max_output_tokens,
                max_tool_calls=self.budget.max_tool_calls,
                use_memory=memory_enabled,
                include_curated=False,
                task_input=task_input,
                memory_context_override=(memory_packet if memory_enabled else {}),
            )
            # Harter, gemeinsamer Cap auch bei fehlerhaftem Agentenoutput.
            candidates = list(candidates)[:self.budget.max_candidates]
            decisions = [pipeline.scout(
                candidate,
                use_guardrail=guardrail_enabled,
                # Memory wurde exakt einmal in der Suchrolle exponiert.
                use_memory=False,
                target_actor_id=task_input.organization_id,
            ).to_dict() for candidate in candidates]
            if self.budget.follow_up_enabled and self.live:
                from follow_up import run_follow_up
                try:
                    decisions, follow_up_info = run_follow_up(
                        pipeline, architecture=architecture, query=task_input.prompt(),
                        candidates=candidates, decisions=decisions,
                        target_actor_id=task_input.organization_id,
                        guardrail=guardrail_enabled)
                except Exception as error:  # Entscheidungen vor der Nachrecherche bleiben
                    broker.mark_failure(f"follow_up_{type(error).__name__}")
                    follow_up_info = {"enabled": True, "triggered": True,
                                      "skipped_reason": f"Fehler {type(error).__name__}",
                                      "candidates": []}
                output = discovery.setdefault("output", {})
                output["follow_up"] = follow_up_info
                if follow_up_info.get("triggered"):
                    output.setdefault("stage_artifacts", {})["post_follow_up"] = [
                        asdict(item) for item in deepcopy(candidates)]
        except Exception as error:
            broker.mark_failure(f"unhandled_{type(error).__name__}")
            discovery = {"status": "error", "info": type(error).__name__}
            decisions = []
        mechanics = self._mechanics(discovery, architecture)
        sensitivity = self._sensitivities(
            pipeline, discovery, architecture, guardrail_enabled, task_input)
        usage = pipeline.llm.usage_ledger()
        totals = _usage_totals(usage)
        resources = broker.summary()
        # Websuchen ueber dem Anteil sind Anbieterverhalten. Sie werden je
        # Stufe als Protokollabweichung berichtet und nur im strikten
        # Sensitivitaetsmodus als Budgetverletzung gewertet.
        web_overrun_fatal = Config.EVAL_WEB_OVERRUN_POLICY == "fail"
        limits = self.budget.resource_limits()
        violation = bool(totals["output_tokens"] > limits.max_output_tokens or
                         (web_overrun_fatal
                          and totals["tool_calls"] > limits.max_web_calls))
        violation = bool(
            violation
            or resources["input_tokens"] > limits.max_input_tokens
            or resources["reasoning_tokens"] > limits.max_reasoning_tokens
            or resources["model_calls"] > limits.max_model_calls
            or resources["resolver_fetches"] > limits.max_resolver_fetches
            or float(resources["cost_usd"]) > limits.max_cost_usd)
        decision_statuses = {
            str(item.get("evaluation_status") or "") for item in decisions
        }
        technical_failure = bool(
            resources["technical_failure"]
            or str(discovery.get("status") or "") in {"error", "technical_error"})
        budget_unchecked = bool(
            "not_checked_budget" in decision_statuses
            or str(discovery.get("status") or "") == "not_checked_budget")
        deviations = list(resources.get("protocol_deviations") or [])
        if technical_failure or violation:
            result_status = "technical_error"
            exclusion_reason = ("budget_violation" if violation
                                else "provider_or_contract_failure")
        elif "completed" in decision_statuses:
            # Eine vollstaendig gepruefte Empfehlung bleibt gueltig, auch wenn
            # Quellen eines ANDEREN Kandidaten wegen des Abrufbudgets
            # ungeprueft blieben (Kap. 7: Erfolg = vollstaendig geprueftes,
            # qualifiziertes Ergebnis). Die strenge Lesart wertet der
            # Auswerter als Sensitivitaet "strict_budget".
            result_status = "completed"
            exclusion_reason = ""
            if budget_unchecked:
                deviations.append("resolver_budget_partial")
        elif budget_unchecked:
            result_status = "not_checked_budget"
            exclusion_reason = "resolver_budget_prevented_complete_check"
        else:
            result_status = "abstention"
            exclusion_reason = "valid_empty_or_no_eligible_candidate"
        stage_artifacts = deepcopy(
            (discovery.get("output") or {}).get("stage_artifacts") or {})
        stage_artifact_hashes = {
            name: "sha256-" + hashlib.sha256(json.dumps(
                value, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode("utf-8")).hexdigest()
            for name, value in stage_artifacts.items()
        }
        raw_outputs = list((discovery.get("output") or {}).get(
            "raw_model_outputs") or [])
        raw_outputs.extend(list(((discovery.get("output") or {}).get(
            "verification") or {}).get("raw_model_outputs") or []))
        for index, record in enumerate(raw_outputs, start=1):
            label = str(record.get("stage") or f"raw_{index}")
            stage_artifact_hashes[f"raw:{label}:{index}"] = (
                "sha256-" + hashlib.sha256(
                    str(record.get("text") or "").encode("utf-8")).hexdigest())
        return {
            "experiment_id": str(uuid.uuid4()),
            "pair_id": pair_id,
            "task_id": task.task_id,
            "task_input_hash": task_input.input_hash(),
            "prompt_hash": task_input.prompt_hash(),
            "blind_arm_id": _blind_code(),
            "architecture_internal": architecture,
            "started_at": started,
            "completed_at": datetime.datetime.now(
                datetime.timezone.utc).isoformat(),
            "model": self.budget.model,
            "reasoning_effort": self.budget.reasoning_effort,
            "budget": asdict(self.budget),
            "mas_allocation": (self.budget.mas_allocation()
                               if architecture == "mas" else None),
            "memory_enabled": memory_enabled,
            "memory_snapshot": pipeline.memory.store.snapshot_id(),
            "memory_packet_hash": hashlib.sha256(json.dumps(
                memory_packet if memory_enabled else {}, ensure_ascii=False,
                sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
            "guardrail_enabled": guardrail_enabled,
            "curated_leads": False,
            "usage": usage,
            "usage_totals": totals,
            "resource_usage": resources,
            "result_status": result_status,
            "primary_analysis_eligible": result_status in {
                "completed", "abstention"},
            "primary_exclusion_reason": exclusion_reason,
            "technical_failure": technical_failure,
            "budget_violation": violation,
            "stage_allocation": self.budget.stage_allocation(),
            "positive_candidate_ids": [
                str((item.get("candidate") or {}).get("candidate_id") or "")
                for item in decisions
                if item.get("decision_state") == "empfehlung"],
            "decision_states": [item.get("decision_state") for item in decisions],
            "review_mechanics": mechanics,
            "sensitivity": sensitivity,
            "protocol_deviations": deviations,
            "discovery_trace": discovery,
            "stage_artifacts": stage_artifacts,
            "stage_artifact_hashes": stage_artifact_hashes,
            "decision_rule": {
                "threshold": Config.THRESHOLD_SUFFICIENT,
                "threshold_role": "necessary_not_sufficient",
                "rubric_version": Config.THRESHOLD_RUBRIC_VERSION,
                "evidence_coverage_definition": (
                    "equal-weight share of supported required relational "
                    "evidence dimensions"),
                "additional_requirement": "fully_supported_and_quality_gates",
            },
            "decisions": decisions,
            "external_actions_enabled": False,
        }

    @staticmethod
    def _status_from_decisions(decisions: list[dict], technical: bool) -> str:
        if technical:
            return "technical_error"
        statuses = {str(item.get("evaluation_status") or "") for item in decisions}
        if "completed" in statuses:
            return "completed"
        if "not_checked_budget" in statuses:
            return "not_checked_budget"
        return "abstention"

    def _sensitivities(self, pipeline: Pipeline, discovery: dict,
                       architecture: str, guardrail_enabled: bool,
                       task_input: PublicSearchTaskInput) -> dict:
        """Kostenfreie Sensitivitaetsanalysen auf denselben Modellantworten.

        * exact_excerpt: wortgleicher statt unscharfer Auszugsabgleich, nur mit
          bereits abgerufenen Dokumenten (keine weiteren Abrufe).
        * mas_scout_sources (nur MAS): Quellen der Scoutingrolle zaehlen, sofern
          der Verifier die Aussage nicht widerlegt. Fehlende Dokumente werden
          mit eigenem, gleich grossem Abrufkontingent geholt (keine API-Kosten).
        Beide veraendern das Primaerergebnis nicht.
        """
        artifacts = ((discovery.get("output") or {}).get("stage_artifacts") or {})
        post = list(artifacts.get("post_architecture_review") or [])
        technical = str(discovery.get("status") or "") in {"error", "technical_error"}
        result = {}

        def evaluate(candidates: list, resolver: EvidenceResolver, cap: int) -> dict:
            resolver.resolve_candidates(candidates, max_fetches_total=cap)
            decisions = [pipeline.scout(candidate, use_guardrail=guardrail_enabled,
                                        use_memory=False,
                                        target_actor_id=task_input.organization_id
                                        ).to_dict() for candidate in candidates]
            return {
                "result_status": self._status_from_decisions(decisions, technical),
                "positive_candidate_ids": [
                    str((item.get("candidate") or {}).get("candidate_id") or "")
                    for item in decisions if item.get("decision_state") == "empfehlung"],
                "decision_states": [item.get("decision_state") for item in decisions],
            }

        previous_mode = Config.EXCERPT_MATCH_MODE
        audit_write = pipeline.audit_write
        pipeline.audit_write = False
        try:
            Config.EXCERPT_MATCH_MODE = "exact"
            offline = EvidenceResolver()
            offline.cache = dict(pipeline.resolver.cache)
            result["exact_excerpt"] = evaluate(
                [candidate_from_dict(item) for item in post], offline, 0)
            Config.EXCERPT_MATCH_MODE = previous_mode
            if architecture == "mas" and post:
                pre = {str(item.get("candidate_id") or ""): candidate_from_dict(item)
                       for item in artifacts.get("pre_architecture_review") or []}
                merged = []
                for item in post:
                    candidate = candidate_from_dict(item)
                    source = pre.get(candidate.candidate_id)
                    merged.append(merge_scout_evidence(candidate, source)
                                  if source is not None else candidate)
                fetcher = EvidenceResolver()
                fetcher.cache = dict(pipeline.resolver.cache)
                result["mas_scout_sources"] = evaluate(
                    merged, fetcher, self.budget.max_resolver_fetches)
                result["mas_scout_sources"]["additional_fetches"] = (
                    len(fetcher.cache) - len(pipeline.resolver.cache))
        except Exception as error:  # Sensitivitaet darf Primaerlauf nie kippen
            result["error"] = type(error).__name__
        finally:
            Config.EXCERPT_MATCH_MODE = previous_mode
            pipeline.audit_write = audit_write
        return result

    @staticmethod
    def _mechanics(discovery: dict, architecture: str) -> dict:
        output = discovery.get("output") or {}
        artifacts = output.get("stage_artifacts") or {}
        post = list(artifacts.get("post_architecture_review") or [])
        if architecture == "mas":
            pre = list(artifacts.get("pre_architecture_review") or [])
        else:
            pre = list(output.get("pre_review_candidates") or [])
        return review_mechanics(pre, post)

    def run_pair(self, task: ComparisonTask, memory_enabled: bool = False,
                 guardrail_enabled: bool = True,
                 planned_assignment: dict | None = None) -> dict:
        task_input = task.public_input(strict=self.live)
        evaluation_context = {
            "task_group_id": task_input.task_group_id or task_input.task_id,
            "dataset_split": task_input.dataset_split,
            "event_time": task_input.event_time,
        }
        memory_service = FeedbackMemory(MemoryStore(
            records=self.memory_records, read_only=True))
        memory_packet = (memory_service.context(
            task_input.organization_id, task_input.prompt(),
            evaluation_context=evaluation_context)
            if memory_enabled else {})
        assignment = dict(planned_assignment or {})
        planned_order = list(assignment.get("order") or [])
        if planned_order and (len(planned_order) != 2
                              or set(planned_order) != {"sas2", "mas"}):
            raise ValueError("Geplante Armreihenfolge muss SAS-2 und MAS enthalten.")
        if assignment:
            if str(assignment.get("task_id") or "") != task.task_id:
                raise ValueError("Versuchsplan und Aufgabe widersprechen sich.")
            if (str(assignment.get("task_input_hash") or "")
                    != task_input.input_hash()):
                raise ValueError("Versuchsplan und Task-Hash widersprechen sich.")
            if bool(assignment.get("memory_enabled")) != bool(memory_enabled):
                raise ValueError("Versuchsplan und Memory-Zustand widersprechen sich.")
        # Entwicklungsaufrufe ohne Studienplan bleiben moeglich, erhalten aber
        # eine klar markierte, stabile Standardreihenfolge. Bezahlte Routen
        # uebergeben immer einen vorab gespeicherten counterbalancierten Plan.
        order = planned_order or ["sas2", "mas"]
        pair_id = (str(assignment.get("execution_id") or "").replace(
            "exec-", "pair-", 1) if assignment else
            f"pair-development-{task.task_id}-{uuid.uuid4().hex[:8]}")
        arms = [self._run_arm(task, architecture, memory_enabled,
                              guardrail_enabled, pair_id, task_input,
                              memory_packet)
                for architecture in order]
        return {
            "pair_id": pair_id,
            "task": task_input.canonical_dict(),
            "task_input_hash": task_input.input_hash(),
            "prompt_hash": task_input.prompt_hash(),
            "order": order,
            "study_id": str(assignment.get("study_id") or "development"),
            "execution_id": str(assignment.get("execution_id") or ""),
            "replicate_index": int(assignment.get("replicate_index") or 0),
            "block_index": int(assignment.get("block_index") or 0),
            "allocation_seed": str(assignment.get("allocation_seed") or ""),
            "randomization_algorithm_version": str(
                assignment.get("randomization_algorithm_version") or
                "unplanned-development"),
            "primary_contrast": "sas2_self_review_vs_mas",
            "arms": arms,
            "annotation_contract": {
                "blind": True,
                "dimensions": [
                    "candidate_validity",
                    "claim_support",
                    "relational_chain_correctness",
                    "usefulness_for_human_review",
                    "over_matching",
                    "missed_relevant_candidate",
                ],
                "note": "Architekturcodes erst nach Abschluss der Annotation entblinden.",
            },
        }

    def run_memory_factorial(self, task: ComparisonTask,
                             guardrail_enabled: bool = True) -> dict:
        """Fuehrt SAS/MAS jeweils ohne und mit identischem Memory-Snapshot aus."""
        return {
            "design": "2x2 architecture_by_memory",
            "task": asdict(task),
            "memory_snapshot": MemoryStore(
                records=self.memory_records, read_only=True).snapshot_id(),
            "cells": [
                self.run_pair(task, memory_enabled=False,
                              guardrail_enabled=guardrail_enabled),
                self.run_pair(task, memory_enabled=True,
                              guardrail_enabled=guardrail_enabled),
            ],
            "interpretation": (
                "Architektureffekt, Memory-Haupteffekt und Interaktion getrennt auswerten; "
                "ein Memory-Haupteffekt allein begruendet kein MAS."
            ),
        }


def append_pair(path: str, result: dict) -> None:
    """Interner Append-only-Export einschliesslich Entblindungsinformationen."""
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False) + "\n")


# Nur Name, Website, Aussagen und Belege. Freitexte des Systems (Beschreibung,
# Kettenfelder, Fortbestand) koennen Systemurteile enthalten, etwa "keine
# verifizierte Empfehlung", und sind deshalb nicht Teil des Blindpakets.
BLIND_CANDIDATE_FIELDS = ("candidate_id", "name", "website", "official_url")
BLIND_SOURCE_FIELDS = (
    "url", "resolved_url", "title", "publisher", "published_at", "excerpt",
    "source_type",
)


def annotation_package(result: dict) -> dict:
    """Erzeugt das tatsaechlich verblindete Paket fuer Fachannotierende.

    Das interne Ergebnis darf wegen Rollenbezeichnungen, Reihenfolge und
    Nutzungsmetadaten nie direkt an Bewertende gegeben werden.
    """
    arms = []
    for arm in result.get("arms", []):
        decisions = []
        for original in arm.get("decisions", []):
            raw_candidate = deepcopy(original.get("candidate") or {})
            matrix = deepcopy(raw_candidate.get("evidence_matrix") or {})
            # Bewertende erhalten Faktenbehauptungen und Belege, aber weder
            # Systemurteil noch Score, Empfehlung, Enthaltung oder Gate-Status.
            # Feste Feldliste statt Ausschlussliste: Felder, die nur eine
            # Architektur befuellt, koennten sonst die Herkunft verraten.
            claims = []
            for item in matrix.get("claim_manifest", []) or []:
                if not isinstance(item, dict):
                    continue
                claims.append({key: item.get(key) for key in (
                    "claim_id", "claim_text", "field", "source_id", "excerpt",
                    "subject_type", "subject_id", "subject_name")})
            candidate = {key: raw_candidate.get(key) for key in BLIND_CANDIDATE_FIELDS
                         if raw_candidate.get(key) not in (None, "", [], {})}
            if not candidate.get("website") and raw_candidate.get("official_url"):
                candidate["website"] = raw_candidate.get("official_url")
            candidate.pop("official_url", None)
            # SAS-2 uebernimmt die Quellen aus Schritt 1, MAS nicht. Gezeigt
            # werden deshalb nur Quellen, auf die sich eine Aussage stuetzt,
            # sonst liesse sich die Architektur an der Quellenzahl erraten.
            referenced = {str(item.get("source_id") or "") for item in claims}
            sources = []
            for index, source in enumerate(raw_candidate.get("sources") or [], start=1):
                if not isinstance(source, dict):
                    continue
                source_id = str(source.get("source_id") or f"s{index}")
                if source_id not in referenced:
                    continue
                kept = {key: source.get(key) for key in BLIND_SOURCE_FIELDS
                        if source.get(key) not in (None, "")}
                kept["source_id"] = source_id
                sources.append(kept)
            candidate["sources"] = sorted(sources, key=lambda item: item["source_id"])
            candidate["claims_for_annotation"] = claims
            decisions.append({"candidate": candidate})
        arms.append({
            "blind_arm_id": arm.get("blind_arm_id"),
            "decisions": decisions,
        })
    # Die Laufreihenfolge (AB/BA) darf aus der Position im Blindpaket nicht
    # ablesbar sein.
    secrets.SystemRandom().shuffle(arms)
    task = result.get("task") or {}
    return {
        "pair_id": result.get("pair_id"),
        "task_id": task.get("task_id"),
        "organization_id": task.get("organization_id"),
        # Auftragsangaben sind fuer beide Arme gleich und verraten nichts.
        "organization_name": task.get("organization_name"),
        "organization_domain_hint": task.get("organization_domain_hint"),
        "search_prompt": task.get("search_prompt"),
        "search_mode": task.get("search_mode"),
        "search_area": task.get("search_area"),
        "search_field": deepcopy(task.get("search_field") or {}),
        "arms": arms,
        "annotation_contract": deepcopy(result.get("annotation_contract") or {}),
    }


def assignment_manifest(result: dict) -> dict:
    """Getrennt zu verwahrende Zuordnung fuer die Entblindung."""
    def candidate_ids(arm: dict) -> list[str]:
        identifiers = []
        for decision in arm.get("decisions") or []:
            candidate = decision.get("candidate") or {}
            identifier = str(candidate.get("candidate_id") or "").strip()
            if not identifier:
                identifier = "candidate-" + hashlib.sha256(
                    str(candidate.get("name") or "").casefold().encode("utf-8")
                ).hexdigest()[:16]
            identifiers.append(identifier)
        return identifiers

    return {
        "schema_version": "venture-scout-assignment-v2",
        "pair_id": result.get("pair_id"),
        "task_id": (result.get("task") or {}).get("task_id"),
        "task_input_hash": result.get("task_input_hash"),
        "prompt_hash": result.get("prompt_hash"),
        "study_id": result.get("study_id"),
        "execution_id": result.get("execution_id"),
        "replicate_index": result.get("replicate_index"),
        "block_index": result.get("block_index"),
        "allocation_seed": result.get("allocation_seed"),
        "randomization_algorithm_version": result.get(
            "randomization_algorithm_version"),
        "order": list(result.get("order") or []),
        "assignments": [
            {
                "blind_arm_id": arm.get("blind_arm_id"),
                "architecture": arm.get("architecture_internal"),
                "expected_candidate_ids": candidate_ids(arm),
                "returned_candidates": len(arm.get("decisions") or []),
                "usage": deepcopy(arm.get("usage_totals") or {}),
                "result_status": arm.get("result_status"),
                "primary_analysis_eligible": bool(
                    arm.get("primary_analysis_eligible")),
                "primary_exclusion_reason": arm.get(
                    "primary_exclusion_reason", ""),
                "technical_failure": bool(arm.get("technical_failure")),
                "budget_violation": bool(arm.get("budget_violation")),
                "protocol_deviations": list(arm.get("protocol_deviations") or []),
                "positive_candidate_ids": list(arm.get("positive_candidate_ids") or []),
                "review_mechanics": deepcopy(arm.get("review_mechanics") or {}),
                "sensitivity": deepcopy(arm.get("sensitivity") or {}),
                "stage_artifact_hashes": deepcopy(
                    arm.get("stage_artifact_hashes") or {}),
                "model_calls": [{key: record.get(key) for key in (
                    "call_id", "response_id", "timestamp_utc", "purpose",
                    "status", "model_requested", "model_returned",
                    "reasoning_effort", "system_prompt_sha256",
                    "user_prompt_sha256", "request_payload_sha256",
                    "api_contract", "api_endpoint", "max_output_tokens",
                    "max_tool_calls", "web_search_context_size")}
                    for record in arm.get("usage") or []],
            }
            for arm in result.get("arms", [])
        ],
    }


def append_blind_exports(annotation_path: str, manifest_path: str,
                         result: dict) -> None:
    """Schreibt Annotation und Entblindung in getrennte Append-only-Dateien."""
    with open(annotation_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(annotation_package(result), ensure_ascii=False) + "\n")
    with open(manifest_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(assignment_manifest(result), ensure_ascii=False) + "\n")


ARCHITECTURE_LABELS = {
    "sas2": "SAS-2 · Einzelagent mit Selbstprüfung",
    "mas": "MAS · Scouting- und Verifikationsrolle",
}


def _unique_claims(manifest: list[dict]) -> list[dict]:
    """Eine Aussage je Feld, Quelle und Auszug (Quellen-Tags erzeugen sonst Dubletten)."""
    seen, rows = set(), []
    for claim in manifest:
        key = (claim.get("field"), claim.get("source_id"),
               " ".join(str(claim.get("excerpt") or "").split()).casefold())
        if key in seen:
            continue
        seen.add(key)
        rows.append({name: claim.get(name) for name in (
            "claim_id", "field", "claim_text", "stance", "source_id",
            "excerpt", "subject_type")})
    return rows


def operator_view(internal_pairs: list[dict], *, run_id: str = "",
                  created_at: str = "") -> dict:
    """Kompakte, nicht verblindete Prueferansicht eines Laufs fuer die Oberflaeche.

    Fachbewertende erhalten ausschliesslich das Blindpaket. Diese Ansicht ist
    fuer die ausfuehrende Person bestimmt (Pruefoberflaeche, QA5) und fuer die
    Vorfuehrung gespeicherter Laeufe ohne erneute API-Kosten.
    """
    def candidate_view(decision: dict) -> dict:
        candidate = decision.get("candidate") or {}
        matrix = candidate.get("evidence_matrix") or {}
        return {
            "candidate_id": candidate.get("candidate_id", ""),
            "name": candidate.get("name", ""),
            "website": candidate.get("official_url") or candidate.get("website", ""),
            "company_type": candidate.get("company_type", ""),
            "operating_status": candidate.get("operating_status", ""),
            "founded": candidate.get("founded"),
            "description": candidate.get("description", ""),
            "decision_state": decision.get("decision_state", ""),
            "decision_state_reason": decision.get("decision_state_reason", ""),
            "evaluation_status": decision.get("evaluation_status", ""),
            "evidence_coverage": decision.get("evidence_coverage"),
            "verification_status": candidate.get("verification_status", ""),
            "verification_reasons": list(candidate.get("verification_reasons") or []),
            "unresolved_requirements": list(candidate.get("unresolved_requirements") or []),
            "matrix": [{key: cell.get(key) for key in (
                "dimension", "claim", "status", "source_ids", "excerpts",
                "open_questions", "basis")} for cell in matrix.get("cells") or []],
            "claims": _unique_claims(matrix.get("claim_manifest") or []),
            "sources": [{key: source.get(key) for key in (
                "source_id", "url", "title", "source_type", "publisher",
                "subject_type", "resolved_status", "excerpt_match_mode",
                "text_status", "resolved_at", "content_hash", "supports",
                "resolved_url", "relocation")}
                for source in candidate.get("sources") or []],
            "quality_gates": decision.get("quality_gates") or [],
            # R2: vom Resolver abgerufenes Impressum (oeffentliche URL des Startups).
            "impressum": {key: (candidate.get("impressum") or {}).get(key) for key in (
                "url", "company_name_found", "register", "country")},
        }

    pairs = []
    task = {}
    model = ""
    budget = {}
    for pair in internal_pairs:
        task = pair.get("task") or task
        arms = []
        for arm in pair.get("arms") or []:
            resources = arm.get("resource_usage") or {}
            model = arm.get("model") or model
            budget = arm.get("budget") or budget
            arms.append({
                "architecture": arm.get("architecture_internal"),
                "label": ARCHITECTURE_LABELS.get(arm.get("architecture_internal"), ""),
                "blind_arm_id": arm.get("blind_arm_id"),
                "result_status": arm.get("result_status"),
                "primary_exclusion_reason": arm.get("primary_exclusion_reason", ""),
                "decision_states": arm.get("decision_states") or [],
                "positive_candidate_ids": arm.get("positive_candidate_ids") or [],
                "resources": {key: resources.get(key) for key in (
                    "input_tokens", "cached_input_tokens", "output_tokens",
                    "reasoning_tokens", "web_calls", "model_calls",
                    "resolver_fetches", "cost_usd", "wall_latency_ms",
                    "stage_usage", "failure_reasons")},
                "protocol_deviations": arm.get("protocol_deviations") or [],
                "review_mechanics": arm.get("review_mechanics") or {},
                "sensitivity": arm.get("sensitivity") or {},
                "model_calls": [{key: call.get(key) for key in (
                    "purpose", "status", "model_returned", "input_tokens",
                    "output_tokens", "reasoning_tokens", "tool_calls")}
                    for call in arm.get("usage") or []],
                "candidates": [candidate_view(item) for item in arm.get("decisions") or []],
            })
        pairs.append({
            "pair_id": pair.get("pair_id"),
            "order": pair.get("order"),
            "replicate_index": pair.get("replicate_index"),
            "arms": arms,
        })
    return {
        "schema_version": "operator-view-v1",
        "run_id": run_id,
        "created_at": created_at,
        "task": {key: task.get(key) for key in (
            "task_id", "organization_name", "search_prompt", "dataset_split",
            "search_mode", "search_area")},
        "model": model,
        "budget": budget,
        "pairs": pairs,
    }
