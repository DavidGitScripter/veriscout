#!/usr/bin/env python3
"""Idempotente Bereitstellung der Pipedrive-Felder ueber Fields API v2.

Ohne ``--apply`` werden ausschliesslich lesende Abfragen ausgefuehrt und ein
Plan ausgegeben. Es wird nie geloescht oder ein bestehender Feldtyp geaendert.
Ein Typkonflikt beendet den Apply-Lauf vor dem ersten Schreibzugriff.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


BASE = Path(__file__).resolve().parent
MANIFEST_PATH = BASE / "config" / "pipedrive_field_manifest.json"
ENTITY_ENDPOINTS = {
    "organization_fields": "organizationFields",
    "person_fields": "personFields",
    "deal_fields": "dealFields",
}


def api_root(value: str) -> str:
    root = (value or "https://api.pipedrive.com").rstrip("/")
    for suffix in ("/api/v1", "/api/v2"):
        if root.endswith(suffix):
            root = root[:-len(suffix)]
    return root


class Client:
    def __init__(self, root: str, token: str):
        self.root = api_root(root)
        self.token = token

    def request(self, method: str, path: str, payload=None):
        url = self.root + path
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method=method,
            headers={"Accept": "application/json", "Content-Type": "application/json",
                     "x-api-token": self.token},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Pipedrive HTTP {exc.code}: {detail}") from None
        if not raw.get("success", False):
            raise RuntimeError(f"Pipedrive API: {raw.get('error', raw)}")
        return raw.get("data")


def normalize_remote(fields: list) -> dict:
    result = {}
    for field in fields or []:
        name = str(field.get("field_name") or field.get("name") or "").strip()
        if not name:
            continue
        result[name.casefold()] = {
            "name": name,
            "field_type": field.get("field_type") or field.get("type"),
            "field_code": field.get("field_code") or field.get("key"),
            "options": [str(x.get("label") or "").strip()
                        for x in (field.get("options") or [])],
        }
    return result


def plan_entity(expected: list, remote_fields: list, endpoint: str) -> list:
    remote = normalize_remote(remote_fields)
    plan = []
    for spec in expected:
        current = remote.get(spec["name"].casefold())
        if not current:
            plan.append({"action": "CREATE", "endpoint": endpoint, "spec": spec})
            continue
        if current["field_type"] != spec["field_type"]:
            plan.append({"action": "CONFLICT", "endpoint": endpoint,
                         "name": spec["name"], "expected": spec["field_type"],
                         "actual": current["field_type"]})
            continue
        expected_options = spec.get("options") or []
        present = {x.casefold() for x in current.get("options") or []}
        missing = [x for x in expected_options if x.casefold() not in present]
        if missing:
            plan.append({"action": "ADD_OPTIONS", "endpoint": endpoint,
                         "field_code": current["field_code"], "name": spec["name"],
                         "options": missing})
        else:
            plan.append({"action": "NOOP", "endpoint": endpoint, "name": spec["name"]})
    return plan


def build_plan(client: Client, manifest: dict) -> list:
    plan = []
    for section, endpoint in ENTITY_ENDPOINTS.items():
        expected = manifest.get(section) or []
        if not expected:
            continue
        remote = client.request("GET", f"/api/v2/{endpoint}?limit=500") or []
        plan.extend(plan_entity(expected, remote, endpoint))
    plan.extend(plan_pipeline(client, manifest.get("pipeline") or {}))
    return plan


def plan_pipeline(client: Client, spec: dict) -> list:
    name = str(spec.get("name") or "").strip()
    stages = [str(x).strip() for x in (spec.get("stages") or []) if str(x).strip()]
    if not name:
        return []
    pipelines = client.request("GET", "/api/v2/pipelines?limit=500") or []
    matches = [item for item in pipelines if str(item.get("name") or "") == name]
    if len(matches) > 1:
        return [{"action": "CONFLICT", "endpoint": "pipelines", "name": name,
                 "reason": "Pipeline-Name ist mehrfach vorhanden"}]
    if not matches:
        return [{"action": "CREATE_PIPELINE", "endpoint": "pipelines",
                 "name": name, "stages": stages}]
    pipeline_id = matches[0].get("id")
    existing = client.request(
        "GET", f"/api/v2/stages?pipeline_id={pipeline_id}&limit=500") or []
    plan = [{"action": "NOOP", "endpoint": "pipelines", "name": name}]
    for stage in stages:
        hits = [item for item in existing if str(item.get("name") or "") == stage]
        if len(hits) > 1:
            plan.append({"action": "CONFLICT", "endpoint": "stages",
                         "name": stage, "reason": "Phase ist mehrfach vorhanden"})
        elif not hits:
            plan.append({"action": "CREATE_STAGE", "endpoint": "stages",
                         "name": stage, "pipeline_id": pipeline_id})
        else:
            plan.append({"action": "NOOP", "endpoint": "stages", "name": stage})
    return plan


def apply_plan(client: Client, plan: list) -> None:
    conflicts = [x for x in plan if x["action"] == "CONFLICT"]
    if conflicts:
        raise RuntimeError("Typkonflikte vorhanden; keine Aenderung ausgefuehrt")
    for item in plan:
        endpoint = item["endpoint"]
        if item["action"] == "CREATE":
            spec = item["spec"]
            payload = {"field_name": spec["name"], "field_type": spec["field_type"]}
            if spec.get("options"):
                payload["options"] = [{"label": x} for x in spec["options"]]
            if endpoint == "dealFields":
                payload["ui_visibility"] = {
                    "add_visible_flag": True,
                    "details_visible_flag": True,
                    "projects_detail_visible_flag": False,
                }
            client.request("POST", f"/api/v2/{endpoint}", payload)
        elif item["action"] == "ADD_OPTIONS":
            client.request("POST", f"/api/v2/{endpoint}/{item['field_code']}/options",
                           [{"label": x} for x in item["options"]])
        elif item["action"] == "CREATE_PIPELINE":
            pipeline = client.request(
                "POST", "/api/v2/pipelines",
                {"name": item["name"], "is_deal_probability_enabled": False})
            pipeline_id = pipeline.get("id") if isinstance(pipeline, dict) else None
            if not pipeline_id:
                raise RuntimeError("Pipedrive lieferte keine Pipeline-ID")
            for stage in item.get("stages") or []:
                client.request("POST", "/api/v2/stages",
                               {"name": stage, "pipeline_id": pipeline_id})
        elif item["action"] == "CREATE_STAGE":
            client.request("POST", "/api/v2/stages",
                           {"name": item["name"],
                            "pipeline_id": item["pipeline_id"]})


def _stable_target_id(organization_id: str) -> str:
    digest = hashlib.sha256(organization_id.encode("utf-8")).hexdigest()[:24]
    return f"scoutref-target-{digest}"


def apply_seed_organizations(client: Client, manifest: dict) -> list:
    """Legt explizite synthetische Zielorganisationen idempotent an.

    Das generische Manifest enthaelt standardmaessig keine Eintraege. Reale
    Organisationen gehoeren in eine private Instanzkonfiguration und nie in das
    veroeffentlichbare Referenzmodell.
    """
    fields = normalize_remote(
        client.request("GET", "/api/v2/organizationFields?limit=500") or [])
    external = fields.get("scoutref entitäts-id")
    if not external or not external.get("field_code"):
        raise RuntimeError(
            "ScoutRef Entitäts-ID fehlt nach der Feldbereitstellung")
    field_code = external["field_code"]
    report = []
    for organization in manifest.get("seed_organizations") or []:
        name = str(organization.get("name") or "").strip()
        organization_id = str(
            organization.get("organization_id") or "").strip()
        if not name or not organization_id:
            raise RuntimeError(
                "Zielorganisation ohne Name oder organization_id")
        query = urllib.parse.urlencode({
            "term": name, "fields": "name", "exact_match": "true", "limit": 2})
        result = client.request(
            "GET", f"/api/v2/organizations/search?{query}") or {}
        items = result.get("items", []) if isinstance(result, dict) else []
        records = [item.get("item", item) for item in items if isinstance(item, dict)]
        if len(records) > 1:
            raise RuntimeError(
                f"Zielorganisation {name!r} ist mehrfach vorhanden")
        if records:
            report.append({"action": "NOOP", "name": name,
                           "id": records[0].get("id")})
            continue
        created = client.request("POST", "/api/v2/organizations", {
            "name": name,
            "custom_fields": {field_code: _stable_target_id(organization_id)},
        })
        report.append({"action": "CREATE", "name": name,
                       "id": created.get("id") if isinstance(created, dict) else None})
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="fehlende Felder/Optionen wirklich anlegen")
    parser.add_argument("--manifest", default=str(MANIFEST_PATH))
    parser.add_argument(
        "--seed-organizations", action="store_true",
        help="synthetische Zielorganisationen aus einem privaten Manifest anlegen")
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    token = os.environ.get("PIPEDRIVE_API_TOKEN", "").strip()
    if not token:
        print("PIPEDRIVE_API_TOKEN fehlt; keine Kontoabfrage moeglich.")
        return 2
    client = Client(os.environ.get("PIPEDRIVE_API_BASE", "https://api.pipedrive.com"), token)
    plan = build_plan(client, manifest)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if args.apply:
        apply_plan(client, plan)
        print("Feldschema idempotent angewendet.")
        if args.seed_organizations:
            print(json.dumps(apply_seed_organizations(client, manifest),
                             ensure_ascii=False, indent=2))
    else:
        print("Nur Plan. Fuer Schreibzugriffe erneut mit --apply starten.")
    return 0 if not any(x["action"] == "CONFLICT" for x in plan) else 3


if __name__ == "__main__":
    sys.exit(main())
