from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ProductImage(BaseModel):
    src: str | None = None
    alt: str | None = None
    width: int | None = None
    height: int | None = None


class ProductVariant(BaseModel):
    id: str | None = None
    title: str | None = None
    price: str | None = None
    sku: str | None = None
    available: bool | None = None


class ProductContext(BaseModel):
    product_id: str
    title: str
    description: str = ""
    price: float | None = None
    currency: str | None = None
    product_url: str | None = None
    images: list[ProductImage] = Field(default_factory=list)
    variants: list[ProductVariant] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    brand_context: dict[str, Any] = Field(default_factory=dict)
    target_market: dict[str, Any] = Field(default_factory=dict)
    restrictions: list[str] = Field(default_factory=list)


class NormalizedMetaCreative(BaseModel):
    campaign_id: str | None = None
    campaign_name: str | None = None
    adset_id: str | None = None
    adset_name: str | None = None
    ad_id: str | None = None
    ad_name: str | None = None
    creative_id: str | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    video_id: str | None = None
    video_thumbnail: str | None = None
    primary_text: str | None = None
    headline: str | None = None
    description: str | None = None
    cta: str | None = None
    destination_url: str | None = None
    format: Literal["IMAGE", "VIDEO", "CAROUSEL", "OTHER"] = "OTHER"
    width: int | None = None
    height: int | None = None
    aspect_ratio: str | None = None
    placement: list[str] | None = None
    creation_date: str | None = None
    creative_fingerprint: str | None = None


class PerformanceSummary(BaseModel):
    impressions: float | None = None
    reach: float | None = None
    clicks: float | None = None
    spend: float | None = None
    ctr: float | None = None
    cpc: float | None = None
    cpm: float | None = None
    purchases: float | None = None
    cpa: float | None = None
    conversion_value: float | None = None
    roas: float | None = None
    video_views: float | None = None
    video_watch: dict[str, Any] | None = None
    frequency: float | None = None
    date_range_start: str | None = None
    date_range_end: str | None = None
    insufficient_data: bool = False


class VisualDNA(BaseModel):
    style: str | None = None
    composition: str | None = None
    human_presence: bool | None = None
    product_visibility: str | None = None
    product_position: str | None = None
    framing: str | None = None
    background: str | None = None
    lighting: str | None = None
    text_overlay: bool | None = None
    promotional_elements: bool | None = None
    ugc_characteristics: bool | None = None
    visual_hook: str | None = None
    overall_style: str | None = None
    notes: str | None = None


class CopyDNA(BaseModel):
    hook_type: str | None = None
    tone: str | None = None
    cta: str | None = None
    offer_presentation: str | None = None
    notes: str | None = None


class FormatDNA(BaseModel):
    type: str | None = None
    aspect_ratio: str | None = None
    width: int | None = None
    height: int | None = None


class PerformanceDNA(BaseModel):
    ctr_percentile: float | None = None
    roas_percentile: float | None = None
    cpa_percentile: float | None = None
    spend_percentile: float | None = None

    @field_validator("ctr_percentile", "roas_percentile", "cpa_percentile", "spend_percentile")
    @classmethod
    def _pct_range(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if v < 0 or v > 1:
            raise ValueError("percentiles must be between 0 and 1 or omitted")
        return v


class CreativeDNAModel(BaseModel):
    visual_dna: VisualDNA = Field(default_factory=VisualDNA)
    copy_dna: CopyDNA = Field(default_factory=CopyDNA)
    format_dna: FormatDNA = Field(default_factory=FormatDNA)
    performance_dna: PerformanceDNA = Field(default_factory=PerformanceDNA)
    analysis_basis: str = "copy_only"
    observed: list[str] = Field(default_factory=list)
    interpretation: list[str] = Field(default_factory=list)


class PatternFinding(BaseModel):
    statement: str
    supporting_creative_ids: list[str] = Field(default_factory=list)
    kind: Literal["observed", "interpretation", "experiment"] = "observed"
    confidence: float | None = None


class IntelligenceRecommendation(BaseModel):
    title: str
    explanation: str
    supporting_creative_ids: list[str] = Field(default_factory=list)
    supporting_metrics: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    recommended_action: str = ""
    kind: Literal["observed", "interpretation", "experiment"] = "interpretation"


class CreativeIntelligenceReport(BaseModel):
    winning_creatives: list[str] = Field(default_factory=list)
    average_creatives: list[str] = Field(default_factory=list)
    losing_creatives: list[str] = Field(default_factory=list)
    visual_patterns: list[PatternFinding] = Field(default_factory=list)
    copy_patterns: list[PatternFinding] = Field(default_factory=list)
    hook_patterns: list[PatternFinding] = Field(default_factory=list)
    composition_patterns: list[PatternFinding] = Field(default_factory=list)
    product_presentation_patterns: list[PatternFinding] = Field(default_factory=list)
    format_patterns: list[PatternFinding] = Field(default_factory=list)
    recommendations: list[IntelligenceRecommendation] = Field(default_factory=list)
    hypotheses_to_test: list[str] = Field(default_factory=list)
    data_quality: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0


class CreativeStrategyModel(BaseModel):
    summary: str = ""
    target_audience: str = ""
    core_value_propositions: list[str] = Field(default_factory=list)
    winning_patterns: list[str] = Field(default_factory=list)
    creative_angles: list[str] = Field(default_factory=list)
    hook_directions: list[str] = Field(default_factory=list)
    visual_directions: list[str] = Field(default_factory=list)
    cta_directions: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class CreativeConceptModel(BaseModel):
    type: str = "IMAGE"
    concept_name: str
    angle: str = ""
    hook: str = ""
    headline: str = ""
    primary_text: str = ""
    cta: str = "SHOP_NOW"
    visual_direction: str = ""
    audience: str = ""
    objective: str = ""
    rationale: str = ""
    source_creative_ids: list[str] = Field(default_factory=list)
    expected_strength: str = ""
    portfolio_bucket: str = ""


class ConceptBatch(BaseModel):
    concepts: list[CreativeConceptModel] = Field(default_factory=list)


class VideoScene(BaseModel):
    duration: float = 2
    visual: str = ""
    voiceover: str = ""
    text_overlay: str = ""


class VideoSpec(BaseModel):
    duration: float = 15
    format: str = "9:16"
    hook: str = ""
    scenes: list[VideoScene] = Field(default_factory=list)
    voice_direction: str = ""
    music_direction: str = ""
    cta: str = ""


class AIScoreBreakdown(BaseModel):
    strategy_alignment: int = 0
    product_relevance: int = 0
    hook_strength: int = 0
    creative_diversity: int = 0
    visual_clarity: int = 0
    audience_relevance: int = 0
    objective_alignment: int = 0


class AICreativeScore(BaseModel):
    total: int = 0
    breakdown: AIScoreBreakdown = Field(default_factory=AIScoreBreakdown)
    label: str = "AI Creative Evaluation"
    disclaimer: str = "This is an evaluation of creative quality and alignment, not a guaranteed ROAS or performance prediction."


class ImageGenerationRequest(BaseModel):
    prompt: str
    aspect_ratio: str = "4:5"
    placement: str = "feed"
    reference_image_urls: list[str] = Field(default_factory=list)
    size: str | None = None


class ImageGenerationResult(BaseModel):
    status: str = "completed"
    local_path: str | None = None
    preview_url: str | None = None
    width: int | None = None
    height: int | None = None
    mime_type: str | None = None
    provider_id: str | None = None
    error: str | None = None
