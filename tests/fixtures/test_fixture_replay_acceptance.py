"""REQ-FIXTURE-001 / TC-FIXTURE-001 / TC-AI-GOLD-001 acceptance tests.

This module intentionally defines the executable fixture contract before the
WP-FOUNDATION-006 implementation exists.  The production API is:

    tools.fixture_loader.load_dataset(
        *, output_root: pathlib.Path,
        dataset_version: str = "mvp-fixture-v1",
        seed: int | None = None,
        scenario_profile: str = "default",
    ) -> pathlib.Path

The returned path must be ``output_root / dataset_version``.  Publishing to an
existing dataset path must raise ``DatasetAlreadyPublishedError`` without
changing any byte.  A missing/None seed means 20260901.

The published dataset consists of four JSON record payloads, ``manifest.json``
and ``checksums.yaml``.  JSON uses UTF-8 and each record payload has the shape
``{"schema_version": "1.0", "records": [...]}``.  ``checksums.yaml`` is not a
payload (which avoids a self-checksum); it covers every JSON payload, including
the manifest, in ascending relative-path order.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import socket
import urllib.request
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DATASET_VERSION = "mvp-fixture-v1"
DEFAULT_SEED = 20260901
SOURCE_DATASET = ROOT / "fixtures" / DATASET_VERSION
PAYLOAD_PATHS = [
    "gold_cases.json",
    "jds.json",
    "manifest.json",
    "questions.json",
    "resumes.json",
]
RECORD_FILES = {
    "resumes": "resumes.json",
    "jds": "jds.json",
    "questions": "questions.json",
    "gold_cases": "gold_cases.json",
}
TECHNICAL_TOPICS = {
    "algorithms",
    "data_structures",
    "databases",
    "networks",
    "operating_systems",
    "system_design",
    "python",
    "software_engineering",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
INTERNATIONAL_PHONE_RE = re.compile(r"(?<!\w)\+\d(?:[\d ()-]{7,}\d)")
CREDENTIAL_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b\s*[:=]"),
    re.compile(r"\b(?:ghp|glpat|xox[baprs])[-_A-Za-z0-9]{10,}\b"),
)
FORBIDDEN_PERSONAL_FIELDS = {
    "email",
    "phone",
    "mobile",
    "address",
    "birth_date",
    "date_of_birth",
    "government_id",
    "id_card",
    "real_name",
}


def _require_source_dataset() -> Path:
    assert SOURCE_DATASET.is_dir(), (
        "WP-FOUNDATION-006 implementation missing: expected published fixture "
        f"directory {SOURCE_DATASET.relative_to(ROOT)}"
    )
    return SOURCE_DATASET


def _loader_module() -> ModuleType:
    package = ROOT / "tools" / "fixture_loader" / "__init__.py"
    assert package.is_file(), (
        "WP-FOUNDATION-006 implementation missing: expected loader package "
        "tools/fixture_loader/__init__.py"
    )
    module = importlib.import_module("tools.fixture_loader")
    assert callable(getattr(module, "load_dataset", None)), (
        "fixture loader contract violation: load_dataset must be callable"
    )
    error_type = getattr(module, "DatasetAlreadyPublishedError", None)
    assert isinstance(error_type, type) and issubclass(error_type, Exception), (
        "fixture loader contract violation: DatasetAlreadyPublishedError is required"
    )
    return module


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        pytest.fail(f"invalid UTF-8 JSON payload {path}: {exc}")
    assert isinstance(value, dict), f"{path.name} must contain a JSON object"
    return value


def _records(dataset: Path, name: str) -> list[dict[str, Any]]:
    document = _json(dataset / RECORD_FILES[name])
    assert set(document) == {"schema_version", "records"}
    assert document["schema_version"] == "1.0"
    assert isinstance(document["records"], list)
    assert all(isinstance(record, dict) for record in document["records"])
    return document["records"]


def _assert_exact_keys(record: dict[str, Any], keys: set[str], label: str) -> None:
    assert set(record) == keys, (
        f"{label} keys differ: missing={sorted(keys - set(record))}, "
        f"extra={sorted(set(record) - keys)}"
    )


def _assert_nonempty_string(value: Any, label: str) -> None:
    assert isinstance(value, str) and value.strip(), f"{label} must be a non-empty string"


def _assert_string_list(value: Any, label: str, *, minimum: int = 1) -> None:
    assert isinstance(value, list) and len(value) >= minimum, f"{label} must be a non-empty list"
    assert all(isinstance(item, str) and item.strip() for item in value), (
        f"{label} must contain non-empty strings"
    )


def _expected_ids(prefix: str, count: int) -> list[str]:
    return [f"{prefix}-{index:03d}" for index in range(1, count + 1)]


def _record_ids(records: list[dict[str, Any]], id_field: str) -> list[str]:
    ids = [record.get(id_field) for record in records]
    assert all(isinstance(value, str) for value in ids)
    return ids


def _validate_resumes(records: list[dict[str, Any]]) -> None:
    assert len(records) == 5
    assert _record_ids(records, "resume_id") == _expected_ids("resume", 5)
    for index, record in enumerate(records, 1):
        label = f"resume #{index}"
        _assert_exact_keys(
            record,
            {"resume_id", "candidate_id", "headline", "summary", "skills", "projects", "synthetic"},
            label,
        )
        assert record["candidate_id"] == f"candidate-{index:03d}"
        assert record["synthetic"] is True
        _assert_nonempty_string(record["headline"], f"{label}.headline")
        _assert_nonempty_string(record["summary"], f"{label}.summary")
        _assert_string_list(record["skills"], f"{label}.skills")
        assert isinstance(record["projects"], list) and record["projects"]
        for project in record["projects"]:
            _assert_exact_keys(project, {"project_id", "title", "description", "skill_tags"}, "project")
            _assert_nonempty_string(project["project_id"], "project.project_id")
            _assert_nonempty_string(project["title"], "project.title")
            _assert_nonempty_string(project["description"], "project.description")
            _assert_string_list(project["skill_tags"], "project.skill_tags")


def _validate_jds(records: list[dict[str, Any]]) -> None:
    assert len(records) == 10
    assert _record_ids(records, "jd_id") == _expected_ids("jd", 10)
    for index, record in enumerate(records, 1):
        label = f"jd #{index}"
        _assert_exact_keys(record, {"jd_id", "title", "summary", "skills", "synthetic"}, label)
        assert record["synthetic"] is True
        _assert_nonempty_string(record["title"], f"{label}.title")
        _assert_nonempty_string(record["summary"], f"{label}.summary")
        assert isinstance(record["skills"], list) and record["skills"]
        for skill in record["skills"]:
            _assert_exact_keys(skill, {"name", "priority"}, "jd skill")
            _assert_nonempty_string(skill["name"], "jd skill.name")
            assert skill["priority"] in {"MUST", "PREFERRED", "BONUS"}


def _validate_questions(records: list[dict[str, Any]]) -> None:
    assert len(records) >= 100
    assert _record_ids(records, "question_id") == _expected_ids("question", len(records))
    for index, record in enumerate(records, 1):
        label = f"question #{index}"
        _assert_exact_keys(
            record,
            {
                "question_id",
                "version",
                "topic",
                "question_type",
                "stem",
                "skill_tags",
                "difficulty",
                "rubric",
                "source",
                "review_status",
                "enabled",
                "synthetic",
            },
            label,
        )
        assert record["version"] == 1
        assert record["topic"] in TECHNICAL_TOPICS
        assert record["question_type"] in {"knowledge", "coding", "project", "system_design"}
        assert record["difficulty"] in {"junior", "intermediate", "senior"}
        assert record["review_status"] == "APPROVED"
        assert record["enabled"] is True
        assert record["synthetic"] is True
        _assert_nonempty_string(record["stem"], f"{label}.stem")
        _assert_string_list(record["skill_tags"], f"{label}.skill_tags")
        _assert_string_list(record["rubric"], f"{label}.rubric")
        _assert_nonempty_string(record["source"], f"{label}.source")


def _validate_gold_cases(records: list[dict[str, Any]]) -> None:
    assert len(records) == 30
    assert _record_ids(records, "gold_case_id") == _expected_ids("gold-case", 30)
    for index, record in enumerate(records, 1):
        label = f"gold case #{index}"
        _assert_exact_keys(
            record,
            {"gold_case_id", "resume_id", "jd_id", "question_ids", "expected_outcome", "synthetic"},
            label,
        )
        assert record["synthetic"] is True
        assert isinstance(record["question_ids"], list) and len(record["question_ids"]) == 10
        assert len(set(record["question_ids"])) == 10
        _assert_exact_keys(
            record["expected_outcome"],
            {"selected_question_count", "minimum_jd_linked_questions", "project_linked_questions"},
            f"{label}.expected_outcome",
        )
        assert record["expected_outcome"] == {
            "selected_question_count": 10,
            "minimum_jd_linked_questions": 7,
            "project_linked_questions": 4,
        }


def _validated_dataset(dataset: Path) -> dict[str, list[dict[str, Any]]]:
    expected_files = set(PAYLOAD_PATHS) | {"checksums.yaml"}
    actual_files = {
        path.relative_to(dataset).as_posix()
        for path in dataset.rglob("*")
        if path.is_file()
    }
    assert actual_files == expected_files

    result = {name: _records(dataset, name) for name in RECORD_FILES}
    _validate_resumes(result["resumes"])
    _validate_jds(result["jds"])
    _validate_questions(result["questions"])
    _validate_gold_cases(result["gold_cases"])
    return result


def _manifest(dataset: Path) -> dict[str, Any]:
    manifest = _json(dataset / "manifest.json")
    _assert_exact_keys(
        manifest,
        {
            "schema_version",
            "dataset_version",
            "seed",
            "scenario_profile",
            "data_policy",
            "payload_files",
            "record_order",
        },
        "manifest",
    )
    assert manifest["schema_version"] == "1.0"
    assert manifest["dataset_version"] == DATASET_VERSION
    assert manifest["seed"] == DEFAULT_SEED
    assert manifest["scenario_profile"] == "default"
    assert manifest["data_policy"] == "synthetic_non_pii_only"
    assert manifest["payload_files"] == PAYLOAD_PATHS
    assert set(manifest["record_order"]) == set(RECORD_FILES)
    return manifest


def _checksums(dataset: Path) -> list[dict[str, str]]:
    document = yaml.safe_load((dataset / "checksums.yaml").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    assert set(document) == {"algorithm", "files"}
    assert document["algorithm"] == "sha256"
    assert isinstance(document["files"], list)
    entries = document["files"]
    assert all(isinstance(entry, dict) and set(entry) == {"path", "sha256"} for entry in entries)
    return entries


def _snapshot(dataset: Path) -> dict[str, bytes]:
    return {
        path.relative_to(dataset).as_posix(): path.read_bytes()
        for path in sorted(dataset.rglob("*"))
        if path.is_file()
    }


def _sha_snapshot(dataset: Path) -> dict[str, str]:
    return {relative: hashlib.sha256(content).hexdigest() for relative, content in _snapshot(dataset).items()}


def _walk_json(value: Any, location: str = "$") -> list[tuple[str, Any]]:
    nodes = [(location, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            nodes.extend(_walk_json(child, f"{location}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            nodes.extend(_walk_json(child, f"{location}[{index}]"))
    return nodes


def _deny_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    attempts: list[str] = []

    def blocked(*args: object, **kwargs: object) -> None:
        target = repr(args[0]) if args else "unknown"
        attempts.append(target)
        raise AssertionError(f"external network access is forbidden: {target}")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    return attempts


def _load(
    loader: ModuleType,
    output_root: Path,
    **kwargs: object,
) -> Path:
    load_dataset: Callable[..., object] = loader.load_dataset
    result = load_dataset(output_root=output_root, **kwargs)
    assert isinstance(result, Path), "load_dataset must return pathlib.Path"
    assert result == output_root / str(kwargs.get("dataset_version", DATASET_VERSION))
    assert result.is_dir()
    return result


def test_fixture_loader_exposes_the_publishing_contract() -> None:
    """TC-FIXTURE-001: resolve the loader at test time, not collection time."""
    _loader_module()


def test_fixture_json_contract_sizes_topics_ids_and_references() -> None:
    """TC-FIXTURE-001: validate schema, cardinality, stable IDs and references."""
    dataset = _require_source_dataset()
    records = _validated_dataset(dataset)
    manifest = _manifest(dataset)

    actual_order = {
        "resumes": _record_ids(records["resumes"], "resume_id"),
        "jds": _record_ids(records["jds"], "jd_id"),
        "questions": _record_ids(records["questions"], "question_id"),
        "gold_cases": _record_ids(records["gold_cases"], "gold_case_id"),
    }
    assert manifest["record_order"] == actual_order

    all_ids = [item for ids in actual_order.values() for item in ids]
    project_ids = [
        project["project_id"]
        for resume in records["resumes"]
        for project in resume["projects"]
    ]
    assert project_ids == _expected_ids("project", len(project_ids))
    assert len(all_ids) == len(set(all_ids)), "record IDs must be globally unique"
    assert len(project_ids) == len(set(project_ids)), "project IDs must be globally unique"
    assert not set(project_ids).intersection(all_ids)

    assert {question["topic"] for question in records["questions"]} == TECHNICAL_TOPICS
    resume_ids = set(actual_order["resumes"])
    jd_ids = set(actual_order["jds"])
    question_ids = set(actual_order["questions"])
    for gold_case in records["gold_cases"]:
        assert gold_case["resume_id"] in resume_ids
        assert gold_case["jd_id"] in jd_ids
        assert set(gold_case["question_ids"]).issubset(question_ids)


def test_fixture_contains_only_synthetic_non_pii_data_and_no_credentials() -> None:
    """Security acceptance: reject PII-shaped fields/content and credentials."""
    dataset = _require_source_dataset()
    _validated_dataset(dataset)
    _manifest(dataset)

    for relative in PAYLOAD_PATHS:
        document = _json(dataset / relative)
        serialized = json.dumps(document, ensure_ascii=False, sort_keys=True)
        assert EMAIL_RE.search(serialized) is None, f"email-like PII found in {relative}"
        assert PHONE_RE.search(serialized) is None, f"phone-like PII found in {relative}"
        assert INTERNATIONAL_PHONE_RE.search(serialized) is None, (
            f"international phone-like PII found in {relative}"
        )
        for pattern in CREDENTIAL_PATTERNS:
            assert pattern.search(serialized) is None, f"credential-like content found in {relative}"
        for location, value in _walk_json(document):
            if isinstance(value, dict):
                forbidden = FORBIDDEN_PERSONAL_FIELDS.intersection(key.lower() for key in value)
                assert not forbidden, f"PII fields {sorted(forbidden)} found at {relative}:{location}"


def test_checksum_manifest_covers_every_payload_in_relative_path_order() -> None:
    """TC-FIXTURE-001/TC-AI-GOLD-001: exact sorted SHA-256 coverage."""
    dataset = _require_source_dataset()
    _validated_dataset(dataset)
    entries = _checksums(dataset)
    paths = [entry["path"] for entry in entries]

    discovered_payloads = sorted(
        path.relative_to(dataset).as_posix()
        for path in dataset.rglob("*.json")
        if path.is_file()
    )
    assert paths == discovered_payloads == PAYLOAD_PATHS
    for entry in entries:
        assert SHA256_RE.fullmatch(entry["sha256"])
        actual = hashlib.sha256((dataset / entry["path"]).read_bytes()).hexdigest()
        assert entry["sha256"] == actual
    assert "gold_cases.json" in paths


def test_two_offline_cold_starts_are_byte_identical_with_default_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-FIXTURE-001: independent empty destinations replay byte-for-byte."""
    source = _require_source_dataset()
    attempts = _deny_network(monkeypatch)
    loader = _loader_module()
    first_root = tmp_path / "cold-start-a"
    second_root = tmp_path / "cold-start-b"
    assert not first_root.exists() and not second_root.exists()

    first = _load(loader, first_root)
    second = _load(loader, second_root)

    first_records = _validated_dataset(first)
    second_records = _validated_dataset(second)
    assert _manifest(first)["seed"] == _manifest(second)["seed"] == DEFAULT_SEED
    assert _snapshot(first) == _snapshot(second) == _snapshot(source)
    assert _checksums(first) == _checksums(second)
    for name, id_field in (
        ("resumes", "resume_id"),
        ("jds", "jd_id"),
        ("questions", "question_id"),
        ("gold_cases", "gold_case_id"),
    ):
        assert _record_ids(first_records[name], id_field) == _record_ids(second_records[name], id_field)
    assert attempts == []


def test_published_dataset_version_cannot_be_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-FIXTURE-001: failed duplicate publish preserves every checksum/byte."""
    _require_source_dataset()
    attempts = _deny_network(monkeypatch)
    loader = _loader_module()
    output_root = tmp_path / "published"
    published = _load(loader, output_root)
    before_bytes = _snapshot(published)
    before_hashes = _sha_snapshot(published)
    before_manifest = (published / "checksums.yaml").read_bytes()

    with pytest.raises(loader.DatasetAlreadyPublishedError):
        _load(loader, output_root, seed=DEFAULT_SEED + 1)

    assert _snapshot(published) == before_bytes
    assert _sha_snapshot(published) == before_hashes
    assert (published / "checksums.yaml").read_bytes() == before_manifest
    assert attempts == []
