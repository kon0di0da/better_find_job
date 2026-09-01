"""Model gateway boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .base import Port
from .dto import ModelRequest, ModelResult


@runtime_checkable
class ModelGatewayPort(Port, Protocol):
    async def generate(
        self,
        *,
        request: ModelRequest,
        idempotency_key: str,
        timeout_seconds: float,
    ) -> ModelResult: ...
