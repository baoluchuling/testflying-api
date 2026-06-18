from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    developer_account_id: str
    connector_token: str
    google_rate_limit_max_requests: int
    google_rate_limit_window_seconds: int
    apple_rate_limit_fallback_max_requests: int
    apple_rate_limit_window_seconds: int
    apple_rate_limit_safety_ratio: float

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            developer_account_id=os.getenv(
                "TESTFLYING_CONNECTOR_DEVELOPER_ACCOUNT_ID",
                "account-apple-enterprise",
            ),
            connector_token=os.getenv("TESTFLYING_CONNECTOR_TOKEN", "dev-connector-token"),
            google_rate_limit_max_requests=_int_from_env(
                "TESTFLYING_CONNECTOR_GOOGLE_RATE_LIMIT_MAX_REQUESTS",
                200,
            ),
            google_rate_limit_window_seconds=_int_from_env(
                "TESTFLYING_CONNECTOR_GOOGLE_RATE_LIMIT_WINDOW_SECONDS",
                60,
            ),
            apple_rate_limit_fallback_max_requests=_int_from_env(
                "TESTFLYING_CONNECTOR_APPLE_RATE_LIMIT_FALLBACK_MAX_REQUESTS",
                2880,
            ),
            apple_rate_limit_window_seconds=_int_from_env(
                "TESTFLYING_CONNECTOR_APPLE_RATE_LIMIT_WINDOW_SECONDS",
                3600,
            ),
            apple_rate_limit_safety_ratio=_float_from_env(
                "TESTFLYING_CONNECTOR_APPLE_RATE_LIMIT_SAFETY_RATIO",
                0.8,
            ),
        )


def _int_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return max(int(raw_value), 1)
    except ValueError:
        return default


def _float_from_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        value = float(raw_value)
    except ValueError:
        return default
    return min(max(value, 0.1), 1.0)
