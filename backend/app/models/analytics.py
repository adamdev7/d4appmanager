from pydantic import BaseModel, Field


class AnalyticsSettingsUpdate(BaseModel):
    meta_access_token: str | None = None
    meta_ad_account_id: str | None = None
    default_shipping_cost: float | None = None
    transaction_fee_percent: float | None = None
    transaction_fee_fixed: float | None = None


class MetaTestRequest(BaseModel):
    meta_access_token: str | None = None
    meta_ad_account_id: str | None = None


class MetaTestResponse(BaseModel):
    ok: bool
    message: str
    account_name: str | None = None


class ProductCostItem(BaseModel):
    shopify_product_id: str
    shopify_variant_id: str
    cost_per_unit: float = Field(ge=0)


class ProductCostsUpdate(BaseModel):
    items: list[ProductCostItem]
