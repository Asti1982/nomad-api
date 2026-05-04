"""Entry point for hosts that default to `python app.py` (e.g. Render).

The HTTP server implementation lives in `nomad_api.py`; this module delegates to it.
If a host starts the app without installing requirements first, this entrypoint
bootstraps `pip install -r requirements.txt` once when `dotenv` is missing.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "requirements.txt"


def _ensure_requirements_installed() -> None:
    if not REQUIREMENTS.exists():
        return
    try:
        import dotenv  # noqa: F401
    except ModuleNotFoundError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", str(REQUIREMENTS)],
            cwd=str(ROOT),
            check=True,
        )


if (os.getenv("RENDER") or "").strip().lower() == "true":
    _ensure_requirements_installed()

from nomad_api import serve

if __name__ == "__main__":
    serve()
