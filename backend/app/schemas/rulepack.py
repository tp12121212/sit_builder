from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RulepackCreateRequest(BaseModel):
    name: str
    description: str | None = None
    sit_ids: list[UUID]


class RulepackCreateResponse(BaseModel):
    rulepack_id: UUID
    name: str
    sit_count: int
    purview_guid: str
    xml_download_url: str
    powershell_download_url: str
    readme_download_url: str
    created_at: datetime


class RulepackSummary(BaseModel):
    rulepack_id: UUID
    name: str
    sit_count: int | None
    created_at: datetime


class RulepackListResponse(BaseModel):
    rulepacks: list[RulepackSummary]


class RulepackDetailResponse(BaseModel):
    rulepack_id: UUID
    name: str
    description: str | None
    sits: list[dict]
    xml_download_url: str
    powershell_download_url: str
    created_at: datetime
