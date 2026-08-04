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


class MetaCapiTestRequest(BaseModel):
    meta_pixel_id: str | None = None
    meta_access_token: str | None = None
    test_event_code: str | None = None
