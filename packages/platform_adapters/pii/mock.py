"""Registered PII redaction Mock using only deterministic local rules."""

from __future__ import annotations

import re

from contracts.ports import RedactionResult
from platform_adapters.testing import BaseMockAdapter

_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


class MockPIIRedactor(BaseMockAdapter):
    mock_id = "MOCK-PII-001"
    allowed_faults = frozenset({"TIMEOUT", "PII_MISS", "PII_FALSE_POSITIVE"})

    async def redact(
        self,
        *,
        text: str,
        idempotency_key: str,
        timeout_seconds: float,
    ) -> RedactionResult:
        self._before_call(timeout_seconds)

        def produce() -> RedactionResult:
            redacted, email_count = _EMAIL.subn("[EMAIL]", text)
            redacted, phone_count = _PHONE.subn("[PHONE]", redacted)
            categories: list[str] = []
            if email_count:
                categories.append("EMAIL")
            if phone_count:
                categories.append("PHONE")
            return RedactionResult(
                text=redacted,
                redaction_count=email_count + phone_count,
                categories=tuple(categories),
            )

        return self._idempotent(
            idempotency_key=idempotency_key,
            request=text,
            produce=produce,
        )
