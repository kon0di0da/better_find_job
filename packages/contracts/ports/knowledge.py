"""Knowledge search boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .base import Port
from .dto import KnowledgeHit, KnowledgeQuery


@runtime_checkable
class KnowledgeSearchPort(Port, Protocol):
    async def search(
        self,
        *,
        query: KnowledgeQuery,
        timeout_seconds: float,
    ) -> tuple[KnowledgeHit, ...]: ...
