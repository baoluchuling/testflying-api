# testflying-api

`testflying-api` 是 `testflying` 内部应用分发客户端的后端 API 项目。服务端只维护分发事实，不保存安装状态、下载进度、用户排序、通知已读等客户端状态。

## 当前能力

- `GET /health`：服务健康检查。
- `GET /v1/test-distribution/workspace`：返回客户端首屏需要的 workspace 快照结构。
- 请求上下文预留 `Authorization`、`X-Device-ID`、`X-Client-Platform`。
- Docker 部署入口：`docker compose up --build`。

## Docker 部署

第一版部署默认使用 Docker Compose，数据库和上传文件先放在本地 `./data` 目录，后续再切 PostgreSQL 或对象存储。

```bash
docker compose up --build
```

如果部署环境没有 Compose 插件，也可以直接使用 Docker：

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

验证：

```bash
curl http://localhost:8000/health
```

预期响应：

```json
{"status":"ok"}
```

默认环境变量在 `docker-compose.yml` 中配置：

- `TESTFLYING_DATABASE_URL`：默认 `sqlite:////app/data/testflying.db`
- `TESTFLYING_PUBLIC_BASE_URL`：默认 `http://localhost:8000`
- `TESTFLYING_STORAGE_ROOT`：默认 `/app/data/artifacts`
- `TESTFLYING_STATIC_TOKEN`：默认 `dev-token`

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
