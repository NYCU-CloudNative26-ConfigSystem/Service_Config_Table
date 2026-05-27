"""
Tests for the Project Template feature — draft keys + publish versioning.

Auth: convenience /api/v1/auth/token endpoint.
DB:   SQLite in-memory (see conftest.py).
Run:  docker compose exec service-config-table python -m pytest tests/ -v
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

PROJ_URL = "/api/v1/projects"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def create_project(client: AsyncClient, headers: dict, proj_id: str, name: str | None = None):
    return await client.post(PROJ_URL, json={
        "proj_id": proj_id,
        "display_name": name or proj_id,
    }, headers=headers)


def keys_url(proj_id: str) -> str:
    return f"{PROJ_URL}/{proj_id}/template/keys"


def versions_url(proj_id: str) -> str:
    return f"{PROJ_URL}/{proj_id}/template/versions"


def publish_url(proj_id: str) -> str:
    return f"{PROJ_URL}/{proj_id}/template/publish"


def published_keys_url(proj_id: str) -> str:
    return f"{PROJ_URL}/{proj_id}/template/published-keys"


# ── Add template key ──────────────────────────────────────────────────────────

async def test_add_template_key(client: AsyncClient, auth_headers: dict):
    proj = "TK-Proj-001"
    await create_project(client, auth_headers, proj)

    res = await client.post(keys_url(proj), json={"alias": "phone"}, headers=auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["alias"] == "phone"
    assert body["proj_id"] == proj
    assert "uuid" in body
    assert "date_created" in body


async def test_add_multiple_template_keys(client: AsyncClient, auth_headers: dict):
    proj = "TK-Proj-002"
    await create_project(client, auth_headers, proj)

    for alias in ["email", "address", "phone"]:
        r = await client.post(keys_url(proj), json={"alias": alias}, headers=auth_headers)
        assert r.status_code == 201

    res = await client.get(keys_url(proj), headers=auth_headers)
    assert res.status_code == 200
    aliases = [k["alias"] for k in res.json()]
    assert set(aliases) == {"email", "address", "phone"}


async def test_add_duplicate_key_returns_409(client: AsyncClient, auth_headers: dict):
    proj = "TK-Proj-003"
    await create_project(client, auth_headers, proj)

    await client.post(keys_url(proj), json={"alias": "phone"}, headers=auth_headers)
    res = await client.post(keys_url(proj), json={"alias": "phone"}, headers=auth_headers)
    assert res.status_code == 409


async def test_only_creator_can_add_key(
    client: AsyncClient, auth_headers: dict, other_headers: dict
):
    proj = "TK-Proj-004"
    await create_project(client, auth_headers, proj)

    res = await client.post(keys_url(proj), json={"alias": "secret"}, headers=other_headers)
    assert res.status_code == 403


# ── Remove template key ───────────────────────────────────────────────────────

async def test_remove_template_key(client: AsyncClient, auth_headers: dict):
    proj = "TK-Proj-005"
    await create_project(client, auth_headers, proj)

    add_res = await client.post(keys_url(proj), json={"alias": "temp-key"}, headers=auth_headers)
    assert add_res.status_code == 201
    key_uuid = add_res.json()["uuid"]

    del_res = await client.delete(f"{keys_url(proj)}/{key_uuid}", headers=auth_headers)
    assert del_res.status_code == 204

    list_res = await client.get(keys_url(proj), headers=auth_headers)
    assert all(k["uuid"] != key_uuid for k in list_res.json())


async def test_remove_nonexistent_key_returns_404(client: AsyncClient, auth_headers: dict):
    proj = "TK-Proj-006"
    await create_project(client, auth_headers, proj)

    res = await client.delete(f"{keys_url(proj)}/no-such-uuid", headers=auth_headers)
    assert res.status_code == 404


async def test_only_creator_can_remove_key(
    client: AsyncClient, auth_headers: dict, other_headers: dict
):
    proj = "TK-Proj-007"
    await create_project(client, auth_headers, proj)

    add_res = await client.post(keys_url(proj), json={"alias": "guarded"}, headers=auth_headers)
    key_uuid = add_res.json()["uuid"]

    res = await client.delete(f"{keys_url(proj)}/{key_uuid}", headers=other_headers)
    assert res.status_code == 403


# ── Publish template ──────────────────────────────────────────────────────────

async def test_publish_creates_version(client: AsyncClient, auth_headers: dict):
    proj = "TK-Proj-010"
    await create_project(client, auth_headers, proj)
    await client.post(keys_url(proj), json={"alias": "email"}, headers=auth_headers)
    await client.post(keys_url(proj), json={"alias": "phone"}, headers=auth_headers)

    res = await client.post(publish_url(proj), headers=auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["version_number"] == 1
    assert body["latest"] is True
    assert set(body["keys"]) == {"email", "phone"}
    assert body["proj_id"] == proj


async def test_publish_increments_version_number(client: AsyncClient, auth_headers: dict):
    proj = "TK-Proj-011"
    await create_project(client, auth_headers, proj)
    await client.post(keys_url(proj), json={"alias": "key-a"}, headers=auth_headers)

    r1 = await client.post(publish_url(proj), headers=auth_headers)
    assert r1.json()["version_number"] == 1

    # Add another key and publish again
    await client.post(keys_url(proj), json={"alias": "key-b"}, headers=auth_headers)
    r2 = await client.post(publish_url(proj), headers=auth_headers)
    assert r2.json()["version_number"] == 2
    assert r2.json()["latest"] is True


async def test_only_latest_version_is_marked_latest(client: AsyncClient, auth_headers: dict):
    proj = "TK-Proj-012"
    await create_project(client, auth_headers, proj)
    await client.post(keys_url(proj), json={"alias": "k"}, headers=auth_headers)

    await client.post(publish_url(proj), headers=auth_headers)
    await client.post(publish_url(proj), headers=auth_headers)

    versions_res = await client.get(versions_url(proj), headers=auth_headers)
    assert versions_res.status_code == 200
    versions = versions_res.json()
    assert len(versions) == 2

    latest_flags = [v["latest"] for v in versions]
    assert latest_flags.count(True) == 1
    assert versions[0]["latest"] is True   # newest first


async def test_only_creator_can_publish(
    client: AsyncClient, auth_headers: dict, other_headers: dict
):
    proj = "TK-Proj-013"
    await create_project(client, auth_headers, proj)
    await client.post(keys_url(proj), json={"alias": "k"}, headers=auth_headers)

    res = await client.post(publish_url(proj), headers=other_headers)
    assert res.status_code == 403


# ── Published keys endpoint ───────────────────────────────────────────────────

async def test_published_keys_empty_before_publish(client: AsyncClient, auth_headers: dict):
    proj = "TK-Proj-020"
    await create_project(client, auth_headers, proj)

    res = await client.get(published_keys_url(proj), headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["version_uuid"] is None
    assert body["keys"] == []


async def test_published_keys_returns_latest_version_keys(client: AsyncClient, auth_headers: dict):
    proj = "TK-Proj-021"
    await create_project(client, auth_headers, proj)

    # Publish v1 with one key
    await client.post(keys_url(proj), json={"alias": "alpha"}, headers=auth_headers)
    await client.post(publish_url(proj), headers=auth_headers)

    # Publish v2 with two keys
    await client.post(keys_url(proj), json={"alias": "beta"}, headers=auth_headers)
    pub_res = await client.post(publish_url(proj), headers=auth_headers)
    v2_uuid = pub_res.json()["uuid"]

    res = await client.get(published_keys_url(proj), headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["version_uuid"] == v2_uuid
    assert set(body["keys"]) == {"alpha", "beta"}


# ── Template version history ──────────────────────────────────────────────────

async def test_get_template_versions(client: AsyncClient, auth_headers: dict):
    proj = "TK-Proj-030"
    await create_project(client, auth_headers, proj)
    await client.post(keys_url(proj), json={"alias": "k1"}, headers=auth_headers)
    await client.post(publish_url(proj), headers=auth_headers)
    await client.post(keys_url(proj), json={"alias": "k2"}, headers=auth_headers)
    await client.post(publish_url(proj), headers=auth_headers)

    res = await client.get(versions_url(proj), headers=auth_headers)
    assert res.status_code == 200
    versions = res.json()
    assert len(versions) == 2
    # newest first
    assert versions[0]["version_number"] == 2
    assert versions[1]["version_number"] == 1
