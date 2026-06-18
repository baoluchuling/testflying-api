from __future__ import annotations

import math
import re
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock

from testflying_connector.config import Settings


@dataclass(frozen=True)
class RateLimitRule:
    key: str
    max_requests: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int
    rule: RateLimitRule


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, rule: RateLimitRule) -> RateLimitDecision:
        now = time.monotonic()
        max_requests = max(rule.max_requests, 1)
        window_seconds = max(rule.window_seconds, 1)
        with self._lock:
            events = self._events.setdefault(rule.key, deque())
            cutoff = now - window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= max_requests:
                retry_after = max(math.ceil(events[0] + window_seconds - now), 1)
                return RateLimitDecision(
                    allowed=False,
                    retry_after=retry_after,
                    rule=RateLimitRule(rule.key, max_requests, window_seconds),
                )
            events.append(now)
        return RateLimitDecision(
            allowed=True,
            retry_after=0,
            rule=RateLimitRule(rule.key, max_requests, window_seconds),
        )

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


class StoreRateLimitPolicy:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._apple_max_requests = max(settings.apple_rate_limit_fallback_max_requests, 1)
        self._apple_window_seconds = max(settings.apple_rate_limit_window_seconds, 1)
        self._lock = Lock()

    def rule_for_platform(self, platform: str) -> RateLimitRule:
        normalized_platform = platform.strip().lower()
        if normalized_platform == "ios":
            with self._lock:
                return RateLimitRule(
                    key="apple",
                    max_requests=self._apple_max_requests,
                    window_seconds=self._apple_window_seconds,
                )
        if normalized_platform == "android":
            return RateLimitRule(
                key="google",
                max_requests=self._settings.google_rate_limit_max_requests,
                window_seconds=self._settings.google_rate_limit_window_seconds,
            )
        return RateLimitRule(
            key="unknown-store",
            max_requests=min(
                self._settings.google_rate_limit_max_requests,
                self._apple_max_requests,
            ),
            window_seconds=max(
                self._settings.google_rate_limit_window_seconds,
                self._apple_window_seconds,
            ),
        )

    def record_apple_rate_limit_header(self, header_value: str | None) -> None:
        user_hour_limit = parse_apple_user_hour_limit(header_value)
        if user_hour_limit is None:
            return
        adjusted_limit = max(
            math.floor(user_hour_limit * self._settings.apple_rate_limit_safety_ratio),
            1,
        )
        with self._lock:
            self._apple_max_requests = adjusted_limit
            self._apple_window_seconds = 3600


def parse_apple_user_hour_limit(header_value: str | None) -> int | None:
    if header_value is None:
        return None
    match = re.search(r"(?:^|;)\s*user-hour-lim\s*:\s*(\d+)\s*(?:;|$)", header_value)
    if match is None:
        return None
    return int(match.group(1))
