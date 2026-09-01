"""PII redaction boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .base import Port
from .dto import RedactionResult


@runtime_checkable
class PIIRedactorPort(Port, Protocol):
    async def redact(
        self,
        *,
        text: str,
        idempotency_key: str,
        timeout_seconds: float,
    ) -> RedactionResult: ...
