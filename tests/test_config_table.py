"""
Integration tests for the Config Table Service.

The test database is SQLite (in-memory via aiosqlite) so no external
services are required.  Config Service validation is exercised via
monkey-patching.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Auth token endpoint
# ---------------------------------------------------------------------------


async def test_get_token(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/token",
        data={"username": "alice", "password": "secret", "client_id": "acme"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert "access_token" in body


async def test_get_token_missing_credentials(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/token",
        data={"username": "", "password": ""},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Unauthenticated access is rejected
# ---------------------------------------------------------------------------


async def test_list_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/configs/")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# CRUD — happy paths
# ---------------------------------------------------------------------------


async def test_create_entry(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/v1/configs/",
        json={"from_id": "key-001", "to_id": "val-001", "company": "testcorp"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["from_id"] == "key-001"
    assert body["to_id"] == "val-001"
    assert body["creator"] == "testuser"
    assert body["company"] == "testcorp"
    assert "id" in body
    assert "create_time" in body


async def test_get_entry(client: AsyncClient, auth_headers: dict):
    # create first
    create_resp = await client.post(
        "/api/v1/configs/",
        json={"from_id": "key-002", "to_id": "val-002", "company": "testcorp"},
        headers=auth_headers,
    )
    entry_id = create_resp.json()["id"]

    response = await client.get(f"/api/v1/configs/{entry_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == entry_id


async def test_get_entry_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        "/api/v1/configs/nonexistent-uuid", headers=auth_headers
    )
    assert response.status_code == 404


async def test_list_entries(client: AsyncClient, auth_headers: dict):
    # create two entries
    for i in range(2):
        await client.post(
            "/api/v1/configs/",
            json={
                "from_id": f"key-list-{i}",
                "to_id": f"val-list-{i}",
                "company": "testcorp",
            },
            headers=auth_headers,
        )

    response = await client.get("/api/v1/configs/", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) >= 2


async def test_list_entries_filter_by_creator(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        "/api/v1/configs/?creator=testuser", headers=auth_headers
    )
    assert response.status_code == 200
    for entry in response.json():
        assert entry["creator"] == "testuser"


async def test_update_entry(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/configs/",
        json={"from_id": "key-upd", "to_id": "val-upd", "company": "testcorp"},
        headers=auth_headers,
    )
    entry_id = create_resp.json()["id"]

    response = await client.put(
        f"/api/v1/configs/{entry_id}",
        json={"to_id": "val-upd-new"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["to_id"] == "val-upd-new"


async def test_delete_entry(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/configs/",
        json={"from_id": "key-del", "to_id": "val-del", "company": "testcorp"},
        headers=auth_headers,
    )
    entry_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/v1/configs/{entry_id}", headers=auth_headers
    )
    assert del_resp.status_code == 204

    get_resp = await client.get(
        f"/api/v1/configs/{entry_id}", headers=auth_headers
    )
    assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Ownership enforcement
# ---------------------------------------------------------------------------


async def test_update_entry_forbidden_for_non_creator(
    client: AsyncClient, auth_headers: dict, other_headers: dict
):
    create_resp = await client.post(
        "/api/v1/configs/",
        json={"from_id": "key-own", "to_id": "val-own", "company": "testcorp"},
        headers=auth_headers,
    )
    entry_id = create_resp.json()["id"]

    response = await client.put(
        f"/api/v1/configs/{entry_id}",
        json={"to_id": "val-hacked"},
        headers=other_headers,
    )
    assert response.status_code == 403


async def test_delete_entry_forbidden_for_non_creator(
    client: AsyncClient, auth_headers: dict, other_headers: dict
):
    create_resp = await client.post(
        "/api/v1/configs/",
        json={"from_id": "key-own2", "to_id": "val-own2", "company": "testcorp"},
        headers=auth_headers,
    )
    entry_id = create_resp.json()["id"]

    response = await client.delete(
        f"/api/v1/configs/{entry_id}", headers=other_headers
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Config Service validation
# ---------------------------------------------------------------------------


async def test_create_entry_invalid_key_id(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    import app.services.config_table_service as svc_module

    async def fake_validate_key_id(key_id: str) -> bool:
        return False

    monkeypatch.setattr(svc_module, "validate_key_id", fake_validate_key_id)

    response = await client.post(
        "/api/v1/configs/",
        json={"from_id": "bad-key", "to_id": "val-001", "company": "testcorp"},
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_create_entry_invalid_value_id(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    import app.services.config_table_service as svc_module

    async def fake_validate_value_id(value_id: str) -> bool:
        return False

    monkeypatch.setattr(svc_module, "validate_value_id", fake_validate_value_id)

    response = await client.post(
        "/api/v1/configs/",
        json={"from_id": "key-001", "to_id": "bad-val", "company": "testcorp"},
        headers=auth_headers,
    )
    assert response.status_code == 422
