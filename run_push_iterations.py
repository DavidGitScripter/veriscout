#!/usr/bin/env python3
"""Reproduzierbare, CRM-freie Iterationslaeufe fuer den PUSH-Pfad.

Das Programm bricht ab, wenn kein Live-Modell verfuegbar ist. Dadurch kann ein
Trockenlauf nicht versehentlich als Web-Evaluation dokumentiert werden. Jeder
Lauf erhaelt eine globale ID; Rohfunde, Verifikationsstatus, Entscheidungen,
Quellen und Kostenhinweise werden als JSONL protokolliert. Es gibt keinerlei
CRM-Schreibzugriff und das adaptive Gedaechtnis bleibt deaktiviert.
"""
from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from core import Config
from pipeline import Pipeline


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run_id(index: int) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"scoutref-eval-{stamp}-{index:02d}-{uuid.uuid4().hex[:8]}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actor", default="demo_manufacturing")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--candidates", type=int, default=5)
    parser.add_argument("--waves", type=int, default=2)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.iterations < 1 or args.candidates < 1 or args.waves < 1:
        raise SystemExit("Iterationen, Kandidaten und Wellen muessen positiv sein")

    pipe = Pipeline(live=True)
    if not pipe.llm.available():
        raise SystemExit("Kein Live-Modell verfuegbar; keine Evaluation ausgefuehrt")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for index in range(1, args.iterations + 1):
            run_id = _run_id(index)
            candidates, discovery = pipe.discover(
                "", n=args.candidates, waves=args.waves,
                target_actor_id=args.actor, push_mode=True, themes=[])
            decisions = []
            for candidate in candidates:
                candidate.run_id = run_id
                decision = pipe.scout(
                    candidate, use_guardrail=True, use_memory=False,
                    target_actor_id=args.actor)
                decisions.append({
                    "candidate": asdict(candidate),
                    "recommendation": decision.recommendation.value,
                    "score": decision.best_score,
                    "abstained": decision.abstained,
                    "abstain_reason": decision.abstain_reason,
                    "audit": decision.audit,
                })

            record = {
                "run_id": run_id,
                "timestamp": _now(),
                "purpose": "engineering_iteration_not_blind_holdout",
                "actor_id": args.actor,
                "config": {
                    "version": Config.VERSION,
                    "model_discovery": Config.MODEL_DISCOVERY,
                    "model_verification": Config.MODEL_JUDGE,
                    "waves": args.waves,
                    "candidate_limit": args.candidates,
                    "memory": False,
                    "guardrail": True,
                },
                "opportunity_plan": pipe.last_opportunity_plan,
                "discovery": discovery,
                "decisions": decisions,
                "summary": {
                    "raw_candidates": len(candidates),
                    "verified_startups": sum(
                        d["candidate"]["verification_status"] == "verified_startup"
                        for d in decisions),
                    "positive_recommendations": sum(
                        d["recommendation"] == "Pilot" for d in decisions),
                    "abstentions": sum(d["abstained"] for d in decisions),
                },
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            print(json.dumps({"run_id": run_id, **record["summary"]},
                             ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
