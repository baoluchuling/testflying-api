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
        "metadata-control-strip",
        "metadata-focus-workspace",
        "metadata-sync-rail",
        "metadata-focus-panel",
        "metadata-side-status",
        "data-sync-item-select",
        "data-sync-item-panel",
    ):
        require(marker in html, f"page is missing {marker}", failures)

    css_url = urljoin(args.url, css_href or "/static/admin/admin.css")
    css = fetch_text(css_url, args.username, args.password)
    css_contracts = {
        "control strip uses compact grid": (
            r"\.metadata-control-strip\s*\{[^}]*grid-template-columns:"
            r"\s*minmax\(0,\s*1fr\)"
        ),
        "version controls are two columns": (
            r"\.metadata-version-controls\s*\{[^}]*repeat"
            r"\(2,\s*minmax\(180px,\s*1fr\)\)"
        ),
        "content set row is compact": (
            r"grid-template-columns:\s*minmax\(280px,\s*1fr\)\s*auto\s*auto\s*auto"
        ),
        "focus card aligns content to top": (
            r"\.metadata-focus-card\s*\{[^}]*align-content:\s*start"
        ),
        "focus locale rows start near header": (
            r"\.metadata-focus-locale-grid\s*\{[^}]*margin-top:\s*12px"
        ),
        "selected text area stays in first viewport": (
            r"textarea\s*\{[^}]*min-height:\s*168px"
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
