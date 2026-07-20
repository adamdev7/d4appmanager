from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.ai_email_assistant.automation_worker import start_automation_worker, stop_automation_worker
from app.config import settings
from app.db.session import init_db
from app.routes import api_router
from app.routes import track_order as track_order_routes

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _BACKEND_ROOT.parent
_FRONTEND_DIST = _PROJECT_ROOT / "frontend" / "dist"
_UPLOADS_DIR = _BACKEND_ROOT / "data" / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_automation_worker()
    yield
    await stop_automation_worker()


app = FastAPI(
    title=settings.app_name,
    description="Automation platform for Shopify stores",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Shopify storefronts (myshopify.com + custom domains) call GET /api/track-order from the browser.
    allow_origin_regex=r"https://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)
# Public storefront alias: GET /api/track-order (same handler as /api/v1/track-order)
app.include_router(track_order_routes.router, prefix="/api")

# Uploaded assets (email logos, etc.) — public so email clients can load images
app.mount("/uploads", StaticFiles(directory=_UPLOADS_DIR), name="uploads")


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}


def _ui_help_page() -> HTMLResponse:
    return HTMLResponse(
        """<!DOCTYPE html><html><body style="font-family:system-ui;max-width:520px;margin:4rem auto">
        <h1>Backend running</h1>
        <p>Open the UI at <a href="http://localhost:5173">http://localhost:5173</a></p>
        <p><a href="/docs">API docs</a></p></body></html>"""
    )


@app.get("/")
async def root():
    index = _FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return _ui_help_page()


if _FRONTEND_DIST.is_dir():
    assets_dir = _FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        if path.startswith("api") or path.startswith("uploads") or path in ("docs", "openapi.json", "redoc", "health"):
            raise HTTPException(status_code=404, detail="Not found")
        file_path = _FRONTEND_DIST / path
        if file_path.is_file():
            return FileResponse(file_path)
        index = _FRONTEND_DIST / "index.html"
        if index.is_file():
            return FileResponse(index)
        return _ui_help_page()
