"""Meta Conversions API (server-side Purchase tracking) routes."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.core.rate_limit import RateLimiter, client_ip
from app.db.models import User
from app.db.session import get_db
from app.models.meta_capi import (
    MetaCapiBackfillOrderRequest,
    MetaCapiBackfillRecentRequest,
    MetaCapiBrowserEventRequest,
    MetaCapiSettingsUpdate,
    MetaCapiTestRequest,
)
from app.services.meta_capi_service import MetaCapiService

router = APIRouter()
_service = MetaCapiService()
_browser_rate_limiter = RateLimiter()


@router.get("/stores/{store_id}/stats")
async def meta_capi_stats(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.get_stats(db, user, store_id)


@router.get("/stores/{store_id}/events")
async def meta_capi_events(
    store_id: str,
    limit: int = Query(100, ge=1, le=500),
    event_name: str | None = Query(None, description="Filter by event type, e.g. Purchase, PageView"),
    status: str | None = Query(None, description="Filter by status: sent, failed, pending, skipped"),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.list_events(
        db, user, store_id, limit=limit, event_name=event_name, status=status
    )


@router.get("/stores/{store_id}/settings")
async def get_meta_capi_settings(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.get_settings(db, user, store_id)


@router.put("/stores/{store_id}/settings")
async def update_meta_capi_settings(
    store_id: str,
    body: MetaCapiSettingsUpdate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.update_settings(db, user, store_id, body.model_dump(exclude_unset=True))


@router.post("/stores/{store_id}/test")
async def test_meta_capi(
    store_id: str,
    body: MetaCapiTestRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.test_connection(
        db, user, store_id, body.model_dump(exclude_unset=True)
    )


@router.post("/stores/{store_id}/backfill")
async def backfill_meta_capi_order(
    store_id: str,
    body: MetaCapiBackfillOrderRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """Send one past Shopify order to Meta (for sales missed before CAPI was enabled)."""
    return await _service.backfill_order(
        db, user, store_id, body.model_dump(exclude_unset=True)
    )


@router.post("/stores/{store_id}/backfill-recent")
async def backfill_meta_capi_recent(
    store_id: str,
    body: MetaCapiBackfillRecentRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """Send paid Shopify orders from the last N hours that were never sent to Meta."""
    return await _service.backfill_recent(
        db, user, store_id, body.model_dump(exclude_unset=True)
    )


@router.post("/stores/{store_id}/browser-event")
async def meta_capi_browser_event(
    store_id: str,
    body: MetaCapiBrowserEventRequest,
    request: Request,
    db: Session = Depends(get_db),
    token: str = Query(..., description="Store browser_event_token from CAPI settings"),
):
    """Theme/Customer Events beacon for ViewContent / AddToCart (no JWT; token-gated)."""
    _browser_rate_limiter.check(
        f"meta_capi_browser:ip:{client_ip(request)}",
        limit=120,
        window_seconds=60,
    )
    _browser_rate_limiter.check(
        f"meta_capi_browser:store:{store_id}",
        limit=300,
        window_seconds=60,
    )
    return await _service.ingest_browser_event(
        db,
        store_id=store_id,
        token=token,
        body=body.model_dump(exclude_unset=True),
        client_ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
