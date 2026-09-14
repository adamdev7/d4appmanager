from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.ai_email_assistant.openai_errors import OpenAIServiceError, openai_error_from_response
from app.config import settings
from app.services.ai_ads.exceptions import InvalidAIOutput

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"
OPENAI_IMAGE_EDITS_URL = "https://api.openai.com/v1/images/edits"
OPENAI_VIDEOS_URL = "https://api.openai.com/v1/videos"

# Newer OpenAI models reject custom temperature (only the default is allowed).
_NO_CUSTOM_TEMPERATURE_PREFIXES = ("gpt-5", "gpt-6", "o1", "o3", "o4")


def model_omits_temperature(model: str) -> bool:
    slug = (model or "").strip().lower()
    return any(slug.startswith(prefix) for prefix in _NO_CUSTOM_TEMPERATURE_PREFIXES)


def temperature_unsupported_in_response(body: str) -> bool:
    text = (body or "").lower()
    return "temperature" in text and ("unsupported" in text or "does not support" in text)


def should_retry_without_temperature(payload: dict[str, Any], status_code: int, body: str) -> bool:
    return (
        status_code == 400
        and "temperature" in payload
        and temperature_unsupported_in_response(body)
    )


class AdsOpenAIClient:
    """Server-side OpenAI client for AI Ads. Never expose the API key to the frontend."""

    def __init__(self, api_key: str, *, store_id: str | None = None) -> None:
        self._api_key = api_key
        self._store_id = store_id

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _log(
        self,
        *,
        request_id: str,
        operation: str,
        model: str,
        status: str,
        latency_ms: int,
        tokens: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        logger.info(
            "ai_ads openai op=%s status=%s model=%s store_id=%s request_id=%s latency_ms=%s tokens=%s error=%s",
            operation,
            status,
            model,
            self._store_id,
            request_id,
            latency_ms,
            tokens or {},
            (error or "")[:300],
        )

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel],
        model: str,
        images: list[dict[str, str]] | None = None,
        temperature: float = 0.3,
        operation: str = "complete_json",
    ) -> BaseModel:
        request_id = str(uuid.uuid4())
        user_content: Any
        if images:
            parts: list[dict[str, Any]] = [{"type": "text", "text": user}]
            for img in images:
                url = img.get("url") or ""
                if not url:
                    continue
                parts.append({"type": "image_url", "image_url": {"url": url}})
            user_content = parts
        else:
            user_content = user

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
        }
        if not model_omits_temperature(model):
            payload["temperature"] = temperature

        raw = await self._chat(payload, operation=operation, request_id=request_id, model=model)
        parsed = _loads_json(raw)
        try:
            return schema.model_validate(parsed)
        except ValidationError as first:
            retry_payload = dict(payload)
            retry_payload["messages"] = list(payload["messages"]) + [
                {
                    "role": "user",
                    "content": (
                        "Your previous JSON failed validation. Return corrected JSON only.\n"
                        f"Errors:\n{first}\n"
                        f"Previous output:\n{raw[:4000]}"
                    ),
                }
            ]
            raw2 = await self._chat(
                retry_payload, operation=f"{operation}_retry", request_id=request_id, model=model
            )
            try:
                return schema.model_validate(_loads_json(raw2))
            except ValidationError as second:
                logger.warning("ai_ads invalid JSON schema store_id=%s op=%s", self._store_id, operation)
                raise InvalidAIOutput(f"AI output failed validation: {second}") from second

    async def complete_text(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float = 0.5,
        operation: str = "complete_text",
    ) -> str:
        request_id = str(uuid.uuid4())
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if not model_omits_temperature(model):
            payload["temperature"] = temperature
        return await self._chat(payload, operation=operation, request_id=request_id, model=model)

    async def _chat(
        self,
        payload: dict[str, Any],
        *,
        operation: str,
        request_id: str,
        model: str,
    ) -> str:
        last_error: OpenAIServiceError | None = None
        max_attempts = settings.openai_max_retries
        started = time.perf_counter()
        payload = dict(payload)
        if model_omits_temperature(model):
            payload.pop("temperature", None)
        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(timeout=max(settings.openai_timeout_seconds, 90)) as client:
                    resp = await client.post(OPENAI_CHAT_URL, headers=self._headers(), json=payload)
                    latency = int((time.perf_counter() - started) * 1000)
                    if should_retry_without_temperature(payload, resp.status_code, resp.text):
                        payload.pop("temperature", None)
                        continue
                    if resp.status_code == 429 and attempt < max_attempts - 1:
                        self._log(
                            request_id=request_id,
                            operation=operation,
                            model=model,
                            status="rate_limited",
                            latency_ms=latency,
                        )
                        await asyncio.sleep(2**attempt)
                        continue
                    if resp.status_code >= 400:
                        raise openai_error_from_response(resp)
                    data = resp.json()
                    choice = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
                    usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
                    self._log(
                        request_id=request_id,
                        operation=operation,
                        model=model,
                        status="ok",
                        latency_ms=latency,
                        tokens=usage,
                    )
                    if not choice:
                        raise OpenAIServiceError(
                            user_message="OpenAI returned an empty response.",
                            stop_autopilot=False,
                            retryable=True,
                        )
                    return str(choice)
            except OpenAIServiceError as exc:
                last_error = exc
                if exc.retryable and attempt < max_attempts - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                self._log(
                    request_id=request_id,
                    operation=operation,
                    model=model,
                    status="error",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error=exc.user_message,
                )
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = OpenAIServiceError(
                    user_message="Could not reach OpenAI. Try again shortly.",
                    stop_autopilot=False,
                    retryable=True,
                )
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                self._log(
                    request_id=request_id,
                    operation=operation,
                    model=model,
                    status="error",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error=str(exc)[:200],
                )
                raise last_error from exc
        if last_error:
            raise last_error
        raise OpenAIServiceError(user_message="OpenAI request failed.", stop_autopilot=False, retryable=True)

    async def generate_image_b64(
        self,
        *,
        prompt: str,
        model: str,
        size: str = "1024x1024",
        operation: str = "image_generate",
        references: list[tuple[bytes, str]] | None = None,
        edit: bool | None = None,
    ) -> tuple[bytes, str]:
        # Product photos go through /images/edits as IDENTITY references so the
        # model cannot invent a different SKU. The prompt must demand a new scene.
        use_edit = bool(references) if edit is None else bool(edit and references)
        if use_edit and references:
            try:
                return await self._image_edits(
                    prompt=prompt,
                    model=model,
                    size=size,
                    references=references,
                    operation=f"{operation}_identity",
                )
            except Exception as exc:
                logger.warning(
                    "ai_ads image identity edit fallback to generate store_id=%s err=%s",
                    self._store_id,
                    str(exc)[:200],
                )
        return await self._image_generations(
            prompt=prompt, model=model, size=size, operation=operation
        )

    async def _image_generations(
        self, *, prompt: str, model: str, size: str, operation: str
    ) -> tuple[bytes, str]:
        request_id = str(uuid.uuid4())
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt[:4000],
            "size": size,
            "n": 1,
        }
        if _is_gpt_image(model):
            payload["quality"] = "medium"
        else:
            payload["response_format"] = "b64_json"
        last_error: Exception | None = None
        for attempt in range(settings.openai_max_retries):
            try:
                async with httpx.AsyncClient(timeout=180) as client:
                    resp = await client.post(OPENAI_IMAGES_URL, headers=self._headers(), json=payload)
                    latency = int((time.perf_counter() - started) * 1000)
                    body = resp.text or ""
                    if resp.status_code == 400 and _should_fallback_square(body) and payload.get("size") != "1024x1024":
                        payload["size"] = "1024x1024"
                        continue
                    if resp.status_code == 400 and "quality" in body.lower() and "quality" in payload:
                        payload.pop("quality", None)
                        continue
                    if resp.status_code == 429 and attempt < settings.openai_max_retries - 1:
                        self._log(
                            request_id=request_id,
                            operation=operation,
                            model=model,
                            status="rate_limited",
                            latency_ms=latency,
                        )
                        await asyncio.sleep(2**attempt)
                        continue
                    if resp.status_code >= 400:
                        raise openai_error_from_response(resp)
                    decoded = _decode_image_payload(resp.json())
                    self._log(
                        request_id=request_id,
                        operation=operation,
                        model=model,
                        status="ok",
                        latency_ms=latency,
                    )
                    if decoded:
                        return decoded
                    raise OpenAIServiceError(
                        user_message="Image generation returned no image data.",
                        stop_autopilot=False,
                    )
            except OpenAIServiceError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < settings.openai_max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                self._log(
                    request_id=request_id,
                    operation=operation,
                    model=model,
                    status="error",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error=str(exc)[:200],
                )
                raise OpenAIServiceError(
                    user_message=f"Image generation failed: {str(exc)[:200]}",
                    stop_autopilot=False,
                    retryable=True,
                ) from exc
        raise OpenAIServiceError(
            user_message=f"Image generation failed: {str(last_error)[:200]}",
            stop_autopilot=False,
            retryable=True,
        )

    async def _image_edits(
        self,
        *,
        prompt: str,
        model: str,
        size: str,
        references: list[tuple[bytes, str]],
        operation: str,
    ) -> tuple[bytes, str]:
        request_id = str(uuid.uuid4())
        started = time.perf_counter()
        headers = {"Authorization": f"Bearer {self._api_key}"}
        form: dict[str, str] = {
            "model": model,
            "prompt": prompt[:4000],
            "size": size,
            "n": "1",
        }
        if _is_gpt_image(model):
            form["quality"] = "medium"
        slug = (model or "").strip().lower()
        if "gpt-image-1" in slug and "gpt-image-2" not in slug:
            form["input_fidelity"] = "high"
        field = "image[]" if _is_gpt_image(model) else "image"
        files = _identity_files(references, field)
        if not files:
            raise OpenAIServiceError(
                user_message="No product reference image was available.",
                stop_autopilot=False,
            )
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(OPENAI_IMAGE_EDITS_URL, headers=headers, data=form, files=files)
            if resp.status_code >= 400 and field == "image[]":
                alt = _identity_files(references, "image")
                resp = await client.post(OPENAI_IMAGE_EDITS_URL, headers=headers, data=form, files=alt)
        latency = int((time.perf_counter() - started) * 1000)
        if resp.status_code >= 400:
            self._log(
                request_id=request_id,
                operation=operation,
                model=model,
                status="error",
                latency_ms=latency,
                error=resp.text[:200],
            )
            raise openai_error_from_response(resp)
        decoded = _decode_image_payload(resp.json())
        self._log(
            request_id=request_id,
            operation=operation,
            model=model,
            status="ok",
            latency_ms=latency,
        )
        if not decoded:
            raise OpenAIServiceError(
                user_message="Image edit returned no image data.",
                stop_autopilot=False,
            )
        return decoded

    async def create_video(
        self,
        *,
        prompt: str,
        model: str,
        size: str = "720x1280",
        seconds: str = "8",
        operation: str = "video_create",
        input_reference: tuple[bytes, str] | None = None,
    ) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        started = time.perf_counter()
        headers = {"Authorization": f"Bearer {self._api_key}"}
        form = {
            "model": model,
            "prompt": prompt[:4000],
            "size": size,
            "seconds": str(seconds),
        }
        files = None
        if input_reference and input_reference[0]:
            raw, mime = input_reference
            mime = (mime or "image/jpeg").split(";")[0].strip() or "image/jpeg"
            ext = "png" if "png" in mime else "jpg"
            files = {"input_reference": (f"product.{ext}", raw, mime)}
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(OPENAI_VIDEOS_URL, headers=headers, data=form, files=files)
        latency = int((time.perf_counter() - started) * 1000)
        if resp.status_code >= 400:
            self._log(
                request_id=request_id,
                operation=operation,
                model=model,
                status="error",
                latency_ms=latency,
                error=resp.text[:240],
            )
            raise openai_error_from_response(resp)
        data = resp.json() if resp.content else {}
        self._log(
            request_id=request_id,
            operation=operation,
            model=model,
            status=str((data or {}).get("status") or "ok"),
            latency_ms=latency,
        )
        if not isinstance(data, dict) or not data.get("id"):
            raise OpenAIServiceError(
                user_message="Video generation did not return a job id.",
                stop_autopilot=False,
            )
        return data

    async def get_video(self, video_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(f"{OPENAI_VIDEOS_URL}/{video_id}", headers=self._headers())
        if resp.status_code >= 400:
            raise openai_error_from_response(resp)
        data = resp.json() if resp.content else {}
        return data if isinstance(data, dict) else {}

    async def download_video_bytes(self, video_id: str) -> bytes:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.get(f"{OPENAI_VIDEOS_URL}/{video_id}/content", headers=headers)
        if resp.status_code >= 400:
            raise openai_error_from_response(resp)
        raw = resp.content or b""
        if len(raw) < 32:
            raise OpenAIServiceError(
                user_message="Video download returned an empty file.",
                stop_autopilot=False,
            )
        return raw


def _is_gpt_image(model: str) -> bool:
    return "gpt-image" in (model or "").strip().lower()


def _identity_files(references: list[tuple[bytes, str]], field: str) -> list[tuple[str, tuple[str, bytes, str]]]:
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for i, (raw, mime) in enumerate(references[:4]):
        if not raw:
            continue
        mime = (mime or "image/jpeg").split(";")[0].strip() or "image/jpeg"
        ext = "png" if "png" in mime else "jpg"
        files.append((field, (f"product-{i}.{ext}", raw, mime)))
    return files


def _should_fallback_square(body: str) -> bool:
    text = (body or "").lower()
    return "size" in text or "resolution" in text or "aspect" in text


def _decode_image_payload(data: Any) -> tuple[bytes, str] | None:
    item = (data.get("data") or [{}])[0] if isinstance(data, dict) else {}
    if not isinstance(item, dict):
        return None
    b64 = item.get("b64_json")
    if b64:
        import base64

        return base64.b64decode(b64), "image/png"
    url = item.get("url")
    if not url:
        return None
    try:
        with httpx.Client(timeout=60) as dl:
            img = dl.get(url)
            img.raise_for_status()
        mime = img.headers.get("content-type", "image/png").split(";")[0].strip()
        return img.content, mime or "image/png"
    except Exception:
        return None


def _loads_json(raw: str) -> Any:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise InvalidAIOutput("AI did not return JSON") from exc
