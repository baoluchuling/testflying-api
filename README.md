# testflying-api

`testflying-api` 是 `testflying` 内部应用分发客户端的后端 API 项目。当前仓库先提供最小 FastAPI 骨架，用来承接客户端已经定义好的 workspace 聚合接口。

## 当前能力

- `GET /health`：服务健康检查。
- `GET /v1/test-distribution/workspace`：返回客户端首屏需要的 workspace 快照结构。
- 请求上下文预留 `Authorization`、`X-Device-ID`、`X-Client-Platform`。

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
- 应用、构建、安装任务。
- 设备登记和设备池。
- 开发者账号续费提醒。
- 通知列表和已读状态。
- 用户维度手动排序。

客户端契约参考 `testflying` 仓库的 `docs/api-contract.md`。
