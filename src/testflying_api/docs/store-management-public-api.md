# testflying 商店连接对外 API

本文只给第三方电脑或外部系统调用使用，不包含后台 UI、Connector 内部协议和实现细节。

## 基础信息

- 基础地址：`http://47.90.163.122:8000`
- 鉴权：所有接口都需要请求头 `Authorization: Bearer <TOKEN>`
- `{accountId}`：testflying 开发者账号 ID，例如 `738W4ARM22`
- `{appId}`：testflying 内部 App ID，不是 Apple 数字 App ID，也不是 Android package name
- iOS 调商店时使用后台绑定的 App Store Connect App ID
- Android 调商店时优先使用后台绑定的 `storePackageName`，没有时使用包里解析出的 package name

## 接口总览

| 接口 | 方法 | 是否连接商店 | 用途 |
| --- | --- | --- | --- |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-locales` | GET | 是 | 读取商店支持语言 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-listings` | GET | 是 | 读取商店文案 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-images` | GET | 是 | 读取商店截图 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-releases` | GET | 是 | 读取 Google Play release |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/metadata-content-sets` | POST | 否 | 保存默认商店页草稿 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-versions/{version}/draft` | POST | 否 | 保存版本草稿 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/marketing-pages` | POST | 否 | 创建自定义产品页面草稿 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/sync-runs` | POST | 是 | 同步默认商店页 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/marketing-pages/{pageId}/sync-runs` | POST | 是 | 同步自定义产品页面 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/product-page-optimizations` | GET | 是 | 查询产品页面优化 |
| `/v1/store-management/developer-accounts/{accountId}/apps/{appId}/product-page-optimizations` | POST | 是 | 创建产品页面优化 |

## 1. 读取商店支持语言

```http
GET /v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-locales
```

用于读取 App Store Connect 或 Google Play 当前 App 支持的语言。

参数：

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `accountId` | path | 是 | 开发者账号 ID |
| `appId` | path | 是 | testflying 内部 App ID |
| `version` | query | 否 | 商店版本上下文 |

```bash
curl "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/store-locales" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "accountId": "738W4ARM22",
  "appId": "app-ios-com-app-qw-readink",
  "platform": "ios",
  "version": "",
  "locales": ["en-US", "zh-Hant"]
}
```

## 2. 读取商店文案

```http
GET /v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-listings
```

用于读取商店侧已存在的描述、宣传文本、关键词等文案。

参数：

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `accountId` | path | 是 | 开发者账号 ID |
| `appId` | path | 是 | testflying 内部 App ID |
| `version` | query | 否 | 商店版本上下文 |

```bash
curl "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/store-listings" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "accountId": "738W4ARM22",
  "appId": "app-ios-com-app-qw-readink",
  "platform": "ios",
  "listings": [
    {
      "locale": "en-US",
      "promotionalText": "Read better stories every day.",
      "description": "Long store description."
    }
  ]
}
```

## 3. 读取商店截图

```http
GET /v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-images
```

用于读取商店侧当前截图。iOS 返回 iPhone/iPad 截图；Android 返回 phone/tablet 截图和 feature graphic。

参数：

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `accountId` | path | 是 | 开发者账号 ID |
| `appId` | path | 是 | testflying 内部 App ID |
| `version` | query | 否 | 商店版本上下文 |

```bash
curl "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/store-images" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "accountId": "738W4ARM22",
  "appId": "app-ios-com-app-qw-readink",
  "platform": "ios",
  "locales": [
    {
      "locale": "en-US",
      "images": {
        "phone_screenshots": [
          {
            "fileName": "01.png",
            "url": "https://example.test/01.png"
          }
        ]
      }
    }
  ]
}
```

## 4. 读取 Google Play Release

```http
GET /v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-releases
```

用于读取 Google Play tracks、releases 和 versionCodes。同步 Android 版本说明前，可以先用这个接口确定 `storeTrack` 和 `storeVersionCode`。

参数：

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `accountId` | path | 是 | 开发者账号 ID |
| `appId` | path | 是 | testflying 内部 Android App ID |
| `version` | query | 否 | 查询上下文 |

```bash
curl "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/store-releases" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "accountId": "738W4ARM22",
  "appId": "app-android-com-app-android-qw-readink",
  "platform": "android",
  "releases": [
    {
      "track": "production",
      "status": "completed",
      "versionCodes": ["10013404"],
      "releaseNotes": []
    }
  ]
}
```

## 5. 保存默认商店页草稿

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/metadata-content-sets
```

用于把默认商店页文案和截图保存到 testflying，不会同步到真实商店。

参数：

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `accountId` | path | 是 | 开发者账号 ID |
| `appId` | path | 是 | testflying 内部 App ID |
| `sourceLocale` | form | 否 | 源语言，默认 `en-US` |
| `locales` | form | 是 | 语言列表，多个值逗号分隔 |
| `promotionalText__{locale}` | form | 否 | 指定语言宣传文本 |
| `description__{locale}` | form | 是 | 指定语言描述 |
| `storeImageFiles__phoneScreenshots__{locale}` | file | 否 | 手机截图 |
| `storeImageFiles__tabletScreenshots__{locale}` | file | 否 | 平板截图 |
| `storeImageFiles__featureGraphicUrl__{locale}` | file | 否 | Android feature graphic |

```bash
curl -X POST "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/metadata-content-sets" \
  -H "Authorization: Bearer $TOKEN" \
  -F "sourceLocale=en-US" \
  -F "locales=en-US,zh-Hant" \
  -F "description__en-US=Long store description"
```

```json
{
  "contentSetId": "default",
  "contentSetName": "默认上架内容",
  "locales": ["en-US", "zh-Hant"],
  "savedLocales": 2,
  "uploadedAssets": 0,
  "warnings": []
}
```

## 6. 保存版本草稿

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-versions/{version}/draft
```

用于保存指定版本的版本说明，也可以同时保存默认商店页文案草稿。不会同步到真实商店。

参数：

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `accountId` | path | 是 | 开发者账号 ID |
| `appId` | path | 是 | testflying 内部 App ID |
| `version` | path | 是 | 商店版本号 |
| `sourceLocale` | body | 否 | 源语言，默认 `en-US` |
| `locales` | body | 是 | 语言列表 |
| `metadataByLocale` | body | 否 | 各语言宣传文本和描述 |
| `releaseNotesByLocale` | body | 否 | 各语言版本说明 |

```bash
curl -X POST "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/store-versions/$VERSION/draft" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"locales":["en-US"],"releaseNotesByLocale":{"en-US":"Fix bugs"}}'
```

```json
{
  "version": "1.0.0",
  "locales": ["en-US"],
  "savedMetadataDrafts": 0,
  "savedReleaseNoteDrafts": 1,
  "warnings": []
}
```

## 7. 创建自定义产品页面草稿

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/marketing-pages
```

用于创建 App Store Connect 自定义产品页面草稿，不会同步到真实商店。

参数：

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `accountId` | path | 是 | 开发者账号 ID |
| `appId` | path | 是 | testflying 内部 iOS App ID |
| `pageName` | form | 是 | 页面名称 |
| `sourceLocale` | form | 否 | 源语言，默认 `en-US` |
| `locales` | form | 是 | 语言列表，多个值逗号分隔 |
| `promotionalText__{locale}` | form | 否 | 页面宣传文本 |
| `storeImageFiles__phoneScreenshots__{locale}` | file | 否 | 手机截图 |
| `storeImageFiles__tabletScreenshots__{locale}` | file | 否 | 平板截图 |

```bash
curl -X POST "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/marketing-pages" \
  -H "Authorization: Bearer $TOKEN" \
  -F "pageName=Campaign A" \
  -F "locales=en-US" \
  -F "promotionalText__en-US=Campaign copy"
```

```json
{
  "pageId": "page-xxxx",
  "pageName": "Campaign A",
  "status": "draft",
  "locales": ["en-US"],
  "savedLocales": 1,
  "uploadedAssets": 0,
  "warnings": []
}
```

## 8. 同步默认商店页

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/sync-runs
```

用于把默认商店页草稿同步到真实商店。可同步文案、商店图、版本说明。

参数：

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `accountId` | path | 是 | 开发者账号 ID |
| `appId` | path | 是 | testflying 内部 App ID |
| `version` | body | 是 | 商店版本号 |
| `locales` | body | 是 | 需要同步的语言 |
| `scopes` | body | 否 | 默认 `["metadata","release_notes","store_images"]` |
| `storeTrack` | body | 否 | Android 版本说明目标轨道 |
| `storeVersionCode` | body | 否 | Android 版本说明目标 versionCode |
| `actor` | body | 否 | 操作来源 |
| `idempotencyKey` | body | 否 | 幂等键 |

```bash
curl -X POST "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/sync-runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"version":"1.0.0","locales":["en-US"],"scopes":["metadata","release_notes","store_images"],"idempotencyKey":"sync-001"}'
```

```json
{
  "status": "succeeded",
  "accountId": "738W4ARM22",
  "appId": "app-ios-com-app-qw-readink",
  "version": "1.0.0",
  "scopes": ["metadata", "release_notes", "store_images"],
  "locales": ["en-US"],
  "runs": [],
  "idempotent": false
}
```

## 9. 同步自定义产品页面

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/marketing-pages/{pageId}/sync-runs
```

用于把指定自定义产品页面草稿同步到 App Store Connect。

参数：

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `accountId` | path | 是 | 开发者账号 ID |
| `appId` | path | 是 | testflying 内部 iOS App ID |
| `pageId` | path | 是 | 自定义产品页面 ID |
| `locales` | body | 是 | 需要同步的语言 |
| `scopes` | body | 否 | 默认 `["marketing_text","store_images"]` |
| `actor` | body | 否 | 操作来源 |
| `idempotencyKey` | body | 否 | 幂等键 |

```bash
curl -X POST "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/marketing-pages/$PAGE_ID/sync-runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"locales":["en-US"],"scopes":["marketing_text","store_images"],"idempotencyKey":"page-sync-001"}'
```

```json
{
  "status": "succeeded",
  "pageId": "page-xxxx",
  "scopes": ["marketing_text", "store_images"],
  "locales": ["en-US"],
  "runs": [],
  "idempotent": false
}
```

## 10. 查询产品页面优化

```http
GET /v1/store-management/developer-accounts/{accountId}/apps/{appId}/product-page-optimizations
```

用于查询 App Store Connect 产品页面优化实验。

参数：

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `accountId` | path | 是 | 开发者账号 ID |
| `appId` | path | 是 | testflying 内部 iOS App ID |

```bash
curl "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/product-page-optimizations" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "accountId": "738W4ARM22",
  "appId": "app-ios-com-app-qw-readink",
  "experiments": []
}
```

## 11. 创建产品页面优化

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/product-page-optimizations
```

用于创建 App Store Connect 产品页面优化实验。

参数：

| 参数 | 位置 | 必填 | 说明 |
| --- | --- | --- | --- |
| `accountId` | path | 是 | 开发者账号 ID |
| `appId` | path | 是 | testflying 内部 iOS App ID |
| `name` | body | 是 | 实验名称 |
| `trafficProportion` | body | 否 | 流量比例，默认 `50` |
| `locales` | body | 否 | 实验语言 |
| `treatments` | body | 是 | 实验变体 |
| `idempotencyKey` | body | 否 | 幂等键 |

```bash
curl -X POST "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/product-page-optimizations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Landing Test","trafficProportion":50,"locales":["en-US"],"treatments":[{"name":"Variant A"}],"idempotencyKey":"ppo-001"}'
```

```json
{
  "accountId": "738W4ARM22",
  "appId": "app-ios-com-app-qw-readink",
  "experiment": {
    "id": "ppo-xxxx",
    "name": "Landing Test",
    "state": "PREPARE_FOR_SUBMISSION"
  },
  "idempotent": false
}
```

## 错误格式

```json
{
  "code": "invalid_static_token",
  "message": "接口 token 不正确",
  "retryable": false
}
```
