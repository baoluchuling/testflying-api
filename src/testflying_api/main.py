from __future__ import annotations

from fastapi import FastAPI, Header

from testflying_api.models import WorkspaceResponse

app = FastAPI(
    title="testflying API",
    version="0.1.0",
    description="Backend API for internal app distribution workspace data.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/test-distribution/workspace", response_model=WorkspaceResponse)
def get_workspace(
    authorization: str | None = Header(default=None),
    device_id: str = Header(default="local", alias="X-Device-ID"),
    client_platform: str = Header(default="ios", alias="X-Client-Platform"),
) -> WorkspaceResponse:
    return WorkspaceResponse.empty(
        device_id=device_id,
        platform=client_platform,
        has_token=bool(authorization),
    )
