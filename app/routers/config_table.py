"""
Config Table router  —  /api/v1/configs
"""

import logging

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.routers.deps import CurrentUser, get_current_user
from app.schemas.config_table import (
    ConfigTableCreate,
    ConfigTableResponse,
    ConfigTableUpdate,
)
from app.services.config_table_service import ConfigTableService
from app.utils.version_control_client import sync_config_entry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/configs", tags=["config-table"])


def _svc(db: AsyncSession = Depends(get_db)) -> ConfigTableService:
    return ConfigTableService(db)


@router.post(
    "/",
    response_model=ConfigTableResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a config table entry",
)
async def create_config_entry(
    payload: ConfigTableCreate,
    request: Request,
    svc: ConfigTableService = Depends(_svc),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Create a new entry that maps a **Key ID** (from) to a **Value ID** (to)
    as stored in the Config Service.  The caller's username is recorded as
    the creator; ``company`` must be supplied in the request body.
    """
    entry = await svc.create_entry(payload, creator=current_user.username)
    await sync_config_entry(
        entry_id=entry.id,
        key_id=entry.from_id,
        value_id=entry.to_id,
        created_at=entry.create_time,
        authorization_header=request.headers.get("Authorization"),
    )
    return entry


@router.get(
    "/",
    response_model=list[ConfigTableResponse],
    summary="List config table entries",
)
async def list_config_entries(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
    creator: str | None = Query(None, description="Filter by creator username"),
    company: str | None = Query(None, description="Filter by company"),
    svc: ConfigTableService = Depends(_svc),
    _: CurrentUser = Depends(get_current_user),
):
    """List entries, optionally filtered by *creator* or *company*."""
    return await svc.list_entries(skip=skip, limit=limit, creator=creator, company=company)


@router.get(
    "/{entry_id}",
    response_model=ConfigTableResponse,
    summary="Get a single config table entry",
)
async def get_config_entry(
    entry_id: str,
    svc: ConfigTableService = Depends(_svc),
    _: CurrentUser = Depends(get_current_user),
):
    """Retrieve a config table entry by its UUID."""
    return await svc.get_entry(entry_id)


@router.put(
    "/{entry_id}",
    response_model=ConfigTableResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Append a new config table entry from an existing one",
)
async def update_config_entry(
    entry_id: str,
    payload: ConfigTableUpdate,
    request: Request,
    svc: ConfigTableService = Depends(_svc),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Treat update as append-only behavior: a new row is created and returned,
    while the original row remains unchanged.
    """
    entry = await svc.append_entry_from_update(
        entry_id, payload, requester=current_user.username
    )
    await sync_config_entry(
        entry_id=entry.id,
        key_id=entry.from_id,
        value_id=entry.to_id,
        created_at=entry.create_time,
        authorization_header=request.headers.get("Authorization"),
    )
    return entry
