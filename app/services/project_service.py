from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project, ProjectCompany
from app.schemas.project import ProjectResponse


def _to_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        uuid=project.uuid,
        proj_id=project.proj_id,
        display_name=project.display_name,
        description=project.description,
        created_by=project.created_by,
        date_created=project.date_created,
        companies=[pc.cmp_id for pc in project.companies],
    )


async def create_project(
    db: AsyncSession,
    proj_id: str,
    display_name: str,
    description: str | None,
    created_by: str,
) -> ProjectResponse:
    project = Project(
        proj_id=proj_id,
        display_name=display_name,
        description=description,
        created_by=created_by,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    # reload with companies relationship
    result = await db.execute(
        select(Project).where(Project.proj_id == proj_id).options(selectinload(Project.companies))
    )
    project = result.scalar_one()
    return _to_response(project)


async def get_projects(db: AsyncSession, cmp_id: str | None = None) -> list[ProjectResponse]:
    stmt = (
        select(Project)
        .where(Project.deleted_datetime.is_(None))
        .options(selectinload(Project.companies))
    )
    if cmp_id is not None:
        stmt = stmt.join(Project.companies).where(ProjectCompany.cmp_id == cmp_id)
    result = await db.execute(stmt)
    projects = result.scalars().unique().all()
    return [_to_response(p) for p in projects]


async def get_project(db: AsyncSession, proj_id: str) -> ProjectResponse | None:
    result = await db.execute(
        select(Project)
        .where(Project.proj_id == proj_id, Project.deleted_datetime.is_(None))
        .options(selectinload(Project.companies))
    )
    project = result.scalar_one_or_none()
    if project is None:
        return None
    return _to_response(project)


async def delete_project(db: AsyncSession, proj_id: str) -> None:
    result = await db.execute(
        select(Project).where(Project.proj_id == proj_id, Project.deleted_datetime.is_(None))
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise LookupError(f"Project '{proj_id}' not found")
    project.deleted_datetime = datetime.now(timezone.utc)
    await db.commit()


async def add_company(db: AsyncSession, proj_id: str, cmp_id: str) -> None:
    result = await db.execute(select(Project).where(Project.proj_id == proj_id))
    if result.scalar_one_or_none() is None:
        raise LookupError(f"Project '{proj_id}' not found")

    existing = await db.execute(
        select(ProjectCompany).where(
            ProjectCompany.proj_id == proj_id,
            ProjectCompany.cmp_id == cmp_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"Company '{cmp_id}' already associated with project '{proj_id}'")

    db.add(ProjectCompany(proj_id=proj_id, cmp_id=cmp_id))
    await db.commit()


async def remove_company(db: AsyncSession, proj_id: str, cmp_id: str) -> None:
    result = await db.execute(
        select(ProjectCompany).where(
            ProjectCompany.proj_id == proj_id,
            ProjectCompany.cmp_id == cmp_id,
        )
    )
    pc = result.scalar_one_or_none()
    if pc is None:
        raise LookupError(f"Company '{cmp_id}' not found in project '{proj_id}'")
    await db.delete(pc)
    await db.commit()
