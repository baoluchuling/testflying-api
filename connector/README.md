# testflying-connector

`testflying-connector` 是按开发者账号隔离部署的商店同步执行器。

中心后台 `testflying-server` 只保存 connector 地址和调用 token，不保存 Apple `.p8` 或 Google service account JSON。每个 connector 只绑定一个开发者账号，只接受该账号的同步请求。

## 本地启动

```bash
cd apps/testflying-server/connector
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
TESTFLYING_CONNECTOR_DEVELOPER_ACCOUNT_ID=account-apple-enterprise \
TESTFLYING_CONNECTOR_TOKEN=dev-connector-token \
uvicorn testflying_connector.main:app --reload --port 8100
```

## Docker

connector 镜像同样使用多阶段构建：builder 阶段生成 wheel，runtime 阶段只安装 wheel 产物，不以源码目录方式运行。

```bash
cd apps/testflying-server/connector
docker build -t testflying-connector:local .
docker run --rm -p 8100:8100 \
  -e TESTFLYING_CONNECTOR_DEVELOPER_ACCOUNT_ID=account-apple-enterprise \
  -e TESTFLYING_CONNECTOR_TOKEN=dev-connector-token \
  testflying-connector:local
```

## 接口

- `GET /health`
- `POST /v1/preflight`
- `POST /v1/sync-runs`
- `GET /v1/sync-runs/{run_id}`

第一版只实现版本说明同步协议。真实 Apple / Google 调用后续在 `store_clients` 层替换。
