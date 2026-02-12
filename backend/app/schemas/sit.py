from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SitCreateRequest(BaseModel):
    name: str
    description: str | None = None
    confidence_level: int = Field(default=85)
    tags: list[str] | None = None


class SitSummary(BaseModel):
    sit_id: UUID
    name: str
    description: str | None = None
    confidence_level: int
    status: str
    version: int
    tags: list[str] | None = None
    created_at: datetime
    updated_at: datetime


class SitListResponse(BaseModel):
    sits: list[SitSummary]
    total: int


class SitElementBase(BaseModel):
    element_role: str
    element_type: str
    pattern: str | None = None
    case_sensitive: bool = False
    word_boundary: bool = True
    checksum_function: str | None = None
    min_matches: int = 1
    max_matches: int | None = None
    source_candidate_id: UUID | None = None


class SitElementResponse(SitElementBase):
    element_id: UUID


class SitGroupCreateRequest(BaseModel):
    group_name: str | None = None
    logic_type: str = "AND"
    proximity_window_chars: int = 300
    threshold_count: int | None = None
    element_ids: list[UUID] = Field(default_factory=list)


class SitGroupElementRef(BaseModel):
    element_id: UUID
    element_type: str
    pattern: str | None = None


class SitGroupResponse(BaseModel):
    group_id: UUID
    group_name: str | None = None
    logic_type: str
    proximity_window_chars: int
    threshold_count: int | None = None
    elements: list[SitGroupElementRef] = Field(default_factory=list)


class SitFilterResponse(BaseModel):
    filter_id: UUID
    filter_type: str
    pattern: str
    description: str | None = None


class SitDetailResponse(BaseModel):
    sit_id: UUID
    name: str
    description: str | None = None
    confidence_level: int
    status: str
    version: int
    elements: list[SitElementResponse] = Field(default_factory=list)
    groups: list[SitGroupResponse] = Field(default_factory=list)
    filters: list[SitFilterResponse] = Field(default_factory=list)


class SitUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    confidence_level: int | None = None
    tags: list[str] | None = None
    elements: list[SitElementBase] | None = None


class VersionEntry(BaseModel):
    version: int
    status: str
    updated_at: datetime


class SitVersionResponse(BaseModel):
    versions: list[VersionEntry]


class SitDiffItem(BaseModel):
    field: str
    old_value: Any
    new_value: Any


class SitCompareResponse(BaseModel):
    diff: dict[str, list[Any]]


class SitTestRequest(BaseModel):
    sample_text: str


class SitTestMatch(BaseModel):
    value: str
    position: int
    confidence: int
    matched_elements: list[dict[str, Any]]
    matched_groups: list[dict[str, Any]]


class SitTestResponse(BaseModel):
    matches: list[SitTestMatch]
    match_count: int
