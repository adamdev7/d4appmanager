from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.core.upload_limits import MAX_UPLOAD_PART_BYTES
from app.db.models import User
from app.db.session import get_db
from app.models.ai_ads import (
    AIAdsAdPackageRegenerateRequest,
    AIAdsAdPackageUpdate,
    AIAdsAvatarUpsert,
    AIAdsGenerationJobRequest,
    AIAdsPublishRequest,
    AIAdsSettingsUpdate,
    AIAdsStrategyRequest,
    DirectorDismissRequest,
    DirectorGenerateRequest,
    DirectorSaveAlternativeRequest,
    DirectorSettingsUpdate,
    DirectorSuggestionEdit,
)
from app.models.ai_email_assistant import OpenAIKeyStatusResponse, SetOpenAIKeyBody
from app.services.ai_ads.director.service import DirectorService
from app.services.ai_ads.service import AIAdsService

router = APIRouter()
_service = AIAdsService()
_director = DirectorService()


@router.get("/stores/{store_id}/overview")
async def overview(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.overview(db, user, store_id)


@router.get("/stores/{store_id}/products")
async def products(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.list_products(db, user, store_id)


@router.post("/stores/{store_id}/products/{product_id}/photos")
async def upload_product_photos(
    store_id: str,
    product_id: str,
    request: Request,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    form = await request.form(max_files=8, max_fields=20, max_part_size=MAX_UPLOAD_PART_BYTES)
    blobs: list[bytes] = []
    try:
        items = form.getlist("files") or list(form.values())
        for item in items[:8]:
            data: bytes | None = None
            if isinstance(item, (bytes, bytearray)):
                data = bytes(item)
            elif isinstance(item, str):
                continue
            elif hasattr(item, "read"):
                data = await item.read()
            if data and len(data) <= MAX_UPLOAD_PART_BYTES:
                blobs.append(data)
    finally:
        await form.close()
    if not blobs:
        raise HTTPException(
            status_code=400,
            detail="Choose a picture under 32 MB. PNG is fine — we convert and compress it here.",
        )
    card = _service.upload_product_photos(db, user, store_id, product_id, blobs)
    db.commit()
    return card


@router.get("/stores/{store_id}/products/{product_id}/photos/{image_key}")
async def get_product_photo(
    store_id: str,
    product_id: str,
    image_key: str,
    v: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Public image bytes for <img> tags. Self-heals from Shopify when the local cache is cold."""
    data, mime = await _service.product_photo(db, store_id, product_id, image_key)
    cache = "public, max-age=31536000, immutable" if v else "public, max-age=300"
    return Response(content=data, media_type=mime, headers={"Cache-Control": cache})


@router.delete("/stores/{store_id}/products/{product_id}/photos")
def clear_product_photos(
    store_id: str,
    product_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.clear_product_photos(db, user, store_id, product_id)


@router.post("/stores/{store_id}/sync-meta")
async def sync_meta(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.sync_meta(db, user, store_id)


@router.post("/stores/{store_id}/analyze")
async def analyze(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.analyze(db, user, store_id)


@router.post("/stores/{store_id}/strategy")
async def create_strategy(
    store_id: str,
    body: AIAdsStrategyRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.create_strategy(db, user, store_id, body.model_dump())


@router.get("/stores/{store_id}/strategy")
async def get_strategy(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.latest_strategy(db, user, store_id)


@router.post("/stores/{store_id}/generation-jobs")
async def create_job(
    store_id: str,
    body: AIAdsGenerationJobRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.create_generation_job(db, user, store_id, body.model_dump())


@router.get("/stores/{store_id}/generation-jobs")
async def list_jobs(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.list_jobs(db, user, store_id)


@router.get("/stores/{store_id}/generation-jobs/{job_id}")
async def get_job(
    store_id: str,
    job_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.get_job(db, user, store_id, job_id)


@router.post("/stores/{store_id}/generation-jobs/{job_id}/stop")
async def stop_job(
    store_id: str,
    job_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.stop_generation_job(db, user, store_id, job_id)


@router.post("/stores/{store_id}/generation-jobs/{job_id}/restart")
async def restart_job(
    store_id: str,
    job_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.restart_generation_job(db, user, store_id, job_id)


@router.post("/stores/{store_id}/generation-jobs/{job_id}/nudge")
async def nudge_job(
    store_id: str,
    job_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.nudge_generation_job(db, user, store_id, job_id)


@router.post("/stores/{store_id}/generation-jobs/{job_id}/sweep")
async def sweep_job(
    store_id: str,
    job_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.sweep_generation_job(db, user, store_id, job_id)


@router.get("/stores/{store_id}/generation-jobs/{job_id}/creatives")
async def job_creatives(
    store_id: str,
    job_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.job_creatives(db, user, store_id, job_id)


@router.get("/stores/{store_id}/creatives")
async def list_creatives(
    store_id: str,
    source: str | None = Query(None),
    status: str | None = Query(None),
    type: str | None = Query(None),
    product_id: str | None = Query(None),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.list_creatives(
        db, user, store_id, source=source, status=status, type=type, product_id=product_id
    )


@router.get("/stores/{store_id}/creatives/{creative_id}")
async def get_creative(
    store_id: str,
    creative_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.get_creative(db, user, store_id, creative_id)


@router.post("/stores/{store_id}/creatives/{creative_id}/approve")
async def approve_creative(
    store_id: str,
    creative_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.set_status(db, user, store_id, creative_id, "APPROVED")


@router.post("/stores/{store_id}/creatives/{creative_id}/reject")
async def reject_creative(
    store_id: str,
    creative_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.set_status(db, user, store_id, creative_id, "REJECTED")


@router.post("/stores/{store_id}/creatives/{creative_id}/regenerate")
async def regenerate_creative(
    store_id: str,
    creative_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.regenerate(db, user, store_id, creative_id)


@router.post("/stores/{store_id}/creatives/{creative_id}/ad-package")
async def regenerate_ad_package(
    store_id: str,
    creative_id: str,
    body: AIAdsAdPackageRegenerateRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.regenerate_ad_package(db, user, store_id, creative_id, body.model_dump())


@router.put("/stores/{store_id}/creatives/{creative_id}/ad-package")
async def save_ad_package(
    store_id: str,
    creative_id: str,
    body: AIAdsAdPackageUpdate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.save_ad_package(db, user, store_id, creative_id, body.package)


@router.delete("/stores/{store_id}/creatives/{creative_id}")
async def delete_creative(
    store_id: str,
    creative_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.delete_creative(db, user, store_id, creative_id)


@router.get("/stores/{store_id}/adsets")
async def list_adsets(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.list_adsets(db, user, store_id)


@router.post("/stores/{store_id}/creatives/{creative_id}/publish")
async def publish_creative(
    store_id: str,
    creative_id: str,
    body: AIAdsPublishRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.publish(db, user, store_id, creative_id, body.model_dump())


@router.get("/stores/{store_id}/performance")
async def performance(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.performance(db, user, store_id)


@router.get("/stores/{store_id}/recommendations")
async def recommendations(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.recommendations(db, user, store_id)


@router.get("/stores/{store_id}/settings")
async def get_settings(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.get_settings(db, user, store_id)


@router.put("/stores/{store_id}/settings")
async def update_settings(
    store_id: str,
    body: AIAdsSettingsUpdate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.update_settings(db, user, store_id, body.model_dump(exclude_unset=True))


@router.get("/stores/{store_id}/weekly-runs")
async def list_weekly_runs(
    store_id: str,
    limit: int = 20,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.list_weekly_runs(db, user, store_id, limit=limit)


@router.post("/stores/{store_id}/weekly-runs/run-now")
async def run_weekly_now(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.run_weekly_now(db, user, store_id)


@router.get("/stores/{store_id}/director")
async def director_overview(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _director.overview(db, user, store_id)


@router.post("/stores/{store_id}/director/run")
async def director_run(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _director.run_now(db, user, store_id)


@router.put("/stores/{store_id}/director/settings")
async def director_settings(
    store_id: str,
    body: DirectorSettingsUpdate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _director.update_settings(db, user, store_id, body.model_dump(exclude_unset=True))


@router.patch("/stores/{store_id}/director/suggestions/{suggestion_id}")
async def director_edit_suggestion(
    store_id: str,
    suggestion_id: str,
    body: DirectorSuggestionEdit,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _director.edit_suggestion(db, user, store_id, suggestion_id, body.model_dump(exclude_unset=True))


@router.post("/stores/{store_id}/director/suggestions/{suggestion_id}/dismiss")
async def director_dismiss(
    store_id: str,
    suggestion_id: str,
    body: DirectorDismissRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _director.dismiss(db, user, store_id, suggestion_id, body.reason)


@router.post("/stores/{store_id}/director/suggestions/{suggestion_id}/save")
async def director_save(
    store_id: str,
    suggestion_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _director.save_for_later(db, user, store_id, suggestion_id)


@router.post("/stores/{store_id}/director/suggestions/{suggestion_id}/generate")
async def director_generate(
    store_id: str,
    suggestion_id: str,
    body: DirectorGenerateRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _director.generate(db, user, store_id, suggestion_id, override_cap=body.override_cap)


@router.post("/stores/{store_id}/director/challenge")
async def director_challenge(
    store_id: str,
    body: AIAdsGenerationJobRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _director.challenge(db, user, store_id, body.model_dump())


@router.post("/stores/{store_id}/director/challenge/save-alternative")
async def director_save_alternative(
    store_id: str,
    body: DirectorSaveAlternativeRequest,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _director.save_alternative(db, user, store_id, body.model_dump())


@router.get("/openai-key", response_model=OpenAIKeyStatusResponse)
async def get_ai_ads_openai_key(
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.get_openai_key_status(db, user)


@router.put("/openai-key", response_model=OpenAIKeyStatusResponse)
async def save_ai_ads_openai_key(
    body: SetOpenAIKeyBody,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.save_openai_key(db, user, body.api_key)


@router.delete("/openai-key", response_model=OpenAIKeyStatusResponse)
async def delete_ai_ads_openai_key(
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.delete_openai_key(db, user)


@router.get("/stores/{store_id}/avatars")
async def list_avatars(
    store_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.list_avatars(db, user, store_id)


@router.put("/stores/{store_id}/avatars")
async def upsert_avatar(
    store_id: str,
    body: AIAdsAvatarUpsert,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.upsert_avatar(db, user, store_id, body.model_dump())
