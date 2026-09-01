"""CLI acceptance contract for the WP-FOUNDATION-007 egress scanner."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from conftest import (
    SCANNER_PATH,
    assert_report_shape,
    fingerprint,
    run_scanner,
    track,
    write_allowlist,
)

RULE_IDS = {"secret", "private-key", "email", "phone"}


def _today() -> date:
    return datetime.now(tz=UTC).date()


def _empty_allowlist(repo: Path) -> Path:
    allowlist = repo / "allowlist.yaml"
    write_allowlist(allowlist)
    return allowlist


def _finding_rules(payload: dict[str, object]) -> set[str]:
    findings = payload["findings"]
    assert isinstance(findings, list)
    return {
        str(finding["rule_id"])
        for finding in findings
        if isinstance(finding, dict) and "rule_id" in finding
    }


def _realistic_sensitive_samples() -> dict[str, str]:
    # Assemble at runtime so this tracked acceptance file never embeds the samples it bans.
    token = "github" + "_pat_" + "11AA22bb33CC44dd55EE66ff77GG88hh99II00jj"
    private_key = "-----BEGIN " + "PRIVATE KEY-----\n" + ("Q" * 72) + "\n-----END PRIVATE KEY-----\n"
    email = "candidate" + "@" + "gmail.com"
    phone = "+86 " + "138" + " 1234 " + "5678"
    return {
        "secret": f"ACCESS_TOKEN={token}\n",
        "private-key": private_key,
        "email": f"contact: {email}\n",
        "phone": f"mobile: {phone}\n",
    }


def test_scanner_file_is_materialized() -> None:
    assert SCANNER_PATH.is_file(), (
        "缺少 .ci/egress_scan.py；这是 TDD 红灯阶段的预期失败，"
        "green 阶段必须实现出口扫描器"
    )


@pytest.mark.parametrize("expected_rule", sorted(RULE_IDS))
def test_cli_rejects_each_sensitive_data_class(
    scanner_path: Path,
    git_repo: Path,
    expected_rule: str,
) -> None:
    track(git_repo, "src/sample.txt", _realistic_sensitive_samples()[expected_rule])
    completed, _, payload = run_scanner(scanner_path, git_repo, _empty_allowlist(git_repo))

    report = assert_report_shape(payload)
    assert completed.returncode != 0
    assert report["status"] == "fail"
    assert expected_rule in _finding_rules(report)


def test_cli_rejects_assignment_style_high_entropy_secret(
    scanner_path: Path,
    git_repo: Path,
) -> None:
    value = "A7b9" * 12
    track(git_repo, "config/settings.env", f"api_secret = {value}\n")
    completed, _, payload = run_scanner(scanner_path, git_repo, _empty_allowlist(git_repo))

    report = assert_report_shape(payload)
    assert completed.returncode != 0
    assert "secret" in _finding_rules(report)
    serialized_report = str(report)
    assert value not in serialized_report
    assert value not in completed.stdout
    assert value not in completed.stderr
    finding = next(item for item in report["findings"] if item["rule_id"] == "secret")
    assert finding["value_fingerprint"] == fingerprint(value)


def test_cli_fails_closed_when_no_eligible_tracked_file_exists(
    scanner_path: Path,
    git_repo: Path,
) -> None:
    track(git_repo, "artifacts/results/generated.json", "{}\n")
    completed, _, payload = run_scanner(scanner_path, git_repo, _empty_allowlist(git_repo))

    report = assert_report_shape(payload)
    assert completed.returncode != 0
    assert report["status"] == "fail"
    assert report["scanned_files"] == []


def test_cli_accepts_ordinary_source_and_explicit_synthetic_placeholders(
    scanner_path: Path,
    git_repo: Path,
) -> None:
    content = """def add(left: int, right: int) -> int:
    return left + right
synthetic_email = 'user@example.com'  # synthetic-test-data
synthetic_phone = '+86 138 0000 0000'  # synthetic-test-data
synthetic_token = 'test-token-placeholder'  # synthetic-test-data
"""
    track(git_repo, "src/example.py", content)
    completed, _, payload = run_scanner(scanner_path, git_repo, _empty_allowlist(git_repo))

    report = assert_report_shape(payload)
    assert completed.returncode == 0, completed.stderr
    assert report["status"] == "pass"
    assert report["findings"] == []


def test_synthetic_marker_does_not_hide_another_sensitive_value_on_same_line(
    scanner_path: Path,
    git_repo: Path,
) -> None:
    real_email = "private.person" + "@" + "real-company.cn"
    track(
        git_repo,
        "tests/data.py",
        f"placeholder='user@example.com'  # synthetic-test-data; owner={real_email}\n",
    )
    completed, _, payload = run_scanner(scanner_path, git_repo, _empty_allowlist(git_repo))

    report = assert_report_shape(payload)
    assert completed.returncode != 0
    assert "email" in _finding_rules(report)


def test_cli_scans_only_tracked_source_files_and_excludes_generated_git_and_databases(
    scanner_path: Path,
    git_repo: Path,
) -> None:
    samples = _realistic_sensitive_samples()
    tracked_source = track(git_repo, "src/clean.py", "ANSWER = 42\n")
    untracked = git_repo / "notes.txt"
    untracked.write_text(samples["email"], encoding="utf-8")
    track(git_repo, "artifacts/logs/generated.log", samples["secret"])
    track(git_repo, "var/test.sqlite3", samples["phone"])
    git_internal = git_repo / ".git" / "scanner-probe"
    git_internal.write_text(samples["private-key"], encoding="utf-8")

    completed, report_path, payload = run_scanner(
        scanner_path,
        git_repo,
        _empty_allowlist(git_repo),
    )
    report = assert_report_shape(payload)

    assert completed.returncode == 0, completed.stderr
    assert report["status"] == "pass"
    assert report["findings"] == []
    assert report_path.is_file()
    scanned = set(report["scanned_files"])
    assert tracked_source.relative_to(git_repo).as_posix() in scanned
    assert "notes.txt" not in scanned
    assert not any(path.startswith(".git/") for path in scanned)
    assert not any(path.startswith("artifacts/") for path in scanned)
    assert not any(path.endswith((".db", ".sqlite", ".sqlite3")) for path in scanned)


def test_valid_exact_unexpired_allowlist_suppresses_only_matching_finding(
    scanner_path: Path,
    git_repo: Path,
) -> None:
    value = "candidate" + "@" + "gmail.com"
    track(git_repo, "docs/contact.txt", f"Contact: {value}\n")
    allowlist = git_repo / "allowlist.yaml"
    write_allowlist(
        allowlist,
        [
            {
                "rule_id": "email",
                "path": "docs/contact.txt",
                "value_fingerprint": fingerprint(value),
                "reason": "Legacy fixture pending synthetic replacement",
                "owner": "security-team",
                "expires_at": (_today() + timedelta(days=30)).isoformat(),
            }
        ],
    )

    completed, _, payload = run_scanner(scanner_path, git_repo, allowlist)
    report = assert_report_shape(payload)
    assert completed.returncode == 0, completed.stderr
    assert report["status"] == "pass"
    assert report["findings"] == []
    assert len(report["allowlisted"]) == 1
    allowed = report["allowlisted"][0]
    assert allowed["rule_id"] == "email"
    assert allowed["path"] == "docs/contact.txt"
    assert allowed["value_fingerprint"] == fingerprint(value)


@pytest.mark.parametrize(
    ("mutation", "error_hint"),
    (
        ({"expires_at": (_today() - timedelta(days=1)).isoformat()}, "expir"),
        ({"path": "**/*"}, "path"),
        ({"value_fingerprint": "*"}, "fingerprint"),
        ({"owner": ""}, "owner"),
    ),
)
def test_invalid_expired_or_overbroad_allowlist_fails_closed(
    scanner_path: Path,
    git_repo: Path,
    mutation: dict[str, str],
    error_hint: str,
) -> None:
    value = "candidate" + "@" + "gmail.com"
    track(git_repo, "docs/contact.txt", f"Contact: {value}\n")
    exception = {
        "rule_id": "email",
        "path": "docs/contact.txt",
        "value_fingerprint": fingerprint(value),
        "reason": "Legacy fixture pending synthetic replacement",
        "owner": "security-team",
        "expires_at": (_today() + timedelta(days=30)).isoformat(),
    }
    exception.update(mutation)
    allowlist = git_repo / "allowlist.yaml"
    write_allowlist(allowlist, [exception])

    completed, _, payload = run_scanner(scanner_path, git_repo, allowlist)
    report = assert_report_shape(payload)
    assert completed.returncode != 0
    assert report["status"] == "fail"
    errors = " ".join(str(error) for error in report["allowlist_errors"]).lower()
    assert error_hint in errors


@pytest.mark.parametrize(
    "missing_field",
    ("rule_id", "path", "value_fingerprint", "reason", "owner", "expires_at"),
)
def test_allowlist_missing_required_field_fails_closed(
    scanner_path: Path,
    git_repo: Path,
    missing_field: str,
) -> None:
    value = "candidate" + "@" + "gmail.com"
    track(git_repo, "docs/contact.txt", f"Contact: {value}\n")
    exception = {
        "rule_id": "email",
        "path": "docs/contact.txt",
        "value_fingerprint": fingerprint(value),
        "reason": "Legacy fixture pending synthetic replacement",
        "owner": "security-team",
        "expires_at": (_today() + timedelta(days=30)).isoformat(),
    }
    del exception[missing_field]
    allowlist = git_repo / "allowlist.yaml"
    write_allowlist(allowlist, [exception])

    completed, _, payload = run_scanner(scanner_path, git_repo, allowlist)
    report = assert_report_shape(payload)
    assert completed.returncode != 0
    assert report["status"] == "fail"
    errors = " ".join(str(error) for error in report["allowlist_errors"])
    assert missing_field in errors


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    (
        ("rule_id", "phone"),
        ("path", "docs/other.txt"),
        ("value_fingerprint", "sha256:" + ("0" * 64)),
    ),
)
def test_allowlist_must_match_rule_path_and_fingerprint_exactly(
    scanner_path: Path,
    git_repo: Path,
    field: str,
    wrong_value: str,
) -> None:
    value = "candidate" + "@" + "gmail.com"
    track(git_repo, "docs/contact.txt", f"Contact: {value}\n")
    exception = {
        "rule_id": "email",
        "path": "docs/contact.txt",
        "value_fingerprint": fingerprint(value),
        "reason": "Intentional mismatch used by acceptance test",
        "owner": "security-team",
        "expires_at": (_today() + timedelta(days=30)).isoformat(),
    }
    exception[field] = wrong_value
    allowlist = git_repo / "allowlist.yaml"
    write_allowlist(allowlist, [exception])

    completed, _, payload = run_scanner(scanner_path, git_repo, allowlist)
    report = assert_report_shape(payload)
    assert completed.returncode != 0
    assert report["status"] == "fail"
    assert "email" in _finding_rules(report)
    assert report["allowlist_errors"], "未命中的 allowlist 条目必须失败"
