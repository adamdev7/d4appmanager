from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.db.models import User
from app.db.session import get_db
from app.models.analytics import (
    AnalyticsSettingsUpdate,
    MetaTestRequest,
    MetaTestResponse,
    MrrWebhookPayload,
    ProductCostsUpdate,
    StripeAccountCreate,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter()
_service = AnalyticsService()


@router.get("/stores/{store_id}/overview")
async def analytics_overview(
    store_id: str,
    period: str = Query("30d", pattern="^(7d|30d|90d|all)$"),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.get_dashboard(db, user, store_id, period)


@router.get("/stores/{store_id}/settings")
async def get_analytics_settings(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.get_settings(db, user, store_id)


@router.put("/stores/{store_id}/settings")
async def update_analytics_settings(
    store_id: str,
    body: AnalyticsSettingsUpdate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.update_settings(db, user, store_id, body.model_dump(exclude_unset=True))


@router.post("/stores/{store_id}/test-meta", response_model=MetaTestResponse)
async def test_meta_connection(
    store_id: str,
    body: MetaTestRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.test_meta_connection(db, user, store_id, body.model_dump(exclude_unset=True))


@router.get("/stores/{store_id}/products")
async def list_analytics_products(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.get_products(db, user, store_id)


@router.put("/stores/{store_id}/products/costs")
async def update_product_costs(
    store_id: str,
    body: ProductCostsUpdate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    items = [item.model_dump() for item in body.items]
    return _service.update_product_costs(db, user, store_id, items)


@router.post("/stores/{store_id}/stripe-accounts")
async def add_stripe_account(
    store_id: str,
    body: StripeAccountCreate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.add_stripe_account(db, user, store_id, body.model_dump())


@router.delete("/stores/{store_id}/stripe-accounts/{account_id}")
async def delete_stripe_account(
    store_id: str,
    account_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.delete_stripe_account(db, user, store_id, account_id)


@router.post("/stores/{store_id}/mrr/sync-stripe")
async def sync_mrr_from_stripe(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.sync_mrr_from_stripe(db, user, store_id)


@router.post("/stores/{store_id}/mrr/webhook")
async def mrr_webhook(
    store_id: str,
    body: MrrWebhookPayload,
    db: Session = Depends(get_db),
    x_mrr_webhook_secret: str | None = Header(default=None, alias="X-MRR-Webhook-Secret"),
):
    """Public webhook for Phoenix / Zapier / scripts to push current MRR."""
    return _service.ingest_mrr_webhook(
        db, store_id, x_mrr_webhook_secret or "", body.model_dump()
    )
