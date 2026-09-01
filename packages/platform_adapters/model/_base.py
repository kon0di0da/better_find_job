"""Shared implementation for the four registered model gateway Mocks."""

from __future__ import annotations

from contracts.ports import (
    ModelOperation,
    ModelRequest,
    ModelResult,
    PortFaultCode,
    PortProviderError,
)
from platform_adapters.testing import BaseMockAdapter


class BaseMockModelGateway(BaseMockAdapter):
    operation: ModelOperation

    async def generate(
        self,
        *,
        request: ModelRequest,
        idempotency_key: str,
        timeout_seconds: float,
    ) -> ModelResult:
        self._before_call(timeout_seconds)
        if request.operation is not self.operation:
            raise PortProviderError(
                code=PortFaultCode.INVALID_INPUT,
                message=f"{self.mock_id} only accepts {self.operation.value}",
                retryable=False,
                trace_id=request.trace_id,
                details={"mock_id": self.mock_id},
            )

        def produce() -> ModelResult:
            return ModelResult(
                operation=self.operation,
                output={
                    "mock_id": self.mock_id,
                    "operation": self.operation.value,
                    "input": dict(request.payload),
                },
                model_version="mock-model-v1",
                prompt_version="mock-prompt-v1",
                trace_id=request.trace_id,
            )

        return self._idempotent(
            idempotency_key=idempotency_key,
            request=request,
            produce=produce,
        )
