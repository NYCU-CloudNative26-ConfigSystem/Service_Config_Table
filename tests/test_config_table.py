"""
Tests for the Config Table Service — new schema (config_relation / CT / GT).

Auth is handled via the convenience /api/v1/auth/token endpoint.
DB is SQLite in-memory (see conftest.py).
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

WRITE_URL = "/api/v1/config/"
READ_URL = "/api/v1/config/"


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def flat_entry(key: str, val: str):
    return {"key": key, "val": val}


def group_entry(key: str, gid: str, children: list):
    return {"key": key, "val": f"GROUP:{gid}", "group_entries": children}


SAMPLE_PAYLOAD = {
    "proj_id": "ProjectA",
    "cmp_id": "CMPA",
    "user_id": "testuser",
    "entries": [
        flat_entry("name-uuid-001", "VALUE:val-uuid-001"),
        flat_entry("name-uuid-002", "VALUE:val-uuid-002"),
    ],
}


# ── Health ─────────────────────────────────────────────────────────────────────


async def test_health(client: AsyncClient):
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


# ── Auth guard ────────────────────────────────────────────────────────────────


async def test_write_requires_auth(client: AsyncClient):
    res = await client.post(WRITE_URL, json=SAMPLE_PAYLOAD)
    assert res.status_code == 401


async def test_read_requires_auth(client: AsyncClient):
    res = await client.get(READ_URL, params={"proj_id": "X", "cmp_id": "Y"})
    assert res.status_code == 401


# ── Write config ──────────────────────────────────────────────────────────────


async def test_write_config_creates_relation(client: AsyncClient, auth_headers: dict):
    res = await client.post(WRITE_URL, json=SAMPLE_PAYLOAD, headers=auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert "config_relation_uuid" in body
    assert "date_created" in body
    assert len(body["rows"]) == 2
    assert body["rows"][0]["key"] == "name-uuid-001"
    assert body["rows"][0]["val"] == "VALUE:val-uuid-001"


async def test_write_config_with_group_entry(client: AsyncClient, auth_headers: dict):
    payload = {
        "proj_id": "ProjectB",
        "cmp_id": "CMPB",
        "user_id": "testuser",
        "entries": [
            {
                "key": "name-tel",
                "val": "GROUP:group-001",
                "group_entries": [
                    {"gid": "group-001", "key": "name-phone", "val": "VALUE:val-phone"},
                    {"gid": "group-001", "key": "name-tex",   "val": "VALUE:val-tex"},
                ],
            }
        ],
    }
    res = await client.post(WRITE_URL, json=payload, headers=auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["rows"][0]["val"] == "GROUP:group-001"


# ── Soft delete / versioning ──────────────────────────────────────────────────


async def test_write_twice_soft_deletes_old_version(client: AsyncClient, auth_headers: dict):
    proj = "ProjectC"
    cmp = "CMPC"
    base = {"proj_id": proj, "cmp_id": cmp, "user_id": "testuser"}

    res1 = await client.post(WRITE_URL, json={**base, "entries": [flat_entry("k1", "VALUE:v1")]}, headers=auth_headers)
    assert res1.status_code == 201
    cr1_uuid = res1.json()["config_relation_uuid"]

    res2 = await client.post(WRITE_URL, json={**base, "entries": [flat_entry("k2", "VALUE:v2")]}, headers=auth_headers)
    assert res2.status_code == 201
    cr2_uuid = res2.json()["config_relation_uuid"]

    assert cr1_uuid != cr2_uuid

    # GET should return the latest version
    get_res = await client.get(READ_URL, params={"proj_id": proj, "cmp_id": cmp}, headers=auth_headers)
    assert get_res.status_code == 200
    latest = get_res.json()
    assert latest["config_relation_uuid"] == cr2_uuid
    assert latest["rows"][0]["key"] == "k2"


# ── Read config ───────────────────────────────────────────────────────────────


async def test_read_config_returns_flat_rows(client: AsyncClient, auth_headers: dict):
    proj, cmp = "ProjectD", "CMPD"
    await client.post(
        WRITE_URL,
        json={"proj_id": proj, "cmp_id": cmp, "user_id": "testuser",
              "entries": [flat_entry("key-a", "VALUE:val-a"), flat_entry("key-b", "VALUE:val-b")]},
        headers=auth_headers,
    )
    res = await client.get(READ_URL, params={"proj_id": proj, "cmp_id": cmp}, headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["config_relation_uuid"]
    rows = body["rows"]
    assert len(rows) == 2
    keys = {r["key"] for r in rows}
    assert keys == {"key-a", "key-b"}


async def test_read_config_returns_404_when_not_found(client: AsyncClient, auth_headers: dict):
    res = await client.get(READ_URL, params={"proj_id": "noproject", "cmp_id": "nocmp"}, headers=auth_headers)
    assert res.status_code == 404


async def test_read_config_rows_are_raw_uuids(client: AsyncClient, auth_headers: dict):
    """Rows must contain raw UUID strings, not resolved names or values."""
    proj, cmp = "ProjectE", "CMPE"
    await client.post(
        WRITE_URL,
        json={"proj_id": proj, "cmp_id": cmp, "user_id": "testuser",
              "entries": [flat_entry("some-name-node-uuid", "VALUE:some-value-node-uuid")]},
        headers=auth_headers,
    )
    res = await client.get(READ_URL, params={"proj_id": proj, "cmp_id": cmp}, headers=auth_headers)
    assert res.status_code == 200
    row = res.json()["rows"][0]
    # key and val are raw UUIDs/references, not resolved names
    assert row["key"] == "some-name-node-uuid"
    assert row["val"] == "VALUE:some-value-node-uuid"
