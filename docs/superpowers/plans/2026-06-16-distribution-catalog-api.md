# Distribution Catalog API Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `testflying-api` as a stateless internal app distribution catalog API that serves package, device, account, notification, and download facts without storing client/user interaction state.

**Architecture:** FastAPI exposes read-only catalog endpoints and upload endpoints. SQLAlchemy stores distribution facts such as apps, builds, artifacts, devices, developer accounts, and service-generated notifications. The mobile client remains responsible for install state, paused/downloading UI, sort order, read/unread notification state, tabs, filters, and all other user-state overlays.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, pytest, httpx, ruff, local filesystem storage for v1.

---

## Scope And Non-Goals

The service is the source of truth for distribution facts only:

- Apps and builds.
- Build environment classification: `development` or `production`.
- Build metadata: bundle id/package name, version, build number, platform, changelog, published time.
- Artifact facts: IPA/APK object path, iOS manifest URL, Android download URL.
- Developer account renewal facts.
- Device registration and build visibility rules.
- Service-generated notification feed items such as new build published and account renewal warning.

The service must not store user/client state:

- No install state.
- No paused/downloading/installing state.
- No download progress.
- No per-user build sort order.
- No notification read/unread state.
- No current tab/filter/sheet/scroll state.
- No device-local usage trace like "this device installed build X".

Deleted from the previous API contract:

- `POST /v1/test-distribution/builds/{buildId}/install-tasks`
- `PATCH /v1/test-distribution/install-tasks/{taskId}`
- `GET /v1/test-distribution/install-tasks/{taskId}`
- `PUT /v1/test-distribution/users/me/build-sort-order`
- `PATCH /v1/test-distribution/notifications/{notificationId}`
- `POST /v1/test-distribution/notifications/mark-all-read`

## File Structure

Create or modify these files in `/Users/admin/ai_project/apps/testflying-api`:

- `pyproject.toml`: add SQLAlchemy, Alembic, python-multipart, and testing dependencies.
- `src/testflying_api/config.py`: settings object for database URL, public base URL, storage path, and token config.
- `src/testflying_api/app.py`: FastAPI app factory.
- `src/testflying_api/main.py`: import app from the factory.
- `src/testflying_api/errors.py`: API error model and exception handlers.
- `src/testflying_api/database.py`: SQLAlchemy engine, session factory, dependency.
- `src/testflying_api/schema.py`: SQLAlchemy table models.
- `src/testflying_api/domain.py`: domain dataclasses/enums independent of FastAPI.
- `src/testflying_api/catalog_repository.py`: queries for apps, builds, devices, accounts, and notifications.
- `src/testflying_api/catalog_service.py`: workspace composition and visibility decisions.
- `src/testflying_api/storage.py`: local artifact storage and public URL generation.
- `src/testflying_api/package_parser.py`: package metadata extraction for IPA and metadata-assisted APK uploads.
- `src/testflying_api/manifest.py`: iOS `manifest.plist` generation.
- `src/testflying_api/routes/health.py`: health route.
- `src/testflying_api/routes/workspace.py`: workspace route.
- `src/testflying_api/routes/uploads.py`: package upload route.
- `src/testflying_api/routes/devices.py`: device read/registration routes.
- `src/testflying_api/routes/accounts.py`: developer account routes.
- `src/testflying_api/routes/notifications.py`: notification feed route.
- `alembic.ini`: Alembic config.
- `alembic/env.py`: migration environment.
- `alembic/versions/*.py`: database migrations.
- `tests/conftest.py`: test app and temporary database fixtures.
- `tests/test_workspace.py`: workspace contract tests.
- `tests/test_uploads.py`: upload and artifact URL tests.
- `tests/test_devices.py`: visibility and current device tests.
- `tests/test_notifications.py`: feed tests, explicitly no read/unread writes.
- `README.md`: local run commands and client connection docs.

## Chunk 1: Project Foundation

### Task 1: Settings And App Factory

**Files:**
- Create: `src/testflying_api/config.py`
- Create: `src/testflying_api/app.py`
- Modify: `src/testflying_api/main.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_health.py`

- [ ] **Step 1: Write failing app factory test**

Create `tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from testflying_api.app import create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
pytest tests/test_health.py -v
```

Expected: FAIL because `testflying_api.app` does not exist.

- [ ] **Step 3: Add settings and app factory**

Implement:

```python
# src/testflying_api/config.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    database_url: str
    public_base_url: str
    storage_root: Path
    static_token: str

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            database_url=os.getenv("TESTFLYING_DATABASE_URL", "sqlite:///./data/testflying.db"),
            public_base_url=os.getenv("TESTFLYING_PUBLIC_BASE_URL", "http://localhost:8000"),
            storage_root=Path(os.getenv("TESTFLYING_STORAGE_ROOT", "./data/artifacts")),
            static_token=os.getenv("TESTFLYING_STATIC_TOKEN", "dev-token"),
        )
```

```python
# src/testflying_api/app.py
from __future__ import annotations

from fastapi import FastAPI

from testflying_api.routes import health


def create_app() -> FastAPI:
    app = FastAPI(title="testflying API", version="0.1.0")
    app.include_router(health.router)
    return app
```

```python
# src/testflying_api/main.py
from __future__ import annotations

from testflying_api.app import create_app

app = create_app()
```

```python
# src/testflying_api/routes/health.py
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Run test and verify pass**

Run:

```bash
pytest tests/test_health.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/testflying_api/config.py src/testflying_api/app.py src/testflying_api/main.py src/testflying_api/routes/health.py tests/test_health.py
git commit -m "feat: add API app foundation"
```

### Task 2: Unified Error Shape

**Files:**
- Create: `src/testflying_api/errors.py`
- Modify: `src/testflying_api/app.py`
- Test: `tests/test_errors.py`

- [ ] **Step 1: Write failing error response test**

```python
from fastapi.testclient import TestClient

from testflying_api.app import create_app
from testflying_api.errors import ApiError


def test_api_errors_use_client_contract_shape() -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise ApiError("build_not_found", "构建不存在", status_code=404)

    client = TestClient(app)
    response = client.get("/boom")

    assert response.status_code == 404
    assert response.json() == {
        "code": "build_not_found",
        "message": "构建不存在",
        "retryable": False,
    }
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
pytest tests/test_errors.py -v
```

Expected: FAIL because `ApiError` is not implemented.

- [ ] **Step 3: Implement error handler**

`ApiError` should carry `code`, `message`, `status_code`, and `retryable`. Register a FastAPI exception handler in `create_app()`.

- [ ] **Step 4: Run test and verify pass**

```bash
pytest tests/test_errors.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/testflying_api/errors.py src/testflying_api/app.py tests/test_errors.py
git commit -m "feat: add API error contract"
```

## Chunk 2: Persistence For Distribution Facts

### Task 3: Database And Schema

**Files:**
- Modify: `pyproject.toml`
- Create: `src/testflying_api/database.py`
- Create: `src/testflying_api/schema.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/20260616_0001_initial_catalog.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Add dependencies**

Add:

```toml
"sqlalchemy>=2.0,<3.0",
"alembic>=1.14,<2.0",
"python-multipart>=0.0.20,<1.0",
```

- [ ] **Step 2: Write schema test**

```python
from sqlalchemy import inspect

from testflying_api.database import create_engine_for_url
from testflying_api.schema import Base


def test_catalog_schema_contains_no_user_state_tables() -> None:
    engine = create_engine_for_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    table_names = set(inspect(engine).get_table_names())

    assert {
        "apps",
        "builds",
        "artifacts",
        "devices",
        "developer_accounts",
        "notifications",
        "device_build_visibility",
    }.issubset(table_names)
    assert "install_tasks" not in table_names
    assert "sort_orders" not in table_names
    assert "notification_reads" not in table_names
```

- [ ] **Step 3: Run test and verify failure**

```bash
pytest tests/test_schema.py -v
```

Expected: FAIL because database/schema modules do not exist.

- [ ] **Step 4: Implement schema**

Create tables:

- `apps`: id, name, bundle_id, platform, icon_url, created_at, updated_at.
- `builds`: id, app_id, version, build_number, environment, changelog, status, published_at, expires_at.
- `artifacts`: id, build_id, file_name, file_size, sha256, storage_path, manifest_path, download_path.
- `devices`: id, name, platform, status, registered_at.
- `device_build_visibility`: device_id, build_id.
- `developer_accounts`: id, name, team_id, expires_at, status.
- `developer_account_apps`: developer_account_id, app_id.
- `notifications`: id, type, title, message, related_app_id, related_build_id, created_at.

Do not add user state tables.

- [ ] **Step 5: Run test and verify pass**

```bash
pytest tests/test_schema.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/testflying_api/database.py src/testflying_api/schema.py alembic.ini alembic tests/test_schema.py
git commit -m "feat: add catalog persistence schema"
```

### Task 4: Seed Data Fixture

**Files:**
- Create: `src/testflying_api/seed.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_seed.py`

- [ ] **Step 1: Write failing seed test**

```python
from sqlalchemy.orm import Session

from testflying_api.schema import App, Build
from testflying_api.seed import seed_demo_catalog


def test_seed_demo_catalog_creates_apps_and_builds(db_session: Session) -> None:
    seed_demo_catalog(db_session)

    assert db_session.query(App).count() >= 1
    assert db_session.query(Build).count() >= 1
```

- [ ] **Step 2: Run test and verify failure**

```bash
pytest tests/test_seed.py -v
```

Expected: FAIL because seed helper is missing.

- [ ] **Step 3: Implement seed helper**

Create deterministic demo data that maps to the current mobile UI examples:

- `Aurora Mobile`
- `Insight Desk`
- `DataFlow`
- development and production environments.
- one iOS build with manifest URL.
- one Android build with APK URL.

- [ ] **Step 4: Run test and verify pass**

```bash
pytest tests/test_seed.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/testflying_api/seed.py tests/conftest.py tests/test_seed.py
git commit -m "feat: add demo catalog seed data"
```

## Chunk 3: Workspace Catalog API

### Task 5: Catalog Repository And Workspace Service

**Files:**
- Create: `src/testflying_api/domain.py`
- Create: `src/testflying_api/catalog_repository.py`
- Create: `src/testflying_api/catalog_service.py`
- Test: `tests/test_catalog_service.py`

- [ ] **Step 1: Write failing service test**

```python
from sqlalchemy.orm import Session

from testflying_api.catalog_repository import CatalogRepository
from testflying_api.catalog_service import CatalogService
from testflying_api.seed import seed_demo_catalog


def test_workspace_contains_distribution_facts_only(db_session: Session) -> None:
    seed_demo_catalog(db_session)
    workspace = CatalogService(CatalogRepository(db_session)).workspace_for_device(
        device_id="device-001",
        platform="ios",
    )

    assert workspace.apps
    assert workspace.builds
    assert workspace.install_tasks == []
    assert workspace.sort_order.build_ids == []
```

- [ ] **Step 2: Run test and verify failure**

```bash
pytest tests/test_catalog_service.py -v
```

Expected: FAIL because repository/service do not exist.

- [ ] **Step 3: Implement repository and service**

Rules:

- Return only builds visible to the current device/platform.
- Return empty `installTasks`.
- Return empty `sortOrder.buildIds`.
- Return notifications without read/unread state.
- Return developer accounts that are related to visible apps.

- [ ] **Step 4: Run test and verify pass**

```bash
pytest tests/test_catalog_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/testflying_api/domain.py src/testflying_api/catalog_repository.py src/testflying_api/catalog_service.py tests/test_catalog_service.py
git commit -m "feat: compose workspace catalog"
```

### Task 6: Workspace Route Contract

**Files:**
- Create: `src/testflying_api/routes/workspace.py`
- Modify: `src/testflying_api/app.py`
- Test: `tests/test_workspace.py`

- [ ] **Step 1: Replace current minimal workspace test**

Assert:

- Response has `apps`, `builds`, `devices`, `developerAccounts`, `notifications`, `installTasks`, `sortOrder`, `profile`.
- `installTasks` is always `[]`.
- `sortOrder.buildIds` is always `[]`.
- No response field exposes `isRead`, `readAt`, `installedAt`, `installState`, or `progress`.

- [ ] **Step 2: Run test and verify failure**

```bash
pytest tests/test_workspace.py -v
```

Expected: FAIL until route is wired to catalog service.

- [ ] **Step 3: Implement route**

Route:

```http
GET /v1/test-distribution/workspace
```

Headers:

```http
Authorization: Bearer <token>
X-Device-ID: <device-id>
X-Client-Platform: ios
```

- [ ] **Step 4: Run test and verify pass**

```bash
pytest tests/test_workspace.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/testflying_api/routes/workspace.py src/testflying_api/app.py tests/test_workspace.py
git commit -m "feat: expose workspace catalog route"
```

## Chunk 4: Upload And Artifact Distribution

### Task 7: Local Artifact Storage

**Files:**
- Create: `src/testflying_api/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing storage test**

```python
from testflying_api.storage import LocalArtifactStorage


def test_storage_writes_file_and_returns_public_url(tmp_path) -> None:
    storage = LocalArtifactStorage(root=tmp_path, public_base_url="https://dist.example.test")

    saved = storage.save("build-1", "app.ipa", b"ipa-bytes")

    assert saved.storage_path.exists()
    assert saved.download_url == "https://dist.example.test/artifacts/build-1/app.ipa"
```

- [ ] **Step 2: Run test and verify failure**

```bash
pytest tests/test_storage.py -v
```

Expected: FAIL because storage module does not exist.

- [ ] **Step 3: Implement local storage**

Store files under:

```text
data/artifacts/{build_id}/{file_name}
```

Use this abstraction so S3/MinIO can replace local storage later.

- [ ] **Step 4: Run test and verify pass**

```bash
pytest tests/test_storage.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/testflying_api/storage.py tests/test_storage.py
git commit -m "feat: add local artifact storage"
```

### Task 8: IPA Metadata And Manifest Generation

**Files:**
- Create: `src/testflying_api/package_parser.py`
- Create: `src/testflying_api/manifest.py`
- Test: `tests/test_package_parser.py`
- Test: `tests/test_manifest.py`

- [ ] **Step 1: Write failing parser tests**

For IPA:

- Build a small zip with `Payload/Test.app/Info.plist`.
- Assert parser extracts bundle id, display name, version, build number.

For APK v1:

- Accept metadata fields from request instead of parsing binary APK.
- Assert missing required APK metadata is rejected.

- [ ] **Step 2: Run tests and verify failure**

```bash
pytest tests/test_package_parser.py tests/test_manifest.py -v
```

Expected: FAIL because modules do not exist.

- [ ] **Step 3: Implement parser and manifest builder**

IPA parser:

- Use `zipfile`.
- Find `Payload/*.app/Info.plist`.
- Parse with `plistlib`.

Manifest builder:

- Generate valid plist with `software-package`.
- Use artifact public download URL.
- Include bundle identifier, version, and title.

- [ ] **Step 4: Run tests and verify pass**

```bash
pytest tests/test_package_parser.py tests/test_manifest.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/testflying_api/package_parser.py src/testflying_api/manifest.py tests/test_package_parser.py tests/test_manifest.py
git commit -m "feat: parse packages and generate manifests"
```

### Task 9: Upload Endpoint

**Files:**
- Create: `src/testflying_api/routes/uploads.py`
- Modify: `src/testflying_api/app.py`
- Test: `tests/test_uploads.py`

- [ ] **Step 1: Write failing upload test**

Test:

- Upload IPA with `environment=development` and changelog.
- Response creates app and build.
- Response includes iOS `itms-services://?...manifest.plist`.
- Workspace after upload contains the new build.

- [ ] **Step 2: Run test and verify failure**

```bash
pytest tests/test_uploads.py -v
```

Expected: FAIL because upload route does not exist.

- [ ] **Step 3: Implement upload route**

Route:

```http
POST /v1/test-distribution/uploads
```

Form fields:

- `file`: IPA/APK.
- `platform`: `ios` or `android`.
- `environment`: `development` or `production`.
- `changelog`: optional.
- APK-only metadata: `packageName`, `appName`, `version`, `buildNumber`.

Rules:

- Upsert app by bundle id/package name + platform.
- Create build.
- Store artifact.
- Generate iOS manifest for IPA.
- Generate `build` notification feed item.
- Do not create install task.
- Do not create user/device install state.

- [ ] **Step 4: Run test and verify pass**

```bash
pytest tests/test_uploads.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/testflying_api/routes/uploads.py src/testflying_api/app.py tests/test_uploads.py
git commit -m "feat: add package upload endpoint"
```

## Chunk 5: Device Visibility And Account Facts

### Task 10: Device Catalog And Visibility

**Files:**
- Create: `src/testflying_api/routes/devices.py`
- Modify: `src/testflying_api/app.py`
- Test: `tests/test_devices.py`

- [ ] **Step 1: Write failing device tests**

Assert:

- `GET /v1/test-distribution/devices/current` returns the device fact for `X-Device-ID`.
- Unknown devices return `device_not_registered`.
- Workspace excludes builds not visible to the device.

- [ ] **Step 2: Run tests and verify failure**

```bash
pytest tests/test_devices.py -v
```

Expected: FAIL until route and visibility logic exist.

- [ ] **Step 3: Implement device route**

Routes:

```http
GET /v1/test-distribution/devices/current
GET /v1/test-distribution/devices
POST /v1/test-distribution/devices/registration-link
```

`registration-link` creates a registration request/link, not an automatic approval.

- [ ] **Step 4: Run tests and verify pass**

```bash
pytest tests/test_devices.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/testflying_api/routes/devices.py src/testflying_api/app.py tests/test_devices.py
git commit -m "feat: add device visibility endpoints"
```

### Task 11: Developer Account Facts

**Files:**
- Create: `src/testflying_api/routes/accounts.py`
- Modify: `src/testflying_api/app.py`
- Test: `tests/test_accounts.py`

- [ ] **Step 1: Write failing account tests**

Assert:

- Accounts include `expiresAt`, `status`, and related app ids.
- Workspace includes account renewal facts for visible apps.
- No client dismissal or read state is stored.

- [ ] **Step 2: Run tests and verify failure**

```bash
pytest tests/test_accounts.py -v
```

Expected: FAIL until account route exists.

- [ ] **Step 3: Implement account route**

Routes:

```http
GET /v1/test-distribution/developer-accounts
GET /v1/test-distribution/developer-accounts/renewals
```

- [ ] **Step 4: Run tests and verify pass**

```bash
pytest tests/test_accounts.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/testflying_api/routes/accounts.py src/testflying_api/app.py tests/test_accounts.py
git commit -m "feat: add developer account renewal facts"
```

## Chunk 6: Notification Feed Without Read State

### Task 12: Notification Feed

**Files:**
- Create: `src/testflying_api/routes/notifications.py`
- Modify: `src/testflying_api/app.py`
- Test: `tests/test_notifications.py`

- [ ] **Step 1: Write failing notification tests**

Assert:

- `GET /v1/test-distribution/notifications` returns build/account/device feed items.
- Feed supports `type=build|account|device` filtering.
- Response does not include `isRead` or `readAt`.
- No mark-read endpoint exists.

- [ ] **Step 2: Run tests and verify failure**

```bash
pytest tests/test_notifications.py -v
```

Expected: FAIL until notification route exists.

- [ ] **Step 3: Implement notification route**

Route:

```http
GET /v1/test-distribution/notifications
```

Do not implement read mutations.

- [ ] **Step 4: Run tests and verify pass**

```bash
pytest tests/test_notifications.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/testflying_api/routes/notifications.py src/testflying_api/app.py tests/test_notifications.py
git commit -m "feat: add notification feed"
```

## Chunk 7: Documentation And Client Contract Cleanup

### Task 13: Update API Documentation

**Files:**
- Modify: `README.md`
- Create: `docs/api-contract.md`
- Test: none

- [ ] **Step 1: Document server-owned facts**

Document:

- Workspace response shape.
- Upload request.
- Manifest generation.
- Device visibility.
- Developer account renewal facts.
- Notification feed.

- [ ] **Step 2: Document client-owned state**

Explicitly document that the server does not store:

- Install status.
- Download progress.
- Pause/resume state.
- User sort order.
- Notification read state.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/api-contract.md
git commit -m "docs: document stateless catalog contract"
```

### Task 14: Client Integration Note

**Files:**
- Create: `docs/client-integration.md`
- Test: none

- [ ] **Step 1: Write integration note**

Document required client adjustment in the `testflying` repo:

```text
Remote service should fetch server catalog/workspace, then overlay local client state:

server catalog
+ local install status
+ local paused/downloading progress
+ local sort order
+ local notification read state
= UI workspace
```

Remote client should not call removed install-task, sort-order, or mark-read endpoints.

- [ ] **Step 2: Commit**

```bash
git add docs/client-integration.md
git commit -m "docs: add client integration boundary"
```

## Final Verification

Run:

```bash
pytest
ruff check src tests
python3.11 -m compileall -q src tests
```

Expected:

- All tests pass.
- Ruff reports no issues.
- Compileall exits 0.

Then push:

```bash
git push
```

## Execution Order

Recommended order:

1. Chunk 1: Project foundation.
2. Chunk 2: Persistence for distribution facts.
3. Chunk 3: Workspace catalog API.
4. Chunk 4: Upload and artifact distribution.
5. Chunk 5: Device visibility and account facts.
6. Chunk 6: Notification feed without read state.
7. Chunk 7: Documentation and client contract cleanup.

Do not start client integration until Chunk 3 passes. Do not start upload support until the read-only catalog is stable.
