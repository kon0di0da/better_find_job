"""Resume parser boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from .base import Port
from .dto import ResumeParseResult


@runtime_checkable
class ResumeParserPort(Port, Protocol):
    async def parse(
        self,
        *,
        resume_id: UUID,
        content: bytes,
        mime_type: str,
        idempotency_key: str,
        timeout_seconds: float,
    ) -> ResumeParseResult: ...
