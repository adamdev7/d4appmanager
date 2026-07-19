from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import EmailAutomationRule, EmailTemplate, GmailAccount, Store, User
from app.email_automation.events import AutomationEventType
from app.models.email_automation import EmailAutomationRuleCreate, EmailAutomationRuleUpdate

_EVENT_LABELS: dict[AutomationEventType, tuple[str, str]] = {
    AutomationEventType.ORDER_PAID: ("Order paid", "Purchase confirmation"),
    AutomationEventType.ORDER_FULFILLED: ("Order fulfilled", "Shipping confirmation"),
    AutomationEventType.ORDER_DELIVERED: ("Order delivered", "Delivery confirmation"),
    AutomationEventType.CUSTOMER_CREATED: ("Customer created", "Welcome email"),
    AutomationEventType.FIRST_PURCHASE: ("First purchase", "Onboarding / thank you"),
    AutomationEventType.REPEAT_PURCHASE: ("Repeat purchase", "Loyalty email"),
    AutomationEventType.TRACKING_ADDED: ("Tracking added", "Tracking notification"),
    AutomationEventType.IN_TRANSIT_UPDATE: ("In transit", "Shipping update"),
}


class AutomationRuleService:
    def _ensure_store(self, db: Session, user: User, store_id: str) -> Store:
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
        return store

    def list_event_types(self) -> list[dict]:
        return [
            {
                "event_type": ev.value,
                "label": _EVENT_LABELS[ev][0],
                "description": _EVENT_LABELS[ev][1],
            }
            for ev in AutomationEventType
        ]

    def _serialize(self, row: EmailAutomationRule) -> dict:
        template_name = row.template.name if row.template else None
        gmail_email = row.gmail_account.email if row.gmail_account else None
        return {
            "id": row.id,
            "store_id": row.store_id,
            "event_type": row.event_type,
            "template_id": row.template_id,
            "template_name": template_name,
            "gmail_account_id": row.gmail_account_id,
            "gmail_email": gmail_email,
            "is_enabled": row.is_enabled,
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        }

    def list_rules(self, db: Session, user: User, store_id: str) -> list[dict]:
        self._ensure_store(db, user, store_id)
        rows = db.scalars(
            select(EmailAutomationRule)
            .where(EmailAutomationRule.store_id == store_id)
            .options(joinedload(EmailAutomationRule.template), joinedload(EmailAutomationRule.gmail_account))
            .order_by(EmailAutomationRule.event_type)
        ).all()
        return [self._serialize(r) for r in rows]

    def create_rule(
        self, db: Session, user: User, store_id: str, data: EmailAutomationRuleCreate
    ) -> dict:
        self._ensure_store(db, user, store_id)
        template = db.get(EmailTemplate, data.template_id)
        if not template or template.store_id != store_id:
            raise HTTPException(status_code=status.HTTP_400_NOT_FOUND, detail="Template not found for store")

        if data.gmail_account_id:
            account = db.get(GmailAccount, data.gmail_account_id)
            if not account or account.owner_id != user.id:
                raise HTTPException(status_code=status.HTTP_400_NOT_FOUND, detail="Gmail account not found")

        existing = db.scalar(
            select(EmailAutomationRule).where(
                EmailAutomationRule.store_id == store_id,
                EmailAutomationRule.event_type == data.event_type.value,
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A rule for this event already exists for the store",
            )

        row = EmailAutomationRule(
            store_id=store_id,
            event_type=data.event_type.value,
            template_id=data.template_id,
            gmail_account_id=data.gmail_account_id,
            is_enabled=data.is_enabled,
        )
        db.add(row)
        db.commit()
        row = db.scalar(
            select(EmailAutomationRule)
            .where(EmailAutomationRule.id == row.id)
            .options(joinedload(EmailAutomationRule.template), joinedload(EmailAutomationRule.gmail_account))
        )
        return self._serialize(row)

    def update_rule(
        self,
        db: Session,
        user: User,
        store_id: str,
        rule_id: str,
        data: EmailAutomationRuleUpdate,
    ) -> dict:
        row = db.get(EmailAutomationRule, rule_id)
        if not row or row.store_id != store_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
        self._ensure_store(db, user, store_id)

        if data.template_id is not None:
            template = db.get(EmailTemplate, data.template_id)
            if not template or template.store_id != store_id:
                raise HTTPException(status_code=status.HTTP_400_NOT_FOUND, detail="Template not found")
            row.template_id = data.template_id

        if data.gmail_account_id is not None:
            if data.gmail_account_id:
                account = db.get(GmailAccount, data.gmail_account_id)
                if not account or account.owner_id != user.id:
                    raise HTTPException(status_code=status.HTTP_400_NOT_FOUND, detail="Gmail account not found")
            row.gmail_account_id = data.gmail_account_id or None

        if data.event_type is not None:
            conflict = db.scalar(
                select(EmailAutomationRule).where(
                    EmailAutomationRule.store_id == store_id,
                    EmailAutomationRule.event_type == data.event_type.value,
                    EmailAutomationRule.id != rule_id,
                )
            )
            if conflict:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Rule for event already exists")
            row.event_type = data.event_type.value

        if data.is_enabled is not None:
            row.is_enabled = data.is_enabled

        db.commit()
        row = db.scalar(
            select(EmailAutomationRule)
            .where(EmailAutomationRule.id == rule_id)
            .options(joinedload(EmailAutomationRule.template), joinedload(EmailAutomationRule.gmail_account))
        )
        return self._serialize(row)

    def delete_rule(self, db: Session, user: User, store_id: str, rule_id: str) -> None:
        row = db.get(EmailAutomationRule, rule_id)
        if not row or row.store_id != store_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
        self._ensure_store(db, user, store_id)
        db.delete(row)
        db.commit()
