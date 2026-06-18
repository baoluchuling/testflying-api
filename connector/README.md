# testflying-connector

`testflying-connector` 是按开发者账号隔离部署的商店同步中转器。

中心后台 `testflying-server` 只保存 connector 地址和调用 token，不保存 Apple `.p8` 或 Google service account JSON。每个 connector 只绑定一个开发者账号，只接受该账号的同步请求。

connector 本身不保存同步任务状态。同步记录、审计和错误摘要由中心后台写入数据库；connector 只负责校验账号、读取商店状态、拉取支持语言并转发同步请求。

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
- `GET /v1/apps/{app_id}/supported-locales`
- `POST /v1/sync-runs`

第一版实现 `update_release_notes` 和 `update_app_metadata` 两类同步协议。商店元数据页会通过 `supported-locales` 拉取当前 App 和版本支持的语言；关键词、宣传文本和描述按语言提交。当前 connector 仍是可运行的示例中转器，真实 Apple / Google 调用后续在 `store_clients` 层替换。
