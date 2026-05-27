from fastapi import APIRouter, Depends, HTTPException, Response

from app.database.connection import get_db
from app.routers.deps import CurrentUser, get_current_user
from app.schemas.company import CompanyCreate, CompanyResponse
from app.services import company_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/companies", tags=["companies"])


@router.post("", status_code=201, response_model=CompanyResponse)
async def create_company(
    payload: CompanyCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await company_service.create_company(
            db,
            cmp_id=payload.cmp_id,
            display_name=payload.display_name,
            description=payload.description,
            created_by=current_user.username,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("", response_model=list[CompanyResponse])
async def list_companies(
    _: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await company_service.get_companies(db)


@router.get("/{cmp_id}", response_model=CompanyResponse)
async def get_company(
    cmp_id: str,
    _: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    company = await company_service.get_company(db, cmp_id)
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company '{cmp_id}' not found")
    return company
