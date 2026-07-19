"""Email automation: rules, templates, webhook triggers, and send pipeline."""

from app.email_automation.events import AutomationEventType
from app.email_automation.services.trigger_service import EmailTriggerService

__all__ = ["AutomationEventType", "EmailTriggerService"]
