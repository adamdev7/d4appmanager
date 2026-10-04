"""Structured outputs for the Director's model calls. Lenient defaults; guards run after parsing."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class DirectorScript(BaseModel):
    first_two_seconds: str = ""
    lines: list[str] = Field(default_factory=list)
    cta: str = ""
    language: str = ""


def _label(value: Any, limit: int = 255) -> str:
    text = "" if value is None else str(value).strip()
    return text[:limit]


class DirectorConcept(BaseModel):
    concept_name: str = ""
    kind: str = "new"
    ad_type: str = "LIFESTYLE"
    product_id: str = ""
    image_count: int = 1
    video_count: int = 0
    hook: str = ""
    hook_type: str = "other"
    angle: str = ""
    emotion: str = ""
    setting: str = ""
    pacing: str = ""
    funnel: str = "prospecting"
    audience: str = ""
    occasion: str = ""
    why: str = ""
    data_points: list[str] = Field(default_factory=list)
    hypothesis: str = ""
    test_variable: str = ""
    test_design: str = ""
    is_wildcard: bool = False
    offer_ids: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    source_creative_id: str = ""
    script: DirectorScript | None = None

    @model_validator(mode="before")
    @classmethod
    def ensure_concept_name(cls, data: Any) -> Any:
        """Models often omit concept_name. Derive a label so ideation still parses."""
        if not isinstance(data, dict):
            return data
        name = _label(data.get("concept_name"))
        if not name:
            for key in ("name", "title", "concept", "headline"):
                name = _label(data.get(key))
                if name:
                    break
        if not name:
            name = _label(data.get("hook"), 120) or _label(data.get("angle"), 120)
        if not name:
            ad_type = _label(data.get("ad_type"), 40).replace("_", " ")
            name = ad_type.title() if ad_type else "Concept"
        if name == data.get("concept_name"):
            return data
        return {**data, "concept_name": name}


class AudienceIdea(BaseModel):
    name: str
    segment_type: str = "interest"
    description: str = ""
    why: str = ""


class OfferIdea(BaseModel):
    label: str
    offer_id: str = ""
    description: str = ""
    why: str = ""


class IdeationResult(BaseModel):
    concepts: list[DirectorConcept] = Field(default_factory=list)
    audience_ideas: list[AudienceIdea] = Field(default_factory=list)
    offer_ideas: list[OfferIdea] = Field(default_factory=list)


class ConceptReview(BaseModel):
    index: int
    brand_fit: int = 3
    novelty: int = 3
    predicted_performance: int = 3
    production_cost: int = 3
    risk: int = 2
    keep: bool = True
    verdict: str = ""
    improved_hook: str = ""


class BriefPick(BaseModel):
    index: int
    reason: str = ""


class WeeklyBrief(BaseModel):
    headline: str = ""
    summary: str = ""
    picks: list[BriefPick] = Field(default_factory=list)
    testing_plan: str = ""
    naming_convention: str = ""
    budget_note: str = ""


class PlaybookUpdate(BaseModel):
    hypothesis_id: str
    status: str = "open"
    evidence: str = ""


class CritiqueResult(BaseModel):
    reviews: list[ConceptReview] = Field(default_factory=list)
    brief: WeeklyBrief = Field(default_factory=WeeklyBrief)
    playbook_updates: list[PlaybookUpdate] = Field(default_factory=list)


class ChallengeAlternative(BaseModel):
    ad_type: str = ""
    hook: str = ""
    angle: str = ""
    audience: str = ""
    product_id: str = ""
    why: str = ""


class ChallengeResult(BaseModel):
    verdict: str = "go"
    notes: list[str] = Field(default_factory=list)
    alternative: ChallengeAlternative | None = None
