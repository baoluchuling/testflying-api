from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from testflying_api.schema import (
    StoreAppMetadataDraft,
    StoreImageSuite,
    StoreImageSuiteLocale,
    StoreMarketingPage,
    StoreMarketingPageLocale,
    StoreReleaseNoteDraft,
    StoreSyncRun,
)
from testflying_api.seed import seed_demo_catalog
from testflying_api.store_sync import CURRENT_METADATA_VERSION
from tests.fixtures import make_png_header_bytes


def test_store_management_import_requires_static_token(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        (
            "/v1/store-management/developer-accounts/account-apple-enterprise"
            "/apps/app-aurora-ios/store-versions/1.0.0/draft"
        ),
        json=_version_payload(),
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_static_token"


def test_store_management_imports_store_version_draft_without_store_sync(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        (
            "/v1/store-management/developer-accounts/account-apple-enterprise"
            "/apps/app-aurora-ios/store-versions/1.0.0/draft"
        ),
        headers={"Authorization": "Bearer dev-token"},
        json=_version_payload(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "version": "1.0.0",
        "locales": ["en-US", "zh-Hant"],
        "savedMetadataDrafts": 2,
        "savedReleaseNoteDrafts": 2,
        "warnings": [],
    }
    assert db_session.query(StoreSyncRun).count() == 0

    metadata_drafts = (
        db_session.query(StoreAppMetadataDraft).order_by(StoreAppMetadataDraft.locale).all()
    )
    release_note_drafts = (
        db_session.query(StoreReleaseNoteDraft).order_by(StoreReleaseNoteDraft.locale).all()
    )
    assert {draft.locale for draft in metadata_drafts} == {"en-US", "zh-Hant"}
    assert {draft.locale for draft in release_note_drafts} == {"en-US", "zh-Hant"}

    en_us = next(draft for draft in metadata_drafts if draft.locale == "en-US")
    zh_hant = next(draft for draft in metadata_drafts if draft.locale == "zh-Hant")
    assert en_us.version == CURRENT_METADATA_VERSION
    assert zh_hant.version == CURRENT_METADATA_VERSION
    assert en_us.content_set_id == "default"
    assert en_us.description == "Long store description for import testing."
    assert all(
        not value["urls"] and not value["assets"]
        for value in en_us.store_images_json.values()
    )
    assert zh_hant.description == "Long store description for import testing."

    en_us_notes = next(draft for draft in release_note_drafts if draft.locale == "en-US")
    zh_hant_notes = next(draft for draft in release_note_drafts if draft.locale == "zh-Hant")
    assert en_us_notes.release_notes == "Fix bugs"
    assert zh_hant_notes.release_notes == "Fix bugs"


def test_store_management_imports_store_image_suite_without_version_scope(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        (
            "/v1/store-management/developer-accounts/account-apple-enterprise"
            "/apps/app-aurora-ios/store-image-suites"
        ),
        headers={"Authorization": "Bearer dev-token"},
        data={"metadata": json.dumps(_image_suite_payload())},
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
    assert response.json() == {
        "imageSuite": {"id": "summer-a", "name": "暑期截图方案 A"},
        "locales": ["en-US", "zh-Hant"],
        "savedLocales": 2,
        "uploadedAssets": 2,
        "warnings": [],
    }
    assert db_session.query(StoreSyncRun).count() == 0
    assert db_session.query(StoreAppMetadataDraft).count() == 0

    suite = db_session.query(StoreImageSuite).one()
    assert suite.suite_id == "summer-a"
    assert suite.suite_name == "暑期截图方案 A"
    assert suite.platform == "ios"

    suite_locales = (
        db_session.query(StoreImageSuiteLocale).order_by(StoreImageSuiteLocale.locale).all()
    )
    assert {item.locale for item in suite_locales} == {"en-US", "zh-Hant"}
    en_us = next(item for item in suite_locales if item.locale == "en-US")
    zh_hant = next(item for item in suite_locales if item.locale == "zh-Hant")
    en_us_phone_assets = en_us.store_images_json["phone_screenshots"]["assets"]
    zh_hant_phone_assets = zh_hant.store_images_json["phone_screenshots"]["assets"]
    assert [asset["fileName"] for asset in en_us_phone_assets] == ["phone-1.png"]
    assert [asset["fileName"] for asset in zh_hant_phone_assets] == ["phone-hant.png"]
    assert "/image-suites/summer-a/en-US/phone_screenshots/" in en_us_phone_assets[0][
        "storageKey"
    ]
    assert "1.0.0" not in en_us_phone_assets[0]["storageKey"]


def test_store_management_imports_marketing_page_without_store_sync(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        (
            "/v1/store-management/developer-accounts/account-apple-enterprise"
            "/apps/app-aurora-ios/marketing-pages"
        ),
        headers={"Authorization": "Bearer dev-token"},
        data={"metadata": json.dumps(_marketing_page_payload())},
        files=[
            (
                "storeImageFiles__phone_screenshots__en-US",
                ("phone-1.png", make_png_header_bytes(1290, 2796), "image/png"),
            ),
            (
                "storeImageFiles__phoneScreenshots__en-US",
                ("phone-2.png", make_png_header_bytes(1320, 2868), "image/png"),
            ),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pageId"].startswith("page-")
    assert body == {
        "pageId": body["pageId"],
        "pageName": "API 自定义产品页",
        "pageType": "custom_product_page",
        "status": "draft",
        "locales": ["en-US", "zh-Hant"],
        "savedLocales": 2,
        "uploadedAssets": 2,
        "warnings": [],
    }
    assert db_session.query(StoreSyncRun).count() == 0

    page = db_session.query(StoreMarketingPage).one()
    assert page.page_id == body["pageId"]
    assert page.page_name == "API 自定义产品页"
    assert page.page_type == "custom_product_page"
    assert page.status == "draft"
    assert page.apple_page_id == ""
    assert page.deep_link_url == "anystories:///campaign"

    locales = (
        db_session.query(StoreMarketingPageLocale)
        .order_by(StoreMarketingPageLocale.locale)
        .all()
    )
    assert [item.locale for item in locales] == ["en-US", "zh-Hant"]
    en_us = next(item for item in locales if item.locale == "en-US")
    zh_hant = next(item for item in locales if item.locale == "zh-Hant")
    assert en_us.promotional_text == "Read better stories every day."
    assert zh_hant.promotional_text == "Read better stories every day."

    phone_assets = en_us.store_images_json["phone_screenshots"]["assets"]
    assert [asset["fileName"] for asset in phone_assets] == ["phone-1.png", "phone-2.png"]
    assert f"/{body['pageId']}/marketing/en-US/phone_screenshots/" in phone_assets[0][
        "storageKey"
    ]


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
    assert en_us.version == CURRENT_METADATA_VERSION
    assert zh_hant.version == CURRENT_METADATA_VERSION
    assert en_us.content_set_id == "default"
    assert en_us.content_set_name == "默认上架内容"
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
            "/apps/app-aurora-ios/store-image-suites"
        ),
        headers={"Authorization": "Bearer dev-token"},
        data={"metadata": json.dumps(_image_suite_payload())},
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
    assert db_session.query(StoreImageSuite).count() == 0
    assert db_session.query(StoreSyncRun).count() == 0


def _version_payload() -> dict[str, object]:
    return {
        "sourceLocale": "en-US",
        "locales": [
            {
                "locale": "en-US",
                "keywords": "novel,reader,story",
                "promotionalText": "Read better stories every day.",
                "description": "Long store description for import testing.",
                "releaseNotes": "Fix bugs",
            },
            {
                "locale": "zh-Hant",
                "keywords": "",
                "promotionalText": "",
                "description": "",
                "releaseNotes": "",
            },
        ],
    }


def _image_suite_payload() -> dict[str, object]:
    return {
        "imageSuite": {
            "id": "summer-a",
            "name": "暑期截图方案 A",
        },
        "source": "api",
        "sourceLocale": "en-US",
        "locales": [
            {
                "locale": "en-US",
                "storeImages": {
                    "phoneScreenshots": ["https://cdn.example.test/source-phone.png"]
                },
            },
            {
                "locale": "zh-Hant",
                "storeImages": {},
            },
        ],
    }


def _marketing_page_payload() -> dict[str, object]:
    return {
        "pageName": "API 自定义产品页",
        "pageType": "custom_product_page",
        "sourceLocale": "en-US",
        "deepLinkUrl": "anystories:///campaign",
        "locales": [
            {
                "locale": "en-US",
                "promotionalText": "Read better stories every day.",
                "storeImages": {
                    "phoneScreenshots": ["https://cdn.example.test/source-phone.png"]
                },
            },
            {
                "locale": "zh-Hant",
                "promotionalText": "",
                "storeImages": {},
            },
        ],
    }


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
