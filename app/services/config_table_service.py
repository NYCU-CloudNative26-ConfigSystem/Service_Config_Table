"""
Config Table Service — business logic layer.

Mirrors the service layer pattern from Service_Login.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
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
    # Append via update semantics
    # ------------------------------------------------------------------

    async def append_entry_from_update(
        self,
        entry_id: str,
        payload: ConfigTableUpdate,
        requester: str,
    ) -> ConfigTable:
        base_entry = await self.get_entry(entry_id)
        if base_entry.creator != requester:
            raise ConfigEntryForbiddenError()

        from_id = payload.from_id if payload.from_id is not None else base_entry.from_id
        to_id = payload.to_id if payload.to_id is not None else base_entry.to_id
        company = payload.company if payload.company is not None else base_entry.company

        if not await validate_key_id(from_id):
            raise InvalidKeyIDError(from_id)
        if not await validate_value_id(to_id):
            raise InvalidValueIDError(to_id)

        new_entry = ConfigTable(
            from_id=from_id,
            to_id=to_id,
            creator=requester,
            company=company,
            create_time=datetime.now(timezone.utc),
        )
        self.db.add(new_entry)

        await self.db.commit()
        await self.db.refresh(new_entry)
        logger.info(
            "Config entry appended from update: base_id=%s new_id=%s by creator=%s",
            entry_id,
            new_entry.id,
            requester,
        )
        return new_entry
