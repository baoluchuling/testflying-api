from __future__ import annotations

import plistlib
from io import BytesIO
from zipfile import ZipFile

import pytest

from testflying_api.package_parser import (
    PackageParseError,
    android_metadata_from_upload,
    parse_ipa_metadata,
)


def test_parse_ipa_metadata() -> None:
    ipa_bytes = make_ipa_bytes()

    metadata = parse_ipa_metadata(ipa_bytes)

    assert metadata.bundle_identifier == "com.example.aurora"
    assert metadata.app_name == "Aurora"
    assert metadata.version == "1.2.3"
    assert metadata.build_number == "45"
    assert metadata.platform == "ios"


def test_android_metadata_requires_upload_fields() -> None:
    with pytest.raises(PackageParseError):
        android_metadata_from_upload(
            package_name="com.example.android",
            app_name=None,
            version="1.0.0",
            build_number="1",
        )


def test_android_metadata_from_upload() -> None:
    metadata = android_metadata_from_upload(
        package_name="com.example.android",
        app_name="Android App",
        version="1.0.0",
        build_number="1",
    )

    assert metadata.bundle_identifier == "com.example.android"
    assert metadata.platform == "android"


def make_ipa_bytes() -> bytes:
    plist = plistlib.dumps(
        {
            "CFBundleIdentifier": "com.example.aurora",
            "CFBundleDisplayName": "Aurora",
            "CFBundleShortVersionString": "1.2.3",
            "CFBundleVersion": "45",
        }
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("Payload/Aurora.app/Info.plist", plist)
    return buffer.getvalue()
