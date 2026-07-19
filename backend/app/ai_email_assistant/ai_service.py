import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.ai_email_assistant.email_filter import EmailFilterResult, parse_classification_json
from app.ai_email_assistant.openai_errors import OpenAIServiceError, openai_error_from_response
from app.ai_email_assistant.prompt_builder import BusinessContext, build_reply_prompt
from app.config import settings

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


@dataclass
class AIReplyResult:
    body: str
    model: str
    intent: str | None
    prompt_snapshot: str


class AIService:
    """OpenAI wrapper for customer email replies. Model is configurable per deployment or per user."""

    def __init__(self, model: str | None = None, *, api_key: str | None = None) -> None:
        self._model = model or settings.openai_model
        self._api_key = api_key

    def _resolve_model(self, override: str | None) -> str:
        return override or self._model or settings.openai_model

    def _require_api_key(self) -> str:
        if not self._api_key:
            raise OpenAIServiceError(
                user_message="OpenAI API key is not set. Add your key in AI Email Assistant → Business context.",
                stop_autopilot=True,
            )
        return self._api_key

    async def generate_reply(
        self,
        *,
        sender: str,
        subject: str,
        email_body: str,
        context: BusinessContext,
        thread_context: str | None = None,
        model_override: str | None = None,
    ) -> AIReplyResult:
        self._require_api_key()

        prompt = build_reply_prompt(
            context=context,
            sender=sender,
            subject=subject,
            email_body=email_body,
            thread_context=thread_context,
        )
        model = self._resolve_model(model_override)
        body = await self._chat_completion(
            system_message=prompt.system_message,
            user_message=prompt.user_message,
            model=model,
        )
        intent = self._guess_intent(email_body)
        snapshot = f"[system]\n{prompt.system_message[:2000]}\n\n[user]\n{prompt.user_message[:2000]}"
        return AIReplyResult(
            body=body.strip(),
            model=model,
            intent=intent,
            prompt_snapshot=snapshot,
        )

    async def classify_should_reply(
        self,
        *,
        sender: str,
        subject: str,
        email_body: str,
        business_name: str,
        business_type: str,
        custom_skip_rules: str = "",
        thread_context: str | None = None,
        model_override: str | None = None,
    ) -> EmailFilterResult:
        """Decide if an incoming email should receive an AI reply."""
        if not self._api_key:
            return EmailFilterResult(should_reply=True)

        custom_block = custom_skip_rules.strip() or "None specified."
        system_message = f"""You classify incoming emails for a {business_type or "business"} named "{business_name or "the business"}".

You receive the FULL email thread when available, plus the latest message. Always use thread context — a lone "thank you" or "ok" is still part of an active customer conversation if the thread shows prior order/support discussion.

Decide whether the business should send a customer support reply to the LATEST message.

Do NOT reply (should_reply: false) for:
- Automated/system messages, no-reply senders, delivery receipts, security codes, password resets
- Newsletters, marketing blasts, platform notifications (Shopify, PayPal, social media, etc.)
- Spam or mail clearly unrelated to this business
- Closing thank-you messages where no response is needed AND the thread is already fully resolved (category: acknowledgment) — only if a polite one-line reply would add no value

DO reply (should_reply: true) for:
- Questions or requests about orders, shipping, refunds, products, cancellations, complaints
- Customer thank-you messages when a brief acknowledgment is appropriate (category: acknowledgment) — NOT "personal"
- Follow-ups in an ongoing support thread (category: customer)

NEVER use category "personal" for customers who bought from or contacted this business. Use "customer" or "acknowledgment".

Additional rules from the business owner (always respect these):
{custom_block}

Respond with JSON only, no markdown:
{{"should_reply": true or false, "reason": "short plain-English explanation for the user", "category": "customer|acknowledgment|automated|newsletter|spam|other"}}"""

        thread_block = ""
        if thread_context and thread_context.strip():
            thread_block = f"""Conversation thread (oldest to newest):
{thread_context.strip()[:10000]}

"""

        user_message = f"""{thread_block}Latest message to classify:

From: {sender}
Subject: {subject}

{email_body.strip()[:4000]}"""

        model = self._resolve_model(model_override)
        raw = await self._chat_completion(
            system_message=system_message,
            user_message=user_message,
            model=model,
            temperature=0.1,
        )
        return parse_classification_json(raw)

    async def _chat_completion(
        self,
        *,
        system_message: str,
        user_message: str,
        model: str,
        temperature: float = 0.4,
    ) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self._require_api_key()}",
            "Content-Type": "application/json",
        }

        last_error: OpenAIServiceError | None = None
        max_attempts = settings.openai_max_retries

        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(timeout=settings.openai_timeout_seconds) as client:
                    resp = await client.post(OPENAI_CHAT_URL, headers=headers, json=payload)
                    if resp.status_code == 429:
                        if attempt < max_attempts - 1:
                            wait = 2**attempt
                            logger.warning("OpenAI rate limited, retry in %ss", wait)
                            await asyncio.sleep(wait)
                            continue
                        raise openai_error_from_response(resp)
                    if resp.status_code >= 400:
                        raise openai_error_from_response(resp)
                    data = resp.json()
                    choice = data["choices"][0]["message"]["content"]
                    if not choice:
                        raise OpenAIServiceError(
                            user_message="OpenAI returned an empty response. Try again.",
                            stop_autopilot=False,
                        )
                    return choice
            except OpenAIServiceError as exc:
                last_error = exc
                if exc.retryable and attempt < max_attempts - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                raise
            except httpx.HTTPStatusError as exc:
                parsed = openai_error_from_response(exc.response)
                last_error = parsed
                if parsed.retryable and attempt < max_attempts - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                raise parsed from exc
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                from app.ai_email_assistant.openai_errors import openai_error_from_exception

                parsed = openai_error_from_exception(exc)
                last_error = parsed
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                raise parsed from exc

        if last_error:
            raise last_error
        raise OpenAIServiceError(
            user_message="OpenAI request failed after multiple retries. Autopilot was paused.",
            stop_autopilot=True,
            retryable=True,
        )

    @staticmethod
    def _guess_intent(body: str) -> str | None:
        text = body.lower()
        keywords = {
            "refund": "refund",
            "return": "refund",
            "cancel": "cancellation",
            "cancellation": "cancellation",
            "track": "order_update",
            "shipping": "order_update",
            "order": "order_update",
            "complaint": "complaint",
            "broken": "complaint",
            "damaged": "complaint",
            "subscription": "subscription",
            "unsubscribe": "subscription",
        }
        for word, intent in keywords.items():
            if word in text:
                return intent
        return "general"
