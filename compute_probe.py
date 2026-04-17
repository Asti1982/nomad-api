import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv


load_dotenv()
ROOT = Path(__file__).resolve().parent


class LocalComputeProbe:
    def __init__(self) -> None:
        load_dotenv(override=True)
        self.ollama_base = (os.getenv("OLLAMA_API_BASE") or "http://127.0.0.1:11434").rstrip("/")
        self.github_token = (
            os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
            or os.getenv("GITHUB_TOKEN")
            or ""
        ).strip()
        self.github_model = (os.getenv("NOMAD_GITHUB_MODEL") or "openai/gpt-4o-mini").strip()
        self.github_api_version = (
            os.getenv("NOMAD_GITHUB_MODELS_API_VERSION") or "2026-03-10"
        ).strip()
        self.hf_token = (
            os.getenv("HF_TOKEN")
            or os.getenv("HUGGINGFACEHUB_API_TOKEN")
            or os.getenv("HUGGING_FACE_HUB_TOKEN")
            or ""
        ).strip()
        self.modal_token_id = (os.getenv("MODAL_TOKEN_ID") or "").strip()
        self.modal_token_secret = (os.getenv("MODAL_TOKEN_SECRET") or "").strip()
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
            "modal": self._modal_info(),
        }

    def _github_models_info(self) -> Dict[str, Any]:
        if not self.github_token:
            return {
                "configured": False,
                "reachable": False,
                "available": False,
                "message": "No GITHUB_TOKEN or GITHUB_PERSONAL_ACCESS_TOKEN configured.",
            }
        try:
            response = requests.get(
                "https://models.github.ai/catalog/models",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.github_token}",
                    "X-GitHub-Api-Version": self.github_api_version,
                },
                timeout=10,
            )
            if not response.ok:
                return {
                    "configured": True,
                    "reachable": True,
                    "available": False,
                    "status_code": response.status_code,
                    "message": f"GitHub Models catalog request failed with {response.status_code}.",
                }
            payload = response.json()
            model_ids = [
                model.get("id", "")
                for model in payload
                if isinstance(model, dict) and model.get("id")
            ]
            inference = self._github_models_inference_check()
            return {
                "configured": True,
                "reachable": True,
                "catalog_available": True,
                "available": inference["available"],
                "model_count": len(model_ids),
                "sample_models": model_ids[:5],
                "inference_model": self.github_model,
                "inference_status_code": inference.get("status_code"),
                "message": inference["message"],
            }
        except Exception as exc:
            return {
                "configured": True,
                "reachable": False,
                "available": False,
                "message": f"GitHub Models probe failed: {exc}",
            }

    def _github_models_inference_check(self) -> Dict[str, Any]:
        try:
            response = requests.post(
                "https://models.github.ai/inference/chat/completions",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.github_token}",
                    "Content-Type": "application/json",
                    "X-GitHub-Api-Version": self.github_api_version,
                },
                json={
                    "model": self.github_model,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "max_tokens": 8,
                    "temperature": 0,
                },
                timeout=15,
            )
            if not response.ok:
                return {
                    "available": False,
                    "status_code": response.status_code,
                    "message": (
                        f"GitHub Models catalog is reachable, but inference with "
                        f"{self.github_model} failed with {response.status_code}."
                    ),
                }
            return {
                "available": True,
                "status_code": response.status_code,
                "message": f"GitHub Models inference is reachable with {self.github_model}.",
            }
        except Exception as exc:
            return {
                "available": False,
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
        return {
            "configured": configured,
            "reachable": False,
            "available": False,
            "message": (
                "Modal credentials detected, but live probe is not implemented yet."
                if configured
                else "No Modal credentials configured."
            ),
        }
