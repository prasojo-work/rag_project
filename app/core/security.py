"""Small in-process security helpers (per-replica rate limiting)."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request


class RateLimiter:
    """Sliding-window limiter.

    This is intentionally in-process: FastAPI Cloud may run up to 3 replicas,
    so the effective limit can be up to 3x. That is acceptable for a portfolio
    demo; use Cloudflare/Redis for strict global limits.
    """

    def __init__(self, limit_per_minute: int = 10) -> None:
        self.limit = max(1, limit_per_minute)
        self.window = 60.0
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        events = self._events[key]
        while events and now - events[0] >= self.window:
            events.popleft()
        if len(events) >= self.limit:
            retry_after = max(1, int(self.window - (now - events[0])))
            return False, retry_after
        events.append(now)
        return True, 0

    def reset(self) -> None:
        self._events.clear()


def client_key(request: Request) -> str:
    for header in ("CF-Connecting-IP", "X-Forwarded-For"):
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
