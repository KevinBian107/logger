"""Runtime config: data paths, DB URL, CORS origins.

Three modes:
  - Dev (default):    DB lives next to the repo at ./logger.db, data/ is the repo's data dir.
                      Frontend on :5173 hits backend on :8000 over CORS.
  - Packaged Mac app: DB lives in ~/Library/Application Support/Logger/logger.db (the .app
                      bundle is read-only after install). Frontend is served same-origin from
                      the bundled SvelteKit static build, so no CORS is needed for the app.
  - Override:         LOGGER_DB_PATH and LOGGER_DATA_DIR env vars win over both above.

Mode detection: set LOGGER_APP_MODE=packaged (we do this in app_entry.py) to switch to the
macOS user-data path. Otherwise dev mode is used.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# Project root (works in dev and inside PyInstaller's _MEIPASS at build time)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_APP_MODE = os.environ.get("LOGGER_APP_MODE", "dev").lower()
IS_PACKAGED = _APP_MODE == "packaged"


def _user_data_dir() -> Path:
    """macOS user-writable data dir. Defers platformdirs import so dev mode
    doesn't require the dep until you actually package the app."""
    from platformdirs import user_data_dir
    return Path(user_data_dir("Logger", "kbian"))


def _resolve_db_path() -> Path:
    override = os.environ.get("LOGGER_DB_PATH")
    if override:
        return Path(override).expanduser().resolve()

    if IS_PACKAGED:
        d = _user_data_dir()
        d.mkdir(parents=True, exist_ok=True)
        db = d / "logger.db"

        # First-launch migration: if a dev-mode logger.db exists alongside the cwd and the
        # packaged DB doesn't, copy it over so the user keeps their data. Never delete the
        # source — the dev checkout's copy is left as a fallback.
        if not db.exists():
            legacy = Path.cwd() / "logger.db"
            if legacy.exists():
                shutil.copy2(legacy, db)
                print(f"[logger] migrated legacy DB {legacy} -> {db}", file=sys.stderr)
        return db

    # Dev mode — keep the repo-local DB so `uvicorn --reload` and SQL inspection still work
    return PROJECT_ROOT / "logger.db"


def _resolve_data_dir() -> Path:
    override = os.environ.get("LOGGER_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return PROJECT_ROOT / "data"


DB_PATH = _resolve_db_path()
DATA_DIR = _resolve_data_dir()
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# CORS only matters in dev (frontend on :5173 cross-origin). In the packaged app the
# frontend is served same-origin from the FastAPI StaticFiles mount.
CORS_ORIGINS = ["http://localhost:5173"]
