from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import boto3

from testflying_api.config import Settings
from testflying_api.errors import ApiError


@dataclass(frozen=True)
class StoredArtifact:
    storage_key: str
    download_url: str
    storage_path: Path | None = None


class ArtifactStorage(Protocol):
    backend: str

    def save(
        self,
        build_id: str,
        file_name: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> StoredArtifact: ...


class LocalArtifactStorage:
    backend = "local"

    def __init__(self, *, root: Path, public_base_url: str) -> None:
        self._root = root
        self._public_base_url = public_base_url.rstrip("/")

    def save(
        self,
        build_id: str,
        file_name: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> StoredArtifact:
        storage_key = _storage_key(build_id, file_name)
        storage_path = self._root / storage_key
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(content)
        return StoredArtifact(
            storage_key=storage_key,
            storage_path=storage_path,
            download_url=f"{self._public_base_url}/artifacts/{_quote_path(storage_key)}",
        )


class S3ArtifactStorage:
    backend = "s3"

    def __init__(self, *, client: object, bucket: str, public_base_url: str) -> None:
        self._client = client
        self._bucket = bucket
        self._public_base_url = public_base_url.rstrip("/")

    def save(
        self,
        build_id: str,
        file_name: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> StoredArtifact:
        storage_key = _storage_key(build_id, file_name)
        self._client.put_object(
            Bucket=self._bucket,
            Key=storage_key,
            Body=content,
            ContentType=content_type,
        )
        return StoredArtifact(
            storage_key=storage_key,
            download_url=f"{self._public_base_url}/{_quote_path(storage_key)}",
        )


def storage_from_settings(settings: Settings) -> ArtifactStorage:
    if settings.storage_backend == "local":
        return LocalArtifactStorage(
            root=settings.storage_root,
            public_base_url=settings.public_base_url,
        )
    if settings.storage_backend != "s3":
        raise ApiError("invalid_storage_backend", "不支持的制品存储后端")
    if not settings.s3_endpoint_url:
        raise ApiError("invalid_storage_config", "缺少 S3 endpoint 配置")
    if not settings.s3_public_base_url:
        raise ApiError("invalid_storage_config", "缺少 S3 public base URL 配置")

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
    )
    return S3ArtifactStorage(
        client=client,
        bucket=settings.s3_bucket,
        public_base_url=settings.s3_public_base_url,
    )


def _storage_key(build_id: str, file_name: str) -> str:
    safe_name = Path(file_name).name or "artifact.bin"
    return f"{build_id}/{safe_name}"


def _quote_path(path: str) -> str:
    return "/".join(quote(part) for part in path.split("/"))
