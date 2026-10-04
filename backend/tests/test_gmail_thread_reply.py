"""Gmail replies must use the RFC Message-ID, not Gmail's API id, or the send is rejected."""

import asyncio
import base64
import json
from email import message_from_bytes
from unittest.mock import patch

from app.integrations.gmail.inbox_client import (
    GmailInboxClient,
    build_reply_email,
    describe_gmail_send_error,
    normalize_rfc_message_id,
    should_retry_send_without_thread,
)


class _Account:
    email = "store@luxory.com"


class _Response:
    def __init__(self, status: int, payload):
        self.status_code = status
        self._payload = payload
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

    def json(self):
        if isinstance(self._payload, str):
            return json.loads(self._payload)
        return self._payload


def _decoded(raw: str):
    return message_from_bytes(base64.urlsafe_b64decode(raw))


def test_gmail_api_id_is_not_a_message_id():
    assert normalize_rfc_message_id("18f3deadbeef") is None
    assert normalize_rfc_message_id("<cust-1@mail.gmail.com>") == "<cust-1@mail.gmail.com>"
    assert normalize_rfc_message_id("cust-1@mail.gmail.com") == "<cust-1@mail.gmail.com>"


def test_build_reply_ignores_a_gmail_api_id():
    message = build_reply_email(
        to="buyer@example.com",
        from_addr="store@luxory.com",
        subject="Where is my order?",
        body_text="It shipped today.",
        threaded=True,
        rfc_message_id="18f3deadbeef",
    )
    assert message["In-Reply-To"] is None
    assert message["Subject"] == "Re: Where is my order?"


def test_fresh_message_keeps_the_subject_we_chose():
    message = build_reply_email(
        to="buyer@example.com",
        from_addr="store@luxory.com",
        subject="Your message to Luxory",
        body_text="Thanks for writing.",
        threaded=False,
        rfc_message_id="<should-not-be-used@mail.gmail.com>",
    )
    assert message["Subject"] == "Your message to Luxory"
    assert message["In-Reply-To"] is None


def test_thread_rejection_is_retried_without_the_thread():
    assert should_retry_send_without_thread(
        400, json.dumps({"error": {"message": "Invalid thread_id value"}})
    )
    assert not should_retry_send_without_thread(
        403, json.dumps({"error": {"message": "insufficient authentication scopes"}})
    )
    assert "Reconnect Gmail" in describe_gmail_send_error(
        403, json.dumps({"error": {"message": "Request had insufficient authentication scopes."}})
    )


def test_threaded_send_uses_the_rfc_message_id():
    calls: list[dict] = []

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None, params=None):
            return _Response(
                200,
                {
                    "payload": {
                        "headers": [
                            {"name": "Message-ID", "value": "<cust-1@mail.gmail.com>"},
                            {"name": "References", "value": "<older@mail.gmail.com>"},
                            {"name": "Subject", "value": "Where is my order?"},
                        ]
                    }
                },
            )

        async def post(self, url, headers=None, json=None):
            calls.append(json)
            return _Response(200, {"id": "sent-1"})

    async def _token(self, account):
        return "tok"

    client = GmailInboxClient(db=None)  # type: ignore[arg-type]
    with patch("app.integrations.gmail.inbox_client.httpx.AsyncClient", _Client), patch.object(
        GmailInboxClient, "_token", _token
    ):
        result = asyncio.run(
            client.send_thread_reply(
                _Account(),  # type: ignore[arg-type]
                to="buyer@example.com",
                subject="Where is my order?",
                body_text="It shipped today.",
                thread_id="thread-9",
                in_reply_to_message_id="18f3deadbeef",
            )
        )

    assert result == {"id": "sent-1"}
    assert calls[0]["threadId"] == "thread-9"
    parsed = _decoded(calls[0]["raw"])
    assert parsed["In-Reply-To"] == "<cust-1@mail.gmail.com>"
    assert "18f3deadbeef" not in (parsed["In-Reply-To"] or "")
    assert "<older@mail.gmail.com>" in parsed["References"]
    assert "<cust-1@mail.gmail.com>" in parsed["References"]
    assert parsed["Subject"] == "Re: Where is my order?"


def test_invalid_thread_falls_back_to_a_new_message():
    calls: list[dict] = []

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None, params=None):
            return _Response(
                200,
                {
                    "payload": {
                        "headers": [
                            {"name": "Message-ID", "value": "<cust-1@mail.gmail.com>"},
                            {"name": "Subject", "value": "Where is my order?"},
                        ]
                    }
                },
            )

        async def post(self, url, headers=None, json=None):
            calls.append(json)
            if len(calls) == 1:
                return _Response(400, {"error": {"message": "Invalid thread_id value"}})
            return _Response(200, {"id": "sent-2"})

    async def _token(self, account):
        return "tok"

    client = GmailInboxClient(db=None)  # type: ignore[arg-type]
    with patch("app.integrations.gmail.inbox_client.httpx.AsyncClient", _Client), patch.object(
        GmailInboxClient, "_token", _token
    ):
        result = asyncio.run(
            client.send_thread_reply(
                _Account(),  # type: ignore[arg-type]
                to="buyer@example.com",
                subject="Your message to Luxory",
                body_text="Thanks for writing.",
                thread_id="thread-9",
                in_reply_to_message_id="18f3deadbeef",
            )
        )

    assert result == {"id": "sent-2"}
    assert "threadId" not in calls[1]
    parsed = _decoded(calls[1]["raw"])
    assert parsed["In-Reply-To"] is None
    assert parsed["Subject"] == "Your message to Luxory"


def test_missing_send_permission_is_reported_and_not_retried():
    calls: list[dict] = []

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None, params=None):
            return _Response(200, {"payload": {"headers": []}})

        async def post(self, url, headers=None, json=None):
            calls.append(json)
            return _Response(
                403,
                {"error": {"message": "Request had insufficient authentication scopes."}},
            )

    async def _token(self, account):
        return "tok"

    client = GmailInboxClient(db=None)  # type: ignore[arg-type]
    with patch("app.integrations.gmail.inbox_client.httpx.AsyncClient", _Client), patch.object(
        GmailInboxClient, "_token", _token
    ):
        result = asyncio.run(
            client.send_thread_reply(
                _Account(),  # type: ignore[arg-type]
                to="buyer@example.com",
                subject="Hello",
                body_text="Hi",
                thread_id="thread-9",
                in_reply_to_message_id="18f3deadbeef",
            )
        )

    assert result is None
    assert len(calls) == 1
    assert client.last_send_error is not None
    assert "Reconnect Gmail" in client.last_send_error
