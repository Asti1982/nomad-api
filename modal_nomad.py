import os
import subprocess
import sys
from pathlib import Path

import modal

from nomad_deployment import (
    modal_api_label,
    modal_api_port,
    modal_app_name,
    modal_environment_name,
    modal_mount_path,
    modal_python_version,
    modal_secret_name,
    modal_should_include,
)


ROOT = Path(__file__).resolve().parent
REMOTE_ROOT = modal_mount_path()
SECRET_NAME = modal_secret_name()
API_PORT = modal_api_port()
API_LABEL = modal_api_label()
PYTHON_VERSION = modal_python_version()
MODAL_ENVIRONMENT = modal_environment_name()


def _ignore_modal_copy(path: Path) -> bool:
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        relative = path
    return not modal_should_include(relative)


image = (
    modal.Image.debian_slim(python_version=PYTHON_VERSION)
    .pip_install_from_requirements(str(ROOT / "requirements.txt"))
    .add_local_dir(
        ROOT,
        remote_path=REMOTE_ROOT,
        ignore=_ignore_modal_copy,
    )
)

app = modal.App(
    modal_app_name(),
    image=image,
    secrets=[modal.Secret.from_name(SECRET_NAME)] if SECRET_NAME else [],
    include_source=False,
)


def _prepare_runtime() -> None:
    os.chdir(REMOTE_ROOT)
    if REMOTE_ROOT not in sys.path:
        sys.path.insert(0, REMOTE_ROOT)
    os.environ.setdefault("NOMAD_API_HOST", "0.0.0.0")
    os.environ.setdefault("NOMAD_API_PORT", str(API_PORT))
    if MODAL_ENVIRONMENT:
        os.environ.setdefault("MODAL_ENVIRONMENT", MODAL_ENVIRONMENT)


@app.function(cpu=1.0, memory=1024, timeout=900, scaledown_window=120)
def run_nomad_query(query: str, profile_id: str = "ai_first") -> dict:
    _prepare_runtime()
    from workflow import NomadAgent

    normalized = str(query or "").strip()
    if normalized and not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if not normalized:
        normalized = f"/self for {profile_id}".strip()
    return NomadAgent().run(normalized)


@app.function(cpu=1.0, memory=1024, timeout=600, scaledown_window=120)
def agent_attractor_manifest(service_type: str = "", role_hint: str = "", limit: int = 5) -> dict:
    _prepare_runtime()
    from workflow import NomadAgent

    return NomadAgent().agent_attractor.manifest(
        service_type=service_type,
        role_hint=role_hint,
        limit=limit,
    )


@app.function(cpu=0.25, memory=512, timeout=120, scaledown_window=120)
def cryptogrift_guard_agent(signal: str = "", connect: bool = False, base_url: str = "") -> dict:
    _prepare_runtime()
    from cryptogrift_guard_agent import CryptoGriftGuardAgent

    return CryptoGriftGuardAgent(timeout=30.0).connect_to_nomad(
        base_url=base_url,
        signal=signal,
        dry_run=not connect,
    )


@app.function(cpu=0.5, memory=512, timeout=180, scaledown_window=120)
def cryptogrift_guard_engage(signal: str = "", connect: bool = False, base_url: str = "", join_first: bool = True) -> dict:
    _prepare_runtime()
    from cryptogrift_guard_agent import CryptoGriftGuardAgent

    return CryptoGriftGuardAgent(timeout=30.0).engage_nomad(
        base_url=base_url,
        signal=signal,
        join_first=join_first,
        dry_run=not connect,
    )


@app.function(cpu=0.5, memory=512, timeout=180, scaledown_window=120)
def cryptogrift_guard_brain_engage(signal: str = "", base_url: str = "") -> dict:
    _prepare_runtime()
    from cryptogrift_guard_agent import CryptoGriftGuardAgent

    return CryptoGriftGuardAgent(timeout=30.0).engage_nomad_brain(
        base_url=base_url,
        signal=signal,
    )


@app.function(cpu=1.0, memory=1024, timeout=1800, scaledown_window=300)
@modal.web_server(API_PORT, startup_timeout=30.0, label=API_LABEL)
def serve_nomad_api() -> None:
    _prepare_runtime()
    env = os.environ.copy()
    env["NOMAD_API_HOST"] = "0.0.0.0"
    env["NOMAD_API_PORT"] = str(API_PORT)
    process = subprocess.Popen(
        [sys.executable, "nomad_api.py"],
        cwd=REMOTE_ROOT,
        env=env,
    )
    process.wait()
