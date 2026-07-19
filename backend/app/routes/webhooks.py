import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Store, StoreStatus, WebhookLog
from app.db.session import get_db
from app.email_automation.services.trigger_service import EmailTriggerService
from app.integrations.shopify.client import ShopifyClient
from app.tracking.enrichment_service import CarrierEnrichmentService
from app.tracking.order_sync import OrderTrackingSyncService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/shopify")
async def shopify_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256", "")
    if not ShopifyClient.verify_webhook_hmac(body, hmac_header):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    topic = request.headers.get("X-Shopify-Topic", "unknown")
    shop_domain = request.headers.get("X-Shopify-Shop-Domain", "")

    store = db.scalar(select(Store).where(Store.shop_domain == shop_domain))
    store_id = store.id if store else None

    preview = body.decode("utf-8", errors="replace")[:2000]
    db.add(
        WebhookLog(
            store_id=store_id,
            topic=topic,
            shop_domain=shop_domain,
            payload_preview=preview,
        )
    )

    if topic == "app/uninstalled" and store:
        store.access_token_encrypted = None
        store.status = StoreStatus.DISCONNECTED.value

    db.commit()

    automation_results: list[dict] = []
    if store and topic != "app/uninstalled":
        try:
            payload = json.loads(body)
            order_row = OrderTrackingSyncService(db).upsert_from_webhook(store.id, topic, payload)
            db.commit()

            if order_row and order_row.tracking_number:
                try:
                    await CarrierEnrichmentService(db).enrich_if_enabled(store.id, order_row.id)
                    db.commit()
                except Exception:
                    logger.exception(
                        "Carrier enrichment failed for store %s order %s",
                        store.id,
                        order_row.id,
                    )

            trigger = EmailTriggerService(db)
            automation_results = await trigger.process_shopify_webhook(
                store_id=store.id,
                topic=topic,
                payload=payload,
            )
        except json.JSONDecodeError:
            logger.warning("Invalid JSON webhook payload for %s", shop_domain)
        except Exception:
            logger.exception("Email automation failed for %s topic %s", shop_domain, topic)

    return {"ok": True, "automation": automation_results}
