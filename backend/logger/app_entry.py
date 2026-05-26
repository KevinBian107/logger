"""Entry point for the packaged Mac .app.

This is what PyInstaller wraps and what the .app bundle launches. It:

  1. Sets LOGGER_APP_MODE=packaged so config.py routes the DB to
     ~/Library/Application Support/Logger/logger.db (and migrates the
     legacy in-repo logger.db on first launch if present).
  2. Picks a free localhost port (avoids colliding with a dev uvicorn on 8000).
  3. Spawns uvicorn in a separate process — pywebview wants the main thread
     for its native UI runloop, so the API server cannot live on the main
     thread or be embedded in pywebview's event loop. The canonical pattern
     is two processes, joined on window close.
  4. Opens a pywebview window pointed at http://127.0.0.1:<port>.
  5. Terminates the API server when the user closes the window.

This module is NOT used in the dev workflow. `pnpm dev` + `uvicorn --reload`
still works exactly as before.
"""

from __future__ import annotations

import multiprocessing
import os
import socket
import sys
import time
from contextlib import closing
from typing import NoReturn


WINDOW_TITLE = "log(ger)"
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900
HEALTH_PATH = "/api/health"
HEALTH_TIMEOUT_S = 15


def _find_free_port() -> int:
    """Bind to :0 and ask the OS for an ephemeral port, then immediately close.
    Brief race with another process is acceptable for a single-user local app."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run_uvicorn(port: int) -> NoReturn:
    """Child process: run uvicorn against logger.main:app."""
    # Re-assert packaged mode in the subprocess (spawn doesn't inherit env on macOS
    # when frozen) so the DB and static-mount logic both fire.
    os.environ["LOGGER_APP_MODE"] = "packaged"
    import uvicorn
    uvicorn.run(
        "logger.main:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    sys.exit(0)


def _wait_for_health(port: int) -> bool:
    """Poll the health endpoint until it answers or we time out."""
    import urllib.error
    import urllib.request
    deadline = time.time() + HEALTH_TIMEOUT_S
    url = f"http://127.0.0.1:{port}{HEALTH_PATH}"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.2)
    return False


def main() -> None:
    os.environ["LOGGER_APP_MODE"] = "packaged"

    port = _find_free_port()
    api_proc = multiprocessing.Process(target=_run_uvicorn, args=(port,), daemon=True)
    api_proc.start()

    if not _wait_for_health(port):
        api_proc.terminate()
        sys.stderr.write(f"[logger] API never became healthy on :{port}; aborting.\n")
        sys.exit(1)

    # Open the native window only after the API is reachable so the SPA's first
    # data fetches don't race the server boot.
    import webview
    webview.create_window(
        WINDOW_TITLE,
        f"http://127.0.0.1:{port}/",
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=(900, 600),
    )
    try:
        webview.start()
    finally:
        if api_proc.is_alive():
            api_proc.terminate()
            api_proc.join(timeout=3)


if __name__ == "__main__":
    # multiprocessing on macOS uses 'spawn' by default with frozen executables;
    # this guard is required so the child doesn't re-enter main().
    multiprocessing.freeze_support()
    main()
