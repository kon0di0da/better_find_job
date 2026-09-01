"""WP-FOUNDATION-002 executable acceptance tests for profile-service."""

from __future__ import annotations

import ast
import asyncio
import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from profile_service.app import app

SERVICE_NAME = "profile_service"
SERVICE_TITLE = "Profile Service"
SERVICE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = SERVICE_ROOT / SERVICE_NAME
OTHER_SERVICES = ("knowledge_service", "interview_service")


def _imports_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_tc_struct_001_required_modules_exist() -> None:
    """TC-STRUCT-001: the service exposes the agreed package boundaries."""
    required = (
        "__init__.py",
        "app.py",
        "domain/__init__.py",
        "routers/__init__.py",
        "routers/health.py",
    )
    missing = [relative for relative in required if not (PACKAGE_ROOT / relative).is_file()]
    assert not missing, f"missing service modules: {missing}"


def test_tc_struct_001_shared_adapter_package_is_importable() -> None:
    """TC-STRUCT-001: the anti-corruption package is a valid module."""
    result = subprocess.run(
        [sys.executable, "-c", "import platform_adapters"],
        cwd=SERVICE_ROOT,
        env={**os.environ, "PYTHONPATH": str(SERVICE_ROOT.parents[1] / "packages" / "platform_adapters")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_tc_startup_001_app_is_fastapi() -> None:
    """TC-STARTUP-001: the ASGI entry point is importable."""
    assert isinstance(app, FastAPI)
    assert app.title == SERVICE_TITLE


def test_tc_startup_001_healthz() -> None:
    """TC-STARTUP-001: the ASGI app serves deterministic health state."""

    async def get_health() -> tuple[int, dict[str, str], str]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/healthz")
        return response.status_code, response.json(), response.headers["content-type"]

    status_code, body, content_type = asyncio.run(get_health())
    assert status_code == 200
    assert body == {"status": "ok", "service": SERVICE_NAME}
    assert content_type.startswith("application/json")


def test_tc_startup_001_imports_in_isolation(tmp_path: Path) -> None:
    """TC-STARTUP-001: importing this app does not require sibling services."""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SERVICE_ROOT)
    result = subprocess.run(
        [sys.executable, "-c", f"from {SERVICE_NAME}.app import app; assert app.title == {SERVICE_TITLE!r}"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_tc_arch_001_domain_does_not_import_adapters() -> None:
    """TC-ARCH-001: domain remains independent from platform adapters."""
    violations: list[str] = []
    for path in sorted((PACKAGE_ROOT / "domain").rglob("*.py")):
        for imported in _imports_in(path):
            if imported == "platform_adapters" or imported.startswith("platform_adapters."):
                violations.append(f"{path.relative_to(SERVICE_ROOT)} imports {imported}")
    assert not violations, "\n".join(violations)


def test_tc_arch_001_service_does_not_import_sibling_apps() -> None:
    """TC-ARCH-001: a service must not import another deployable app."""
    violations: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        for imported in _imports_in(path):
            if any(imported == sibling or imported.startswith(f"{sibling}.") for sibling in OTHER_SERVICES):
                violations.append(f"{path.relative_to(SERVICE_ROOT)} imports {imported}")
    assert not violations, "\n".join(violations)
