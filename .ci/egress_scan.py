#!/usr/bin/env python3
"""Scan repository egress for credentials and personally identifying data.

The default input is the set returned by ``git ls-files``.  Tests and other
callers may instead provide an explicit repository root and file list.  The
report intentionally contains fingerprints, never matched values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

RULE_IDS = frozenset({"secret", "private-key", "email", "phone"})
REQUIRED_EXCEPTION_FIELDS = frozenset(
    {"rule_id", "path", "value_fingerprint", "reason", "owner", "expires_at"}
)
EXCLUDED_PARTS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "artifact",
        "artifacts",
        "build",
        "coverage",
        "dist",
        "generated",
        "htmlcov",
        "junit",
        "logs",
        "node_modules",
        "results",
        "target",
    }
)
DATABASE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})
FINGERPRINT_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}"
    r"(?![A-Za-z0-9._%+-])"
)
CN_PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[ -]?)?1[3-9]\d(?:[ -]?\d){8}(?!\d)")
INTERNATIONAL_PHONE_RE = re.compile(r"(?<!\w)\+\d(?:[\d ()-]{7,}\d)")
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?P<label>(?:(?:RSA|EC|DSA|OPENSSH) )?PRIVATE KEY|"
    r"PGP PRIVATE KEY BLOCK)-----[\s\S]{20,}?-----END (?P=label)-----"
)
KNOWN_SECRET_RES = (
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"),
)
ASSIGNED_SECRET_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|api[_-]?secret|access[_-]?token|auth[_-]?token|"
    r"client[_-]?secret|private[_-]?token|password|passwd)\b\s*[:=]\s*"
    r"[\"']?([A-Za-z0-9_./+=:@-]{8,})"
)


@dataclass(frozen=True)
class Finding:
    rule_id: str
    path: str
    line: int
    value_fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "path": self.path,
            "line": self.line,
            "value_fingerprint": self.value_fingerprint,
        }


def _fingerprint(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _synthetic_email(value: str) -> bool:
    _, domain = value.lower().rsplit("@", 1)
    if domain in {"example.com", "example.net", "example.org", "localhost"}:
        return True
    return domain.endswith((".example", ".invalid", ".test"))


def _synthetic_secret(value: str) -> bool:
    lowered = value.lower()
    if re.fullmatch(
        r"(?:test|dummy|fake|synthetic|example|redacted|masked)"
        r"(?:[-_](?:token|key|secret|password|placeholder))*",
        lowered,
    ):
        return True
    if value.startswith(("${", "<")):
        return True
    return len(set(value)) <= 3


def _credible_assigned_secret(value: str) -> bool:
    if len(value) < 16 or _synthetic_secret(value):
        return False
    classes = sum(
        bool(pattern.search(value))
        for pattern in (re.compile(r"[a-z]"), re.compile(r"[A-Z]"), re.compile(r"\d"))
    )
    return classes >= 3


def _synthetic_phone(value: str) -> bool:
    normalized = value.upper().replace("-", "_")
    if re.fullmatch(r"<MOBILE_\d{1,12}>", normalized):
        return True
    digits = re.sub(r"\D", "", value)
    national = digits[2:] if digits.startswith("86") and len(digits) == 13 else digits
    return len(national) == 11 and national.startswith("1") and set(national[3:]) == {"0"}


def _iter_matches(text: str, relative_path: str) -> Iterable[Finding]:
    candidates: list[tuple[str, re.Match[str], str]] = []
    for match in PRIVATE_KEY_RE.finditer(text):
        candidates.append(("private-key", match, match.group(0)))
    for pattern in KNOWN_SECRET_RES:
        for match in pattern.finditer(text):
            candidates.append(("secret", match, match.group(0)))
    for match in ASSIGNED_SECRET_RE.finditer(text):
        value = match.group(1)
        if _credible_assigned_secret(value):
            candidates.append(("secret", match, value))
    for match in EMAIL_RE.finditer(text):
        value = match.group(0)
        if not _synthetic_email(value):
            candidates.append(("email", match, value))
    for pattern in (CN_PHONE_RE, INTERNATIONAL_PHONE_RE):
        for match in pattern.finditer(text):
            value = match.group(0)
            if not _synthetic_phone(value):
                candidates.append(("phone", match, value))

    seen: set[tuple[str, str, int]] = set()
    for rule_id, match, value in sorted(candidates, key=lambda item: item[1].start()):
        key = (rule_id, _fingerprint(value), match.start())
        if key in seen:
            continue
        seen.add(key)
        yield Finding(
            rule_id=rule_id,
            path=relative_path,
            line=_line_number(text, match.start()),
            value_fingerprint=key[1],
        )


def _is_excluded(relative_path: str) -> bool:
    path = PurePosixPath(relative_path)
    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts.intersection(EXCLUDED_PARTS):
        return True
    return path.suffix.lower() in DATABASE_SUFFIXES


def _normalize_file(root: Path, supplied: str) -> tuple[str, Path]:
    candidate = Path(supplied)
    absolute = candidate if candidate.is_absolute() else root / candidate
    resolved = absolute.resolve(strict=False)
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("file path escapes repository root") from exc
    if relative in {"", "."} or ".." in PurePosixPath(relative).parts:
        raise ValueError("file path must name a file below repository root")
    return relative, resolved


def _tracked_files(root: Path) -> tuple[list[str], list[str]]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return [], ["unable to enumerate git tracked files"]
    names = [item.decode("utf-8") for item in completed.stdout.split(b"\0") if item]
    return names, []


def _load_allowlist(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return [], ["allowlist cannot be read as YAML"]
    if not isinstance(payload, dict) or set(payload) != {"version", "exceptions"}:
        return [], ["allowlist schema requires only version and exceptions"]
    if payload["version"] != 1:
        return [], ["allowlist version must be 1"]
    raw_exceptions = payload["exceptions"]
    if not isinstance(raw_exceptions, list):
        return [], ["allowlist exceptions must be a list"]

    exceptions: list[dict[str, str]] = []
    errors: list[str] = []
    today = datetime.now(tz=UTC).date()
    identities: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(raw_exceptions):
        label = f"exception[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{label} must be a mapping")
            continue
        fields = set(raw)
        missing = REQUIRED_EXCEPTION_FIELDS - fields
        unknown = fields - REQUIRED_EXCEPTION_FIELDS
        if missing:
            errors.append(f"{label} missing fields: {', '.join(sorted(missing))}")
        if unknown:
            errors.append(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
        if missing or unknown:
            continue
        invalid_types = [
            field for field in REQUIRED_EXCEPTION_FIELDS if not isinstance(raw[field], str)
        ]
        if invalid_types:
            errors.append(
                f"{label} fields must be strings: {', '.join(sorted(invalid_types))}"
            )
            continue
        item = {field: raw[field].strip() for field in REQUIRED_EXCEPTION_FIELDS}
        if item["rule_id"] not in RULE_IDS:
            errors.append(f"{label} rule_id is invalid")
        path_value = item["path"]
        path_parts = PurePosixPath(path_value).parts
        if (
            not path_value
            or Path(path_value).is_absolute()
            or ".." in path_parts
            or any(character in path_value for character in "*?[]{}")
            or path_value.endswith("/")
        ):
            errors.append(f"{label} path must be one exact repository-relative file")
        if not FINGERPRINT_RE.fullmatch(item["value_fingerprint"]):
            errors.append(f"{label} fingerprint must be one exact sha256 value")
        if not item["reason"]:
            errors.append(f"{label} reason must not be empty")
        if not item["owner"]:
            errors.append(f"{label} owner must not be empty")
        try:
            expires_at = date.fromisoformat(item["expires_at"])
        except ValueError:
            errors.append(f"{label} expires_at must be an ISO date")
        else:
            if expires_at <= today:
                errors.append(f"{label} is expired")
        identity = (item["rule_id"], path_value, item["value_fingerprint"])
        if identity in identities:
            errors.append(f"{label} duplicates another exception")
        identities.add(identity)
        exceptions.append(item)
    return exceptions, errors


def _write_report(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--allowlist", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--file", action="append", default=[], dest="file_list")
    parser.add_argument("--files", nargs="*", default=[])
    return parser


def scan(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.repo_root.resolve()
    report_path = args.report.resolve() if args.report else None
    allowlist_path = (
        args.allowlist.resolve()
        if args.allowlist
        else root / ".ci" / "egress-allowlist.yaml"
    )
    exceptions, allowlist_errors = _load_allowlist(allowlist_path)
    supplied_files = [*args.file_list, *args.files]
    file_names: list[str]
    scan_errors: list[str] = []
    if supplied_files:
        file_names = supplied_files
    else:
        file_names, scan_errors = _tracked_files(root)

    scanned_files: list[str] = []
    findings: list[Finding] = []
    normalized_seen: set[str] = set()
    for supplied in file_names:
        try:
            relative, path = _normalize_file(root, supplied)
        except ValueError:
            scan_errors.append("an input file is outside the repository root")
            continue
        if relative in normalized_seen or _is_excluded(relative):
            continue
        normalized_seen.add(relative)
        if not path.is_file() or path.is_symlink():
            scan_errors.append(f"cannot scan regular file: {relative}")
            continue
        try:
            raw = path.read_bytes()
            if b"\0" in raw:
                continue
            text = raw.decode("utf-8")
        except (OSError, UnicodeError):
            scan_errors.append(f"cannot decode tracked file: {relative}")
            continue
        scanned_files.append(relative)
        findings.extend(_iter_matches(text, relative))

    exception_index = {
        (item["rule_id"], item["path"], item["value_fingerprint"]): item
        for item in exceptions
    }
    matched: set[tuple[str, str, str]] = set()
    outstanding: list[Finding] = []
    allowlisted: list[dict[str, Any]] = []
    for finding in findings:
        identity = (finding.rule_id, finding.path, finding.value_fingerprint)
        if identity in exception_index:
            matched.add(identity)
            allowlisted.append(finding.as_dict())
        else:
            outstanding.append(finding)
    for identity in sorted(set(exception_index) - matched):
        rule_id, path, _ = identity
        allowlist_errors.append(f"unused allowlist exception for {rule_id} at {path}")

    if not scanned_files:
        scan_errors.append("no eligible files were scanned")
    failed = bool(outstanding or allowlist_errors or scan_errors)
    payload = {
        "status": "fail" if failed else "pass",
        "scanned_files": sorted(scanned_files),
        "findings": [item.as_dict() for item in outstanding],
        "allowlisted": allowlisted,
        "allowlist_errors": allowlist_errors,
        "scan_errors": scan_errors,
    }
    try:
        _write_report(report_path, payload)
    except OSError:
        print("egress-scan: FAIL (machine report could not be written)", file=sys.stderr)
        return 2
    print(
        "egress-scan: "
        f"{'FAIL' if failed else 'PASS'} "
        f"({len(scanned_files)} files, {len(outstanding)} findings, "
        f"{len(allowlist_errors) + len(scan_errors)} errors)"
    )
    return 1 if failed else 0


def main() -> None:
    raise SystemExit(scan())


if __name__ == "__main__":
    main()
