import importlib.util
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv
try:
    import tomllib
except ImportError:  # pragma: no cover - Python <3.11 fallback
    import toml as tomllib

from nomad_codebuddy import CodeBuddyProbe
from nomad_health import LaneCooldownManager


load_dotenv()
ROOT = Path(__file__).resolve().parent
DEFAULT_GITHUB_MODEL = "openai/gpt-4.1-mini"
DEFAULT_GITHUB_MODEL_CANDIDATES = (
    "openai/gpt-4.1-mini",
    "openai/gpt-4.1-nano",
    "openai/gpt-4o-mini",
    "openai/gpt-4.1",
    "openai/gpt-4o",
)
DEFAULT_GITHUB_MODELS_API_VERSION = "2026-03-10"
DEFAULT_GITHUB_MODELS_BASE_URL = "https://models.github.ai/inference"
DEFAULT_GITHUB_MODELS_CATALOG_URL = "https://models.github.ai/catalog/models"
GITHUB_MODELS_TOKEN_ENV_VARS = ("GITHUB_PERSONAL_ACCESS_TOKEN", "GITHUB_TOKEN")
GITHUB_MODELS_REQUIRED_PERMISSION = "models: read"
DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"
DEFAULT_XAI_MODEL = "grok-4.20-reasoning"
DEFAULT_XAI_MODEL_CANDIDATES = (
    "grok-4.20-reasoning",
    "grok-4.20",
    "grok-4-1-fast",
)
XAI_TOKEN_ENV_VAR = "XAI_API_KEY"


def _modal_config_path() -> Path:
    configured = (os.getenv("MODAL_CONFIG_PATH") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".modal.toml"


def _modal_credentials_from_config() -> Dict[str, str]:
    path = _modal_config_path()
    if not path.exists():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    requested_profile = (os.getenv("MODAL_PROFILE") or "").strip()
    candidates: List[tuple[str, Dict[str, Any]]] = []
    for profile, payload in data.items():
        if isinstance(payload, dict):
            candidates.append((str(profile), payload))
    if requested_profile:
        candidates.sort(key=lambda item: item[0] != requested_profile)
    else:
        candidates.sort(key=lambda item: not bool(item[1].get("active")))
    for profile, payload in candidates:
        token_id = str(payload.get("token_id") or "").strip()
        token_secret = str(payload.get("token_secret") or "").strip()
        if token_id and token_secret:
            return {
                "profile": profile,
                "token_id": token_id,
                "token_secret": token_secret,
                "source": str(path),
            }
    return {}


def github_models_base_url() -> str:
    return (os.getenv("NOMAD_GITHUB_MODELS_BASE_URL") or DEFAULT_GITHUB_MODELS_BASE_URL).rstrip("/")


def github_models_catalog_url() -> str:
    return (os.getenv("NOMAD_GITHUB_MODELS_CATALOG_URL") or DEFAULT_GITHUB_MODELS_CATALOG_URL).strip()


def github_models_chat_completions_url(base_url: str = "") -> str:
    return f"{(base_url or github_models_base_url()).rstrip('/')}/chat/completions"


def github_model_candidates(
    configured_model: str = "",
    catalog_model_ids: List[str] | None = None,
) -> List[str]:
    env_candidates = [
        item.strip()
        for item in (os.getenv("NOMAD_GITHUB_MODEL_CANDIDATES") or "").replace(";", ",").split(",")
        if item.strip()
    ]
    candidates = [
        configured_model,
        *env_candidates,
        *DEFAULT_GITHUB_MODEL_CANDIDATES,
        *((catalog_model_ids or [])[:5]),
    ]
    unique: List[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def xai_base_url() -> str:
    return (os.getenv("NOMAD_XAI_BASE_URL") or DEFAULT_XAI_BASE_URL).rstrip("/")


def xai_chat_completions_url(base_url: str = "") -> str:
    return f"{(base_url or xai_base_url()).rstrip('/')}/chat/completions"


def xai_model_candidates(configured_model: str = "") -> List[str]:
    env_candidates = [
        item.strip()
        for item in (os.getenv("NOMAD_XAI_MODEL_CANDIDATES") or "").replace(";", ",").split(",")
        if item.strip()
    ]
    candidates = [
        configured_model,
        *env_candidates,
        *DEFAULT_XAI_MODEL_CANDIDATES,
    ]
    unique: List[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def github_models_headers(token: str, api_version: str, *, json_request: bool = False) -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": api_version or DEFAULT_GITHUB_MODELS_API_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if json_request:
        headers["Content-Type"] = "application/json"
    return headers


def xai_status_help(
    status_code: int | None,
    *,
    model: str = "",
    body: str = "",
    base_url: str = "",
) -> Dict[str, Any]:
    base = (base_url or xai_base_url()).rstrip("/")
    help_payload: Dict[str, Any] = {
        "status_code": status_code,
        "token_env_var": XAI_TOKEN_ENV_VAR,
        "base_url": base,
        "chat_completions_url": xai_chat_completions_url(base),
        "openai_compatible_config": {
            "provider": "openai",
            "apiBase": base,
            "apiKey": "${XAI_API_KEY}",
            "models": list(DEFAULT_XAI_MODEL_CANDIDATES),
        },
        "curl_hint": (
            "curl -L -X POST -H \"Authorization: Bearer $XAI_API_KEY\" "
            "-H \"Content-Type: application/json\" "
            f"{xai_chat_completions_url(base)} "
            "-d '{\"model\":\"grok-4.20-reasoning\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply OK\"}],\"max_tokens\":8}'"
        ),
    }
    if body:
        help_payload["response_excerpt"] = _safe_xai_response_excerpt(body)

    if status_code is None:
        help_payload.update(
            {
                "issue": "xai_grok_missing_token",
                "message": "No xAI/Grok API key is configured.",
                "next_action": "Set XAI_API_KEY or send /token grok <token>, then rerun /compute.",
                "remediation": [
                    "Create or copy an xAI API key.",
                    "Set XAI_API_KEY locally or send it through Telegram as /token grok <token>.",
                    "Keep NOMAD_XAI_BASE_URL=https://api.x.ai/v1 unless xAI documents a different base URL.",
                ],
            }
        )
    elif status_code == 403 and any(
        marker in str(body or "").lower()
        for marker in ("credits", "license", "licence", "billing")
    ):
        help_payload.update(
            {
                "issue": "xai_grok_missing_credits_or_license",
                "message": "xAI/Grok accepted the API path but the team has no usable credits or license.",
                "next_action": "Add xAI API credits/license for this team, or let Nomad use another hosted/free lane.",
                "remediation": [
                    "Open the xAI console and add API credits or an API-capable license to the team.",
                    "Do not rotate the key unless it was exposed; this is an account/credits gate.",
                    "Use Ollama, GitHub Models, Hugging Face, or Cloudflare as fallback until xAI has credits.",
                ],
            }
        )
    elif status_code in {401, 403}:
        help_payload.update(
            {
                "issue": "xai_grok_auth_or_permission",
                "message": f"xAI/Grok rejected the API key with HTTP {status_code}.",
                "next_action": "Verify or rotate the xAI API key, then restart Nomad or rerun /compute.",
                "remediation": [
                    "Check that XAI_API_KEY is active in the xAI console.",
                    "Confirm the account has API access for the selected Grok model.",
                    "Rotate the key if it was ever stored in plaintext or shared.",
                ],
            }
        )
    elif status_code in {400, 404, 422}:
        help_payload.update(
            {
                "issue": "xai_grok_endpoint_or_model",
                "message": f"xAI/Grok returned HTTP {status_code} for model {model or '<unset>'}.",
                "next_action": "Try another Grok model candidate or verify NOMAD_XAI_BASE_URL.",
                "remediation": [
                    "Set NOMAD_XAI_BASE_URL=https://api.x.ai/v1.",
                    "Try NOMAD_XAI_MODEL=grok-4.20-reasoning or another model listed by xAI.",
                    "Run /compute again so Nomad can test model candidates.",
                ],
            }
        )
    elif status_code == 429:
        help_payload.update(
            {
                "issue": "xai_grok_rate_limited",
                "message": "xAI/Grok is reachable but rate limited this request.",
                "next_action": "Retry later or let Nomad fall back to Ollama, GitHub Models, Hugging Face, or Cloudflare.",
                "remediation": [
                    "Do not rotate a working key just for HTTP 429.",
                    "Reduce hosted self-improvement frequency or max tokens.",
                    "Keep another compute lane active as fallback.",
                ],
            }
        )
    else:
        help_payload.update(
            {
                "issue": "xai_grok_unknown_failure",
                "message": f"xAI/Grok failed with HTTP {status_code}.",
                "next_action": "Inspect response_excerpt and verify token, endpoint, and model ID.",
                "remediation": [
                    "Verify XAI_API_KEY is valid.",
                    "Verify NOMAD_XAI_BASE_URL and NOMAD_XAI_MODEL.",
                    "Retry with the curl_hint shown by the probe.",
                ],
            }
        )
    return help_payload


def _safe_response_excerpt(text: str) -> str:
    return " ".join(str(text or "").split())[:500]


def _safe_xai_response_excerpt(text: str) -> str:
    cleaned = re.sub(r"team/[0-9a-fA-F-]{20,}", "team/<redacted>", str(text or ""))
    cleaned = re.sub(r"xai-[A-Za-z0-9_\-.]+", "xai-<redacted>", cleaned)
    return _safe_response_excerpt(cleaned)


def github_models_status_help(
    status_code: int | None,
    *,
    model: str = "",
    body: str = "",
    base_url: str = "",
    api_version: str = "",
) -> Dict[str, Any]:
    base = (base_url or github_models_base_url()).rstrip("/")
    api_version_value = api_version or DEFAULT_GITHUB_MODELS_API_VERSION
    help_payload: Dict[str, Any] = {
        "status_code": status_code,
        "required_permission": GITHUB_MODELS_REQUIRED_PERMISSION,
        "token_env_vars": list(GITHUB_MODELS_TOKEN_ENV_VARS),
        "base_url": base,
        "catalog_url": github_models_catalog_url(),
        "chat_completions_url": github_models_chat_completions_url(base),
        "docs_api_version": DEFAULT_GITHUB_MODELS_API_VERSION,
        "api_version": api_version_value,
        "openai_compatible_config": {
            "provider": "openai",
            "apiBase": base,
            "apiKey": "${GITHUB_PERSONAL_ACCESS_TOKEN}",
            "models": list(DEFAULT_GITHUB_MODEL_CANDIDATES),
        },
        "curl_hint": (
            "curl -L -X POST -H \"Accept: application/vnd.github+json\" "
            "-H \"Authorization: Bearer <PAT>\" -H \"X-GitHub-Api-Version: 2026-03-10\" "
            "-H \"Content-Type: application/json\" "
            f"{github_models_chat_completions_url(base)} "
            "-d '{\"model\":\"openai/gpt-4.1-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply OK\"}]}'"
        ),
    }
    if api_version_value != DEFAULT_GITHUB_MODELS_API_VERSION:
        help_payload["api_version_warning"] = (
            f"GitHub Models docs use {DEFAULT_GITHUB_MODELS_API_VERSION}; "
            f"current NOMAD_GITHUB_MODELS_API_VERSION is {api_version_value}."
        )
    if body:
        help_payload["response_excerpt"] = _safe_response_excerpt(body)

    if status_code is None:
        help_payload.update(
            {
                "issue": "github_models_missing_token",
                "message": "No GitHub Models token is configured.",
                "next_action": (
                    "Create a fine-grained PAT with Models: Read and set "
                    "GITHUB_PERSONAL_ACCESS_TOKEN, or set GITHUB_TOKEN in GitHub Actions."
                ),
                "remediation": [
                    "Create a fine-grained GitHub PAT with Models: Read.",
                    "Set GITHUB_PERSONAL_ACCESS_TOKEN locally, or GITHUB_TOKEN in Actions.",
                    "Keep NOMAD_GITHUB_MODELS_BASE_URL=https://models.github.ai/inference.",
                    "Use NOMAD_GITHUB_MODELS_API_VERSION=2026-03-10.",
                ],
            }
        )
    elif status_code in {401, 403}:
        help_payload.update(
            {
                "issue": "github_models_auth_or_permission",
                "message": f"GitHub Models rejected the token with HTTP {status_code}.",
                "next_action": (
                    "Regenerate the PAT with Models: Read, then restart Nomad so the new "
                    "environment variable is loaded."
                ),
                "remediation": [
                    "Use a fine-grained PAT that has Models: Read.",
                    "Prefer GITHUB_PERSONAL_ACCESS_TOKEN over an older generic GITHUB_TOKEN.",
                    "If this is an organization repository, confirm GitHub Models is enabled for the org/repo.",
                    "Restart the agent process after changing the token.",
                ],
            }
        )
    elif status_code in {400, 404, 422}:
        help_payload.update(
            {
                "issue": "github_models_endpoint_or_model",
                "message": (
                    f"GitHub Models returned HTTP {status_code} for model "
                    f"{model or '<unset>'}."
                ),
                "next_action": (
                    "Use the official base URL, API version 2026-03-10, and a model ID from "
                    "the GitHub Models catalog."
                ),
                "remediation": [
                    "Set NOMAD_GITHUB_MODELS_BASE_URL=https://models.github.ai/inference.",
                    "Set NOMAD_GITHUB_MODELS_API_VERSION=2026-03-10.",
                    "Try NOMAD_GITHUB_MODEL=openai/gpt-4.1-mini, openai/gpt-4.1-nano, or openai/gpt-4o-mini.",
                    "Run python main.py --cli compute --json to see which model candidate works.",
                ],
            }
        )
    elif status_code == 429:
        help_payload.update(
            {
                "issue": "github_models_rate_limited",
                "message": "GitHub Models is reachable but rate limited this request.",
                "next_action": "Retry later or let Nomad use Ollama/Hugging Face as a fallback lane.",
                "remediation": [
                    "Wait for the GitHub Models quota window to reset.",
                    "Keep Ollama or Hugging Face enabled as a fallback brain.",
                    "Reduce self-improvement cycle frequency or max tokens.",
                ],
            }
        )
    elif status_code >= 500:
        help_payload.update(
            {
                "issue": "github_models_service_unavailable",
                "message": f"GitHub Models returned HTTP {status_code}.",
                "next_action": "Treat GitHub Models as temporarily unavailable and fall back to local compute.",
                "remediation": [
                    "Retry later.",
                    "Use Ollama/Hugging Face/Cloudflare as a temporary self-improvement lane.",
                ],
            }
        )
    else:
        help_payload.update(
            {
                "issue": "github_models_unknown_failure",
                "message": f"GitHub Models failed with HTTP {status_code}.",
                "next_action": "Inspect response_excerpt and verify token, endpoint, API version, and model ID.",
                "remediation": [
                    "Verify the token has Models: Read.",
                    "Verify the base URL and model ID.",
                    "Retry with the curl_hint shown by the probe.",
                ],
            }
        )
    return help_payload


class LocalComputeProbe:
    def __init__(self, health: Optional[LaneCooldownManager] = None) -> None:
        load_dotenv()
        self.health = health or LaneCooldownManager()
        self.ollama_base = (os.getenv("OLLAMA_API_BASE") or "http://127.0.0.1:11434").rstrip("/")
        self.github_token = (
            os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
            or os.getenv("GITHUB_TOKEN")
            or ""
        ).strip()
        self.github_model = (os.getenv("NOMAD_GITHUB_MODEL") or DEFAULT_GITHUB_MODEL).strip()
        self.github_model_candidates = github_model_candidates(self.github_model)
        self.github_base_url = github_models_base_url()
        self.github_catalog_url = github_models_catalog_url()
        self.github_chat_url = github_models_chat_completions_url(self.github_base_url)
        self.github_api_version = (
            os.getenv("NOMAD_GITHUB_MODELS_API_VERSION") or DEFAULT_GITHUB_MODELS_API_VERSION
        ).strip()
        self.hf_token = (
            os.getenv("HF_TOKEN")
            or os.getenv("HUGGINGFACEHUB_API_TOKEN")
            or os.getenv("HUGGING_FACE_HUB_TOKEN")
            or ""
        ).strip()
        modal_config = _modal_credentials_from_config()
        self.modal_token_id = (os.getenv("MODAL_TOKEN_ID") or modal_config.get("token_id") or "").strip()
        self.modal_token_secret = (os.getenv("MODAL_TOKEN_SECRET") or modal_config.get("token_secret") or "").strip()
        self.modal_profile = (os.getenv("MODAL_PROFILE") or modal_config.get("profile") or "").strip()
        self.modal_credential_source = (
            "env"
            if os.getenv("MODAL_TOKEN_ID") and os.getenv("MODAL_TOKEN_SECRET")
            else "modal_config"
            if modal_config.get("token_id") and modal_config.get("token_secret")
            else ""
        )
        self.cloudflare_account_id = (os.getenv("CLOUDFLARE_ACCOUNT_ID") or "").strip()
        self.cloudflare_api_token = (os.getenv("CLOUDFLARE_API_TOKEN") or "").strip()
        self.cloudflare_model = (
            os.getenv("NOMAD_CLOUDFLARE_MODEL") or "@cf/meta/llama-3.2-1b-instruct"
        ).strip()
        self.xai_token = (os.getenv("XAI_API_KEY") or "").strip()
        self.xai_base_url = xai_base_url()
        self.xai_chat_url = xai_chat_completions_url(self.xai_base_url)
        self.xai_model = (os.getenv("NOMAD_XAI_MODEL") or DEFAULT_XAI_MODEL).strip()
        self.xai_model_candidates = xai_model_candidates(self.xai_model)
        self.lambda_labs_token = (os.getenv("LAMBDA_LABS_API_TOKEN") or "").strip()
        self.runpod_api_key = (os.getenv("RUNPOD_API_KEY") or "").strip()
        configured_llama_dir = (os.getenv("LLAMA_CPP_BIN_DIR") or "tools/llama.cpp").strip()
        llama_dir = Path(configured_llama_dir)
        if not llama_dir.is_absolute():
            llama_dir = ROOT / llama_dir
        self.llama_cpp_bin_dir = llama_dir

    def snapshot(self) -> Dict[str, Any]:
        return {
            "os": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_count": os.cpu_count() or 0,
            "memory_gb": self._memory_gb(),
            "gpu": self._gpu_info(),
            "ollama": self._ollama_info(),
            "llama_cpp": self._llama_cpp_info(),
            "hosted": self._hosted_provider_info(),
            "developer_assistants": self._developer_assistant_info(),
        }

    def _memory_gb(self) -> float:
        try:
            if os.name == "nt":
                import ctypes

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                status = MEMORYSTATUSEX()
                status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
                return round(status.ullTotalPhys / (1024**3), 2)

            page_size = os.sysconf("SC_PAGE_SIZE")
            page_count = os.sysconf("SC_PHYS_PAGES")
            return round((page_size * page_count) / (1024**3), 2)
        except Exception:
            return 0.0

    def _gpu_info(self) -> Dict[str, Any]:
        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            return {
                "available": False,
                "vendor": "",
                "gpus": [],
            }

        try:
            completed = subprocess.run(
                [
                    nvidia_smi,
                    "--query-gpu=name,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            gpus: List[Dict[str, Any]] = []
            for line in completed.stdout.splitlines():
                if not line.strip():
                    continue
                parts = [part.strip() for part in line.split(",")]
                name = parts[0] if parts else "NVIDIA GPU"
                memory_mb = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                gpus.append(
                    {
                        "name": name,
                        "memory_gb": round(memory_mb / 1024, 2),
                    }
                )
            return {
                "available": bool(gpus),
                "vendor": "nvidia",
                "gpus": gpus,
            }
        except Exception:
            return {
                "available": False,
                "vendor": "nvidia",
                "gpus": [],
            }

    def _ollama_info(self) -> Dict[str, Any]:
        available = bool(shutil.which("ollama"))
        try:
            response = requests.get(f"{self.ollama_base}/api/tags", timeout=5)
            response.raise_for_status()
            payload = response.json()
            models = [model.get("name", "") for model in payload.get("models", []) if model.get("name")]
            return {
                "available": True,
                "api_reachable": True,
                "models": models,
                "count": len(models),
            }
        except Exception:
            return {
                "available": available,
                "api_reachable": False,
                "models": [],
                "count": 0,
            }

    def _llama_cpp_info(self) -> Dict[str, Any]:
        cli_path = self._find_llama_cpp_binary("llama-cli")
        server_path = self._find_llama_cpp_binary("llama-server")
        available = bool(cli_path or server_path)
        version = ""

        executable = cli_path or server_path
        if executable:
            try:
                completed = subprocess.run(
                    [str(executable), "--version"],
                    cwd=str(executable.parent),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                output = (completed.stdout or completed.stderr).strip().splitlines()
                version = next(
                    (line.strip() for line in output if line.lower().startswith("version:")),
                    output[0].strip() if output else "",
                )
            except Exception:
                version = ""

        return {
            "available": available,
            "cli_path": str(cli_path) if cli_path else "",
            "server_path": str(server_path) if server_path else "",
            "bin_dir": str(self.llama_cpp_bin_dir),
            "version": version,
            "message": (
                "llama.cpp is available locally."
                if available
                else "llama.cpp was not found in LLAMA_CPP_BIN_DIR or PATH."
            ),
        }

    def _find_llama_cpp_binary(self, name: str) -> Path | None:
        executable_names = [name]
        if os.name == "nt":
            executable_names.insert(0, f"{name}.exe")

        for executable_name in executable_names:
            candidate = self.llama_cpp_bin_dir / executable_name
            if candidate.exists():
                return candidate

        for executable_name in executable_names:
            found = shutil.which(executable_name)
            if found:
                return Path(found)
        return None

    def _hosted_provider_info(self) -> Dict[str, Any]:
        return {
            "github_models": self._github_models_info(),
            "huggingface": self._huggingface_info(),
            "cloudflare_workers_ai": self._cloudflare_workers_ai_info(),
            "xai_grok": self._xai_grok_info(),
            "modal": self._modal_info(),
            "lambda_labs": self._lambda_labs_info(),
            "runpod": self._runpod_info(),
        }

    def _developer_assistant_info(self) -> Dict[str, Any]:
        return {
            "codebuddy": CodeBuddyProbe().snapshot(),
        }

    def _github_models_info(self) -> Dict[str, Any]:
        lane_id = "github-models"
        if self.health.is_on_cooldown(lane_id):
            remaining = self.health.get_cooldown_remaining(lane_id)
            return {
                "configured": True,
                "reachable": False,
                "available": False,
                "on_cooldown": True,
                "cooldown_remaining_seconds": remaining,
                "message": f"GitHub Models is on cooldown for {remaining}s due to rate limits.",
            }

        if not self.github_token:
            help_payload = github_models_status_help(
                None,
                model=self.github_model,
                base_url=self.github_base_url,
                api_version=self.github_api_version,
            )
            return {
                "configured": False,
                "reachable": False,
                "available": False,
                "model": self.github_model,
                **help_payload,
            }
        try:
            response = requests.get(
                self.github_catalog_url,
                headers=github_models_headers(self.github_token, self.github_api_version),
                timeout=10,
            )
            if not response.ok:
                if response.status_code == 429:
                    self.health.record_cooldown(lane_id, minutes=60)

                help_payload = github_models_status_help(
                    response.status_code,
                    model=self.github_model,
                    body=response.text,
                    base_url=self.github_base_url,
                    api_version=self.github_api_version,
                )
                return {
                    "configured": True,
                    "reachable": True,
                    "available": False,
                    "catalog_available": False,
                    "status_code": response.status_code,
                    "model": self.github_model,
                    **help_payload,
                }
            payload = response.json()
            model_ids = [
                model.get("id", "")
                for model in payload
                if isinstance(model, dict) and model.get("id")
            ]
            inference = self._github_models_inference_check(model_ids)
            if not inference["available"] and inference.get("status_code") == 429:
                self.health.record_cooldown(lane_id, minutes=60)

            return {
                "configured": True,
                "reachable": True,
                "catalog_available": True,
                "available": inference["available"],
                "model_count": len(model_ids),
                "sample_models": model_ids[:5],
                "inference_model": self.github_model,
                "model_candidates": inference.get("model_candidates", self.github_model_candidates),
                "working_model": inference.get("working_model", ""),
                "inference_status_code": inference.get("status_code"),
                "attempts": inference.get("attempts", []),
                "issue": inference.get("issue", ""),
                "required_permission": GITHUB_MODELS_REQUIRED_PERMISSION,
                "base_url": self.github_base_url,
                "chat_completions_url": self.github_chat_url,
                "openai_compatible_config": inference.get("openai_compatible_config", {}),
                "curl_hint": inference.get("curl_hint", ""),
                "api_version_warning": inference.get("api_version_warning", ""),
                "next_action": inference.get("next_action", ""),
                "remediation": inference.get("remediation", []),
                "message": inference["message"],
            }
        except Exception as exc:
            return {
                "configured": True,
                "reachable": False,
                "available": False,
                "model": self.github_model,
                "base_url": self.github_base_url,
                "catalog_url": self.github_catalog_url,
                "remediation": [
                    "Check network access to models.github.ai.",
                    "Verify NOMAD_GITHUB_MODELS_BASE_URL and proxy/firewall settings.",
                ],
                "message": f"GitHub Models probe failed: {exc}",
            }

    def _github_models_inference_check(self, catalog_model_ids: List[str] | None = None) -> Dict[str, Any]:
        candidates = github_model_candidates(self.github_model, catalog_model_ids)
        attempts: List[Dict[str, Any]] = []
        last_help: Dict[str, Any] = {}
        try:
            for model in candidates:
                response = requests.post(
                    self.github_chat_url,
                    headers=github_models_headers(
                        self.github_token,
                        self.github_api_version,
                        json_request=True,
                    ),
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "Reply with OK."}],
                        "max_tokens": 8,
                        "temperature": 0,
                    },
                    timeout=15,
                )
                if response.ok:
                    message = f"GitHub Models inference is reachable with {model}."
                    if model != self.github_model:
                        message += f" Set NOMAD_GITHUB_MODEL={model} to make it the primary model."
                    return {
                        "available": True,
                        "status_code": response.status_code,
                        "working_model": model,
                        "model_candidates": candidates,
                        "attempts": attempts,
                        "next_action": (
                            ""
                            if model == self.github_model
                            else f"Set NOMAD_GITHUB_MODEL={model}."
                        ),
                        "remediation": [],
                        "message": message,
                    }

                last_help = github_models_status_help(
                    response.status_code,
                    model=model,
                    body=response.text,
                    base_url=self.github_base_url,
                    api_version=self.github_api_version,
                )
                attempts.append(
                    {
                        "model": model,
                        "status_code": response.status_code,
                        "issue": last_help.get("issue"),
                        "next_action": last_help.get("next_action"),
                    }
                )
                if response.status_code not in {400, 404, 422}:
                    return {
                        "available": False,
                        "status_code": response.status_code,
                        "model_candidates": candidates,
                        "attempts": attempts,
                        **last_help,
                    }

            return {
                "available": False,
                "status_code": attempts[-1]["status_code"] if attempts else None,
                "model_candidates": candidates,
                "attempts": attempts,
                **last_help,
            }
        except Exception as exc:
            return {
                "available": False,
                "model_candidates": candidates,
                "attempts": attempts,
                "base_url": self.github_base_url,
                "chat_completions_url": self.github_chat_url,
                "remediation": [
                    "Check network access to models.github.ai.",
                    "Verify proxy/firewall settings and retry the curl_hint from the compute probe.",
                ],
                "message": f"GitHub Models inference probe failed: {exc}",
            }

    def _huggingface_info(self) -> Dict[str, Any]:
        if not self.hf_token:
            return {
                "configured": False,
                "reachable": False,
                "available": False,
                "message": "No Hugging Face token configured.",
            }
        try:
            response = requests.get(
                "https://huggingface.co/api/whoami-v2",
                headers={"Authorization": f"Bearer {self.hf_token}"},
                timeout=10,
            )
            if not response.ok:
                return {
                    "configured": True,
                    "reachable": True,
                    "available": False,
                    "status_code": response.status_code,
                    "message": f"Hugging Face token check failed with {response.status_code}.",
                }
            payload = response.json()
            auth = payload.get("auth") or {}
            return {
                "configured": True,
                "reachable": True,
                "available": True,
                "user": payload.get("name") or payload.get("fullname") or "",
                "scopes": auth.get("accessToken", {}).get("role") or auth.get("type") or "",
                "message": "Hugging Face token is valid.",
            }
        except Exception as exc:
            return {
                "configured": True,
                "reachable": False,
                "available": False,
                "message": f"Hugging Face probe failed: {exc}",
            }

    def _modal_info(self) -> Dict[str, Any]:
        configured = bool(self.modal_token_id and self.modal_token_secret)
        if not configured:
            return {
                "configured": False,
                "reachable": False,
                "available": False,
                "config_path": str(_modal_config_path()),
                "message": "No MODAL_TOKEN_ID/MODAL_TOKEN_SECRET or usable ~/.modal.toml profile configured.",
            }
        # Modal doesn't have a simple "whoami" REST endpoint without their SDK,
        # but we can check if the CLI or SDK is installed as a proxy for 'reachable'.
        cli_available = bool(shutil.which("modal"))
        sdk_available = importlib.util.find_spec("modal") is not None
        reachable = bool(cli_available or sdk_available)
        return {
            "configured": True,
            "reachable": reachable,
            "available": reachable,
            "cli_available": cli_available,
            "sdk_available": sdk_available,
            "credential_source": self.modal_credential_source or "unknown",
            "profile": self.modal_profile,
            "config_path": str(_modal_config_path()) if self.modal_credential_source == "modal_config" else "",
            "message": (
                "Modal credentials configured"
                + (f" via {self.modal_credential_source}" if self.modal_credential_source else "")
                + "."
                + (" CLI is also available." if cli_available else " SDK is available; CLI executable not found on PATH.")
            ),
        }

    def _lambda_labs_info(self) -> Dict[str, Any]:
        lane_id = "lambda-labs"
        if self.health.is_on_cooldown(lane_id):
            remaining = self.health.get_cooldown_remaining(lane_id)
            return {
                "configured": True,
                "reachable": False,
                "available": False,
                "on_cooldown": True,
                "cooldown_remaining_seconds": remaining,
                "message": f"Lambda Labs is on cooldown for {remaining}s due to rate limits.",
            }

        api_token = (os.getenv("LAMBDA_LABS_API_TOKEN") or "").strip()
        if not api_token:
            return {
                "configured": False,
                "reachable": False,
                "available": False,
                "message": "No LAMBDA_LABS_API_TOKEN configured.",
            }
        try:
            response = requests.get(
                "https://cloud.lambdalabs.com/api/v1/instance-types",
                headers={"Authorization": f"Basic {api_token}:"}, # Lambda uses Basic auth with token as username
                timeout=10,
            )
            if response.ok:
                return {
                    "configured": True,
                    "reachable": True,
                    "available": True,
                    "status_code": response.status_code,
                    "message": "Lambda Labs API is reachable and token is valid.",
                }
            if response.status_code == 429:
                self.health.record_cooldown(lane_id, minutes=60)

            return {
                "configured": True,
                "reachable": True,
                "available": False,
                "status_code": response.status_code,
                "message": f"Lambda Labs API check failed with {response.status_code}.",
            }
        except Exception as exc:
            return {
                "configured": True,
                "reachable": False,
                "available": False,
                "message": f"Lambda Labs probe failed: {exc}",
            }

    def _runpod_info(self) -> Dict[str, Any]:
        lane_id = "runpod"
        if self.health.is_on_cooldown(lane_id):
            remaining = self.health.get_cooldown_remaining(lane_id)
            return {
                "configured": True,
                "reachable": False,
                "available": False,
                "on_cooldown": True,
                "cooldown_remaining_seconds": remaining,
                "message": f"RunPod is on cooldown for {remaining}s due to rate limits.",
            }

        api_key = (os.getenv("RUNPOD_API_KEY") or "").strip()
        if not api_key:
            return {
                "configured": False,
                "reachable": False,
                "available": False,
                "message": "No RUNPOD_API_KEY configured.",
            }
        try:
            # RunPod uses GraphQL for their main API
            response = requests.post(
                "https://api.runpod.io/v1/user/self",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"query": "{ myself { id email } }"},
                timeout=10,
            )
            if response.ok:
                return {
                    "configured": True,
                    "reachable": True,
                    "available": True,
                    "status_code": response.status_code,
                    "message": "RunPod API is reachable and API key is valid.",
                }
            if response.status_code == 429:
                self.health.record_cooldown(lane_id, minutes=60)

            return {
                "configured": True,
                "reachable": True,
                "available": False,
                "status_code": response.status_code,
                "message": f"RunPod API check failed with {response.status_code}.",
            }
        except Exception as exc:
            return {
                "configured": True,
                "reachable": False,
                "available": False,
                "message": f"RunPod probe failed: {exc}",
            }

    def _cloudflare_workers_ai_info(self) -> Dict[str, Any]:
        lane_id = "cloudflare-workers-ai"
        if self.health.is_on_cooldown(lane_id):
            remaining = self.health.get_cooldown_remaining(lane_id)
            return {
                "configured": True,
                "reachable": False,
                "available": False,
                "on_cooldown": True,
                "cooldown_remaining_seconds": remaining,
                "message": f"Cloudflare Workers AI is on cooldown for {remaining}s due to rate limits.",
            }

        configured = bool(self.cloudflare_account_id and self.cloudflare_api_token)
        if not configured:
            return {
                "configured": False,
                "reachable": False,
                "available": False,
                "message": "No CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN configured.",
            }
        try:
            response = requests.post(
                f"https://api.cloudflare.com/client/v4/accounts/{self.cloudflare_account_id}/ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.cloudflare_api_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.cloudflare_model,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "max_tokens": 8,
                    "temperature": 0,
                },
                timeout=15,
            )
            if not response.ok:
                if response.status_code == 429:
                    self.health.record_cooldown(lane_id, minutes=60)

                return {
                    "configured": True,
                    "reachable": True,
                    "available": False,
                    "status_code": response.status_code,
                    "inference_model": self.cloudflare_model,
                    "message": (
                        "Cloudflare Workers AI credentials are present, but the probe failed "
                        f"with {response.status_code}."
                    ),
                }
            return {
                "configured": True,
                "reachable": True,
                "available": True,
                "status_code": response.status_code,
                "inference_model": self.cloudflare_model,
                "message": f"Cloudflare Workers AI is reachable with {self.cloudflare_model}.",
            }
        except Exception as exc:
            return {
                "configured": True,
                "reachable": False,
                "available": False,
                "inference_model": self.cloudflare_model,
                "message": f"Cloudflare Workers AI probe failed: {exc}",
            }

    def _xai_grok_info(self) -> Dict[str, Any]:
        if not self.xai_token:
            return {
                "configured": False,
                "reachable": False,
                "available": False,
                "model": self.xai_model,
                **xai_status_help(None, model=self.xai_model, base_url=self.xai_base_url),
            }
        return self._xai_grok_inference_check()

    def _xai_grok_inference_check(self) -> Dict[str, Any]:
        lane_id = "xai-grok"
        if self.health.is_on_cooldown(lane_id):
            remaining = self.health.get_cooldown_remaining(lane_id)
            return {
                "configured": True,
                "reachable": False,
                "available": False,
                "on_cooldown": True,
                "cooldown_remaining_seconds": remaining,
                "message": f"xAI Grok is on cooldown for {remaining}s due to rate limits.",
            }

        attempts: List[Dict[str, Any]] = []
        last_help: Dict[str, Any] = {}
        try:
            for model in self.xai_model_candidates:
                response = requests.post(
                    self.xai_chat_url,
                    headers={
                        "Authorization": f"Bearer {self.xai_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "Reply with OK."}],
                        "max_tokens": 8,
                        "temperature": 0,
                    },
                    timeout=15,
                )
                if response.ok:
                    message = f"xAI Grok inference is reachable with {model}."
                    if model != self.xai_model:
                        message += f" Set NOMAD_XAI_MODEL={model} to make it the primary model."
                    return {
                        "configured": True,
                        "reachable": True,
                        "available": True,
                        "status_code": response.status_code,
                        "model": self.xai_model,
                        "working_model": model,
                        "model_candidates": self.xai_model_candidates,
                        "attempts": attempts,
                        "base_url": self.xai_base_url,
                        "chat_completions_url": self.xai_chat_url,
                        "openai_compatible_config": xai_status_help(
                            response.status_code,
                            model=model,
                            base_url=self.xai_base_url,
                        ).get("openai_compatible_config", {}),
                        "next_action": "" if model == self.xai_model else f"Set NOMAD_XAI_MODEL={model}.",
                        "remediation": [],
                        "message": message,
                    }

                if response.status_code == 429:
                    self.health.record_cooldown(lane_id, minutes=60)

                last_help = xai_status_help(
                    response.status_code,
                    model=model,
                    body=response.text,
                    base_url=self.xai_base_url,
                )
                attempts.append(
                    {
                        "model": model,
                        "status_code": response.status_code,
                        "issue": last_help.get("issue"),
                        "next_action": last_help.get("next_action"),
                    }
                )
                if response.status_code not in {400, 404, 422}:
                    return {
                        "configured": True,
                        "reachable": True,
                        "available": False,
                        "model": self.xai_model,
                        "attempts": attempts,
                        **last_help,
                    }

            return {
                "configured": True,
                "reachable": True,
                "available": False,
                "model": self.xai_model,
                "attempts": attempts,
                **last_help,
            }
        except Exception as exc:
            return {
                "configured": True,
                "reachable": False,
                "available": False,
                "model": self.xai_model,
                "base_url": self.xai_base_url,
                "chat_completions_url": self.xai_chat_url,
                "attempts": attempts,
                "remediation": [
                    "Check network access to api.x.ai.",
                    "Verify NOMAD_XAI_BASE_URL and proxy/firewall settings.",
                ],
                "message": f"xAI Grok probe failed: {exc}",
            }
