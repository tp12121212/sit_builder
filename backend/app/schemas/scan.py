from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ScanCreateResponse(BaseModel):
    scan_id: UUID
    status: str
    files_count: int
    total_size_bytes: int
    created_at: datetime


class ScanResponse(BaseModel):
    scan_id: UUID
    name: str | None
    scan_type: str
    status: str
    source_files_count: int | None
    extracted_text_length: int | None
    ocr_confidence_avg: float | None
    extraction_duration_sec: float | None
    analysis_duration_sec: float | None
    created_at: datetime
    completed_at: datetime | None
    metadata: dict[str, Any] | None = None


class ScanSummary(BaseModel):
    scan_id: UUID
    name: str | None
    scan_type: str
    status: str
    source_files_count: int | None
    created_at: datetime
    completed_at: datetime | None


class ScanListResponse(BaseModel):
    scans: list[ScanSummary]


class ScanFileResponse(BaseModel):
    file_id: UUID
    file_name: str | None
    file_type: str | None
    file_size_bytes: int | None
    extraction_method: str | None
    ocr_confidence: float | None
    page_count: int | None


class EvidenceSnippet(BaseModel):
    context: str
    position: int
    confidence: float | None = None


class CandidateResponse(BaseModel):
    candidate_id: UUID
    candidate_type: str
    element_type_hint: str
    value: str
    pattern_template: str | None
    frequency: int
    confidence: float
    score: float | None
    evidence: list[EvidenceSnippet] | None = None
    metadata: dict[str, Any] | None = None


class CandidateListResponse(BaseModel):
    candidates: list[CandidateResponse]
    total: int
    page: int
    page_size: int


class ScanStatusEvent(BaseModel):
    type: str = "STATUS_UPDATE"
    scan_id: UUID
    status: str
    progress: float = Field(ge=0.0, le=1.0)
    message: str
