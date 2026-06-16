from __future__ import annotations

from fastapi import APIRouter, Header

from testflying_api.models import WorkspaceResponse

router = APIRouter()


@router.get(
    "/v1/test-distribution/workspace",
    response_model=WorkspaceResponse,
)
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
