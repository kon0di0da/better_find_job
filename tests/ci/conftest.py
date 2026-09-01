"""Shared fixtures for the WP-FOUNDATION-007 CI acceptance suite."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCANNER_PATH = REPOSITORY_ROOT / ".ci" / "egress_scan.py"
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture
def scanner_path() -> Path:
    """Skip dependent contract checks until the scanner reaches the green phase."""
    if not SCANNER_PATH.is_file():
        pytest.skip("缺少 .ci/egress_scan.py；扫描器契约测试等待 green 阶段实现")
    return SCANNER_PATH


@pytest.fixture
def workflow_path() -> Path:
    """Skip dependent contract checks until the workflow reaches the green phase."""
    if not WORKFLOW_PATH.is_file():
        pytest.skip("缺少 .github/workflows/ci.yml；workflow 契约测试等待 green 阶段实现")
    return WORKFLOW_PATH


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repository"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    return repo


def write_allowlist(path: Path, exceptions: list[dict[str, str]] | None = None) -> None:
    """Write the deliberately small YAML subset accepted by the scanner contract."""
    lines = ["version: 1", "exceptions:"]
    if not exceptions:
        lines.append("  []")
    else:
        for exception in exceptions:
            lines.append("  - rule_id: " + exception.get("rule_id", ""))
            for field in ("path", "value_fingerprint", "reason", "owner", "expires_at"):
                if field in exception:
                    value = exception[field].replace("'", "''")
                    lines.append(f"    {field}: '{value}'")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def track(repo: Path, relative_path: str, content: str) -> Path:
    target = repo / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "--force", "--", relative_path],
        check=True,
        capture_output=True,
        text=True,
    )
    return target


def fingerprint(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def run_scanner(
    scanner_path: Path,
    repo: Path,
    allowlist: Path,
) -> tuple[subprocess.CompletedProcess[str], Path, dict[str, Any] | None]:
    """Exercise the public scanner CLI contract and decode its machine report."""
    report = repo.parent / "egress-report.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(scanner_path),
            "--repo-root",
            str(repo),
            "--allowlist",
            str(allowlist),
            "--report",
            str(report),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else None
    return completed, report, payload


def assert_report_shape(payload: dict[str, Any] | None) -> dict[str, Any]:
    assert payload is not None, "scanner 必须在成功和失败时都写入 JSON 报告"
    assert payload.get("status") in {"pass", "fail"}
    assert isinstance(payload.get("scanned_files"), list)
    assert isinstance(payload.get("findings"), list)
    assert isinstance(payload.get("allowlisted"), list)
    assert isinstance(payload.get("allowlist_errors"), list)
    return payload
