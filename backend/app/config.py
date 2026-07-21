from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Always load backend/.env (uvicorn reload only watches app/ — .env edits need a restart)
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "App Manager"
    debug: bool = True
    api_prefix: str = "/api/v1"

    # Public URLs (OAuth redirects, email links)
    app_url: str = "http://127.0.0.1:8000"
    frontend_url: str = "http://localhost:5173"

    database_url: str = "sqlite:///./data/app_manager.db"

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    # JWT
    jwt_secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    # Encrypt Shopify/Gmail tokens at rest (Fernet key, 32 url-safe base64 bytes)
    encryption_key: str = ""

    # Email verification (SMTP)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_from_name: str = "App Manager"
    smtp_use_tls: bool = True

    @field_validator("smtp_password", mode="before")
    @classmethod
    def strip_smtp_password_spaces(cls, v: object) -> object:
        if isinstance(v, str):
            return v.replace(" ", "")
        return v

    verification_code_expire_minutes: int = 15
    verification_code_length: int = 6

    # Shopify
    shopify_client_id: str = ""
    shopify_client_secret: str = ""
    shopify_scopes: str = (
        "read_products,read_orders,read_customers,read_fulfillments,write_fulfillments,"
        "write_orders,read_shopify_payments_payouts"
    )
    shopify_api_version: str = "2024-10"

    # Google / Gmail
    google_client_id: str = ""
    google_client_secret: str = ""
    google_scopes: str = (
        "openid email profile "
        "https://www.googleapis.com/auth/gmail.send "
        "https://www.googleapis.com/auth/gmail.readonly"
    )

    # OpenAI (AI Email Assistant — server-side only)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_max_retries: int = 3
    openai_timeout_seconds: int = 60

    # Autopilot scheduler tick (seconds between checks for due user automations)
    automation_poll_seconds: int = 60

    # Order tracking page — optional carrier APIs
    track17_api_key: str = ""
    yunexpress_api_key: str = ""
    yunexpress_api_url: str = "https://api.yunexpress.com"

    @property
    def shopify_redirect_uri(self) -> str:
        return f"{self.app_url.rstrip('/')}{self.api_prefix}/stores/shopify/callback"

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.app_url.rstrip('/')}{self.api_prefix}/gmail/oauth/callback"


settings = Settings()
