"""Deterministic, offline publisher for the WP-FOUNDATION-006 fixture."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_DATASET_VERSION = "mvp-fixture-v1"
DEFAULT_SEED = 20260901
SCHEMA_VERSION = "1.0"
_DATASET_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TOPICS = (
    "algorithms",
    "data_structures",
    "databases",
    "networks",
    "operating_systems",
    "system_design",
    "python",
    "software_engineering",
)
_TOPIC_LABELS = {
    "algorithms": "algorithm analysis",
    "data_structures": "data structure selection",
    "databases": "database consistency",
    "networks": "network reliability",
    "operating_systems": "operating system isolation",
    "system_design": "distributed system design",
    "python": "Python engineering",
    "software_engineering": "software delivery",
}
_QUESTION_TYPES = {
    "algorithms": "coding",
    "data_structures": "coding",
    "databases": "knowledge",
    "networks": "knowledge",
    "operating_systems": "knowledge",
    "system_design": "system_design",
    "python": "coding",
    "software_engineering": "project",
}
_DIFFICULTIES = ("junior", "intermediate", "senior")


class DatasetAlreadyPublishedError(RuntimeError):
    """Raised when a dataset version already exists at the publication root."""


def _stable_number(seed: int, scope: str, index: int, modulo: int) -> int:
    material = f"{seed}:{scope}:{index}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big") % modulo


def _resumes(seed: int) -> list[dict[str, Any]]:
    roles = (
        "Backend Systems Engineer",
        "Data Platform Engineer",
        "Reliability Engineer",
        "Python Service Engineer",
        "Distributed Systems Engineer",
    )
    skill_sets = (
        ["Python", "SQL", "API design", "testing"],
        ["data modeling", "Python", "databases", "observability"],
        ["networks", "operating systems", "incident analysis", "automation"],
        ["Python", "data structures", "algorithms", "software engineering"],
        ["system design", "databases", "networks", "reliability"],
    )
    records: list[dict[str, Any]] = []
    for index, (role, skills) in enumerate(zip(roles, skill_sets, strict=True), 1):
        variant = _stable_number(seed, "resume", index, 4) + 1
        first_project = index * 2 - 1
        records.append(
            {
                "resume_id": f"resume-{index:03d}",
                "candidate_id": f"candidate-{index:03d}",
                "headline": f"Synthetic {role}",
                "summary": (
                    "Synthetic candidate profile for deterministic evaluation; "
                    f"scenario variant {variant} emphasizes maintainable services."
                ),
                "skills": skills,
                "projects": [
                    {
                        "project_id": f"project-{first_project:03d}",
                        "title": f"Synthetic service project {first_project:03d}",
                        "description": (
                            "Designed a synthetic service workflow with deterministic "
                            "tests and measurable reliability goals."
                        ),
                        "skill_tags": [skills[0], skills[1]],
                    },
                    {
                        "project_id": f"project-{first_project + 1:03d}",
                        "title": f"Synthetic platform project {first_project + 1:03d}",
                        "description": (
                            "Improved a synthetic platform through explicit contracts, "
                            "reviewable changes, and offline validation."
                        ),
                        "skill_tags": [skills[2], skills[3]],
                    },
                ],
                "synthetic": True,
            }
        )
    return records


def _jds(seed: int) -> list[dict[str, Any]]:
    roles = (
        "Backend Engineer",
        "Data Infrastructure Engineer",
        "Site Reliability Engineer",
        "Python Engineer",
        "Database Engineer",
        "Network Services Engineer",
        "Systems Engineer",
        "Distributed Systems Engineer",
        "Developer Productivity Engineer",
        "Software Quality Engineer",
    )
    primary_skills = (
        "API design",
        "data structures",
        "observability",
        "Python",
        "databases",
        "networks",
        "operating systems",
        "system design",
        "software engineering",
        "testing",
    )
    records: list[dict[str, Any]] = []
    for index, (role, skill) in enumerate(zip(roles, primary_skills, strict=True), 1):
        variant = _stable_number(seed, "jd", index, 5) + 1
        records.append(
            {
                "jd_id": f"jd-{index:03d}",
                "title": f"Synthetic {role}",
                "summary": (
                    "Synthetic job scenario used only for offline fixture evaluation; "
                    f"deterministic variant {variant}."
                ),
                "skills": [
                    {"name": skill, "priority": "MUST"},
                    {"name": "Python", "priority": "PREFERRED"},
                    {"name": "technical communication", "priority": "BONUS"},
                ],
                "synthetic": True,
            }
        )
    return records


def _questions(seed: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for topic_index, topic in enumerate(_TOPICS):
        label = _TOPIC_LABELS[topic]
        for local_index in range(1, 14):
            index = topic_index * 13 + local_index
            variant = _stable_number(seed, f"question:{topic}", local_index, 7) + 1
            records.append(
                {
                    "question_id": f"question-{index:03d}",
                    "version": 1,
                    "topic": topic,
                    "question_type": _QUESTION_TYPES[topic],
                    "stem": (
                        f"In synthetic scenario {variant}, explain how you would apply "
                        f"{label} to requirement {local_index} and verify the result."
                    ),
                    "skill_tags": [topic, label],
                    "difficulty": _DIFFICULTIES[(local_index - 1) % len(_DIFFICULTIES)],
                    "rubric": [
                        "States assumptions and constraints",
                        "Explains a technically sound approach",
                        "Describes deterministic verification",
                    ],
                    "source": "synthetic-generator-v1",
                    "review_status": "APPROVED",
                    "enabled": True,
                    "synthetic": True,
                }
            )
    return records


def _gold_cases(seed: int, question_count: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index in range(1, 31):
        offset = _stable_number(seed, "gold-case", index, question_count)
        question_ids = [
            f"question-{((offset + step * 9) % question_count) + 1:03d}"
            for step in range(10)
        ]
        records.append(
            {
                "gold_case_id": f"gold-case-{index:03d}",
                "resume_id": f"resume-{((index - 1) % 5) + 1:03d}",
                "jd_id": f"jd-{((index - 1) % 10) + 1:03d}",
                "question_ids": question_ids,
                "expected_outcome": {
                    "selected_question_count": 10,
                    "minimum_jd_linked_questions": 7,
                    "project_linked_questions": 4,
                },
                "synthetic": True,
            }
        )
    return records


def _record_document(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "records": records}


def _documents(
    *, dataset_version: str, seed: int, scenario_profile: str
) -> dict[str, dict[str, Any]]:
    resumes = _resumes(seed)
    jds = _jds(seed)
    questions = _questions(seed)
    gold_cases = _gold_cases(seed, len(questions))
    payloads: dict[str, dict[str, Any]] = {
        "gold_cases.json": _record_document(gold_cases),
        "jds.json": _record_document(jds),
        "questions.json": _record_document(questions),
        "resumes.json": _record_document(resumes),
    }
    payload_paths = sorted([*payloads, "manifest.json"])
    payloads["manifest.json"] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "seed": seed,
        "scenario_profile": scenario_profile,
        "data_policy": "synthetic_non_pii_only",
        "payload_files": payload_paths,
        "record_order": {
            "resumes": [record["resume_id"] for record in resumes],
            "jds": [record["jd_id"] for record in jds],
            "questions": [record["question_id"] for record in questions],
            "gold_cases": [record["gold_case_id"] for record in gold_cases],
        },
    }
    return payloads


def _json_bytes(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode()


def _checksum_manifest(payloads: dict[str, bytes]) -> bytes:
    lines = ["algorithm: sha256", "files:"]
    for relative_path in sorted(payloads):
        digest = hashlib.sha256(payloads[relative_path]).hexdigest()
        lines.extend((f"  - path: {relative_path}", f"    sha256: {digest}"))
    return ("\n".join(lines) + "\n").encode()


def _validate_inputs(dataset_version: str, seed: int | None, scenario_profile: str) -> int:
    if not isinstance(dataset_version, str) or not _DATASET_VERSION_RE.fullmatch(dataset_version):
        raise ValueError("dataset_version must be a safe, non-empty path segment")
    if seed is None:
        resolved_seed = DEFAULT_SEED
    elif isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer or None")
    else:
        resolved_seed = seed
    if not isinstance(scenario_profile, str) or not scenario_profile.strip():
        raise ValueError("scenario_profile must be a non-empty string")
    return resolved_seed


def load_dataset(
    *,
    output_root: Path,
    dataset_version: str = DEFAULT_DATASET_VERSION,
    seed: int | None = None,
    scenario_profile: str = "default",
) -> Path:
    """Publish a deterministic fixture into an empty dataset-version path.

    Publication is local-only. An existing path is never read, changed, or replaced.
    """

    resolved_seed = _validate_inputs(dataset_version, seed, scenario_profile)
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / dataset_version
    if os.path.lexists(target):
        raise DatasetAlreadyPublishedError(f"dataset version is already published: {target}")

    documents = _documents(
        dataset_version=dataset_version,
        seed=resolved_seed,
        scenario_profile=scenario_profile,
    )
    payloads = {name: _json_bytes(document) for name, document in documents.items()}
    files = {**payloads, "checksums.yaml": _checksum_manifest(payloads)}
    staging = Path(tempfile.mkdtemp(prefix=".fixture-loader-", dir=root))
    target_reserved = False
    try:
        for relative_path in sorted(files):
            (staging / relative_path).write_bytes(files[relative_path])
        try:
            target.mkdir()
            target_reserved = True
        except FileExistsError as exc:
            raise DatasetAlreadyPublishedError(
                f"dataset version is already published: {target}"
            ) from exc
        for source in sorted(staging.iterdir()):
            source.replace(target / source.name)
    except Exception:
        if target_reserved:
            shutil.rmtree(target)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return target


__all__ = [
    "DEFAULT_DATASET_VERSION",
    "DEFAULT_SEED",
    "DatasetAlreadyPublishedError",
    "load_dataset",
]
