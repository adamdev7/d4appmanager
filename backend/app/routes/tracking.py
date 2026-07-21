from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.db.models import User
from app.db.session import get_db
from app.models.tracking_settings import (
    CarrierTestRequest,
    CarrierTestResponse,
    TrackingSettingsUpdate,
)
from app.services.tracking_service import TrackingService
from app.tracking.enrichment_service import CarrierEnrichmentService

router = APIRouter()
_service = TrackingService()


@router.get("/stores/{store_id}/overview")
async def tracking_overview(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.get_overview(db, user, store_id)


@router.get("/stores/{store_id}/settings")
async def get_tracking_settings(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.get_settings(db, user, store_id)


@router.put("/stores/{store_id}/settings")
async def update_tracking_settings(
    store_id: str,
    body: TrackingSettingsUpdate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.update_settings(db, user, store_id, body.model_dump(exclude_unset=True))


@router.post("/stores/{store_id}/sync")
async def sync_shopify_orders(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """Pull recent orders from the connected Shopify store into tracking."""
    return await _service.sync_from_shopify(db, user, store_id)


@router.post("/stores/{store_id}/test-carrier", response_model=CarrierTestResponse)
async def test_carrier_api(
    store_id: str,
    body: CarrierTestRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    _service._ensure_store(db, user, store_id)
    provider = body.provider.strip().lower()
    if provider not in ("17track", "yunexpress"):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="provider must be 17track or yunexpress")

    result = await CarrierEnrichmentService(db).test_provider(
        store_id,
        provider,
        body.tracking_number,
    )
    return CarrierTestResponse(provider=provider, **result)
