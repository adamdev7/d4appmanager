from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.db.models import User
from app.db.session import get_db
from app.services.dashboard_service import DashboardService

router = APIRouter()
_dashboard = DashboardService()


@router.get("")
async def list_modules(
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _dashboard.get_app_modules(db, user)
