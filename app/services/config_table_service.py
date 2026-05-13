"""
Config Table Service — business logic layer.

Mirrors the service layer pattern from Service_Login.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConfigEntryForbiddenError,
    ConfigEntryNotFoundError,
    InvalidKeyIDError,
    InvalidValueIDError,
)
from app.models.config_table import ConfigTable
from app.schemas.config_table import ConfigTableCreate, ConfigTableUpdate
from app.utils.config_service_client import validate_key_id, validate_value_id

logger = logging.getLogger(__name__)


class ConfigTableService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_entry(
        self,
        payload: ConfigTableCreate,
        creator: str,
    ) -> ConfigTable:
        if not await validate_key_id(payload.from_id):
            raise InvalidKeyIDError(payload.from_id)
        if not await validate_value_id(payload.to_id):
            raise InvalidValueIDError(payload.to_id)

        entry = ConfigTable(
            from_id=payload.from_id,
            to_id=payload.to_id,
            creator=creator,
            company=payload.company,
            create_time=datetime.now(timezone.utc),
        )
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        logger.info("Config entry created: id=%s by creator=%s", entry.id, creator)
        return entry

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_entry(self, entry_id: str) -> ConfigTable:
        result = await self.db.execute(
            select(ConfigTable).where(ConfigTable.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            raise ConfigEntryNotFoundError(entry_id)
        return entry

    async def list_entries(
        self,
        skip: int = 0,
        limit: int = 100,
        creator: str | None = None,
        company: str | None = None,
    ) -> list[ConfigTable]:
        stmt = select(ConfigTable)
        if creator is not None:
            stmt = stmt.where(ConfigTable.creator == creator)
        if company is not None:
            stmt = stmt.where(ConfigTable.company == company)
        stmt = stmt.offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_entry(
        self,
        entry_id: str,
        payload: ConfigTableUpdate,
        requester: str,
    ) -> ConfigTable:
        entry = await self.get_entry(entry_id)
        if entry.creator != requester:
            raise ConfigEntryForbiddenError()

        if payload.from_id is not None and not await validate_key_id(payload.from_id):
            raise InvalidKeyIDError(payload.from_id)
        if payload.to_id is not None and not await validate_value_id(payload.to_id):
            raise InvalidValueIDError(payload.to_id)

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(entry, field, value)

        await self.db.commit()
        await self.db.refresh(entry)
        logger.info("Config entry updated: id=%s by creator=%s", entry_id, requester)
        return entry

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_entry(self, entry_id: str, requester: str) -> None:
        entry = await self.get_entry(entry_id)
        if entry.creator != requester:
            raise ConfigEntryForbiddenError()

        await self.db.execute(
            delete(ConfigTable).where(ConfigTable.id == entry_id)
        )
        await self.db.commit()
        logger.info("Config entry deleted: id=%s by creator=%s", entry_id, requester)
