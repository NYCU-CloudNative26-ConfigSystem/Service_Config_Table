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
    environment: str = "production"
    user_id: str
    entries: list[ConfigEntrySchema]
    template_version_uuid: str | None = None
    change_description: str | None = None
    source_snapshot_uuid: str | None = None
    name: str | None = None


class ConfigPromoteRequest(BaseModel):
    proj_id: str
    cmp_id: str
    from_environment: str
    to_environment: str


class ConfigPromoteByUuidRequest(BaseModel):
    to_environment: str


class RejectRequest(BaseModel):
    reason: str | None = None


class ConfigUpdateRequest(BaseModel):
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
    environment: str
    rows: list[CTRowResponse]
    # Approval fields — populated by getByUuid; None when returned by get_config (latest-only)
    approval_status: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    created_by: str | None = None
    is_latest: bool | None = None
    change_description: str | None = None
    promoted_from_uuid: str | None = None
    proj_id: str | None = None
    cmp_id: str | None = None
    name: str | None = None


class ReviewSimilaritySourceEntry(BaseModel):
    path: str
    key_uuid: str
    key_alias: str
    value_ref: str
    value_display: str
    is_group: bool = False


class ReviewSimilarityEntryMatch(BaseModel):
    source_path: str
    source_key_alias: str
    source_value_display: str
    source_value_ref: str
    candidate_path: str
    candidate_key_alias: str
    candidate_value_display: str
    candidate_value_ref: str
    match_kind: str
    score: float
    display_state: str
    display_reason: str | None = None


class ReviewSimilarityCandidate(BaseModel):
    config_relation_uuid: str
    date_created: datetime
    environment: str
    approval_status: str
    score: float
    name: str | None = None
    proj_id: str | None = None
    cmp_id: str | None = None
    matched_entries: list[ReviewSimilarityEntryMatch]


class ReviewSimilarityReport(BaseModel):
    config_relation_uuid: str
    date_created: datetime
    environment: str
    approval_status: str
    created_by: str | None = None
    name: str | None = None
    proj_id: str | None = None
    cmp_id: str | None = None
    source_entry_count: int
    candidate_count: int
    source_entries: list[ReviewSimilaritySourceEntry]
    candidates: list[ReviewSimilarityCandidate]


class ConfigApprovalResponse(BaseModel):
    config_relation_uuid: str
    approval_status: str
    approved_by: str | None
    approved_at: datetime | None
    rejection_reason: str | None


class ConfigHistoryItem(BaseModel):
    config_relation_uuid: str
    date_created: datetime
    date_deleted: datetime | None
    created_by: str | None
    entry_count: int
    is_latest: bool
    environment: str
    template_version_uuid: str | None = None
    template_version_number: int | None = None
    approval_status: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    change_description: str | None = None
    promoted_from_uuid: str | None = None
    name: str | None = None
    proj_id: str | None = None
    cmp_id: str | None = None
