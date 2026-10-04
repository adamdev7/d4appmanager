from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.db.models import User
from app.db.session import get_db
from app.services.connections_service import ConnectionsService

router = APIRouter()
_service = ConnectionsService()


class MetaConnectionUpdate(BaseModel):
    meta_access_token: str | None = None
    clear_access_token: bool = False
    meta_ad_account_id: str | None = None
    meta_pixel_id: str | None = None


class MetaConnectionTest(BaseModel):
    meta_access_token: str | None = None
    meta_ad_account_id: str | None = None


@router.get("/models")
async def list_text_models(user: User = Depends(get_verified_user)):
    _ = user
    return _service.text_models()


@router.get("/meta")
async def get_meta_connection(
    store_id: str = Query(...),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.get_meta(db, user, store_id)


@router.put("/meta")
async def update_meta_connection(
    body: MetaConnectionUpdate,
    store_id: str = Query(...),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.update_meta(db, user, store_id, body.model_dump())


@router.post("/meta/test")
async def test_meta_connection(
    body: MetaConnectionTest,
    store_id: str = Query(...),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.test_meta(db, user, store_id, body.model_dump())
