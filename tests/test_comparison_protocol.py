from compare_architectures import (ComparisonTask, ExperimentBudget,
                                   PairedArchitectureRunner,
                                   annotation_package, assignment_manifest)
from core import Config, LLMClient, Source
from agents import ScoutingAgent
from baselines import SingleAgentScoutingAgent
from knowledge_base import KnowledgeBase


def test_mas_subbudgets_sum_to_the_same_sas_total_budget():
    budget = ExperimentBudget(
        model=Config.MODEL, max_output_tokens=12001,
        max_tool_calls=9, max_candidates=5)
    allocation = budget.mas_allocation()
    assert sum(item["max_output_tokens"] for item in allocation.values()) == 12001
    assert sum(item["max_tool_calls"] for item in allocation.values()) == 9


def test_offline_pair_uses_same_snapshot_and_has_no_external_actions():
    runner = PairedArchitectureRunner(
        memory_records=[{"actor_id": "demo_manufacturing", "description": "Reststoffe",
                         "label": False, "score": 40, "outcome": "not_useful"}],
        live=False)
    result = runner.run_pair(ComparisonTask(
        task_id="offline-contract", target_actor_id="demo_manufacturing", query="",
        push_mode=True), memory_enabled=True)
    assert {arm["architecture_internal"] for arm in result["arms"]} == {"sas2", "mas"}
    assert len({arm["memory_snapshot"] for arm in result["arms"]}) == 1
    assert all(arm["external_actions_enabled"] is False for arm in result["arms"])
    assert all(arm["budget"] == result["arms"][0]["budget"] for arm in result["arms"])


def test_only_structured_api_sources_are_grounded():
    text, citations, calls = LLMClient._extract_text_and_citations({
        "output": [
            {"type": "web_search_call", "action": {"sources": [
                {"url": "https://real.example.org/startup", "title": "Real"}
            ]}},
            {"type": "message", "content": [{"type": "output_text",
                "text": "[]", "annotations": []}]},
        ]
    })
    client = LLMClient(live=False)
    client.last_citations = citations
    grounded = client.ground_sources([
        Source(url="https://real.example.org/startup"),
        Source(url="https://invented.example.org/startup"),
    ])
    assert text == "[]"
    assert calls == 1
    assert [item.url for item in grounded] == ["https://real.example.org/startup"]
    assert grounded[0].citation_verified is True


def test_requested_live_mas_never_falls_back_without_api_key():
    client = LLMClient(live=False)
    client.requested_live = True
    client.live = False
    client.api_key = ""
    candidates, trace = ScoutingAgent(KnowledgeBase(), client).run(
        "PUSH-Suche", seed_pool=[])
    assert candidates == []
    assert trace["status"] == "error"
    assert trace["output"]["Modus"] == "live"


def test_requested_live_sas_never_falls_back_without_api_key():
    client = LLMClient(live=False)
    client.requested_live = True
    client.live = False
    client.api_key = ""
    candidates, trace = SingleAgentScoutingAgent(
        KnowledgeBase(), client).run("PUSH-Suche", seed_pool=[])
    assert candidates == []
    assert trace["status"] == "error"
    assert trace["output"]["Modus"] == "live"


def test_annotation_export_is_separate_from_architecture_assignment():
    runner = PairedArchitectureRunner(live=False)
    result = runner.run_pair(ComparisonTask(
        task_id="blind-contract", target_actor_id="demo_manufacturing", query="",
        push_mode=True))
    blind = annotation_package(result)
    manifest = assignment_manifest(result)
    assert all("architecture_internal" not in arm for arm in blind["arms"])
    assert all("discovery_trace" not in arm for arm in blind["arms"])
    assert {item["architecture"] for item in manifest["assignments"]} == {"sas2", "mas"}
    assert {arm["blind_arm_id"] for arm in blind["arms"]} == {
        item["blind_arm_id"] for item in manifest["assignments"]
    }


def test_memory_factorial_contains_both_architectures_in_both_memory_states():
    runner = PairedArchitectureRunner(
        memory_records=[{"actor_id": "demo_manufacturing", "description": "Reststoff",
                         "label": True, "score": 70, "outcome": "useful"}],
        live=False)
    result = runner.run_memory_factorial(ComparisonTask(
        task_id="factorial-contract", target_actor_id="demo_manufacturing"))
    assert len(result["cells"]) == 2
    assert {cell["arms"][0]["memory_enabled"] for cell in result["cells"]} == {
        False, True
    }
    assert all({arm["architecture_internal"] for arm in cell["arms"]}
        == {"sas2", "mas"} for cell in result["cells"])
