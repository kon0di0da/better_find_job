"""Object storage boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .base import Port
from .dto import ObjectMetadata, StoredObject


@runtime_checkable
class ObjectStoragePort(Port, Protocol):
    async def put(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        checksum: str,
        idempotency_key: str,
        timeout_seconds: float,
    ) -> ObjectMetadata: ...

    async def get(
        self,
        *,
        object_key: str,
        timeout_seconds: float,
    ) -> StoredObject: ...

    async def delete(
        self,
        *,
        object_key: str,
        idempotency_key: str,
        timeout_seconds: float,
    ) -> None: ...
