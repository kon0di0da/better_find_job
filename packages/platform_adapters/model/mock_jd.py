"""Registered JD model gateway Mock."""

from contracts.ports import ModelOperation

from model._base import BaseMockModelGateway


class MockModelGatewayJD(BaseMockModelGateway):
    mock_id = "MOCK-MODEL-JD-001"
    operation = ModelOperation.JD
    allowed_faults = frozenset({"TIMEOUT", "INVALID_OUTPUT", "EMPTY_RESULT"})
