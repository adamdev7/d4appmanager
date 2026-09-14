class AIAdsError(Exception):
    """Base error for the AI Ads engine. Never crash the FastAPI process."""

    def __init__(self, message: str, *, retryable: bool = False, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.code = code


class ProviderNotConfigured(AIAdsError):
    pass


class InvalidAIOutput(AIAdsError):
    pass


class MetaImportError(AIAdsError):
    pass


class ImageGenerationError(AIAdsError):
    pass


class GenerationCancelled(AIAdsError):
    """Operator stopped the job from the workplace console."""

    def __init__(self, message: str = "Generation stopped.") -> None:
        super().__init__(message, retryable=False, code="CANCELLED")


class VideoProviderError(AIAdsError):
    pass


class InsufficientDataError(AIAdsError):
    pass


PILLOW_INSTALL_HINT = (
    "This server cannot process pictures (Pillow is missing). "
    "On the VPS run: cd /var/www/appmanager/backend && .venv/bin/pip install -r requirements.txt "
    "&& sudo systemctl restart appmanager. Then tap Run again."
)


def operator_error_message(exc: BaseException) -> str:
    """Turn raw exceptions into something an operator can act on in the Generate UI."""
    if isinstance(exc, AIAdsError) and exc.message:
        text = exc.message.strip()
    else:
        text = str(exc or "").strip() or type(exc).__name__
    blob = f"{type(exc).__name__} {text}".lower()
    if (
        "no module named 'pil'" in blob
        or "no module named \"pil\"" in blob
        or "no module named 'pillow'" in blob
        or "missing_pillow" in blob
        or "pillow is missing" in blob
        or "pillow is not installed" in blob
    ):
        return PILLOW_INSTALL_HINT
    if "timed out" in blob or "timeout" in blob:
        return "OpenAI took too long. Tap Run again in a minute."
    if "rate limit" in blob or "too many requests" in blob:
        return "OpenAI rate-limited this run. Wait a minute, then tap Run again."
    return text[:800]
