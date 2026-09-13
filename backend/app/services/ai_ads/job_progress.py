from __future__ import annotations

import json
from datetime import UTC, datetime

from app.db.models import CreativeGenerationJob

MAX_LOG = 40


def append_job_progress(
    job: CreativeGenerationJob,
    *,
    step: str,
    title: str,
    detail: str = "",
    pct: int | None = None,
) -> None:
    """Update the live studio fields so polling clients can show what the AI is doing."""
    job.progress_step = step
    job.progress_message = title
    if pct is not None:
        job.progress_pct = max(0, min(100, int(pct)))
    raw = getattr(job, "progress_log_json", None) or "[]"
    try:
        log = json.loads(raw)
        if not isinstance(log, list):
            log = []
    except json.JSONDecodeError:
        log = []
    log.append(
        {
            "at": datetime.now(UTC).isoformat(),
            "step": step,
            "title": title,
            "detail": (detail or "")[:400],
            "pct": getattr(job, "progress_pct", 0) or 0,
        }
    )
    job.progress_log_json = json.dumps(log[-MAX_LOG:])


def parse_job_log(job: CreativeGenerationJob) -> list[dict]:
    raw = getattr(job, "progress_log_json", None) or "[]"
    try:
        log = json.loads(raw)
        return log if isinstance(log, list) else []
    except json.JSONDecodeError:
        return []
