"""ASGI entry point for knowledge service."""

from fastapi import FastAPI

from knowledge_service.routers.health import router as health_router


def create_app() -> FastAPI:
    """Create an isolated knowledge-service application."""
    application = FastAPI(title="Knowledge Service")
    application.include_router(health_router)
    return application


app = create_app()
