"""Structured outputs for the Director's model calls. Lenient defaults; guards run after parsing."""

from __future__ import annotations

import json
import logging
import re
import types
from typing import Any, ClassVar, Union, get_args, get_origin

from pydantic import BaseModel, Field, ValidationError, model_validator

logger = logging.getLogger(__name__)

_MISSING = object()
_INT_RE = re.compile(r"[-+]?\d+")


def _label(value: Any, limit: int = 255) -> str:
    text = "" if value is None else str(value).strip()
    return text[:limit]


def _parse_json_container(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if len(text) < 2 or text[0] not in "[{":
        return value
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return value
    return parsed if isinstance(parsed, (dict, list)) else value


def _strip_optional(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _as_str(value: Any, limit: int = 4000) -> Any:
    if isinstance(value, str):
        return value.strip()[:limit]
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and value == value:
        return str(value)[:limit]
    if isinstance(value, dict):
        for key in ("name", "label", "value", "text", "input_value", "title", "hook", "description", "why"):
            if value.get(key) not in (None, "", [], {}):
                return _as_str(value[key], limit)
        return _MISSING
    if isinstance(value, list):
        parts = [piece for item in value if (piece := _as_str(item, limit)) not in (_MISSING, "")]
        return "\n".join(parts)[:limit]
    return _MISSING


def _as_int(value: Any) -> Any:
    if isinstance(value, bool):
        return _MISSING
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == value:
        return int(value)
    if isinstance(value, str):
        match = _INT_RE.search(value.strip())
        if match:
            return int(match.group(0))
    if isinstance(value, list) and value:
        return _as_int(value[0])
    return _MISSING


def _as_bool(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"true", "yes", "y", "1"}:
            return True
        if token in {"false", "no", "n", "0"}:
            return False
    return _MISSING


def _as_float(value: Any) -> Any:
    if isinstance(value, bool):
        return _MISSING
    if isinstance(value, (int, float)) and value == value:
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return _MISSING
    return _MISSING


def _is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _string_to_model(model: type[BaseModel], text: str) -> dict[str, Any]:
    text = text.strip()
    fields = model.model_fields
    if len(text) > 80 and "summary" in fields:
        return {"summary": text}
    if "why" in fields and "ad_type" in fields and len(text) > 40:
        return {"why": text}
    if "notes" in fields and "verdict" in fields and len(text) > 20:
        return {"notes": [text]}
    for name, field in fields.items():
        if _strip_optional(field.annotation) is str:
            return {name: text}
    return {}


def _as_model(value: Any, model: type[BaseModel]) -> Any:
    value = _parse_json_container(value)
    if isinstance(value, model):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        return _string_to_model(model, value)
    if isinstance(value, list):
        if len(value) == 1 and isinstance(value[0], dict):
            return value[0]
        for name, field in model.model_fields.items():
            if get_origin(_strip_optional(field.annotation)) is list:
                return {name: value}
    return _MISSING


def _as_list(value: Any, inner: Any) -> Any:
    value = _parse_json_container(value)
    if isinstance(value, dict):
        if _is_model(inner) and value and all(isinstance(item, dict) for item in value.values()):
            items = list(value.values())
        else:
            items = [value]
    elif isinstance(value, list):
        items = value
    elif value is None or value == "":
        return _MISSING
    else:
        items = [value]
    cleaned: list[Any] = []
    for item in items:
        if item is None:
            continue
        coerced = _coerce(item, inner)
        if coerced is _MISSING or coerced == "":
            continue
        cleaned.append(coerced)
    return cleaned


def _coerce(value: Any, annotation: Any) -> Any:
    value = _parse_json_container(value)
    if value is None:
        return _MISSING
    annotation = _strip_optional(annotation)
    origin = get_origin(annotation)
    if annotation is str:
        return _as_str(value)
    if annotation is int:
        return _as_int(value)
    if annotation is bool:
        return _as_bool(value)
    if annotation is float:
        return _as_float(value)
    if origin is list:
        args = get_args(annotation)
        return _as_list(value, args[0] if args else str)
    if _is_model(annotation):
        return _as_model(value, annotation)
    return value


class LenientModel(BaseModel):
    """Accept the shapes models actually return. Guards still run after parsing."""

    _aliases: ClassVar[dict[str, tuple[str, ...]]] = {}

    @model_validator(mode="before")
    @classmethod
    def soften(cls, data: Any) -> Any:
        if isinstance(data, list):
            for name, field in cls.model_fields.items():
                if get_origin(_strip_optional(field.annotation)) is list:
                    data = {name: data}
                    break
            else:
                return {}
        elif isinstance(data, str) and data.strip():
            data = _string_to_model(cls, data)
        if data is None or not isinstance(data, dict):
            return {}
        out = dict(data)
        for field, aliases in cls._aliases.items():
            if out.get(field) not in (None, "", [], {}):
                continue
            for key in aliases:
                if out.get(key) not in (None, "", [], {}):
                    out[field] = out[key]
                    break
        for name, field in cls.model_fields.items():
            if name not in out:
                continue
            coerced = _coerce(out[name], field.annotation)
            if coerced is _MISSING:
                out.pop(name, None)
            else:
                out[name] = coerced
        return out

    @model_validator(mode="wrap")
    @classmethod
    def accept_any(cls, data: Any, handler):
        try:
            return handler(data)
        except ValidationError:
            logger.warning("director schema %s fell back to defaults after invalid model output", cls.__name__)
            try:
                return handler({})
            except ValidationError:
                return cls.model_construct()


def _fill(data: dict[str, Any], field: str, aliases: tuple[str, ...], fallback: str) -> dict[str, Any]:
    current = _label(data.get(field))
    if current:
        return data if current == data.get(field) else {**data, field: current}
    for key in aliases:
        alt = _label(data.get(key))
        if alt:
            return {**data, field: alt}
    return {**data, field: fallback}


_SEGMENT_TYPES = {
    "interest": "interest",
    "lookalike": "lookalike",
    "retargeting": "retargeting",
    "retarget": "retargeting",
    "broad": "broad",
}


class DirectorScript(LenientModel):
    first_two_seconds: str = ""
    lines: list[str] = Field(default_factory=list)
    cta: str = ""
    language: str = ""


class DirectorConcept(LenientModel):
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


class AudienceIdea(LenientModel):
    name: str = ""
    segment_type: str = "interest"
    description: str = ""
    why: str = ""

    @model_validator(mode="before")
    @classmethod
    def ensure_fields(cls, data: Any) -> Any:
        """Models often send type/input_value instead of segment_type/name."""
        if not isinstance(data, dict):
            return data
        data = _fill(data, "name", ("input_value", "value", "label", "title", "audience"), "Audience")
        raw = _label(data.get("segment_type")) or _label(data.get("type"))
        token = raw.lower().replace("-", " ").replace("_", " ").split()[0] if raw else ""
        segment = _SEGMENT_TYPES.get(token, "interest")
        if data.get("segment_type") == segment:
            return data
        return {**data, "segment_type": segment}


class OfferIdea(LenientModel):
    label: str = ""
    offer_id: str = ""
    description: str = ""
    why: str = ""

    _aliases: ClassVar[dict[str, tuple[str, ...]]] = {"offer_id": ("id",)}

    @model_validator(mode="before")
    @classmethod
    def ensure_label(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        return _fill(data, "label", ("name", "input_value", "value", "title", "offer"), "Offer")


class IdeationResult(LenientModel):
    concepts: list[DirectorConcept] = Field(default_factory=list)
    audience_ideas: list[AudienceIdea] = Field(default_factory=list)
    offer_ideas: list[OfferIdea] = Field(default_factory=list)

    _aliases: ClassVar[dict[str, tuple[str, ...]]] = {
        "concepts": ("ideas", "ad_concepts", "concept_ideas"),
        "audience_ideas": ("audiences", "audienceIdeas"),
        "offer_ideas": ("offers", "offerIdeas"),
    }


class ConceptReview(LenientModel):
    index: int = -1
    brand_fit: int = 3
    novelty: int = 3
    predicted_performance: int = 3
    production_cost: int = 3
    risk: int = 2
    keep: bool = True
    verdict: str = ""
    improved_hook: str = ""

    _aliases: ClassVar[dict[str, tuple[str, ...]]] = {
        "index": ("i", "idx", "concept_index", "position", "candidate"),
    }


class BriefPick(LenientModel):
    index: int = -1
    reason: str = ""

    _aliases: ClassVar[dict[str, tuple[str, ...]]] = {
        "index": ("i", "idx", "concept_index", "position", "candidate"),
    }


class WeeklyBrief(LenientModel):
    headline: str = ""
    summary: str = ""
    picks: list[BriefPick] = Field(default_factory=list)
    testing_plan: str = ""
    naming_convention: str = ""
    budget_note: str = ""


class PlaybookUpdate(LenientModel):
    hypothesis_id: str = ""
    status: str = "open"
    evidence: str = ""

    _aliases: ClassVar[dict[str, tuple[str, ...]]] = {
        "hypothesis_id": ("id", "hypothesis", "hypothesisId"),
    }

    @model_validator(mode="before")
    @classmethod
    def normalize_status(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        status = _label(data.get("status")).lower()
        if not status or status == data.get("status"):
            return data
        return {**data, "status": status}


class CritiqueResult(LenientModel):
    reviews: list[ConceptReview] = Field(default_factory=list)
    brief: WeeklyBrief = Field(default_factory=WeeklyBrief)
    playbook_updates: list[PlaybookUpdate] = Field(default_factory=list)

    _aliases: ClassVar[dict[str, tuple[str, ...]]] = {
        "reviews": ("concept_reviews", "review"),
        "brief": ("weekly_brief", "weeklyBrief"),
        "playbook_updates": ("playbook", "updates", "playbookUpdates"),
    }

    @model_validator(mode="after")
    def fill_missing_indexes(self) -> CritiqueResult:
        for position, review in enumerate(self.reviews):
            if review.index < 0:
                review.index = position
        for position, pick in enumerate(self.brief.picks):
            if pick.index < 0:
                pick.index = position
        self.playbook_updates = [item for item in self.playbook_updates if item.hypothesis_id.strip()]
        return self


class ChallengeAlternative(LenientModel):
    ad_type: str = ""
    hook: str = ""
    angle: str = ""
    audience: str = ""
    product_id: str = ""
    why: str = ""


class ChallengeResult(LenientModel):
    verdict: str = "go"
    notes: list[str] = Field(default_factory=list)
    alternative: ChallengeAlternative | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_verdict(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        token = _label(data.get("verdict")).lower()
        if token in {"reconsider", "revise", "no", "stop", "weak"}:
            verdict = "reconsider"
        elif token in {"go", "yes", "ok", "okay", "approve", "approved"}:
            verdict = "go"
        else:
            return data
        if verdict == data.get("verdict"):
            return data
        return {**data, "verdict": verdict}
