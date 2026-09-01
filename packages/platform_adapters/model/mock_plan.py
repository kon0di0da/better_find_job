"""Registered interview-plan model gateway Mock."""

from contracts.ports import ModelOperation

from model._base import BaseMockModelGateway


class MockModelGatewayPlan(BaseMockModelGateway):
    mock_id = "MOCK-MODEL-PLAN-001"
    operation = ModelOperation.PLAN
    allowed_faults = frozenset({"TIMEOUT", "INVALID_OUTPUT", "HALLUCINATION"})
