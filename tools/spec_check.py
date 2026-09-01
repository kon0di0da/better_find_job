#!/usr/bin/env python3
"""WP-FOUNDATION-001 的最小规范一致性检查器。"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC_ROOT = ROOT / "specs"

REQUIRED_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    "Makefile",
    "specs/baseline.yaml",
    "specs/openapi/interview-agent.openapi.yaml",
    "specs/ddl/v0.2.sql",
    "specs/events/domain-events.schema.json",
    "specs/mocks/manifest.schema.json",
    "specs/mocks/manifest.yaml",
    "specs/product/requirements.yaml",
    "specs/product/traceability.yaml",
    "specs/governance/apply-protocol.md",
    "specs/governance/change-request-template.yaml",
    "specs/governance/archive-policy.md",
]
EXPECTED_WP_IDS = {
    "WP-FOUNDATION-001", "WP-FOUNDATION-002", "WP-FOUNDATION-003",
    "WP-FOUNDATION-004", "WP-FOUNDATION-005", "WP-FOUNDATION-006",
    "WP-FOUNDATION-007", "WP-PROFILE-001", "WP-PROFILE-002", "WP-JD-001",
    "WP-KNOWLEDGE-001", "WP-PLAN-001", "WP-SESSION-001", "WP-ASSESS-001",
    "WP-OPS-001", "WP-OPS-002", "WP-DATA-001", "WP-EVENT-001",
    "WP-SECURITY-001", "WP-PERF-001", "WP-RELEASE-001",
}
EXPECTED_OPENAPI_SCHEMAS = {
    "ResumeParseResult", "JDProfile", "Question", "InterviewPlan",
    "InterviewAnswer", "AssessmentReport", "EvidenceRef", "ErrorResponse",
}
MOCK_REQUIRED_FIELDS = {
    "mock_id", "adapter_class", "source_path", "port", "contract_version",
    "fixture_version", "owner", "status", "replacement_target",
    "replacement_pr", "fault_scenarios",
}
MOCK_ID_RE = re.compile(r"^MOCK-[A-Z0-9]+(?:-[A-Z0-9]+)*-[0-9]{3}$")


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_sql(path: Path, errors: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        fail(errors, f"SQL 为空: {path.relative_to(ROOT)}")
        return
    if text.count("(") != text.count(")"):
        fail(errors, f"SQL 括号不平衡: {path.relative_to(ROOT)}")
    statements = [part.strip() for part in text.split(";") if part.strip()]
    if not statements:
        fail(errors, f"SQL 不含语句: {path.relative_to(ROOT)}")
    allowed = ("CREATE SCHEMA", "CREATE TABLE", "CREATE INDEX")
    for index, statement in enumerate(statements, 1):
        if not statement.upper().startswith(allowed):
            fail(errors, f"SQL 第 {index} 条语句不在 v0.2 DDL allowlist")


def main() -> int:
    errors: list[str] = []

    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            fail(errors, f"缺少必需文件: {relative}")

    yaml_documents: dict[Path, Any] = {}
    for path in sorted(SPEC_ROOT.rglob("*.yaml")):
        try:
            yaml_documents[path] = load_yaml(path)
        except Exception as exc:  # noqa: BLE001 - checker must aggregate failures
            fail(errors, f"YAML 解析失败 {path.relative_to(ROOT)}: {exc}")

    json_documents: dict[Path, Any] = {}
    for path in sorted(SPEC_ROOT.rglob("*.json")):
        try:
            document = load_json(path)
            json_documents[path] = document
            if path.name.endswith(".schema.json") and document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                fail(errors, f"JSON Schema 不是 Draft 2020-12: {path.relative_to(ROOT)}")
        except Exception as exc:  # noqa: BLE001
            fail(errors, f"JSON 解析失败 {path.relative_to(ROOT)}: {exc}")

    openapi_path = ROOT / "specs/openapi/interview-agent.openapi.yaml"
    if openapi_path in yaml_documents:
        openapi = yaml_documents[openapi_path]
        if str(openapi.get("openapi", "")) != "3.1.0":
            fail(errors, "OpenAPI 版本必须为 3.1.0")
        schemas = openapi.get("components", {}).get("schemas", {})
        missing = EXPECTED_OPENAPI_SCHEMAS - set(schemas)
        if missing:
            fail(errors, f"OpenAPI 缺少 canonical schemas: {sorted(missing)}")

    manifest_path = ROOT / "specs/mocks/manifest.yaml"
    manifest_schema_path = ROOT / "specs/mocks/manifest.schema.json"
    mock_ids: set[str] = set()
    if manifest_path in yaml_documents:
        manifest = yaml_documents[manifest_path]
        if str(manifest.get("manifest_version")) != "0.2":
            fail(errors, "Mock manifest_version 必须为 0.2")
        schema_document = json_documents.get(manifest_schema_path, {})
        allowed_ports = set(schema_document.get("$defs", {}).get("mock", {}).get("properties", {}).get("port", {}).get("enum", []))
        allowed_statuses = set(schema_document.get("$defs", {}).get("mock", {}).get("properties", {}).get("status", {}).get("enum", []))
        allowed_faults = set(schema_document.get("$defs", {}).get("mock", {}).get("properties", {}).get("fault_scenarios", {}).get("items", {}).get("enum", []))
        for index, mock in enumerate(manifest.get("mocks", []), 1):
            missing = MOCK_REQUIRED_FIELDS - set(mock)
            if missing:
                fail(errors, f"Mock #{index} 缺字段: {sorted(missing)}")
            mock_id = mock.get("mock_id", "")
            if not MOCK_ID_RE.fullmatch(mock_id):
                fail(errors, f"非法 Mock ID: {mock_id}")
            if mock_id in mock_ids:
                fail(errors, f"重复 Mock ID: {mock_id}")
            mock_ids.add(mock_id)
            if mock.get("port") not in allowed_ports:
                fail(errors, f"{mock_id} 使用未知 Port: {mock.get('port')}")
            if mock.get("status") not in allowed_statuses:
                fail(errors, f"{mock_id} 使用未知状态: {mock.get('status')}")
            unknown_faults = set(mock.get("fault_scenarios", [])) - allowed_faults
            if unknown_faults:
                fail(errors, f"{mock_id} 使用未知故障场景: {sorted(unknown_faults)}")

    wp_documents: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted((SPEC_ROOT / "work-packages").glob("*.yaml")):
        document = yaml_documents.get(path)
        if not isinstance(document, dict):
            continue
        wp_id = document.get("id")
        if not isinstance(wp_id, str):
            fail(errors, f"WP 缺少字符串 id: {path.relative_to(ROOT)}")
            continue
        if wp_id in wp_documents:
            fail(errors, f"重复 WP ID: {wp_id}")
        wp_documents[wp_id] = (path, document)
        for field in ("depends_on", "outputs", "traceability", "verification", "dod", "rollback", "path_allowlist"):
            if field not in document:
                fail(errors, f"{wp_id} 缺字段 {field}")
    if set(wp_documents) != EXPECTED_WP_IDS:
        fail(errors, f"WP 集合不完整；missing={sorted(EXPECTED_WP_IDS - set(wp_documents))}, extra={sorted(set(wp_documents) - EXPECTED_WP_IDS)}")
    for wp_id, (_, document) in wp_documents.items():
        for dependency in document.get("depends_on", []):
            if dependency not in wp_documents:
                fail(errors, f"{wp_id} 依赖不存在: {dependency}")

    requirements_path = ROOT / "specs/product/requirements.yaml"
    trace_path = ROOT / "specs/product/traceability.yaml"
    if requirements_path in yaml_documents and trace_path in yaml_documents:
        requirements = yaml_documents[requirements_path]
        traceability = yaml_documents[trace_path]
        requirement_ids = {item.get("id") for item in requirements.get("requirements", [])}
        trace_entries = traceability.get("entries", [])
        traced_ids = {item.get("requirement_id") for item in trace_entries}
        missing = requirement_ids - traced_ids
        if requirements.get("priority") == "P0" and missing:
            fail(errors, f"P0 REQ 缺追踪: {sorted(missing)}")
        for entry in trace_entries:
            req_id = entry.get("requirement_id")
            if req_id not in requirement_ids:
                fail(errors, f"追踪引用未知 REQ: {req_id}")
            if not entry.get("work_packages") or not entry.get("test_cases"):
                fail(errors, f"{req_id} 缺 WP 或 TC 追踪")
            for wp_id in entry.get("work_packages", []):
                if wp_id not in wp_documents:
                    fail(errors, f"{req_id} 引用未知 WP: {wp_id}")
            for mock_id in entry.get("mocks", []):
                if mock_id not in mock_ids:
                    fail(errors, f"{req_id} 引用未知 Mock: {mock_id}")
            for relative in entry.get("implementation_paths", []):
                if not (ROOT / relative).exists():
                    fail(errors, f"{req_id} implementation_path 不存在: {relative}")

    ddl_path = ROOT / "specs/ddl/v0.2.sql"
    if ddl_path.is_file():
        check_sql(ddl_path, errors)

    baseline_path = ROOT / "specs/baseline.yaml"
    if baseline_path in yaml_documents:
        baseline = yaml_documents[baseline_path]
        expected_metadata = {
            "spec_version": "v0.2",
            "status": "Accepted",
            "date": "2026-09-01",
            "remote_repository": "https://github.com/kon0di0da/better_find_job.git",
            "branch": "aime/1788264697-spec-materialization",
            "git_commit": "PENDING_FIRST_COMMIT",
        }
        for key, expected in expected_metadata.items():
            if str(baseline.get(key)) != expected:
                fail(errors, f"baseline.{key} 应为 {expected!r}")
        lark = baseline.get("lark", {})
        if lark.get("doc_token") != "AIsvdTz9CoM8qhxZ4S9cPJt0n3c" or lark.get("accepted_revision_id") != 87 or lark.get("materialized_revision_id") != 90:
            fail(errors, "baseline Lark token/revision 不符合锁定值")
        checksums = baseline.get("checksums", {})
        for relative, expected in checksums.items():
            path = ROOT / relative
            if not path.is_file():
                fail(errors, f"baseline checksum 文件不存在: {relative}")
            elif expected != f"sha256:{sha256(path)}":
                fail(errors, f"baseline checksum 不一致: {relative}")
        canonical = {
            path.relative_to(ROOT).as_posix()
            for path in SPEC_ROOT.rglob("*")
            if path.is_file() and path != baseline_path
        }
        if set(checksums) != canonical:
            fail(errors, f"baseline 未完整覆盖 canonical 文件；missing={sorted(canonical - set(checksums))}, extra={sorted(set(checksums) - canonical)}")
        try:
            branch = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"], cwd=ROOT,
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            if branch != baseline.get("branch"):
                fail(errors, f"当前分支 {branch} 与 baseline 不一致")
        except (OSError, subprocess.CalledProcessError) as exc:
            fail(errors, f"无法读取 Git 分支: {exc}")

    if errors:
        print("spec-check: FAIL", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"spec-check: PASS ({len(yaml_documents)} YAML, {len(list(SPEC_ROOT.rglob('*.json')))} JSON, {len(wp_documents)} WP, {len(mock_ids)} Mock)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
