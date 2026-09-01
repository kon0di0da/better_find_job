"""ASGI entry point for interview service."""

from fastapi import FastAPI

from interview_service.routers.health import router as health_router


def create_app() -> FastAPI:
    """Create an isolated interview-service application."""
    application = FastAPI(title="Interview Service")
    application.include_router(health_router)
    return application


app = create_app()
