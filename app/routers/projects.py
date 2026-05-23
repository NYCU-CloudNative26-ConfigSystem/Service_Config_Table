from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.routers.deps import CurrentUser, get_current_user
from app.schemas.project import AddCompanyRequest, ProjectCreate, ProjectResponse
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", status_code=201, response_model=ProjectResponse)
async def create_project(
    payload: ProjectCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await project_service.create_project(
        db,
        proj_id=payload.proj_id,
        display_name=payload.display_name,
        description=payload.description,
        created_by=current_user.username,
    )


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    cmp_id: str | None = None,
    _: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await project_service.get_projects(db, cmp_id=cmp_id)


@router.get("/{proj_id}", response_model=ProjectResponse)
async def get_project(
    proj_id: str,
    _: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get_project(db, proj_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{proj_id}' not found")
    return project


@router.post("/{proj_id}/companies", status_code=200)
async def add_company(
    proj_id: str,
    payload: AddCompanyRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get_project(db, proj_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{proj_id}' not found")
    if project.created_by != current_user.username:
        raise HTTPException(status_code=403, detail="Only the project creator can add companies")
    try:
        await project_service.add_company(db, proj_id, payload.cmp_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True}


@router.delete("/{proj_id}", status_code=204)
async def delete_project(
    proj_id: str,
    _: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await project_service.delete_project(db, proj_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(status_code=204)


@router.delete("/{proj_id}/companies/{cmp_id}", status_code=204)
async def remove_company(
    proj_id: str,
    cmp_id: str,
    _: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await project_service.remove_company(db, proj_id, cmp_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(status_code=204)
