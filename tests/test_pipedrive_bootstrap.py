from pipedrive_bootstrap import (api_root, apply_seed_organizations, plan_entity,
                                 plan_pipeline)


def test_api_root_removes_legacy_suffix():
    assert api_root("https://example.pipedrive.com/api/v1") == "https://example.pipedrive.com"
    assert api_root("https://api.pipedrive.com/api/v2") == "https://api.pipedrive.com"


def test_plan_is_idempotent_and_fails_closed_on_type_conflict():
    expected = [
        {"name": "ScoutRef Relation-ID", "field_type": "varchar"},
        {"name": "Zielorganisation", "field_type": "org"},
        {"name": "Evidenzstatus Bewertung", "field_type": "enum",
         "options": ["Verifiziert", "Nicht ausreichend"]},
    ]
    remote = [
        {"field_name": "ScoutRef Relation-ID", "field_type": "varchar", "field_code": "a"},
        {"field_name": "Zielorganisation", "field_type": "varchar", "field_code": "b"},
        {"field_name": "Evidenzstatus Bewertung", "field_type": "enum",
         "field_code": "c", "options": [{"label": "Verifiziert"}]},
    ]
    plan = plan_entity(expected, remote, "dealFields")
    assert [x["action"] for x in plan] == ["NOOP", "CONFLICT", "ADD_OPTIONS"]
    assert plan[2]["options"] == ["Nicht ausreichend"]


class _PipelineClient:
    def request(self, method, path, payload=None):
        if path.startswith("/api/v2/pipelines"):
            return [{"id": 7, "name": "ScoutRef Scouting"}]
        if path.startswith("/api/v2/stages"):
            return [{"id": 1, "name": "Vorqualifiziert"}]
        raise AssertionError(path)


def test_pipeline_plan_only_adds_missing_stages():
    plan = plan_pipeline(_PipelineClient(), {
        "name": "ScoutRef Scouting",
        "stages": ["Vorqualifiziert", "Kontakt vorbereitet"],
    })
    assert [item["action"] for item in plan] == ["NOOP", "NOOP", "CREATE_STAGE"]
    assert plan[-1]["pipeline_id"] == 7


class _OrganizationClient:
    def __init__(self):
        self.created = []

    def request(self, method, path, payload=None):
        if path.startswith("/api/v2/organizationFields"):
            return [{"field_name": "ScoutRef Entitäts-ID", "field_type": "varchar",
                     "field_code": "external_hash"}]
        if path.startswith("/api/v2/organizations/search"):
            return {"items": []}
        if method == "POST" and path == "/api/v2/organizations":
            self.created.append(payload)
            return {"id": 42}
        raise AssertionError((method, path))


def test_target_seed_uses_stable_external_id_and_no_invented_profile_data():
    client = _OrganizationClient()
    report = apply_seed_organizations(client, {
        "seed_organizations": [{
            "organization_id": "demo_manufacturing",
            "name": "Demo Manufacturing",
        }]
    })
    assert report == [
        {"action": "CREATE", "name": "Demo Manufacturing", "id": 42}
    ]
    assert client.created[0]["name"] == "Demo Manufacturing"
    assert client.created[0]["custom_fields"]["external_hash"].startswith(
        "scoutref-target-")
    assert set(client.created[0]) == {"name", "custom_fields"}
