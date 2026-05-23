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
