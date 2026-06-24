# 商店管理对外接口

本文档描述 `testflying-server` 当前保留的商店管理对外 API。接口只把数据保存到
testflying 中心后台，不会直接同步到 App Store Connect 或 Google Play Console。

## 基础信息

示例中的线上地址和测试 token：

```bash
BASE_URL="http://47.90.163.122:8000"
TOKEN="dev-token"
ACCOUNT_ID="ceshi"
APP_ID="app-ios-com-boluchuling-app-lookrva"
```

所有接口都需要静态 token：

```http
Authorization: Bearer <TESTFLYING_STATIC_TOKEN>
```

图片上传字段规则：

```text
storeImageFiles__phone_screenshots__{locale}
storeImageFiles__tablet_screenshots__{locale}
storeImageFiles__feature_graphic_url__{locale}
```

图片字段的素材类型也兼容 camelCase，例如：

```text
storeImageFiles__phoneScreenshots__en-US
storeImageFiles__tabletScreenshots__en-US
storeImageFiles__featureGraphicUrl__en-US
```

上传图片会保存到当前对象存储后端，并按 App 平台校验尺寸和格式。iOS 使用
App Store Connect 截图精确尺寸规则，Android 使用 Google Play 截图和
Feature graphic 规则。

## 1. 导入默认商店页文案和截图草稿

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/metadata-content-sets
Content-Type: multipart/form-data
```

用途：

- 保存默认商店页的关键词、宣传文本、描述和商店图草稿。
- 空语言字段会使用 `sourceLocale` 对应内容填充。
- 不调用 connector，不创建同步记录，不直接同步商店。

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

## 2. 导入版本草稿

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-versions/{version}/draft
Content-Type: application/json
```

用途：

- 保存指定商店版本的版本说明草稿。
- 如果同时传入关键词、宣传文本或描述，也会更新当前默认商店页文案草稿。
- 空语言字段会使用 `sourceLocale` 对应内容填充。
- 不调用 connector，不创建同步记录，不直接同步商店。

完整 curl：

```bash
curl -X POST "$BASE_URL/v1/store-management/developer-accounts/$ACCOUNT_ID/apps/$APP_ID/store-versions/1.0.0/draft" \
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

## 3. 创建自定义产品页面并导入内容

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/marketing-pages
Content-Type: multipart/form-data
```

用途：

- 创建 App Store Connect 自定义产品页面草稿。
- 保存页面名称、Deep Link、各语言宣传文本和截图草稿。
- 当前只支持 iOS App。
- 不调用 connector，不创建同步记录，不直接同步商店。

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

## 错误响应

未传或传错 token：

```json
{
  "code": "invalid_static_token",
  "message": "接口 token 不正确"
}
```

App 不属于当前开发者账号：

```json
{
  "code": "app_not_found",
  "message": "当前开发者账号下没有这个 App"
}
```

图片尺寸或格式不符合商店要求：

```json
{
  "code": "store_image_invalid",
  "message": "en-US phone.png: Apple 要求精确尺寸..."
}
```

metadata JSON 不合法：

```json
{
  "code": "invalid_metadata",
  "message": "metadata JSON 格式不正确：..."
}
```
