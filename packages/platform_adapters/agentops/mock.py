"""Registered AgentOps Mock."""

from __future__ import annotations

from contracts.ports import AgentOpsEvent
from platform_adapters.testing import BaseMockAdapter


class MockAgentOps(BaseMockAdapter):
    mock_id = "MOCK-AGENTOPS-001"
    allowed_faults = frozenset({"TIMEOUT", "TRACE_DROPPED", "VERSION_MISSING"})

    def __init__(self) -> None:
        super().__init__()
        self._events: list[AgentOpsEvent] = []

    @property
    def events(self) -> tuple[AgentOpsEvent, ...]:
        return tuple(self._events)

    async def record(
        self,
        *,
        event: AgentOpsEvent,
        idempotency_key: str,
        timeout_seconds: float,
    ) -> None:
        self._before_call(timeout_seconds)

        def produce() -> None:
            self._events.append(event)

        self._idempotent(
            idempotency_key=idempotency_key,
            request=event,
            produce=produce,
        )
