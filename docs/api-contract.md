# testflying-api 接口契约

本文档描述服务端第一版已经实现的 API。服务端只保存内部应用分发事实，不保存安装状态、下载进度、暂停状态、用户手动排序和通知已读状态。

## 请求上下文

常规客户端请求携带：

```http
Authorization: Bearer <token>
X-Device-ID: <registered-device-id>
X-Client-Platform: ios
```

当前版本预留 token 上下文，但还没有接入正式登录态。设备可见性由 `X-Device-ID` 和服务端设备登记事实决定。

## 健康检查

```http
GET /health
```

响应：

```json
{"status":"ok"}
```

## Workspace 快照

```http
GET /v1/test-distribution/workspace
```

响应顶层结构：

```json
{
  "apps": [],
  "builds": [],
  "devices": [],
  "developerAccounts": [],
  "notifications": [],
  "installTasks": [],
  "sortOrder": {
    "buildIds": []
  },
  "profile": {}
}
```

规则：

- `apps` 和 `builds` 只包含当前设备和平台可见的分发事实。
- `builds[].installInfo.installUrl` 是客户端点击安装时打开的地址。
- iOS 构建的 `installUrl` 使用 `itms-services://?action=download-manifest&url=<manifest>`。
- Android 构建的 `installUrl` 直接指向 APK 下载地址。
- `installTasks` 永远返回空数组。
- `sortOrder.buildIds` 永远返回空数组。
- 通知对象不包含 `isRead` 或 `readAt`。

## 上传包

```http
POST /v1/test-distribution/uploads
Content-Type: multipart/form-data
```

表单字段：

- `file`：IPA 或 APK。
- `platform`：`ios` 或 `android`。
- `environment`：`development` 或 `production`。
- `changelog`：可选更新说明。
- `appName`：可选，仅用于覆盖服务端解析出的应用名称。
- `developerAccountId`：可选，上传后把新 App 或未绑定 App 归属到指定开发者账号。
- `storeAppId`：可选，Apple App Store Connect App ID。
- `storePackageName`：可选，Google Play package 或备用商店包名。

iOS 上传会从 IPA 的 `Payload/*.app/Info.plist` 解析 bundle id、应用名、版本号和 build number。Android 上传会从 APK 的 binary manifest 和资源表解析 package name、应用名、version name 和 version code。

上传成功后服务端会：

- 根据 bundle id 或 package name 加平台 upsert 应用。
- 如果传入 `developerAccountId`，校验账号存在；如果 App 已绑定其他账号，则拒绝上传，避免静默改绑。
- 创建构建。
- 保存 IPA/APK 制品。
- iOS 额外生成 `manifest.plist`。
- 创建一条 `build` 类型通知。
- 给同平台已登记设备创建构建可见性。

`installUrl`、`manifestUrl` 和 `downloadUrl` 在上传时由当前部署的公开 URL 配置生成。S3/MinIO 部署依赖 `TESTFLYING_S3_PUBLIC_BASE_URL`，本地文件部署依赖 `TESTFLYING_PUBLIC_BASE_URL`。这些 URL 写入数据库后不会随环境变量自动变化。

上传不会创建安装任务，也不会记录某台设备是否安装过该构建。

## 导入商店版本草稿

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-versions/{version}/draft
Authorization: Bearer <TESTFLYING_STATIC_TOKEN>
Content-Type: application/json
```

这个接口给内部脚本、CI 或内容生成工具使用。它只把某个商店版本的文案元数据和版本说明保存到
testflying 草稿，不调用 connector，不做商店版本预检查，也不同步到 App Store Connect 或
Google Play Console。

请求体示例：

```json
{
  "sourceLocale": "en-US",
  "locales": [
    {
      "locale": "en-US",
      "keywords": "novel,reader,story",
      "promotionalText": "Read better stories every day.",
      "description": "Long store description.",
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
}
```

如果某个语言的 `keywords`、`promotionalText`、`description` 或 `releaseNotes` 为空，会使用
`sourceLocale` 对应内容填充。只传版本说明时可以不传文案元数据；如果传了文案元数据，
`description` 最终不能为空，否则返回 `422`。

成功响应：

```json
{
  "version": "1.0.0",
  "locales": ["en-US", "zh-Hant"],
  "savedMetadataDrafts": 2,
  "savedReleaseNoteDrafts": 2,
  "warnings": []
}
```

这个接口不会创建 `store_sync_runs` 记录。后续需要同步到商店时，仍然从管理后台打开对应
App 的商店管理页面，选择版本内容后执行预检查、确认清单和同步。

## 导入商店图套件

```http
POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/store-image-suites
Authorization: Bearer <TESTFLYING_STATIC_TOKEN>
Content-Type: multipart/form-data
```

这个接口用于上传 App 级商店图套件。商店图套件和商店版本平行，不挂到具体版本；第一版不做
AB 实验，只保存多套可选截图方案，后续同步时由后台选择要搭配的套件。

表单字段：

- `metadata`：必填，JSON 字符串。
- `storeImageFiles__phone_screenshots__{locale}`：可选，当前语言的手机截图，支持多文件。
- `storeImageFiles__tablet_screenshots__{locale}`：可选，当前语言的平板截图，支持多文件。
- `storeImageFiles__feature_graphic_url__{locale}`：可选，当前语言的 Google Play 功能宣传图。

图片字段的素材类型也兼容 camelCase，例如
`storeImageFiles__phoneScreenshots__en-US`。上传图片会保存到当前对象存储后端，并按 App
平台校验尺寸和格式：iOS 使用 App Store Connect 截图精确尺寸规则，Android 使用 Google Play
截图和 Feature graphic 规则。

`metadata` 示例：

```json
{
  "imageSuite": {
    "id": "summer-a",
    "name": "暑期截图方案 A"
  },
  "source": "api",
  "sourceLocale": "en-US",
  "locales": [
    {
      "locale": "en-US",
      "storeImages": {
        "phoneScreenshots": [
          "https://cdn.example.test/source-phone.png"
        ]
      }
    },
    {
      "locale": "zh-Hant",
      "storeImages": {}
    }
  ]
}
```

如果某个语言的商店图为空，会使用 `sourceLocale` 对应内容填充。

成功响应：

```json
{
  "imageSuite": {
    "id": "summer-a",
    "name": "暑期截图方案 A"
  },
  "locales": ["en-US", "zh-Hant"],
  "savedLocales": 2,
  "uploadedAssets": 3,
  "warnings": []
}
```

兼容入口 `POST /v1/store-management/developer-accounts/{accountId}/apps/{appId}/metadata-content-sets`
仍然保留给旧调用方使用，但新接入应使用上面两个拆分后的接口。

## 管理后台

```http
GET /admin
GET /admin/uploads
POST /admin/uploads
GET /admin/apps
GET /admin/builds
GET /admin/devices
GET /admin/developer-accounts
GET /admin/developer-accounts/new
POST /admin/developer-accounts
GET /admin/developer-accounts/{accountId}
GET /admin/developer-accounts/{accountId}/edit
POST /admin/developer-accounts/{accountId}
POST /admin/developer-accounts/{accountId}/connector
POST /admin/developer-accounts/{accountId}/connector/check
POST /admin/developer-accounts/{accountId}/apps
POST /admin/developer-accounts/{accountId}/apps/{appId}/settings
POST /admin/developer-accounts/{accountId}/apps/{appId}/unbind
GET /admin/developer-accounts/{accountId}/apps/{appId}/store-metadata
POST /admin/developer-accounts/{accountId}/apps/{appId}/store-metadata
POST /admin/developer-accounts/{accountId}/apps/{appId}/store-metadata/preflight
POST /admin/developer-accounts/{accountId}/apps/{appId}/store-metadata/sync
GET /admin/developer-accounts/{accountId}/apps/{appId}/release-notes
POST /admin/developer-accounts/{accountId}/apps/{appId}/release-notes
POST /admin/developer-accounts/{accountId}/apps/{appId}/release-notes/sync
GET /admin/notifications
```

管理后台是给内部管理员使用的 server-side HTML 页面。它使用 HTTP Basic 认证：

- 用户名：`TESTFLYING_ADMIN_USERNAME`，默认 `admin`。
- 密码：复用 `TESTFLYING_STATIC_TOKEN`。

后台上传表单复用 `POST /v1/test-distribution/uploads` 的业务逻辑，上传成功后同样会创建应用、构建、制品、iOS manifest 和通知。后台页面使用浏览器上传进度事件展示上传百分比；服务端收到完整文件后再解析包信息和写入数据库。MinIO Console 只管理对象存储文件，不能替代管理后台上传，因为直接上传到 MinIO 不会写入业务数据库。

开发者账号后台支持新增/编辑账号、配置账号级 connector、检查 connector 连接状态、绑定/解绑 App、维护 App 商店标识，并在账号上下文中同步版本说明和商店元数据。每个开发者账号只能有一个 connector，保存后只能编辑原 connector；账号详情页进入时会自动检查一次连接状态。App 商店标识按平台收窄：iOS 只填 App Store Connect App ID，Android 只填 Google Play package name。商店元数据支持多语言编辑，语言列表只使用 connector 从商店 App 拉取的实际支持语言；页面默认优先使用 `en-US` 作为源文案语言，并按 App 平台展示术语：iOS 显示 App Store Connect 的 `Keywords`、`Promotional Text`、`Description`、`iPhone screenshots` 和 `iPad screenshots`；Android 显示 Google Play 的 `Full description`、`Feature graphic`、`Phone screenshots` 和 `Tablet screenshots`。标题、副标题、隐私政策 URL、支持 URL、营销 URL、App 图标和素材备注当前不支持设置。商店元数据和商店图按 App 级当前草稿保存，不再跟随版本；版本说明继续按商店版本保存。同步到商店前必须填写目标版本，并显式勾选同步范围：文案元数据、版本说明、商店图可以单独同步或组合同步。后台会把图片保存到对象存储，后续同步时将勾选的商店图放入 payload 的 `metadata.storeImages` 传给 connector。页面会保存同步历史快照，按版本、同步时间、语言、同步范围和状态展示。Apple App 额外提供营销页面控制台，自定义产品页面和产品页面优化独立于 App 版本，可以创建多个页面。商店同步页面进入时会自动预检查；相同账号、App、平台、版本、语言和操作的预检查结果缓存 5 分钟；商店元数据页的实时查询按钮可以绕过 5 分钟缓存，但同一请求 1 分钟内只允许触发一次；同步前中心后台会按平台校验商店文案字段长度和图片尺寸，校验失败时不调用 connector。商店侧截图上传适配由 connector 后续消费 `metadata.storeImages` 完成；connector 是独立 Go 服务，支持 Linux、macOS 和 Windows 单二进制运行，也支持 Docker 镜像部署；生产环境使用 `TESTFLYING_CONNECTOR_STORE_MODE=live` 并在 connector 部署机器挂载 Apple `.p8` 或 Google service account JSON；中心后台不保存这些商店凭据。

## 设备

```http
GET /v1/test-distribution/devices/current
GET /v1/test-distribution/devices
POST /v1/test-distribution/devices/registration-link
```

`devices/current` 在设备未登记时返回：

```json
{
  "code": "device_not_registered",
  "message": "当前设备未登记",
  "retryable": false
}
```

`registration-link` 只生成登记请求，不自动审批设备，也不授予构建可见性。

## 开发者账号续费

```http
GET /v1/test-distribution/developer-accounts
GET /v1/test-distribution/developer-accounts/renewals
```

账号响应包含：

- `expiresAt`
- `status`
- `appIds`
- `remainingDays`
- `renewalActionLabel`

账号提醒是服务端事实。客户端是否关闭提醒、如何展示横幅、滚动位置等都由客户端本地处理。

## 通知 Feed

```http
GET /v1/test-distribution/notifications
GET /v1/test-distribution/notifications?type=build
GET /v1/test-distribution/notifications?type=account
GET /v1/test-distribution/notifications?type=device
```

通知类型：

- `build`
- `account`
- `device`

服务端没有通知已读写接口，不实现：

- `PATCH /v1/test-distribution/notifications/{notificationId}`
- `POST /v1/test-distribution/notifications/mark-all-read`

## 已删除的用户态接口

服务端第一版不实现这些旧接口：

- `POST /v1/test-distribution/builds/{buildId}/install-tasks`
- `PATCH /v1/test-distribution/install-tasks/{taskId}`
- `GET /v1/test-distribution/install-tasks/{taskId}`
- `PUT /v1/test-distribution/users/me/build-sort-order`
- `PATCH /v1/test-distribution/notifications/{notificationId}`
- `POST /v1/test-distribution/notifications/mark-all-read`

这些能力属于客户端状态：安装中、暂停、下载进度、手动排序和通知已读由移动端本地保存。
