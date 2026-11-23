"""
pipeline.py — Orchestrierung des Referenzmodells.

Ablauf:
  SAS oder (Scouting -> Verifikation) -> Quellenresolver -> Evidenzmatrix
            -> Profilkontext -> Relationsbewertung -> Policy Gate -> Decision
            -> (optional: schreibgeschuetzter Memory-Kontext)
  --- HITL-Gate 1 (Vorqualifizierung durch Mensch) ---
  -> CRM (Pipedrive, Phase 'Vorqualifiziert')
  -> Outreach-Entwurf (Kontaktermittlung + BCC, KEIN Versand)
  --- HITL-Gate 2 (Mensch versendet manuell) ---

Die Gates sind explizite Methodenaufrufe; keine Aussenwirkung passiert ohne sie.
Flags: use_guardrail (Ablation), use_memory, autonomy.
"""
from __future__ import annotations

import hashlib
import time
from copy import deepcopy
from dataclasses import asdict
from urllib.parse import urlsplit
from core import Config, Candidate, Decision, Recommendation, Autonomy, LLMClient
from knowledge_base import KnowledgeBase
from agents import (ScoutingAgent, CandidateNormalizer, RelationContextService,
                    RelationEvaluationService, PolicyGate, DecisionFormatter,
                    VerificationAgent)
from baselines import SingleAgentScoutingAgent, SelfReviewSingleAgent
from entity_verifier import BLOCKED_ENTITY_TYPES
from crm_pipedrive import PipedriveAdapter, CRMWriteService
from outreach import OutreachAgent
from provenance import AuditRecorder
from memory import FeedbackMemory, MemoryStore
from opportunity_planner import OpportunityPlanner
from evidence_matrix import EvidenceMatrixBuilder
from evidence_resolver import EvidenceResolver
from quality_gates import QualityGateEvaluator
from experiment_protocol import PublicSearchTaskInput


def _is_public_http_url(value: str) -> bool:
    try:
        parsed = urlsplit(str(value or "").strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)
    except Exception:
        return False


def _normalise_task_sources(packet: dict, organization_id: str,
                            organization_name: str = "") -> list[dict]:
    """Bindet alle Ausgangsquellen fail-closed an die Zielorganisation.

    Die Hauptquelle des Suchfelds ist Teil des fachlichen Auftrags und muss
    deshalb auch dann im Evidenzmanifest erscheinen, wenn sie nicht zusaetzlich
    im Quellenpaket dupliziert wurde. Sie belegt dabei nur das festgelegte
    oeffentliche Suchfeld, nicht automatisch einen konkreten Zielprozess.
    """
    sources: list[dict] = []

    def add_document(raw: dict, *, field_evidence: dict | None = None) -> None:
        document = deepcopy(dict(raw or {}))
        classification = str(
            document.get("classification") or
            document.get("datenklassifikation") or "public"
        ).strip().casefold()
        if classification not in {"public", "oeffentlich"}:
            raise ValueError("Nichtoeffentliche Quelle im public-only Taskpaket.")
        source_organization = str(
            document.get("organization_id") or document.get("actor_id") or ""
        ).strip()
        if source_organization and source_organization != organization_id:
            raise ValueError(
                "Das Taskpaket darf keine Belege einer anderen Organisation enthalten.")
        url = str(document.get("url") or "").strip()
        if url and not _is_public_http_url(url):
            raise ValueError("Taskquelle enthaelt keine oeffentliche HTTP(S)-URL.")
        document.pop("actor_id", None)
        document["organization_id"] = organization_id
        document["classification"] = "public"
        document["subject_type"] = "target_organization"
        document["subject_id"] = organization_id
        document["subject_name"] = organization_name
        normalised_evidence = []
        for evidence in document.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            bound = deepcopy(evidence)
            bound["subject_type"] = "target_organization"
            bound["subject_id"] = organization_id
            bound["subject_name"] = organization_name
            normalised_evidence.append(bound)
        if normalised_evidence:
            document["evidence"] = normalised_evidence
        if field_evidence:
            field_evidence = deepcopy(field_evidence)
            field_evidence["subject_type"] = "target_organization"
            field_evidence["subject_id"] = organization_id
            field_evidence["subject_name"] = organization_name
            document.setdefault("evidence", [])
            if field_evidence not in document["evidence"]:
                document["evidence"].append(field_evidence)

        # Gleiche URL bzw. Dokument-ID wird zusammengefuehrt, damit Suchfeld-
        # und Prozessclaims derselben Seite nicht gegenseitig verloren gehen.
        key = (url or str(document.get("document_id") or
                          document.get("source_id") or "").strip())
        for existing in sources:
            existing_key = (str(existing.get("url") or "").strip() or
                            str(existing.get("document_id") or
                                existing.get("source_id") or "").strip())
            if key and key == existing_key:
                for evidence in document.get("evidence") or []:
                    existing.setdefault("evidence", [])
                    if evidence not in existing["evidence"]:
                        existing["evidence"].append(evidence)
                for name, value in document.items():
                    if name != "evidence" and value and not existing.get(name):
                        existing[name] = value
                return
        sources.append(document)

    for item in packet.get("public_source_package") or []:
        if not isinstance(item, dict):
            raise ValueError("Jede Taskquelle muss ein Objekt sein.")
        add_document(item)

    search_field = dict(packet.get("search_field") or {})
    field_source = search_field.get("source") or {}
    if isinstance(field_source, str):
        field_source = {"label": field_source}
    if not isinstance(field_source, dict):
        raise ValueError("Die Quelle des oeffentlichen Suchfelds ist ungueltig.")
    source_url = str(field_source.get("url") or "").strip()
    if source_url:
        theme_id = str(search_field.get("theme_id") or
                       search_field.get("id") or "field").strip()
        digest = hashlib.sha256(
            f"{organization_id}|{theme_id}|{source_url}".encode("utf-8")
        ).hexdigest()[:12]
        excerpt = str(field_source.get("excerpt") or "").strip()
        claim_text = str(search_field.get("description") or
                         search_field.get("title") or excerpt).strip()
        add_document({
            "document_id": f"field-src-{digest}",
            "organization_id": organization_id,
            "classification": field_source.get("classification") or "public",
            "title": field_source.get("title") or search_field.get("title") or "",
            "publisher": field_source.get("publisher") or "",
            "url": source_url,
            "published_at": field_source.get("published_at") or "",
            "retrieved_at": field_source.get("retrieved_at") or "",
        }, field_evidence={
            "field": "public_search_field",
            "claim_text": claim_text,
            "excerpt": excerpt,
            "stance": "support",
        })
    return sources


class Pipeline:
    def __init__(self, live: bool = False, adapter: PipedriveAdapter = None,
                 memory: FeedbackMemory = None, llm: LLMClient = None,
                 resource_broker=None, audit_write: bool | None = None,
                 reasoning_effort: str | None = None):
        self.kb = KnowledgeBase()
        self.resource_broker = resource_broker
        self.llm = llm or LLMClient(
            live=live, resource_broker=resource_broker,
            reasoning_effort=reasoning_effort)
        if llm and hasattr(self.llm, "attach_resource_broker"):
            self.llm.attach_resource_broker(resource_broker)
        if llm and hasattr(self.llm, "set_reasoning_effort"):
            self.llm.set_reasoning_effort(reasoning_effort)
        self.resolver = EvidenceResolver(resource_broker=resource_broker)
        self.scouting = ScoutingAgent(self.kb, self.llm)
        self.discovery = self.scouting  # bestehende UI-Aufrufe
        self.verify = VerificationAgent(self.llm, resolver=self.resolver)
        self.sas = SingleAgentScoutingAgent(
            self.kb, self.llm, resolver=self.resolver)
        self.sas2 = SelfReviewSingleAgent(
            self.kb, self.llm, resolver=self.resolver)
        self.opportunity = OpportunityPlanner(self.kb)
        self.ingest = CandidateNormalizer()
        self.enrich = RelationContextService(self.kb)
        self.match = RelationEvaluationService(self.kb)
        self.guard = PolicyGate(self.kb)
        self.report = DecisionFormatter()
        self.matrix_builder = EvidenceMatrixBuilder()
        self.quality = QualityGateEvaluator()
        self.audit = AuditRecorder()
        self.memory = memory or FeedbackMemory(MemoryStore())
        self.adapter = adapter or PipedriveAdapter(dry_run=True)
        self.crm = CRMWriteService(self.adapter, self.kb)
        self.outreach = OutreachAgent(self.llm)
        self.last_opportunity_plan = None
        self.last_discovery_traces = []
        self.audit_write = Config.AUDIT_WRITE if audit_write is None else bool(audit_write)

    # ---- Discovery ----
    def discover(self, query: str, n: int = 5, seed_pool: list = None,
                 waves: int = None, target_actor_id: str = "",
                 push_mode: bool = False, themes: list = None,
                 architecture: str = "mas", max_tokens: int = None,
                 max_tool_calls: int = None, use_memory: bool = False,
                 include_curated: bool = True,
                 task_input: PublicSearchTaskInput | dict | None = None,
                 memory_context_override: dict | None = None,
                 memory_evaluation_context: dict | None = None):
        architecture = architecture.strip().lower()
        if architecture not in {"sas", "sas1", "sas2", "mas"}:
            raise ValueError("architecture muss sas1, sas2 oder mas sein")
        self.last_opportunity_plan = None
        # Eine Pipeline kann in der UI mehrere Auftraege nacheinander bedienen.
        # Der vorherige Laufzeitkontext darf dabei nie in den naechsten Auftrag
        # gelangen.
        self.kb.clear_task_organization()
        if task_input:
            packet = (task_input.canonical_dict()
                      if isinstance(task_input, PublicSearchTaskInput)
                      else dict(task_input))
            packet_organization = str(
                packet.get("organization_id") or ""
            ).strip()
            organization_name = str(
                packet.get("organization_name") or ""
            ).strip()
            organization_domain_hint = str(
                packet.get("organization_domain_hint") or ""
            ).strip()
            if not packet_organization or not organization_name:
                raise ValueError(
                    "Taskpaket braucht organization_id und organization_name.")
            if target_actor_id and target_actor_id != packet_organization:
                raise ValueError("Taskpaket und target_actor_id widersprechen sich.")
            target_actor_id = packet_organization
            push_mode = True
            query = str(packet.get("shared_prompt") or "")
            if not query:
                raise ValueError("Kanonischer shared_prompt fehlt.")
            public_sources = _normalise_task_sources(
                packet, target_actor_id, organization_name)
            search_field = dict(packet.get("search_field") or {})
            # Task-lokal: kein Eintrag in actors.json, kein persistierter
            # Themenkatalog und keine Ableitung aus einem frueheren Auftrag.
            self.kb.bind_task_organization(
                target_actor_id, organization_name,
                # Ein Domainhinweis dient nur der Identitaetsaufloesung und ist
                # weder Profilquelle noch Evidenz.
                public_url="",
                search_field=search_field,
            )
            self.last_opportunity_plan = self.opportunity.build_task_plan(
                organization_id=target_actor_id,
                organization_name=organization_name,
                organization_domain_hint=organization_domain_hint,
                search_field=search_field,
                public_sources=public_sources,
            )
            include_curated = False
        elif push_mode:
            if not target_actor_id:
                raise ValueError("PUSH-Suche braucht eine Zielorganisation")
            query, self.last_opportunity_plan = self.opportunity.build_prompt(
                target_actor_id, themes=themes)

        total_tokens = max_tokens or Config.EVAL_TOTAL_MAX_OUTPUT_TOKENS
        total_tools = (Config.EVAL_TOTAL_MAX_TOOL_CALLS if max_tool_calls is None
                       else max_tool_calls)
        memory_context = {}
        if memory_context_override is not None:
            memory_context = dict(memory_context_override)
        elif use_memory and target_actor_id and hasattr(self.memory, "context"):
            memory_context = self.memory.context(
                target_actor_id, query,
                evaluation_context=memory_evaluation_context)

        if architecture in {"sas", "sas2"}:
            cands, discovery_trace = self.sas2.run(
                query, n=n, seed_pool=seed_pool,
                max_tokens=total_tokens, max_tool_calls=total_tools,
                memory_context=memory_context,
                defer_resolution=True,
                target_actor_id=target_actor_id,
                target_actor_name=str(
                    (self.last_opportunity_plan or {}).get("organization_name")
                    or "").strip())
        elif architecture == "sas1":
            cands, discovery_trace = self.sas.run(
                query, n=n, seed_pool=seed_pool,
                max_tokens=total_tokens, max_tool_calls=total_tools,
                memory_context=memory_context,
                defer_resolution=True)
        else:
            scout_tokens = total_tokens // 2
            scout_tools = total_tools // 2
            cands, discovery_trace = self.scouting.run(
                query, n=n, seed_pool=seed_pool, waves=waves,
                max_tokens=scout_tokens, max_tool_calls=scout_tools,
                memory_context=memory_context)
        curated = []
        if push_mode and self.last_opportunity_plan and include_curated:
            curated = self.opportunity.seed_candidates(
                target_actor_id, self.last_opportunity_plan)
            # Ein Teil der Plaetze ist fuer dokumentierte Rohhinweise reserviert,
            # der Rest fuer neue Live-Funde. Bleibt die Websuche leer, werden die
            # freien Plaetze mit weiteren kuratierten Hinweisen aufgefuellt.
            reserve = (min(len(curated), n) if not self.llm.available()
                       else min(len(curated), max(1, n // 2)))
            merged = list(curated[:reserve])
            known = {candidate.name.strip().casefold() for candidate in merged}
            for candidate in cands:
                if len(merged) >= n:
                    break
                if candidate.name.strip().casefold() not in known:
                    merged.append(candidate)
                    known.add(candidate.name.strip().casefold())
            for candidate in curated[reserve:]:
                if len(merged) >= n:
                    break
                if candidate.name.strip().casefold() not in known:
                    merged.append(candidate)
                    known.add(candidate.name.strip().casefold())
            cands = merged[:n]
            discovery_trace.setdefault("output", {})["kuratierte_rohhinweise"] = len(curated)
            discovery_trace["info"] = (
                discovery_trace.get("info", "") +
                f"; {len(curated)} kuratierte Rohhinweise erneut geprueft")
        for candidate in cands:
            # Die Zielbindung stammt ausschliesslich aus dem serverseitigen
            # Auftrag. Ein Kandidatenobjekt oder ein frueherer Lauf darf sie
            # weder setzen noch fortschreiben.
            candidate.target_actor_id = target_actor_id
            candidate.target_actor_name = str(
                (self.last_opportunity_plan or {}).get("organization_name") or ""
            ).strip()
        cands = list(cands)[:max(0, int(n))]
        pre_review_candidates = [asdict(item) for item in deepcopy(cands)]
        if architecture == "mas":
            cands, verification_trace = self.verify.run(
                cands, query,
                max_tokens=total_tokens - total_tokens // 2,
                max_tool_calls=total_tools - total_tools // 2,
                defer_resolution=True)
        else:
            verification_trace = {
                "agent": "ArchitectureReviewStage",
                "status": discovery_trace.get("status", "error"),
                "info": "SAS-2-Self-Review ist im Architekturtrace enthalten",
                "output": {},
                "ms": 0.0,
            }

        post_architecture_candidates = [asdict(item) for item in deepcopy(cands)]
        # Ein gemeinsamer, architekturunabhaengiger Round-Robin-Resolver stellt
        # fuer SAS und MAS dieselbe Kandidaten-/Quellenbudgetlogik her.
        # Die Abrufreserve der Nachrecherche (M2) bleibt hier unangetastet.
        resolver_cap = (int(self.resource_broker.limits.max_resolver_fetches)
                        - int(getattr(self.resource_broker, "follow_up_fetch_reserve", 0) or 0)
                        if self.resource_broker else
                        Config.EVAL_MAX_RESOLVER_FETCHES)
        resolution = self.resolver.resolve_candidates(
            cands, max_fetches_total=resolver_cap)
        verification_results = [self.verify.rules.verify(candidate)
                                for candidate in cands]
        verified = sum(item.status == "verified_startup"
                       for item in verification_results)
        # Einzelne nicht abrufbare Quellen (403, 404, Zeitueberschreitung) sind
        # kein technischer Fehler des Arms. Sie werden gezaehlt und wirken auf
        # Kandidatenebene: Fehlt dadurch ein Beleg, folgt eine Enthaltung.
        if resolution["not_checked_budget"]:
            resolver_status = "not_checked_budget"
        else:
            resolver_status = "ok" if verified else "abstain"
        resolver_trace = {
            "agent": "SharedEvidenceResolver",
            "status": resolver_status,
            "info": (
                f"{verified} von {len(cands)} Funden durch identische, "
                "deterministische Quellenpruefung bestaetigt; "
                f"{resolution['not_checked_budget']} budgetbedingt ungeprueft"),
            "output": {
                **resolution,
                "kandidaten": [
                    {"name": candidate.name, **result.to_dict()}
                    for candidate, result in zip(cands, verification_results)
                ],
                "post_resolution_candidates": [asdict(item) for item in cands],
            },
            "ms": 0.0,
        }
        self.last_discovery_traces = [
            discovery_trace, verification_trace, resolver_trace]
        combined = dict(discovery_trace)
        combined["info"] = "; ".join(filter(None, [
            discovery_trace.get("info", ""),
            verification_trace.get("info", ""), resolver_trace.get("info", "")]))
        stage_statuses = {str(item.get("status") or "")
                          for item in self.last_discovery_traces}
        if stage_statuses & {"error", "technical_error"}:
            combined["status"] = "technical_error"
        elif "not_checked_budget" in stage_statuses:
            combined["status"] = "not_checked_budget"
        elif verified:
            combined["status"] = "ok"
        else:
            combined["status"] = "abstain"
        combined["output"] = dict(discovery_trace.get("output", {}))
        combined["output"]["verification"] = verification_trace.get("output", {})
        combined["output"]["shared_evidence_resolution"] = resolver_trace["output"]
        combined["output"]["stage_artifacts"] = {
            "pre_architecture_review": pre_review_candidates,
            "post_architecture_review": post_architecture_candidates,
            "post_shared_resolution": [asdict(item) for item in cands],
        }
        discovery_cost = combined["output"].get("kosten_usd_ca") or 0
        verification_cost = ((verification_trace.get("output") or {})
                             .get("kosten", {}).get("kosten_usd_ca") or 0)
        combined["output"]["kosten_usd_ca"] = round(
            float(discovery_cost) + float(verification_cost), 3)
        combined["output"]["opportunity_plan"] = self.last_opportunity_plan or {}
        combined["output"]["architecture"] = architecture
        combined["output"]["experiment_budget"] = {
            "model": (Config.MODEL_SAS if architecture != "mas" else Config.MODEL_SCOUT),
            "max_output_tokens": total_tokens,
            "max_tool_calls": total_tools,
            "reasoning_effort": Config.REASONING_EFFORT,
            "memory_snapshot": memory_context.get("snapshot_id", "off"),
            "curated_leads": bool(include_curated),
        }
        combined["output"]["usage_ledger"] = self.llm.usage_ledger()
        if self.resource_broker:
            if combined["status"] == "technical_error":
                self.resource_broker.mark_failure("architecture_stage_failure")
            combined["output"]["resource_usage"] = self.resource_broker.summary()
        combined["traces"] = self.last_discovery_traces
        combined["query"] = query
        return list(cands)[:max(0, int(n))], combined

    # ---- Urteilspipeline (keine Aussenwirkung) ----
    def scout(self, c: Candidate, use_guardrail: bool = True,
              use_memory: bool = True, target_actor_id: str = "") -> Decision:
        trace = []
        c, tr = self.ingest.run(c); trace.append(tr)
        if target_actor_id:
            c.target_actor_id = target_actor_id
        if c.target_actor_id and not c.target_actor_name:
            try:
                c.target_actor_name = str(self.kb.get(c.target_actor_id).get("name") or "")
            except (KeyError, TypeError, AttributeError):
                c.target_actor_name = ""
        tr = self.verify.check_one(c); trace.append(tr)
        plan = self.last_opportunity_plan or (
            self.opportunity.build(c.target_actor_id, themes=[])
            if c.target_actor_id else {})
        matrix = self.matrix_builder.build(
            c, target_sources=plan.get("public_sources", []))
        c.evidence_matrix = matrix.to_dict()
        trace.append({
            "agent": "EvidenceMatrix",
            "status": ("ok" if matrix.decision_state in {"fully_supported", "development_only"}
                       else "abstain"),
            "info": (f"Evidenzabdeckung {matrix.evidence_coverage}; blockierend: "
                     f"{', '.join(matrix.blocking_dimensions) or 'keine'}"),
            "output": matrix.to_dict(),
            "ms": 0.0,
        })
        retrieved, tr = self.enrich.run(
            c, target_actor_id=c.target_actor_id); trace.append(tr)
        matches, tr = self.match.run(
            c, retrieved, c.target_actor_id, evidence_matrix=matrix)
        trace.append(tr)

        eff_threshold = Config.THRESHOLD_SUFFICIENT
        mem_out = {}
        if use_memory and matches:
            aid = matches[0].actor_id
            if hasattr(self.memory, "context"):
                mem_out = self.memory.context(aid, c.description)
            else:
                # Kompatibilitaet fuer alte Test-Doubles; keine unkalibrierte
                # Score- oder Schwellenmutation mehr.
                mem_out = {"akteur": aid, "retrieved": [],
                           "hinweis": "Legacy-Memory ohne Kontextschnittstelle"}
            trace.append({"agent": "FeedbackMemory", "status": "ok",
                          "info": "Vergleichsfaelle abgerufen; keine Scoremutation",
                          "output": mem_out, "ms": 0.0})

        if use_guardrail:
            (abstained, reason), tr = self.guard.run(
                c, matches, eff_threshold, c.target_actor_id,
                evidence_matrix=matrix)
            trace.append(tr)
        else:
            # Ablation: ohne Guardrail gilt nur die nackte Schwelle, keine Ausschluesse
            for m in matches:
                target_ok = (not c.target_actor_id or m.actor_id == c.target_actor_id)
                m.sufficient = target_ok and m.score >= eff_threshold
            abstained = not any(m.sufficient for m in matches)
            reason = "(Ablation: Guardrail deaktiviert)"
            trace.append({"agent": "Guardrail", "status": "off",
                          "info": reason, "output": {}, "ms": 0.0})

        (rec, conf), tr = self.report.run(
            matches, abstained, evidence_matrix=matrix)
        trace.append(tr)

        best = matches[0] if matches else None
        source_statuses = {
            str(getattr(source, "resolved_status", "") or "")
            for source in (c.sources or [])
        }
        if not abstained:
            # Ein vollstaendig belegter positiver Fall bleibt abgeschlossen, auch
            # wenn eine zusaetzliche, nicht tragende Quelle (z. B. HTTP 403)
            # technisch nicht abrufbar war.
            evaluation_status = "completed"
        elif source_statuses and source_statuses <= {"technical_error"}:
            # Nur wenn keine einzige Quelle abrufbar war, ist der Fall
            # technisch nicht pruefbar; sonst fachliche Enthaltung.
            evaluation_status = "technical_error"
        elif "not_checked_budget" in source_statuses:
            evaluation_status = "not_checked_budget"
        else:
            evaluation_status = "abstention"
        # Im public-only PUSH-Auftrag wird ausschliesslich das ausgewaehlte
        # Zielorganisation bewertet. Allgemeine Offline-Aufrufe ohne Ziel-ID behalten
        # die rueckwaertskompatible Profiluebersicht.
        general_fit = [
            {"akteur": m.actor_name, "typ": m.fit, "begruendung": m.rationale,
             "score": m.score}
            for m in matches
            if (not c.target_actor_id and m.fit in ("generell", "thematisch")
                and not m.sufficient)
        ][:8]
        decision = Decision(
            candidate=c, matches=matches,
            best_actor_id=best.actor_id if best else None,
            best_score=best.score if best else 0,
            recommendation=rec, confidence=conf,
            confidence_is_calibrated=False,
            evidence_coverage=matrix.evidence_coverage,
            evidence_grade=("vollstaendig" if matrix.evidence_coverage == 1.0 else
                            "teilweise" if matrix.evidence_coverage > 0 else
                            "nicht_ausreichend"),
            evaluation_status=evaluation_status,
            abstained=abstained, abstain_reason=reason,
            trace=trace, memory=mem_out, general_fit=general_fit)
        gate_results = self.quality.evaluate(decision)
        decision.quality_gates = [result.to_dict() for result in gate_results]
        decision.operationally_eligible = self.quality.operationally_eligible(
            gate_results)
        decision.decision_state, decision.decision_state_reason = (
            self._decision_state(c, matrix, decision))
        trace.append({
            "agent": "QualityGates",
            "status": "ok" if decision.operationally_eligible else "blocked",
            "info": ("alle sechs Quality Gates bestanden" if decision.operationally_eligible
                     else "mindestens ein Quality Gate blockiert Aussenwirkung"),
            "output": {"gates": decision.quality_gates},
            "ms": 0.0,
        })
        decision.audit = self.audit.run(
            decision, self.kb, write_log=self.audit_write)
        return decision

    @staticmethod
    def _decision_state(c: Candidate, matrix, decision: Decision) -> tuple[str, str]:
        """Bildet die Pruefstatus auf die vier fachlichen Zielzustaende ab.

        Reihenfolge wie im Referenzmodell: technische Gueltigkeit, belegter
        Ausschluss oder Gegenbeleg, Evidenzluecke, positive Empfehlung.
        """
        if decision.evaluation_status == "technical_error":
            return "technischer_fehler", "Quelle oder Modellantwort technisch nicht verfuegbar"
        if decision.evaluation_status == "not_checked_budget":
            return "technischer_fehler", "Pruefbudget erschoepft, Quellen ungeprueft"
        exclusions = [reason[len("Ausschluss: "):] for reason in
                      (getattr(c, "verification_reasons", None) or [])
                      if str(reason).startswith("Ausschluss: ")]
        if exclusions:
            # R1/R3 (11.11.2026): belegter Sitz ausserhalb DACH oder zu alt.
            return "ablehnung", "Ausschlusskriterium: " + "; ".join(exclusions)
        entity = str(getattr(c, "company_type", "") or "").lower()
        if (entity in BLOCKED_ENTITY_TYPES or entity == "non_existing"
                or getattr(c, "is_service_provider", False)
                or getattr(c, "verification_status", "") == "not_a_startup"):
            return "ablehnung", f"Unternehmenstyp '{entity or 'unbekannt'}' ausgeschlossen"
        contradictions = list(getattr(matrix, "contradictions", []) or [])
        if contradictions:
            return "ablehnung", "Gegenbeleg zu: " + ", ".join(contradictions)
        if not decision.abstained and decision.operationally_eligible:
            # R5 (11.11.2026): abgeleitete Glieder sichtbar benennen.
            labels = {"input_stream": "Input", "transformation": "Wirkung",
                      "output_application": "Ergebnis"}
            derived = [labels[getattr(cell, "dimension", "")]
                       for cell in getattr(matrix, "cells", []) or []
                       if getattr(cell, "dimension", "") in labels
                       and getattr(cell, "basis", "direct") == "derived"]
            if derived:
                names = (", ".join(derived[:-1]) + " und " + derived[-1]
                         if len(derived) > 1 else derived[0])
                return "empfehlung", (f"Empfehlung; {names} abgeleitet, im Erstgespraech "
                                      "zu klaeren; uebrige Pflichtdimensionen belegt")
            return "empfehlung", "alle neun Pflichtdimensionen belegt, Gates bestanden"
        blocking = list(getattr(matrix, "blocking_dimensions", []) or [])
        return "enthaltung", ("offen: " + ", ".join(blocking) if blocking
                              else decision.abstain_reason or "Evidenz unvollstaendig")

    # ---- HITL-Gate 1: Vorqualifizierung -> CRM ----
    def qualify(self, decision: Decision, autonomy: Autonomy = Autonomy.DRAFT,
                human_approved: bool = False) -> dict:
        if not human_approved:
            return {"status": "wartet_auf_freigabe",
                    "hinweis": "Human-in-the-Loop: erst nach manueller Bestaetigung "
                               "wird ins CRM geschrieben."}
        if not self._operationally_eligible(decision):
            return {"status": "kein_eintrag",
                    "grund": "Nur evidenzgebundene Pilot-Vorschlaege duerfen ins CRM."}
        return self.crm.run(decision, autonomy=autonomy)

    # ---- Outreach-Entwurf (Gate 2 = Mensch versendet) ----
    def draft_outreach(self, decision: Decision, crm_result: dict,
                       use_case: str = "") -> dict:
        if not self._operationally_eligible(decision):
            return {"status": "kein_entwurf",
                    "grund": "Keine Aussenwirkung bei Ablehnung, Beobachtung oder Evidenzmangel."}
        return self.outreach.run(decision, crm_result, use_case=use_case)

    @staticmethod
    def _operationally_eligible(decision: Decision) -> bool:
        return bool(decision.operationally_eligible)
