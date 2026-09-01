"""Shared deterministic behavior for registered in-memory Mock adapters."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import TypeVar
from uuid import UUID

from contracts.ports import (
    CONTRACT_VERSION,
    PortCapability,
    PortFaultCode,
    PortIdempotencyError,
    PortProviderError,
    PortTimeoutError,
    port_fault_from_manifest,
    validate_idempotency_key,
    validate_timeout,
)

_Result = TypeVar("_Result")
_RETRYABLE_FAULTS = {
    PortFaultCode.UNAVAILABLE,
    PortFaultCode.TRACE_DROPPED,
    PortFaultCode.DELETE_FAILED,
}


def _canonicalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _canonicalize(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return {"$bytes": value.hex()}
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonicalize(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported idempotency value: {type(value).__name__}")


def _request_fingerprint(request: object) -> str:
    encoded = json.dumps(
        _canonicalize(request),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class BaseMockAdapter:
    """Instance-scoped fault injection and deterministic idempotency support."""

    mock_id = ""
    contract_version = CONTRACT_VERSION
    capabilities = PortCapability.ASYNC | PortCapability.IDEMPOTENCY
    allowed_faults: frozenset[str] = frozenset()

    def __init__(self) -> None:
        self._pending_fault: str | None = None
        self._idempotency_cache: dict[str, tuple[str, object]] = {}

    def inject_fault(self, fault: str) -> None:
        """Inject one declared fault into the next adapter call."""
        if fault not in self.allowed_faults:
            raise ValueError(f"{fault} is not declared for {self.mock_id}")
        self._pending_fault = fault

    def _before_call(self, timeout_seconds: float) -> None:
        validate_timeout(timeout_seconds)
        if self._pending_fault is None:
            return
        fault = self._pending_fault
        self._pending_fault = None
        if fault == "TIMEOUT":
            raise PortTimeoutError(
                message=f"injected timeout for {self.mock_id}",
                trace_id=f"mock:{self.mock_id}:timeout",
                details={"mock_id": self.mock_id},
            )
        code = port_fault_from_manifest(fault)
        raise PortProviderError(
            code=code,
            message=f"injected {fault} for {self.mock_id}",
            retryable=code in _RETRYABLE_FAULTS,
            trace_id=f"mock:{self.mock_id}:{fault.lower()}",
            details={"mock_id": self.mock_id},
        )

    def _idempotent(
        self,
        *,
        idempotency_key: str,
        request: object,
        produce: Callable[[], _Result],
    ) -> _Result:
        key = validate_idempotency_key(idempotency_key)
        fingerprint = _request_fingerprint(request)
        cached = self._idempotency_cache.get(key)
        if cached is not None:
            cached_fingerprint, cached_result = cached
            if cached_fingerprint != fingerprint:
                raise PortIdempotencyError(
                    message="idempotency key reused with a different request",
                    trace_id=f"mock:{self.mock_id}:idempotency",
                    details={"mock_id": self.mock_id},
                )
            return cached_result  # type: ignore[return-value]
        result = produce()
        self._idempotency_cache[key] = (fingerprint, result)
        return result
