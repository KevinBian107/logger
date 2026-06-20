import os
import sys
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from logger.config import CORS_ORIGINS, IS_PACKAGED
from logger.database import init_db
from logger.routers import sessions, categories, import_csv, settings, timers, manual_entries, daily, groups, analytics, chat, projects, family_rules, breaks


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    yield


app = FastAPI(title="Logger", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/api")
app.include_router(categories.router, prefix="/api")
app.include_router(import_csv.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(timers.router, prefix="/api")
app.include_router(manual_entries.router, prefix="/api")
app.include_router(daily.router, prefix="/api")
app.include_router(groups.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(family_rules.router, prefix="/api")
app.include_router(breaks.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ── Static frontend (packaged Mac app only) ──────────────────────────────
#
# In the packaged build we mount the built SvelteKit SPA at /. The dev workflow
# (pnpm dev on :5173 + uvicorn on :8000) is unaffected: this whole block is a
# no-op unless LOGGER_APP_MODE=packaged AND the frontend has been built.

def _frontend_dist() -> Path | None:
    """Locate the SvelteKit build directory in either PyInstaller's _MEIPASS
    or the project tree, returning None if not built."""
    candidates = []
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "frontend" / "build")
    here = Path(__file__).resolve().parent
    candidates.append(here.parent.parent.parent / "frontend" / "build")
    override = os.environ.get("LOGGER_FRONTEND_DIST")
    if override:
        candidates.insert(0, Path(override).expanduser().resolve())
    for c in candidates:
        if c.is_dir() and (c / "index.html").exists():
            return c
    return None


if IS_PACKAGED:
    dist = _frontend_dist()
    if dist is None:
        raise RuntimeError(
            "Packaged mode requested but the SvelteKit build is missing. "
            "Run `pnpm --dir frontend build` before packaging."
        )

    # Serve hashed asset bundles directly
    app.mount("/_app", StaticFiles(directory=dist / "_app"), name="app_assets")

    # SPA fallback: any non-API path returns index.html so client-side routing works.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Serve favicon / static assets at the root if they exist as real files
        candidate = dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")
