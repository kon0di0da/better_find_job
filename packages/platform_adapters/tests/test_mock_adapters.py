"""TC-MOCK-001/002 executable tests for registered Mock adapters."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
import yaml
from contracts.ports import (
    CONTRACT_VERSION,
    AgentOpsEvent,
    AgentOpsPort,
    KnowledgeQuery,
    KnowledgeSearchPort,
    ModelGatewayPort,
    ModelRequest,
    ObjectStoragePort,
    PIIRedactorPort,
    PortError,
    PortFaultCode,
    PortIdempotencyError,
    PortTimeoutError,
    ResumeParserPort,
)

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / "specs" / "mocks" / "manifest.yaml"
PORTS = {
    "ResumeParserPort": ResumeParserPort,
    "ModelGatewayPort": ModelGatewayPort,
    "KnowledgeSearchPort": KnowledgeSearchPort,
    "AgentOpsPort": AgentOpsPort,
    "ObjectStoragePort": ObjectStoragePort,
    "PIIRedactorPort": PIIRedactorPort,
}


def _manifest_entries() -> list[dict[str, object]]:
    document = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    return document["mocks"]


def _load_adapter(entry: dict[str, object]) -> type[object]:
    source = ROOT / str(entry["source_path"])
    module_name = f"_manifest_{str(entry['mock_id']).lower().replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return getattr(module, str(entry["adapter_class"]))


def _call(adapter: object, port_name: str, *, key: str, variant: str = "a") -> object:
    timeout = 0.5
    if port_name == "ResumeParserPort":
        return adapter.parse(  # type: ignore[attr-defined, no-any-return]
            resume_id=uuid5(NAMESPACE_URL, variant),
            content=f"synthetic-{variant}".encode(),
            mime_type="text/plain",
            idempotency_key=key,
            timeout_seconds=timeout,
        )
    if port_name == "ModelGatewayPort":
        return adapter.generate(  # type: ignore[attr-defined, no-any-return]
            request=ModelRequest(
                operation=adapter.operation,  # type: ignore[attr-defined]
                payload={"variant": variant},
                trace_id=f"trace-{variant}",
            ),
            idempotency_key=key,
            timeout_seconds=timeout,
        )
    if port_name == "KnowledgeSearchPort":
        return adapter.search(  # type: ignore[attr-defined, no-any-return]
            query=KnowledgeQuery(text=f"query-{variant}", limit=3),
            timeout_seconds=timeout,
        )
    if port_name == "AgentOpsPort":
        return adapter.record(  # type: ignore[attr-defined, no-any-return]
            event=AgentOpsEvent(
                name="synthetic.event",
                trace_id=f"trace-{variant}",
                attributes={"variant": variant},
            ),
            idempotency_key=key,
            timeout_seconds=timeout,
        )
    if port_name == "ObjectStoragePort":
        content = f"synthetic-{variant}".encode()
        return adapter.put(  # type: ignore[attr-defined, no-any-return]
            object_key=f"objects/{variant}",
            content=content,
            content_type="text/plain",
            checksum="sha256:" + hashlib.sha256(content).hexdigest(),
            idempotency_key=key,
            timeout_seconds=timeout,
        )
    if port_name == "PIIRedactorPort":
        return adapter.redact(  # type: ignore[attr-defined, no-any-return]
            text=f"Synthetic User {variant}",
            idempotency_key=key,
            timeout_seconds=timeout,
        )
    raise AssertionError(f"unknown port: {port_name}")


def test_tc_mock_001_manifest_has_no_missing_or_unregistered_adapters() -> None:
    entries = _manifest_entries()
    declared_paths = {str(entry["source_path"]) for entry in entries}
    discovered_paths = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "packages" / "platform_adapters").rglob("mock*.py")
    }
    assert len({entry["mock_id"] for entry in entries}) == len(entries)
    assert discovered_paths == declared_paths

    for entry in entries:
        adapter_class = _load_adapter(entry)
        adapter = adapter_class()
        assert adapter.mock_id == entry["mock_id"]
        assert adapter.contract_version == entry["contract_version"] == CONTRACT_VERSION
        assert isinstance(adapter, PORTS[str(entry["port"])])
        assert adapter.allowed_faults == frozenset(entry["fault_scenarios"])


def test_tc_mock_002_every_declared_fault_is_injectable_once() -> None:
    for entry in _manifest_entries():
        adapter_class = _load_adapter(entry)
        for index, fault in enumerate(entry["fault_scenarios"]):
            adapter = adapter_class()
            adapter.inject_fault(str(fault))
            with pytest.raises(PortError) as captured:
                asyncio.run(_call(adapter, str(entry["port"]), key=f"fault-{index}"))
            if fault == "TIMEOUT":
                assert isinstance(captured.value, PortTimeoutError)
                assert captured.value.code is PortFaultCode.PORT_TIMEOUT
                assert captured.value.retryable is True
            else:
                assert captured.value.code.value == fault
            result = asyncio.run(_call(adapter, str(entry["port"]), key=f"after-{index}"))
            if str(entry["port"]) != "AgentOpsPort":
                assert result is not None


def test_tc_mock_002_idempotent_methods_cache_and_reject_conflicts() -> None:
    for entry in _manifest_entries():
        if str(entry["port"]) == "KnowledgeSearchPort":
            continue
        adapter = _load_adapter(entry)()
        first = asyncio.run(_call(adapter, str(entry["port"]), key="same-key", variant="same"))
        second = asyncio.run(_call(adapter, str(entry["port"]), key="same-key", variant="same"))
        assert second is first or second == first
        with pytest.raises(PortIdempotencyError):
            asyncio.run(_call(adapter, str(entry["port"]), key="same-key", variant="different"))


def test_mock_success_paths_are_deterministic_and_in_memory_only() -> None:
    entries = {entry["mock_id"]: entry for entry in _manifest_entries()}

    knowledge = _load_adapter(entries["MOCK-KNOWLEDGE-001"])()
    hits = asyncio.run(
        knowledge.search(query=KnowledgeQuery(text="postgresql", limit=2), timeout_seconds=0.5)
    )
    assert len(hits) == 1
    assert hits[0].question_id == uuid5(NAMESPACE_URL, "MOCK-KNOWLEDGE-001:postgresql")

    storage = _load_adapter(entries["MOCK-OBJECT-001"])()
    content = b"synthetic-object"
    metadata = asyncio.run(
        storage.put(
            object_key="objects/1",
            content=content,
            content_type="text/plain",
            checksum="sha256:" + hashlib.sha256(content).hexdigest(),
            idempotency_key="put-1",
            timeout_seconds=0.5,
        )
    )
    stored = asyncio.run(storage.get(object_key=metadata.object_key, timeout_seconds=0.5))
    assert stored.content == content
    asyncio.run(
        storage.delete(
            object_key=metadata.object_key,
            idempotency_key="delete-1",
            timeout_seconds=0.5,
        )
    )

    agentops = _load_adapter(entries["MOCK-AGENTOPS-001"])()
    event = AgentOpsEvent(name="synthetic.event", trace_id=str(uuid4()), attributes={})
    asyncio.run(
        agentops.record(
            event=event,
            idempotency_key="event-1",
            timeout_seconds=0.5,
        )
    )
    assert agentops.events == (event,)
