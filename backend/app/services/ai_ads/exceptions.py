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


class VideoProviderError(AIAdsError):
    pass


class InsufficientDataError(AIAdsError):
    pass
