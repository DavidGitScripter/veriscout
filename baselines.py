"""Single-Agent-Baseline fuer den kontrollierten SAS--MAS-Vergleich."""
from __future__ import annotations

import json
import time
from copy import deepcopy
from dataclasses import asdict

from agents import (SEARCH_EVIDENCE_RULES, ScoutingAgent, _trace,
                    shared_search_user_prompt)
from core import Config
from entity_verifier import EntityVerifier
from evidence_resolver import EvidenceResolver
from review_contract import (REVIEW_OUTPUT_SPEC, REVIEW_ROLE_COMMON,
                             SAS_REVIEW_ROLE, apply_review, fail_closed,
                             parse_review, review_checklist)


class SingleAgentScoutingAgent:
    """Ein Modellaufruf fuer Recherche, Gegenpruefung und Strukturierung.

    Die deterministische Quellenaufloesung, Evidenzmatrix und Policy-Pruefung
    sind bewusst dieselben wie beim MAS. Verglichen wird damit die
    Rollenaufteilung, nicht ein zusaetzliches Kontrollmodul.
    """

    SYSTEM = ScoutingAgent.SYSTEM + (
        "\nDu bist in dieser Baseline die einzige Modellrolle. Fuehre innerhalb "
        "desselben Aufrufs zunaechst eine breite Kandidatensuche und danach eine "
        "skeptische Gegenpruefung durch. Liefere nur Kandidaten, deren Existenz, "
        "Unternehmenstyp, Gruendungsjahr und Produktfaehigkeit durch eine "
        "offizielle und eine unabhaengige Quelle gestuetzt werden. Pruefe die "
        "relationale Kette Zielprozess -> Input -> Transformation -> nutzbarer "
        "Output. Ein unbekanntes Glied bleibt unbekannt; uebernimm keine "
        "Vermutung als Tatsache."
    )

    def __init__(self, kb, llm=None, resolver: EvidenceResolver | None = None):
        self.kb = kb
        self.llm = llm
        self.resolver = resolver or EvidenceResolver()
        self.rules = EntityVerifier()
        self._dry = ScoutingAgent(kb, llm=None)

    def run(self, query: str, n: int = 5, seed_pool: list | None = None,
            max_tokens: int | None = None, max_tool_calls: int | None = None,
            memory_context: dict | None = None,
            defer_resolution: bool = False) -> tuple:
        t0 = time.perf_counter()
        if (self.llm and getattr(self.llm, "requested_live", False)
                and not self.llm.available()):
            reason = (self.llm.live_configuration_error()
                      if hasattr(self.llm, "live_configuration_error") else
                      "Live-Konfiguration unvollstaendig")
            return [], _trace(
                "SingleAgentBaseline", "error",
                reason + "; kein deterministischer Ersatzlauf",
                {"Modus": "live", "Architektur": "SAS", "Treffer": 0,
                 "fehler": [reason]}, t0)
        if not self.llm or not self.llm.available():
            candidates, trace = self._dry.run(query, n=n, seed_pool=seed_pool)
            trace["agent"] = "SingleAgentBaseline"
            trace["info"] += "; deterministischer Offline-Kontrollpfad"
            return deepcopy(candidates), trace

        memory_note = ""
        if memory_context and memory_context.get("retrieved"):
            memory_note = ("\nGleicher eingefrorener Feedback-Snapshot wie im "
                           "Vergleichsarm; keine eigenstaendige Evidenz:\n" +
                           json.dumps(memory_context, ensure_ascii=False))
        raw = self.llm.complete(
            model=Config.MODEL_SAS,
            system=self.SYSTEM,
            user=(f"Suchauftrag:\n{query}\n\nMaximal {n} Kandidaten. "
                  "Ehrlichkeit vor Zielzahl." + memory_note),
            tools=[{"type": "web_search"}],
            max_tokens=(max_tokens or Config.EVAL_TOTAL_MAX_OUTPUT_TOKENS),
            max_tool_calls=(Config.EVAL_TOTAL_MAX_TOOL_CALLS
                            if max_tool_calls is None else max_tool_calls),
            purpose="sas_single_agent",
        )
        completed = str((self.llm.last_usage or {}).get("status") or "") == "completed"
        contract_valid = False
        if completed:
            try:
                contract = ScoutingAgent._strict_array(raw)
                candidates = ScoutingAgent._parse_live(raw)
                contract_valid = (
                    not contract
                    or (len(candidates) == len(contract) and len(contract) <= n))
                if not contract_valid:
                    candidates = []
            except (ValueError, TypeError, json.JSONDecodeError):
                candidates = []
                preamble = ScoutingAgent._empty_array_preamble(raw)
                if preamble is not None:
                    contract_valid = True
                    ScoutingAgent._note_empty_preamble(self.llm, preamble)
        else:
            candidates = []
        for candidate in candidates:
            candidate.sources = self.llm.ground_sources(candidate.sources)
            candidate.model_usage = [dict(self.llm.last_usage or {})]
        if not defer_resolution:
            self.resolver.resolve_candidates(
                candidates,
                max_fetches_total=Config.EVAL_MAX_RESOLVER_FETCHES)
            for candidate in candidates:
                self.rules.verify(candidate)
        verified = sum(candidate.verification_status == "verified_startup"
                       for candidate in candidates)
        output = {
            "Modus": "live",
            "Architektur": "SAS",
            "Treffer": len(candidates),
            "verifiziert": verified,
            "budget": {
                "max_output_tokens": max_tokens or Config.EVAL_TOTAL_MAX_OUTPUT_TOKENS,
                "max_tool_calls": (Config.EVAL_TOTAL_MAX_TOOL_CALLS
                                   if max_tool_calls is None else max_tool_calls),
            },
            "usage": dict(self.llm.last_usage or {}),
            "kosten": self.llm.cost_estimate(),
            "raw_model_outputs": [{
                "stage": "sas_single_pass",
                "text": raw,
                "usage": dict(self.llm.last_usage or {}),
            }],
            "post_stage_candidates": [asdict(item) for item in candidates],
        }
        trace_status = ("ok" if (verified or (defer_resolution and candidates
                                              and contract_valid)) else
                        "abstain" if contract_valid else "error")
        trace_info = (f"Ein Modellaufruf: {verified} evidenzgebundene Kandidaten"
                      if completed else
                      "Responses-Aufruf technisch oder vertraglich unvollstaendig; fail-closed")
        return candidates[:n], _trace(
            "SingleAgentBaseline", trace_status,
            trace_info,
            output, t0)


class SelfReviewSingleAgent:
    """Starke SAS-2-Baseline mit Recherche und eigenem Self-Review.

    Beide Aufrufe gehoeren logisch demselben Agenten: Der zweite Pass erhaelt
    den vollstaendigen Suchauftrag und den vollstaendigen eigenen Erstentwurf.
    Es gibt weder Rollenwechsel noch informationsreduzierenden Handoff. Damit
    wird geprueft, ob ein MAS-Vorteil ueber den blossen zweiten Modellaufruf
    hinausgeht.
    """

    # Identische Pruefregeln und kompakter Ausgabevertrag wie der MAS-Verifier.
    # Unterschiedlich sind nur Rollensatz und Kontext (vollstaendiger Entwurf).
    REVIEW_SYSTEM = (SAS_REVIEW_ROLE + REVIEW_ROLE_COMMON + REVIEW_OUTPUT_SPEC
                     + SEARCH_EVIDENCE_RULES)

    def __init__(self, kb, llm=None, resolver: EvidenceResolver | None = None):
        self.kb = kb
        self.llm = llm
        self.resolver = resolver or EvidenceResolver()
        self.rules = EntityVerifier()
        self._sas1 = SingleAgentScoutingAgent(kb, llm, resolver=self.resolver)

    def run(self, query: str, n: int = 5, seed_pool: list | None = None,
            max_tokens: int | None = None, max_tool_calls: int | None = None,
            memory_context: dict | None = None,
            defer_resolution: bool = False,
            target_actor_id: str = "", target_actor_name: str = "") -> tuple:
        t0 = time.perf_counter()
        if not self.llm or not self.llm.available():
            candidates, trace = self._sas1.run(
                query, n=n, seed_pool=seed_pool,
                max_tokens=max_tokens, max_tool_calls=max_tool_calls,
                memory_context=memory_context,
                defer_resolution=defer_resolution)
            trace["agent"] = "SelfReviewSingleAgent"
            trace["info"] += "; Offline-Vertrag ohne simulierten Modellmehrwert"
            return candidates[:n], trace

        total_tokens = int(max_tokens or Config.EVAL_TOTAL_MAX_OUTPUT_TOKENS)
        total_tools = int(Config.EVAL_TOTAL_MAX_TOOL_CALLS
                          if max_tool_calls is None else max_tool_calls)
        first_tokens = total_tokens // 2
        first_tools = total_tools // 2
        first_user = shared_search_user_prompt(query, n, memory_context)
        first = self.llm.complete(
            model=Config.MODEL_SAS,
            system=ScoutingAgent.SYSTEM,
            user=first_user,
            tools=[{"type": "web_search"}],
            max_tokens=first_tokens,
            max_tool_calls=first_tools,
            purpose="sas2_research",
        )
        first_provider_ok = (
            str((self.llm.last_usage or {}).get("status") or "") == "completed")
        first_usage = dict(self.llm.last_usage or {})
        first_citations = deepcopy(getattr(self.llm, "last_citations", []))
        first_contract_valid = False
        first_candidates = []
        if first_provider_ok:
            try:
                first_contract = ScoutingAgent._strict_array(first)
                first_candidates = ScoutingAgent._parse_live(first)[:n]
                first_contract_valid = (
                    not first_contract or
                    (len(first_candidates) == len(first_contract)
                     and len(first_contract) <= n))
            except (ValueError, TypeError, json.JSONDecodeError):
                first_contract_valid = False
                preamble = ScoutingAgent._empty_array_preamble(first)
                if preamble is not None:
                    first_contract_valid = True
                    ScoutingAgent._note_empty_preamble(self.llm, preamble, first_usage)
        first_ok = first_provider_ok and first_contract_valid
        pre_review_snapshot = [asdict(item) for item in deepcopy(first_candidates)]
        second = ""
        second_usage = {}
        checklists = {}
        contract_valid = False
        candidates = []
        completed = False
        for candidate in first_candidates:
            # Gleiche Zielbindung und Pruefliste wie im MAS-Handoff.
            candidate.target_actor_id = target_actor_id
            candidate.target_actor_name = target_actor_name
            checklist = review_checklist(candidate)
            checklists[candidate.candidate_id] = checklist
        if first_ok and not first_candidates:
            # Gueltiges leeres Ergebnis: wie im MAS keine Pruefstufe ohne Rohfund.
            completed = True
            contract_valid = True
        elif first_ok:
            second = self.llm.complete(
                model=Config.MODEL_SAS,
                system=self.REVIEW_SYSTEM,
                user=(f"Unveraenderter Suchauftrag:\n{query}\n\n"
                      f"Vollstaendiger eigener Erstentwurf:\n{first}\n\n"
                      "Pruefliste (identisch zum Vergleichsarm):\n"
                      + json.dumps(list(checklists.values()), ensure_ascii=False)),
                tools=[{"type": "web_search"}],
                max_tokens=total_tokens - first_tokens,
                max_tool_calls=total_tools - first_tools,
                purpose="sas2_self_review",
            )
            completed = str((self.llm.last_usage or {}).get("status") or "") == "completed"
            second_usage = dict(self.llm.last_usage or {})
            by_id = parse_review(second, set(checklists)) if completed else None
            contract_valid = by_id is not None
            # Dieselbe logische SAS-Rolle behaelt auch die nativen Quellen ihres
            # Erstentwurfs. Modellgenerierte URLs werden dadurch nicht legitimiert.
            if hasattr(self.llm, "last_citations"):
                self.llm.last_citations = first_citations + list(self.llm.last_citations)
            for candidate in first_candidates:
                data = (by_id or {}).get(candidate.candidate_id)
                if data is None:
                    fail_closed(candidate, "Kandidat im Self-Review nicht bestaetigt")
                    continue
                apply_review(candidate, checklists[candidate.candidate_id], data,
                             keep_stage1_sources=True)
                candidate.sources = self.llm.ground_sources(candidate.sources)
                candidate.model_usage = [dict(record) for record in
                                         self.llm.usage_ledger()[-2:]]
            candidates = list(first_candidates) if contract_valid else []
        if not defer_resolution:
            self.resolver.resolve_candidates(
                candidates,
                max_fetches_total=Config.EVAL_MAX_RESOLVER_FETCHES)
            for candidate in candidates:
                self.rules.verify(candidate)
        verified = sum(candidate.verification_status == "verified_startup"
                       for candidate in candidates)
        return candidates, _trace(
            "SelfReviewSingleAgent",
            "ok" if (verified or (contract_valid and candidates
                                  and defer_resolution))
            else "abstain" if contract_valid else "error",
            (f"SAS-2 mit eigenem Self-Review: {verified} evidenzgebundene Kandidaten"
             if completed else "SAS-2 technisch oder vertraglich unvollstaendig"),
            {
                "Modus": "live", "Architektur": "SAS-2",
                "Treffer": len(candidates), "verifiziert": verified,
                "budget": {"max_output_tokens": total_tokens,
                           "max_tool_calls": total_tools},
                "usage": self.llm.usage_ledger()[-2:],
                "raw_model_outputs": [
                    {"stage": "sas2_research", "text": first,
                     "usage": first_usage},
                    {"stage": "sas2_self_review", "text": second,
                     "usage": second_usage},
                    {"stage": "sas2_review_checklist",
                     "text": json.dumps(list(checklists.values()),
                                        ensure_ascii=False)},
                ],
                "pre_review_candidates": pre_review_snapshot,
                "post_review_candidates": [asdict(item)
                                           for item in candidates],
            },
            t0,
        )
