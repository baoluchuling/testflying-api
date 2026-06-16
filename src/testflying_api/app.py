from __future__ import annotations

from fastapi import FastAPI

from testflying_api.config import Settings
from testflying_api.errors import ApiError, api_error_handler
from testflying_api.routes import health, workspace


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="testflying API",
        version="0.1.0",
        description="Backend API for internal app distribution workspace data.",
    )
    app.state.settings = settings or Settings.from_environment()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(health.router)
    app.include_router(workspace.router)
    return app
