from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.db.models import User
from app.db.session import get_db
from app.models.ads import AdsMetaTestRequest, AdsReportGenerateRequest, AdsSettingsUpdate
from app.services.ads_service import AdsService

router = APIRouter()
_service = AdsService()


@router.get("/stores/{store_id}/overview")
async def ads_overview(
    store_id: str,
    period: str = Query("30d", pattern="^(7d|30d|90d)$"),
    run_scheduled: bool = Query(False),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    if run_scheduled:
        await _service.maybe_run_scheduled_reports(db, user, store_id)
    return await _service.get_dashboard(db, user, store_id, period)


@router.get("/stores/{store_id}/settings")
async def get_ads_settings(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.get_settings(db, user, store_id)


@router.put("/stores/{store_id}/settings")
async def update_ads_settings(
    store_id: str,
    body: AdsSettingsUpdate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.update_settings(db, user, store_id, body.model_dump(exclude_unset=True))


@router.post("/stores/{store_id}/test-meta")
async def test_meta_connection(
    store_id: str,
    body: AdsMetaTestRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.test_meta_connection(
        db, user, store_id, body.model_dump(exclude_unset=True)
    )


@router.get("/stores/{store_id}/reports")
async def list_ads_reports(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.list_reports(db, user, store_id)


@router.post("/stores/{store_id}/reports/generate")
async def generate_ads_report(
    store_id: str,
    body: AdsReportGenerateRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.generate_ai_report(
        db,
        user,
        store_id,
        report_type=body.report_type,
        period=body.period,
    )
