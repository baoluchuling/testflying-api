# testflying-api

`testflying-api` 是 `testflying` 内部应用分发客户端的后端 API 项目。服务端只维护分发事实，不保存安装状态、下载进度、用户排序、通知已读等客户端状态。

## 当前能力

- `GET /health`：服务健康检查。
- `GET /v1/test-distribution/workspace`：返回客户端首屏需要的 workspace 快照结构。
- `POST /v1/test-distribution/uploads`：上传 IPA/APK，自动解析包信息，创建应用、构建、制品和构建通知。
- `GET /v1/test-distribution/devices/current`：读取当前设备登记事实。
- `GET /v1/test-distribution/devices`：读取设备列表。
- `POST /v1/test-distribution/devices/registration-link`：生成设备登记请求链接，不自动审批设备。
- `GET /v1/test-distribution/developer-accounts`：读取开发者账号续费事实。
- `GET /v1/test-distribution/developer-accounts/renewals`：读取需要续费提醒的账号。
- `GET /v1/test-distribution/notifications`：读取服务端通知 feed，支持 `type=build|account|device`。
- `GET /admin`：内置管理后台，用于上传包、查看应用/构建/设备/账号/通知和复制安装资源链接。
- 请求上下文预留 `Authorization`、`X-Device-ID`、`X-Client-Platform`。
- Docker Compose 默认启动 API、PostgreSQL、MinIO。

## Docker 部署

第一版部署默认使用 Docker Compose，并直接包含：

- `api`：FastAPI 服务。
- `postgres`：PostgreSQL，保存应用、构建、设备、账号、通知等分发事实。
- `minio`：S3 兼容对象存储，保存 IPA/APK 和 iOS manifest。
- `minio-init`：启动时自动创建 `testflying` bucket。

```bash
docker compose up --build
```

验证：

```bash
curl http://localhost:8000/health
```

预期响应：

```json
{"status":"ok"}
```

MinIO 控制台：

```text
http://localhost:9001
```

本地默认账号仅用于开发和内网试部署：

```text
username: testflying
password: testflying-secret
```

正式部署前必须修改 `docker-compose.yml` 里的数据库密码、MinIO 密码、`TESTFLYING_STATIC_TOKEN` 和公开访问域名。当前全栈 Compose 的公开访问域名默认指向测试服务器 `47.90.163.122`，也可以通过同名环境变量或 `.env` 覆盖。iOS OTA 安装真实使用时，`TESTFLYING_PUBLIC_BASE_URL` 和对象存储下载地址需要是设备可访问的 HTTPS 地址。

管理后台：

```text
http://localhost:8000/admin
```

后台使用 HTTP Basic 认证：

```text
username: admin
password: dev-token
```

`username` 来自 `TESTFLYING_ADMIN_USERNAME`，默认是 `admin`；`password` 复用 `TESTFLYING_STATIC_TOKEN`。测试环境可以沿用默认值，公网或正式环境必须替换 `TESTFLYING_STATIC_TOKEN`。

默认环境变量在 `docker-compose.yml` 中配置：

- `TESTFLYING_DATABASE_URL`：默认 `postgresql+psycopg://testflying:testflying@postgres:5432/testflying`
- `TESTFLYING_PUBLIC_BASE_URL`：默认 `http://47.90.163.122:8000`
- `TESTFLYING_STORAGE_BACKEND`：默认 `s3`
- `TESTFLYING_S3_ENDPOINT_URL`：默认 `http://minio:9000`
- `TESTFLYING_S3_PUBLIC_BASE_URL`：默认 `http://47.90.163.122:9000/testflying`
- `TESTFLYING_S3_BUCKET`：默认 `testflying`
- `TESTFLYING_STATIC_TOKEN`：默认 `dev-token`
- `TESTFLYING_ADMIN_USERNAME`：默认 `admin`
- `TESTFLYING_CORS_ALLOWED_ORIGINS`：默认允许 `http://localhost:8080,http://127.0.0.1:8080`，用于 Flutter Web 本地联调。

这些公开 URL 会在上传时写入构建制品记录。修改环境变量后，已经上传过的构建不会自动改 URL；需要重新上传包，或者用 SQL 替换 `artifacts.download_url`、`artifacts.manifest_url` 和 `artifacts.install_url` 里的旧域名。

## 轻量本地测试

如果本地测试环境没有 PostgreSQL 或 MinIO，可以使用 SQLite 和本地 `./data` 目录：

```bash
docker compose -f docker-compose.local.yml up --build
```

如果部署环境没有 Compose 插件，也可以直接使用 Docker 跑轻量模式：

```bash
docker build -t testflying-api:latest .
docker run -d \
  --name testflying-api \
  -p 8000:8000 \
  -e TESTFLYING_DATABASE_URL=sqlite:////app/data/testflying.db \
  -e TESTFLYING_PUBLIC_BASE_URL=http://localhost:8000 \
  -e TESTFLYING_STORAGE_ROOT=/app/data/artifacts \
  -e TESTFLYING_STATIC_TOKEN=dev-token \
  -e TESTFLYING_CORS_ALLOWED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080 \
  -v "$(pwd)/data:/app/data" \
  testflying-api:latest
```

## 本地开发

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn testflying_api.main:app --reload
```

本地启动默认使用 SQLite 和 `./data/artifacts`。应用启动时会根据 SQLAlchemy schema 自动建表，后续正式迁移路径保留在 `alembic/`。

访问管理后台：

```bash
open http://localhost:8000/admin
```

第一版后台支持上传 IPA/APK、查看应用/构建/设备/开发者账号/通知，以及复制 `installUrl`、`manifestUrl` 和 `downloadUrl`。上传页会显示上传进度；IPA/APK 的包名、应用名、版本号和构建号由服务端自动解析，必要时可以在后台覆盖应用名称。设备审批、构建删除和开发者账号编辑会放到后续管理能力里。

运行测试：

```bash
pytest
ruff check src tests
```

## 接口边界

服务端拥有这些事实：

- 应用、构建、制品和 iOS `manifest.plist` 地址。
- IPA/APK 自动解析出的包名、应用名、版本号和构建号。
- 构建环境分类：`development` 或 `production`。
- 设备登记事实和设备对构建的可见性。
- 开发者账号续费事实。
- 服务端产生的通知 feed。

服务端明确不做：

- 安装状态。
- 下载进度。
- 暂停/继续状态。
- 用户排序。
- 通知已读。

这些客户端状态不会落库，也没有对应写接口。详细契约见 `docs/api-contract.md` 和 `docs/client-integration.md`。
