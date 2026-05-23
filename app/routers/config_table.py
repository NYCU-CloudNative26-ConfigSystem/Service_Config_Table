import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.routers.deps import CurrentUser, get_current_user
from app.schemas.config_table import ConfigReadResponse, ConfigWriteRequest
from app.services.config_table_service import ConfigTableService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["config-table"])


def _svc(db: AsyncSession = Depends(get_db)) -> ConfigTableService:
    return ConfigTableService(db)


@router.post(
    "/",
    response_model=ConfigReadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Write a new versioned config snapshot",
)
async def write_config(
    payload: ConfigWriteRequest,
    svc: ConfigTableService = Depends(_svc),
    _: CurrentUser = Depends(get_current_user),
):
    return await svc.write_config(payload)


@router.get(
    "/",
    response_model=ConfigReadResponse,
    summary="Get current config (flat CT rows with raw UUIDs)",
)
async def get_config(
    proj_id: str = Query(..., description="Project ID"),
    cmp_id: str = Query(..., description="Company ID"),
    svc: ConfigTableService = Depends(_svc),
    _: CurrentUser = Depends(get_current_user),
):
    result = await svc.get_config(proj_id, cmp_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No config found for this project/company")
    return result
