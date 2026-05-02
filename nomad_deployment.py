import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv


DEFAULT_GITHUB_DEPLOY_BRANCH = "syndiode"
DEFAULT_MODAL_APP_NAME = "nomad-agent"
DEFAULT_MODAL_API_LABEL = "nomad-agent-api"
DEFAULT_MODAL_SECRET_NAME = "nomad-env"
DEFAULT_MODAL_PYTHON_VERSION = "3.12"
DEFAULT_MODAL_PORT = 8787
DEFAULT_MODAL_MOUNT_PATH = "/root/nomad"
DEFAULT_RENDER_SERVICE_NAME = "nomad-api"
DEFAULT_RENDER_DOMAIN = "onrender.syndiode.com"

LOCAL_PUBLIC_URL_MARKERS = ("127.0.0.1", "localhost")
MODAL_ALLOWED_JSON_FILES = {
    "nomad_addressable_painpoints.json",
    "nomad_agent_seed_sources.json",
    "nomad_lead_sources.json",
    "nomad_market_patterns.json",
}
MODAL_EXCLUDED_DIRECTORIES = {
    ".devcontainer",
    ".git",
    ".pytest_cache",
    "__pycache__",
    "nomad_autonomous_artifacts",
    "nomad_mutual_aid_modules",
    "tools",
}
MODAL_EXCLUDED_FILENAMES = {
    ".env",
}
MODAL_EXCLUDED_SUFFIXES = {
    ".log",
    ".pyc",
    ".zip",
}


def _repo_root(repo_root: Path | str | None = None) -> Path:
    return Path(repo_root or Path(__file__).resolve().parent)


def _normalize_domain_or_url(value: str) -> str:
    normalized = str(value or "").strip().rstrip("/")
    if not normalized:
        return ""
    if normalized.startswith(("http://", "https://")):
        return normalized
    return f"https://{normalized}"


def derive_public_api_url(configured_public_url: str = "", render_domain: str = "") -> str:
    public_url = str(configured_public_url or "").strip().rstrip("/")
    if public_url and not any(marker in public_url for marker in LOCAL_PUBLIC_URL_MARKERS):
        return public_url
    return _normalize_domain_or_url(render_domain)


def github_repository() -> str:
    load_dotenv()
    return (
        os.getenv("NOMAD_GITHUB_REPOSITORY")
        or os.getenv("GITHUB_REPOSITORY")
        or ""
    ).strip()


def github_deploy_branch() -> str:
    load_dotenv()
    return (os.getenv("NOMAD_GITHUB_DEPLOY_BRANCH") or DEFAULT_GITHUB_DEPLOY_BRANCH).strip()


def render_service_name() -> str:
    load_dotenv()
    return (os.getenv("NOMAD_RENDER_SERVICE_NAME") or DEFAULT_RENDER_SERVICE_NAME).strip()


def render_domain() -> str:
    load_dotenv()
    return (os.getenv("NOMAD_RENDER_DOMAIN") or DEFAULT_RENDER_DOMAIN).strip()


def modal_app_name() -> str:
    load_dotenv()
    return (os.getenv("NOMAD_MODAL_APP_NAME") or DEFAULT_MODAL_APP_NAME).strip()


def modal_api_label() -> str:
    load_dotenv()
    return (os.getenv("NOMAD_MODAL_API_LABEL") or DEFAULT_MODAL_API_LABEL).strip()


def modal_secret_name() -> str:
    load_dotenv()
    raw = os.getenv("NOMAD_MODAL_SECRET_NAME")
    if raw is not None and raw.strip().lower() in {"none", "off", "false", "0"}:
        return ""
    return (raw or DEFAULT_MODAL_SECRET_NAME).strip()


def modal_python_version() -> str:
    load_dotenv()
    return (os.getenv("NOMAD_MODAL_PYTHON_VERSION") or DEFAULT_MODAL_PYTHON_VERSION).strip()


def modal_environment_name() -> str:
    load_dotenv()
    return (
        os.getenv("NOMAD_MODAL_ENVIRONMENT")
        or os.getenv("MODAL_ENVIRONMENT")
        or ""
    ).strip()


def modal_api_port() -> int:
    load_dotenv()
    raw = (
        os.getenv("NOMAD_MODAL_API_PORT")
        or os.getenv("NOMAD_API_PORT")
        or os.getenv("PORT")
        or str(DEFAULT_MODAL_PORT)
    ).strip()
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_MODAL_PORT


def modal_mount_path() -> str:
    load_dotenv()
    return (os.getenv("NOMAD_MODAL_MOUNT_PATH") or DEFAULT_MODAL_MOUNT_PATH).strip()


def modal_should_include(path: str | Path) -> bool:
    relative = Path(path).as_posix().strip("/")
    if not relative or relative == ".":
        return True
    parts = relative.split("/")
    if parts[0] in MODAL_EXCLUDED_DIRECTORIES:
        return False
    filename = parts[-1]
    if filename in MODAL_EXCLUDED_FILENAMES:
        return False
    suffix = Path(filename).suffix.lower()
    if suffix in MODAL_EXCLUDED_SUFFIXES:
        return False
    if suffix == ".json" and filename not in MODAL_ALLOWED_JSON_FILES:
        return False
    return True


def modal_deployment_snapshot(repo_root: Path | str | None = None) -> Dict[str, Any]:
    load_dotenv()
    root = _repo_root(repo_root)
    public_url = derive_public_api_url(
        configured_public_url=os.getenv("NOMAD_PUBLIC_API_URL", ""),
        render_domain=render_domain(),
    )
    app_path = root / "modal_nomad.py"
    secret_name = modal_secret_name()
    environment_name = modal_environment_name()
    deploy_command = f"modal deploy {app_path.name}"
    if environment_name:
        deploy_command += f" -e {environment_name}"
    return {
        "provider": "Modal",
        "role": "bursty_compute_and_optional_api_hosting",
        "app_name": modal_app_name(),
        "api_label": modal_api_label(),
        "secret_name": secret_name,
        "environment_name": environment_name,
        "python_version": modal_python_version(),
        "api_port": modal_api_port(),
        "mount_path": modal_mount_path(),
        "github_repository": github_repository(),
        "github_branch": github_deploy_branch(),
        "render_service_name": render_service_name(),
        "render_domain": render_domain(),
        "public_api_url": public_url,
        "app_path": str(app_path),
        "requirements_path": str(root / "requirements.txt"),
        "deploy_commands": [
            f"modal secret create {secret_name} --from-dotenv .env --force",
            deploy_command,
        ],
        "notes": [
            "Use Modal for burst compute or a preview web endpoint.",
            "Keep Render as the canonical public API URL when NOMAD_PUBLIC_API_URL points at syndiode/onrender.",
            "Set NOMAD_GITHUB_DEPLOY_BRANCH before linking GitHub-based deploy workflows if syndiode is not the desired branch.",
        ],
    }
