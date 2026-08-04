"""Meta Conversions API (server-side Purchase tracking) routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.db.models import User
from app.db.session import get_db
from app.models.meta_capi import MetaCapiSettingsUpdate, MetaCapiTestRequest
from app.services.meta_capi_service import MetaCapiService

router = APIRouter()
_service = MetaCapiService()


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
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return {"events": _service.list_events(db, user, store_id, limit=limit)}


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
