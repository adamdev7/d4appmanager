from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.db.models import EmailSendLog, Store, User
from app.db.session import get_db
from app.email_automation.default_templates import seed_store_automation_defaults
from app.email_automation.services.rule_service import AutomationRuleService
from app.email_automation.services.template_service import EmailTemplateService
from app.email_automation.variable_resolver import list_supported_variables
from app.models.email_automation import (
    EmailAutomationRuleCreate,
    EmailAutomationRuleUpdate,
    EmailTemplateCreate,
    EmailTemplateUpdate,
)

router = APIRouter()
_templates = EmailTemplateService()
_rules = AutomationRuleService()


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
