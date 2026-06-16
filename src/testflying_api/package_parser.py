from __future__ import annotations

import plistlib
from dataclasses import dataclass
from io import BytesIO
from zipfile import BadZipFile, ZipFile


class PackageParseError(ValueError):
    pass


@dataclass(frozen=True)
class PackageMetadata:
    app_name: str
    bundle_identifier: str
    version: str
    build_number: str
    platform: str


def parse_ipa_metadata(content: bytes) -> PackageMetadata:
    try:
        with ZipFile(BytesIO(content)) as archive:
            info_plist_name = _find_info_plist(archive)
            raw_plist = archive.read(info_plist_name)
    except (BadZipFile, KeyError) as error:
        raise PackageParseError("IPA 包结构不正确") from error

    plist = plistlib.loads(raw_plist)
    bundle_identifier = _required_plist_value(plist, "CFBundleIdentifier")
    version = _required_plist_value(plist, "CFBundleShortVersionString")
    build_number = _required_plist_value(plist, "CFBundleVersion")
    app_name = (
        _optional_plist_value(plist, "CFBundleDisplayName")
        or _optional_plist_value(plist, "CFBundleName")
        or bundle_identifier
    )
    return PackageMetadata(
        app_name=app_name,
        bundle_identifier=bundle_identifier,
        version=version,
        build_number=build_number,
        platform="ios",
    )


def android_metadata_from_upload(
    *,
    package_name: str | None,
    app_name: str | None,
    version: str | None,
    build_number: str | None,
) -> PackageMetadata:
    missing_fields = [
        field_name
        for field_name, value in {
            "packageName": package_name,
            "appName": app_name,
            "version": version,
            "buildNumber": build_number,
        }.items()
        if not value
    ]
    if missing_fields:
        raise PackageParseError(f"Android 上传缺少 metadata: {', '.join(missing_fields)}")
    return PackageMetadata(
        app_name=app_name or "",
        bundle_identifier=package_name or "",
        version=version or "",
        build_number=build_number or "",
        platform="android",
    )


def _find_info_plist(archive: ZipFile) -> str:
    for name in archive.namelist():
        if name.startswith("Payload/") and name.endswith(".app/Info.plist"):
            return name
    raise PackageParseError("IPA 缺少 Payload/*.app/Info.plist")


def _required_plist_value(plist: dict[object, object], key: str) -> str:
    value = _optional_plist_value(plist, key)
    if value is None:
        raise PackageParseError(f"Info.plist 缺少 {key}")
    return value


def _optional_plist_value(plist: dict[object, object], key: str) -> str | None:
    value = plist.get(key)
    return value if isinstance(value, str) and value else None
