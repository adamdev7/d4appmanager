from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AIAdsSettingsUpdate(BaseModel):
    weekly_generation_enabled: bool | None = None
    generation_day: str | None = None
    image_count: int | None = Field(default=None, ge=0)
    video_count: int | None = Field(default=None, ge=0)
    auto_publish: bool | None = None
    winner_pct: float | None = Field(default=None, ge=0, le=1)
    combination_pct: float | None = Field(default=None, ge=0, le=1)
    exploration_pct: float | None = Field(default=None, ge=0, le=1)
    experimental_pct: float | None = Field(default=None, ge=0, le=1)
    brand_style: str | None = None
    default_audience: str | None = None
    default_objective: str | None = None
    default_placement: str | None = None
    default_aspect_ratio: str | None = None
    creative_styles: list[str] | None = None
    meta_page_id: str | None = None
    whatsapp_weekly_alerts_enabled: bool | None = None
    text_model: str | None = None

    @field_validator("image_count")
    @classmethod
    def _cap_images(cls, v: int | None) -> int | None:
        if v is None:
            return v
        return max(0, min(int(v), 8))

    @field_validator("video_count")
    @classmethod
    def _cap_videos(cls, v: int | None) -> int | None:
        if v is None:
            return v
        return max(0, min(int(v), 4))


class AIAdsStrategyRequest(BaseModel):
    product_id: str
    audience: str | None = None
    objective: str | None = None
    brand_style: str | None = None


class AIAdsGenerationJobRequest(BaseModel):
    product_id: str
    image_count: int = Field(default=2, ge=0)
    video_count: int = Field(default=1, ge=0)
    styles: list[str] | None = None
    audience: str | None = None
    objective: str | None = None
    placement: str | None = None
    aspect_ratio: str | None = None
    brand_style: str | None = None
    avatar_id: str | None = None
    copy_language: Literal["auto", "en", "fr"] | None = None

    @field_validator("image_count")
    @classmethod
    def _cap_images(cls, v: int) -> int:
        return max(0, min(int(v), 8))

    @field_validator("video_count")
    @classmethod
    def _cap_videos(cls, v: int) -> int:
        return max(0, min(int(v), 4))


class AIAdsAvatarUpsert(BaseModel):
    id: str | None = None
    name: str = ""
    image_url: str | None = None
    description: str = ""
    usage_rules: str = ""
    active: bool = True


class AIAdsPublishRequest(BaseModel):
    adset_id: str
    page_id: str | None = None
    activate: bool = False


class AIAdsAdPackageRegenerateRequest(BaseModel):
    """Omit `field` to regenerate the whole package. `field` examples: headline, primary_text_variants.1."""

    language: Literal["auto", "en", "fr"] | None = None
    field: str | None = None


class AIAdsAdPackageUpdate(BaseModel):
    package: dict[str, Any]


class DirectorOffer(BaseModel):
    id: str | None = None
    label: str = ""
    details: str = ""


class DirectorSettingsUpdate(BaseModel):
    enabled: bool | None = None
    drive_weekly: bool | None = None
    challenge_requests: bool | None = None
    aggressiveness: Literal["safe", "balanced", "bold"] | None = None
    weekly_credit_cap_usd: float | None = Field(default=None, ge=0, le=10000)
    priority_product_ids: list[str] | None = None
    excluded_product_ids: list[str] | None = None
    offers: list[DirectorOffer] | None = None
    never_do: list[str] | None = None
    margin_floor_pct: float | None = Field(default=None, ge=0, le=95)
    low_stock_threshold: int | None = Field(default=None, ge=0, le=1000)
    copy_language: Literal["auto", "en", "fr"] | None = None


class DirectorSuggestionEdit(BaseModel):
    concept_name: str | None = None
    ad_type: str | None = None
    product_id: str | None = None
    hook: str | None = None
    angle: str | None = None
    audience: str | None = None
    hypothesis: str | None = None
    test_design: str | None = None
    image_count: int | None = Field(default=None, ge=0, le=4)
    video_count: int | None = Field(default=None, ge=0, le=2)


class DirectorDismissRequest(BaseModel):
    reason: str = ""


class DirectorGenerateRequest(BaseModel):
    override_cap: bool = False


class DirectorSaveAlternativeRequest(BaseModel):
    alternative: dict[str, Any]
    request: dict[str, Any] = Field(default_factory=dict)
