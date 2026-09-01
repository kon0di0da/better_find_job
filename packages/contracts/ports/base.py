"""Shared primitives for all external capability ports."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from enum import Flag, StrEnum, auto
from types import MappingProxyType
from typing import Protocol

CONTRACT_VERSION = "0.2"
_ERROR_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]+$")


class PortCapability(Flag):
    """Capabilities that an adapter can advertise without exposing its provider."""

    ASYNC = auto()
    IDEMPOTENCY = auto()
    STREAMING = auto()
    BATCH = auto()


class PortFaultCode(StrEnum):
    """Stable fault vocabulary shared by the manifest and all adapters."""

    PORT_TIMEOUT = "PORT_TIMEOUT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    INVALID_INPUT = "INVALID_INPUT"
    PARTIAL_RESULT = "PARTIAL_RESULT"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    EMPTY_RESULT = "EMPTY_RESULT"
    HALLUCINATION = "HALLUCINATION"
    DUPLICATE_OUTPUT = "DUPLICATE_OUTPUT"
    UNAVAILABLE = "UNAVAILABLE"
    TRACE_DROPPED = "TRACE_DROPPED"
    VERSION_MISSING = "VERSION_MISSING"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    DELETE_FAILED = "DELETE_FAILED"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    PII_MISS = "PII_MISS"
    PII_FALSE_POSITIVE = "PII_FALSE_POSITIVE"


class PortError(Exception):
    """Provider-neutral error safe to cross the application boundary."""

    def __init__(
        self,
        *,
        code: PortFaultCode,
        message: str,
        retryable: bool,
        trace_id: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        if not message:
            raise ValueError("message must not be empty")
        if not trace_id:
            raise ValueError("trace_id must not be empty")
        if not _ERROR_CODE_PATTERN.fullmatch(code.value):
            raise ValueError(f"invalid error code: {code.value}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.trace_id = trace_id
        self.details = MappingProxyType(dict(details or {}))

    def to_error_response(self) -> dict[str, object]:
        """Return fields compatible with error-response.schema.json."""
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "trace_id": self.trace_id,
            "details": dict(self.details),
        }


class PortTimeoutError(PortError):
    """Normalized timeout; callers may retry with the same idempotency key."""

    def __init__(
        self,
        *,
        message: str,
        trace_id: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(
            code=PortFaultCode.PORT_TIMEOUT,
            message=message,
            retryable=True,
            trace_id=trace_id,
            details=details,
        )


class PortIdempotencyError(PortError):
    """The same key was reused with a different logical request."""

    def __init__(
        self,
        *,
        message: str,
        trace_id: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(
            code=PortFaultCode.IDEMPOTENCY_CONFLICT,
            message=message,
            retryable=False,
            trace_id=trace_id,
            details=details,
        )


class PortProviderError(PortError):
    """A provider fault mapped into the stable Port error vocabulary."""


def port_fault_from_manifest(value: str) -> PortFaultCode:
    """Map manifest vocabulary to the stable provider-neutral error code."""
    normalized = PortFaultCode.PORT_TIMEOUT.value if value == "TIMEOUT" else value
    try:
        return PortFaultCode(normalized)
    except ValueError as exc:
        raise ValueError(f"unknown manifest fault code: {value}") from exc


def validate_timeout(timeout_seconds: float) -> float:
    """Validate the mandatory finite, positive timeout contract."""
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise TypeError("timeout_seconds must be a number")
    normalized = float(timeout_seconds)
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError("timeout_seconds must be finite and greater than zero")
    return normalized


def validate_idempotency_key(idempotency_key: str) -> str:
    """Validate a non-empty key bounded by the persistence contract."""
    if not isinstance(idempotency_key, str):
        raise TypeError("idempotency_key must be a string")
    if not idempotency_key.strip():
        raise ValueError("idempotency_key must not be empty")
    if len(idempotency_key) > 128:
        raise ValueError("idempotency_key must contain at most 128 characters")
    return idempotency_key


class Port(Protocol):
    """Metadata every concrete adapter must expose."""

    contract_version: str
    capabilities: PortCapability
