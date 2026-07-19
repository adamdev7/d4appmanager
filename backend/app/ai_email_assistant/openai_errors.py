"""Map OpenAI / network failures to user-facing messages and autopilot stop rules."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class OpenAIServiceError(Exception):
    """Raised when OpenAI cannot complete a request; may require stopping autopilot."""

    user_message: str
    stop_autopilot: bool = True
    status_code: int | None = None
    error_code: str | None = None
    retryable: bool = False

    def __str__(self) -> str:
        return self.user_message


def _parse_openai_body(response: httpx.Response) -> tuple[str, str | None, str | None]:
    try:
        data = response.json()
    except json.JSONDecodeError:
        return response.text[:300] or "Unknown OpenAI error", None, None

    err = data.get("error") if isinstance(data, dict) else None
    if not isinstance(err, dict):
        return str(data)[:300], None, None

    message = str(err.get("message") or "Unknown OpenAI error")
    code = err.get("code")
    err_type = err.get("type")
    return message, str(code) if code else None, str(err_type) if err_type else None


def openai_error_from_response(response: httpx.Response) -> OpenAIServiceError:
    raw_message, code, err_type = _parse_openai_body(response)
    status = response.status_code
    combined = f"{raw_message} {code or ''} {err_type or ''}".lower()

    if status == 401 or code in ("invalid_api_key", "authentication_error") or "invalid api key" in combined:
        return OpenAIServiceError(
            user_message="Your OpenAI API key is invalid or revoked. Update it under Business context, then turn autopilot back on.",
            stop_autopilot=True,
            status_code=status,
            error_code=code,
        )

    if status == 403 or "permission" in combined or "does not have access" in combined:
        return OpenAIServiceError(
            user_message="OpenAI denied access for this API key. Check your organization permissions and model access.",
            stop_autopilot=True,
            status_code=status,
            error_code=code,
        )

    quota_hit = (
        status == 402
        or code in ("insufficient_quota", "billing_not_active", "billing_hard_limit_reached")
        or err_type in ("insufficient_quota",)
        or "insufficient_quota" in combined
        or "exceeded your current quota" in combined
        or "billing" in combined
        or "credit" in combined
        or "balance" in combined
    )
    if quota_hit:
        return OpenAIServiceError(
            user_message="OpenAI account has insufficient credits or billing is inactive. Add credits at platform.openai.com, then re-enable autopilot.",
            stop_autopilot=True,
            status_code=status,
            error_code=code,
        )

    if status == 429 or code == "rate_limit_exceeded" or err_type == "rate_limit_exceeded":
        return OpenAIServiceError(
            user_message="OpenAI rate limit reached. Autopilot was paused — wait a few minutes or upgrade your OpenAI plan, then turn it on again.",
            stop_autopilot=True,
            status_code=status,
            error_code=code,
            retryable=True,
        )

    if status == 404 or code == "model_not_found" or "model" in combined and "not found" in combined:
        return OpenAIServiceError(
            user_message=f"The configured OpenAI model is not available for your API key. Choose another model in settings. ({raw_message[:120]})",
            stop_autopilot=True,
            status_code=status,
            error_code=code,
        )

    if status == 400:
        if "context_length" in combined or "maximum context" in combined:
            return OpenAIServiceError(
                user_message="Email is too long for the AI model context window. Try a shorter thread or a larger-context model.",
                stop_autopilot=False,
                status_code=status,
                error_code=code,
            )
        return OpenAIServiceError(
            user_message=f"OpenAI rejected the request: {raw_message[:200]}",
            stop_autopilot=True,
            status_code=status,
            error_code=code,
        )

    if status >= 500:
        return OpenAIServiceError(
            user_message="OpenAI is temporarily unavailable. Autopilot was paused — try again later.",
            stop_autopilot=True,
            status_code=status,
            error_code=code,
            retryable=True,
        )

    return OpenAIServiceError(
        user_message=f"OpenAI error ({status}): {raw_message[:200]}",
        stop_autopilot=True,
        status_code=status,
        error_code=code,
    )


def openai_error_from_exception(exc: Exception) -> OpenAIServiceError:
    if isinstance(exc, OpenAIServiceError):
        return exc

    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return openai_error_from_response(exc.response)

    if isinstance(exc, httpx.TimeoutException):
        return OpenAIServiceError(
            user_message="OpenAI request timed out. Autopilot was paused — check your connection or try again.",
            stop_autopilot=True,
            retryable=True,
        )

    if isinstance(exc, httpx.ConnectError):
        return OpenAIServiceError(
            user_message="Could not reach OpenAI. Autopilot was paused — check network connectivity.",
            stop_autopilot=True,
            retryable=True,
        )

    if isinstance(exc, ValueError) and "api key" in str(exc).lower():
        return OpenAIServiceError(
            user_message=str(exc),
            stop_autopilot=True,
        )

    if isinstance(exc, RuntimeError) and "openai" in str(exc).lower():
        return OpenAIServiceError(
            user_message="OpenAI failed after multiple retries. Autopilot was paused — try again in a few minutes.",
            stop_autopilot=True,
            retryable=True,
        )

    return OpenAIServiceError(
        user_message=f"AI error: {str(exc)[:200]}",
        stop_autopilot=True,
    )
