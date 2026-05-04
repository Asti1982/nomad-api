"""Entry point for hosts that default to `python app.py` (e.g. Render).

The HTTP server implementation lives in `nomad_api.py`; this module delegates to it.
If a host starts without dependencies installed, bootstrap only missing modules
needed for import-time startup (instead of installing full requirements.txt).
"""

from __future__ import annotations

import os
import subprocess
import sys

MODULE_TO_PACKAGE = {
    "dotenv": "python-dotenv",
    "telegram": "python-telegram-bot",
    "solcx": "py-solc-x",
}


def _install_module_package(module_name: str) -> None:
    package_name = MODULE_TO_PACKAGE.get(module_name, module_name)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-cache-dir", package_name],
        check=True,
    )


def _import_nomad_api_with_bootstrap(max_attempts: int = 4):
    for _ in range(max_attempts):
        try:
            from nomad_api import serve as _serve

            return _serve
        except ModuleNotFoundError as exc:
            missing = (exc.name or "").strip()
            if not missing:
                raise
            _install_module_package(missing)
    from nomad_api import serve as _serve

    return _serve


if (os.getenv("RENDER") or "").strip().lower() == "true":
    serve = _import_nomad_api_with_bootstrap()
else:
    from nomad_api import serve

if __name__ == "__main__":
    serve()
