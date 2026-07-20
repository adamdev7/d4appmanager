from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.db.models import User
from app.db.session import get_db
from app.models.analytics import (
    AnalyticsSettingsUpdate,
    MetaTestRequest,
    MetaTestResponse,
    ProductCostsUpdate,
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
