# 中心后台商店连接对外接口

本文档只描述 `testflying-server` 中心后台里和商店连接有关的对外接口。

不包含客户端分发接口、设备接口、通知接口、App 日志接口和 `/admin/*` 管理后台页面。

## 基础约定

示例变量：

```bash
BASE_URL="http://47.90.163.122:8000"
TOKEN="dev-token"
ACCOUNT_ID="ceshi"
APP_ID="app-ios-com-boluchuling-app-lookrva"
VERSION="1.0.0"
PAGE_ID="page-xxxxxxxx"
```

所有 `/v1/store-management/*` 接口都需要静态 token：

```http
Authorization: Bearer <TESTFLYING_STATIC_TOKEN>
```

路径参数规则：

- `{accountId}` 是 testflying 中心后台里的开发者账号 ID，例如 `738W4ARM22`。
- `{appId}` 是 testflying 中心后台里的内部 App ID，不是 App Store Connect 数字 App ID，也不是 Google Play package name。
- `appId` 在 App 创建或上传包解析后生成，格式为：

```text
app-{platform}-{slug(bundleIdentifier/packageName)}
```

`slug` 规则：

1. 将 `bundleIdentifier` 或 `packageName` 中连续的非英文字母、数字字符替换为 `-`。
2. 去掉开头和结尾的 `-`。
3. 转成小写。
4. 最多保留 48 个字符。
5. 如果结果为空，使用随机 12 位字符串兜底。正常包名不会触发这个兜底。

示例：

| 平台 | 商店应用标识 | testflying `appId` |
| --- | --- | --- |
| iOS | `com.boluchuling.app.lookrva` | `app-ios-com-boluchuling-app-lookrva` |
| Android | `com.novelago.android.app` | `app-android-com-novelago-android-app` |
| Android | `com.app.android.qw.readink` | `app-android-com-app-android-qw-readink` |

商店侧应用标识和 `appId` 的区别：

- iOS 调用 App Store Connect 时使用 App Store Connect App ID，也就是 Apple 的数字 App ID；它和路径里的 `{appId}` 不是同一个字段。
- Android 调用 Google Play 时使用 `storePackageName`；如果没有单独配置，则使用上传 APK 解析出来的 `packageName`。Google service account JSON 里的 `project_id` 只表示 Google Cloud 项目，不指定具体 App。

当前接口有两类行为：

- 只保存到 testflying：导入默认商店页草稿、导入版本草稿、创建自定义产品页面草稿。
- 会连接真实商店：读取商店语言、读取商店文案、读取商店图、同步默认商店页、同步自定义产品页面、查询/创建产品页面优化。

图片上传字段规则：

```text
storeImageFiles__phone_screenshots__{locale}
storeImageFiles__tablet_screenshots__{locale}
storeImageFiles__feature_graphic_url__{locale}
```

兼容 camelCase 素材类型：

```text
storeImageFiles__phoneScreenshots__en-US
storeImageFiles__tabletScreenshots__en-US
storeImageFiles__featureGraphicUrl__en-US
```

上传图片会保存到中心后台对象存储，并按 App 平台校验尺寸和格式。iOS 使用 App Store Connect 截图精确尺寸规则；Android 使用 Google Play 截图和 Feature graphic 规则。

同步类接口和创建产品页面优化接口有限流：

- 同一 token + 开发者账号 + App：`10 次/分钟`
- 同一 token + 开发者账号 + App：`100 次/小时`
- 同一开发者账号同一时间只允许一个直接同步或创建实验请求执行
- `idempotencyKey` 缓存 1 小时，同 key 重试返回同一结果

## 接口总览

| 接口 | 方法 | 是否连接真实商店 | 用途 |
| --- | --- | --- | --- |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-locales` | GET | 是 | 从商店读取 App 支持语言 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-listings` | GET | 是 | 从商店读取当前文案配置 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-images` | GET | 是 | 从商店读取当前截图/商店图配置 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/metadata-content-sets` | POST | 否 | 导入默认商店页文案和截图草稿 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-versions/{version}/draft` | POST | 否 | 导入版本说明和可选文案草稿 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/marketing-pages` | POST | 否 | 创建自定义产品页面草稿 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/sync-runs` | POST | 是 | 同步默认商店页、版本说明、商店图 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/marketing-pages/{pageId}/sync-runs` | POST | 是 | 同步自定义产品页面 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/product-page-optimizations` | GET | 是 | 查询 Apple 产品页面优化实验 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/product-page-optimizations` | POST | 是 | 创建 Apple 产品页面优化实验 |

## 1. 读取商店支持语言

```http
GET /v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-locales?version={version}
```

用途：

- 通过账号 Connector 查询 App Store Connect 或 Google Play 当前 App 支持的语言。
- `version` 可选；不传时读取商店侧默认/当前上下文。

完整 curl：

```bash
curl "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/store-locales?version=$VERSION" \
  -H "Authorization: Bearer $TOKEN"
```

成功响应示例：

```json
{
  "accountId": "ceshi",
  "appId": "app-ios-com-boluchuling-app-lookrva",
  "platform": "ios",
  "version": "1.0.0",
  "locales": ["en-US", "zh-Hant", "fr-FR"]
}
```

## 2. 读取商店文案配置

```http
GET /v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-listings?version={version}
```

用途：

- 通过账号 Connector 查询商店侧已经存在的文案配置。
- iOS 对应 App Store Connect metadata/localization。
- Android 对应 Google Play listings。

完整 curl：

```bash
curl "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/store-listings?version=$VERSION" \
  -H "Authorization: Bearer $TOKEN"
```

成功响应示例：

```json
{
  "accountId": "ceshi",
  "appId": "app-ios-com-boluchuling-app-lookrva",
  "platform": "ios",
  "version": "1.0.0",
  "listings": [
    {
      "locale": "en-US",
      "keywords": "novel,reader,story",
      "promotionalText": "Read better stories every day.",
      "description": "Long store description."
    }
  ]
}
```

## 3. 读取商店图片配置

```http
GET /v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-images?version={version}
```

用途：

- 通过账号 Connector 查询商店侧已经存在的截图/商店图配置。
- iOS 主要对应 iPhone/iPad screenshots。
- Android 对应 phone/tablet screenshots 和 feature graphic。

完整 curl：

```bash
curl "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/store-images?version=$VERSION" \
  -H "Authorization: Bearer $TOKEN"
```

成功响应示例：

```json
{
  "accountId": "ceshi",
  "appId": "app-ios-com-boluchuling-app-lookrva",
  "platform": "ios",
  "version": "1.0.0",
  "locales": [
    {
      "locale": "en-US",
      "phoneScreenshots": [
        {
          "url": "https://example.test/screenshot-1.png",
          "fileName": "screenshot-1.png"
        }
      ],
      "tabletScreenshots": []
    }
  ]
}
```

## 4. 导入默认商店页草稿

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/metadata-content-sets
Content-Type: multipart/form-data
```

用途：

- 保存默认商店页的关键词、宣传文本、描述和商店图草稿。
- 空语言字段会使用 `sourceLocale` 对应内容填充。
- 不调用 Connector，不创建同步记录，不直接同步商店。

完整 curl：

```bash
curl -X POST "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/metadata-content-sets" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'metadata={
    "version": "1.0.0",
    "contentSet": {
      "id": "default",
      "name": "默认上架内容"
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
        }
      },
      {
        "locale": "zh-Hant",
        "keywords": "",
        "promotionalText": "",
        "description": ""
      }
    ]
  }' \
  -F "storeImageFiles__phone_screenshots__en-US=@/path/to/en-US-phone-1.png;type=image/png" \
  -F "storeImageFiles__phone_screenshots__zh-Hant=@/path/to/zh-Hant-phone-1.png;type=image/png"
```

成功响应示例：

```json
{
  "contentSet": {
    "id": "default",
    "name": "默认上架内容"
  },
  "version": "1.0.0",
  "locales": ["en-US", "zh-Hant"],
  "savedDrafts": 2,
  "uploadedAssets": 2,
  "warnings": []
}
```

## 5. 导入版本草稿

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-versions/{version}/draft
Content-Type: application/json
```

用途：

- 保存指定商店版本的版本说明草稿。
- 如果同时传入关键词、宣传文本或描述，也会更新当前默认商店页文案草稿。
- 空语言字段会使用 `sourceLocale` 对应内容填充。
- 不调用 Connector，不创建同步记录，不直接同步商店。

完整 curl：

```bash
curl -X POST "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/store-versions/$VERSION/draft" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "sourceLocale": "en-US",
    "locales": [
      {
        "locale": "en-US",
        "keywords": "novel,reader,story",
        "promotionalText": "Read better stories every day.",
        "description": "Long store description for import testing.",
        "releaseNotes": "Fix bugs"
      },
      {
        "locale": "zh-Hant",
        "keywords": "",
        "promotionalText": "",
        "description": "",
        "releaseNotes": ""
      }
    ]
  }'
```

成功响应示例：

```json
{
  "version": "1.0.0",
  "locales": ["en-US", "zh-Hant"],
  "savedMetadataDrafts": 2,
  "savedReleaseNoteDrafts": 2,
  "warnings": []
}
```

## 6. 创建自定义产品页面草稿

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/marketing-pages
Content-Type: multipart/form-data
```

用途：

- 创建 App Store Connect 自定义产品页面草稿。
- 保存页面名称、Deep Link、各语言宣传文本和截图草稿。
- 当前只支持 iOS App。
- 不调用 Connector，不创建同步记录，不直接同步商店。

完整 curl：

```bash
curl -X POST "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/marketing-pages" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'metadata={
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
        }
      },
      {
        "locale": "zh-Hant",
        "promotionalText": "",
        "storeImages": {}
      }
    ]
  }' \
  -F "storeImageFiles__phone_screenshots__en-US=@/path/to/en-US-phone-1.png;type=image/png" \
  -F "storeImageFiles__phone_screenshots__zh-Hant=@/path/to/zh-Hant-phone-1.png;type=image/png"
```

成功响应示例：

```json
{
  "pageId": "page-xxxxxxxx",
  "pageName": "API 自定义产品页",
  "pageType": "custom_product_page",
  "status": "draft",
  "locales": ["en-US", "zh-Hant"],
  "savedLocales": 2,
  "uploadedAssets": 2,
  "warnings": []
}
```

## 7. 同步默认商店页、商店图和版本说明

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/sync-runs
Content-Type: application/json
```

用途：

- 第三方电脑通过中心后台直接触发真实商店同步。
- 只同步已经保存到中心后台的草稿，不会在本接口里修改草稿内容。
- `metadata` 和 `store_images` 读取当前默认商店页草稿。
- `release_notes` 读取指定 `version` 的版本说明草稿。
- 中心后台会创建同步记录，并通过当前账号 Connector 调用 App Store Connect 或 Google Play。

请求字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `version` | 是 | 商店版本号。同步版本说明时必须和商店侧版本一致 |
| `locales` | 是 | 需要同步的语言列表，不能为空 |
| `scopes` | 否 | 默认 `["metadata", "release_notes", "store_images"]` |
| `actor` | 否 | 操作来源，默认 `api` |
| `idempotencyKey` | 否 | 幂等键，建议第三方电脑必传 |

允许的 `scopes`：

```json
["metadata", "release_notes", "store_images"]
```

完整 curl：

```bash
curl -X POST "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/sync-runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "version": "1.0.0",
    "locales": ["en-US", "zh-Hant"],
    "scopes": ["metadata", "release_notes", "store_images"],
    "actor": "third-party-computer",
    "idempotencyKey": "build-123-store-sync"
  }'
```

成功响应示例：

```json
{
  "status": "succeeded",
  "accountId": "ceshi",
  "appId": "app-ios-com-boluchuling-app-lookrva",
  "version": "1.0.0",
  "pageId": null,
  "scopes": ["metadata", "release_notes", "store_images"],
  "locales": ["en-US", "zh-Hant"],
  "runs": [
    {
      "runId": "sync-xxxx",
      "operation": "update_app_metadata",
      "locale": "en-US",
      "status": "succeeded",
      "errorCode": null,
      "errorSummary": null
    },
    {
      "runId": "sync-yyyy",
      "operation": "update_release_notes",
      "locale": "en-US",
      "status": "succeeded",
      "errorCode": null,
      "errorSummary": null
    }
  ],
  "idempotent": false
}
```

## 8. 同步自定义产品页面

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/marketing-pages/{pageId}/sync-runs
Content-Type: application/json
```

用途：

- 同步已经保存在中心后台的 App Store Connect 自定义产品页面草稿。
- 当前只支持 iOS App。
- `marketing_text` 同步宣传文本。
- `store_images` 同步自定义产品页面截图。

请求字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `locales` | 是 | 需要同步的语言列表，不能为空 |
| `scopes` | 否 | 默认 `["marketing_text", "store_images"]` |
| `actor` | 否 | 操作来源，默认 `api` |
| `idempotencyKey` | 否 | 幂等键，建议第三方电脑必传 |

允许的 `scopes`：

```json
["marketing_text", "store_images"]
```

完整 curl：

```bash
curl -X POST "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/marketing-pages/$PAGE_ID/sync-runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "locales": ["en-US", "zh-Hant"],
    "scopes": ["marketing_text", "store_images"],
    "actor": "third-party-computer",
    "idempotencyKey": "campaign-a-page-sync"
  }'
```

成功响应示例：

```json
{
  "status": "succeeded",
  "accountId": "ceshi",
  "appId": "app-ios-com-boluchuling-app-lookrva",
  "version": "page-xxxxxxxx",
  "pageId": "page-xxxxxxxx",
  "scopes": ["marketing_text", "store_images"],
  "locales": ["en-US", "zh-Hant"],
  "runs": [
    {
      "runId": "sync-zzzz",
      "operation": "update_marketing_page",
      "locale": "en-US",
      "status": "succeeded",
      "errorCode": null,
      "errorSummary": null
    }
  ],
  "idempotent": false
}
```

## 9. 查询产品页面优化实验

```http
GET /v1/store-management/developer-accounts/{accountId}/apps/{appId}/product-page-optimizations
```

用途：

- 查询 App Store Connect 当前 App 的产品页面优化实验列表。
- 当前只支持 iOS App。
- 只读取商店状态，不创建中心后台同步记录，不修改商店内容。

完整 curl：

```bash
curl "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/product-page-optimizations" \
  -H "Authorization: Bearer $TOKEN"
```

成功响应示例：

```json
{
  "accountId": "ceshi",
  "appId": "app-ios-com-boluchuling-app-lookrva",
  "experiments": [
    {
      "id": "123456789",
      "name": "Summer Landing Test",
      "platform": "IOS",
      "state": "PREPARE_FOR_SUBMISSION",
      "trafficProportion": 50,
      "reviewRequired": false,
      "startDate": "",
      "endDate": "",
      "treatments": [
        {
          "id": "987654321",
          "name": "Variant A",
          "appIconName": "",
          "locales": ["en-US", "zh-Hant"]
        }
      ]
    }
  ]
}
```

## 10. 创建产品页面优化实验

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/product-page-optimizations
Content-Type: application/json
```

用途：

- 第三方电脑通过中心后台创建 App Store Connect 产品页面优化实验。
- 当前只支持 iOS App。
- 创建成功后会返回 App Store Connect 生成的实验 ID 和 treatment ID。
- 建议传 `idempotencyKey`，网络重试时中心后台会返回同一份创建结果，避免重复创建。

请求字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 实验名称 |
| `trafficProportion` | 否 | 流量比例，`1-100`，默认 `50` |
| `locales` | 否 | 实验涉及语言 |
| `treatments` | 否 | 变体列表 |
| `idempotencyKey` | 否 | 幂等键 |

完整 curl：

```bash
curl -X POST "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/product-page-optimizations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Summer Landing Test",
    "trafficProportion": 50,
    "locales": ["en-US", "zh-Hant"],
    "idempotencyKey": "ppo-summer-landing-20260629",
    "treatments": [
      {
        "name": "Variant A",
        "locales": ["en-US", "zh-Hant"]
      },
      {
        "name": "Variant B",
        "locales": ["en-US"]
      }
    ]
  }'
```

成功响应示例：

```json
{
  "accountId": "ceshi",
  "appId": "app-ios-com-boluchuling-app-lookrva",
  "experiment": {
    "id": "123456789",
    "name": "Summer Landing Test",
    "platform": "IOS",
    "state": "PREPARE_FOR_SUBMISSION",
    "trafficProportion": 50,
    "reviewRequired": true,
    "startDate": "",
    "endDate": "",
    "treatments": [
      {
        "id": "987654321",
        "name": "Variant A",
        "appIconName": "",
        "locales": ["en-US", "zh-Hant"]
      }
    ]
  },
  "idempotent": false
}
```

## 主动 Connector 协议

这组接口是中心后台和 Windows/Mac 上运行的主动 Connector 之间的内部协议。第三方业务脚本一般不需要直接调用。

主动 Connector 的配置方式是：

- 中心后台保存 `baseUrl=active://...`
- Connector 本机保存中心后台地址、账号 ID 和 connector token
- Connector 主动轮询中心后台任务
- 中心后台需要调用商店时，把 HTTP 方法、路径、请求体下发给 Connector
- Connector 请求真实 App Store Connect / Google Play 后，再把结果回传给中心后台

### 轮询任务

```http
POST /connector-agent/v1/poll
Content-Type: application/json
Authorization: Bearer <connector_auth_token>
```

完整 curl：

```bash
curl -X POST "$BASE_URL/connector-agent/v1/poll" \
  -H "Authorization: Bearer <connector_auth_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "accountId": "738W4ARM22",
    "timeoutSeconds": 25
  }'
```

无任务响应：

```json
{
  "task": null
}
```

有任务响应：

```json
{
  "task": {
    "id": "task-xxxx",
    "method": "GET",
    "path": "/v1/apps/app-ios-com-example/store-listings?developerAccountId=738W4ARM22&platform=ios",
    "headers": {},
    "body": ""
  }
}
```

### 回传任务结果

```http
POST /connector-agent/v1/results
Content-Type: application/json
Authorization: Bearer <connector_auth_token>
```

完整 curl：

```bash
curl -X POST "$BASE_URL/connector-agent/v1/results" \
  -H "Authorization: Bearer <connector_auth_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "accountId": "738W4ARM22",
    "taskId": "task-xxxx",
    "statusCode": 200,
    "body": "{\"status\":\"ok\"}"
  }'
```

成功响应：

```json
{
  "ok": true
}
```

## 错误响应

中心后台业务错误统一返回：

```json
{
  "code": "invalid_static_token",
  "message": "接口 token 不正确",
  "retryable": false
}
```

可重试错误会带 `retryable: true`。限流错误会额外返回 `retryAfterSeconds`：

```json
{
  "code": "rate_limited",
  "message": "同步请求过于频繁，请稍后重试",
  "retryable": true,
  "retryAfterSeconds": 43
}
```

常见错误：

| code | HTTP 状态 | 说明 |
| --- | --- | --- |
| `invalid_static_token` | 401 | `/v1/store-management/*` token 不正确 |
| `invalid_connector_token` | 401 | 主动 Connector token 不正确 |
| `app_not_found` | 404 | 当前开发者账号下没有这个 App |
| `connector_missing` | 422 | 开发者账号没有配置 Connector |
| `connector_call_failed` | 502 | Connector 调用真实商店失败 |
| `store_image_invalid` | 422 | 上传图片尺寸、格式或类型不符合商店要求 |
| `invalid_sync_scopes` | 422 | 同步范围不合法或为空 |
| `locales_required` | 422 | 直接同步接口没有传语言 |
| `account_sync_in_progress` | 409 | 同一个开发者账号已有同步任务执行中 |
| `rate_limited` | 429 | 直接同步或创建实验过于频繁 |
| `unsupported_marketing_page` | 422 | 非 iOS App 调用了自定义产品页面接口 |
| `unsupported_product_page_optimization` | 422 | 非 iOS App 调用了产品页面优化接口 |
