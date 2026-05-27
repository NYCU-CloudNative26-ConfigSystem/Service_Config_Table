from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.schemas.company import CompanyResponse


def _to_response(company: Company) -> CompanyResponse:
    return CompanyResponse(
        uuid=company.uuid,
        cmp_id=company.cmp_id,
        display_name=company.display_name,
        description=company.description,
        created_by=company.created_by,
        date_created=company.date_created,
    )


async def create_company(
    db: AsyncSession,
    cmp_id: str,
    display_name: str,
    description: str | None,
    created_by: str,
) -> CompanyResponse:
    existing = await db.execute(select(Company).where(Company.cmp_id == cmp_id))
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"Company '{cmp_id}' already exists")
    company = Company(
        cmp_id=cmp_id,
        display_name=display_name,
        description=description,
        created_by=created_by,
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return _to_response(company)


async def get_companies(db: AsyncSession) -> list[CompanyResponse]:
    result = await db.execute(select(Company).order_by(Company.display_name))
    return [_to_response(c) for c in result.scalars().all()]


async def get_company(db: AsyncSession, cmp_id: str) -> CompanyResponse | None:
    result = await db.execute(select(Company).where(Company.cmp_id == cmp_id))
    company = result.scalar_one_or_none()
    return _to_response(company) if company else None
