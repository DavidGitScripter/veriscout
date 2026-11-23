#!/usr/bin/env python3
"""Explicit live write test for the disposable Pipedrive developer sandbox.

The script is fail-closed and never runs unless PIPEDRIVE_INTEGRATION_TEST=1.
It creates an unmistakably labelled technical test organization and deal, then
replays the same relation to verify idempotent upserts. It is not a discovery
result and must not be interpreted as empirical evaluation evidence.
"""
from __future__ import annotations

import json
import os
import sys

from core import Candidate, Recommendation
from crm_pipedrive import PipedriveAdapter
from pipeline import Pipeline


def main() -> int:
    if os.environ.get("PIPEDRIVE_INTEGRATION_TEST") != "1":
        print("Abbruch: PIPEDRIVE_INTEGRATION_TEST=1 fehlt.")
        return 2

    adapter = PipedriveAdapter(dry_run=False)
    pipeline = Pipeline(live=False, adapter=adapter)
    candidate = Candidate(
        name="[TEST] ScoutRef CRM Synthetic Case",
        description=(
            "Rein technischer Sandbox-Datensatz zur Prüfung von Recycling, "
            "Materialien und Fertigung bei mineralischen Reststoffen; kein "
            "recherchiertes Startup."
        ),
        founded=2026,
        company_type="test_record",
        funding_stage="Pre-Seed",
        discovery_mode="integration_test",
        verification_status="synthetic_case",
        problem_fit=True,
        sectors=["Circular Economy"],
        target_actor_id="demo_manufacturing",
        run_id="scoutref-crm-integration-20260823-v1",
        ceo="",
    )
    decision = pipeline.scout(
        candidate, use_memory=False, target_actor_id="demo_manufacturing")
    # Rein technischer Sandbox-Datensatz; kein Evaluationsurteil.
    decision.recommendation = Recommendation.PILOT
    decision.abstained = False
    decision.operationally_eligible = True

    first = pipeline.qualify(decision, human_approved=True)
    second = pipeline.qualify(decision, human_approved=True)
    same_ids = (
        first.get("org_id") == second.get("org_id")
        and first.get("deal_id") == second.get("deal_id")
    )
    result = {
        "first_status": first.get("status"),
        "second_status": second.get("status"),
        "same_ids": same_ids,
        "organization_id": second.get("org_id"),
        "deal_id": second.get("deal_id"),
        "target_organization": second.get("target_organization", {}).get("name"),
        "stage": second.get("stage"),
        "person_created": second.get("person_id") is not None,
        "skipped_fields": second.get("felder_uebersprungen"),
        "note_errors": second.get("notizfehler"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if same_ids and second.get("status") == "aktualisiert" else 1


if __name__ == "__main__":
    sys.exit(main())
