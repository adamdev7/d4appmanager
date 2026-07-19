"""Public track-your-order API for Shopify storefront pages."""

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.tracking.track_service import TrackOrderService

router = APIRouter()


def _cors_headers(origin: str | None) -> dict[str, str]:
    """Allow Shopify storefront origins to call this endpoint from the browser."""
    headers: dict[str, str] = {
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Accept, ngrok-skip-browser-warning",
        "Access-Control-Max-Age": "86400",
    }
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Vary"] = "Origin"
    else:
        headers["Access-Control-Allow-Origin"] = "*"
    return headers


@router.options("/track-order")
async def track_order_preflight(request: Request):
    return JSONResponse(content={}, headers=_cors_headers(request.headers.get("origin")))


@router.get("/track-order")
async def track_order(
    request: Request,
    order_number: str = Query(..., min_length=1),
    email: str = Query(..., min_length=3),
    store_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    service = TrackOrderService(db)
    result = await service.track(
        store_id=store_id,
        order_number=order_number,
        email=email,
    )
    if not result:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Order not found. Check your order number and email."},
            headers=_cors_headers(request.headers.get("origin")),
        )
    return JSONResponse(content=result, headers=_cors_headers(request.headers.get("origin")))
