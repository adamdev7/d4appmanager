from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.db.models import EmailSendLog, Store, User
from app.db.session import get_db
from app.email_automation.default_templates import seed_store_automation_defaults
from app.email_automation.layout_presets import LAYOUT_PRESETS
from app.email_automation.services.branding_service import EmailBrandingService
from app.email_automation.services.rule_service import AutomationRuleService
from app.email_automation.services.template_service import EmailTemplateService
from app.email_automation.variable_resolver import list_supported_variables
from app.models.email_automation import (
    EmailAutomationRuleCreate,
    EmailAutomationRuleUpdate,
    EmailBrandingUpdate,
    EmailTemplateCreate,
    EmailTemplateUpdate,
)

router = APIRouter()
_templates = EmailTemplateService()
_rules = AutomationRuleService()
_branding = EmailBrandingService()


def _ensure_store_access(db: Session, user: User, store_id: str) -> None:
    store = db.get(Store, store_id)
    if not store or store.owner_id != user.id:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")


@router.get("/events")
async def list_automation_events(user: User = Depends(get_verified_user)):
    _ = user
    return _rules.list_event_types()


@router.get("/variables")
async def list_template_variables(user: User = Depends(get_verified_user)):
    _ = user
    return {"variables": list_supported_variables()}


@router.get("/layouts")
async def list_layout_presets(user: User = Depends(get_verified_user)):
    _ = user
    return {"layouts": LAYOUT_PRESETS}


@router.get("/stores/{store_id}/branding")
async def get_branding(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _branding.get_branding(db, user, store_id)


@router.patch("/stores/{store_id}/branding")
async def update_branding(
    store_id: str,
    data: EmailBrandingUpdate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    if data.theme_color is None:
        return _branding.get_branding(db, user, store_id)
    return _branding.update_theme_color(db, user, store_id, data.theme_color)


@router.post("/stores/{store_id}/branding/logo")
async def upload_branding_logo(
    store_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _branding.upload_logo(db, user, store_id, file)


@router.delete("/stores/{store_id}/branding/logo")
async def delete_branding_logo(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _branding.remove_logo(db, user, store_id)


@router.post("/stores/{store_id}/seed-defaults")
async def seed_defaults(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    _ensure_store_access(db, user, store_id)
    seed_store_automation_defaults(db, store_id)
    return {"message": "Default templates and rules created (disabled until you enable them)"}


@router.get("/stores/{store_id}/templates")
async def list_templates(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _templates.list_templates(db, user, store_id)


@router.post("/stores/{store_id}/templates")
async def create_template(
    store_id: str,
    data: EmailTemplateCreate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _templates.create_template(db, user, store_id, data)


@router.get("/stores/{store_id}/templates/{template_id}")
async def get_template(
    store_id: str,
    template_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _templates.get_template(db, user, store_id, template_id)


@router.patch("/stores/{store_id}/templates/{template_id}")
async def update_template(
    store_id: str,
    template_id: str,
    data: EmailTemplateUpdate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _templates.update_template(db, user, store_id, template_id, data)


@router.delete("/stores/{store_id}/templates/{template_id}")
async def delete_template(
    store_id: str,
    template_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    _templates.delete_template(db, user, store_id, template_id)
    return {"message": "Template deleted"}


@router.get("/stores/{store_id}/rules")
async def list_rules(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    _ensure_store_access(db, user, store_id)
    # Quietly upgrade one-line starter copy to fuller professional templates.
    seed_store_automation_defaults(db, store_id, refresh_legacy_bodies=True)
    return _rules.list_rules(db, user, store_id)


@router.post("/stores/{store_id}/rules")
async def create_rule(
    store_id: str,
    data: EmailAutomationRuleCreate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _rules.create_rule(db, user, store_id, data)


@router.patch("/stores/{store_id}/rules/{rule_id}")
async def update_rule(
    store_id: str,
    rule_id: str,
    data: EmailAutomationRuleUpdate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _rules.update_rule(db, user, store_id, rule_id, data)


@router.delete("/stores/{store_id}/rules/{rule_id}")
async def delete_rule(
    store_id: str,
    rule_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    _rules.delete_rule(db, user, store_id, rule_id)
    return {"message": "Rule deleted"}


@router.get("/stores/{store_id}/send-logs")
async def list_send_logs(
    store_id: str,
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    _ensure_store_access(db, user, store_id)
    rows = db.scalars(
        select(EmailSendLog)
        .where(EmailSendLog.store_id == store_id)
        .order_by(EmailSendLog.sent_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "store_id": r.store_id,
            "rule_id": r.rule_id,
            "event_type": r.event_type,
            "recipient": r.recipient,
            "subject": r.subject,
            "status": r.status,
            "error_message": r.error_message,
            "provider_message_id": r.provider_message_id,
            "sent_at": r.sent_at.isoformat() if r.sent_at else "",
        }
        for r in rows
    ]
