import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.routers.deps import CurrentUser, get_current_user
from app.schemas.config_table import ConfigApprovalResponse, ConfigHistoryItem, ConfigPromoteByUuidRequest, ConfigPromoteRequest, ConfigReadResponse, ConfigWriteRequest, RejectRequest
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
    environment: str = Query("production", description="Environment (development/testing/staging/production)"),
    svc: ConfigTableService = Depends(_svc),
    _: CurrentUser = Depends(get_current_user),
):
    result = await svc.get_config(proj_id, cmp_id, environment)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No config found for this project/company/environment")
    return result


@router.get(
    "/companies",
    response_model=list[str],
    summary="List distinct companies that have configs for a project",
)
async def get_companies_with_config(
    proj_id: str = Query(..., description="Project ID"),
    svc: ConfigTableService = Depends(_svc),
    _: CurrentUser = Depends(get_current_user),
):
    return await svc.get_companies_with_config(proj_id)


@router.get(
    "/history",
    response_model=list[ConfigHistoryItem],
    summary="Get all config snapshots for a project/company/environment, newest first",
)
async def get_history(
    proj_id: str = Query(..., description="Project ID"),
    cmp_id: str = Query(..., description="Company ID"),
    environment: str = Query("production", description="Environment (development/testing/staging/production)"),
    svc: ConfigTableService = Depends(_svc),
    _: CurrentUser = Depends(get_current_user),
):
    return await svc.get_history(proj_id, cmp_id, environment)


@router.post(
    "/promote",
    response_model=ConfigReadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Promote latest config from one environment to another",
)
async def promote_config(
    payload: ConfigPromoteRequest,
    svc: ConfigTableService = Depends(_svc),
    current_user: CurrentUser = Depends(get_current_user),
):
    from fastapi import HTTPException
    if payload.from_environment == payload.to_environment:
        raise HTTPException(status_code=400, detail="Source and target environments must differ")
    try:
        return await svc.promote_config(payload, user_id=current_user.username)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{config_uuid}/promote",
    response_model=ConfigReadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Promote a specific config snapshot to another environment",
)
async def promote_config_by_uuid(
    config_uuid: str,
    payload: ConfigPromoteByUuidRequest,
    svc: ConfigTableService = Depends(_svc),
    current_user: CurrentUser = Depends(get_current_user),
):
    from fastapi import HTTPException
    try:
        return await svc.promote_config_by_uuid(config_uuid, payload.to_environment, current_user.username)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{config_uuid}/approve",
    response_model=ConfigApprovalResponse,
    summary="Approve a pending config snapshot",
)
async def approve_config(
    config_uuid: str,
    svc: ConfigTableService = Depends(_svc),
    current_user: CurrentUser = Depends(get_current_user),
):
    from fastapi import HTTPException
    if current_user.role not in ("reviewer", "admin"):
        raise HTTPException(status_code=403, detail="Only reviewers and admins can approve configs")
    try:
        return await svc.approve_config(config_uuid, approver_id=current_user.username)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post(
    "/{config_uuid}/reject",
    response_model=ConfigApprovalResponse,
    summary="Reject a pending config snapshot",
)
async def reject_config(
    config_uuid: str,
    payload: RejectRequest,
    svc: ConfigTableService = Depends(_svc),
    current_user: CurrentUser = Depends(get_current_user),
):
    from fastapi import HTTPException
    if current_user.role not in ("reviewer", "admin"):
        raise HTTPException(status_code=403, detail="Only reviewers and admins can reject configs")
    try:
        return await svc.reject_config(config_uuid, rejector_id=current_user.username, reason=payload.reason)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get(
    "/{uuid}",
    response_model=ConfigReadResponse,
    summary="Get a specific config snapshot by UUID",
)
async def get_config_by_uuid(
    uuid: str,
    svc: ConfigTableService = Depends(_svc),
    _: CurrentUser = Depends(get_current_user),
):
    result = await svc.get_config_by_uuid(uuid)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Config snapshot not found")
    return result


@router.get(
    "/{uuid}/children",
    response_model=list[ConfigHistoryItem],
    summary="Get all snapshots that were inherited from the given snapshot",
)
async def get_config_children(
    uuid: str,
    svc: ConfigTableService = Depends(_svc),
    _: CurrentUser = Depends(get_current_user),
):
    return await svc.get_children(uuid)
