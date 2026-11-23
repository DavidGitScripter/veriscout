#!/usr/bin/env python3
"""
run.py — Kommandozeile fuer das Referenzmodell (Dry-Run ohne API-Key).

Beispiele:
  python3 run.py --discover "Logistik KI"      # Discovery + Bewertung je Treffer
  python3 run.py --demo                          # voller Durchlauf inkl. HITL + CRM + Outreach
  python3 run.py --evaluate                       # Metriken am Seed-Korpus
  python3 run.py --ablation                        # Guardrail mit vs. ohne
  python3 run.py --pipeline "Geothermie Bohr-Automatisierung"  # ein freier Kandidat
  python3 run.py --demo --live                     # Live-Pfad (benoetigt OPENAI_API_KEY)
  python3 run.py --demo --no-guardrail             # Ablation im Durchlauf
  python3 run.py --compare-actor demo_manufacturing --live  # synthetischer Vertragstest
"""
import argparse
import json
from core import Candidate, Autonomy, Recommendation
from pipeline import Pipeline
from evaluate import load_corpus, run_eval, run_ablation
from compare_architectures import (ComparisonTask, PairedArchitectureRunner,
                                   append_pair, append_blind_exports)


def _seed_pool():
    return [c for c, _ in load_corpus()]


def _print_decision(dec):
    print(f"\n=== {dec.candidate.name} ===")
    for t in dec.trace:
        flag = {"ok": "✓", "abstain": "⊘", "off": "·"}.get(t["status"], "·")
        print(f"  {flag} {t['agent']:<10} {t['info']}")
    print(f"  → Empfehlung: {dec.recommendation.value} "
          f"(Score {dec.best_score}, Evidenzabdeckung {dec.evidence_coverage})")
    if dec.abstained:
        print(f"    Abstention: {dec.abstain_reason}")


def cmd_discover(pipe, query, guardrail):
    cands, tr = pipe.discover(query, n=5, seed_pool=_seed_pool())
    print(f"[Discovery] {tr['info']}")
    for c in cands:
        dec = pipe.scout(c, use_guardrail=guardrail)
        _print_decision(dec)


def cmd_pipeline(pipe, desc, guardrail, autonomy):
    c = Candidate(name="Freier Kandidat", description=desc)
    dec = pipe.scout(c, use_guardrail=guardrail)
    _print_decision(dec)
    # HITL-Gate 1 simuliert (in der Demo automatisch bei Pilot)
    approve = dec.recommendation == Recommendation.PILOT
    crm = pipe.qualify(dec, autonomy=autonomy, human_approved=approve)
    print(f"  [CRM] {json.dumps(crm, ensure_ascii=False)}")
    if crm.get("status") == "angelegt":
        draft = pipe.draft_outreach(dec, crm)
        print(f"  [Outreach] Status: {draft['status']} | to={draft['to']} "
              f"({draft['to_quelle']}) | bcc={draft['bcc']}")
        print("  --- Anschreiben-Entwurf ---")
        print("  " + draft["body"].replace("\n", "\n  "))
        print(f"  HINWEIS: {draft['hinweis']}")


def cmd_demo(pipe, guardrail, autonomy):
    print("### VOLLER DURCHLAUF (Dry-Run) — Discovery → HITL → Pipedrive → Outreach\n")
    cands = _seed_pool()
    for c in cands:
        dec = pipe.scout(c, use_guardrail=guardrail)
        _print_decision(dec)
        approve = dec.recommendation == Recommendation.PILOT
        crm = pipe.qualify(dec, autonomy=autonomy, human_approved=approve)
        print(f"  [HITL-Gate 1] {'FREIGEGEBEN' if approve else 'kein Eintrag'} "
              f"→ CRM: {crm.get('status')}")
        if crm.get("status") == "angelegt":
            draft = pipe.draft_outreach(dec, crm)
            print(f"  [Outreach-Entwurf] to={draft['to']} bcc={draft['bcc']} "
                  f"→ {draft['status']} ({draft['hinweis']})")
    print("\n--- Pipedrive-Board (Phasen) ---")
    board = pipe.adapter.board()
    for stage, deals in board.items():
        if deals:
            print(f"  [{stage}] " + ", ".join(d["title"] for d in deals))


def cmd_evaluate(pipe, guardrail):
    r = run_eval(pipe, use_guardrail=guardrail)
    print(json.dumps({k: v for k, v in r.items() if k != "rows"},
                     ensure_ascii=False, indent=2))
    print("\nFaelle:")
    for row in r["rows"]:
        mark = "✓" if row["pred_sufficient"] == row["reference"] else "✗"
        print(f"  {mark} {row['name']:<14} pred={row['pred_sufficient']!s:<5} "
              f"ref={row['reference']!s:<5} score={row['score']:<3} {row['rec']}")


def cmd_ablation(pipe):
    r = run_ablation(pipe)
    for k in ("mit_guardrail", "ohne_guardrail"):
        m = r[k]
        print(f"[{k}] F1={m['f1']}  Precision={m['precision']}  "
              f"Recall={m['recall']}  Over-Match-Rate={m['over_match_rate']}  "
              f"Accuracy={m['accuracy']}")


def cmd_compare(actor_id: str, query: str, live: bool,
                memory_enabled: bool, output_path: str = ""):
    task = ComparisonTask(
        task_id=f"{actor_id}-push",
        target_actor_id=actor_id,
        query=query,
        push_mode=True,
    )
    result = PairedArchitectureRunner(live=live).run_pair(
        task, memory_enabled=memory_enabled, guardrail_enabled=True)
    if output_path:
        append_pair(output_path, result)
        append_blind_exports(
            output_path + ".blind.jsonl",
            output_path + ".manifest.jsonl",
            result,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(
        description="VeriScout Scouting-Referenzmodell (Prototyp)")
    ap.add_argument("--discover", metavar="QUERY")
    ap.add_argument("--pipeline", metavar="DESC")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--evaluate", action="store_true")
    ap.add_argument("--ablation", action="store_true")
    ap.add_argument("--compare-actor", metavar="ACTOR_ID",
                    help="Gepaarter SAS--MAS-PUSH-Vergleich fuer eine Zielorganisation")
    ap.add_argument("--compare-query", default="",
                    help="Optionaler Zusatzauftrag; PUSH funktioniert auch ohne Thema")
    ap.add_argument("--compare-memory", action="store_true",
                    help="Denselben eingefrorenen Feedback-Snapshot in beiden Armen nutzen")
    ap.add_argument("--comparison-output", default="",
                    help="Optionaler Append-only-JSONL-Pfad fuer den Paarlauf")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--crm-live", dest="crm_live", action="store_true",
                    help="In echtes Pipedrive schreiben (PIPEDRIVE_API_TOKEN noetig)")
    ap.add_argument("--list-orgs", dest="list_orgs", action="store_true",
                    help="Organisationen aus Pipedrive/Speicher zuruecklesen")
    ap.add_argument("--no-guardrail", dest="guardrail", action="store_false")
    ap.add_argument("--autonomy", default="draft", choices=[a.value for a in Autonomy])
    ap.set_defaults(guardrail=True)
    args = ap.parse_args()

    from crm_pipedrive import PipedriveAdapter
    adapter = PipedriveAdapter(dry_run=not args.crm_live)
    pipe = Pipeline(live=args.live, adapter=adapter)
    if not adapter.dry_run:
        print("[CRM] LIVE-Modus: schreibe in echtes Pipedrive.\n")
    autonomy = Autonomy(args.autonomy)

    if args.list_orgs:
        for o in pipe.adapter.list_organizations():
            print(o)
    elif args.discover:
        cmd_discover(pipe, args.discover, args.guardrail)
    elif args.pipeline:
        cmd_pipeline(pipe, args.pipeline, args.guardrail, autonomy)
    elif args.demo:
        cmd_demo(pipe, args.guardrail, autonomy)
    elif args.evaluate:
        cmd_evaluate(pipe, args.guardrail)
    elif args.ablation:
        cmd_ablation(pipe)
    elif args.compare_actor:
        cmd_compare(args.compare_actor, args.compare_query, args.live,
                    args.compare_memory, args.comparison_output)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
