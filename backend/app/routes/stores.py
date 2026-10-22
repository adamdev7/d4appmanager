from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.config import settings
from app.db.models import User
from app.db.session import get_db
from app.models.store import ShopifyClaimRequest, StoreSettingsUpdate
from app.services.store_service import (
    LAUNCH_STATE_TTL_SECONDS,
    SHOPIFY_STATE_COOKIE,
    StoreService,
)

router = APIRouter()
_stores = StoreService()
_STATE_COOKIE_PATH = f"{settings.api_prefix}/stores/shopify"


@router.get("")
async def list_stores(
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _stores.list_stores(db, user)


@router.get("/shopify/install-link")
async def shopify_install_link(user: User = Depends(get_verified_user)):
    return {"url": _stores.shopify_install_link(user)}


@router.get("/shopify/launch")
async def shopify_launch(request: Request, db: Session = Depends(get_db)):
    """App URL configured in the Shopify Dev Dashboard."""
    url, state = _stores.handle_shopify_launch(db, dict(request.query_params))
    response = RedirectResponse(url, status_code=302)
    if state:
        response.set_cookie(
            SHOPIFY_STATE_COOKIE,
            state,
            max_age=LAUNCH_STATE_TTL_SECONDS,
            path=_STATE_COOKIE_PATH,
            httponly=True,
            secure=True,
            samesite="lax",
        )
    return response


@router.get("/shopify/callback")
async def shopify_callback(request: Request, db: Session = Depends(get_db)):
    url = await _stores.complete_shopify_oauth(
        db, dict(request.query_params), request.cookies.get(SHOPIFY_STATE_COOKIE)
    )
    response = RedirectResponse(url, status_code=302)
    response.delete_cookie(SHOPIFY_STATE_COOKIE, path=_STATE_COOKIE_PATH)
    return response


@router.post("/shopify/claim")
async def claim_shopify_install(
    data: ShopifyClaimRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _stores.claim_shopify_install(db, user, data.claim)


@router.post("/{store_id}/shopify/reauthorize")
async def reauthorize_shopify_store(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return {"authorize_url": _stores.begin_shopify_reauthorize(db, user, store_id)}


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


@router.post("/{store_id}/delete")
async def delete_store(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    if not _stores.delete_store(db, user, store_id):
        raise HTTPException(status_code=404, detail="Store not found")
    return {"message": "Store deleted"}
