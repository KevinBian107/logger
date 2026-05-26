"""Build script for the packaged Mac .app.

What this does:

  1. Confirms the SvelteKit static build exists at frontend/build/ (if not, prints
     the command to produce it and exits).
  2. Invokes PyInstaller from inside backend/ in --windowed --onedir mode against
     `logger/app_entry.py`. The frontend/build dir is bundled with --add-data so
     FastAPI's StaticFiles mount can resolve it via sys._MEIPASS at runtime.
  3. Adds the hidden imports that uvicorn/anthropic/sqlalchemy need on cold start
     (PyInstaller's static analysis misses some dynamic imports inside uvicorn's
     loop/protocol auto-detection).
  4. Produces dist/Logger.app. You can copy it to /Applications, double-click it,
     or `open dist/Logger.app`.

Usage:
    uv sync --extra macapp
    pnpm --dir frontend install
    pnpm --dir frontend build
    uv run python scripts/build_macapp.py

The build does NOT code-sign or notarize. On first launch you'll need to
right-click → Open to get past Gatekeeper, or run:
    xattr -dr com.apple.quarantine dist/Logger.app
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_BUILD = REPO_ROOT / "frontend" / "build"
DIST_DIR = REPO_ROOT / "dist"
BUILD_WORKDIR = REPO_ROOT / "build"
ICNS_PATH = BUILD_WORKDIR / "Logger.icns"
ICON_BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_app_icon.sh"

APP_NAME = "Logger"
ENTRY = "logger/app_entry.py"

# uvicorn discovers protocol/loop implementations at runtime via importlib;
# PyInstaller's static analyzer misses these. Anthropic and httpx have similar
# dynamic-import patterns. Add new ones here if a packaged-app crash names a
# missing module.
HIDDEN_IMPORTS = [
    "uvicorn.loops.auto",
    "uvicorn.loops.uvloop",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "aiosqlite",
    "anthropic",
    "anthropic._types",
    "platformdirs",
    "platformdirs.macos",
]


def _die(msg: str, code: int = 1) -> None:
    sys.stderr.write(f"[build_macapp] {msg}\n")
    sys.exit(code)


def _check_prerequisites() -> None:
    if not FRONTEND_BUILD.is_dir() or not (FRONTEND_BUILD / "index.html").exists():
        _die(
            "Missing frontend/build/. Run:\n"
            "    pnpm --dir frontend install\n"
            "    pnpm --dir frontend build"
        )

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        _die(
            "PyInstaller not installed. Run:\n"
            "    uv sync --extra macapp"
        )
    try:
        import webview  # noqa: F401
    except ImportError:
        _die(
            "pywebview not installed. Run:\n"
            "    uv sync --extra macapp"
        )


def _clean_previous() -> None:
    """Remove previous build artifacts so PyInstaller starts fresh.

    We intentionally only delete dist/Logger.app and build/Logger; we leave the
    parent dirs intact in case the user has other artifacts in them.
    """
    for path in (DIST_DIR / f"{APP_NAME}.app", DIST_DIR / APP_NAME, BUILD_WORKDIR / APP_NAME):
        if path.is_dir():
            shutil.rmtree(path)


def _build_icon() -> None:
    """Build Logger.icns from frontend/static/logo.svg using sips + iconutil."""
    if not ICON_BUILD_SCRIPT.exists():
        _die(f"Missing icon build script: {ICON_BUILD_SCRIPT}")
    print("[build_macapp] building app icon...")
    result = subprocess.run(["bash", str(ICON_BUILD_SCRIPT)])
    if result.returncode != 0 or not ICNS_PATH.exists():
        _die("Icon build failed", result.returncode or 1)


def _run_pyinstaller() -> None:
    add_data = f"{FRONTEND_BUILD}:frontend/build"  # src:dest, : is macOS/Linux separator

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name", APP_NAME,
        "--icon", str(ICNS_PATH),
        f"--distpath={DIST_DIR}",
        f"--workpath={BUILD_WORKDIR}",
        f"--specpath={BUILD_WORKDIR}",
        "--add-data", add_data,
        "--collect-submodules", "uvicorn",
        "--collect-submodules", "anthropic",
        "--collect-submodules", "logger",
    ]
    for mod in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", mod])
    cmd.append(ENTRY)

    print("[build_macapp] running PyInstaller...")
    print("  " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=BACKEND_DIR)
    if result.returncode != 0:
        _die("PyInstaller failed", result.returncode)


def main() -> None:
    _check_prerequisites()
    _clean_previous()
    _build_icon()
    _run_pyinstaller()

    app_path = DIST_DIR / f"{APP_NAME}.app"
    if not app_path.exists():
        _die(f"Expected {app_path} to exist but it doesn't.")

    size_mb = sum(p.stat().st_size for p in app_path.rglob("*") if p.is_file()) / 1024 / 1024
    print(f"\n[build_macapp] built {app_path} ({size_mb:.1f} MB)")
    print("[build_macapp] launch with:  open dist/Logger.app")
    print("[build_macapp] first-launch tip:  xattr -dr com.apple.quarantine dist/Logger.app")


if __name__ == "__main__":
    main()
