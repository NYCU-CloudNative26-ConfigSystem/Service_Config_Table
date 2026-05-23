from datetime import datetime

from pydantic import BaseModel


# ── Incoming (from frontend, after SSOT write) ────────────────────────────────

class GroupEntrySchema(BaseModel):
    gid: str
    key: str
    val: str
    group_entries: list["GroupEntrySchema"] | None = None

GroupEntrySchema.model_rebuild()


class ConfigEntrySchema(BaseModel):
    key: str   # NameNode UUID
    val: str   # "VALUE:<uuid>" or "GROUP:<uuid>"
    group_entries: list[GroupEntrySchema] | None = None


class ConfigWriteRequest(BaseModel):
    proj_id: str
    cmp_id: str
    user_id: str
    entries: list[ConfigEntrySchema]


# ── Outgoing ──────────────────────────────────────────────────────────────────

class CTRowResponse(BaseModel):
    uuid: str
    key: str
    val: str

    model_config = {"from_attributes": True}


class ConfigReadResponse(BaseModel):
    config_relation_uuid: str
    date_created: datetime
    rows: list[CTRowResponse]
