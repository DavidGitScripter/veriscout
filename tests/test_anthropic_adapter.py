"""Claude-Anbindung ohne Netzwerk: Vertrag, Quellen, Nutzung, pause_turn."""
import sys
import types
from types import SimpleNamespace as NS

import llm_anthropic


def _install_fake(monkeypatch, responses, seen):
    module = types.ModuleType("anthropic")

    class Anthropic:
        def __init__(self, **kwargs):
            seen["client"] = kwargs
            self.messages = self

        def create(self, **params):
            seen.setdefault("calls", []).append(params)
            return responses.pop(0)

    module.Anthropic = Anthropic
    monkeypatch.setitem(sys.modules, "anthropic", module)


def _usage(inp, out, searches):
    return NS(input_tokens=inp, output_tokens=out, cache_creation_input_tokens=0,
              cache_read_input_tokens=0,
              server_tool_use=NS(web_search_requests=searches))


def test_adapter_maps_text_citations_usage_and_resumes_pause_turn(monkeypatch):
    first = NS(id="m1", model="claude-sonnet-5-5", stop_reason="pause_turn",
               usage=_usage(1000, 50, 2),
               content=[NS(type="web_search_tool_result", content=[
                   NS(url="https://a.example.org/x", title="A")])])
    second = NS(id="m2", model="claude-sonnet-5-5", stop_reason="end_turn",
                usage=_usage(2000, 300, 1),
                content=[NS(type="text", text="[]", citations=[
                    NS(url="https://b.example.org/y", title="B")])])
    seen = {}
    _install_fake(monkeypatch, [first, second], seen)
    result = llm_anthropic.complete(
        api_key="test", model="claude-sonnet-5-5", system="s", user="u",
        max_tokens=8000, effort="low", tool_budget=4, use_web=True, timeout=10)
    assert seen["client"]["base_url"] == "https://api.anthropic.com"
    assert seen["calls"][0]["tools"][0]["max_uses"] == 4
    assert "fallbacks" not in seen["calls"][0]
    assert len(seen["calls"]) == 2
    assert result["text"] == "[]" and result["status"] == "completed"
    assert result["input_tokens"] == 3000 and result["output_tokens"] == 350
    assert result["tool_calls"] == 3
    assert {c["url"] for c in result["citations"]} == {
        "https://a.example.org/x", "https://b.example.org/y"}


def test_truncated_or_refused_answer_is_not_completed(monkeypatch):
    for reason in ("max_tokens", "refusal"):
        response = NS(id="m", model="claude-sonnet-5-5", stop_reason=reason,
                      usage=_usage(10, 10, 0), content=[NS(type="text", text="[", citations=None)])
        _install_fake(monkeypatch, [response], {})
        result = llm_anthropic.complete(
            api_key="t", model="claude-sonnet-5-5", system="s", user="u",
            max_tokens=10, effort="low", tool_budget=0, use_web=False, timeout=5)
        assert result["status"] == "incomplete"
        assert result["incomplete_reason"] == reason


def test_only_text_after_last_tool_block_is_the_answer(monkeypatch):
    response = NS(id="m", model="claude-sonnet-5-5", stop_reason="end_turn",
                  usage=_usage(10, 10, 1), content=[
                      NS(type="text", text="Jetzt suchen.", citations=None),
                      NS(type="server_tool_use"),
                      NS(type="web_search_tool_result", content=[]),
                      NS(type="text", text="Result is a string.", citations=None),
                      NS(type="code_execution_tool_result"),
                      NS(type="text", text="[]", citations=None)])
    _install_fake(monkeypatch, [response], {})
    result = llm_anthropic.complete(
        api_key="t", model="claude-sonnet-5-5", system="s", user="u",
        max_tokens=10, effort="low", tool_budget=2, use_web=True, timeout=5)
    assert result["text"] == "[]"


def test_search_queries_and_results_are_logged_without_changing_request(monkeypatch):
    response = NS(id="m", model="claude-sonnet-5-5", stop_reason="end_turn", usage=_usage(10, 10, 1),
                  content=[NS(type="server_tool_use", name="web_search", id="srv_1",
                              input={"query": "Baufritz Holzbau Startup"}),
                           NS(type="web_search_tool_result", tool_use_id="srv_1",
                              content=[NS(url="https://a.example.org", title="A")]),
                           NS(type="text", text="[]", citations=None)])
    seen = {}
    _install_fake(monkeypatch, [response], seen)
    result = llm_anthropic.complete(
        api_key="t", model="claude-sonnet-5-5", system="s", user="u",
        max_tokens=100, effort="low", tool_budget=2, use_web=True, timeout=5)
    assert result["search_log"] == [{"tool_use_id": "srv_1", "input": {"query": "Baufritz Holzbau Startup"},
                                     "results": [{"title": "A", "url": "https://a.example.org"}]}]
    assert set(seen["calls"][0]) == {"model", "max_tokens", "system", "messages", "output_config", "tools"}
    assert result["text"] == "[]"
