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
