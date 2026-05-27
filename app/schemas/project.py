from datetime import datetime

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    proj_id: str
    display_name: str
    description: str | None = None


class AddCompanyRequest(BaseModel):
    cmp_id: str


class ProjectResponse(BaseModel):
    uuid: str
    proj_id: str
    display_name: str
    description: str | None
    created_by: str
    date_created: datetime
    companies: list[str]

    model_config = {"from_attributes": True}


class AddTemplateKeyRequest(BaseModel):
    alias: str
    position: int = 0


class ProjectTemplateKeyResponse(BaseModel):
    uuid: str
    proj_id: str
    alias: str
    position: int
    date_created: datetime

    model_config = {"from_attributes": True}


class ProjectTemplateVersionResponse(BaseModel):
    uuid: str
    proj_id: str
    version_number: int
    latest: bool
    created_by: str
    date_created: datetime
    keys: list[str]

    model_config = {"from_attributes": True}


class PublishedTemplateKeysResponse(BaseModel):
    version_uuid: str | None
    keys: list[str]
