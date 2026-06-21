# 商店同步设计

## 目标

`testflying-server` 保持测试包管理分发主线能力，同时新增商店同步能力。商店同步必须按开发者账号隔离，避免中心后台持有多个开发者账号的商店私钥，也避免一个执行单元处理多个开发者账号的商店任务。

## 项目拆分

- `testflying-server`：中心化后台，负责账号、App、构建、版本说明草稿、商店元数据草稿、预检查缓存、同步记录和审计。
- `testflying-connector`：账号级 Go 子项目，每个开发者账号单独部署一份，负责保存该账号商店凭证并调用 Apple / Google 商店 API。

中心后台可以通过 HTTP 直接调用 connector，也可以让 connector 主动轮询中心后台领取任务。中心后台不能长期保存 Apple `.p8`、Google service account JSON 或商店访问 token；Windows 一次性安装包生成时会短暂接收凭据并直接写入 zip 响应，数据库只保存 connector token 和 `active://<account_id>` 地址。

## 第一版范围

第一版支持后台可配置闭环和两类手动同步：

- 后台可以新增/编辑开发者账号。
- 上传包时可以选择开发者账号，也可以在账号详情页绑定已有 App。
- 账号详情页可以维护 App 的 `store_app_id` / `store_package_name`。
- 账号详情页会自动检查 connector，也支持手动检查连接状态。
- 账号下 App 商店标识按平台收窄：iOS 只填 App Store Connect App ID，Android 只填 Google Play package name。
- 后台在开发者账号详情页下进入 App 的 `商店元数据` 或 `管理版本说明` 页面。
- 页面进入时自动发起预检查。
- 商店元数据页进入时通过 connector 拉取商店 App 实际支持语言；后台不再把本地默认语言混入商店返回结果。
- 商店元数据页默认优先使用 `en-US` 作为源文案语言，并按 App 平台展示商店术语。iOS 使用 App Store Connect 的 `Keywords`、`Promotional Text` 和 `Description`；Android 使用 Google Play 的 `Full description`。标题、副标题、隐私政策 URL、支持 URL、营销 URL、App 图标和素材备注当前不支持设置。
- 商店元数据页支持多套商店内容草稿；同一个账号、App、平台、版本和语言下，可以按 `content_set_id` 保存多套文案和商店图。
- 商店元数据页默认只展示当前语言；每个字段可以单独展开查看所有语言，并提供“从英文填充其他语言”按钮；第一版未接入翻译服务时只把英文源文案填充到空白语言。
- 商店元数据页支持商店图素材上传草稿，并按平台展示术语。iOS 展示 `iPhone screenshots` 和 `iPad screenshots`；Android 展示 `Feature graphic`、`Phone screenshots` 和 `Tablet screenshots`。图片可以直接拖拽上传，也可以拖入按语言命名的文件夹，后台会按语言和素材类型归类并上传到对象存储。
- 相同账号、App、平台、版本、语言和操作的预检查结果缓存 5 分钟。
- 商店元数据页提供“实时查询”按钮，可以绕过 5 分钟缓存重新查询商店状态；同一账号、App、版本、语言和操作 1 分钟内只能触发一次手动实时查询。
- 只有预检查通过时才允许同步。
- 同步前复用同一套 5 分钟预检查规则。
- 商店元数据同步前，中心后台会先做平台字段校验。iOS 会校验 `Keywords`、`Promotional Text` 和 `Description` 的长度；Android 会校验 `Full description` 的长度。校验失败时不调用 connector，也不会创建同步记录。草稿保存阶段仍允许保存半成品，只要求描述非空。
- 同步结果写入 `store_sync_runs`，操作写入 `audit_logs`。

暂不做：

- 商店截图尺寸校验和商店侧截图同步的完整适配；当前中心后台已保存图片文件并在同步 payload 中提供图片 URL，connector 后续按商店平台要求消费这些图片。
- 自动提审。
- 定时同步。
- 跨账号批量同步。
- Android 版本说明真实同步。Google Play 需要 `track` 和 `versionCode`，当前中心后台协议还没有提供这两个字段；Android 商店元数据同步可先使用。

## 中心后台数据

- `apps.developer_account_id`：App 直接归属开发者账号。
- `apps.store_app_id` / `apps.store_package_name`：商店侧 App 标识。
- `store_connectors`：账号对应 connector 地址和调用 token。
- `store_release_note_drafts`：版本说明草稿。
- `store_app_metadata_drafts`：商店元数据草稿，包括平台适用的文案字段、商店图素材和内容套件信息。表内保留的标题、副标题和 URL 旧列仅用于兼容历史数据，当前后台不同步这些字段，也不再提供 App 图标和素材备注设置。唯一范围是账号、App、平台、版本、语言和 `content_set_id`。
- `store_preflight_checks`：5 分钟预检查缓存。
- `store_sync_runs`：同步执行记录。
- `audit_logs`：后台操作审计。

旧表 `developer_account_apps` 暂时保留，用于兼容现有客户端账号续费接口。商店同步新流程以 `apps.developer_account_id` 为准。

## Connector 接口

中心后台调用 connector：

```http
GET  /health
POST /v1/preflight
GET  /v1/apps/{app_id}/supported-locales
POST /v1/sync-runs
```

所有商店接口都需要：

```http
Authorization: Bearer <connector-token>
```

`GET /v1/apps/{app_id}/supported-locales` 示例：

```http
GET /v1/apps/app-aurora-ios/supported-locales?developerAccountId=account-apple-enterprise&platform=ios&version=2.4.0
```

返回：

```json
{
  "locales": ["zh-Hans", "en-US", "ja", "ko"]
}
```

`POST /v1/preflight` 示例：

```json
{
  "developerAccountId": "account-apple-enterprise",
  "operation": "update_release_notes",
  "platform": "ios",
  "version": "2.4.0",
  "locale": "zh-Hans",
  "app": {
    "appId": "app-aurora-ios",
    "bundleIdentifier": "com.internal.aurora",
    "storeAppId": "1234567890",
    "packageName": "com.internal.aurora"
  }
}
```

`POST /v1/sync-runs` 示例：

```json
{
  "runId": "sync-001",
  "developerAccountId": "account-apple-enterprise",
  "operation": "update_release_notes",
  "platform": "ios",
  "version": "2.4.0",
  "locale": "zh-Hans",
  "app": {
    "appId": "app-aurora-ios",
    "bundleIdentifier": "com.internal.aurora",
    "storeAppId": "1234567890",
    "packageName": "com.internal.aurora"
  },
  "releaseNotes": "修复已知问题，优化安装体验。"
}
```

商店元数据同步使用同一个接口，`operation` 改为 `update_app_metadata`，并传入 `metadata`：

```json
{
  "runId": "sync-002",
  "developerAccountId": "account-apple-enterprise",
  "operation": "update_app_metadata",
  "platform": "ios",
  "version": "2.4.0",
  "locale": "zh-Hans",
  "app": {
    "appId": "app-aurora-ios",
    "bundleIdentifier": "com.internal.aurora",
    "storeAppId": "1234567890",
    "packageName": "com.internal.aurora"
  },
  "metadata": {
    "contentSet": {
      "id": "default",
      "name": "默认上架内容"
    },
    "keywords": "internal,test",
    "promotionalText": "更稳定的测试体验。",
    "description": "用于内部测试包分发和回归验证。",
    "storeImages": {
      "phone_screenshots": {
        "urls": [],
        "assets": [
          {
            "fileName": "phone-1.png",
            "contentType": "image/png",
            "sizeBytes": 12345,
            "storageKey": "store-assets/account-apple-enterprise/app-aurora-ios/default/2.4.0/zh-Hans/phone_screenshots/phone-1.png",
            "downloadUrl": "https://dist.example.test/artifacts/store-assets/account-apple-enterprise/app-aurora-ios/default/2.4.0/zh-Hans/phone_screenshots/phone-1.png"
          }
        ]
      },
      "tablet_screenshots": {
        "urls": [],
        "assets": []
      },
      "feature_graphic_url": {
        "urls": [],
        "assets": []
      }
    }
  }
}
```

中心后台会按语言多次调用 `POST /v1/sync-runs`，每次请求的 `locale` 和 `metadata` 对应该语言。connector 不提供同步记录查询接口，任务状态以中心后台 `store_sync_runs` 为准。

### Active Connector 协议

当 `store_connectors.base_url` 为 `active://<account_id>` 时，中心后台不再发起出站 HTTP 请求，而是把上述请求投递到内存任务队列。connector 运行在 Windows 或其它受限网络环境时主动连接中心后台：

```http
POST /connector-agent/v1/poll
Authorization: Bearer <connector-token>
Content-Type: application/json

{
  "accountId": "account-apple-enterprise",
  "timeoutSeconds": 25
}
```

没有任务时返回：

```json
{
  "task": null
}
```

有任务时返回：

```json
{
  "task": {
    "id": "task-...",
    "method": "POST",
    "path": "/v1/preflight",
    "headers": {
      "Authorization": "Bearer <connector-token>",
      "Content-Type": "application/json",
      "Accept": "application/json"
    },
    "body": "{...}"
  }
}
```

connector 在本地复用同一个 HTTP handler 执行任务，然后回传：

```http
POST /connector-agent/v1/results
Authorization: Bearer <connector-token>
Content-Type: application/json

{
  "accountId": "account-apple-enterprise",
  "taskId": "task-...",
  "statusCode": 200,
  "body": "{\"status\":\"ok\"}"
}
```

这个协议是长轮询，不需要 Windows 开放入站端口，也不需要 SSH 反向隧道。connector 断线后会自动退避并重新轮询；中心后台请求等待超时后会按 connector 调用失败处理。

## Connector 部署和凭据

connector 默认以 `mock` 模式启动，用于本地测试。生产部署必须显式开启 `live`：

```bash
TESTFLYING_CONNECTOR_STORE_MODE=live
```

Apple connector 需要 App Store Connect API Key：

- `TESTFLYING_CONNECTOR_APPLE_ISSUER_ID`
- `TESTFLYING_CONNECTOR_APPLE_KEY_ID`
- `TESTFLYING_CONNECTOR_APPLE_PRIVATE_KEY_PATH`

`.p8` 文件挂载在 connector 所在机器，例如：

```bash
-v /opt/testflying/secrets/apple-a:/run/secrets/apple:ro
```

Google connector 需要 service account JSON：

- `TESTFLYING_CONNECTOR_GOOGLE_SERVICE_ACCOUNT_JSON_PATH`
- `TESTFLYING_CONNECTOR_GOOGLE_DEVELOPER_ID` 可选

JSON 文件挂载在 connector 所在机器，例如：

```bash
-v /opt/testflying/secrets/google-a:/run/secrets/google:ro
```

中心后台只持久化 connector URL 和 token，不转存这些商店凭据。

Windows 推荐使用账号详情页的 `生成 Windows 一次性安装包`：

- 后台根据账号平台要求上传 App Store Connect `.p8` 或 Google service account JSON。
- 后台生成 zip，包含 `install.ps1`、`config.json`、`README.txt` 和 `secrets/...`。
- 生成时自动把当前账号 connector 保存为 `active://<account_id>`。
- `install.ps1` 会把文件复制到 `C:\ProgramData\TestFlying\connectors\<account_id>`，注册 `testflying-connector-<account_id>` 计划任务，并从 GitHub Release 下载 Windows connector exe。
- 手动重启：`schtasks /Run /TN testflying-connector-<account_id>`。

## 隔离规则

- 一个 connector 只能绑定一个 `developer_account_id`。
- 中心后台对 `store_connectors.developer_account_id` 加唯一约束，同一账号重复保存时只能编辑原 connector。
- connector 收到请求后必须校验请求账号等于自身绑定账号。
- 中心后台不能把一个账号的任务发给另一个账号的 connector。
- 商店私钥只存在 connector 部署环境。
- 中心后台日志和同步记录不能保存商店私钥、完整 Authorization header 或 service account JSON。
- connector 对商店接口做平台限流：Google / Android 默认 200 次 / 分钟；Apple / iOS 根据 Apple `X-Rate-Limit` 的 `user-hour-lim` 下调 20% 后执行，未拿到响应头前使用 fallback。
