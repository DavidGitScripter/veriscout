#!/usr/bin/env python3
"""Read-only check of the Pipedrive sandbox against the versioned manifest."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from core import Config
from crm_pipedrive import PipedriveAdapter


BASE = Path(__file__).resolve().parent
MANIFEST = BASE / "config" / "pipedrive_field_manifest.json"


def _labels(field: dict) -> set[str]:
    return {
        str(option.get("label") or "").strip().casefold()
        for option in field.get("options") or []
    }


def main() -> int:
    if not Config.PIPEDRIVE_API_TOKEN:
        print("PIPEDRIVE_API_TOKEN fehlt; keine Kontoabfrage ausgefuehrt.")
        return 2

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    adapter = PipedriveAdapter(dry_run=False)
    me = adapter.current_user()
    errors: list[str] = []

    for section, remote in (
        ("organization_fields", adapter._org_fields()),
        ("deal_fields", adapter._deal_fields()),
    ):
        for spec in manifest.get(section) or []:
            field = remote.get(spec["name"].casefold())
            if not field:
                errors.append(f"{section}: {spec['name']} fehlt")
                continue
            if field.get("type") != spec["field_type"]:
                errors.append(
                    f"{section}: {spec['name']} hat Typ {field.get('type')}, "
                    f"erwartet {spec['field_type']}"
                )
            missing = [
                label for label in spec.get("options") or []
                if label.casefold() not in _labels(field)
            ]
            if missing:
                errors.append(
                    f"{section}: {spec['name']} ohne Optionen {', '.join(missing)}"
                )

    target = adapter._resolve_stage()
    expected_stages = manifest["pipeline"]["stages"]
    actual_stages = set(target["id2name"].values())
    for stage in expected_stages:
        if stage not in actual_stages:
            errors.append(f"pipeline: Phase {stage} fehlt")

    members = []
    for item in manifest.get("member_organizations") or []:
        found = adapter.find_organization(item["name"])
        if not found:
            errors.append(f"member: {item['name']} fehlt")
        else:
            members.append(found["id"])

    print(json.dumps({
        "account_user": me.get("name", ""),
        "organization_fields": len(manifest.get("organization_fields") or []),
        "deal_fields": len(manifest.get("deal_fields") or []),
        "pipeline": manifest["pipeline"]["name"],
        "stages": len(expected_stages),
        "members": len(members),
        "errors": errors,
    }, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
