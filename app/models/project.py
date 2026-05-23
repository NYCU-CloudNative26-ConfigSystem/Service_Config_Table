import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class Project(Base):
    __tablename__ = "project"

    uuid: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    proj_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    deleted_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    companies: Mapped[list["ProjectCompany"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectCompany(Base):
    __tablename__ = "project_company"
    __table_args__ = (UniqueConstraint("proj_id", "cmp_id", name="uq_project_company"),)

    uuid: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    proj_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("project.proj_id", ondelete="CASCADE"), nullable=False, index=True
    )
    cmp_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    date_added: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    project: Mapped["Project"] = relationship(back_populates="companies")
