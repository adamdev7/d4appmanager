"""Only the read-only integration API (/api/v1/integration) for Central AI on this computer.

No schedulers, webhooks or user routes, so it can run next to (or instead of) the full app:

    uvicorn app.integration_app:app --host 127.0.0.1 --port 8001
"""

from fastapi import FastAPI

from app.config import settings
from app.routes import integration

app = FastAPI(title="App Manager integration API", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(integration.router, prefix=f"{settings.api_prefix}/integration")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "appmanager-integration", "enabled": bool(settings.integration_api_key)}
