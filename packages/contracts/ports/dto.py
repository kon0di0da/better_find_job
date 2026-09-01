"""Provider-neutral data transfer objects used by Port protocols."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

_CHECKSUM_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")


class EvidenceSourceType(StrEnum):
    RESUME = "RESUME"
    JD = "JD"
    ANSWER = "ANSWER"


class ResumeStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class SkillLevel(StrEnum):
    MUST = "MUST"
    PREFERRED = "PREFERRED"
    BONUS = "BONUS"


class ModelOperation(StrEnum):
    JD = "JD"
    PLAN = "PLAN"
    FOLLOW_UP = "FOLLOW_UP"
    ASSESS = "ASSESS"


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceRef:
    source_type: EvidenceSourceType
    source_id: str
    start_offset: int
    end_offset: int
    quote: str
    checksum: str
    page_no: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_type", EvidenceSourceType(self.source_type))
        if not self.source_id:
            raise ValueError("source_id must not be empty")
        if self.page_no is not None and self.page_no < 1:
            raise ValueError("page_no must be at least 1")
        if self.start_offset < 0 or self.end_offset <= self.start_offset:
            raise ValueError("evidence offsets must define a non-empty range")
        if not self.quote:
            raise ValueError("quote must not be empty")
        if not _CHECKSUM_PATTERN.fullmatch(self.checksum):
            raise ValueError("checksum must use sha256:<64 lowercase hex> format")


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeParseResult:
    resume_id: UUID
    version: int
    status: ResumeStatus
    fields: Mapping[str, object]
    evidence: tuple[EvidenceRef, ...]
    warnings: tuple[str, ...]
    task_id: UUID | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ResumeStatus(self.status))
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if self.version < 1:
            raise ValueError("version must be at least 1")


@dataclass(frozen=True, slots=True, kw_only=True)
class JDSkill:
    skill_id: str
    name: str
    level: SkillLevel
    evidence_ref: EvidenceRef

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", SkillLevel(self.level))
        if not self.skill_id or not self.name:
            raise ValueError("skill_id and name must not be empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class JDProfile:
    jd_id: UUID
    version: int
    title: str | None
    skills: tuple[JDSkill, ...]
    evidence: tuple[EvidenceRef, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "skills", tuple(self.skills))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if self.version < 1:
            raise ValueError("version must be at least 1")


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelRequest:
    operation: ModelOperation
    payload: Mapping[str, object]
    trace_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation", ModelOperation(self.operation))
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        if not self.trace_id:
            raise ValueError("trace_id must not be empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelResult:
    operation: ModelOperation
    output: Mapping[str, object]
    model_version: str
    prompt_version: str
    trace_id: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation", ModelOperation(self.operation))
        object.__setattr__(self, "output", MappingProxyType(dict(self.output)))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if not self.model_version or not self.prompt_version or not self.trace_id:
            raise ValueError("model_version, prompt_version and trace_id are required")


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeQuery:
    text: str
    limit: int
    filters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "filters", MappingProxyType(dict(self.filters)))
        if not self.text.strip():
            raise ValueError("query text must not be empty")
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")


@dataclass(frozen=True, slots=True, kw_only=True)
class KnowledgeHit:
    question_id: UUID
    question_version_id: UUID
    score: float
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        if not 0 <= self.score <= 1:
            raise ValueError("score must be between 0 and 1")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentOpsEvent:
    name: str
    trace_id: str
    attributes: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))
        if not self.name or not self.trace_id:
            raise ValueError("event name and trace_id must not be empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class ObjectMetadata:
    object_key: str
    checksum: str
    size_bytes: int
    content_type: str

    def __post_init__(self) -> None:
        if not self.object_key or not self.content_type:
            raise ValueError("object_key and content_type must not be empty")
        if not _CHECKSUM_PATTERN.fullmatch(self.checksum):
            raise ValueError("checksum must use sha256:<64 lowercase hex> format")
        if self.size_bytes <= 0:
            raise ValueError("size_bytes must be greater than zero")


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredObject:
    metadata: ObjectMetadata
    content: bytes

    def __post_init__(self) -> None:
        if len(self.content) != self.metadata.size_bytes:
            raise ValueError("content length must equal metadata.size_bytes")


@dataclass(frozen=True, slots=True, kw_only=True)
class RedactionResult:
    text: str
    redaction_count: int
    categories: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "categories", tuple(self.categories))
        if self.redaction_count < 0:
            raise ValueError("redaction_count must not be negative")
