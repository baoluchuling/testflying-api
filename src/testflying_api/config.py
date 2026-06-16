from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    public_base_url: str
    storage_backend: str
    storage_root: Path
    static_token: str
    s3_endpoint_url: str | None
    s3_public_base_url: str | None
    s3_bucket: str
    s3_access_key_id: str | None
    s3_secret_access_key: str | None

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            database_url=os.getenv(
                "TESTFLYING_DATABASE_URL",
                "sqlite:///./data/testflying.db",
            ),
            public_base_url=os.getenv(
                "TESTFLYING_PUBLIC_BASE_URL",
                "http://localhost:8000",
            ),
            storage_backend=os.getenv("TESTFLYING_STORAGE_BACKEND", "local"),
            storage_root=Path(
                os.getenv("TESTFLYING_STORAGE_ROOT", "./data/artifacts"),
            ),
            static_token=os.getenv("TESTFLYING_STATIC_TOKEN", "dev-token"),
            s3_endpoint_url=os.getenv("TESTFLYING_S3_ENDPOINT_URL"),
            s3_public_base_url=os.getenv("TESTFLYING_S3_PUBLIC_BASE_URL"),
            s3_bucket=os.getenv("TESTFLYING_S3_BUCKET", "testflying"),
            s3_access_key_id=os.getenv("TESTFLYING_S3_ACCESS_KEY_ID"),
            s3_secret_access_key=os.getenv("TESTFLYING_S3_SECRET_ACCESS_KEY"),
        )
