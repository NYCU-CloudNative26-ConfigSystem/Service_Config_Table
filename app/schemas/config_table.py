from datetime import datetime

from pydantic import BaseModel, Field


class ConfigTableCreate(BaseModel):
    """Payload for creating a new config table entry."""

    from_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Key ID from Config Service",
    )
    to_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Value ID from Config Service",
    )
    company: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Company the creator belongs to",
    )


class ConfigTableUpdate(BaseModel):
    """Payload for partially updating an existing config table entry."""

    from_id: str | None = Field(None, min_length=1, max_length=255)
    to_id: str | None = Field(None, min_length=1, max_length=255)
    company: str | None = Field(None, min_length=1, max_length=255)


class ConfigTableResponse(BaseModel):
    """Response schema for a config table entry."""

    id: str
    from_id: str
    to_id: str
    creator: str
    company: str
    create_time: datetime

    model_config = {"from_attributes": True}
