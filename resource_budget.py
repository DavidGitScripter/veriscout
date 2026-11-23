"""Gemeinsamer Ressourcenbroker fuer faire SAS--MAS-Vergleiche."""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass

from core import Config


@dataclass(frozen=True)
class ResourceLimits:
    max_input_tokens: int
    max_output_tokens: int
    max_reasoning_tokens: int
    max_web_calls: int
    max_model_calls: int
    max_resolver_fetches: int
    max_cost_usd: float

    def validate(self) -> None:
        for name in (
            "max_input_tokens", "max_output_tokens", "max_reasoning_tokens",
            "max_web_calls", "max_model_calls", "max_resolver_fetches",
        ):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} darf nicht negativ sein.")
        if float(self.max_cost_usd) < 0:
            raise ValueError("max_cost_usd darf nicht negativ sein.")


# Beide Architekturen bestehen aus genau zwei Modellstufen. Die Zuordnung
# erfolgt ueber den protokollierten Aufrufzweck, nicht ueber die Architektur.
STAGE_PURPOSE_PREFIXES = (
    ("sas2_research", "stage_1"),
    ("mas_scouting", "stage_1"),
    ("sas2_self_review", "stage_2"),
    ("mas_verification", "stage_2"),
    ("follow_up", "stage_3"),  # M2 Nachrecherche, beide Arme
)


def stage_for_purpose(purpose: str) -> str:
    value = str(purpose or "")
    for prefix, stage in STAGE_PURPOSE_PREFIXES:
        if value.startswith(prefix):
            return stage
    return ""


class ResourceBroker:
    """Zaehlt Ressourcen global je Arm und stoppt weitere Arbeit fail-closed.

    Provider-Tokens sind erst nach einer Antwort exakt bekannt. Vor jedem Call
    wird deshalb die Eingabe konservativ geschaetzt und das explizite
    Ausgabelimit geprueft. Nach der Antwort sind ausschliesslich die gemessenen
    Providerwerte fuehrend; eine Ueberschreitung sperrt jeden weiteren Call und
    markiert den Arm als ungueltig.
    """

    def __init__(self, limits: ResourceLimits):
        limits.validate()
        self.limits = limits
        self.started = time.perf_counter()
        self._lock = threading.Lock()
        self.input_tokens = 0
        self.cached_input_tokens = 0
        self.output_tokens = 0
        self.reasoning_tokens = 0
        self.web_calls = 0
        self.model_calls = 0
        self.resolver_fetches = 0
        self.cost_usd = 0.0
        self.model_latency_ms = 0.0
        self.resolver_latency_ms = 0.0
        self.technical_failure = False
        self.failure_reasons: list[str] = []
        # Optionale harte Reservierung je Modellstufe. Ohne Reservierung gilt
        # ausschliesslich das globale Armbudget (Altverhalten).
        self.stage_allocations: dict[str, dict] = {}
        self.stage_usage: dict[str, dict] = {}
        self.protocol_deviations: list[str] = []

    @staticmethod
    def estimate_input_tokens(system: str, user: str) -> int:
        # Nur Preflight. Der finale Messwert stammt aus der API-Antwort.
        return max(1, (len(str(system or "")) + len(str(user or "")) + 3) // 4)

    def _fail(self, reason: str) -> None:
        self.technical_failure = True
        if reason and reason not in self.failure_reasons:
            self.failure_reasons.append(reason)

    def reserve_stages(self, allocations: dict[str, dict]) -> None:
        """Reserviert Ausgabe- und Websuchbudget je Modellstufe.

        Die zweite Stufe (Self-Review bzw. Verifier) erhaelt dadurch ihren
        Anteil unabhaengig davon, wie viel die erste Stufe tatsaechlich
        verbraucht hat. SAS-2 und MAS verwenden dieselbe Aufteilung.
        """
        total_output = sum(int(item.get("max_output_tokens") or 0)
                           for item in allocations.values())
        total_web = sum(int(item.get("max_tool_calls") or 0)
                        for item in allocations.values())
        if (total_output > self.limits.max_output_tokens
                or total_web > self.limits.max_web_calls):
            raise ValueError("Stufenreservierung uebersteigt das Armbudget.")
        with self._lock:
            self.stage_allocations = {
                str(stage): {
                    "max_output_tokens": int(item.get("max_output_tokens") or 0),
                    "max_tool_calls": int(item.get("max_tool_calls") or 0),
                } for stage, item in allocations.items()}
            self.stage_usage = {stage: {"output_tokens": 0, "web_calls": 0,
                                        "model_calls": 0}
                                for stage in self.stage_allocations}

    def _deviation(self, reason: str) -> None:
        if reason and reason not in self.protocol_deviations:
            self.protocol_deviations.append(reason)

    def authorize_model_call(self, *, estimated_input_tokens: int,
                             max_output_tokens: int,
                             max_web_calls: int,
                             model: str = "",
                             purpose: str = "") -> tuple[bool, str]:
        with self._lock:
            if self.technical_failure:
                return False, "prior_resource_failure"
            model = str(model or Config.MODEL)
            if model not in Config.PRICES:
                self._fail("unknown_model_price")
                return False, "unknown_model_price"
            price_in, price_out = Config.PRICES[model]
            projected_cost = (
                self.cost_usd
                + max(0, int(estimated_input_tokens)) / 1e6 * price_in
                + max(0, int(max_output_tokens)) / 1e6 * price_out
                + max(0, int(max_web_calls)) * Config.WEB_SEARCH_PRICE
            )
            stage = stage_for_purpose(purpose)
            allocation = self.stage_allocations.get(stage)
            if allocation is not None:
                used = self.stage_usage[stage]
                output_check = (
                    used["output_tokens"] + max_output_tokens
                    <= allocation["max_output_tokens"],
                    f"{stage}_output_token_budget_exhausted")
                web_check = (
                    used["web_calls"] + max_web_calls
                    <= allocation["max_tool_calls"],
                    f"{stage}_web_call_budget_exhausted")
            else:
                output_check = (
                    self.output_tokens + max_output_tokens
                    <= self.limits.max_output_tokens,
                    "output_token_budget_exhausted")
                web_check = (
                    self.web_calls + max_web_calls <= self.limits.max_web_calls,
                    "web_call_budget_exhausted")
            checks = (
                (self.model_calls + 1 <= self.limits.max_model_calls,
                 "model_call_budget_exhausted"),
                (self.input_tokens + estimated_input_tokens <=
                 self.limits.max_input_tokens, "input_token_budget_exhausted"),
                output_check,
                web_check,
                (projected_cost <= self.limits.max_cost_usd,
                 "projected_cost_budget_exhausted"),
            )
            for allowed, reason in checks:
                if not allowed:
                    self._fail(reason)
                    return False, reason
            return True, ""

    def record_model_usage(self, record: dict, latency_ms: float = 0.0) -> None:
        with self._lock:
            self.model_calls += 1
            self.input_tokens += int(record.get("input_tokens") or 0)
            self.cached_input_tokens += int(record.get("cached_input_tokens") or 0)
            self.output_tokens += int(record.get("output_tokens") or 0)
            self.reasoning_tokens += int(record.get("reasoning_tokens") or 0)
            self.web_calls += int(record.get("tool_calls") or 0)
            self.model_latency_ms += float(latency_ms or 0.0)
            model = record.get("model_returned") or record.get("model_requested") or ""
            requested_model = str(record.get("model_requested") or "")
            price_model = model if model in Config.PRICES else requested_model
            if price_model not in Config.PRICES:
                self._fail("unknown_model_price")
                pin, pout = 0.0, 0.0
            else:
                pin, pout = Config.PRICES[price_model]
            self.cost_usd += (
                int(record.get("input_tokens") or 0) / 1e6 * pin
                + int(record.get("output_tokens") or 0) / 1e6 * pout
                + int(record.get("tool_calls") or 0) * Config.WEB_SEARCH_PRICE
            )
            if str(record.get("status") or "") != "completed":
                self._fail("model_technical_failure")
            requested = requested_model
            returned = str(record.get("model_returned") or requested)
            if requested and returned and requested != returned:
                self._fail("model_identity_mismatch")
            if self.input_tokens > self.limits.max_input_tokens:
                self._fail("input_token_budget_exceeded")
            if self.output_tokens > self.limits.max_output_tokens:
                self._fail("output_token_budget_exceeded")
            if self.reasoning_tokens > self.limits.max_reasoning_tokens:
                self._fail("reasoning_token_budget_exceeded")
            stage = stage_for_purpose(record.get("purpose", ""))
            if stage in self.stage_usage:
                usage = self.stage_usage[stage]
                usage["output_tokens"] += int(record.get("output_tokens") or 0)
                usage["web_calls"] += int(record.get("tool_calls") or 0)
                usage["model_calls"] += 1
                if (usage["web_calls"]
                        > self.stage_allocations[stage]["max_tool_calls"]):
                    if Config.EVAL_WEB_OVERRUN_POLICY == "fail":
                        self._fail(f"{stage}_web_call_budget_exceeded")
                    else:
                        self._deviation(f"provider_tool_overrun:{stage}")
            if self.web_calls > self.limits.max_web_calls:
                if (self.stage_allocations
                        and Config.EVAL_WEB_OVERRUN_POLICY != "fail"):
                    self._deviation("provider_tool_overrun:arm_total")
                else:
                    self._fail("web_call_budget_exceeded")
            if self.cost_usd > self.limits.max_cost_usd:
                self._fail("cost_budget_exceeded")

    def begin_resolver_fetch(self) -> tuple[bool, str]:
        with self._lock:
            if self.resolver_fetches >= self.limits.max_resolver_fetches:
                # Das Erreichen einer vorab festgelegten Obergrenze ist kein
                # technischer Fehler. Nicht mehr gepruefte Quellen werden vom
                # Resolver explizit als ``not_checked_budget`` ausgewiesen und
                # duerfen weder als fachliche Enthaltung noch als Providerfehler
                # in die Auswertung eingehen.
                return False, "resolver_fetch_budget_exhausted"
            self.resolver_fetches += 1
            return True, ""

    def remaining_resolver_fetches(self) -> int:
        """Noch zulaessige direkte Dokumentabrufe dieses Arms."""
        with self._lock:
            return max(0, int(self.limits.max_resolver_fetches)
                       - int(self.resolver_fetches))

    def record_resolver_latency(self, latency_ms: float) -> None:
        with self._lock:
            self.resolver_latency_ms += float(latency_ms or 0.0)

    def mark_failure(self, reason: str) -> None:
        with self._lock:
            self._fail(reason)

    def summary(self) -> dict:
        with self._lock:
            elapsed = round((time.perf_counter() - self.started) * 1000, 3)
            return {
                "limits": asdict(self.limits),
                "input_tokens": self.input_tokens,
                "cached_input_tokens": self.cached_input_tokens,
                "output_tokens": self.output_tokens,
                "reasoning_tokens": self.reasoning_tokens,
                "web_calls": self.web_calls,
                "model_calls": self.model_calls,
                "resolver_fetches": self.resolver_fetches,
                "resolver_budget_exhausted": (
                    self.resolver_fetches >= self.limits.max_resolver_fetches),
                "cost_usd": round(self.cost_usd, 6),
                "model_latency_ms": round(self.model_latency_ms, 3),
                "resolver_latency_ms": round(self.resolver_latency_ms, 3),
                "wall_latency_ms": elapsed,
                "technical_failure": self.technical_failure,
                "failure_reasons": list(self.failure_reasons),
                "stage_allocations": {key: dict(value) for key, value
                                      in self.stage_allocations.items()},
                "stage_usage": {key: dict(value) for key, value
                                in self.stage_usage.items()},
                "protocol_deviations": list(self.protocol_deviations),
                "web_overrun_policy": Config.EVAL_WEB_OVERRUN_POLICY,
            }
