"""Registered assessment model gateway Mock."""

from contracts.ports import ModelOperation

from model._base import BaseMockModelGateway


class MockModelGatewayAssess(BaseMockModelGateway):
    mock_id = "MOCK-MODEL-ASSESS-001"
    operation = ModelOperation.ASSESS
    allowed_faults = frozenset({"TIMEOUT", "INVALID_OUTPUT"})
