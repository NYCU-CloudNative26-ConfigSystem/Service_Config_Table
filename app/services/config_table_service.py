import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config_table import CT, GT, ConfigRelation, ConfigRelationUser
from app.schemas.config_table import ConfigEntrySchema, ConfigReadResponse, ConfigWriteRequest, CTRowResponse, GroupEntrySchema

logger = logging.getLogger(__name__)


class ConfigTableService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def write_config(self, payload: ConfigWriteRequest) -> ConfigReadResponse:
        now = datetime.now(timezone.utc)

        # Soft-delete previous latest version
        await self.db.execute(
            update(ConfigRelation)
            .where(
                ConfigRelation.proj_id == payload.proj_id,
                ConfigRelation.cmp_id == payload.cmp_id,
                ConfigRelation.latest == True,  # noqa: E712
            )
            .values(latest=False, date_deleted=now)
        )

        # New config_relation
        cr = ConfigRelation(proj_id=payload.proj_id, cmp_id=payload.cmp_id)
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
            rows=[CTRowResponse(uuid=ct.uuid, key=ct.key, val=ct.val) for ct in ct_rows],
        )

    def _insert_gt_rows(self, entries: list[GroupEntrySchema]) -> None:
        for entry in entries:
            self.db.add(GT(gid=entry.gid, key=entry.key, val=entry.val))
            if entry.group_entries:
                self._insert_gt_rows(entry.group_entries)

    async def get_config(self, proj_id: str, cmp_id: str) -> ConfigReadResponse | None:
        result = await self.db.execute(
            select(ConfigRelation).where(
                ConfigRelation.proj_id == proj_id,
                ConfigRelation.cmp_id == cmp_id,
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
            rows=[CTRowResponse(uuid=ct.uuid, key=ct.key, val=ct.val) for ct in ct_rows],
        )
