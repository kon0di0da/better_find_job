"""Agent observability boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .base import Port
from .dto import AgentOpsEvent


@runtime_checkable
class AgentOpsPort(Port, Protocol):
    async def record(
        self,
        *,
        event: AgentOpsEvent,
        idempotency_key: str,
        timeout_seconds: float,
    ) -> None: ...
