import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class ConfigRelation(Base):
    __tablename__ = "config_relation"

    uuid: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    date_deleted: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proj_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cmp_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(20), nullable=False, default="production", index=True)
    template_version_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)

    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    promoted_from_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)

    users: Mapped[list["ConfigRelationUser"]] = relationship(back_populates="config_relation", cascade="all, delete-orphan")
    ct_rows: Mapped[list["CT"]] = relationship(back_populates="config_relation", cascade="all, delete-orphan")


class ConfigRelationUser(Base):
    __tablename__ = "config_relation_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    config_relation_uuid: Mapped[str] = mapped_column(
        String(36), ForeignKey("config_relation.uuid", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    config_relation: Mapped["ConfigRelation"] = relationship(back_populates="users")


class CT(Base):
    """One row per top-level config element."""
    __tablename__ = "ct"

    uuid: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    config_relation_uuid: Mapped[str] = mapped_column(
        String(36), ForeignKey("config_relation.uuid", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False, comment="NameNode UUID from Neo4j")
    val: Mapped[str] = mapped_column(String(512), nullable=False, comment="VALUE:<uuid> or GROUP:<uuid>")

    config_relation: Mapped["ConfigRelation"] = relationship(back_populates="ct_rows")


class GT(Base):
    """Recursive sub-entries inside a GroupNode."""
    __tablename__ = "gt"

    uuid: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    gid: Mapped[str] = mapped_column(String(255), nullable=False, index=True, comment="GroupNode UUID from Neo4j")
    key: Mapped[str] = mapped_column(String(255), nullable=False, comment="NameNode UUID from Neo4j")
    val: Mapped[str] = mapped_column(String(512), nullable=False, comment="VALUE:<uuid> or GROUP:<uuid>")
