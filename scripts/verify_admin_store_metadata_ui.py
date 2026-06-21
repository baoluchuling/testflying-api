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
        "card toolbar",
        "toolbar-left",
        "toolbar-right",
        "metadata-refresh-button",
        "class=\"workspace\"",
        "card rail",
        "class=\"sync-item",
        "class=\"card editor\"",
        "class=\"main-input\"",
        "data-current-metadata-editor",
        "class=\"locale-row\"",
        "class=\"image-locale-row store-image-locale-row\"",
        "class=\"side\"",
        "class=\"checks\"",
        "最近同步记录",
        "image-count",
        "asset-uploader",
        "preview-grid",
        "data-store-image-track",
        "store-image-add-card",
        "data-store-image-preview-all",
        "data-store-image-lightbox",
        "openStoreImageLightbox",
        "closeStoreImageLightbox",
        "snapshotStoreImageFiles(input)",
        "appendStoreImageFiles(input, selected",
        "uniqueStoreImageFiles([...existing, ...files])",
        "data-sync-item-select",
        "data-sync-item-panel",
        "row.hidden = false",
        "row.dataset.expanded = expanded ? 'true' : 'false'",
        "toggle.addEventListener('click'",
        "toggle.dataset.localeToggleBound = 'true'",
        "event.stopPropagation()",
        "syncMetadataEditor(form)",
        "label.textContent = groupExpanded ? '收起多语言' : '展开所有语言'",
        "function toggleLocaleRow(row)",
        "const localeRow = event.target.closest('[data-locale-row]')",
        "row.dataset.rowExpanded = expanded ? 'true' : 'false'",
        "data-locale-detail-input",
    ):
        require(marker in html, f"page is missing {marker}", failures)

    require(
        bool(
            re.search(
                r'name="storeImageFiles__phone_screenshots__[^"]+"[^>]*multiple',
                html,
                re.DOTALL,
            )
        ),
        "phone screenshot upload input is not multi-select",
        failures,
    )
    require(
        bool(
            re.search(
                r'name="storeImageFiles__tablet_screenshots__[^"]+"[^>]*multiple',
                html,
                re.DOTALL,
            )
        ),
        "tablet screenshot upload input is not multi-select",
        failures,
    )
    for label in ("关键词", "宣传文本", "描述", "手机截图", "平板截图"):
        require(label in html, f"page is missing short label {label}", failures)

    css_url = urljoin(args.url, css_href or "/static/admin/admin.css")
    css = fetch_text(css_url, args.username, args.password)
    css_contracts = {
        "store metadata main width matches demo frame": (
            r"\.store-metadata-main\s*\{[^}]*max-width:\s*1262px"
        ),
        "toolbar is left-right aligned": (
            r"\.store-metadata-main\s+\.toolbar\s*\{[^}]*justify-content:\s*space-between"
        ),
        "content set picker is demo sized": (
            r"\.store-metadata-main\s+\.content-set-picker\s*\{[^}]*flex:\s*0\s+0\s+184px"
            r"[^}]*width:\s*184px[^}]*max-width:\s*184px"
        ),
        "language picker is demo sized": (
            r"\.store-metadata-main\s+\.language-picker\s*\{[^}]*flex:\s*0\s+0\s+138px"
            r"[^}]*width:\s*138px[^}]*max-width:\s*138px"
        ),
        "sync item keeps title readable": (
            r"\.store-metadata-main\s+\.sync-item\s*\{[^}]*grid-template-columns:"
            r"\s*26px\s+minmax\(0,\s*1fr\)\s*8px\s*auto\s*14px"
        ),
        "editor card keeps demo height": (
            r"\.store-metadata-main\s+\.editor\s*\{[^}]*min-height:\s*608px"
        ),
        "current editor stays in first viewport": (
            r"\.store-metadata-main\s+\.main-input\s*\{[^}]*height:\s*168px"
            r"[^}]*min-height:\s*168px"
        ),
        "locale rows keep demo height": (
            r"\.store-metadata-main\s+\.locale-row:not\(\[data-expanded=\"true\"\]\)\s*\{"
            r"[^}]*height:\s*64px"
        ),
        "expanded locale rows can show details": (
            r"\.store-metadata-main\s+\.locale-row\[data-expanded=\"true\"\]\s*\{"
            r"[^}]*height:\s*auto"
        ),
        "locale detail input is available": (
            r"\.store-metadata-main\s+\.locale-detail-input\s*\{[^}]*grid-column:\s*2\s*/\s*-2"
        ),
        "locale rows remain compact": (
            r"\.store-metadata-main\s+\.locale-preview\s*\{[^}]*white-space:\s*nowrap"
        ),
        "right side uses one summary card": (
            r"\.store-metadata-main\s+\.side-card\s*\{[^}]*padding:\s*20px\s*16px"
        ),
        "demo workspace columns are the source of truth": (
            r"\.store-metadata-main\s+\.workspace\s*\{[^}]*grid-template-columns:"
            r"\s*244px\s+minmax\(520px,\s*1fr\)\s*278px"
        ),
        "store image previews use real preview grid": (
            r"\.store-metadata-main\s+\.preview-grid\s*\{[^}]*grid-template-columns:"
            r"\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)"
        ),
        "store image rows expose image count": (
            r"\.store-metadata-main\s+\.image-locale-row\s*\{[^}]*grid-template-columns:"
        ),
        "store image rows use horizontal track": (
            r"\.store-metadata-main\s+\.store-image-track\s*\{[^}]*overflow-x:\s*auto"
        ),
        "store image add card is compact": (
            r"\.store-metadata-main\s+\.store-image-add-card\s*\{[^}]*flex:\s*0\s+0\s+88px"
        ),
        "store image lightbox is fullscreen": (
            r"\.store-image-lightbox\s*\{[^}]*position:\s*fixed"
            r"[^}]*inset:\s*0[^}]*place-items:\s*stretch[^}]*padding:\s*0"
        ),
        "store image lightbox panel fills viewport": (
            r"\.store-image-lightbox-panel\s*\{[^}]*width:\s*100vw"
            r"[^}]*height:\s*100vh[^}]*border:\s*0[^}]*border-radius:\s*0"
        ),
        "store image fullscreen grid scrolls": (
            r"\.store-image-lightbox-grid\s*\{[^}]*grid-template-columns:"
            r"\s*repeat\(auto-fill,\s*minmax\(240px,\s*1fr\)\)[^}]*overflow:\s*auto"
        ),
        "rail history link stays one row": (
            r"\.store-metadata-main\s+\.history-link\s*\{[^}]*display:\s*grid"
            r"[^}]*grid-template-columns:\s*26px\s+minmax\(0,\s*1fr\)\s*24px"
            r"[^}]*white-space:\s*nowrap"
        ),
    }
    for label, pattern in css_contracts.items():
        require(re.search(pattern, css, flags=re.S) is not None, label, failures)

    final_guard_index = css.rfind("Store metadata final conflict guards")
    require(final_guard_index != -1, "final conflict guard block is missing", failures)
    for selector in (
        ".store-metadata-main .toolbar-left",
        ".store-metadata-main .content-set-picker",
        ".store-metadata-main .language-picker",
        ".store-metadata-main .metadata-preflight-chip.blocked",
        ".store-metadata-main .main-input",
        ".store-metadata-main .locale-row",
        ".store-metadata-main .history-link",
    ):
        require(
            css.rfind(selector) > final_guard_index,
            f"{selector} is not guarded after demo contract rules",
            failures,
        )

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
