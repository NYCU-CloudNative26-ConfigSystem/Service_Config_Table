import logging
import re
from datetime import datetime, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.config_table import CT, GT, ConfigRelation, ConfigRelationUser
from app.models.project import Project, ProjectTemplateVersion
from app.schemas.config_table import ConfigApprovalResponse, ConfigEntrySchema, ConfigHistoryItem, ConfigPromoteByUuidRequest, ConfigPromoteRequest, ConfigReadResponse, ConfigWriteRequest, CTRowResponse, GroupEntrySchema

logger = logging.getLogger(__name__)


class ConfigTableService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _slugify(text: str) -> str:
        """Replace whitespace runs with underscores and strip non-word characters."""
        text = text.strip()
        text = re.sub(r"\s+", "_", text)
        text = re.sub(r"[^\w\-]", "", text)
        return text

    async def _build_default_name(self, proj_id: str, cmp_id: str) -> str:
        proj_result = await self.db.execute(select(Project).where(Project.proj_id == proj_id))
        proj = proj_result.scalar_one_or_none()
        cmp_result = await self.db.execute(select(Company).where(Company.cmp_id == cmp_id))
        cmp = cmp_result.scalar_one_or_none()
        proj_label = self._slugify(proj.display_name if proj else proj_id)
        cmp_label = self._slugify(cmp.display_name if cmp else cmp_id)
        date_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
        return f"{proj_label}_{cmp_label}_{date_str}"

    async def write_config(self, payload: ConfigWriteRequest) -> ConfigReadResponse:
        name = self._slugify(payload.name) if payload.name and payload.name.strip() else None
        if not name:
            name = await self._build_default_name(payload.proj_id, payload.cmp_id)

        # New config_relation starts as pending — approval required before it becomes latest
        cr = ConfigRelation(
            proj_id=payload.proj_id,
            cmp_id=payload.cmp_id,
            environment=payload.environment,
            template_version_uuid=payload.template_version_uuid,
            latest=False,
            approval_status="pending",
            change_description=payload.change_description,
            promoted_from_uuid=payload.source_snapshot_uuid,
            name=name,
        )
        self.db.add(cr)
        await self.db.flush()  # get cr.uuid

        # Junction row
        self.db.add(ConfigRelationUser(config_relation_uuid=cr.uuid, user_id=payload.user_id))

        # CT rows + recursive GT rows
        ct_rows: list[CT] = []
        for entry in payload.entries:
            ct = CT(config_relation_uuid=cr.uuid, key=entry.key, val=entry.val)
            self.db.add(ct)
            ct_rows.append(ct)
            if entry.group_entries:
                self._insert_gt_rows(entry.group_entries)

        await self.db.commit()
        await self.db.refresh(cr)

        logger.info("Config written: config_relation=%s proj=%s cmp=%s", cr.uuid, payload.proj_id, payload.cmp_id)

        return ConfigReadResponse(
            config_relation_uuid=cr.uuid,
            date_created=cr.date_created,
            environment=cr.environment,
            rows=[CTRowResponse(uuid=ct.uuid, key=ct.key, val=ct.val) for ct in ct_rows],
            name=cr.name,
        )

    def _insert_gt_rows(self, entries: list[GroupEntrySchema]) -> None:
        for entry in entries:
            self.db.add(GT(gid=entry.gid, key=entry.key, val=entry.val))
            if entry.group_entries:
                self._insert_gt_rows(entry.group_entries)

    async def promote_config(self, payload: ConfigPromoteRequest, user_id: str) -> ConfigReadResponse:
        now = datetime.now(timezone.utc)

        # Fetch source latest
        src_result = await self.db.execute(
            select(ConfigRelation).where(
                ConfigRelation.proj_id == payload.proj_id,
                ConfigRelation.cmp_id == payload.cmp_id,
                ConfigRelation.environment == payload.from_environment,
                ConfigRelation.latest == True,  # noqa: E712
            )
        )
        source = src_result.scalar_one_or_none()
        if source is None:
            raise LookupError(
                f"No config found in '{payload.from_environment}' to promote"
            )

        # Fetch source CT rows
        ct_result = await self.db.execute(
            select(CT).where(CT.config_relation_uuid == source.uuid)
        )
        source_rows = list(ct_result.scalars().all())

        # Soft-delete previous latest in target environment
        await self.db.execute(
            update(ConfigRelation)
            .where(
                ConfigRelation.proj_id == payload.proj_id,
                ConfigRelation.cmp_id == payload.cmp_id,
                ConfigRelation.environment == payload.to_environment,
                ConfigRelation.latest == True,  # noqa: E712
            )
            .values(latest=False, date_deleted=now)
        )

        # New config_relation for target environment — auto-approved (source was already vetted)
        new_cr = ConfigRelation(
            proj_id=payload.proj_id,
            cmp_id=payload.cmp_id,
            environment=payload.to_environment,
            template_version_uuid=source.template_version_uuid,
            latest=True,
            approval_status="approved",
            approved_by=user_id,
            approved_at=now,
            promoted_from_uuid=source.uuid,
        )
        self.db.add(new_cr)
        await self.db.flush()

        self.db.add(ConfigRelationUser(config_relation_uuid=new_cr.uuid, user_id=user_id))

        # Copy CT rows — GT rows are keyed by gid (not config_relation_uuid) so they remain valid
        new_ct_rows: list[CT] = []
        for row in source_rows:
            ct = CT(config_relation_uuid=new_cr.uuid, key=row.key, val=row.val)
            self.db.add(ct)
            new_ct_rows.append(ct)

        await self.db.commit()
        await self.db.refresh(new_cr)

        logger.info(
            "Config promoted: %s → %s  proj=%s cmp=%s new_cr=%s",
            payload.from_environment, payload.to_environment,
            payload.proj_id, payload.cmp_id, new_cr.uuid,
        )

        return ConfigReadResponse(
            config_relation_uuid=new_cr.uuid,
            date_created=new_cr.date_created,
            environment=new_cr.environment,
            rows=[CTRowResponse(uuid=ct.uuid, key=ct.key, val=ct.val) for ct in new_ct_rows],
        )

    async def promote_config_by_uuid(self, config_uuid: str, to_environment: str, user_id: str) -> ConfigReadResponse:
        now = datetime.now(timezone.utc)

        # Fetch the specific source snapshot
        src_result = await self.db.execute(
            select(ConfigRelation).where(ConfigRelation.uuid == config_uuid)
        )
        source = src_result.scalar_one_or_none()
        if source is None:
            raise LookupError(f"Config snapshot '{config_uuid}' not found")
        if source.approval_status != "approved":
            raise ValueError(
                f"Cannot promote snapshot with status '{source.approval_status}'"
            )

        # Fetch its CT rows
        ct_result = await self.db.execute(
            select(CT).where(CT.config_relation_uuid == source.uuid)
        )
        source_rows = list(ct_result.scalars().all())

        # Soft-delete previous latest in target environment
        await self.db.execute(
            update(ConfigRelation)
            .where(
                ConfigRelation.proj_id == source.proj_id,
                ConfigRelation.cmp_id == source.cmp_id,
                ConfigRelation.environment == to_environment,
                ConfigRelation.latest == True,  # noqa: E712
            )
            .values(latest=False, date_deleted=now)
        )

        # New config_relation for target environment — auto-approved (source was already vetted)
        new_cr = ConfigRelation(
            proj_id=source.proj_id,
            cmp_id=source.cmp_id,
            environment=to_environment,
            template_version_uuid=source.template_version_uuid,
            latest=True,
            approval_status="approved",
            approved_by=user_id,
            approved_at=now,
            promoted_from_uuid=source.uuid,
        )
        self.db.add(new_cr)
        await self.db.flush()

        self.db.add(ConfigRelationUser(config_relation_uuid=new_cr.uuid, user_id=user_id))

        # Copy CT rows — GT rows are keyed by gid so they remain valid without re-inserting
        new_ct_rows: list[CT] = []
        for row in source_rows:
            ct = CT(config_relation_uuid=new_cr.uuid, key=row.key, val=row.val)
            self.db.add(ct)
            new_ct_rows.append(ct)

        await self.db.commit()
        await self.db.refresh(new_cr)

        logger.info(
            "Config promoted by uuid: %s → %s  proj=%s cmp=%s new_cr=%s",
            source.environment, to_environment,
            source.proj_id, source.cmp_id, new_cr.uuid,
        )

        return ConfigReadResponse(
            config_relation_uuid=new_cr.uuid,
            date_created=new_cr.date_created,
            environment=new_cr.environment,
            rows=[CTRowResponse(uuid=ct.uuid, key=ct.key, val=ct.val) for ct in new_ct_rows],
        )

    async def get_companies_with_config(self, proj_id: str) -> list[str]:
        result = await self.db.execute(
            select(ConfigRelation.cmp_id)
            .where(ConfigRelation.proj_id == proj_id)
            .distinct()
            .order_by(ConfigRelation.cmp_id)
        )
        return list(result.scalars().all())

    async def get_history(self, proj_id: str, cmp_id: str, environment: str) -> list[ConfigHistoryItem]:
        # Fetch all config_relations for this proj+cmp+env with user and entry count
        cr_result = await self.db.execute(
            select(ConfigRelation)
            .where(
                ConfigRelation.proj_id == proj_id,
                ConfigRelation.cmp_id == cmp_id,
                ConfigRelation.environment == environment,
            )
            .order_by(ConfigRelation.date_created.desc())
        )
        relations = list(cr_result.scalars().all())

        items: list[ConfigHistoryItem] = []
        for cr in relations:
            ct_count = await self.db.scalar(
                select(func.count(CT.uuid)).where(CT.config_relation_uuid == cr.uuid)
            )
            user_result = await self.db.execute(
                select(ConfigRelationUser.user_id)
                .where(ConfigRelationUser.config_relation_uuid == cr.uuid)
                .limit(1)
            )
            created_by = user_result.scalar_one_or_none()

            # Resolve template version number if linked
            tmpl_version_number: int | None = None
            if cr.template_version_uuid:
                tv_result = await self.db.execute(
                    select(ProjectTemplateVersion.version_number)
                    .where(ProjectTemplateVersion.uuid == cr.template_version_uuid)
                )
                tmpl_version_number = tv_result.scalar_one_or_none()

            items.append(ConfigHistoryItem(
                config_relation_uuid=cr.uuid,
                date_created=cr.date_created,
                date_deleted=cr.date_deleted,
                created_by=created_by,
                entry_count=ct_count or 0,
                is_latest=cr.latest,
                environment=cr.environment,
                template_version_uuid=cr.template_version_uuid,
                template_version_number=tmpl_version_number,
                approval_status=cr.approval_status,
                approved_by=cr.approved_by,
                approved_at=cr.approved_at,
                rejection_reason=cr.rejection_reason,
                change_description=cr.change_description,
                promoted_from_uuid=cr.promoted_from_uuid,
                name=cr.name,
                proj_id=cr.proj_id,
                cmp_id=cr.cmp_id,
            ))
        return items

    async def get_config_by_uuid(self, uuid: str) -> ConfigReadResponse | None:
        result = await self.db.execute(
            select(ConfigRelation).where(ConfigRelation.uuid == uuid)
        )
        cr = result.scalar_one_or_none()
        if cr is None:
            return None
        ct_result = await self.db.execute(
            select(CT).where(CT.config_relation_uuid == cr.uuid)
        )
        ct_rows = list(ct_result.scalars().all())
        user_result = await self.db.execute(
            select(ConfigRelationUser.user_id)
            .where(ConfigRelationUser.config_relation_uuid == cr.uuid)
            .limit(1)
        )
        created_by = user_result.scalar_one_or_none()
        return ConfigReadResponse(
            config_relation_uuid=cr.uuid,
            date_created=cr.date_created,
            environment=cr.environment,
            rows=[CTRowResponse(uuid=ct.uuid, key=ct.key, val=ct.val) for ct in ct_rows],
            approval_status=cr.approval_status,
            approved_by=cr.approved_by,
            approved_at=cr.approved_at,
            rejection_reason=cr.rejection_reason,
            created_by=created_by,
            is_latest=cr.latest,
            change_description=cr.change_description,
            promoted_from_uuid=cr.promoted_from_uuid,
            proj_id=cr.proj_id,
            cmp_id=cr.cmp_id,
            name=cr.name,
        )

    async def get_config(self, proj_id: str, cmp_id: str, environment: str = "production") -> ConfigReadResponse | None:
        result = await self.db.execute(
            select(ConfigRelation).where(
                ConfigRelation.proj_id == proj_id,
                ConfigRelation.cmp_id == cmp_id,
                ConfigRelation.environment == environment,
                ConfigRelation.latest == True,  # noqa: E712
            )
        )
        cr = result.scalar_one_or_none()
        if cr is None:
            return None

        ct_result = await self.db.execute(
            select(CT).where(CT.config_relation_uuid == cr.uuid)
        )
        ct_rows = list(ct_result.scalars().all())

        return ConfigReadResponse(
            config_relation_uuid=cr.uuid,
            date_created=cr.date_created,
            environment=cr.environment,
            rows=[CTRowResponse(uuid=ct.uuid, key=ct.key, val=ct.val) for ct in ct_rows],
        )

    async def approve_config(self, config_uuid: str, approver_id: str) -> ConfigApprovalResponse:
        now = datetime.now(timezone.utc)

        result = await self.db.execute(select(ConfigRelation).where(ConfigRelation.uuid == config_uuid))
        cr = result.scalar_one_or_none()
        if cr is None:
            raise LookupError(f"Config snapshot '{config_uuid}' not found")
        if cr.approval_status != "pending":
            raise ValueError(f"Config is already '{cr.approval_status}', cannot approve")

        user_result = await self.db.execute(
            select(ConfigRelationUser.user_id)
            .where(ConfigRelationUser.config_relation_uuid == config_uuid)
            .limit(1)
        )
        submitter = user_result.scalar_one_or_none()
        if submitter == approver_id:
            raise PermissionError("Cannot approve your own config submission")

        # Soft-delete current latest in same scope
        await self.db.execute(
            update(ConfigRelation)
            .where(
                ConfigRelation.proj_id == cr.proj_id,
                ConfigRelation.cmp_id == cr.cmp_id,
                ConfigRelation.environment == cr.environment,
                ConfigRelation.latest == True,  # noqa: E712
            )
            .values(latest=False, date_deleted=now)
        )

        cr.approval_status = "approved"
        cr.approved_by = approver_id
        cr.approved_at = now
        cr.latest = True
        await self.db.commit()
        await self.db.refresh(cr)

        logger.info("Config approved: %s by %s", config_uuid, approver_id)
        return ConfigApprovalResponse(
            config_relation_uuid=cr.uuid,
            approval_status=cr.approval_status,
            approved_by=cr.approved_by,
            approved_at=cr.approved_at,
            rejection_reason=cr.rejection_reason,
        )

    async def reject_config(self, config_uuid: str, rejector_id: str, reason: str | None) -> ConfigApprovalResponse:
        result = await self.db.execute(select(ConfigRelation).where(ConfigRelation.uuid == config_uuid))
        cr = result.scalar_one_or_none()
        if cr is None:
            raise LookupError(f"Config snapshot '{config_uuid}' not found")
        if cr.approval_status != "pending":
            raise ValueError(f"Config is already '{cr.approval_status}', cannot reject")

        user_result = await self.db.execute(
            select(ConfigRelationUser.user_id)
            .where(ConfigRelationUser.config_relation_uuid == config_uuid)
            .limit(1)
        )
        submitter = user_result.scalar_one_or_none()
        if submitter == rejector_id:
            raise PermissionError("Cannot reject your own config submission")

        cr.approval_status = "rejected"
        cr.approved_by = rejector_id
        cr.rejection_reason = reason
        await self.db.commit()
        await self.db.refresh(cr)

        logger.info("Config rejected: %s by %s", config_uuid, rejector_id)
        return ConfigApprovalResponse(
            config_relation_uuid=cr.uuid,
            approval_status=cr.approval_status,
            approved_by=cr.approved_by,
            approved_at=cr.approved_at,
            rejection_reason=cr.rejection_reason,
        )

    async def search_configs(
        self,
        q: str | None,
        key_uuids: list[str] | None,
        proj_id: str | None,
        cmp_id: str | None,
        environment: str | None,
        skip: int,
        limit: int,
    ) -> list[ConfigHistoryItem]:
        stmt = select(ConfigRelation)

        filters = []
        if q:
            pattern = f"%{q}%"
            filters.append(or_(
                ConfigRelation.name.ilike(pattern),
                ConfigRelation.proj_id.ilike(pattern),
                ConfigRelation.cmp_id.ilike(pattern),
            ))
        if proj_id:
            filters.append(ConfigRelation.proj_id == proj_id)
        if cmp_id:
            filters.append(ConfigRelation.cmp_id == cmp_id)
        if environment:
            filters.append(ConfigRelation.environment == environment)

        if key_uuids:
            # subquery: config_relation_uuids that have at least one matching CT key
            sub = select(CT.config_relation_uuid).where(CT.key.in_(key_uuids)).distinct()
            filters.append(ConfigRelation.uuid.in_(sub))

        if filters:
            stmt = stmt.where(*filters)

        stmt = stmt.order_by(ConfigRelation.date_created.desc()).offset(skip).limit(limit)
        cr_result = await self.db.execute(stmt)
        relations = list(cr_result.scalars().all())

        items: list[ConfigHistoryItem] = []
        for cr in relations:
            ct_count = await self.db.scalar(
                select(func.count(CT.uuid)).where(CT.config_relation_uuid == cr.uuid)
            )
            user_result = await self.db.execute(
                select(ConfigRelationUser.user_id)
                .where(ConfigRelationUser.config_relation_uuid == cr.uuid)
                .limit(1)
            )
            created_by = user_result.scalar_one_or_none()

            tmpl_version_number: int | None = None
            if cr.template_version_uuid:
                tv_result = await self.db.execute(
                    select(ProjectTemplateVersion.version_number)
                    .where(ProjectTemplateVersion.uuid == cr.template_version_uuid)
                )
                tmpl_version_number = tv_result.scalar_one_or_none()

            items.append(ConfigHistoryItem(
                config_relation_uuid=cr.uuid,
                date_created=cr.date_created,
                date_deleted=cr.date_deleted,
                created_by=created_by,
                entry_count=ct_count or 0,
                is_latest=cr.latest,
                environment=cr.environment,
                template_version_uuid=cr.template_version_uuid,
                template_version_number=tmpl_version_number,
                approval_status=cr.approval_status,
                approved_by=cr.approved_by,
                approved_at=cr.approved_at,
                rejection_reason=cr.rejection_reason,
                change_description=cr.change_description,
                promoted_from_uuid=cr.promoted_from_uuid,
                name=cr.name,
                proj_id=cr.proj_id,
                cmp_id=cr.cmp_id,
            ))
        return items
