import httpx
import pytest

from app.ai_email_assistant.openai_errors import (
    OpenAIServiceError,
    openai_error_from_response,
)


def _response(status: int, body: dict) -> httpx.Response:
    import json

    return httpx.Response(
        status_code=status,
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
        content=json.dumps(body).encode(),
    )


def test_insufficient_quota_stops_autopilot():
    err = openai_error_from_response(
        _response(
            429,
            {
                "error": {
                    "message": "You exceeded your current quota",
                    "type": "insufficient_quota",
                    "code": "insufficient_quota",
                }
            },
        )
    )
    assert err.stop_autopilot is True
    assert "credit" in err.user_message.lower() or "billing" in err.user_message.lower()


def test_invalid_api_key():
    err = openai_error_from_response(
        _response(401, {"error": {"message": "Incorrect API key", "code": "invalid_api_key"}})
    )
    assert err.stop_autopilot is True
    assert "invalid" in err.user_message.lower() or "api key" in err.user_message.lower()
