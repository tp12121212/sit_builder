import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    SIT_AUTHOR = "SIT_AUTHOR"
    VIEWER = "VIEWER"
    AUDITOR = "AUDITOR"


class ScanStatus(str, Enum):
    PENDING = "PENDING"
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ScanType(str, Enum):
    CLASSIC_NLP = "classic_nlp"
    SENTENCE_TRANSFORMER = "sentence_transformer"


class ExtractionMethod(str, Enum):
    NATIVE = "NATIVE"
    OCR = "OCR"
    HYBRID = "HYBRID"


class CandidateType(str, Enum):
    ENTITY = "ENTITY"
    KEYWORD = "KEYWORD"
    PATTERN = "PATTERN"
    NOUN_PHRASE = "NOUN_PHRASE"


class ElementTypeHint(str, Enum):
    REGEX = "REGEX"
    KEYWORD_LIST = "KEYWORD_LIST"
    DICTIONARY = "DICTIONARY"


class SitStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class ElementRole(str, Enum):
    PRIMARY = "PRIMARY"
    SUPPORTING = "SUPPORTING"


class SitElementType(str, Enum):
    REGEX = "REGEX"
    KEYWORD_LIST = "KEYWORD_LIST"
    DICTIONARY = "DICTIONARY"
    FUNCTION = "FUNCTION"


class LogicType(str, Enum):
    AND = "AND"
    OR = "OR"
    THRESHOLD = "THRESHOLD"


class FilterType(str, Enum):
    INCLUDE = "INCLUDE"
    EXCLUDE = "EXCLUDE"


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    azure_tenant_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    storage_quota_gb: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    azure_oid: Mapped[str | None] = mapped_column(String(255), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(String(50), default=UserRole.ADMIN.value, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Scan(Base):
    __tablename__ = "scans"

    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    name: Mapped[str | None] = mapped_column(String(255))
    scan_type: Mapped[ScanType] = mapped_column(String(50), default=ScanType.CLASSIC_NLP.value, nullable=False)
    status: Mapped[ScanStatus] = mapped_column(String(50), default=ScanStatus.PENDING.value, nullable=False)
    source_files_count: Mapped[int | None] = mapped_column(Integer)
    total_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    extracted_text_length: Mapped[int | None] = mapped_column(Integer)
    extraction_duration_sec: Mapped[float | None] = mapped_column(Float)
    analysis_duration_sec: Mapped[float | None] = mapped_column(Float)
    ocr_confidence_avg: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScanFile(Base):
    __tablename__ = "scan_files"

    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scans.scan_id", ondelete="CASCADE"))
    file_name: Mapped[str | None] = mapped_column(String(500))
    file_type: Mapped[str | None] = mapped_column(String(100))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    blob_path: Mapped[str | None] = mapped_column(String(1000))
    extracted_text_blob_path: Mapped[str | None] = mapped_column(String(1000))
    extraction_method: Mapped[ExtractionMethod | None] = mapped_column(String(50))
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    page_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Candidate(Base):
    __tablename__ = "candidates"

    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scans.scan_id", ondelete="CASCADE"))
    candidate_type: Mapped[CandidateType] = mapped_column(String(50), nullable=False)
    element_type_hint: Mapped[ElementTypeHint] = mapped_column(String(50), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    pattern_template: Mapped[str | None] = mapped_column(String(500))
    frequency: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    document_frequency: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    entropy: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[list | None] = mapped_column(JSON)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SitDefinition(Base):
    __tablename__ = "sit_definitions"

    sit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    confidence_level: Mapped[int] = mapped_column(Integer, default=85, nullable=False)
    status: Mapped[SitStatus] = mapped_column(String(50), default=SitStatus.DRAFT.value, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    parent_sit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sit_definitions.sit_id"))
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("confidence_level IN (75,85,95)", name="ck_sit_confidence_level"),
        UniqueConstraint("tenant_id", "name", "version", name="uq_sit_tenant_name_version"),
    )


class SitElement(Base):
    __tablename__ = "sit_elements"

    element_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sit_definitions.sit_id", ondelete="CASCADE"))
    element_role: Mapped[ElementRole] = mapped_column(String(50), nullable=False)
    element_type: Mapped[SitElementType] = mapped_column(String(50), nullable=False)
    pattern: Mapped[str | None] = mapped_column(Text)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    word_boundary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    checksum_function: Mapped[str | None] = mapped_column(String(100))
    min_matches: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_matches: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SitElementGroup(Base):
    __tablename__ = "sit_element_groups"

    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sit_definitions.sit_id", ondelete="CASCADE"))
    group_name: Mapped[str | None] = mapped_column(String(255))
    logic_type: Mapped[LogicType] = mapped_column(String(50), default=LogicType.AND.value, nullable=False)
    threshold_count: Mapped[int | None] = mapped_column(Integer)
    proximity_window_chars: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SitGroupElement(Base):
    __tablename__ = "sit_group_elements"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sit_element_groups.group_id", ondelete="CASCADE"), primary_key=True
    )
    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sit_elements.element_id", ondelete="CASCADE"), primary_key=True
    )


class SitFilter(Base):
    __tablename__ = "sit_filters"

    filter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sit_definitions.sit_id", ondelete="CASCADE"))
    filter_type: Mapped[FilterType] = mapped_column(String(50), nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Rulepack(Base):
    __tablename__ = "rulepacks"

    rulepack_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    xml_blob_path: Mapped[str | None] = mapped_column(String(1000))
    powershell_blob_path: Mapped[str | None] = mapped_column(String(1000))
    readme_blob_path: Mapped[str | None] = mapped_column(String(1000))
    sit_count: Mapped[int | None] = mapped_column(Integer)
    purview_guid: Mapped[str | None] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RulepackSit(Base):
    __tablename__ = "rulepack_sits"

    rulepack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rulepacks.rulepack_id", ondelete="CASCADE"), primary_key=True
    )
    sit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sit_definitions.sit_id", ondelete="CASCADE"), primary_key=True
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    changes: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
