from __future__ import annotations

import argparse
import base64
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.request import Request, urlopen


@dataclass
class PageAssets:
    css_href: str | None = None


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.assets = PageAssets()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "link":
            return
        values = dict(attrs)
        if values.get("rel") == "stylesheet" and ".css" in values.get("href", ""):
            self.assets.css_href = values["href"]


def fetch_text(url: str, username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    request = Request(url, headers={"Authorization": f"Basic {token}"})
    with urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify admin store metadata UI contract.")
    parser.add_argument(
        "--url",
        default=(
            "http://127.0.0.1:8000/admin/developer-accounts/ceshi/"
            "apps/app-ios-com-boluchuling-app-lookrva/store-metadata"
        ),
    )
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="dev-token")
    args = parser.parse_args()

    failures: list[str] = []
    html = fetch_text(args.url, args.username, args.password)
    asset_parser = AssetParser()
    asset_parser.feed(html)
    css_href = asset_parser.assets.css_href

    require(css_href is not None, "admin css link is missing", failures)
    require(bool(css_href and "?v=" in css_href), "admin css link is not versioned", failures)

    for marker in (
        "store-metadata-main",
        "metadata-control-strip",
        "card toolbar metadata-control-strip",
        "metadata-toolbar-left",
        "metadata-refresh-button",
        "metadata-focus-workspace",
        "workspace metadata-focus-workspace",
        "metadata-sync-rail",
        "card rail metadata-sync-rail",
        "sync-item metadata-sync-item",
        "metadata-focus-panel",
        "metadata-current-editor",
        "data-current-metadata-editor",
        "metadata-locale-tag",
        "locale-row metadata-locale-input metadata-focus-locale-row",
        "metadata-side-status",
        "side metadata-side-status",
        "metadata-side-summary-card",
        "metadata-check-list",
        "最近同步记录",
        "store-image-count",
        "data-sync-item-select",
        "data-sync-item-panel",
    ):
        require(marker in html, f"page is missing {marker}", failures)
    for label in ("关键词", "宣传文本", "描述", "手机截图", "平板截图"):
        require(label in html, f"page is missing short label {label}", failures)

    css_url = urljoin(args.url, css_href or "/static/admin/admin.css")
    css = fetch_text(css_url, args.username, args.password)
    css_contracts = {
        "store metadata main width matches demo frame": (
            r"\.store-metadata-main\s*\{[^}]*max-width:\s*1262px"
        ),
        "control strip is a left-right toolbar": (
            r"\.metadata-control-strip\s*\{[^}]*justify-content:\s*space-between"
        ),
        "content set picker is demo sized": (
            r"\.metadata-toolbar-left\s+\.content-set-picker\s*\{[^}]*width:\s*184px"
        ),
        "sync item keeps title readable": (
            r"\.metadata-sync-item\s*\{[^}]*grid-template-columns:"
            r"\s*26px\s+minmax\(74px,\s*1fr\)\s*8px\s*auto\s*14px"
        ),
        "focus card aligns content to top": (
            r"\.metadata-focus-card\s*\{[^}]*align-content:\s*start"
        ),
        "current editor stays in first viewport": (
            r"\.store-metadata-main\s+\.main-input\s*\{[^}]*min-height:\s*168px"
        ),
        "locale rows remain compact": (
            r"\.store-metadata-main\s+\.locale-preview\s*\{[^}]*max-height:\s*22px"
        ),
        "right side uses one summary card": (
            r"\.metadata-side-summary-card\s*\{[^}]*display:\s*grid"
        ),
        "demo workspace columns are the source of truth": (
            r"\.store-metadata-main\s+\.workspace\s*\{[^}]*grid-template-columns:"
            r"\s*244px\s+minmax\(520px,\s*1fr\)\s*278px"
        ),
        "demo sync item class is styled": (
            r"\.store-metadata-main\s+\.sync-item\s*\{[^}]*grid-template-columns:"
            r"\s*26px\s+minmax\(0,\s*1fr\)\s*8px\s*auto\s*14px"
        ),
        "store image rows expose image count": (
            r"\.store-image-count\s*\{[^}]*grid-column:\s*5"
        ),
    }
    for label, pattern in css_contracts.items():
        require(re.search(pattern, css, flags=re.S) is not None, label, failures)

    if failures:
        print("UI verification failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("UI verification passed")
    print(f"url: {args.url}")
    print(f"css: {css_href}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
