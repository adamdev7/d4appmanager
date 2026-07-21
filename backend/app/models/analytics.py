from pydantic import BaseModel, Field


class AnalyticsSettingsUpdate(BaseModel):
    meta_access_token: str | None = None
    meta_ad_account_id: str | None = None
    default_shipping_cost: float | None = None
    transaction_fee_percent: float | None = None
    transaction_fee_fixed: float | None = None
    analytics_start_date: str | None = None  # YYYY-MM-DD or "" to clear
    prior_external_revenue: float | None = None
    prior_external_costs: float | None = None
    prior_external_label: str | None = None
    mrr_enabled: bool | None = None
    mrr_source: str | None = None  # manual | multi_stripe
    mrr_manual_amount: float | None = None
    mrr_manual_subscribers: int | None = None
    mrr_manual_churn_pct: float | None = None
    regenerate_mrr_webhook_secret: bool | None = None


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


class StripeAccountCreate(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    secret_key: str = Field(min_length=8)


class StripeAccountTestRequest(BaseModel):
    secret_key: str | None = None
    account_id: str | None = None


class MrrWebhookPayload(BaseModel):
    """Push MRR from Phoenix / Zapier / custom scripts."""

    mrr: float = Field(ge=0)
    subscribers: int = Field(ge=0, default=0)
    churn_pct: float = Field(ge=0, default=0)
    snapshot_date: str | None = None  # YYYY-MM-DD
    note: str | None = None
