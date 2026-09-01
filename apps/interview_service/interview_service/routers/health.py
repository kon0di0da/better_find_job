"""Operational health endpoint for interview service."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    """Report that the process is ready to receive traffic."""
    return {"status": "ok", "service": "interview_service"}
