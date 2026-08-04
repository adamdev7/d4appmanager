"""Pydantic schemas for Meta Conversions API settings / stats."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MetaCapiSettingsUpdate(BaseModel):
    enabled: bool | None = None
    meta_pixel_id: str | None = None
    meta_access_token: str | None = None
    clear_access_token: bool | None = None
    test_event_code: str | None = None
    clear_test_event_code: bool | None = None
    event_id_scheme: str | None = Field(
        default=None,
        description="order_id | checkout_token | order_name — must match browser Pixel",
    )
    trigger_topic: str | None = Field(
        default=None,
        description="orders/paid | orders/create",
    )
    api_version: str | None = None
    use_analytics_token: bool | None = Field(
        default=None,
        description="If true, fall back to Analytics Meta Marketing token when CAPI token empty",
    )
    send_initiate_checkout: bool | None = None
    rotate_browser_event_token: bool | None = None


class MetaCapiTestRequest(BaseModel):
    meta_pixel_id: str | None = None
    meta_access_token: str | None = None
    test_event_code: str | None = None


class MetaCapiBackfillOrderRequest(BaseModel):
    """Send one past Shopify order to Meta CAPI (missed before tracking was enabled)."""

    order_ref: str = Field(
        ...,
        description="Shopify order id (numeric) or order name like #1042 / 1042",
    )
    force: bool = Field(
        default=False,
        description="Re-send even if this order was already marked sent",
    )


class MetaCapiBackfillRecentRequest(BaseModel):
    """Backfill paid orders from the last N hours that were never sent to Meta."""

    hours: int = Field(default=24, ge=1, le=168)
    limit: int = Field(default=50, ge=1, le=100)


class MetaCapiBrowserEventRequest(BaseModel):
    event_name: str
    event_id: str
    event_source_url: str | None = None
    value: float | None = None
    currency: str | None = None
    content_ids: list[str] | None = None
    contents: list[dict] | None = None
    num_items: int | None = None
    email: str | None = None
    phone: str | None = None
    fbp: str | None = None
    fbc: str | None = None
    fbclid: str | None = None
    external_id: str | None = None
    client_ip_address: str | None = None
    client_user_agent: str | None = None
