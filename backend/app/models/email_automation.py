from pydantic import BaseModel, Field

from app.email_automation.events import AutomationEventType


class EmailTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    subject: str = Field(min_length=1, max_length=512)
    body_html: str = ""
    layout_preset: str = Field(default="classic", max_length=32)


class EmailTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    subject: str | None = Field(default=None, min_length=1, max_length=512)
    body_html: str | None = None
    layout_preset: str | None = Field(default=None, max_length=32)


class EmailTemplateResponse(BaseModel):
    id: str
    store_id: str
    name: str
    subject: str
    body_html: str
    layout_preset: str = "classic"
    created_at: str
    updated_at: str


class EmailBrandingUpdate(BaseModel):
    theme_color: str | None = Field(default=None, max_length=32)


class EmailBrandingResponse(BaseModel):
    store_id: str
    theme_color: str
    logo_url: str | None = None


class EmailAutomationRuleCreate(BaseModel):
    event_type: AutomationEventType
    template_id: str
    gmail_account_id: str | None = None
    is_enabled: bool = True


class EmailAutomationRuleUpdate(BaseModel):
    event_type: AutomationEventType | None = None
    template_id: str | None = None
    gmail_account_id: str | None = None
    is_enabled: bool | None = None


class EmailAutomationRuleResponse(BaseModel):
    id: str
    store_id: str
    event_type: str
    template_id: str
    template_name: str | None = None
    gmail_account_id: str | None
    gmail_email: str | None = None
    is_enabled: bool
    created_at: str
    updated_at: str


class EmailSendLogResponse(BaseModel):
    id: str
    store_id: str
    rule_id: str | None
    event_type: str
    recipient: str
    subject: str
    status: str
    error_message: str | None
    provider_message_id: str | None
    sent_at: str


class AutomationEventInfo(BaseModel):
    event_type: str
    label: str
    description: str
