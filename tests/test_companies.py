"""
Tests for the Company management endpoints.
Run via: docker compose exec service-config-table python -m pytest tests/test_companies.py -v
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/companies"


# ── 1. Create company ─────────────────────────────────────────────────────────

async def test_create_company(client: AsyncClient, auth_headers: dict):
    res = await client.post(BASE, json={
        "cmp_id": "acme-corp",
        "display_name": "ACME Corporation",
        "description": "A test company",
    }, headers=auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["cmp_id"] == "acme-corp"
    assert body["display_name"] == "ACME Corporation"
    assert body["description"] == "A test company"
    assert body["created_by"] == "testuser"


# ── 2. Create company without description ─────────────────────────────────────

async def test_create_company_no_description(client: AsyncClient, auth_headers: dict):
    res = await client.post(BASE, json={
        "cmp_id": "bare-corp",
        "display_name": "Bare Corp",
    }, headers=auth_headers)
    assert res.status_code == 201
    assert res.json()["description"] is None


# ── 3. Duplicate cmp_id → 409 ─────────────────────────────────────────────────

async def test_create_duplicate_company_returns_409(client: AsyncClient, auth_headers: dict):
    await client.post(BASE, json={"cmp_id": "dup-corp", "display_name": "Dup"}, headers=auth_headers)
    res = await client.post(BASE, json={"cmp_id": "dup-corp", "display_name": "Dup Again"}, headers=auth_headers)
    assert res.status_code == 409


# ── 4. List companies ─────────────────────────────────────────────────────────

async def test_list_companies(client: AsyncClient, auth_headers: dict):
    await client.post(BASE, json={"cmp_id": "list-corp-1", "display_name": "List One"}, headers=auth_headers)
    await client.post(BASE, json={"cmp_id": "list-corp-2", "display_name": "List Two"}, headers=auth_headers)
    res = await client.get(BASE, headers=auth_headers)
    assert res.status_code == 200
    cmp_ids = [c["cmp_id"] for c in res.json()]
    assert "list-corp-1" in cmp_ids
    assert "list-corp-2" in cmp_ids


# ── 5. Get company detail ─────────────────────────────────────────────────────

async def test_get_company_detail(client: AsyncClient, auth_headers: dict):
    await client.post(BASE, json={"cmp_id": "detail-corp", "display_name": "Detail Corp"}, headers=auth_headers)
    res = await client.get(f"{BASE}/detail-corp", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["cmp_id"] == "detail-corp"


async def test_get_nonexistent_company_returns_404(client: AsyncClient, auth_headers: dict):
    res = await client.get(f"{BASE}/no-such-company", headers=auth_headers)
    assert res.status_code == 404


# ── 6. Auth guard ─────────────────────────────────────────────────────────────

async def test_no_auth_returns_401(client: AsyncClient):
    res = await client.get(BASE)
    assert res.status_code == 401

    res = await client.post(BASE, json={"cmp_id": "x", "display_name": "x"})
    assert res.status_code == 401
