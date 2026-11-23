"""Absicherungen vor dem bezahlten Hauptlauf (Pruefrunde 06.11.2026)."""
import argparse
import io
import json
import socket
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

import compare_architectures
import core
import evidence_resolver
from compare_architectures import ExperimentBudget, PairedArchitectureRunner
from core import Config, LLMClient, Source
from evaluation_analysis import _itt_block

from tests.test_variante_a import _arm, _candidate, _plan_files  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_study  # noqa: E402


def test_code_fingerprint_covers_every_local_module_of_the_study_run():
    # Frischer Prozess: genau die Module, die ein Studienlauf laedt (inkl. des
    # erst bei Claude geladenen Adapters).
    probe = (
        "import sys, runpy, pathlib\n"
        "root = pathlib.Path(sys.argv[1])\n"
        "sys.path.insert(0, str(root)); sys.argv = ['run_study.py', 'status', '--plan', 'x']\n"
        "import importlib.util\n"
        "spec = importlib.util.spec_from_file_location('rs', root / 'scripts' / 'run_study.py')\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "import llm_anthropic\n"
        "names = sorted({pathlib.Path(mod.__file__).name for mod in list(sys.modules.values())\n"
        "    if getattr(mod, '__file__', None) and pathlib.Path(mod.__file__).resolve().parent == root})\n"
        "print(' '.join(names))\n")
    output = subprocess.run([sys.executable, "-c", probe, str(ROOT)], capture_output=True,
                            text=True, check=True).stdout.split()
    assert output, "keine Module gefunden"
    assert not set(output) - set(run_study.CODE_FILES)
    for name in run_study.CODE_FILES:
        assert (ROOT / name).is_file(), name


def test_plan_freezes_runtime_values_and_run_refuses_drift(tmp_path, monkeypatch):
    args = _plan_files(tmp_path)
    protocol = tmp_path / "protokoll.md"
    protocol.write_text("Bewertungsprotokoll v1", encoding="utf-8")
    args.protocol_file = str(protocol)
    assert run_study.make_plan(args) == 0
    plan = run_study.load_plan(tmp_path / "plan.json")
    assert plan["rating_protocol"]["name"] == "protokoll.md"
    assert len(plan["rating_protocol"]["sha256"]) == 64
    assert plan["effective_config"]["budget"]["max_cost_usd"] == Config.EVAL_MAX_COST_USD
    run_args = argparse.Namespace(plan=str(tmp_path / "plan.json"), role="primary",
                                  max_total_usd=0.0, confirm_paid=False)
    assert run_study.run_phase(run_args) == 0
    # Eine geaenderte Umgebungsvariable (etwa in .env) aendert den Abgleich.
    monkeypatch.setattr(Config, "EXCERPT_MATCH_MODE", "exact")
    assert run_study.run_phase(run_args) == 2
    monkeypatch.setattr(Config, "EXCERPT_MATCH_MODE", plan["effective_config"]["excerpt_match_mode"])
    monkeypatch.setattr(Config, "REASONING_EFFORT", "high")
    assert run_study.run_phase(run_args) == 2


def test_interrupted_pair_is_rerun_once_and_stays_booked(tmp_path, monkeypatch):
    args = _plan_files(tmp_path)
    args.stability = 0
    # v14: Paar-Hoechstkosten inkl. Nachrecherche 2,00 USD; Deckel so, dass genau
    # ein Neustart passt und danach der Kostenstopp greift.
    args.max_total_usd = 5.0  # 2 Abbruch + 2 Neustart + 0,50 Aufschlag; danach Stopp
    run_study.make_plan(args)
    state = {"fail": True, "calls": 0}

    class StubRunner:
        def __init__(self, live=False, memory_records=None):
            self.budget = ExperimentBudget()

        def run_pair(self, task, planned_assignment=None):
            state["calls"] += 1
            if state["fail"]:
                state["fail"] = False
                raise KeyboardInterrupt  # Strg+C oder Ruhezustand mitten im Paar
            pair_id = planned_assignment["execution_id"].replace("exec-", "pair-", 1)
            return {"pair_id": pair_id, "task": task.public_input(strict=True).canonical_dict(),
                    "order": planned_assignment["order"],
                    "arms": [_arm("sas2", "arm-x", [_candidate("z", "Zeta")]),
                             _arm("mas", "arm-y", [])]}

    monkeypatch.setenv("SCOUTREF_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    monkeypatch.setattr(run_study, "PairedArchitectureRunner", StubRunner)
    run_args = argparse.Namespace(plan=str(tmp_path / "plan.json"), role="primary",
                                  max_total_usd=0.0, confirm_paid=True)
    with pytest.raises(KeyboardInterrupt):
        run_study.run_phase(run_args)
    plan = run_study.load_plan(tmp_path / "plan.json")
    ledger_file = run_study.ledger_path(tmp_path / "plan.json", plan)
    ledger = run_study.load_ledger(ledger_file)
    first = next(iter(ledger["entries"]))
    assert ledger["entries"][first]["status"] == "started"
    assert not list(tmp_path.glob(".lauf-*.lock"))  # Sperre wieder frei
    # Fortsetzen: dasselbe Paar wird einmal neu gestartet, der Abbruch bleibt verbucht.
    assert run_study.run_phase(run_args) == 3  # Kostenstopp greift danach
    ledger = run_study.load_ledger(ledger_file)
    entry = ledger["entries"][first]
    assert entry["status"] == "done" and entry["attempt"] == 2
    assert len(entry["aborted_attempts"]) == 1
    assert run_study.spent(ledger, plan) == pytest.approx(0.8 + plan["max_pair_cost_usd"])
    record = json.loads((tmp_path / "runs" / f"{entry['run_id']}.json").read_text(encoding="utf-8"))
    assert record["study"]["attempt"] == 2
    # Ein zweiter Abbruch desselben Paars wird nicht ein drittes Mal gestartet.
    ledger = {"entries": {item["entry_id"]: {"status": "done", "cost_usd": 0.0}
                          for item in plan["pairs"]}}
    victim = plan["pairs"][0]["entry_id"]
    ledger["entries"][victim] = {"status": "started", "attempt": 2,
                                 "aborted_attempts": [{"attempt": 1}]}
    run_study.save_ledger(ledger_file, ledger)
    state["calls"] = 0
    for model in plan["models"]:
        monkeypatch.setattr(run_study.Config, "MODEL", model)
        assert run_study.run_phase(run_args) == 0
    assert state["calls"] == 0
    assert run_study.spent(run_study.load_ledger(ledger_file), plan) == pytest.approx(
        2 * plan["max_pair_cost_usd"])


def _fake_pipeline(decisions, discovery_status):
    class FakeStore:
        @staticmethod
        def snapshot_id():
            return "mem-test"

    class FakeLLM:
        @staticmethod
        def usage_ledger():
            return []

    class FakeResolver:
        cache = {}

    class FakePipeline:
        llm = FakeLLM()
        memory = type("M", (), {"store": FakeStore()})()
        resolver = FakeResolver()
        audit_write = False

        def discover(self, *args, **kwargs):
            return list(range(len(decisions))), {"status": discovery_status, "output": {}}

        def scout(self, candidate, **kwargs):
            data = decisions[candidate]
            return type("D", (), {"to_dict": staticmethod(lambda: dict(data))})()

    return FakePipeline()


def test_recommendation_survives_unchecked_sources_of_another_candidate(monkeypatch):
    runner = PairedArchitectureRunner()
    decisions = [
        {"evaluation_status": "completed", "decision_state": "empfehlung",
         "candidate": {"candidate_id": "gut"}},
        {"evaluation_status": "not_checked_budget", "decision_state": "technischer_fehler",
         "candidate": {"candidate_id": "rest"}},
    ]
    monkeypatch.setattr(runner, "_pipeline", lambda broker: _fake_pipeline(
        decisions, "not_checked_budget"))
    monkeypatch.setattr(runner, "_sensitivities", lambda *a, **k: {})
    task = compare_architectures.ComparisonTask(
        task_id="t", organization_name="Firma",
        search_prompt="Suche ein reales B2B-Startup fuer einen belegten Prozess.")
    task_input = task.public_input(strict=False)
    arm = runner._run_arm(task, "mas", False, True, "pair-1", task_input, {})
    assert arm["result_status"] == "completed"
    assert arm["primary_analysis_eligible"] is True
    assert "resolver_budget_partial" in arm["protocol_deviations"]
    assert arm["positive_candidate_ids"] == ["gut"]
    # Ohne Empfehlung bleibt es beim Budgetstatus.
    monkeypatch.setattr(runner, "_pipeline", lambda broker: _fake_pipeline(
        decisions[1:], "not_checked_budget"))
    arm = runner._run_arm(task, "sas2", False, True, "pair-1", task_input, {})
    assert arm["result_status"] == "not_checked_budget"
    assert PairedArchitectureRunner._status_from_decisions(decisions, False) == "completed"


def test_strict_budget_sensitivity_counts_partial_arm_as_zero():
    base = {"task_id": "t1", "result_status": "completed", "primary_analysis_eligible": True,
            "positive_candidate_ids": ("c1",), "protocol_deviations": ("resolver_budget_partial",),
            "sensitivity_positive_ids": {}, "study_role": "primary", "model": "m", "stratum": ""}
    assignments = {("p1", "a"): {**base, "architecture": "mas"},
                   ("p1", "b"): {**base, "architecture": "sas2", "positive_candidate_ids": (),
                                 "protocol_deviations": ()}}
    by_arm = {("t1", "p1", "mas"): [{"candidate_id": "c1", "candidate_rank": 1,
                                     "qualified": True}],
              ("t1", "p1", "sas2"): []}
    assert _itt_block(assignments, by_arm)["mean_success"]["mas"] == 1.0
    assert _itt_block(assignments, by_arm, variant="strict_budget")["mean_success"]["mas"] == 0.0


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _ok_payload():
    return json.dumps({"id": "r1", "status": "completed", "model": "gpt-6.1-sol",
                       "output": [], "usage": {"input_tokens": 10, "output_tokens": 5}}).encode()


def test_openai_path_retries_overload_but_not_timeout(monkeypatch):
    client = LLMClient(live=True)
    client.api_key = "test"
    monkeypatch.setattr(client, "available", lambda: True)
    monkeypatch.setattr(core, "_sleep", lambda seconds: None)
    calls = []

    def flaky(request, timeout=None, context=None):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError(request.full_url, 503, "busy", {}, None)
        return _Response(_ok_payload())

    monkeypatch.setattr(core.urllib.request, "urlopen", flaky)
    client.complete(model="gpt-6.1-sol", system="s", user="u", purpose="sas2_research")
    assert len(calls) == 2 and client.last_usage["status"] == "completed"
    assert client.last_usage["transport_retries"] == 1

    calls.clear()

    def timeout(request, timeout=None, context=None):
        calls.append(1)
        raise TimeoutError("timed out")

    monkeypatch.setattr(core.urllib.request, "urlopen", timeout)
    client.complete(model="gpt-6.1-sol", system="s", user="u", purpose="sas2_research")
    assert len(calls) == 1 and client.last_usage["status"] == "technical_failure"

    calls.clear()

    def always_busy(request, timeout=None, context=None):
        calls.append(1)
        raise urllib.error.HTTPError(request.full_url, 429, "rate", {"Retry-After": "2"}, None)

    monkeypatch.setattr(core.urllib.request, "urlopen", always_busy)
    client.complete(model="gpt-6.1-sol", system="s", user="u", purpose="sas2_research")
    assert len(calls) == 3 and client.last_usage["status"] == "technical_failure"
    assert core._transient_retry_delay(
        urllib.error.URLError(socket.timeout("timed out")), 0) is None
    assert core._transient_retry_delay(
        urllib.error.HTTPError("u", 400, "bad", {}, None), 0) is None


def test_matched_context_records_the_found_passage():
    text = ("Willkommen. " + "Fuellwort " * 200 + "Unsere Anlage trocknet Schleifschlamm "
            "aus der Natursteinbearbeitung mit Abwaerme. " + "Ende " * 200)
    exact = evidence_resolver.matched_context(
        "Unsere Anlage trocknet Schleifschlamm aus der Natursteinbearbeitung mit Abwaerme.", text)
    assert "schleifschlamm aus der natursteinbearbeitung" in exact and len(exact) <= 600
    fuzzy = evidence_resolver.matched_context(
        "Unsere Anlage trocknet den Schleifschlamm aus Natursteinbearbeitung mit Abwaerme", text)
    assert "schleifschlamm" in fuzzy
    assert evidence_resolver.matched_context("Nicht vorhanden irgendwo hier", "") == ""
    assert "matched_context" in Source.__dataclass_fields__


def test_resolver_stores_context_only_for_found_excerpts(monkeypatch):
    resolver = evidence_resolver.EvidenceResolver()
    page = ("Die Firma Beta GmbH entwickelt Sensoren fuer die Ueberwachung von "
            "Trocknungsanlagen in der Industrie und bietet sie seit 2022 an.")
    monkeypatch.setattr(resolver, "_fetch", lambda url: {
        "status": "resolved", "text": page, "resolved_url": url, "http_status": 200})
    source = Source(url="https://beta.example", citation_verified=True,
                    excerpt="Die Firma Beta GmbH entwickelt Sensoren fuer die Ueberwachung "
                            "von Trocknungsanlagen")
    resolver.resolve_source(source)
    assert source.excerpt_verified and "beta gmbh entwickelt sensoren" in source.matched_context
    missing = Source(url="https://beta.example", citation_verified=True,
                     excerpt="Ein ganz anderer Satz, der auf dieser Seite nicht steht.")
    monkeypatch.setattr(resolver, "_subpage_match", lambda url, excerpt: "")
    resolver.resolve_source(missing)
    assert not missing.excerpt_verified and missing.matched_context == ""


def test_replicated_plan_alternates_order_within_each_task_and_model(tmp_path):
    args = _plan_files(tmp_path)
    args.replicates, args.stability, args.modes = 2, 0, "push"
    assert run_study.make_plan(args) == 0
    plan = run_study.load_plan(tmp_path / "plan.json")
    orders = {}
    for item in plan["pairs"]:
        orders.setdefault((item["task_key"], item["model"]), set()).add(tuple(item["order"]))
    assert orders and all(value == {("sas2", "mas"), ("mas", "sas2")} for value in orders.values())
    assert len({item["entry_id"] for item in plan["pairs"]}) == len(plan["pairs"])


def test_plan_refuses_budget_that_differs_from_the_thesis_profile(tmp_path, monkeypatch):
    args = _plan_files(tmp_path)
    monkeypatch.setattr(run_study, "ExperimentBudget",
                        lambda: ExperimentBudget(max_input_tokens=160_000))
    assert run_study.main.__call__  # main faengt ValueError ab; hier direkt pruefen
    with pytest.raises(ValueError):
        run_study.make_plan(args)
