from __future__ import annotations

from pydantic import BaseModel


class AdminNavItem(BaseModel):
    key: str
    label: str
    path: str


class AdminHealthState(BaseModel):
    state: str
    label: str


class AdminBootstrapResponse(BaseModel):
    app_name: str
    nav_items: list[AdminNavItem]
    health: AdminHealthState

    model_config = {
        "alias_generator": lambda value: "".join(
            word.capitalize() if index else word
            for index, word in enumerate(value.split("_"))
        ),
        "populate_by_name": True,
    }
