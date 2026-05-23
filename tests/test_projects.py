"""
TDD tests for the Project & Company management endpoints.
Run via: docker compose exec service-config-table python -m pytest tests/test_projects.py -v
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/projects"


# ── 1. Create project ─────────────────────────────────────────────────────────

async def test_create_project(client: AsyncClient, auth_headers: dict):
    res = await client.post(BASE, json={
        "proj_id": "proj-alpha",
        "display_name": "Project Alpha",
        "description": "First test project",
    }, headers=auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["proj_id"] == "proj-alpha"
    assert body["display_name"] == "Project Alpha"
    assert body["description"] == "First test project"
    assert body["created_by"] == "testuser"
    assert body["companies"] == []


# ── 2. List projects (no filter) ──────────────────────────────────────────────

async def test_list_projects(client: AsyncClient, auth_headers: dict):
    await client.post(BASE, json={"proj_id": "proj-list-1", "display_name": "List One"}, headers=auth_headers)
    await client.post(BASE, json={"proj_id": "proj-list-2", "display_name": "List Two"}, headers=auth_headers)
    res = await client.get(BASE, headers=auth_headers)
    assert res.status_code == 200
    proj_ids = [p["proj_id"] for p in res.json()]
    assert "proj-list-1" in proj_ids
    assert "proj-list-2" in proj_ids


# ── 3. Filter projects by cmp_id ──────────────────────────────────────────────

async def test_list_projects_filter_by_company(client: AsyncClient, auth_headers: dict):
    # create two projects
    await client.post(BASE, json={"proj_id": "proj-cmp-a", "display_name": "CMP A proj"}, headers=auth_headers)
    await client.post(BASE, json={"proj_id": "proj-cmp-b", "display_name": "CMP B proj"}, headers=auth_headers)
    # add FILTERCORP only to proj-cmp-a
    await client.post(f"{BASE}/proj-cmp-a/companies", json={"cmp_id": "FILTERCORP"}, headers=auth_headers)

    res = await client.get(BASE, params={"cmp_id": "FILTERCORP"}, headers=auth_headers)
    assert res.status_code == 200
    proj_ids = [p["proj_id"] for p in res.json()]
    assert "proj-cmp-a" in proj_ids
    assert "proj-cmp-b" not in proj_ids


# ── 4. Get project detail ─────────────────────────────────────────────────────

async def test_get_project_detail(client: AsyncClient, auth_headers: dict):
    await client.post(BASE, json={"proj_id": "proj-detail", "display_name": "Detail Test"}, headers=auth_headers)
    res = await client.get(f"{BASE}/proj-detail", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["proj_id"] == "proj-detail"
    assert body["companies"] == []


async def test_get_project_not_found(client: AsyncClient, auth_headers: dict):
    res = await client.get(f"{BASE}/nonexistent-proj", headers=auth_headers)
    assert res.status_code == 404


# ── 5. Add company to project ─────────────────────────────────────────────────

async def test_add_company_to_project(client: AsyncClient, auth_headers: dict):
    await client.post(BASE, json={"proj_id": "proj-addcmp", "display_name": "Add Company Test"}, headers=auth_headers)
    res = await client.post(f"{BASE}/proj-addcmp/companies", json={"cmp_id": "ACME"}, headers=auth_headers)
    assert res.status_code == 200


# ── 5b. Non-creator cannot add company → 403 ─────────────────────────────────

async def test_add_company_by_non_creator_returns_403(
    client: AsyncClient, auth_headers: dict, other_headers: dict
):
    await client.post(BASE, json={"proj_id": "proj-notmine", "display_name": "Not Mine"}, headers=auth_headers)
    res = await client.post(f"{BASE}/proj-notmine/companies", json={"cmp_id": "STRANGER"}, headers=other_headers)
    assert res.status_code == 403


# ── 6. Duplicate company → 409 ────────────────────────────────────────────────

async def test_add_duplicate_company_returns_409(client: AsyncClient, auth_headers: dict):
    await client.post(BASE, json={"proj_id": "proj-dupcmp", "display_name": "Dup Company Test"}, headers=auth_headers)
    await client.post(f"{BASE}/proj-dupcmp/companies", json={"cmp_id": "DUPCORP"}, headers=auth_headers)
    res = await client.post(f"{BASE}/proj-dupcmp/companies", json={"cmp_id": "DUPCORP"}, headers=auth_headers)
    assert res.status_code == 409


# ── 7. Get project detail shows added company ─────────────────────────────────

async def test_get_project_after_add_company(client: AsyncClient, auth_headers: dict):
    await client.post(BASE, json={"proj_id": "proj-withcmp", "display_name": "With Company"}, headers=auth_headers)
    await client.post(f"{BASE}/proj-withcmp/companies", json={"cmp_id": "SHOWCORP"}, headers=auth_headers)
    res = await client.get(f"{BASE}/proj-withcmp", headers=auth_headers)
    assert res.status_code == 200
    assert "SHOWCORP" in res.json()["companies"]


# ── 8. Remove company ─────────────────────────────────────────────────────────

async def test_remove_company_from_project(client: AsyncClient, auth_headers: dict):
    await client.post(BASE, json={"proj_id": "proj-rmcmp", "display_name": "Remove Company"}, headers=auth_headers)
    await client.post(f"{BASE}/proj-rmcmp/companies", json={"cmp_id": "RMCORP"}, headers=auth_headers)
    res = await client.delete(f"{BASE}/proj-rmcmp/companies/RMCORP", headers=auth_headers)
    assert res.status_code == 204


# ── 9. Companies list empty after remove ──────────────────────────────────────

async def test_companies_empty_after_remove(client: AsyncClient, auth_headers: dict):
    await client.post(BASE, json={"proj_id": "proj-emptycmp", "display_name": "Empty After Remove"}, headers=auth_headers)
    await client.post(f"{BASE}/proj-emptycmp/companies", json={"cmp_id": "GONECORP"}, headers=auth_headers)
    await client.delete(f"{BASE}/proj-emptycmp/companies/GONECORP", headers=auth_headers)
    res = await client.get(f"{BASE}/proj-emptycmp", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["companies"] == []


# ── 10. Auth guard ────────────────────────────────────────────────────────────

async def test_no_auth_returns_401(client: AsyncClient):
    res = await client.get(BASE)
    assert res.status_code == 401

    res = await client.post(BASE, json={"proj_id": "x", "display_name": "x"})
    assert res.status_code == 401


# ── 11. Soft delete ───────────────────────────────────────────────────────────

async def test_delete_project_returns_204(client: AsyncClient, auth_headers: dict):
    await client.post(BASE, json={"proj_id": "proj-del", "display_name": "Delete Me"}, headers=auth_headers)
    res = await client.delete(f"{BASE}/proj-del", headers=auth_headers)
    assert res.status_code == 204


async def test_deleted_project_not_in_list(client: AsyncClient, auth_headers: dict):
    await client.post(BASE, json={"proj_id": "proj-gone", "display_name": "Gone"}, headers=auth_headers)
    await client.delete(f"{BASE}/proj-gone", headers=auth_headers)
    res = await client.get(BASE, headers=auth_headers)
    assert res.status_code == 200
    assert all(p["proj_id"] != "proj-gone" for p in res.json())


async def test_deleted_project_detail_returns_404(client: AsyncClient, auth_headers: dict):
    await client.post(BASE, json={"proj_id": "proj-hidden", "display_name": "Hidden"}, headers=auth_headers)
    await client.delete(f"{BASE}/proj-hidden", headers=auth_headers)
    res = await client.get(f"{BASE}/proj-hidden", headers=auth_headers)
    assert res.status_code == 404


async def test_delete_nonexistent_returns_404(client: AsyncClient, auth_headers: dict):
    res = await client.delete(f"{BASE}/no-such-project", headers=auth_headers)
    assert res.status_code == 404
