"""Store-level email branding (theme color + logo)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.models import Store, User
from app.email_automation.layout_presets import DEFAULT_THEME_COLOR

_HEX_COLOR_RE = re.compile(r"^#?[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?$")
_ALLOWED_LOGO_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB


def uploads_root() -> Path:
    # backend/data/uploads (stable next to sqlite db)
    root = Path(__file__).resolve().parents[3] / "data" / "uploads" / "email-logos"
    root.mkdir(parents=True, exist_ok=True)
    return root


class EmailBrandingService:
    def _ensure_store(self, db: Session, user: User, store_id: str) -> Store:
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
        return store

    def _public_logo_url(self, logo_path: str | None) -> str | None:
        if not logo_path:
            return None
        path = logo_path.strip()
        if path.startswith("http://") or path.startswith("https://") or path.startswith("data:"):
            return path
        if not path.startswith("/"):
            path = f"/{path}"
        # Don't return a broken preview URL when the file is missing on disk.
        file_path = uploads_root() / Path(path).name
        if not file_path.is_file():
            return None
        return path

    def serialize(self, store: Store) -> dict:
        return {
            "store_id": store.id,
            "theme_color": getattr(store, "email_theme_color", None) or DEFAULT_THEME_COLOR,
            "logo_url": self._public_logo_url(getattr(store, "email_logo_path", None)),
        }

    def get_branding(self, db: Session, user: User, store_id: str) -> dict:
        store = self._ensure_store(db, user, store_id)
        return self.serialize(store)

    def update_theme_color(
        self, db: Session, user: User, store_id: str, theme_color: str
    ) -> dict:
        store = self._ensure_store(db, user, store_id)
        color = theme_color.strip()
        if not _HEX_COLOR_RE.match(color):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="theme_color must be a hex color like #0d9488",
            )
        if not color.startswith("#"):
            color = f"#{color}"
        # Expand short hex
        if len(color) == 4:
            color = f"#{color[1]*2}{color[2]*2}{color[3]*2}"
        store.email_theme_color = color.lower()
        db.commit()
        db.refresh(store)
        return self.serialize(store)

    def _delete_logo_file(self, logo_path: str | None) -> None:
        if not logo_path:
            return
        # logo_path stored as /uploads/email-logos/filename
        name = Path(logo_path).name
        file_path = uploads_root() / name
        if file_path.is_file():
            try:
                file_path.unlink()
            except OSError:
                pass

    async def upload_logo(
        self, db: Session, user: User, store_id: str, file: UploadFile
    ) -> dict:
        store = self._ensure_store(db, user, store_id)
        content_type = (file.content_type or "").lower()
        ext = _ALLOWED_LOGO_TYPES.get(content_type)
        if not ext:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Logo must be PNG, JPG, WEBP, or GIF",
            )
        data = await file.read()
        if not data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
        if len(data) > _MAX_LOGO_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Logo must be 2 MB or smaller",
            )

        self._delete_logo_file(store.email_logo_path)
        filename = f"{store_id}-{uuid.uuid4().hex[:8]}{ext}"
        dest = uploads_root() / filename
        dest.write_bytes(data)
        store.email_logo_path = f"/uploads/email-logos/{filename}"
        db.commit()
        db.refresh(store)
        return self.serialize(store)

    def remove_logo(self, db: Session, user: User, store_id: str) -> dict:
        store = self._ensure_store(db, user, store_id)
        self._delete_logo_file(store.email_logo_path)
        store.email_logo_path = None
        db.commit()
        db.refresh(store)
        return self.serialize(store)
