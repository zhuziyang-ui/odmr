"""Portable entry: serve API + built SPA on http://127.0.0.1:8000 and open browser."""

from __future__ import annotations

import sys
import threading
import time
import webbrowser
from pathlib import Path

# Embeddable CPython ignores PYTHONPATH when a python*._pth is present.
# Always put this app directory on sys.path first.
_APP_DIR = Path(__file__).resolve().parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

import uvicorn

from backend.app.main import app


def _open_browser(url: str, delay_s: float = 1.2) -> None:
    def _worker() -> None:
        time.sleep(delay_s)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


if __name__ == "__main__":
    host = "127.0.0.1"
    port = 8000
    url = f"http://{host}:{port}/"
    print("=" * 56)
    print("  NV / ODMR Measurement Console (portable)")
    print(f"  UI:   {url}")
    print(f"  API:  http://{host}:{port}/docs")
    print("  Close this window to stop the server.")
    print("=" * 56)
    _open_browser(url)
    uvicorn.run(app, host=host, port=port, log_level="info")
