from pydantic import BaseModel, Field


class AdsSettingsUpdate(BaseModel):
    """Ads module prefs. Meta token/account can also be saved here (shared with Analytics)."""

    meta_access_token: str | None = None
    meta_ad_account_id: str | None = None
    ai_reports_consent: bool | None = None
    daily_ai_reports: bool | None = None
    weekly_ai_reports: bool | None = None


class AdsMetaTestRequest(BaseModel):
    meta_access_token: str | None = None
    meta_ad_account_id: str | None = None


class AdsReportGenerateRequest(BaseModel):
    report_type: str = Field(default="on_demand", pattern="^(daily|weekly|on_demand)$")
    period: str = Field(
        default="7d",
        pattern="^(1d|7d|14d|30d|90d|all|custom)$",
    )
    since: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    until: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
