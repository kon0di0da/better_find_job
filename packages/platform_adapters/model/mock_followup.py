"""Registered follow-up model gateway Mock."""

from contracts.ports import ModelOperation

from model._base import BaseMockModelGateway


class MockModelGatewayFollowUp(BaseMockModelGateway):
    mock_id = "MOCK-MODEL-FOLLOWUP-001"
    operation = ModelOperation.FOLLOW_UP
    allowed_faults = frozenset({"TIMEOUT", "INVALID_OUTPUT", "DUPLICATE_OUTPUT"})
