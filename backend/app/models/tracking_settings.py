from pydantic import BaseModel, Field


class TrackingSettingsResponse(BaseModel):
    store_id: str
    carrier_mode: str
    auto_enrich_enabled: bool
    yunexpress_api_url: str
    yunexpress_customer_code: str | None
    yunexpress_carrier_keywords: str
    track17_configured: bool
    track17_key_masked: str | None
    yunexpress_configured: bool
    yunexpress_key_masked: str | None
    uses_server_track17_fallback: bool
    uses_server_yunexpress_fallback: bool


class TrackingSettingsUpdate(BaseModel):
    carrier_mode: str | None = Field(
        default=None,
        description="auto | 17track | yunexpress | shopify_only",
    )
    auto_enrich_enabled: bool | None = None
    yunexpress_api_url: str | None = None
    yunexpress_customer_code: str | None = None
    yunexpress_carrier_keywords: str | None = None
    track17_api_key: str | None = Field(
        default=None,
        description="New key, or empty string to remove",
    )
    yunexpress_api_key: str | None = Field(
        default=None,
        description="New key, or empty string to remove",
    )


class CarrierTestRequest(BaseModel):
    provider: str = Field(description="17track or yunexpress")
    tracking_number: str | None = Field(
        default=None,
        description="Optional sample tracking number to query",
    )


class CarrierTestResponse(BaseModel):
    ok: bool
    provider: str
    message: str
    status: str | None = None
