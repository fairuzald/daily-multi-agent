from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


@dataclass(frozen=True)
class RateLimitRule:
    path: str
    max_requests: int


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        window_seconds: int,
        rules: tuple[RateLimitRule, ...],
        trust_forwarded_for: bool = True,
    ) -> None:
        super().__init__(app)
        self.window_seconds = max(window_seconds, 1)
        self.rules = {rule.path: max(rule.max_requests, 1) for rule in rules}
        self.trust_forwarded_for = trust_forwarded_for
        self._buckets: dict[tuple[str, str], tuple[float, int]] = {}
        self._lock = Lock()

    async def dispatch(self, request: Request, call_next) -> Response:
        max_requests = self.rules.get(request.url.path)
        if max_requests is None:
            return await call_next(request)

        client_ip = self._client_ip(request)
        now = time.monotonic()
        retry_after = 0
        allowed = True

        with self._lock:
            self._cleanup(now)
            key = (request.url.path, client_ip)
            window_start, count = self._buckets.get(key, (now, 0))
            if now - window_start >= self.window_seconds:
                window_start, count = now, 0
            count += 1
            self._buckets[key] = (window_start, count)
            if count > max_requests:
                allowed = False
                retry_after = max(1, int(self.window_seconds - (now - window_start)))

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."},
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)

    def _client_ip(self, request: Request) -> str:
        if self.trust_forwarded_for:
            forwarded = request.headers.get("x-forwarded-for", "")
            if forwarded:
                first_hop = forwarded.split(",", 1)[0].strip()
                if first_hop:
                    return first_hop
        client = request.client
        return client.host if client else "unknown"

    def _cleanup(self, now: float) -> None:
        expired = [
            key
            for key, (window_start, _) in self._buckets.items()
            if now - window_start >= self.window_seconds
        ]
        for key in expired:
            self._buckets.pop(key, None)
