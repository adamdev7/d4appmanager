"""Personal WhatsApp alerts for the store owner (CallMeBot).

One connection per user, shared by AI Email Assistant, AI Ads, and any later
module. Each module only stores its own on/off flag.
Setup guide: https://www.callmebot.com/blog/free-api-whatsapp-messages/
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_value, encrypt_value
from app.db.models import (
    AIEmailAssistantSettings,
    CreativeAsset,
    CreativeConcept,
    CreativeGenerationJob,
    ShopifyCatalogProduct,
    Store,
    StoreAIAdsSettings,
    User,
    UserWhatsAppSettings,
)

logger = logging.getLogger(__name__)

CALLMEBOT_GUIDE_URL = "https://www.callmebot.com/blog/free-api-whatsapp-messages/"
CALLMEBOT_API_URL = "https://api.callmebot.com/whatsapp.php"
ALLOW_MESSAGE = "I allow callmebot to send me messages"

MODULE_EMAIL = "AI Email Assistant"
MODULE_ADS = "AI Ads"

_PHONE_KEEP = re.compile(r"[^\d+]+")


@dataclass
class WhatsAppSendResult:
    ok: bool
    error: str | None = None


def normalize_whatsapp_phone(raw: str | None) -> str:
    """International number for CallMeBot, e.g. +15145550100."""
    cleaned = _PHONE_KEEP.sub("", (raw or "").strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if cleaned and not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    digits = re.sub(r"\D", "", cleaned)
    if len(digits) < 8:
        return ""
    return "+" + digits


def mask_whatsapp_api_key(api_key: str | None) -> str | None:
    key = (api_key or "").strip()
    if not key:
        return None
    if len(key) <= 4:
        return "••••"
    return f"••••{key[-4:]}"


def mask_whatsapp_phone(raw: str | None) -> str:
    number = normalize_whatsapp_phone(raw)
    if len(number) < 8:
        return number
    return number[:3] + "••••" + number[-4:]


def format_manual_review_alert(
    *,
    business_name: str,
    sender: str,
    sender_email: str,
    subject: str,
    reason: str,
) -> str:
    store = (business_name or "Your store").strip() or "Your store"
    who = (sender or sender_email or "a customer").strip()
    subj = (subject or "(no subject)").strip()
    why = (reason or "Needs an admin").strip()
    return (
        f"*Manual review needed* — {store}\n"
        f"From: {who}\n"
        f"Subject: {subj}\n"
        f"Why: {why}\n\n"
        "Open App Manager → AI Email Assistant → Manual review to reply."
    )


def format_weekly_ads_recap(
    *,
    store_name: str,
    status: str,
    product_title: str,
    image_count: int,
    video_count: int,
    items: list[str],
    failed_count: int = 0,
    error: str | None = None,
) -> str:
    store = (store_name or "Your store").strip() or "Your store"
    status_key = (status or "").strip().upper()
    if status_key == "COMPLETED":
        headline = "This week's ads are ready"
    elif status_key == "PARTIAL":
        headline = "This week's ads are partly ready"
    else:
        headline = "This week's ads run did not finish"

    stills = f"{image_count} still" + ("" if image_count == 1 else "s")
    clips = f"{video_count} video" + ("" if video_count == 1 else "s")
    lines = [
        f"*{headline}* — {store}",
        f"Made: {stills}, {clips}",
    ]
    product = (product_title or "").strip()
    if product:
        lines.append(f"Product: {product}")
    for item in items[:6]:
        label = (item or "").strip()
        if label:
            lines.append(f"• {label}")
    if failed_count:
        lines.append(f"{failed_count} creative(s) failed.")
    if error and status_key == "FAILED":
        lines.append(f"Error: {error.strip()[:180]}")
    lines.append("")
    lines.append("Nothing was published. Open App Manager → AI Ads → Library to review.")
    return "\n".join(lines)


async def send_callmebot_whatsapp(
    *,
    phone: str,
    api_key: str,
    text: str,
    timeout_seconds: float = 20,
) -> WhatsAppSendResult:
    number = normalize_whatsapp_phone(phone)
    key = (api_key or "").strip()
    body = (text or "").strip()
    if not number:
        return WhatsAppSendResult(ok=False, error="Enter your WhatsApp number with country code.")
    if not key:
        return WhatsAppSendResult(ok=False, error="Paste the CallMeBot API key from WhatsApp.")
    if not body:
        return WhatsAppSendResult(ok=False, error="Message is empty.")

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.get(
                CALLMEBOT_API_URL,
                params={"phone": number, "text": body, "apikey": key},
            )
    except httpx.TimeoutException:
        return WhatsAppSendResult(
            ok=False,
            error="WhatsApp timed out. CallMeBot can be slow — try the test again in a minute.",
        )
    except httpx.HTTPError as exc:
        logger.warning("CallMeBot request failed: %s", exc)
        return WhatsAppSendResult(ok=False, error="Could not reach WhatsApp (CallMeBot). Try again.")

    payload = (resp.text or "").strip()
    lowered = payload.lower()
    rejected = (
        resp.status_code >= 400
        or "apikey is invalid" in lowered
        or lowered.startswith("error")
        or " error:" in lowered[:80]
    )
    if rejected:
        detail = payload[:180] if payload else f"HTTP {resp.status_code}"
        return WhatsAppSendResult(
            ok=False,
            error=f"CallMeBot rejected the send: {detail}",
        )
    return WhatsAppSendResult(ok=True)


_EMPTY_PUBLIC = {
    "whatsapp_configured": False,
    "whatsapp_phone": "",
    "whatsapp_api_key_hint": None,
    "whatsapp_last_error": None,
    "whatsapp_setup_url": CALLMEBOT_GUIDE_URL,
    "whatsapp_allow_message": ALLOW_MESSAGE,
    "whatsapp_connected_modules": [],
}


def _repair_whatsapp_schema() -> None:
    from app.db.session import _migrate_shared_whatsapp_connection

    _migrate_shared_whatsapp_connection()


def get_whatsapp_connection(db: Session, user: User) -> UserWhatsAppSettings | None:
    """Existing shared connection, or None. Never commits — callers own the transaction."""
    try:
        return _load_whatsapp_connection(db, user)
    except Exception:
        logger.exception("WhatsApp connection lookup failed")
        db.rollback()
        try:
            _repair_whatsapp_schema()
            return _load_whatsapp_connection(db, user)
        except Exception:
            logger.exception("WhatsApp connection lookup failed after schema repair")
            db.rollback()
            return None


def _load_whatsapp_connection(db: Session, user: User) -> UserWhatsAppSettings | None:
    row = db.scalar(select(UserWhatsAppSettings).where(UserWhatsAppSettings.user_id == user.id))
    if not row:
        imported = UserWhatsAppSettings(user_id=user.id)
        _import_legacy_email_credentials(db, user, imported)
        if not imported.api_key_encrypted:
            return None
        db.add(imported)
        db.flush()
        return imported
    if not row.api_key_encrypted:
        _import_legacy_email_credentials(db, user, row)
    return row


def get_or_create_whatsapp_connection(db: Session, user: User) -> UserWhatsAppSettings:
    row = get_whatsapp_connection(db, user)
    if row:
        return row
    row = UserWhatsAppSettings(user_id=user.id)
    db.add(row)
    db.flush()
    return row


def _import_legacy_email_credentials(
    db: Session, user: User, row: UserWhatsAppSettings
) -> None:
    """First-time share: copy a key saved earlier on AI Email Assistant (leftover columns)."""
    try:
        bind = db.get_bind()
        insp = inspect(bind)
        if "ai_email_assistant_settings" not in insp.get_table_names():
            return
        cols = {c["name"] for c in insp.get_columns("ai_email_assistant_settings")}
        if "whatsapp_api_key_encrypted" not in cols:
            return
        legacy = db.execute(
            text(
                """
                SELECT whatsapp_phone, whatsapp_api_key_encrypted,
                       whatsapp_api_key_hint, whatsapp_last_error
                FROM ai_email_assistant_settings
                WHERE user_id = :uid AND whatsapp_api_key_encrypted IS NOT NULL
                LIMIT 1
                """
            ),
            {"uid": user.id},
        ).mappings().first()
    except Exception:
        logger.exception("Legacy WhatsApp credential import skipped")
        return
    if not legacy or not legacy["whatsapp_api_key_encrypted"]:
        return
    row.phone = normalize_whatsapp_phone(legacy["whatsapp_phone"])
    row.api_key_encrypted = legacy["whatsapp_api_key_encrypted"]
    row.api_key_hint = legacy["whatsapp_api_key_hint"]
    row.last_error = legacy["whatsapp_last_error"]


def save_whatsapp_connection(
    db: Session,
    user: User,
    *,
    phone: str | None = None,
    api_key: str | None = None,
) -> UserWhatsAppSettings:
    row = get_or_create_whatsapp_connection(db, user)
    if phone is not None:
        cleaned = normalize_whatsapp_phone(phone)
        if cleaned:
            row.phone = cleaned
    new_key = (api_key or "").strip()
    if new_key:
        row.api_key_encrypted = encrypt_value(new_key)
        row.api_key_hint = mask_whatsapp_api_key(new_key)
        row.last_error = None
    return row


def _module_flag_on(db: Session, stmt) -> bool:
    try:
        return bool(db.scalar(stmt))
    except Exception:
        logger.exception("WhatsApp module flag lookup failed")
        db.rollback()
        try:
            _repair_whatsapp_schema()
            return bool(db.scalar(stmt))
        except Exception:
            logger.exception("WhatsApp module flag lookup failed after schema repair")
            db.rollback()
            return False


def whatsapp_enabled_modules(db: Session, user: User) -> list[str]:
    labels: list[str] = []
    if _module_flag_on(
        db,
        select(AIEmailAssistantSettings.id).where(
            AIEmailAssistantSettings.user_id == user.id,
            AIEmailAssistantSettings.whatsapp_alerts_enabled.is_(True),
        ),
    ):
        labels.append(MODULE_EMAIL)
    if _module_flag_on(
        db,
        select(StoreAIAdsSettings.id)
        .join(Store, Store.id == StoreAIAdsSettings.store_id)
        .where(
            Store.owner_id == user.id,
            StoreAIAdsSettings.whatsapp_weekly_alerts_enabled.is_(True),
        ),
    ):
        labels.append(MODULE_ADS)
    return labels


def whatsapp_public_payload(db: Session, user: User) -> dict:
    """Safe for settings GET — never raises, never commits."""
    try:
        row = get_whatsapp_connection(db, user)
        return {
            "whatsapp_configured": bool(row and row.api_key_encrypted and row.phone),
            "whatsapp_phone": (row.phone if row else "") or "",
            "whatsapp_api_key_hint": row.api_key_hint if row else None,
            "whatsapp_last_error": row.last_error if row else None,
            "whatsapp_setup_url": CALLMEBOT_GUIDE_URL,
            "whatsapp_allow_message": ALLOW_MESSAGE,
            "whatsapp_connected_modules": whatsapp_enabled_modules(db, user),
        }
    except Exception:
        logger.exception("WhatsApp settings payload failed")
        try:
            db.rollback()
        except Exception:
            pass
        return dict(_EMPTY_PUBLIC)


async def send_user_whatsapp(
    db: Session, user: User, text: str
) -> WhatsAppSendResult:
    try:
        row = get_whatsapp_connection(db, user)
    except Exception:
        logger.exception("WhatsApp send aborted: connection lookup failed")
        try:
            db.rollback()
        except Exception:
            pass
        return WhatsAppSendResult(ok=False, error="WhatsApp is not available right now.")
    if not row:
        return WhatsAppSendResult(
            ok=False,
            error="WhatsApp alerts are on, but the phone number or API key is missing.",
        )
    phone = normalize_whatsapp_phone(row.phone)
    if not phone or not row.api_key_encrypted:
        result = WhatsAppSendResult(
            ok=False,
            error="WhatsApp alerts are on, but the phone number or API key is missing.",
        )
        row.last_error = result.error
        db.commit()
        return result
    try:
        api_key = decrypt_value(row.api_key_encrypted)
    except ValueError:
        result = WhatsAppSendResult(
            ok=False,
            error="Could not read the saved WhatsApp API key. Paste it again in Settings.",
        )
        row.last_error = result.error
        db.commit()
        return result

    result = await send_callmebot_whatsapp(phone=phone, api_key=api_key, text=text)
    row.last_error = None if result.ok else result.error
    db.commit()
    return result


def _job_is_weekly(job: CreativeGenerationJob) -> bool:
    try:
        request = json.loads(job.request_json or "{}")
    except json.JSONDecodeError:
        return False
    return str(request.get("source") or "") == "weekly_automation"


def _product_title(db: Session, store_id: str, product_id: str | None) -> str:
    if not product_id:
        return ""
    row = db.scalar(
        select(ShopifyCatalogProduct).where(
            ShopifyCatalogProduct.store_id == store_id,
            ShopifyCatalogProduct.shopify_product_id == str(product_id),
        )
    )
    return (row.title if row else "") or ""


def _weekly_recap_items(db: Session, job: CreativeGenerationJob) -> tuple[int, int, list[str], int]:
    assets = db.scalars(
        select(CreativeAsset).where(CreativeAsset.job_id == job.id)
    ).all()
    ready = [a for a in assets if (a.status or "").upper() != "FAILED"]
    failed = sum(1 for a in assets if (a.status or "").upper() == "FAILED")
    images = sum(1 for a in ready if (a.type or "").upper() == "IMAGE")
    videos = sum(1 for a in ready if (a.type or "").upper() == "VIDEO")
    items: list[str] = []
    for asset in ready[:6]:
        kind = "Still" if (asset.type or "").upper() == "IMAGE" else "Video"
        label = kind
        if asset.concept_id:
            concept = db.get(CreativeConcept, asset.concept_id)
            name = ((concept.concept_name if concept else "") or (concept.headline if concept else "") or "").strip()
            if name:
                label = f"{kind}: {name}"
        items.append(label)
    if not items and job.completed_items:
        images = images or max(0, int(job.completed_items) - videos)
    return images, videos, items, failed


async def notify_weekly_ads_generation(
    db: Session,
    user: User,
    store: Store,
    job: CreativeGenerationJob,
) -> None:
    """Ping the owner when a weekly AI Ads batch finishes. Failures are stored, not raised."""
    if not _job_is_weekly(job):
        return
    if (job.status or "").upper() not in {"COMPLETED", "PARTIAL", "FAILED"}:
        return
    try:
        ads = db.scalar(select(StoreAIAdsSettings).where(StoreAIAdsSettings.store_id == store.id))
    except Exception:
        logger.exception("WhatsApp weekly recap skipped: could not load AI Ads settings")
        db.rollback()
        return
    if not ads or not getattr(ads, "whatsapp_weekly_alerts_enabled", False):
        return
    images, videos, items, failed = _weekly_recap_items(db, job)
    text = format_weekly_ads_recap(
        store_name=store.name,
        status=job.status,
        product_title=_product_title(db, store.id, job.product_id),
        image_count=images,
        video_count=videos,
        items=items,
        failed_count=failed,
        error=job.error_message,
    )
    result = await send_user_whatsapp(db, user, text)
    if not result.ok:
        logger.warning(
            "WhatsApp weekly ads recap failed store=%s job=%s err=%s",
            store.id,
            job.id,
            result.error,
        )
