"""Acceptance contract for the WP-FOUNDATION-007 GitHub Actions workflow."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import WORKFLOW_PATH

GATES = (
    "lint",
    "unit",
    "spec-check",
    "mock-check",
    "contract-test",
    "fixture-test",
    "migration-test",
    "egress-scan",
)


def _load_workflow(path: Path) -> dict[str, Any]:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict), "ci.yml 必须是有效 YAML mapping"
    assert isinstance(workflow.get("jobs"), dict) and workflow["jobs"], "workflow 必须定义 jobs"
    return workflow


def _job_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps = job.get("steps", [])
    assert isinstance(steps, list)
    return [step for step in steps if isinstance(step, dict)]


def _gate_locations(workflow: dict[str, Any]) -> dict[str, list[tuple[str, dict[str, Any], dict[str, Any]]]]:
    locations = {gate: [] for gate in GATES}
    for job_name, job in workflow["jobs"].items():
        if not isinstance(job, dict):
            continue
        for step in _job_steps(job):
            command = str(step.get("run", ""))
            for gate in GATES:
                if re.search(rf"(?m)^\s*make\s+{re.escape(gate)}(?:\s|$)", command):
                    locations[gate].append((str(job_name), job, step))
    return locations


def _contains_true_continue_on_error(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (key == "continue-on-error" and child is True)
            or _contains_true_continue_on_error(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_true_continue_on_error(child) for child in value)
    return False


def test_workflow_file_is_materialized() -> None:
    assert WORKFLOW_PATH.is_file(), (
        "缺少 .github/workflows/ci.yml；这是 TDD 红灯阶段的预期失败，"
        "green 阶段必须实现 GitHub Actions workflow"
    )


def test_workflow_defines_all_eight_required_gates(workflow_path: Path) -> None:
    workflow = _load_workflow(workflow_path)
    locations = _gate_locations(workflow)
    missing = [gate for gate, matches in locations.items() if not matches]
    assert not missing, f"workflow 缺少 required gate: {missing}"


@pytest.mark.parametrize("gate", GATES)
def test_gate_failure_is_not_silently_ignored(workflow_path: Path, gate: str) -> None:
    workflow = _load_workflow(workflow_path)
    assert not _contains_true_continue_on_error(workflow), "required gate 禁止 continue-on-error: true"
    matches = _gate_locations(workflow)[gate]
    assert matches, f"未找到 make {gate}"
    for _, _, step in matches:
        command = str(step["run"])
        assert not re.search(r"\|\|\s*(?:true|:)(?:\s|$)", command), f"{gate} 禁止吞掉失败"
        if "|" in command:
            assert "pipefail" in command, f"{gate} 使用管道时必须启用 pipefail"


@pytest.mark.parametrize("gate", GATES)
def test_each_gate_uploads_auditable_artifacts_even_on_failure(
    workflow_path: Path,
    gate: str,
) -> None:
    workflow = _load_workflow(workflow_path)
    matches = _gate_locations(workflow)[gate]
    assert matches, f"未找到 make {gate}"

    for _, job, _ in matches:
        upload_steps = [
            step
            for step in _job_steps(job)
            if str(step.get("uses", "")).startswith("actions/upload-artifact@")
        ]
        assert upload_steps, f"{gate} 所在 job 未上传 artifact"
        eligible = []
        for step in upload_steps:
            condition = re.sub(r"\s+", "", str(step.get("if", ""))).lower()
            paths = str(step.get("with", {}).get("path", ""))
            if condition in {"always()", "${{always()}}"}:
                eligible.append(paths)
        assert eligible, f"{gate} artifact 上传必须使用 if: always()"
        combined_paths = "\n".join(eligible)
        for required_path in ("logs/", "results/", "junit/"):
            assert required_path in combined_paths, f"{gate} artifact 缺少 {required_path}"


def test_workflow_records_required_gate_result_fields(workflow_path: Path) -> None:
    source = workflow_path.read_text(encoding="utf-8")
    for field in ("gate", "command", "exit_code", "started_at", "finished_at"):
        assert re.search(rf"[\"']?{field}[\"']?\s*:", source), (
            f"机器可读 gate 结果缺少字段 {field}"
        )


def test_migration_gate_uses_postgresql_15_or_newer(workflow_path: Path) -> None:
    workflow = _load_workflow(workflow_path)
    matches = _gate_locations(workflow)["migration-test"]
    assert matches, "未找到 make migration-test"
    for _, job, _ in matches:
        services = job.get("services", {})
        images = [
            str(service.get("image", ""))
            for service in services.values()
            if isinstance(service, dict)
        ] if isinstance(services, dict) else []
        postgres_images = [image for image in images if re.match(r"^postgres:\d+", image)]
        assert postgres_images, "migration-test 所在 job 必须启动 PostgreSQL service"
        major = int(postgres_images[0].split(":", 1)[1].split("-", 1)[0].split(".", 1)[0])
        assert major >= 15, "PostgreSQL service 版本必须为 15+"


def test_destructive_migration_credentials_are_scoped_to_migration_step(
    workflow_path: Path,
) -> None:
    workflow = _load_workflow(workflow_path)
    protected = {"ALLOW_DESTRUCTIVE_MIGRATION_TEST", "TEST_DATABASE_URL"}
    assert not protected.intersection(workflow.get("env", {})), "迁移变量禁止设在 workflow 全局"

    migration_steps: list[dict[str, Any]] = []
    for job in workflow["jobs"].values():
        if not isinstance(job, dict):
            continue
        assert not protected.intersection(job.get("env", {})), "迁移变量禁止设在 job 全局"
        for step in _job_steps(job):
            command = str(step.get("run", ""))
            env = step.get("env", {})
            if re.search(r"(?m)^\s*make\s+migration-test(?:\s|$)", command):
                migration_steps.append(step)
                assert env.get("ALLOW_DESTRUCTIVE_MIGRATION_TEST") in {1, "1"}
                database_url = str(env.get("TEST_DATABASE_URL", ""))
                assert database_url.startswith(("postgres://", "postgresql://"))
                database_name = database_url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
                assert "test" in database_name.lower(), "CI 专用数据库名必须包含 test"
            else:
                assert not protected.intersection(env), "迁移变量只能暴露给 migration-test step"
    assert migration_steps
