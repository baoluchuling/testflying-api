from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from testflying_api.schema import StoreAppMetadataDraft, StoreSyncRun
from testflying_api.seed import seed_demo_catalog
from tests.fixtures import make_png_header_bytes


def test_store_management_import_requires_static_token(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        (
            "/v1/store-management/developer-accounts/account-apple-enterprise"
            "/apps/app-aurora-ios/metadata-content-sets"
        ),
        data={"metadata": json.dumps(_metadata_payload())},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_static_token"


def test_store_management_imports_metadata_content_set_without_store_sync(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        (
            "/v1/store-management/developer-accounts/account-apple-enterprise"
            "/apps/app-aurora-ios/metadata-content-sets"
        ),
        headers={"Authorization": "Bearer dev-token"},
        data={"metadata": json.dumps(_metadata_payload())},
        files=[
            (
                "storeImageFiles__phone_screenshots__en-US",
                ("phone-1.png", make_png_header_bytes(1290, 2796), "image/png"),
            ),
            (
                "storeImageFiles__phoneScreenshots__zh-Hant",
                ("phone-hant.png", make_png_header_bytes(1320, 2868), "image/png"),
            ),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "contentSet": {"id": "summer-a", "name": "暑期截图方案 A"},
        "version": "1.0.0",
        "locales": ["en-US", "zh-Hant"],
        "savedDrafts": 2,
        "uploadedAssets": 2,
        "warnings": [],
    }

    drafts = db_session.query(StoreAppMetadataDraft).order_by(StoreAppMetadataDraft.locale).all()
    assert db_session.query(StoreSyncRun).count() == 0
    assert {draft.locale for draft in drafts} == {"en-US", "zh-Hant"}

    en_us = next(draft for draft in drafts if draft.locale == "en-US")
    zh_hant = next(draft for draft in drafts if draft.locale == "zh-Hant")
    assert en_us.content_set_id == "summer-a"
    assert en_us.content_set_name == "暑期截图方案 A"
    assert en_us.keywords == "novel,reader,story"
    assert en_us.promotional_text == "Read better stories every day."
    assert en_us.description == "Long store description for import testing."
    assert en_us.store_images_json["phone_screenshots"]["urls"] == [
        "https://cdn.example.test/source-phone.png"
    ]
    en_us_phone_assets = en_us.store_images_json["phone_screenshots"]["assets"]
    assert [asset["fileName"] for asset in en_us_phone_assets] == ["phone-1.png"]
    assert zh_hant.description == "Long store description for import testing."
    zh_hant_phone_assets = zh_hant.store_images_json["phone_screenshots"]["assets"]
    assert [asset["fileName"] for asset in zh_hant_phone_assets] == ["phone-hant.png"]


def test_store_management_import_rejects_invalid_store_image_size(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        (
            "/v1/store-management/developer-accounts/account-apple-enterprise"
            "/apps/app-aurora-ios/metadata-content-sets"
        ),
        headers={"Authorization": "Bearer dev-token"},
        data={"metadata": json.dumps(_metadata_payload())},
        files=[
            (
                "storeImageFiles__phone_screenshots__en-US",
                ("bad-phone.png", make_png_header_bytes(500, 500), "image/png"),
            )
        ],
    )

    assert response.status_code == 422
    assert response.json()["code"] == "store_image_invalid"
    assert "Apple 要求精确尺寸" in response.json()["message"]
    assert db_session.query(StoreAppMetadataDraft).count() == 0
    assert db_session.query(StoreSyncRun).count() == 0


def _metadata_payload() -> dict[str, object]:
    return {
        "version": "1.0.0",
        "contentSet": {
            "id": "summer-a",
            "name": "暑期截图方案 A",
        },
        "sourceLocale": "en-US",
        "locales": [
            {
                "locale": "en-US",
                "keywords": "novel,reader,story",
                "promotionalText": "Read better stories every day.",
                "description": "Long store description for import testing.",
                "storeImages": {
                    "phoneScreenshots": ["https://cdn.example.test/source-phone.png"]
                },
            },
            {
                "locale": "zh-Hant",
                "keywords": "",
                "promotionalText": "",
                "description": "",
            },
        ],
    }
