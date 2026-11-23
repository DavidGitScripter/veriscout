"""Anbindung an Claude (Anthropic Messages API) mit Websuche.

Wird vom gemeinsamen LLMClient genutzt, wenn die konfigurierte Modellkennung
mit ``claude-`` beginnt. Die Rueckgabe entspricht exakt dem Vertrag des
OpenAI-Pfads: Antworttext, ein Nutzungsdatensatz im selben Format und native
Quellenmetadaten des Websuchwerkzeugs. Ressourcenbroker, Resolver,
Evidenzmatrix und Entscheidungsregeln bleiben dadurch fuer beide Anbieter
identisch.

Bewusste Festlegungen fuer den Architekturvergleich:
* Nur das Websuchwerkzeug (``web_search``), kein zusaetzliches Web-Fetch,
  damit die Werkzeugklasse der des OpenAI-Pfads entspricht.
* Keine serverseitigen Fallbacks auf andere Modelle: Die Modellkennung muss
  in beiden Armen fest bleiben. Eine Ablehnung (``refusal``) wird als
  technisch unvollstaendige Antwort protokolliert.
* ``pause_turn`` wird innerhalb desselben logischen Aufrufs fortgesetzt; die
  Nutzung aller Teilanfragen wird summiert und als ein Aufruf gezaehlt.
* Reasoning-Tokens weist die Messages API nicht getrennt aus; sie sind in den
  Ausgabetokens enthalten und werden mit 0 protokolliert.
* Als Antwort zaehlt nur der Text nach dem letzten Werkzeugblock;
  Zwischenkommentare der Websuche werden verworfen.
"""
from __future__ import annotations

ANTHROPIC_API_URL = "https://api.anthropic.com"
API_CONTRACT = "anthropic-messages-v1"
# 12.11.2026 (David): Mit web_search_20260209 sendete Sonnet die Suche wiederholt
# als {"params": {...}} (invalid_tool_input). Beide Sonnet-Arme nutzen daher das
# aeltere Werkzeug; die Version wird je Aufruf protokolliert.
WEB_SEARCH_TOOL_VERSION = "web_search_20250305"
MAX_CONTINUATIONS = 3


def is_anthropic_model(model: str) -> bool:
    return str(model or "").startswith("claude-")


def complete(*, api_key: str, model: str, system: str, user: str,
             max_tokens: int, effort: str, tool_budget: int,
             use_web: bool, timeout: float) -> dict:
    """Fuehrt einen logischen Modellaufruf aus.

    Rueckgabe: {"text", "citations", "status", "incomplete_reason",
    "model_returned", "response_id", "input_tokens", "cached_input_tokens",
    "output_tokens", "tool_calls"}. Netzwerk- und API-Fehler werden als
    Ausnahme an den Aufrufer weitergegeben.
    """
    import anthropic

    # base_url ausdruecklich setzen: Eine gesetzte Umgebungsvariable
    # ANTHROPIC_BASE_URL (z. B. einer Entwicklungsumgebung) darf Studienlaeufe
    # nicht unbemerkt umleiten.
    client = anthropic.Anthropic(api_key=api_key, base_url=ANTHROPIC_API_URL,
                                 timeout=timeout, max_retries=2)
    tools = ([{"type": WEB_SEARCH_TOOL_VERSION, "name": "web_search",
               "max_uses": max(1, int(tool_budget))}]
             if use_web and tool_budget > 0 else [])
    messages = [{"role": "user", "content": user}]
    totals = {"input_tokens": 0, "cached_input_tokens": 0,
              "output_tokens": 0, "tool_calls": 0}
    text_parts: list[str] = []
    citations: list[dict] = []
    # Nur Protokoll: Suchanfragen (Eingabe des Werkzeugs, unveraendert) und
    # Treffer (Titel, URL) je Suche. Beeinflusst weder Anfrage noch Auswertung.
    search_log: list[dict] = []
    search_by_id: dict = {}
    response = None
    for _ in range(MAX_CONTINUATIONS + 1):
        params = {
            "model": model,
            "max_tokens": int(max_tokens),
            "system": system,
            "messages": messages,
            "output_config": {"effort": effort},
        }
        if tools:
            params["tools"] = tools
        response = client.messages.create(**params)
        usage = response.usage
        totals["input_tokens"] += int(
            (usage.input_tokens or 0)
            + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
            + (getattr(usage, "cache_read_input_tokens", 0) or 0))
        totals["cached_input_tokens"] += int(
            getattr(usage, "cache_read_input_tokens", 0) or 0)
        totals["output_tokens"] += int(usage.output_tokens or 0)
        server = getattr(usage, "server_tool_use", None)
        totals["tool_calls"] += int(getattr(server, "web_search_requests", 0) or 0)
        for block in response.content:
            if block.type not in {"text", "thinking", "redacted_thinking"}:
                # Text zwischen Werkzeugaufrufen ist Zwischenkommentar; die
                # Antwort ist nur der Text nach dem letzten Werkzeugblock.
                text_parts = []
            if block.type == "text":
                text_parts.append(block.text)
                for citation in getattr(block, "citations", None) or []:
                    url = getattr(citation, "url", "") or ""
                    if url:
                        citations.append({"url": url,
                                          "title": getattr(citation, "title", "") or "",
                                          "origin": "output_annotation"})
            elif block.type == "server_tool_use" and getattr(block, "name", "") == "web_search":
                entry = {"tool_use_id": getattr(block, "id", ""),
                         "input": dict(getattr(block, "input", None) or {}), "results": []}
                search_log.append(entry)
                search_by_id[entry["tool_use_id"]] = entry
            elif block.type == "web_search_tool_result":
                content = block.content
                entry = search_by_id.get(getattr(block, "tool_use_id", ""))
                if entry is None:
                    entry = {"tool_use_id": getattr(block, "tool_use_id", ""), "input": {}, "results": []}
                    search_log.append(entry)
                if isinstance(content, list):
                    entry["results"].extend(
                        {"title": getattr(item, "title", "") or "", "url": getattr(item, "url", "") or ""}
                        for item in content)
                else:
                    entry["error"] = getattr(content, "error_code", "") or str(type(content).__name__)
                if isinstance(content, list):  # Fehler kommen als Objekt
                    for item in content:
                        url = getattr(item, "url", "") or ""
                        if url:
                            citations.append({"url": url,
                                              "title": getattr(item, "title", "") or "",
                                              "origin": "web_search_source"})
        if response.stop_reason != "pause_turn":
            break
        # Fortsetzung: dieselbe Anfrage mit der pausierten Antwort, ohne neue
        # Nutzernachricht; der Server setzt die Suche fort.
        messages = [{"role": "user", "content": user},
                    {"role": "assistant", "content": response.content}]
        text_parts = []
    stop = getattr(response, "stop_reason", "") or ""
    status = "completed" if stop in {"end_turn", "stop_sequence"} else "incomplete"
    return {
        "text": "".join(text_parts),
        "citations": citations,
        "search_log": search_log,
        "status": status,
        "incomplete_reason": "" if status == "completed" else stop,
        "model_returned": getattr(response, "model", model) or model,
        "response_id": getattr(response, "id", "") or "",
        **totals,
    }
