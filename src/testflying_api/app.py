from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, sessionmaker

from testflying_api.config import Settings
from testflying_api.database import create_engine_for_url, create_session_factory
from testflying_api.errors import ApiError, api_error_handler
from testflying_api.schema import Base
from testflying_api.storage import ArtifactStorage, storage_from_settings


def create_app(
    settings: Settings | None = None,
    *,
    session_factory: sessionmaker[Session] | None = None,
    artifact_storage: ArtifactStorage | None = None,
) -> FastAPI:
    app_settings = settings or Settings.from_environment()
    app = FastAPI(
        title="testflying API",
        version="0.1.0",
        description="Backend API for internal app distribution workspace data.",
    )
    app.state.settings = app_settings
    if session_factory is None:
        engine = create_engine_for_url(app_settings.database_url)
        Base.metadata.create_all(engine)
        session_factory = create_session_factory(engine)
        app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.artifact_storage = artifact_storage or storage_from_settings(app_settings)

    if app_settings.storage_backend == "local":
        app_settings.storage_root.mkdir(parents=True, exist_ok=True)
        app.mount(
            "/artifacts",
            StaticFiles(directory=app_settings.storage_root),
            name="artifacts",
        )

    app.add_exception_handler(ApiError, api_error_handler)

    from testflying_api.routes import accounts, devices, health, notifications, uploads, workspace

    app.include_router(health.router)
    app.include_router(workspace.router)
    app.include_router(uploads.router)
    app.include_router(devices.router)
    app.include_router(accounts.router)
    app.include_router(notifications.router)
    return app
