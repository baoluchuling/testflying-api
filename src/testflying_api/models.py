from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class AppSortOrder(CamelModel):
    build_ids: list[str] = Field(default_factory=list, alias="buildIds")


class UserProfile(CamelModel):
    id: str
    name: str
    role: str


class TestDevice(CamelModel):
    id: str
    name: str
    platform: str
    status: str


class WorkspaceResponse(CamelModel):
    apps: list[dict[str, object]] = Field(default_factory=list)
    builds: list[dict[str, object]] = Field(default_factory=list)
    devices: list[TestDevice] = Field(default_factory=list)
    developer_accounts: list[dict[str, object]] = Field(
        default_factory=list,
        alias="developerAccounts",
    )
    notifications: list[dict[str, object]] = Field(default_factory=list)
    install_tasks: list[dict[str, object]] = Field(default_factory=list, alias="installTasks")
    sort_order: AppSortOrder = Field(default_factory=AppSortOrder, alias="sortOrder")
    profile: UserProfile

    @classmethod
    def empty(cls, *, device_id: str, platform: str, has_token: bool) -> WorkspaceResponse:
        return cls(
            devices=[
                TestDevice(
                    id=device_id,
                    name="Local Test Device",
                    platform=platform,
                    status="registered",
                )
            ],
            profile=UserProfile(
                id="current-user",
                name="Internal Tester",
                role="authenticated" if has_token else "local",
            ),
        )
