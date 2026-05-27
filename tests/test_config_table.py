"""
Tests for the Config Table Service — config_relation / CT / GT schema.

Auth: convenience /api/v1/auth/token endpoint (any username accepted).
DB:   SQLite in-memory (see conftest.py) — no Postgres needed.
Run:  docker compose exec service-config-table python -m pytest tests/ -v
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

WRITE_URL = "/api/v1/config/"
READ_URL  = "/api/v1/config/"
HIST_URL  = "/api/v1/config/history"
COMP_URL  = "/api/v1/config/companies"


# ── Helpers ───────────────────────────────────────────────────────────────────

def flat_entry(key: str, val: str) -> dict:
    return {"key": key, "val": val}


def write_payload(proj: str, cmp: str, entries: list, env: str = "production", user_id: str = "testuser") -> dict:
    return {"proj_id": proj, "cmp_id": cmp, "environment": env,
            "user_id": user_id, "entries": entries}


async def approve(client: AsyncClient, uuid: str, reviewer_headers: dict) -> dict:
    res = await client.post(f"/api/v1/config/{uuid}/approve", headers=reviewer_headers)
    assert res.status_code == 200, res.text
    return res.json()


# ── Health ────────────────────────────────────────────────────────────────────

async def test_health(client: AsyncClient):
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


# ── Auth guards ───────────────────────────────────────────────────────────────

async def test_write_requires_auth(client: AsyncClient):
    res = await client.post(WRITE_URL, json=write_payload("P", "C", [flat_entry("k", "v")]))
    assert res.status_code == 401


async def test_read_requires_auth(client: AsyncClient):
    res = await client.get(READ_URL, params={"proj_id": "X", "cmp_id": "Y"})
    assert res.status_code == 401


async def test_history_requires_auth(client: AsyncClient):
    res = await client.get(HIST_URL, params={"proj_id": "X", "cmp_id": "Y"})
    assert res.status_code == 401


# ── Write config ──────────────────────────────────────────────────────────────

async def test_write_config_creates_relation(client: AsyncClient, auth_headers: dict):
    payload = write_payload("WC-Proj-1", "WC-Cmp-1", [
        flat_entry("name-uuid-001", "VALUE:val-uuid-001"),
        flat_entry("name-uuid-002", "VALUE:val-uuid-002"),
    ])
    res = await client.post(WRITE_URL, json=payload, headers=auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert "config_relation_uuid" in body
    assert "date_created" in body
    assert body["environment"] == "production"
    assert len(body["rows"]) == 2
    assert body["rows"][0]["key"] == "name-uuid-001"
    assert body["rows"][0]["val"] == "VALUE:val-uuid-001"


async def test_write_config_with_group_entry(client: AsyncClient, auth_headers: dict):
    payload = {
        "proj_id": "WC-Proj-2", "cmp_id": "WC-Cmp-2",
        "environment": "production", "user_id": "testuser",
        "entries": [{
            "key": "name-tel",
            "val": "GROUP:group-001",
            "group_entries": [
                {"gid": "group-001", "key": "name-phone", "val": "VALUE:val-phone"},
                {"gid": "group-001", "key": "name-tex",   "val": "VALUE:val-tex"},
            ],
        }],
    }
    res = await client.post(WRITE_URL, json=payload, headers=auth_headers)
    assert res.status_code == 201
    assert res.json()["rows"][0]["val"] == "GROUP:group-001"


async def test_write_config_different_environment(client: AsyncClient, auth_headers: dict):
    payload = write_payload("WC-Proj-3", "WC-Cmp-3",
                            [flat_entry("dev-key", "VALUE:dev-val")], env="development")
    res = await client.post(WRITE_URL, json=payload, headers=auth_headers)
    assert res.status_code == 201
    assert res.json()["environment"] == "development"


# ── Soft-delete / versioning ──────────────────────────────────────────────────

async def test_write_twice_soft_deletes_old_version(client: AsyncClient, auth_headers: dict, reviewer_headers: dict):
    proj, cmp = "SD-Proj-1", "SD-Cmp-1"

    r1 = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("k1", "VALUE:v1")]),
        headers=auth_headers)
    assert r1.status_code == 201
    cr1 = r1.json()["config_relation_uuid"]
    await approve(client, cr1, reviewer_headers)

    r2 = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("k2", "VALUE:v2")]),
        headers=auth_headers)
    assert r2.status_code == 201
    cr2 = r2.json()["config_relation_uuid"]
    await approve(client, cr2, reviewer_headers)

    assert cr1 != cr2

    get_res = await client.get(READ_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "production"},
        headers=auth_headers)
    assert get_res.status_code == 200
    body = get_res.json()
    assert body["config_relation_uuid"] == cr2
    assert body["rows"][0]["key"] == "k2"


async def test_soft_delete_scoped_to_environment(client: AsyncClient, auth_headers: dict, reviewer_headers: dict):
    """Writing to production must not affect development's latest pointer."""
    proj, cmp = "SD-Proj-2", "SD-Cmp-2"

    await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("prod-k1", "VALUE:pv1")], env="production"),
        headers=auth_headers)

    dev_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("dev-k1", "VALUE:dv1")], env="development"),
        headers=auth_headers)
    await approve(client, dev_res.json()["config_relation_uuid"], reviewer_headers)

    r3 = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("prod-k2", "VALUE:pv2")], env="production"),
        headers=auth_headers)
    assert r3.status_code == 201

    r_dev = await client.get(READ_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "development"},
        headers=auth_headers)
    assert r_dev.status_code == 200
    assert r_dev.json()["rows"][0]["key"] == "dev-k1"


# ── Read config ───────────────────────────────────────────────────────────────

async def test_read_config_returns_flat_rows(client: AsyncClient, auth_headers: dict, reviewer_headers: dict):
    proj, cmp = "RC-Proj-1", "RC-Cmp-1"
    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("key-a", "VALUE:val-a"), flat_entry("key-b", "VALUE:val-b")]),
        headers=auth_headers)
    await approve(client, write_res.json()["config_relation_uuid"], reviewer_headers)

    res = await client.get(READ_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "production"},
        headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["config_relation_uuid"]
    assert body["environment"] == "production"
    keys = {r["key"] for r in body["rows"]}
    assert keys == {"key-a", "key-b"}


async def test_read_config_404_when_not_found(client: AsyncClient, auth_headers: dict):
    res = await client.get(READ_URL,
        params={"proj_id": "no-proj", "cmp_id": "no-cmp", "environment": "production"},
        headers=auth_headers)
    assert res.status_code == 404


async def test_read_config_404_wrong_environment(client: AsyncClient, auth_headers: dict):
    """Config exists in production but not in staging → 404 for staging."""
    proj, cmp = "RC-Proj-2", "RC-Cmp-2"
    await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("k", "VALUE:v")], env="production"),
        headers=auth_headers)

    res = await client.get(READ_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "staging"},
        headers=auth_headers)
    assert res.status_code == 404


async def test_read_config_rows_are_raw_uuids(client: AsyncClient, auth_headers: dict, reviewer_headers: dict):
    proj, cmp = "RC-Proj-3", "RC-Cmp-3"
    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("some-name-node-uuid", "VALUE:some-value-node-uuid")]),
        headers=auth_headers)
    await approve(client, write_res.json()["config_relation_uuid"], reviewer_headers)

    res = await client.get(READ_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "production"},
        headers=auth_headers)
    assert res.status_code == 200
    row = res.json()["rows"][0]
    assert row["key"] == "some-name-node-uuid"
    assert row["val"] == "VALUE:some-value-node-uuid"


# ── Environment isolation ─────────────────────────────────────────────────────

async def test_environment_isolation(client: AsyncClient, auth_headers: dict, reviewer_headers: dict):
    """Each environment has a completely independent config history."""
    proj, cmp = "EI-Proj-1", "EI-Cmp-1"

    r_prod = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("prod-key", "VALUE:prod-val")], env="production"),
        headers=auth_headers)
    await approve(client, r_prod.json()["config_relation_uuid"], reviewer_headers)

    r_dev = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("dev-key", "VALUE:dev-val")], env="development"),
        headers=auth_headers)
    await approve(client, r_dev.json()["config_relation_uuid"], reviewer_headers)

    r_staging = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("staging-key", "VALUE:staging-val")], env="staging"),
        headers=auth_headers)
    await approve(client, r_staging.json()["config_relation_uuid"], reviewer_headers)

    r_prod_get = await client.get(READ_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "production"},
        headers=auth_headers)
    r_dev_get = await client.get(READ_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "development"},
        headers=auth_headers)
    r_staging_get = await client.get(READ_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "staging"},
        headers=auth_headers)

    assert r_prod_get.json()["rows"][0]["key"] == "prod-key"
    assert r_dev_get.json()["rows"][0]["key"] == "dev-key"
    assert r_staging_get.json()["rows"][0]["key"] == "staging-key"


# ── History endpoint ──────────────────────────────────────────────────────────

async def test_history_returns_all_snapshots(client: AsyncClient, auth_headers: dict, reviewer_headers: dict):
    proj, cmp = "HI-Proj-1", "HI-Cmp-1"

    uuids = []
    for i in range(3):
        r = await client.post(WRITE_URL,
            json=write_payload(proj, cmp, [flat_entry(f"k{i}", f"VALUE:v{i}")]),
            headers=auth_headers)
        uuids.append(r.json()["config_relation_uuid"])

    # Approve all three; each approval retires the previous latest
    for uuid in uuids:
        await approve(client, uuid, reviewer_headers)

    res = await client.get(HIST_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "production"},
        headers=auth_headers)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 3

    # newest first; only the last approved is latest
    assert items[0]["is_latest"] is True
    assert items[1]["is_latest"] is False
    assert items[2]["is_latest"] is False

    for item in items:
        assert "config_relation_uuid" in item
        assert "date_created" in item
        assert "entry_count" in item
        assert item["environment"] == "production"


async def test_history_scoped_to_environment(client: AsyncClient, auth_headers: dict):
    """History for production must not include development snapshots."""
    proj, cmp = "HI-Proj-2", "HI-Cmp-2"

    await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("p1", "VALUE:pv1")], env="production"),
        headers=auth_headers)
    await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("p2", "VALUE:pv2")], env="production"),
        headers=auth_headers)
    await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("d1", "VALUE:dv1")], env="development"),
        headers=auth_headers)

    prod_hist = await client.get(HIST_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "production"},
        headers=auth_headers)
    dev_hist = await client.get(HIST_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "development"},
        headers=auth_headers)

    assert len(prod_hist.json()) == 2
    assert len(dev_hist.json()) == 1


async def test_history_empty_for_unknown(client: AsyncClient, auth_headers: dict):
    res = await client.get(HIST_URL,
        params={"proj_id": "nonexistent", "cmp_id": "nonexistent", "environment": "production"},
        headers=auth_headers)
    assert res.status_code == 200
    assert res.json() == []


# ── Get by UUID ───────────────────────────────────────────────────────────────

async def test_get_config_by_uuid(client: AsyncClient, auth_headers: dict):
    proj, cmp = "UUID-Proj-1", "UUID-Cmp-1"
    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("uuid-key", "VALUE:uuid-val")]),
        headers=auth_headers)
    assert write_res.status_code == 201
    uuid = write_res.json()["config_relation_uuid"]

    res = await client.get(f"/api/v1/config/{uuid}", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["config_relation_uuid"] == uuid
    assert body["rows"][0]["key"] == "uuid-key"


async def test_get_config_by_uuid_not_found(client: AsyncClient, auth_headers: dict):
    res = await client.get("/api/v1/config/nonexistent-uuid-000", headers=auth_headers)
    assert res.status_code == 404


# ── Companies with config ─────────────────────────────────────────────────────

async def test_companies_with_config(client: AsyncClient, auth_headers: dict):
    proj = "CWC-Proj-1"

    for cmp in ["CWC-CmpA", "CWC-CmpB", "CWC-CmpC"]:
        await client.post(WRITE_URL,
            json=write_payload(proj, cmp, [flat_entry("k", "VALUE:v")]),
            headers=auth_headers)

    res = await client.get(COMP_URL, params={"proj_id": proj}, headers=auth_headers)
    assert res.status_code == 200
    companies = res.json()
    assert set(companies) == {"CWC-CmpA", "CWC-CmpB", "CWC-CmpC"}


async def test_companies_with_config_across_environments(client: AsyncClient, auth_headers: dict):
    """Companies endpoint shows a company if it has config in ANY environment."""
    proj = "CWC-Proj-2"
    await client.post(WRITE_URL,
        json=write_payload(proj, "CWC-MultiEnv-Cmp", [flat_entry("k", "VALUE:v")], env="development"),
        headers=auth_headers)

    res = await client.get(COMP_URL, params={"proj_id": proj}, headers=auth_headers)
    assert res.status_code == 200
    assert "CWC-MultiEnv-Cmp" in res.json()


# ── Promote config ────────────────────────────────────────────────────────────

PROMOTE_URL = "/api/v1/config/promote"


async def test_promote_copies_latest_to_target_env(client: AsyncClient, auth_headers: dict, reviewer_headers: dict):
    proj, cmp = "PR-Proj-1", "PR-Cmp-1"

    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [
            flat_entry("key-alpha", "VALUE:val-alpha"),
            flat_entry("key-beta", "VALUE:val-beta"),
        ], env="development"),
        headers=auth_headers)
    await approve(client, write_res.json()["config_relation_uuid"], reviewer_headers)

    res = await client.post(PROMOTE_URL, json={
        "proj_id": proj, "cmp_id": cmp,
        "from_environment": "development", "to_environment": "testing",
    }, headers=auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["environment"] == "testing"
    assert len(body["rows"]) == 2
    keys = {r["key"] for r in body["rows"]}
    assert keys == {"key-alpha", "key-beta"}


async def test_promote_creates_new_latest_in_target(client: AsyncClient, auth_headers: dict, reviewer_headers: dict):
    proj, cmp = "PR-Proj-2", "PR-Cmp-2"

    await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("old-key", "VALUE:old")], env="testing"),
        headers=auth_headers)

    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("new-key", "VALUE:new")], env="development"),
        headers=auth_headers)
    await approve(client, write_res.json()["config_relation_uuid"], reviewer_headers)

    await client.post(PROMOTE_URL, json={
        "proj_id": proj, "cmp_id": cmp,
        "from_environment": "development", "to_environment": "testing",
    }, headers=auth_headers)

    read_res = await client.get(READ_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "testing"},
        headers=auth_headers)
    assert read_res.status_code == 200
    assert read_res.json()["rows"][0]["key"] == "new-key"


async def test_promote_does_not_affect_source(client: AsyncClient, auth_headers: dict, reviewer_headers: dict):
    proj, cmp = "PR-Proj-3", "PR-Cmp-3"

    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("dev-key", "VALUE:dev")], env="development"),
        headers=auth_headers)
    await approve(client, write_res.json()["config_relation_uuid"], reviewer_headers)

    await client.post(PROMOTE_URL, json={
        "proj_id": proj, "cmp_id": cmp,
        "from_environment": "development", "to_environment": "testing",
    }, headers=auth_headers)

    dev_res = await client.get(READ_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "development"},
        headers=auth_headers)
    assert dev_res.status_code == 200
    assert dev_res.json()["rows"][0]["key"] == "dev-key"


async def test_promote_404_when_source_empty(client: AsyncClient, auth_headers: dict):
    res = await client.post(PROMOTE_URL, json={
        "proj_id": "no-proj", "cmp_id": "no-cmp",
        "from_environment": "development", "to_environment": "testing",
    }, headers=auth_headers)
    assert res.status_code == 404


async def test_promote_same_env_returns_400(client: AsyncClient, auth_headers: dict):
    res = await client.post(PROMOTE_URL, json={
        "proj_id": "any", "cmp_id": "any",
        "from_environment": "production", "to_environment": "production",
    }, headers=auth_headers)
    assert res.status_code == 400


async def test_promote_requires_auth(client: AsyncClient):
    res = await client.post(PROMOTE_URL, json={
        "proj_id": "p", "cmp_id": "c",
        "from_environment": "development", "to_environment": "testing",
    })
    assert res.status_code == 401


# ── Promote by UUID ───────────────────────────────────────────────────────────

async def test_promote_by_uuid_copies_snapshot(client: AsyncClient, auth_headers: dict):
    proj, cmp = "PBU-Proj-1", "PBU-Cmp-1"

    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [
            flat_entry("uuid-key-1", "VALUE:uuid-val-1"),
            flat_entry("uuid-key-2", "VALUE:uuid-val-2"),
        ], env="development"),
        headers=auth_headers)
    assert write_res.status_code == 201
    snapshot_uuid = write_res.json()["config_relation_uuid"]

    res = await client.post(f"/api/v1/config/{snapshot_uuid}/promote",
        json={"to_environment": "testing"},
        headers=auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["environment"] == "testing"
    assert len(body["rows"]) == 2
    keys = {r["key"] for r in body["rows"]}
    assert keys == {"uuid-key-1", "uuid-key-2"}


async def test_promote_by_uuid_makes_new_latest_in_target(client: AsyncClient, auth_headers: dict):
    proj, cmp = "PBU-Proj-2", "PBU-Cmp-2"

    await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("old-key", "VALUE:old")], env="testing"),
        headers=auth_headers)

    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("dev-key", "VALUE:dev")], env="development"),
        headers=auth_headers)
    snapshot_uuid = write_res.json()["config_relation_uuid"]

    await client.post(f"/api/v1/config/{snapshot_uuid}/promote",
        json={"to_environment": "testing"},
        headers=auth_headers)

    read_res = await client.get(READ_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "testing"},
        headers=auth_headers)
    assert read_res.status_code == 200
    assert read_res.json()["rows"][0]["key"] == "dev-key"


async def test_promote_by_uuid_404_for_missing_snapshot(client: AsyncClient, auth_headers: dict):
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    res = await client.post(f"/api/v1/config/{fake_uuid}/promote",
        json={"to_environment": "testing"},
        headers=auth_headers)
    assert res.status_code == 404


async def test_promote_by_uuid_requires_auth(client: AsyncClient, auth_headers: dict):
    write_res = await client.post(WRITE_URL,
        json=write_payload("PBU-P3", "PBU-C3", [flat_entry("k", "VALUE:v")], env="development"),
        headers=auth_headers)
    snapshot_uuid = write_res.json()["config_relation_uuid"]

    res = await client.post(f"/api/v1/config/{snapshot_uuid}/promote",
        json={"to_environment": "testing"})
    assert res.status_code == 401


async def test_promote_by_uuid_historical_snapshot(client: AsyncClient, auth_headers: dict):
    """Promote a non-latest (historical) snapshot by UUID."""
    proj, cmp = "PBU-Proj-4", "PBU-Cmp-4"

    first_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("historical-key", "VALUE:hist")], env="development"),
        headers=auth_headers)
    historical_uuid = first_res.json()["config_relation_uuid"]

    await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("latest-key", "VALUE:latest")], env="development"),
        headers=auth_headers)

    res = await client.post(f"/api/v1/config/{historical_uuid}/promote",
        json={"to_environment": "staging"},
        headers=auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["environment"] == "staging"
    assert body["rows"][0]["key"] == "historical-key"


# ── Approval workflow ─────────────────────────────────────────────────────────

async def test_write_config_creates_pending_snapshot(client: AsyncClient, auth_headers: dict):
    proj, cmp = "AP-Proj-1", "AP-Cmp-1"
    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("k", "VALUE:v")]),
        headers=auth_headers)
    assert write_res.status_code == 201
    uuid = write_res.json()["config_relation_uuid"]

    hist = await client.get(HIST_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "production"},
        headers=auth_headers)
    items = hist.json()
    assert len(items) == 1
    assert items[0]["config_relation_uuid"] == uuid
    assert items[0]["approval_status"] == "pending"
    assert items[0]["is_latest"] is False


async def test_approve_config(client: AsyncClient, auth_headers: dict, reviewer_headers: dict):
    proj, cmp = "AP-Proj-2", "AP-Cmp-2"
    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("k", "VALUE:v")]),
        headers=auth_headers)
    uuid = write_res.json()["config_relation_uuid"]

    ap_res = await client.post(f"/api/v1/config/{uuid}/approve", headers=reviewer_headers)
    assert ap_res.status_code == 200
    body = ap_res.json()
    assert body["approval_status"] == "approved"
    assert body["approved_by"] == "reviewer"

    get_res = await client.get(READ_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "production"},
        headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["config_relation_uuid"] == uuid


async def test_approve_replaces_previous_latest(client: AsyncClient, auth_headers: dict, reviewer_headers: dict):
    proj, cmp = "AP-Proj-3", "AP-Cmp-3"

    r1 = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("k1", "VALUE:v1")]),
        headers=auth_headers)
    cr1 = r1.json()["config_relation_uuid"]
    await approve(client, cr1, reviewer_headers)

    r2 = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("k2", "VALUE:v2")]),
        headers=auth_headers)
    cr2 = r2.json()["config_relation_uuid"]
    await approve(client, cr2, reviewer_headers)

    get_res = await client.get(READ_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "production"},
        headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["config_relation_uuid"] == cr2


async def test_reject_config(client: AsyncClient, auth_headers: dict, reviewer_headers: dict):
    proj, cmp = "AP-Proj-4", "AP-Cmp-4"
    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("k", "VALUE:v")]),
        headers=auth_headers)
    uuid = write_res.json()["config_relation_uuid"]

    rej_res = await client.post(f"/api/v1/config/{uuid}/reject",
        json={"reason": None}, headers=reviewer_headers)
    assert rej_res.status_code == 200
    assert rej_res.json()["approval_status"] == "rejected"

    get_res = await client.get(READ_URL,
        params={"proj_id": proj, "cmp_id": cmp, "environment": "production"},
        headers=auth_headers)
    assert get_res.status_code == 404


async def test_reject_with_reason(client: AsyncClient, auth_headers: dict, reviewer_headers: dict):
    proj, cmp = "AP-Proj-5", "AP-Cmp-5"
    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("k", "VALUE:v")]),
        headers=auth_headers)
    uuid = write_res.json()["config_relation_uuid"]

    rej_res = await client.post(f"/api/v1/config/{uuid}/reject",
        json={"reason": "values wrong"}, headers=reviewer_headers)
    assert rej_res.status_code == 200
    assert rej_res.json()["rejection_reason"] == "values wrong"


async def test_approve_requires_reviewer_role(client: AsyncClient, auth_headers: dict):
    proj, cmp = "AP-Proj-6", "AP-Cmp-6"
    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("k", "VALUE:v")]),
        headers=auth_headers)
    uuid = write_res.json()["config_relation_uuid"]

    res = await client.post(f"/api/v1/config/{uuid}/approve", headers=auth_headers)
    assert res.status_code == 403


async def test_approve_requires_non_self(client: AsyncClient, reviewer_headers: dict):
    proj, cmp = "AP-Proj-7", "AP-Cmp-7"
    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("k", "VALUE:v")], user_id="reviewer"),
        headers=reviewer_headers)
    uuid = write_res.json()["config_relation_uuid"]

    res = await client.post(f"/api/v1/config/{uuid}/approve", headers=reviewer_headers)
    assert res.status_code == 403


async def test_approve_requires_auth(client: AsyncClient, auth_headers: dict):
    proj, cmp = "AP-Proj-8", "AP-Cmp-8"
    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("k", "VALUE:v")]),
        headers=auth_headers)
    uuid = write_res.json()["config_relation_uuid"]

    res = await client.post(f"/api/v1/config/{uuid}/approve")
    assert res.status_code == 401


async def test_approve_already_approved(client: AsyncClient, auth_headers: dict, reviewer_headers: dict):
    proj, cmp = "AP-Proj-9", "AP-Cmp-9"
    write_res = await client.post(WRITE_URL,
        json=write_payload(proj, cmp, [flat_entry("k", "VALUE:v")]),
        headers=auth_headers)
    uuid = write_res.json()["config_relation_uuid"]

    await approve(client, uuid, reviewer_headers)

    res = await client.post(f"/api/v1/config/{uuid}/approve", headers=reviewer_headers)
    assert res.status_code == 400
