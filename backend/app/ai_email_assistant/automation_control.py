"""Pause autopilot and persist a user-visible error message."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import AIEmailAssistantSettings


def stop_autopilot(
    db: Session,
    settings_row: AIEmailAssistantSettings,
    message: str,
    *,
    disable: bool = True,
) -> None:
    prefix = "Autopilot stopped: "
    full = message if message.startswith(prefix) else f"{prefix}{message}"
    settings_row.automation_last_error = full[:500]
    if disable:
        settings_row.automation_enabled = False
    settings_row.automation_last_run_at = datetime.now(UTC)
    db.commit()
