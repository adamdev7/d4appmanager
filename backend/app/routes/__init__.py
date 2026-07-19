from fastapi import APIRouter

from app.routes import (
    ai_email_assistant,
    auth,
    dashboard,
    email_automation,
    gmail,
    modules,
    stores,
    track_order,
    tracking,
    webhooks,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(stores.router, prefix="/stores", tags=["stores"])
api_router.include_router(gmail.router, prefix="/gmail", tags=["gmail"])
api_router.include_router(
    email_automation.router, prefix="/email-automation", tags=["email-automation"]
)
api_router.include_router(
    ai_email_assistant.router, prefix="/ai-email-assistant", tags=["ai-email-assistant"]
)
api_router.include_router(modules.router, prefix="/modules", tags=["modules"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(track_order.router, tags=["track-order"])
api_router.include_router(tracking.router, prefix="/tracking", tags=["tracking"])
