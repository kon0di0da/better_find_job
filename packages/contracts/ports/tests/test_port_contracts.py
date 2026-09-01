"""TC-PORT-001 executable contract tests."""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import yaml
from contracts.ports import (
    CONTRACT_VERSION,
    AgentOpsEvent,
    AgentOpsPort,
    EvidenceRef,
    JDProfile,
    JDSkill,
    KnowledgeQuery,
    KnowledgeSearchPort,
    ModelGatewayPort,
    ObjectStoragePort,
    PIIRedactorPort,
    PortCapability,
    PortError,
    PortFaultCode,
    PortIdempotencyError,
    PortTimeoutError,
    ResumeParseResult,
    ResumeParserPort,
    ResumeStatus,
    SkillLevel,
    port_fault_from_manifest,
    validate_idempotency_key,
    validate_timeout,
)

ROOT = Path(__file__).resolve().parents[4]
MANIFEST = ROOT / "specs" / "mocks" / "manifest.yaml"
EXPECTED_PORTS = {
    "ResumeParserPort",
    "ModelGatewayPort",
    "KnowledgeSearchPort",
    "AgentOpsPort",
    "ObjectStoragePort",
    "PIIRedactorPort",
}
METHODS = {
    ResumeParserPort: {"parse"},
    ModelGatewayPort: {"generate"},
    KnowledgeSearchPort: {"search"},
    AgentOpsPort: {"record"},
    ObjectStoragePort: {"put", "get", "delete"},
    PIIRedactorPort: {"redact"},
}
IDEMPOTENT_METHODS = {"parse", "generate", "record", "put", "delete", "redact"}


class CompleteAdapter:
    """Structural fake used only to verify runtime-checkable protocols."""

    contract_version = CONTRACT_VERSION
    capabilities = PortCapability.ASYNC | PortCapability.IDEMPOTENCY

    async def parse(self, **kwargs: object) -> object:
        return kwargs

    async def generate(self, **kwargs: object) -> object:
        return kwargs

    async def search(self, **kwargs: object) -> object:
        return kwargs

    async def record(self, **kwargs: object) -> object:
        return kwargs

    async def put(self, **kwargs: object) -> object:
        return kwargs

    async def get(self, **kwargs: object) -> object:
        return kwargs

    async def delete(self, **kwargs: object) -> object:
        return kwargs

    async def redact(self, **kwargs: object) -> object:
        return kwargs


def test_contract_version_and_runtime_protocols() -> None:
    """All six manifest ports are exported as runtime-checkable contracts."""
    adapter = CompleteAdapter()
    assert CONTRACT_VERSION == "0.2"
    assert {port.__name__ for port in METHODS} == EXPECTED_PORTS
    assert all(isinstance(adapter, port) for port in METHODS)


@pytest.mark.parametrize(("port", "method_names"), METHODS.items())
def test_async_timeout_and_idempotency_signatures(
    port: type[object], method_names: set[str]
) -> None:
    """Every external call is async and declares timeout/idempotency explicitly."""
    for method_name in method_names:
        method = getattr(port, method_name)
        assert inspect.iscoroutinefunction(method), f"{port.__name__}.{method_name} must be async"
        parameters = inspect.signature(method).parameters
        timeout = parameters["timeout_seconds"]
        assert timeout.kind is inspect.Parameter.KEYWORD_ONLY
        assert timeout.default is inspect.Parameter.empty
        if method_name in IDEMPOTENT_METHODS:
            idempotency = parameters["idempotency_key"]
            assert idempotency.kind is inspect.Parameter.KEYWORD_ONLY
            assert idempotency.default is inspect.Parameter.empty
        else:
            assert "idempotency_key" not in parameters


def test_manifest_ports_and_faults_are_fully_represented() -> None:
    """Every registered Mock targets a known Port and a typed fault code."""
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == CONTRACT_VERSION
    assert {item["port"] for item in manifest["mocks"]} == EXPECTED_PORTS
    assert all(item["contract_version"] == CONTRACT_VERSION for item in manifest["mocks"])
    manifest_faults = {fault for item in manifest["mocks"] for fault in item["fault_scenarios"]}
    mapped_faults = {fault: port_fault_from_manifest(fault) for fault in manifest_faults}
    assert set(mapped_faults) == manifest_faults
    assert mapped_faults["TIMEOUT"] is PortFaultCode.PORT_TIMEOUT


def test_port_error_is_losslessly_serializable() -> None:
    error = PortError(
        code=PortFaultCode.INVALID_OUTPUT,
        message="provider returned invalid output",
        retryable=False,
        trace_id="trace-001",
        details={"provider": "mock"},
    )
    assert str(error) == "provider returned invalid output"
    assert error.to_error_response() == {
        "code": "INVALID_OUTPUT",
        "message": "provider returned invalid output",
        "retryable": False,
        "trace_id": "trace-001",
        "details": {"provider": "mock"},
    }
    assert re.fullmatch(r"^[A-Z][A-Z0-9_]+$", error.code.value)


def test_timeout_and_idempotency_errors_have_fixed_semantics() -> None:
    timeout = PortTimeoutError(message="deadline exceeded", trace_id="trace-timeout")
    assert timeout.code is PortFaultCode.PORT_TIMEOUT
    assert timeout.retryable is True

    conflict = PortIdempotencyError(message="payload mismatch", trace_id="trace-idem")
    assert conflict.code is PortFaultCode.IDEMPOTENCY_CONFLICT
    assert conflict.retryable is False


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_timeout_must_be_positive_and_finite(value: float) -> None:
    with pytest.raises(ValueError):
        validate_timeout(value)


@pytest.mark.parametrize("value", ["", " ", "x" * 129])
def test_idempotency_key_must_be_non_empty_and_bounded(value: str) -> None:
    with pytest.raises(ValueError):
        validate_idempotency_key(value)


def test_canonical_dtos_are_strict_and_validate_constraints() -> None:
    source_id = str(uuid4())
    evidence = EvidenceRef(
        source_type="RESUME",
        source_id=source_id,
        page_no=1,
        start_offset=0,
        end_offset=8,
        quote="FastAPI",
        checksum="sha256:" + "a" * 64,
    )
    result = ResumeParseResult(
        resume_id=UUID(source_id),
        version=1,
        status=ResumeStatus.SUCCEEDED,
        fields={"skills": ["Python"]},
        evidence=(evidence,),
        warnings=(),
    )
    profile = JDProfile(
        jd_id=uuid4(),
        version=1,
        title="Backend Engineer",
        skills=(
            JDSkill(skill_id="python", name="Python", level=SkillLevel.MUST, evidence_ref=evidence),
        ),
        evidence=(evidence,),
        warnings=(),
    )
    assert result.version == 1
    assert profile.skills[0].level is SkillLevel.MUST

    with pytest.raises(ValueError):
        EvidenceRef(
            source_type="RESUME",
            source_id=source_id,
            page_no=None,
            start_offset=8,
            end_offset=8,
            quote="bad",
            checksum="not-a-checksum",
        )
    with pytest.raises(TypeError):
        KnowledgeQuery(text="postgres", limit=5, filters={}, unexpected=True)  # type: ignore[call-arg]


def test_capability_flags_are_composable() -> None:
    capabilities = PortCapability.ASYNC | PortCapability.IDEMPOTENCY
    assert PortCapability.ASYNC in capabilities
    assert PortCapability.IDEMPOTENCY in capabilities
    assert PortCapability.STREAMING not in capabilities


def test_event_dto_rejects_empty_trace_id() -> None:
    with pytest.raises(ValueError):
        AgentOpsEvent(name="assessment.completed", trace_id="", attributes={})
