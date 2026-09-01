"""ASGI entry point for profile service."""

from fastapi import FastAPI

from profile_service.routers.health import router as health_router


def create_app() -> FastAPI:
    """Create an isolated profile-service application."""
    application = FastAPI(title="Profile Service")
    application.include_router(health_router)
    return application


app = create_app()
