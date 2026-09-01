"""Registered knowledge search Mock."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from contracts.ports import KnowledgeHit, KnowledgeQuery, PortCapability
from platform_adapters.testing import BaseMockAdapter


class MockKnowledgeSearch(BaseMockAdapter):
    mock_id = "MOCK-KNOWLEDGE-001"
    capabilities = PortCapability.ASYNC | PortCapability.BATCH
    allowed_faults = frozenset({"UNAVAILABLE", "EMPTY_RESULT"})

    async def search(
        self,
        *,
        query: KnowledgeQuery,
        timeout_seconds: float,
    ) -> tuple[KnowledgeHit, ...]:
        self._before_call(timeout_seconds)
        normalized = query.text.strip().lower()
        return (
            KnowledgeHit(
                question_id=uuid5(NAMESPACE_URL, f"{self.mock_id}:{normalized}"),
                question_version_id=uuid5(NAMESPACE_URL, f"{self.mock_id}:{normalized}:v1"),
                score=1.0,
                payload={"stem": f"Synthetic question about {normalized}", "filters": dict(query.filters)},
            ),
        )[: query.limit]
