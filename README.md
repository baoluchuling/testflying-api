# testflying-api

`testflying-api` 是 `testflying` 内部应用分发客户端的后端 API 项目。服务端只维护分发事实，不保存安装状态、下载进度、用户排序、通知已读等客户端状态。

## 当前能力

- `GET /health`：服务健康检查。
- `GET /v1/test-distribution/workspace`：返回客户端首屏需要的 workspace 快照结构。
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

正式部署前必须修改 `docker-compose.yml` 里的数据库密码、MinIO 密码、`TESTFLYING_STATIC_TOKEN` 和公开访问域名。iOS OTA 安装真实使用时，`TESTFLYING_PUBLIC_BASE_URL` 和对象存储下载地址需要是设备可访问的 HTTPS 地址。

默认环境变量在 `docker-compose.yml` 中配置：

- `TESTFLYING_DATABASE_URL`：默认 `postgresql+psycopg://testflying:testflying@postgres:5432/testflying`
- `TESTFLYING_PUBLIC_BASE_URL`：默认 `http://localhost:8000`
- `TESTFLYING_STORAGE_BACKEND`：默认 `s3`
- `TESTFLYING_S3_ENDPOINT_URL`：默认 `http://minio:9000`
- `TESTFLYING_S3_PUBLIC_BASE_URL`：默认 `http://localhost:9000/testflying`
- `TESTFLYING_S3_BUCKET`：默认 `testflying`
- `TESTFLYING_STATIC_TOKEN`：默认 `dev-token`

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

运行测试：

```bash
pytest
ruff check src tests
```

## 后续接口边界

服务端后续按客户端契约补齐：

- 包上传和 CI webhook。
- 应用、构建、制品下载地址。
- 设备登记和设备池。
- 开发者账号续费提醒。
- 通知 feed。

服务端明确不做：

- 安装状态。
- 下载进度。
- 暂停/继续状态。
- 用户排序。
- 通知已读。

客户端契约参考 `testflying` 仓库的 `docs/api-contract.md`。
