import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base


class ConfigTable(Base):
    """
    Config Table entry.

    Maps a Key ID (from_id) to a Value ID (to_id) as managed by the
    Config Service.  Stores the creator's username, the company they
    belong to, and the UTC creation timestamp.
    """

    __tablename__ = "config_table"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    from_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Key ID (from Config Service)"
    )
    to_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Value ID (from Config Service)"
    )
    creator: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Username of the creator"
    )
    company: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Company the creator belongs to"
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="UTC timestamp of creation",
    )
