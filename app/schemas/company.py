from datetime import datetime

from pydantic import BaseModel


class CompanyCreate(BaseModel):
    cmp_id: str
    display_name: str
    description: str | None = None


class CompanyResponse(BaseModel):
    uuid: str
    cmp_id: str
    display_name: str
    description: str | None
    created_by: str
    date_created: datetime

    model_config = {"from_attributes": True}
