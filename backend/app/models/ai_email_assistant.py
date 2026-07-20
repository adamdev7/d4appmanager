from pydantic import BaseModel, Field


class AIEmailAssistantSettingsUpdate(BaseModel):
    business_name: str = ""
    business_type: str = "e-commerce"
    tone_of_voice: str = "friendly and professional"
    rules: str = ""
    policies: str = ""
    faq: str = ""
    auto_send_enabled: bool = False
    gmail_account_id: str | None = None
    openai_model: str | None = None
    email_filter_enabled: bool = True
    filter_automated_emails: bool = True
    filter_non_business_emails: bool = True
    filter_custom_rules: str = ""
    automation_enabled: bool = False
    automation_interval_minutes: int = Field(default=15, ge=5, le=120)
    automation_max_emails_per_run: int = Field(default=10, ge=1, le=50)
    one_reply_per_thread: bool = True
    sync_only_customer_unread: bool = True
    verify_gmail_thread_before_reply: bool = True
    use_thread_context: bool = True


class AIEmailAssistantSettingsResponse(AIEmailAssistantSettingsUpdate):
    id: str
    openai_configured: bool = False
    openai_key_masked: str | None = None
    openai_key_is_user_owned: bool = False
    openai_uses_server_fallback: bool = False
    default_model: str = "gpt-4o-mini"
    automation_last_run_at: str | None = None
    automation_last_error: str | None = None


class AutomationRunResponse(BaseModel):
    ok: bool
    processed: int = 0
    skipped: bool = False
    stopped: bool = False
    reason: str | None = None
    error: str | None = None


class SetOpenAIKeyBody(BaseModel):
    api_key: str = Field(min_length=20, max_length=256)


class OpenAIKeyStatusResponse(BaseModel):
    openai_configured: bool
    openai_key_masked: str | None = None
    openai_key_is_user_owned: bool = False
    openai_uses_server_fallback: bool = False


class InboxEmailResponse(BaseModel):
    id: str
    gmail_message_id: str
    thread_id: str
    sender: str
    sender_email: str
    subject: str
    body_text: str
    detected_intent: str | None
    skip_reason: str | None = None
    filter_category: str | None = None
    status: str
    received_at: str
    latest_reply: "AIReplyResponse | None" = None


class AIReplyResponse(BaseModel):
    id: str
    inbox_email_id: str
    generated_body: str
    edited_body: str | None
    effective_body: str
    status: str
    model_used: str
    detected_intent: str | None = None
    error_message: str | None = None
    created_at: str
    sent_at: str | None = None


class UpdateReplyDraftBody(BaseModel):
    body: str = Field(min_length=1)


class SyncInboxRequest(BaseModel):
    gmail_account_id: str
    max_results: int = Field(default=15, ge=1, le=50)


class FullHistoryScanRequest(BaseModel):
    """Scan the entire Gmail inbox history (requires explicit user confirmation)."""

    gmail_account_id: str
    confirmed: bool = False
    max_threads: int = Field(default=100, ge=1, le=200)


class FullHistoryScanResponse(BaseModel):
    threads_scanned: int = 0
    imported: int = 0
    needs_reply: int = 0
    never_answered: int = 0
    skipped_already_answered: int = 0
    skipped_filtered: int = 0
    processed_replies: int = 0
    message: str = ""
    inbox: list[InboxEmailResponse] = []


class AIReplyLogEntry(BaseModel):
    id: str
    inbox_email_id: str
    subject: str
    sender_email: str
    status: str
    model_used: str
    body_preview: str
    created_at: str
    sent_at: str | None = None


class NamedCount(BaseModel):
    name: str
    count: int


class PeriodStats(BaseModel):
    emails_received: int = 0
    replies_sent: int = 0
    drafts_pending: int = 0
    filtered: int = 0
    failed: int = 0
    awaiting_reply: int = 0


class AIEmailAssistantStatsResponse(BaseModel):
    """Store-owner dashboard metrics for AI Email Assistant."""

    all_time: PeriodStats
    today: PeriodStats
    last_7_days: PeriodStats
    last_30_days: PeriodStats

    filter_breakdown: list[NamedCount] = []
    intent_breakdown: list[NamedCount] = []

    unique_customers_helped: int = 0
    minutes_saved_estimate: int = 0
    hours_saved_estimate: float = 0.0
    filter_efficiency_pct: float = 0.0
    reply_rate_pct: float = 0.0

    autopilot_enabled: bool = False
    auto_send_enabled: bool = False
    automation_last_run_at: str | None = None
    openai_configured: bool = False
    gmail_connected: bool = False
