from __future__ import annotations

import json

from fastapi.testclient import TestClient

from testflying_api.app_logs import UNKNOWN_TOKEN, parse_log_line
from tests.test_admin import _admin_headers


def test_parse_log_line_extracts_key_values_and_quoted_values() -> None:
    parsed = parse_log_line(
        '2026-06-18 12:00:00.123 级别=错误 标签=腾讯播放器 事件=播放器日志 '
        '消息=播放章节 章节序号=3 错误="timeout error = wait" 起播进度=0ms'
    )

    assert parsed.timestamp == "2026-06-18 12:00:00.123"
    assert parsed.level == "错误"
    assert parsed.tag == "腾讯播放器"
    assert parsed.event == "播放器日志"
    assert parsed.message == "播放章节"
    assert parsed.fields == [
        {"key": "章节序号", "value": "3"},
        {"key": "错误", "value": "timeout error = wait"},
        {"key": "起播进度", "value": "0ms"},
    ]


def test_app_log_websocket_groups_logs_by_token(client: TestClient) -> None:
    with client.websocket_connect("/push?token=device-fixed-id") as websocket:
        websocket.send_text(
            json.dumps(
                {
                    "type": "hello",
                    "protocol": 1,
                    "deviceId": "device-fixed-id",
                    "device": "Pixel 8",
                    "platform": "android",
                    "sentAt": "2026-06-18T12:00:00.000",
                }
            )
        )
        websocket.send_text(
            json.dumps(
                {
                    "type": "logs",
                    "history": True,
                    "lines": [
                        "2026-06-18 12:00:00.123 级别=信息 标签=腾讯播放器 "
                        "事件=播放器日志 消息=播放章节 章节序号=3 起播进度=0ms"
                    ],
                    "sentAt": "2026-06-18T12:00:00.000",
                }
            )
        )
        websocket.send_text(
            json.dumps(
                {
                    "type": "client_error",
                    "message": "读取历史日志失败",
                    "sentAt": "2026-06-18T12:00:01.000",
                }
            )
        )

        response = client.get("/admin/app-logs/events", headers=_admin_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["devices"][0]["token"] == "device-fixed-id"
    assert payload["devices"][0]["device"] == "Pixel 8"
    assert payload["devices"][0]["connected"] is True
    assert payload["logs"][0]["token"] == "device-fixed-id"
    assert payload["logs"][0]["history"] is True
    assert payload["logs"][0]["level"] == "信息"
    assert payload["logs"][0]["message"] == "播放章节"
    assert payload["logs"][0]["fields"] == [
        {"key": "章节序号", "value": "3"},
        {"key": "起播进度", "value": "0ms"},
    ]
    assert payload["errors"][0]["message"] == "读取历史日志失败"


def test_app_log_websocket_allows_missing_token(client: TestClient) -> None:
    with client.websocket_connect("/push") as websocket:
        websocket.send_text(
            json.dumps(
                {
                    "type": "logs",
                    "history": False,
                    "lines": ["2026-06-18 12:00:00.123 级别=警告 消息=无token"],
                }
            )
        )
        response = client.get("/admin/app-logs/events", headers=_admin_headers())

    assert response.status_code == 200
    assert response.json()["devices"][0]["token"] == UNKNOWN_TOKEN
    assert response.json()["devices"][0]["knownToken"] is False
    assert response.json()["logs"][0]["token"] == UNKNOWN_TOKEN


def test_admin_app_logs_page_and_qr_render(client: TestClient) -> None:
    page = client.get("/admin/app-logs", headers=_admin_headers())
    qr = client.get(
        "/admin/app-logs/qr.svg?host=192.168.1.23&port=18080&name=Mac",
        headers=_admin_headers(),
    )

    assert page.status_code == 200
    assert "App 日志" in page.text
    assert "ws://" in page.text
    assert "/push?token=&lt;设备ID&gt;" in page.text
    assert "/app-logs/connect" in page.text
    assert "anystories:///connect" in page.text
    assert "data-app-log-list" in page.text
    assert "syncAppLogConnectedLayout" in page.text
    assert "syncAppLogStickyOffsets" in page.text
    assert "is-compact" in page.text
    assert "window.addEventListener('scroll'" in page.text
    assert qr.status_code == 200
    assert qr.headers["content-type"].startswith("image/svg+xml")


def test_admin_app_logs_connected_layout_styles(client: TestClient) -> None:
    response = client.get("/static/admin/admin.css")

    assert response.status_code == 200
    assert ".app-log-connect-panel.is-connected" in response.text
    assert ".app-log-connect-panel.is-compact" in response.text
    assert "position: sticky" in response.text
    assert "--app-log-sticky-offset" in response.text
    assert "grid-template-columns: 240px minmax(0, 1fr)" in response.text
    assert "min-height: calc(100vh - 188px)" in response.text


def test_app_log_mobile_connect_page_is_public_and_opens_app_scheme(client: TestClient) -> None:
    page = client.get("/app-logs/connect?host=192.168.1.23&port=18080&name=Mac")

    assert page.status_code == 200
    assert "AnyStories" in page.text
    assert "打开 AnyStories 并连接" in page.text
    assert "192.168.1.23:18080" in page.text
    assert "anystories:///connect?host=192.168.1.23&amp;port=18080&amp;name=Mac" in page.text
