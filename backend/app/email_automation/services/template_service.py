from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EmailTemplate, Store, User
from app.email_automation.layout_presets import DEFAULT_LAYOUT, LAYOUT_PRESETS
from app.models.email_automation import EmailTemplateCreate, EmailTemplateUpdate

_VALID_LAYOUTS = {p["id"] for p in LAYOUT_PRESETS}


class EmailTemplateService:
    def _ensure_store(self, db: Session, user: User, store_id: str) -> Store:
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
        return store

    def _normalize_layout(self, value: str | None) -> str:
        preset = (value or DEFAULT_LAYOUT).lower().strip()
        if preset not in _VALID_LAYOUTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid layout_preset. Choose one of: {', '.join(sorted(_VALID_LAYOUTS))}",
            )
        return preset

    def _serialize(self, row: EmailTemplate) -> dict:
        return {
            "id": row.id,
            "store_id": row.store_id,
            "name": row.name,
            "subject": row.subject,
            "body_html": row.body_html,
            "layout_preset": getattr(row, "layout_preset", None) or DEFAULT_LAYOUT,
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        }

    def list_templates(self, db: Session, user: User, store_id: str) -> list[dict]:
        self._ensure_store(db, user, store_id)
        rows = db.scalars(
            select(EmailTemplate)
            .where(EmailTemplate.store_id == store_id)
            .order_by(EmailTemplate.name)
        ).all()
        return [self._serialize(r) for r in rows]

    def get_template(self, db: Session, user: User, store_id: str, template_id: str) -> dict:
        self._ensure_store(db, user, store_id)
        row = db.get(EmailTemplate, template_id)
        if not row or row.store_id != store_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
        return self._serialize(row)

    def create_template(
        self, db: Session, user: User, store_id: str, data: EmailTemplateCreate
    ) -> dict:
        self._ensure_store(db, user, store_id)
        existing = db.scalar(
            select(EmailTemplate).where(
                EmailTemplate.store_id == store_id,
                EmailTemplate.name == data.name,
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A template with this name already exists for the store",
            )
        row = EmailTemplate(
            store_id=store_id,
            name=data.name,
            subject=data.subject,
            body_html=data.body_html,
            layout_preset=self._normalize_layout(data.layout_preset),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return self._serialize(row)

    def update_template(
        self,
        db: Session,
        user: User,
        store_id: str,
        template_id: str,
        data: EmailTemplateUpdate,
    ) -> dict:
        row = db.get(EmailTemplate, template_id)
        if not row or row.store_id != store_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
        self._ensure_store(db, user, store_id)
        if data.name is not None:
            row.name = data.name
        if data.subject is not None:
            row.subject = data.subject
        if data.body_html is not None:
            row.body_html = data.body_html
        if data.layout_preset is not None:
            row.layout_preset = self._normalize_layout(data.layout_preset)
        db.commit()
        db.refresh(row)
        return self._serialize(row)

    def delete_template(self, db: Session, user: User, store_id: str, template_id: str) -> None:
        row = db.get(EmailTemplate, template_id)
        if not row or row.store_id != store_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
        self._ensure_store(db, user, store_id)
        db.delete(row)
        db.commit()
