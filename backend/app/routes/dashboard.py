from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.db.models import User
from app.db.session import get_db
from app.services.dashboard_service import DashboardService

router = APIRouter()
_dashboard = DashboardService()


@router.get("/overview")
async def overview(
    store_id: str | None = Query(default=None),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _dashboard.get_overview(db, user, store_id)


@router.get("/activity")
async def activity(
    store_id: str | None = Query(default=None),
    limit: int = Query(default=10, le=50),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _dashboard.get_activity_feed(db, user, store_id, limit)
