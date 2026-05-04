"""Entry point for hosts that default to `python app.py` (e.g. some Render setups).

The canonical Nomad HTTP server lives in `nomad_api.py`; this module only delegates.

Prefer configuring Render Build Command to: pip install -r requirements.txt
If the service still runs with a no-op build (e.g. only ``python --version``), a one-time
``pip install`` runs at cold start when RENDER=true and python-dotenv is missing.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_REQUIREMENTS = _ROOT / "requirements.txt"


def _maybe_install_requirements_on_render() -> None:
    if (os.environ.get("RENDER") or "").strip().lower() != "true":
        return
    if not _REQUIREMENTS.is_file():
        return
    try:
        import dotenv  # noqa: F401
    except ModuleNotFoundError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", str(_REQUIREMENTS)],
            cwd=str(_ROOT),
            check=True,
        )


_maybe_install_requirements_on_render()

from nomad_api import serve

if __name__ == "__main__":
    serve()
