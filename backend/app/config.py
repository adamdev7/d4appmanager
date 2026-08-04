from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Always load backend/.env (uvicorn reload only watches app/ — .env edits need a restart)
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# Canonical production host — Shopify OAuth + webhooks use this unless a dev tunnel is explicitly allowed
PRODUCTION_PUBLIC_URL = "https://appmanager.store"


def _is_ephemeral_public_url(url: str) -> bool:
    u = (url or "").lower()
    return any(
        marker in u
        for marker in (
            "ngrok",
            "localhost",
            "127.0.0.1",
            "loca.lt",
            "trycloudflare",
            "cloudflare.com",
        )
    )


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
    app_url: str = PRODUCTION_PUBLIC_URL
    frontend_url: str = PRODUCTION_PUBLIC_URL
    # Shopify OAuth/webhooks always use this host (override only if needed)
    shopify_public_url: str = PRODUCTION_PUBLIC_URL
    # Set true ONLY for local Shopify testing with ngrok (also whitelist that tunnel in Partners)
    shopify_allow_dev_tunnel: bool = False

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
    verification_code_max_attempts: int = 5
    # Auth rate limits (per IP / email window)
    auth_login_rate_limit: int = 10
    auth_otp_rate_limit: int = 8
    auth_rate_window_seconds: int = 60

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
        "https://www.googleapis.com/auth/gmail.modify "
        "https://www.googleapis.com/auth/gmail.send"
    )
    # Sign-in / sign-up with Google (no Gmail API scopes)
    google_auth_scopes: str = "openid email profile"

    # OpenAI (AI Email Assistant — server-side only)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_max_retries: int = 3
    openai_timeout_seconds: int = 60

    # Autopilot scheduler tick (seconds between checks for due user automations)
    automation_poll_seconds: int = 60

    # Meta CAPI — poll Shopify for paid orders not yet sent (never-miss safety net)
    meta_capi_reconcile_seconds: int = 300
    meta_capi_reconcile_hours: int = 48
    meta_capi_max_send_attempts: int = 15

    # Order tracking page — optional carrier APIs
    track17_api_key: str = ""
    yunexpress_api_key: str = ""
    yunexpress_api_url: str = "https://api.yunexpress.com"

    @property
    def shopify_oauth_base(self) -> str:
        """Public origin used for Shopify OAuth redirect_uri and webhook registration."""
        if self.shopify_allow_dev_tunnel and self.debug:
            base = (self.app_url or PRODUCTION_PUBLIC_URL).rstrip("/")
            return base
        base = (self.shopify_public_url or PRODUCTION_PUBLIC_URL).rstrip("/")
        if _is_ephemeral_public_url(base):
            return PRODUCTION_PUBLIC_URL
        return base

    @property
    def shopify_redirect_uri(self) -> str:
        return f"{self.shopify_oauth_base}{self.api_prefix}/stores/shopify/callback"

    @property
    def shopify_webhook_base(self) -> str:
        return self.shopify_oauth_base

    @property
    def public_frontend_url(self) -> str:
        """Where browsers return after Shopify OAuth."""
        fu = (self.frontend_url or PRODUCTION_PUBLIC_URL).rstrip("/")
        if not self.debug and _is_ephemeral_public_url(fu):
            return PRODUCTION_PUBLIC_URL
        return fu

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.app_url.rstrip('/')}{self.api_prefix}/gmail/oauth/callback"

    @property
    def google_auth_redirect_uri(self) -> str:
        return f"{self.app_url.rstrip('/')}{self.api_prefix}/auth/google/callback"


settings = Settings()
