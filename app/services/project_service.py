from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project, ProjectCompany, ProjectTemplateKey, ProjectTemplateVersion, ProjectTemplateVersionKey
from app.schemas.project import ProjectResponse, ProjectTemplateKeyResponse, ProjectTemplateVersionResponse, PublishedTemplateKeysResponse


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


async def get_template_keys(db: AsyncSession, proj_id: str) -> list[ProjectTemplateKeyResponse]:
    result = await db.execute(
        select(ProjectTemplateKey)
        .where(ProjectTemplateKey.proj_id == proj_id)
        .order_by(ProjectTemplateKey.position, ProjectTemplateKey.date_created)
    )
    return [ProjectTemplateKeyResponse.model_validate(k) for k in result.scalars().all()]


async def add_template_key(
    db: AsyncSession, proj_id: str, alias: str, position: int
) -> ProjectTemplateKeyResponse:
    existing = await db.execute(
        select(ProjectTemplateKey).where(
            ProjectTemplateKey.proj_id == proj_id,
            ProjectTemplateKey.alias == alias,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"'{alias}' is already a required template key for this project")

    # auto-position after existing keys
    if position == 0:
        count = await db.scalar(
            select(func.count(ProjectTemplateKey.uuid)).where(ProjectTemplateKey.proj_id == proj_id)
        )
        position = (count or 0)

    key = ProjectTemplateKey(proj_id=proj_id, alias=alias, position=position)
    db.add(key)
    await db.commit()
    await db.refresh(key)
    return ProjectTemplateKeyResponse.model_validate(key)


async def get_template_versions(db: AsyncSession, proj_id: str) -> list[ProjectTemplateVersionResponse]:
    result = await db.execute(
        select(ProjectTemplateVersion)
        .where(ProjectTemplateVersion.proj_id == proj_id)
        .options(selectinload(ProjectTemplateVersion.keys))
        .order_by(ProjectTemplateVersion.version_number.desc())
    )
    versions = result.scalars().all()
    return [
        ProjectTemplateVersionResponse(
            uuid=v.uuid,
            proj_id=v.proj_id,
            version_number=v.version_number,
            template_name=v.template_name,
            latest=v.latest,
            created_by=v.created_by,
            date_created=v.date_created,
            keys=[k.alias for k in v.keys],
        )
        for v in versions
    ]


async def get_published_template_keys(db: AsyncSession, proj_id: str) -> PublishedTemplateKeysResponse:
    result = await db.execute(
        select(ProjectTemplateVersion)
        .where(ProjectTemplateVersion.proj_id == proj_id, ProjectTemplateVersion.latest == True)  # noqa: E712
        .options(selectinload(ProjectTemplateVersion.keys))
    )
    version = result.scalar_one_or_none()
    if version is None:
        return PublishedTemplateKeysResponse(version_uuid=None, keys=[])
    return PublishedTemplateKeysResponse(
        version_uuid=version.uuid,
        keys=[k.alias for k in version.keys],
    )


async def publish_template(
    db: AsyncSession,
    proj_id: str,
    created_by: str,
    template_name: str | None = None,
) -> ProjectTemplateVersionResponse:
    draft_keys = await get_template_keys(db, proj_id)

    # Mark current latest as not latest
    await db.execute(
        update(ProjectTemplateVersion)
        .where(ProjectTemplateVersion.proj_id == proj_id, ProjectTemplateVersion.latest == True)  # noqa: E712
        .values(latest=False)
    )

    # Compute next version number
    max_result = await db.scalar(
        select(func.max(ProjectTemplateVersion.version_number))
        .where(ProjectTemplateVersion.proj_id == proj_id)
    )
    next_version = (max_result or 0) + 1

    version = ProjectTemplateVersion(
        proj_id=proj_id,
        version_number=next_version,
        template_name=template_name,
        latest=True,
        created_by=created_by,
    )
    db.add(version)
    await db.flush()

    for key in draft_keys:
        db.add(ProjectTemplateVersionKey(
            template_version_uuid=version.uuid,
            alias=key.alias,
            position=key.position,
        ))

    await db.commit()
    await db.refresh(version)

    return ProjectTemplateVersionResponse(
        uuid=version.uuid,
        proj_id=version.proj_id,
        version_number=version.version_number,
        template_name=version.template_name,
        latest=version.latest,
        created_by=version.created_by,
        date_created=version.date_created,
        keys=[k.alias for k in draft_keys],
    )


async def apply_template_version(
    db: AsyncSession,
    proj_id: str,
    version_uuid: str,
) -> ProjectTemplateVersionResponse:
    result = await db.execute(
        select(ProjectTemplateVersion)
        .where(ProjectTemplateVersion.proj_id == proj_id)
        .options(selectinload(ProjectTemplateVersion.keys))
    )
    versions = result.scalars().all()
    target = next((v for v in versions if v.uuid == version_uuid), None)
    if target is None:
        raise LookupError(f"Template version '{version_uuid}' not found in project '{proj_id}'")

    for version in versions:
        version.latest = version.uuid == version_uuid

    await db.commit()
    await db.refresh(target)

    return ProjectTemplateVersionResponse(
        uuid=target.uuid,
        proj_id=target.proj_id,
        version_number=target.version_number,
        template_name=target.template_name,
        latest=target.latest,
        created_by=target.created_by,
        date_created=target.date_created,
        keys=[k.alias for k in target.keys],
    )


async def remove_template_key(db: AsyncSession, proj_id: str, key_uuid: str) -> None:
    result = await db.execute(
        select(ProjectTemplateKey).where(
            ProjectTemplateKey.uuid == key_uuid,
            ProjectTemplateKey.proj_id == proj_id,
        )
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise LookupError(f"Template key '{key_uuid}' not found in project '{proj_id}'")
    await db.delete(key)
    await db.commit()
