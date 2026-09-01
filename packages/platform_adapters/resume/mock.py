"""Registered resume parser Mock."""

from __future__ import annotations

from uuid import UUID

from contracts.ports import ResumeParseResult, ResumeStatus
from platform_adapters.testing import BaseMockAdapter


class MockResumeParser(BaseMockAdapter):
    mock_id = "MOCK-RESUME-001"
    allowed_faults = frozenset({"TIMEOUT", "INVALID_INPUT", "PARTIAL_RESULT"})

    async def parse(
        self,
        *,
        resume_id: UUID,
        content: bytes,
        mime_type: str,
        idempotency_key: str,
        timeout_seconds: float,
    ) -> ResumeParseResult:
        self._before_call(timeout_seconds)

        def produce() -> ResumeParseResult:
            return ResumeParseResult(
                resume_id=resume_id,
                version=1,
                status=ResumeStatus.SUCCEEDED,
                fields={"content_length": len(content), "mime_type": mime_type},
                evidence=(),
                warnings=(),
            )

        return self._idempotent(
            idempotency_key=idempotency_key,
            request=(resume_id, content, mime_type),
            produce=produce,
        )
