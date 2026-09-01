#!/usr/bin/env python3
"""Run one CI gate and persist an auditable log, JSON result, and JUnit file."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree


def _timestamp() -> str:
    return datetime.now(tz=UTC).isoformat()


def _write_junit(path: Path, gate: str, exit_code: int) -> None:
    suite = ElementTree.Element(
        "testsuite",
        name=gate,
        tests="1",
        failures="1" if exit_code else "0",
    )
    case = ElementTree.SubElement(suite, "testcase", classname="ci.gate", name=gate)
    if exit_code:
        failure = ElementTree.SubElement(
            case,
            "failure",
            message=f"gate exited with status {exit_code}",
        )
        failure.text = "See the corresponding gate log."
    ElementTree.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", required=True)
    parser.add_argument("--report-root", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required after --")

    root = args.report_root.resolve()
    logs = root / "logs"
    results = root / "results"
    junit = root / "junit"
    for directory in (logs, results, junit):
        directory.mkdir(parents=True, exist_ok=True)

    started_at = _timestamp()
    log_path = logs / f"{args.gate}.log"
    try:
        with log_path.open("w", encoding="utf-8") as stream:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
            )
            assert process.stdout is not None
            for line in process.stdout:
                stream.write(line)
                stream.flush()
                sys.stdout.write(line)
                sys.stdout.flush()
            exit_code = process.wait()
    except OSError as exc:
        exit_code = 127
        message = f"unable to execute gate command: {type(exc).__name__}\n"
        log_path.write_text(message, encoding="utf-8")
        sys.stderr.write(message)
    finished_at = _timestamp()

    result = {
        "gate": args.gate,
        "command": command,
        "exit_code": exit_code,
        "started_at": started_at,
        "finished_at": finished_at,
    }
    (results / f"{args.gate}.json").write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_junit(junit / f"{args.gate}.xml", args.gate, exit_code)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
