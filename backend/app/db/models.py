import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    openai_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    openai_api_key_hint: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stores: Mapped[list["Store"]] = relationship(back_populates="owner")
    gmail_accounts: Mapped[list["GmailAccount"]] = relationship(back_populates="owner")
    verification_codes: Mapped[list["VerificationCode"]] = relationship(back_populates="user")


class VerificationPurpose(str, enum.Enum):
    EMAIL_VERIFY = "email_verify"
    PASSWORD_RESET = "password_reset"


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    code_hash: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[str] = mapped_column(String(32), default=VerificationPurpose.EMAIL_VERIFY.value)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="verification_codes")


class StoreStatus(str, enum.Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    PENDING = "pending"


class Store(Base):
    __tablename__ = "stores"
    __table_args__ = (UniqueConstraint("shop_domain", name="uq_store_domain"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    shop_domain: Mapped[str] = mapped_column(String(255), index=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=StoreStatus.PENDING.value)
    plan: Mapped[str] = mapped_column(String(64), default="Basic")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    shopify_webhook_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_theme_color: Mapped[str] = mapped_column(String(32), default="#0d9488")
    email_logo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="stores")
    gmail_links: Mapped[list["GmailStoreLink"]] = relationship(back_populates="store")
    email_templates: Mapped[list["EmailTemplate"]] = relationship(back_populates="store")
    automation_rules: Mapped[list["EmailAutomationRule"]] = relationship(back_populates="store")


class GmailAccountStatus(str, enum.Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    EXPIRED = "expired"


class GmailAccount(Base):
    __tablename__ = "gmail_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default=GmailAccountStatus.DISCONNECTED.value)
    is_default_sender: Mapped[bool] = mapped_column(Boolean, default=False)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped["User"] = relationship(back_populates="gmail_accounts")
    store_links: Mapped[list["GmailStoreLink"]] = relationship(back_populates="gmail_account")


class GmailStoreLink(Base):
    __tablename__ = "gmail_store_links"
    __table_args__ = (UniqueConstraint("gmail_account_id", "store_id", name="uq_gmail_store"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    gmail_account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("gmail_accounts.id", ondelete="CASCADE")
    )
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id", ondelete="CASCADE"))

    gmail_account: Mapped["GmailAccount"] = relationship(back_populates="store_links")
    store: Mapped["Store"] = relationship(back_populates="gmail_links")


class UserEmailSettings(Base):
    __tablename__ = "user_email_settings"
    __table_args__ = (
        UniqueConstraint("user_id", "store_id", name="uq_user_email_settings_user_store"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    store_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stores.id", ondelete="SET NULL"), nullable=True
    )
    reply_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signature_html: Mapped[str] = mapped_column(Text, default="")
    track_opens: Mapped[bool] = mapped_column(Boolean, default=False)
    track_clicks: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_send_limit: Mapped[int] = mapped_column(default=500)


class OAuthState(Base):
    """Short-lived OAuth state (Shopify / Google)."""

    __tablename__ = "oauth_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    state: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(32))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    extra: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: shop domain, store_id, etc.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrderTracking(Base):
    """Customer order tracking snapshot synced from Shopify webhooks."""

    __tablename__ = "order_tracking"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "order_number_normalized",
            "customer_email",
            name="uq_order_tracking_store_order_email",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id", ondelete="CASCADE"), index=True)
    shopify_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_number_display: Mapped[str] = mapped_column(String(64))
    order_number_normalized: Mapped[str] = mapped_column(String(64), index=True)
    customer_email: Mapped[str] = mapped_column(String(255), index=True)
    tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    carrier: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    timeline_json: Mapped[str] = mapped_column(Text, default="[]")
    order_placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_total_display: Mapped[str | None] = mapped_column(String(32), nullable=True)
    order_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    line_items_json: Mapped[str] = mapped_column(Text, default="[]")
    fulfillments_json: Mapped[str] = mapped_column(Text, default="[]")
    shopify_financial_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    shopify_fulfillment_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StoreTrackingSettings(Base):
    """Per-store carrier API credentials and enrichment behavior."""

    __tablename__ = "store_tracking_settings"
    __table_args__ = (UniqueConstraint("store_id", name="uq_store_tracking_settings_store"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id", ondelete="CASCADE"), index=True)
    carrier_mode: Mapped[str] = mapped_column(String(32), default="auto")
    auto_enrich_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    yunexpress_api_url: Mapped[str] = mapped_column(String(512), default="https://api.yunexpress.com")
    yunexpress_customer_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    yunexpress_carrier_keywords: Mapped[str] = mapped_column(String(255), default="yun,yunexpress")
    track17_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    track17_api_key_hint: Mapped[str | None] = mapped_column(String(8), nullable=True)
    yunexpress_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    yunexpress_api_key_hint: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WebhookLog(Base):
    __tablename__ = "webhook_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    store_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("stores.id", ondelete="SET NULL"))
    topic: Mapped[str] = mapped_column(String(128))
    shop_domain: Mapped[str] = mapped_column(String(255))
    payload_preview: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailTemplate(Base):
    __tablename__ = "email_templates"
    __table_args__ = (UniqueConstraint("store_id", "name", name="uq_email_template_store_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    subject: Mapped[str] = mapped_column(String(512))
    body_html: Mapped[str] = mapped_column(Text, default="")
    layout_preset: Mapped[str] = mapped_column(String(32), default="classic")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    store: Mapped["Store"] = relationship(back_populates="email_templates")
    rules: Mapped[list["EmailAutomationRule"]] = relationship(back_populates="template")


class EmailAutomationRule(Base):
    __tablename__ = "email_automation_rules"
    __table_args__ = (
        UniqueConstraint("store_id", "event_type", name="uq_automation_rule_store_event"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    template_id: Mapped[str] = mapped_column(String(36), ForeignKey("email_templates.id", ondelete="CASCADE"))
    gmail_account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("gmail_accounts.id", ondelete="SET NULL"), nullable=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    store: Mapped["Store"] = relationship(back_populates="automation_rules")
    template: Mapped["EmailTemplate"] = relationship(back_populates="rules")
    gmail_account: Mapped["GmailAccount | None"] = relationship()


class EmailSendStatus(str, enum.Enum):
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class EmailSendLog(Base):
    __tablename__ = "email_send_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    store_id: Mapped[str] = mapped_column(String(36), ForeignKey("stores.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("email_automation_rules.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64))
    recipient: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(32), default=EmailSendStatus.SKIPPED.value)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InboxEmailStatus(str, enum.Enum):
    NEW = "new"
    DRAFT_PENDING = "draft_pending"
    REPLIED = "replied"
    PROCESSED = "processed"
    SKIPPED = "skipped"


class AIReplyStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    FAILED = "failed"
    REJECTED = "rejected"


class AIEmailAssistantSettings(Base):
    """Business context and behavior for AI-generated customer email replies."""

    __tablename__ = "ai_email_assistant_settings"
    __table_args__ = (
        UniqueConstraint("user_id", "store_id", name="uq_ai_email_settings_user_store"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    store_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stores.id", ondelete="SET NULL"), nullable=True
    )
    gmail_account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("gmail_accounts.id", ondelete="SET NULL"), nullable=True
    )
    business_name: Mapped[str] = mapped_column(String(255), default="")
    business_type: Mapped[str] = mapped_column(String(128), default="e-commerce")
    tone_of_voice: Mapped[str] = mapped_column(String(128), default="friendly and professional")
    rules: Mapped[str] = mapped_column(Text, default="")
    policies: Mapped[str] = mapped_column(Text, default="")
    faq: Mapped[str] = mapped_column(Text, default="")
    auto_send_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    openai_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_filter_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    filter_automated_emails: Mapped[bool] = mapped_column(Boolean, default=True)
    filter_non_business_emails: Mapped[bool] = mapped_column(Boolean, default=True)
    filter_custom_rules: Mapped[str] = mapped_column(Text, default="")
    automation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    automation_interval_minutes: Mapped[int] = mapped_column(default=15)
    automation_max_emails_per_run: Mapped[int] = mapped_column(default=10)
    automation_last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    automation_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    one_reply_per_thread: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_only_customer_unread: Mapped[bool] = mapped_column(Boolean, default=True)
    verify_gmail_thread_before_reply: Mapped[bool] = mapped_column(Boolean, default=True)
    use_thread_context: Mapped[bool] = mapped_column(Boolean, default=True)
    # Background "Check inbox" / full-history scan (avoids gateway timeouts)
    full_scan_status: Mapped[str] = mapped_column(String(32), default="idle")
    full_scan_message: Mapped[str] = mapped_column(Text, default="")
    full_scan_progress: Mapped[int] = mapped_column(default=0)
    full_scan_total: Mapped[int] = mapped_column(default=0)
    full_scan_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    full_scan_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InboxEmail(Base):
    """Incoming customer email metadata synced from Gmail."""

    __tablename__ = "inbox_emails"
    __table_args__ = (
        UniqueConstraint("gmail_account_id", "gmail_message_id", name="uq_inbox_gmail_message"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    store_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stores.id", ondelete="SET NULL"), nullable=True
    )
    gmail_account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("gmail_accounts.id", ondelete="CASCADE"), index=True
    )
    gmail_message_id: Mapped[str] = mapped_column(String(128))
    thread_id: Mapped[str] = mapped_column(String(128))
    sender: Mapped[str] = mapped_column(String(512))
    sender_email: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(String(512), default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    detected_intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    filter_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=InboxEmailStatus.NEW.value)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    replies: Mapped[list["AIEmailReply"]] = relationship(back_populates="inbox_email")


class AIEmailReply(Base):
    """AI-generated reply draft or sent message linked to an inbox email."""

    __tablename__ = "ai_email_replies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    inbox_email_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inbox_emails.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    generated_body: Mapped[str] = mapped_column(Text, default="")
    edited_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=AIReplyStatus.DRAFT.value)
    model_used: Mapped[str] = mapped_column(String(64), default="")
    prompt_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    gmail_sent_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    inbox_email: Mapped["InboxEmail"] = relationship(back_populates="replies")
