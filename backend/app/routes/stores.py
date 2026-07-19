from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.config import settings
from app.db.models import User
from app.db.session import get_db
from app.models.store import StoreSettingsUpdate
from app.services.store_service import StoreService

router = APIRouter()
_stores = StoreService()


@router.get("")
async def list_stores(
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _stores.list_stores(db, user)


@router.get("/shopify/install")
async def shopify_install(
    shop: str = Query(..., description="myshopify.com domain"),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    url = _stores.begin_shopify_install(db, user, shop)
    return {"authorize_url": url}


@router.get("/shopify/callback")
async def shopify_callback(
    shop: str = Query(...),
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    _, store = await _stores.complete_shopify_oauth(db, shop, code, state)
    return RedirectResponse(
        f"{settings.frontend_url}/settings/stores?connected=1&store_id={store.id}"
    )


@router.get("/{store_id}")
async def get_store(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    store = _stores.get_store(db, user, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


@router.patch("/{store_id}/settings")
async def update_store_settings(
    store_id: str,
    data: StoreSettingsUpdate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    store = _stores.update_settings(db, user, store_id, data)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


@router.post("/{store_id}/disconnect")
async def disconnect_store(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    if not _stores.disconnect_store(db, user, store_id):
        raise HTTPException(status_code=404, detail="Store not found")
    return {"message": "Store disconnected"}
