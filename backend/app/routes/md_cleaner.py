"""MD Cleaner: strip AI provenance metadata from pictures before they are uploaded to Meta.

Uploads are processed in memory and never stored.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import get_verified_user
from app.core.rate_limit import RateLimiter
from app.db.models import User
from app.services.md_cleaner import MAX_INPUT_BYTES, CleanError, clean_image, scan_bytes

router = APIRouter()
_limiter = RateLimiter()


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise HTTPException(status_code=413, detail="Pictures must be under 32 MB.")
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    return data


@router.post("/clean")
async def clean_picture(
    file: UploadFile = File(...),
    output_format: str = Form("auto"),
    user: User = Depends(get_verified_user),
):
    """Rebuild the picture from pixels only, rescan it, and return it with before/after reports."""
    _limiter.check(f"md_cleaner:clean:{user.id}", limit=300, window_seconds=600)
    data = await _read_upload(file)
    try:
        result = await run_in_threadpool(clean_image, data, file.filename or "", output_format)
    except CleanError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    return result.to_dict()


@router.post("/scan")
async def scan_picture(
    file: UploadFile = File(...),
    user: User = Depends(get_verified_user),
):
    """Report what Meta (and anyone else) can read from the picture, without changing it."""
    _limiter.check(f"md_cleaner:scan:{user.id}", limit=300, window_seconds=600)
    data = await _read_upload(file)
    report = await run_in_threadpool(scan_bytes, data, file.filename or "")
    return report.to_dict()
