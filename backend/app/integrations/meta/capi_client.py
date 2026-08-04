"""Meta Conversions API (CAPI) HTTP client with retries."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_API_VERSION = "v25.0"
# Backoff before retries 2 and 3 (attempt 1 is immediate)
_RETRY_DELAYS_SEC = (0.0, 5.0, 30.0, 120.0)


class MetaCapiClient:
    def __init__(
        self,
        *,
        pixel_id: str,
        access_token: str,
        api_version: str = DEFAULT_API_VERSION,
        test_event_code: str | None = None,
    ) -> None:
        self.pixel_id = pixel_id.strip()
        self.access_token = access_token.strip()
        version = (api_version or DEFAULT_API_VERSION).strip()
        if not version.startswith("v"):
            version = f"v{version}"
        self.api_version = version
        self.test_event_code = (test_event_code or "").strip() or None

    @property
    def events_url(self) -> str:
        return f"https://graph.facebook.com/{self.api_version}/{self.pixel_id}/events"

    async def send_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """POST events to Meta. Retries on 5xx/network; raises on 4xx without retry."""
        body: dict[str, Any] = {
            "data": events,
            "access_token": self.access_token,
        }
        if self.test_event_code:
            body["test_event_code"] = self.test_event_code

        last_error: Exception | None = None
        max_attempts = 3
        async with httpx.AsyncClient(timeout=30) as client:
            for attempt in range(1, max_attempts + 1):
                if attempt > 1:
                    await asyncio.sleep(_RETRY_DELAYS_SEC[min(attempt, len(_RETRY_DELAYS_SEC) - 1)])

                try:
                    resp = await client.post(self.events_url, json=body)
                except (httpx.TransportError, httpx.TimeoutException) as exc:
                    last_error = exc
                    logger.warning(
                        "meta_capi network error attempt=%s pixel=%s error=%s",
                        attempt,
                        self.pixel_id,
                        type(exc).__name__,
                    )
                    if attempt >= max_attempts:
                        raise
                    continue

                if resp.status_code >= 500:
                    last_error = httpx.HTTPStatusError(
                        f"Meta CAPI {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                    logger.warning(
                        "meta_capi 5xx attempt=%s status=%s pixel=%s body=%s",
                        attempt,
                        resp.status_code,
                        self.pixel_id,
                        resp.text[:500],
                    )
                    if attempt >= max_attempts:
                        raise last_error
                    continue

                if resp.status_code >= 400:
                    err_body = resp.text[:2000]
                    logger.error(
                        "meta_capi 4xx status=%s pixel=%s response=%s",
                        resp.status_code,
                        self.pixel_id,
                        err_body,
                    )
                    raise httpx.HTTPStatusError(
                        f"Meta CAPI {resp.status_code}: {err_body}",
                        request=resp.request,
                        response=resp,
                    )

                data = resp.json()
                logger.info(
                    "meta_capi ok pixel=%s events_received=%s fbtrace_id=%s",
                    self.pixel_id,
                    data.get("events_received"),
                    data.get("fbtrace_id"),
                )
                return data

        if last_error:
            raise last_error
        raise RuntimeError("Meta CAPI send failed with no response")
