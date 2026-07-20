from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai_email_assistant.services.assistant_service import AIEmailAssistantService
from app.auth.dependencies import get_verified_user
from app.db.models import User
from app.db.session import get_db
from app.models.ai_email_assistant import (
    AIEmailAssistantSettingsResponse,
    AIEmailAssistantSettingsUpdate,
    AIEmailAssistantStatsResponse,
    AIReplyResponse,
    AutomationRunResponse,
    FullHistoryScanRequest,
    FullHistoryScanResponse,
    OpenAIKeyStatusResponse,
    SetOpenAIKeyBody,
    SyncInboxRequest,
    UpdateReplyDraftBody,
)

router = APIRouter()
_service = AIEmailAssistantService()


@router.get("/openai-key", response_model=OpenAIKeyStatusResponse)
async def get_openai_key_status(
    user: User = Depends(get_verified_user),
):
    return _service.get_openai_key_status(user)


@router.put("/openai-key", response_model=OpenAIKeyStatusResponse)
async def save_openai_key(
    body: SetOpenAIKeyBody,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.save_openai_key(db, user, body)


@router.delete("/openai-key", response_model=OpenAIKeyStatusResponse)
async def delete_openai_key(
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.delete_openai_key(db, user)


@router.get("/settings", response_model=AIEmailAssistantSettingsResponse)
async def get_settings(
    store_id: str | None = Query(default=None),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.get_settings_response(db, user, store_id)


@router.put("/settings", response_model=AIEmailAssistantSettingsResponse)
async def update_settings(
    data: AIEmailAssistantSettingsUpdate,
    store_id: str | None = Query(default=None),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.update_settings(db, user, data, store_id)


@router.get("/inbox")
async def list_inbox(
    store_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.list_inbox(db, user, store_id=store_id, limit=limit)


@router.post("/automation/run", response_model=AutomationRunResponse)
async def run_automation_now(
    store_id: str | None = Query(default=None),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    result = await _service.run_automation_now(db, user, store_id)
    return AutomationRunResponse(
        ok=result.get("ok", False),
        processed=result.get("processed", 0),
        skipped=result.get("skipped", False),
        stopped=result.get("stopped", False),
        reason=result.get("reason"),
        error=result.get("error"),
    )


@router.post("/inbox/sync")
async def sync_inbox(
    body: SyncInboxRequest,
    store_id: str | None = Query(default=None),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.sync_inbox(
        db,
        user,
        gmail_account_id=body.gmail_account_id,
        store_id=store_id,
        max_results=body.max_results,
    )


@router.post("/inbox/full-scan", response_model=FullHistoryScanResponse)
async def full_history_scan(
    body: FullHistoryScanRequest,
    store_id: str | None = Query(default=None),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """Start a background full-history scan (returns immediately to avoid gateway timeouts)."""
    return await _service.start_full_history_scan(
        db,
        user,
        gmail_account_id=body.gmail_account_id,
        store_id=store_id,
        max_threads=body.max_threads,
        confirmed=body.confirmed,
    )


@router.get("/inbox/full-scan/status", response_model=FullHistoryScanResponse)
async def full_history_scan_status(
    store_id: str | None = Query(default=None),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.get_full_scan_status(db, user, store_id=store_id)


@router.post("/inbox/{inbox_email_id}/unskip")
async def unskip_email(
    inbox_email_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.unskip_email(db, user, inbox_email_id)


@router.post("/inbox/{inbox_email_id}/generate", response_model=AIReplyResponse)
async def generate_reply(
    inbox_email_id: str,
    store_id: str | None = Query(default=None),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.generate_and_maybe_send(db, user, inbox_email_id, store_id=store_id)


@router.post("/replies/{reply_id}/approve", response_model=AIReplyResponse)
async def approve_reply(
    reply_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.approve_and_send(db, user, reply_id)


@router.post("/replies/{reply_id}/reject", response_model=AIReplyResponse)
async def reject_reply(
    reply_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return await _service.reject_reply(db, user, reply_id)


@router.patch("/replies/{reply_id}", response_model=AIReplyResponse)
async def update_reply_draft(
    reply_id: str,
    body: UpdateReplyDraftBody,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.update_draft(db, user, reply_id, body.body)


@router.get("/stats", response_model=AIEmailAssistantStatsResponse)
async def get_stats(
    store_id: str | None = Query(default=None),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.get_stats(db, user, store_id=store_id)


@router.get("/logs")
async def list_ai_logs(
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _service.list_reply_logs(db, user, limit=limit)
