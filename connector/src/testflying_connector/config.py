from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    developer_account_id: str
    connector_token: str

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            developer_account_id=os.getenv(
                "TESTFLYING_CONNECTOR_DEVELOPER_ACCOUNT_ID",
                "account-apple-enterprise",
            ),
            connector_token=os.getenv("TESTFLYING_CONNECTOR_TOKEN", "dev-connector-token"),
        )
