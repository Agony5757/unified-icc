"""Route registration for the unified-icc server."""

from fastapi import FastAPI

from .sessions import router as sessions_router


def register_routes(app: FastAPI) -> None:
    """Register all API routers on the FastAPI app."""
    app.include_router(sessions_router)
