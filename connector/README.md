# testflying-connector

`testflying-connector` 是按开发者账号隔离部署的商店 API 中转器。它使用 Go 实现，运行时是单二进制服务，不依赖数据库、MinIO 或 Python Web 框架。

中心后台 `testflying-server` 只保存 connector 地址和调用 token，不保存 Apple `.p8`、Google service account JSON 或商店访问 token。每个 connector 只绑定一个开发者账号，只接受该账号的同步请求。

## 模式

- `mock`：默认模式，用于本地开发和无商店凭据测试，返回可预测的示例结果。
- `live`：生产模式，读取 Apple / Google 凭据并调用真实商店 API。

生产环境必须显式设置：

```bash
TESTFLYING_CONNECTOR_STORE_MODE=live
```

## 本地启动

```bash
cd apps/testflying-server/connector
go test ./...
TESTFLYING_CONNECTOR_DEVELOPER_ACCOUNT_ID=account-apple-enterprise \
TESTFLYING_CONNECTOR_TOKEN=dev-connector-token \
go run ./cmd/testflying-connector
```

默认监听 `:8100`，可用 `TESTFLYING_CONNECTOR_LISTEN_ADDR` 覆盖。

## Docker

```bash
cd apps/testflying-server/connector
docker build -t testflying-connector:local .
docker run --rm -p 8100:8100 --memory=64m \
  -e TESTFLYING_CONNECTOR_DEVELOPER_ACCOUNT_ID=account-apple-enterprise \
  -e TESTFLYING_CONNECTOR_TOKEN=dev-connector-token \
  testflying-connector:local
```

## Apple 凭据

Apple 使用 App Store Connect API Key。准备步骤：

1. 登录 App Store Connect。
2. 进入 Users and Access / Integrations / App Store Connect API。
3. 创建 Team API Key。
4. 记录 `Issuer ID` 和 `Key ID`。
5. 下载 `.p8` 私钥文件。
6. 角色建议先用 `App Manager`，因为需要读取和修改 App Store 信息、版本本地化和商店文案。

部署示例：

```bash
docker run -d --name testflying-connector-apple-a \
  -p 8100:8100 --memory=64m \
  -v /opt/testflying/secrets/apple-a:/run/secrets/apple:ro \
  -e TESTFLYING_CONNECTOR_STORE_MODE=live \
  -e TESTFLYING_CONNECTOR_DEVELOPER_ACCOUNT_ID=apple-account-a \
  -e TESTFLYING_CONNECTOR_TOKEN='<random-token>' \
  -e TESTFLYING_CONNECTOR_APPLE_ISSUER_ID='<issuer-id>' \
  -e TESTFLYING_CONNECTOR_APPLE_KEY_ID='<key-id>' \
  -e TESTFLYING_CONNECTOR_APPLE_PRIVATE_KEY_PATH=/run/secrets/apple/AuthKey_XXXX.p8 \
  testflying-connector:local
```

## Google 凭据

Google 使用 service account。准备步骤：

1. 创建或选择 Google Cloud Project。
2. 启用 Google Play Developer API。
3. 创建 service account。
4. 在 Google Play Console 的 Users and permissions 中邀请 service account 邮箱。
5. 给目标 App 授权，至少需要能查看和管理商店信息。
6. 下载 service account JSON。

部署示例：

```bash
docker run -d --name testflying-connector-google-a \
  -p 8100:8100 --memory=64m \
  -v /opt/testflying/secrets/google-a:/run/secrets/google:ro \
  -e TESTFLYING_CONNECTOR_STORE_MODE=live \
  -e TESTFLYING_CONNECTOR_DEVELOPER_ACCOUNT_ID=google-account-a \
  -e TESTFLYING_CONNECTOR_TOKEN='<random-token>' \
  -e TESTFLYING_CONNECTOR_GOOGLE_SERVICE_ACCOUNT_JSON_PATH=/run/secrets/google/service-account.json \
  testflying-connector:local
```

## 接口

- `GET /health`
- `POST /v1/preflight`
- `GET /v1/apps/{app_id}/supported-locales`
- `POST /v1/sync-runs`

除 `/health` 外，所有接口都需要：

```http
Authorization: Bearer <connector-token>
```

`live` 模式当前能力：

- Apple / iOS：支持版本预检查、版本支持语言、版本说明同步、文字类商店元数据同步。
- Google / Android：支持连接预检查、商店 listing 支持语言、文字类商店元数据同步。
- Google / Android 版本说明同步暂时返回失败，因为 Google Play 需要 `track` 和 `versionCode`，当前中心后台协议还没有这两个字段。

## 限流

`GET /health` 不限流。其它商店接口按平台限流：

- Google / Android 默认 `200` 次 / `60` 秒。
- Apple / iOS 根据 Apple 返回的 `X-Rate-Limit` 中 `user-hour-lim` 下调 20% 后执行；未拿到响应头前使用 fallback `2880` 次 / 小时。

可用环境变量覆盖：

- `TESTFLYING_CONNECTOR_GOOGLE_RATE_LIMIT_MAX_REQUESTS`
- `TESTFLYING_CONNECTOR_GOOGLE_RATE_LIMIT_WINDOW_SECONDS`
- `TESTFLYING_CONNECTOR_APPLE_RATE_LIMIT_FALLBACK_MAX_REQUESTS`
- `TESTFLYING_CONNECTOR_APPLE_RATE_LIMIT_WINDOW_SECONDS`
- `TESTFLYING_CONNECTOR_APPLE_RATE_LIMIT_SAFETY_RATIO`
