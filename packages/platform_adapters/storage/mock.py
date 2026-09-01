"""Registered object storage Mock."""

from __future__ import annotations

import hashlib

from contracts.ports import (
    ObjectMetadata,
    PortFaultCode,
    PortProviderError,
    StoredObject,
)
from platform_adapters.testing import BaseMockAdapter


class MockObjectStorage(BaseMockAdapter):
    mock_id = "MOCK-OBJECT-001"
    allowed_faults = frozenset({"QUOTA_EXCEEDED", "DELETE_FAILED", "CHECKSUM_MISMATCH"})

    def __init__(self) -> None:
        super().__init__()
        self._objects: dict[str, StoredObject] = {}

    async def put(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        checksum: str,
        idempotency_key: str,
        timeout_seconds: float,
    ) -> ObjectMetadata:
        self._before_call(timeout_seconds)
        actual_checksum = "sha256:" + hashlib.sha256(content).hexdigest()
        if checksum != actual_checksum:
            raise PortProviderError(
                code=PortFaultCode.CHECKSUM_MISMATCH,
                message="object checksum mismatch",
                retryable=False,
                trace_id=f"mock:{self.mock_id}:checksum",
                details={"mock_id": self.mock_id},
            )

        def produce() -> ObjectMetadata:
            metadata = ObjectMetadata(
                object_key=object_key,
                checksum=checksum,
                size_bytes=len(content),
                content_type=content_type,
            )
            self._objects[object_key] = StoredObject(metadata=metadata, content=content)
            return metadata

        return self._idempotent(
            idempotency_key=idempotency_key,
            request=(object_key, content, content_type, checksum),
            produce=produce,
        )

    async def get(self, *, object_key: str, timeout_seconds: float) -> StoredObject:
        self._before_call(timeout_seconds)
        try:
            return self._objects[object_key]
        except KeyError as exc:
            raise PortProviderError(
                code=PortFaultCode.INVALID_INPUT,
                message="object does not exist",
                retryable=False,
                trace_id=f"mock:{self.mock_id}:missing",
                details={"mock_id": self.mock_id},
            ) from exc

    async def delete(
        self,
        *,
        object_key: str,
        idempotency_key: str,
        timeout_seconds: float,
    ) -> None:
        self._before_call(timeout_seconds)

        def produce() -> None:
            self._objects.pop(object_key, None)

        self._idempotent(
            idempotency_key=idempotency_key,
            request=object_key,
            produce=produce,
        )
