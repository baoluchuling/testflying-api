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
- `packageName`：Android 必填。
- `appName`：Android 必填。
- `version`：Android 必填。
- `buildNumber`：Android 必填。

iOS 上传会从 IPA 的 `Payload/*.app/Info.plist` 解析 bundle id、应用名、版本号和 build number。Android 第一版不解析二进制 APK，必须由上传方提供 metadata。

上传成功后服务端会：

- 根据 bundle id 或 package name 加平台 upsert 应用。
- 创建构建。
- 保存 IPA/APK 制品。
- iOS 额外生成 `manifest.plist`。
- 创建一条 `build` 类型通知。
- 给同平台已登记设备创建构建可见性。

上传不会创建安装任务，也不会记录某台设备是否安装过该构建。

## 管理后台

```http
GET /admin
GET /admin/uploads
POST /admin/uploads
GET /admin/apps
GET /admin/builds
GET /admin/devices
GET /admin/developer-accounts
GET /admin/notifications
```

管理后台是给内部管理员使用的 server-side HTML 页面。它使用 HTTP Basic 认证：

- 用户名：`TESTFLYING_ADMIN_USERNAME`，默认 `admin`。
- 密码：复用 `TESTFLYING_STATIC_TOKEN`。

后台上传表单复用 `POST /v1/test-distribution/uploads` 的业务逻辑，上传成功后同样会创建应用、构建、制品、iOS manifest 和通知。MinIO Console 只管理对象存储文件，不能替代管理后台上传，因为直接上传到 MinIO 不会写入业务数据库。

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
