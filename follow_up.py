"""M2 (12.11.2026): gezielte Nachrecherche fuer Beinahe-Treffer.

Fester dritter Schritt in BEIDEN Armen, nach der Pruefstufe und der
deterministischen Belegpruefung. Er laeuft nur fuer Kandidaten mit
Evidenzindex >= Config.FOLLOW_UP_MIN_INDEX, hoechstens
Config.FOLLOW_UP_MAX_OPEN_DIMENSIONS offenen Dimensionen (ohne Kettenschluss),
ohne Gegenbeleg und ohne Ausschluss. Er fragt nur nach den offenen Dimensionen.

Gleichbehandlung: Der Aufruf nutzt die Pruefrolle des jeweiligen Arms
(SAS-2: Fortsetzung der eigenen Pruefung; MAS: getrennte Verifikationsrolle),
denselben Regeltext, dieselbe Eingabe und dieselbe feste Budgetreserve.

Die Nachrecherche ergaenzt nur Aussagen und Quellen. Sie ueberschreibt weder
das Urteil der Pruefstufe noch bestehende Aussagen. Neue Quellen zaehlen nur,
wenn die Websuche sie als tatsaechlich verwendete Quelle ausweist und der
wortgleiche Auszug auf der abgerufenen Seite steht (dieselbe Belegpruefung wie
vorher). Danach laufen Belegpruefung und Entscheidung unveraendert erneut.
"""
from __future__ import annotations

import hashlib
import json

from core import Config, Source
from evidence_resolver import is_blocked_source
from review_contract import (MAS_REVIEW_ROLE, REVIEW_ROLE_COMMON, SAS_REVIEW_ROLE,
                             _rebind_subjects)

# Reihenfolge = Vorrang (Zielprozess, Input, Ergebnis, Gruendung, dann der Rest).
PRIORITY = ("target_process", "input_stream", "output_application", "startup_status",
            "transformation", "startup_capability", "identity")
TARGET_FIELDS = {"target_process", "input_stream", "target_identity"}
FIELDS = {"target_process", "input_stream", "input_stream_mechanism", "startup_capability",
          "transformation", "output_application", "startup_status", "identity"}
DIMENSION_TEXT = {
    "target_process": "Zielprozess: welcher konkrete Prozessschritt der Zielorganisation ist oeffentlich belegt",
    "input_stream": "Input: welche Art Material, Daten oder Ressource faellt in diesem Prozess an, und welche Art Input verarbeitet das Produkt laut Startup-Quelle (field input_stream bzw. input_stream_mechanism)",
    "output_application": "Ergebnis: welches nutzbare Ergebnis erzeugt das Produkt laut Startup-Quelle",
    "startup_status": "Gruendung: Gruendungsjahr mit Quelle (eigene Website, Impressum, freies Register, Presse)",
    "transformation": "Wirkung: wie veraendert das Produkt den Prozess laut Startup-Quelle",
    "startup_capability": "Faehigkeit: was das Produkt laut eigener Quelle des Startups leistet",
    "identity": "Identitaet: offizielle Website und Impressum des Startups",
}

FOLLOW_UP_SPEC = (
    "\nNACHRECHERCHE (v14, fester Schritt, fuer beide Architekturen identisch): "
    "Fuer die uebergebenen Kandidaten sind nur die genannten Dimensionen noch offen. "
    "Suche gezielt und nur dafuer, mit hoechstens drei Websuchen, nach oeffentlichen "
    "Belegen. Vorrang in dieser Reihenfolge: Zielprozess, Input, Ergebnis, Gruendung. "
    "Zitiere nur URLs, die in deinen Suchergebnissen vorkamen, und nur woertlich "
    "kopierte, zusammenhaengende Saetze der Quelle (mindestens acht Woerter, keine "
    "aus Tabellenzellen oder Satzteilen zusammengesetzten Auszuege, keine "
    "Auslassungszeichen). WORTLAUT-HILFE (v15): Unter wortlaut_hilfe steht zu "
    "Aussagen, deren Auszug nicht wortgleich auf der Seite stand, der aehnlichste "
    "Abschnitt der abgerufenen Seite. Zitiere daraus woertlich oder verwirf die "
    "Aussage; gib dann die URL dieser Seite als Quelle an. "
    "Findest du fuer eine Dimension keinen Beleg, liefere dafuer "
    "nichts. Erfinde nichts. Bewerte keinen Kandidaten neu und aendere keine "
    "bestehende Aussage. Antworte NUR mit einem JSON-Array, ohne Text davor oder "
    "danach und ohne Markdown-Zaeune, genau ein Eintrag je Kandidat: "
    "{\"candidate_id\": str (unveraendert), \"founded\": int|null, "
    "\"claims\": [{\"field\": \"target_process|input_stream|input_stream_mechanism|"
    "startup_capability|transformation|output_application|startup_status|identity\", "
    "\"claim_text\": str, \"source_id\": str, \"excerpt\": str}], "
    "\"sources\": [{\"source_id\": str, \"url\": str, \"title\": str, "
    "\"source_type\": \"official|register|press|database|public_body|social\", "
    "\"subject_type\": \"target_organization|candidate_startup|relation\", "
    "\"subject_name\": str, \"excerpt\": str}]}."
)


def follow_up_system(architecture: str) -> str:
    from agents import SEARCH_EVIDENCE_RULES
    role = SAS_REVIEW_ROLE if architecture == "sas2" else MAS_REVIEW_ROLE
    return role + REVIEW_ROLE_COMMON + FOLLOW_UP_SPEC + SEARCH_EVIDENCE_RULES


def open_dimensions(decision: dict) -> list[str]:
    matrix = (decision.get("candidate") or {}).get("evidence_matrix") or {}
    blocking = [d for d in matrix.get("blocking_dimensions") or [] if d != "relational_chain"]
    return sorted(blocking, key=lambda d: PRIORITY.index(d) if d in PRIORITY else 99)


def qualifies(decision: dict) -> tuple[bool, str]:
    candidate = decision.get("candidate") or {}
    matrix = candidate.get("evidence_matrix") or {}
    if decision.get("decision_state") != "enthaltung":
        return False, f"Zustand {decision.get('decision_state')}"
    if matrix.get("contradictions"):
        return False, "Gegenbeleg"
    if any(str(r).startswith("Ausschluss: ") for r in candidate.get("verification_reasons") or []):
        return False, "Ausschluss"
    if int(decision.get("best_score") or 0) < Config.FOLLOW_UP_MIN_INDEX:
        return False, "Index unter Schwelle"
    dims = open_dimensions(decision)
    if not dims:
        return False, "keine offene Dimension (nur Tore)"
    if len(dims) > Config.FOLLOW_UP_MAX_OPEN_DIMENSIONS:
        return False, "zu viele offene Dimensionen"
    return True, ""


def follow_up_user(query: str, targets: list[tuple], hints: dict | None = None) -> str:
    items = []
    for candidate, dims in targets:
        item = {
            "candidate_id": candidate.candidate_id, "name": candidate.name,
            "claimed_website": candidate.website or candidate.official_url,
            "target_organization_name": candidate.target_actor_name,
            "open_dimensions": [{"dimension": d, "frage": DIMENSION_TEXT.get(d, d)} for d in dims],
        }
        if (hints or {}).get(candidate.candidate_id):
            item["wortlaut_hilfe"] = hints[candidate.candidate_id]
        items.append(item)
    return ("Suchauftrag:\n" + query + "\n\nOffene Dimensionen je Kandidat:\n"
            + json.dumps(items, ensure_ascii=False))


def _parse(raw: str, expected: set[str]) -> dict[str, dict] | None:
    from agents import ScoutingAgent
    try:
        parsed = ScoutingAgent._strict_array(raw)
    except Exception:  # noqa: BLE001 - Vertragsfehler fuehrt zu "nichts ergaenzt"
        return None
    if not isinstance(parsed, list):
        return None
    out = {}
    for item in parsed:
        if isinstance(item, dict) and str(item.get("candidate_id") or "") in expected:
            out[str(item["candidate_id"])] = item
    return out


def merge(candidate, entry: dict, llm) -> dict:
    """Ergaenzt gepruefte Quellen und Aussagen; nichts wird ersetzt.

    Je uebernommener Aussage entsteht eine Quelle mit genau deren Auszug, damit
    die Belegpruefung den Auszug der Aussage prueft (v15). Eine URL zaehlt nur,
    wenn die Websuche sie in diesem Aufruf ausweist oder sie schon frueher als
    tatsaechlich verwendete Quelle dieses Kandidaten ausgewiesen war.
    """
    report = {"claims_offered": 0, "claims_added": 0, "sources_offered": 0,
              "sources_grounded": 0, "sources_blocked": 0, "founded_set": False}
    existing = {}
    for source in candidate.sources or []:
        existing.setdefault(str(source.url), source)
    normalise = getattr(llm, "_normalise_url", None) or (lambda u: str(u or ""))
    cited = {normalise(item.get("url", "")): item for item in (getattr(llm, "last_citations", None) or [])
             if normalise(item.get("url", ""))} if llm else {}

    def provenance(url: str):
        if normalise(url) in cited:
            return cited[normalise(url)].get("origin", "") or "web_search_source"
        old = existing.get(url)
        if old is not None and getattr(old, "citation_verified", False):
            return getattr(old, "citation_origin", "") or "earlier_web_search_source"
        return None

    offered = {}
    for raw in entry.get("sources") or []:
        if isinstance(raw, dict) and raw.get("url"):
            offered[str(raw.get("source_id") or "")] = raw
    report["sources_offered"] = len(offered)
    for raw in offered.values():
        url = str(raw.get("url")).strip()
        if is_blocked_source(url):
            report["sources_blocked"] += 1
        elif provenance(url):
            report["sources_grounded"] += 1
    by_id = {s.source_id: s for s in candidate.sources or []}
    sources = list(candidate.sources or [])
    claims = list(candidate.evidence_claims or [])
    for raw in entry.get("claims") or []:
        if not isinstance(raw, dict):
            continue
        report["claims_offered"] += 1
        field = str(raw.get("field") or "").strip().lower()
        excerpt = " ".join(str(raw.get("excerpt") or "").split())
        ref = str(raw.get("source_id") or "")
        meta = offered.get(ref) or {}
        url = str(meta.get("url") or getattr(by_id.get(ref), "url", "") or "").strip()
        if field not in FIELDS or len(excerpt) < 20 or not url or is_blocked_source(url):
            continue
        origin = provenance(url)
        if not origin:
            continue
        old = existing.get(url)
        sid = "fu-" + hashlib.sha256(f"{url}|{excerpt}".encode("utf-8")).hexdigest()[:12]
        if not any(s.source_id == sid for s in sources):
            sources.append(Source(
                url=url, title=str(meta.get("title") or getattr(old, "title", "") or ""), source_id=sid,
                source_type=str(meta.get("source_type") or getattr(old, "source_type", "") or "official"),
                publisher=str(meta.get("subject_name") or getattr(old, "publisher", "") or ""),
                subject_type=str(meta.get("subject_type") or getattr(old, "subject_type", "") or "").strip().lower(),
                subject_name=str(meta.get("subject_name") or getattr(old, "subject_name", "") or ""),
                excerpt=excerpt, supports=[], citation_verified=True, citation_origin=origin))
        if field in TARGET_FIELDS:
            subject_type, subject_name = "target_organization", candidate.target_actor_name
        elif field == "input_stream_mechanism":
            # Fachbeleg zur Beziehung Prozess -> Input (kein festes Subjekt).
            subject_type = "relation"
            subject_name = str(meta.get("subject_name") or getattr(old, "subject_name", "") or "")
        else:
            subject_type, subject_name = "candidate_startup", candidate.name
        claims.append({
            "claim_id": "fu-" + hashlib.sha256(f"{field}|{sid}|{excerpt}".encode("utf-8")).hexdigest()[:12],
            "claim_text": " ".join(str(raw.get("claim_text") or excerpt).split()),
            "field": field, "source_id": sid, "excerpt": excerpt, "stance": "support",
            "basis": "derived" if field == "input_stream_mechanism" else "direct",
            "subject_type": subject_type, "subject_name": subject_name,
            "subject_id": "", "origin": "follow_up",
        })
        report["claims_added"] += 1
    candidate.sources = sources
    candidate.evidence_claims = claims
    founded = entry.get("founded")
    if candidate.founded is None and isinstance(founded, int) and 1900 < founded < 2100:
        candidate.founded = founded
        report["founded_set"] = True
    _rebind_subjects(candidate, candidate.sources, candidate.evidence_claims)
    return report


# N2 (12.11.2026): Wortlaut-Hilfe. Fuer Aussagen, deren Seite abgerufen wurde,
# deren Auszug dort aber nicht wortgleich steht, erhaelt die Nachrecherche den
# aehnlichsten Abschnitt des Seitentexts (deterministisch, hoechstens 600 Zeichen).
HINT_MAX_CHARS = 600
HINTS_PER_CANDIDATE = 4


def _words(text: str) -> list[str]:
    from evidence_resolver import _normalise_claim
    return _normalise_claim(text).split()


def similar_section(excerpt: str, text: str, limit: int = HINT_MAX_CHARS) -> str:
    """Aehnlichster Abschnitt: Satz mit dem hoechsten Anteil gemeinsamer Woerter,
    erweitert um Nachbarsaetze bis hoechstens ``limit`` Zeichen."""
    import re
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", str(text or "")) if s.strip()]
    target = set(_words(excerpt))
    if not sentences or not target:
        return ""
    scores = [len(target & set(_words(s))) / len(target) for s in sentences]
    best = max(range(len(sentences)), key=lambda i: (scores[i], -i))
    if scores[best] == 0:
        return ""
    lo = hi = best
    section = sentences[best][:limit]
    while True:
        grown = False
        for nxt in (hi + 1, lo - 1):
            if 0 <= nxt < len(sentences):
                parts = sentences[min(lo, nxt):max(hi, nxt) + 1]
                candidate = " ".join(parts)
                if len(candidate) <= limit:
                    lo, hi, section, grown = min(lo, nxt), max(hi, nxt), candidate, True
        if not grown:
            return section


def wording_hints(candidate, cache: dict) -> list[dict]:
    hints = []
    for source in candidate.sources or []:
        if len(hints) >= HINTS_PER_CANDIDATE:
            break
        if (getattr(source, "resolved_status", "") != "resolved" or getattr(source, "excerpt_verified", False)
                or not str(getattr(source, "excerpt", "") or "").strip() or is_blocked_source(source.url)):
            continue
        page = cache.get(source.url) or {}
        section = similar_section(source.excerpt, page.get("text", ""))
        if section:
            hints.append({"source_id": source.source_id, "url": source.url,
                          "bisheriger_auszug": source.excerpt, "seitenabschnitt": section})
    return hints


def run_follow_up(pipeline, *, architecture: str, query: str, candidates: list,
                  decisions: list[dict], target_actor_id: str, guardrail: bool) -> tuple[list[dict], dict]:
    """Fuehrt die Nachrecherche aus und gibt neue Entscheidungen plus Protokoll zurueck."""
    info = {"enabled": bool(Config.FOLLOW_UP_ENABLED), "triggered": False, "skipped_reason": "",
            "candidates": [], "usage": {}}
    if not Config.FOLLOW_UP_ENABLED:
        info["skipped_reason"] = "abgeschaltet"
        return decisions, info
    targets = []
    for candidate, decision in zip(candidates, decisions):
        ok, reason = qualifies(decision)
        entry = {"candidate_id": candidate.candidate_id, "name": candidate.name,
                 "index_before": decision.get("best_score"),
                 "state_before": decision.get("decision_state"),
                 "open_before": open_dimensions(decision), "qualified": ok, "reason": reason}
        info["candidates"].append(entry)
        if ok:
            targets.append((candidate, entry["open_before"]))
    llm = getattr(pipeline, "llm", None)
    if not targets:
        info["skipped_reason"] = "kein Beinahe-Treffer"
        return decisions, info
    if not (llm and llm.available()):
        info["skipped_reason"] = "kein Live-Modell"
        return decisions, info
    broker = getattr(pipeline, "resource_broker", None)
    if broker is not None:
        limits = broker.limits
        headroom = (
            broker.model_calls + 1 <= limits.max_model_calls
            and broker.input_tokens + Config.FOLLOW_UP_MAX_INPUT_TOKENS <= limits.max_input_tokens
            and broker.reasoning_tokens + Config.FOLLOW_UP_MAX_REASONING_TOKENS <= limits.max_reasoning_tokens
            and broker.cost_usd + Config.FOLLOW_UP_MAX_COST_USD <= limits.max_cost_usd + 1e-9
            and not broker.technical_failure)
        if not headroom:
            # Nie einen Budgetfehler riskieren: ohne volle Reserve kein Aufruf.
            info["skipped_reason"] = "Reserve nicht vollstaendig frei"
            return decisions, info
    info["triggered"] = True
    cache = getattr(getattr(pipeline, "resolver", None), "cache", {}) or {}
    info["wording_hints"] = {c.candidate_id: wording_hints(c, cache) for c, _ in targets}
    raw = llm.complete(
        model=Config.MODEL_VERIFY, system=follow_up_system(architecture),
        user=follow_up_user(query, targets, info["wording_hints"]), tools=[{"type": "web_search"}],
        max_tokens=Config.FOLLOW_UP_MAX_OUTPUT_TOKENS,
        max_tool_calls=Config.FOLLOW_UP_MAX_TOOL_CALLS,
        purpose=f"follow_up_{architecture}")
    usage = dict(llm.last_usage or {})
    info["usage"] = {k: usage.get(k) for k in ("status", "input_tokens", "output_tokens",
                                               "reasoning_tokens", "tool_calls", "purpose")}
    info["search_log"] = usage.get("search_log") or []
    info["raw_text"] = raw or ""
    if str(usage.get("status") or "") != "completed":
        info["skipped_reason"] = "Modellaufruf nicht abgeschlossen"
        return decisions, info
    parsed = _parse(raw, {c.candidate_id for c, _ in targets})
    if parsed is None:
        info["skipped_reason"] = "Antwort ausserhalb des Vertrags"
        return decisions, info
    touched = []
    for candidate, _ in targets:
        entry = parsed.get(candidate.candidate_id)
        record = next(e for e in info["candidates"] if e["candidate_id"] == candidate.candidate_id)
        record["merge"] = merge(candidate, entry, llm) if entry else {"claims_added": 0}
        candidate.model_usage = list(getattr(candidate, "model_usage", []) or []) + [usage]
        touched.append(candidate)
    if touched:
        pipeline.resolver.resolve_candidates(touched, max_fetches_total=Config.FOLLOW_UP_MAX_FETCHES)
    new_decisions = [pipeline.scout(c, use_guardrail=guardrail, use_memory=False,
                                    target_actor_id=target_actor_id).to_dict() for c in candidates]
    for record, decision in zip(info["candidates"], new_decisions):
        record["index_after"] = decision.get("best_score")
        record["state_after"] = decision.get("decision_state")
        record["open_after"] = open_dimensions(decision)
    return new_decisions, info
