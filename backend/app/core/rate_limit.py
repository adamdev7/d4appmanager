"""Simple in-memory rate limiter for auth endpoints (per process)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key -> list of attempt timestamps
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            hits = [t for t in self._hits[key] if t >= cutoff]
            if len(hits) >= limit:
                self._hits[key] = hits
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Please wait a few minutes and try again.",
                )
            hits.append(now)
            self._hits[key] = hits


auth_rate_limiter = RateLimiter()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_auth_rate_limit(
    request: Request,
    *,
    action: str,
    email: str | None = None,
    limit: int = 10,
    window_seconds: int = 60,
) -> None:
    ip = client_ip(request)
    email_key = (email or "").strip().lower() or "none"
    # Limit both by IP and by email to slow credential stuffing / OTP brute force
    auth_rate_limiter.check(f"{action}:ip:{ip}", limit=limit, window_seconds=window_seconds)
    auth_rate_limiter.check(
        f"{action}:email:{email_key}",
        limit=max(5, limit // 2),
        window_seconds=window_seconds,
    )
