#!/usr/bin/env python3
"""AGP paper benchmark runner for Nomad.

This runner closes the practical gap between local benchmark assets and
Nomad's receipt-gated paper benchmark endpoint:

* inventories GPQA/AIME/GAIA/LeetCode dataset and prediction files,
* builds the exact payload expected by /swarm/agp/paper-benchmark-runs,
* can evaluate locally without exposing gated datasets to the public service,
* refuses to submit local filesystem paths to a remote Render host.

It does not generate answers, execute untrusted code, print secrets, or treat
lite fixtures as full paper-grade evidence.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


MODES = ("gpqa_diamond", "aime", "gaia", "leetcode")
DEFAULT_BASE_URL = os.getenv("NOMAD_PUBLIC_API_URL", "https://www.syndiode.com/nomad").rstrip("/")
DEFAULT_AGENT_ID = "nomad-agp-paper-benchmark-runner-local"
DEFAULT_DATA_DIR = Path("data") / "agp-benchmarks"
DEFAULT_PROVIDER_QUOTA_STATE = ".nomad_provider_quota.json"

DATASET_ENV = {
    "gpqa_diamond": "NOMAD_AGP_GPQA_DATASET_PATH",
    "aime": "NOMAD_AGP_AIME_DATASET_PATH",
    "gaia": "NOMAD_AGP_GAIA_DATASET_PATH",
    "leetcode": "NOMAD_AGP_LEETCODE_DATASET_PATH",
}
DATASET_URL_ENV = {
    "gpqa_diamond": "NOMAD_AGP_GPQA_DATASET_URL",
    "aime": "NOMAD_AGP_AIME_DATASET_URL",
    "gaia": "NOMAD_AGP_GAIA_DATASET_URL",
    "leetcode": "NOMAD_AGP_LEETCODE_DATASET_URL",
}
PREDICTION_ENV = {
    "gpqa_diamond": "NOMAD_AGP_GPQA_PREDICTIONS_PATH",
    "aime": "NOMAD_AGP_AIME_PREDICTIONS_PATH",
    "gaia": "NOMAD_AGP_GAIA_PREDICTIONS_PATH",
    "leetcode": "NOMAD_AGP_LEETCODE_PREDICTIONS_PATH",
}
PREDICTION_URL_ENV = {
    "gpqa_diamond": "NOMAD_AGP_GPQA_PREDICTIONS_URL",
    "aime": "NOMAD_AGP_AIME_PREDICTIONS_URL",
    "gaia": "NOMAD_AGP_GAIA_PREDICTIONS_URL",
    "leetcode": "NOMAD_AGP_LEETCODE_PREDICTIONS_URL",
}

DATASET_STEMS = {
    "gpqa_diamond": ("gpqa_diamond", "gpqa-diamond", "gpqa"),
    "aime": ("aime", "aime2024", "aime_2024", "aime-2024"),
    "gaia": ("gaia", "gaia_validation", "gaia-validation"),
    "leetcode": ("leetcode", "humaneval", "human_eval", "leetcode_results"),
}
PREDICTION_STEMS = {
    mode: tuple(
        dict.fromkeys(
            tuple(f"{stem}_predictions" for stem in stems)
            + tuple(f"{stem}-predictions" for stem in stems)
            + tuple(f"{stem}.predictions" for stem in stems)
        )
    )
    for mode, stems in DATASET_STEMS.items()
}
DATASET_SUFFIXES = (".csv", ".jsonl", ".json", ".jsonl.gz", ".ndjson")
PREDICTION_SUFFIXES = (".json", ".jsonl", ".ndjson")
MODEL_KEY_NAMES = (
    "OPENROUTER_API_KEY",
    "GITHUB_TOKEN",
    "GITHUB_PERSONAL_ACCESS_TOKEN",
    "XAI_API_KEY",
    "HF_TOKEN",
    "HUGGINGFACE_TOKEN",
)
ANSWER_KEYS = {
    "answer",
    "Answer",
    "correct_answer",
    "Correct Answer",
    "final_answer",
    "Final answer",
    "target",
    "canonical_solution",
}
QUESTION_KEYS = (
    "question",
    "Question",
    "problem",
    "Problem",
    "prompt",
    "Prompt",
    "task",
    "Task",
    "query",
    "Query",
)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _now_ts() -> float:
    return time.time()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _as_path(value: str | Path) -> Path:
    p = Path(value)
    if not p.is_absolute():
        p = (_repo_root() / p).resolve()
    return p


def _looks_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_local_base_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local")


def _load_env_file(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {"loaded": False, "path": "", "keys_loaded": 0}
    p = Path(path)
    if not p.exists():
        return {"loaded": False, "path": str(p), "reason": "env_file_missing", "keys_loaded": 0}
    count = 0
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return {"loaded": False, "path": str(p), "reason": f"env_read_failed:{type(exc).__name__}", "keys_loaded": 0}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            count += 1
    return {"loaded": True, "path": str(p), "keys_loaded": count}


def _first_existing(base_dir: Path, stems: tuple[str, ...], suffixes: tuple[str, ...]) -> Path | None:
    for stem in stems:
        for suffix in suffixes:
            candidate = base_dir / f"{stem}{suffix}"
            if candidate.exists():
                return candidate.resolve()
    return None


def _safe_exists(path_text: str) -> bool:
    try:
        return Path(path_text).exists()
    except OSError:
        return False


class ProviderRateLimitError(RuntimeError):
    def __init__(self, message: str, *, retry_after_seconds: float = 0.0, status: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = max(0.0, float(retry_after_seconds or 0.0))
        self.status = status


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default)) or default))
    except ValueError:
        return default


def _parse_retry_after(value: str | None) -> float:
    if not value:
        return 0.0
    text = value.strip()
    try:
        return max(0.0, float(text))
    except ValueError:
        return 0.0


def _provider_state_key(config: dict[str, Any]) -> str:
    provider = str(config.get("provider") or "provider").strip().lower()
    model = str(config.get("model") or "model").strip().lower().replace("/", "_").replace(":", "_")
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in f"{provider}:{model}")


def _quota_defaults(config: dict[str, Any]) -> dict[str, float | int]:
    provider = str(config.get("provider") or "").lower()
    model = str(config.get("model") or "").lower()
    free_model = provider == "openrouter" and (model == "openrouter/free" or model.endswith(":free"))
    return {
        "min_interval_seconds": _float_env("NOMAD_AGP_PROVIDER_MIN_INTERVAL_SECONDS", 20.0 if free_model else 6.0),
        "cooldown_seconds": _float_env("NOMAD_AGP_PROVIDER_COOLDOWN_SECONDS", 1800.0 if free_model else 900.0),
        "window_seconds": _float_env("NOMAD_AGP_PROVIDER_WINDOW_SECONDS", 3600.0),
        "window_call_limit": _int_env("NOMAD_AGP_PROVIDER_WINDOW_CALL_LIMIT", 18 if free_model else 60),
    }


class ProviderQuota:
    def __init__(
        self,
        *,
        state_path: str | Path,
        config: dict[str, Any],
        min_interval_seconds: float | None = None,
        cooldown_seconds: float | None = None,
        window_seconds: float | None = None,
        window_call_limit: int | None = None,
        sleep: bool = True,
    ):
        defaults = _quota_defaults(config)
        self.state_path = Path(state_path)
        self.key = _provider_state_key(config)
        self.min_interval_seconds = float(defaults["min_interval_seconds"] if min_interval_seconds is None else min_interval_seconds)
        self.cooldown_seconds = float(defaults["cooldown_seconds"] if cooldown_seconds is None else cooldown_seconds)
        self.window_seconds = float(defaults["window_seconds"] if window_seconds is None else window_seconds)
        self.window_call_limit = int(defaults["window_call_limit"] if window_call_limit is None else window_call_limit)
        self.sleep = bool(sleep)

    def _read(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"schema": "nomad.provider_quota_state.v1", "providers": {}}
        try:
            parsed = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema": "nomad.provider_quota_state.v1", "providers": {}}
        if not isinstance(parsed, dict):
            return {"schema": "nomad.provider_quota_state.v1", "providers": {}}
        parsed.setdefault("providers", {})
        return parsed

    def _write(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")

    def _provider(self, state: dict[str, Any]) -> dict[str, Any]:
        providers = state.setdefault("providers", {})
        provider = providers.setdefault(self.key, {})
        provider.setdefault("success_timestamps", [])
        provider.setdefault("cooldown_until", 0.0)
        provider.setdefault("last_call_at", 0.0)
        return provider

    def before_call(self) -> dict[str, Any]:
        state = self._read()
        provider = self._provider(state)
        now = _now_ts()
        cooldown_until = float(provider.get("cooldown_until") or 0.0)
        if cooldown_until > now:
            raise ProviderRateLimitError(
                "provider_cooling_down",
                retry_after_seconds=round(cooldown_until - now, 3),
            )
        timestamps = [
            float(item)
            for item in provider.get("success_timestamps", [])
            if isinstance(item, (int, float)) and now - float(item) <= self.window_seconds
        ]
        provider["success_timestamps"] = timestamps
        if self.window_call_limit > 0 and len(timestamps) >= self.window_call_limit:
            retry_after = max(1.0, self.window_seconds - (now - min(timestamps)))
            provider["cooldown_until"] = now + retry_after
            self._write(state)
            raise ProviderRateLimitError(
                "provider_window_call_limit_reached",
                retry_after_seconds=round(retry_after, 3),
            )
        last = float(provider.get("last_call_at") or 0.0)
        wait = max(0.0, self.min_interval_seconds - (now - last))
        if wait > 0:
            if self.sleep:
                time.sleep(wait)
            else:
                raise ProviderRateLimitError("provider_min_interval_not_elapsed", retry_after_seconds=round(wait, 3))
        provider["last_call_at"] = _now_ts()
        self._write(state)
        return {"ok": True, "waited_seconds": round(wait, 3)}

    def after_success(self) -> None:
        state = self._read()
        provider = self._provider(state)
        now = _now_ts()
        timestamps = [
            float(item)
            for item in provider.get("success_timestamps", [])
            if isinstance(item, (int, float)) and now - float(item) <= self.window_seconds
        ]
        timestamps.append(now)
        provider["success_timestamps"] = timestamps
        provider["last_success_at"] = now
        provider["last_error"] = ""
        self._write(state)

    def after_rate_limit(self, retry_after_seconds: float = 0.0, *, reason: str = "provider_rate_limited") -> float:
        state = self._read()
        provider = self._provider(state)
        now = _now_ts()
        retry_after = max(float(retry_after_seconds or 0.0), self.cooldown_seconds)
        provider["cooldown_until"] = now + retry_after
        provider["last_error"] = reason
        provider["last_rate_limited_at"] = now
        self._write(state)
        return retry_after


def _read_small_text(path: str | Path, *, max_bytes: int = 4_000_000) -> str:
    raw = Path(path).read_bytes()
    if len(raw) > max_bytes:
        raise ValueError(f"file_too_large_for_free_tier:{len(raw)}>{max_bytes}")
    if str(path).endswith(".gz"):
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def _parse_dataset_records(path: str | Path) -> list[dict[str, Any]]:
    text = _read_small_text(path)
    hint = str(path).lower()
    if hint.endswith(".csv"):
        return [row for row in csv.DictReader(io.StringIO(text)) if isinstance(row, dict)]
    if hint.endswith(".json"):
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [row for row in parsed if isinstance(row, dict)]
        if isinstance(parsed, dict):
            for key in ("data", "records", "examples", "questions", "tasks"):
                value = parsed.get(key)
                if isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]
            return [parsed]
        return []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _record_id(record: dict[str, Any], index: int) -> str:
    for key in ("id", "ID", "task_id", "question_id", "record_id", "Record ID", "problem_id", "name"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return str(index + 1)


def _question_text(record: dict[str, Any]) -> str:
    for key in QUESTION_KEYS:
        value = str(record.get(key) or "").strip()
        if value:
            return value
    visible = {
        str(key): value
        for key, value in record.items()
        if str(key) not in ANSWER_KEYS and value not in (None, "")
    }
    return json.dumps(visible, ensure_ascii=True, sort_keys=True)[:4000]


def _choice_lines(record: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, value in record.items():
        label = str(key)
        if label in ANSWER_KEYS or label in QUESTION_KEYS:
            continue
        if "answer" in label.lower() or "choice" in label.lower() or "option" in label.lower():
            text = str(value or "").strip()
            if text:
                lines.append(f"{label}: {text}")
    return lines[:12]


def _prompt_for_record(mode: str, record: dict[str, Any]) -> str:
    instructions = {
        "gpqa_diamond": "Return only the exact final answer text for this graduate-level science question.",
        "aime": "Return only the final numeric AIME answer, with no explanation.",
        "gaia": "Return only the concise final answer. If the task requires unavailable files or browsing, return UNKNOWN.",
        "leetcode": "Do not solve code tasks here. LeetCode/HumanEval needs an execution result file with passed/ok booleans.",
    }
    parts = [instructions.get(mode, "Return only the final answer."), "", _question_text(record)]
    choices = _choice_lines(record)
    if choices:
        parts.extend(["", "Candidate answer choices:", *choices])
    return "\n".join(parts).strip()[:8000]


def discover_sources(
    *,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    overrides: dict[str, dict[str, str]] | None = None,
    allow_remote_fetch: bool = False,
    allow_remote_predictions: bool = False,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Return Nomad dataset payload specs and a redacted inventory report."""

    base_dir = _as_path(data_dir)
    raw_overrides = overrides or {}
    datasets: dict[str, dict[str, Any]] = {}
    report: dict[str, Any] = {
        "schema": "nomad.agp_paper_benchmark_runner_inventory.v1",
        "generated_at": _now(),
        "data_dir": str(base_dir),
        "modes": {},
        "model_keys_present": {name: bool(os.getenv(name)) for name in MODEL_KEY_NAMES},
    }
    for mode in MODES:
        override = raw_overrides.get(mode, {})
        path = (
            override.get("path")
            or os.getenv(DATASET_ENV[mode])
            or str(_first_existing(base_dir, DATASET_STEMS[mode], DATASET_SUFFIXES) or "")
        )
        url = override.get("url") or os.getenv(DATASET_URL_ENV[mode]) or ""
        pred_path = (
            override.get("predictions_path")
            or os.getenv(PREDICTION_ENV[mode])
            or str(_first_existing(base_dir, PREDICTION_STEMS[mode], PREDICTION_SUFFIXES) or "")
        )
        pred_url = override.get("predictions_url") or os.getenv(PREDICTION_URL_ENV[mode]) or ""
        spec: dict[str, Any] = {}
        if path:
            spec["path"] = str(Path(path).resolve()) if not _looks_url(path) else path
        if url:
            spec["url"] = url
        if pred_path:
            spec["predictions_path"] = str(Path(pred_path).resolve()) if not _looks_url(pred_path) else pred_path
        if pred_url:
            spec["predictions_url"] = pred_url
        if allow_remote_fetch:
            spec["allow_remote_fetch"] = True
        if allow_remote_predictions:
            spec["allow_remote_predictions"] = True
        datasets[mode] = spec
        report["modes"][mode] = {
            "dataset_path_present": bool(path),
            "dataset_path_exists": _safe_exists(path) if path and not _looks_url(path) else False,
            "dataset_url_present": bool(url),
            "predictions_path_present": bool(pred_path),
            "predictions_path_exists": _safe_exists(pred_path) if pred_path and not _looks_url(pred_path) else False,
            "predictions_url_present": bool(pred_url),
            "ready_for_local_eval": bool((path and _safe_exists(path)) and (pred_path and _safe_exists(pred_path))),
            "ready_for_remote_submit": bool((url or (path and not _is_local_path(path))) and pred_url),
        }
    return datasets, report


def _is_local_path(value: str) -> bool:
    return bool(value) and not _looks_url(value)


def parse_overrides(items: list[str]) -> dict[str, dict[str, str]]:
    """Parse CLI overrides like gpqa_diamond.path=C:\\x\\gpqa.csv."""

    out: dict[str, dict[str, str]] = {mode: {} for mode in MODES}
    for item in items:
        if "=" not in item or "." not in item.split("=", 1)[0]:
            raise ValueError(f"override must look like mode.field=value: {item}")
        left, value = item.split("=", 1)
        mode, field = left.split(".", 1)
        if mode not in MODES:
            raise ValueError(f"unsupported benchmark mode: {mode}")
        if field not in {"path", "url", "predictions_path", "predictions_url"}:
            raise ValueError(f"unsupported override field for {mode}: {field}")
        out[mode][field] = value
    return out


def build_payload(
    *,
    agent_id: str = DEFAULT_AGENT_ID,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    overrides: dict[str, dict[str, str]] | None = None,
    baselines: dict[str, float] | None = None,
    allow_remote_fetch: bool = False,
    allow_remote_predictions: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    datasets, report = discover_sources(
        data_dir=data_dir,
        overrides=overrides,
        allow_remote_fetch=allow_remote_fetch,
        allow_remote_predictions=allow_remote_predictions,
    )
    payload = {
        "agent_id": agent_id,
        "datasets": datasets,
        "baselines": baselines or {mode: 0.0 for mode in MODES},
        "runner_receipt": {
            "schema": "nomad.agp_paper_benchmark_runner.v1",
            "generated_at": _now(),
            "side_effect_scope": "benchmark_receipt_payload_only",
            "truth_boundary": {
                "does_not_generate_predictions": True,
                "does_not_execute_untrusted_code": True,
                "does_not_claim_lite_as_full": True,
                "secrets_redacted": True,
            },
        },
    }
    return payload, report


def validate_submission_target(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    remote = not _is_local_base_url(base_url)
    local_dataset_paths: list[str] = []
    local_prediction_paths: list[str] = []
    datasets = payload.get("datasets") if isinstance(payload.get("datasets"), dict) else {}
    for mode, spec in datasets.items():
        if not isinstance(spec, dict):
            continue
        path = str(spec.get("path") or "")
        pred_path = str(spec.get("predictions_path") or "")
        if path and _is_local_path(path):
            local_dataset_paths.append(str(mode))
        if pred_path and _is_local_path(pred_path):
            local_prediction_paths.append(str(mode))
    ok = not (remote and (local_dataset_paths or local_prediction_paths))
    return {
        "ok": ok,
        "base_url": base_url,
        "remote_target": remote,
        "local_dataset_path_modes": local_dataset_paths,
        "local_prediction_path_modes": local_prediction_paths,
        "reason": "" if ok else "remote_nomad_cannot_read_local_filesystem_paths; run --local-eval or supply URLs",
    }


def _provider_config(provider: str, model_override: str = "") -> dict[str, Any]:
    name = provider.strip().lower()
    if name == "openrouter":
        return {
            "ok": bool(os.getenv("OPENROUTER_API_KEY")),
            "provider": "openrouter",
            "api_key": os.getenv("OPENROUTER_API_KEY", ""),
            "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            "model": model_override or os.getenv("NOMAD_AGP_BENCHMARK_MODEL") or os.getenv("OPENROUTER_MODEL", "openrouter/free"),
        }
    if name == "github":
        return {
            "ok": bool(os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")),
            "provider": "github",
            "api_key": os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", ""),
            "base_url": os.getenv("NOMAD_GITHUB_MODELS_BASE_URL", "https://models.github.ai/inference").rstrip("/"),
            "model": model_override or os.getenv("NOMAD_AGP_BENCHMARK_MODEL") or os.getenv("NOMAD_GITHUB_MODEL", "openai/gpt-4.1-mini"),
        }
    return {"ok": False, "provider": name, "reason": "unsupported_provider"}


def _chat_completion(config: dict[str, Any], prompt: str, *, timeout: float = 90.0, max_tokens: int = 80) -> str:
    if not config.get("ok"):
        raise RuntimeError(str(config.get("reason") or "provider_key_missing"))
    if not config.get("model"):
        raise RuntimeError("benchmark_model_not_configured")
    payload = {
        "model": config["model"],
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a benchmark answerer. Return only the final answer. "
                    "Do not include reasoning, markdown, citations, or prose."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max(1, int(max_tokens)),
    }
    raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {config['api_key']}",
        "User-Agent": "nomad-agp-paper-benchmark-runner/1",
    }
    if config.get("provider") == "openrouter":
        headers["HTTP-Referer"] = os.getenv("NOMAD_PUBLIC_API_URL", "https://www.syndiode.com/nomad")
        headers["X-Title"] = "Nomad AGP Paper Benchmark Runner"
    request = Request(
        f"{config['base_url']}/chat/completions",
        data=raw,
        method="POST",
        headers=headers,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 429:
            raise ProviderRateLimitError(
                "provider_returned_429",
                retry_after_seconds=_parse_retry_after(exc.headers.get("Retry-After")),
                status=429,
            ) from exc
        raise
    choices = parsed.get("choices") if isinstance(parsed, dict) else []
    if not choices:
        raise RuntimeError("provider_returned_no_choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    return str(message.get("content") or "").strip()


def _load_prediction_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(parsed, dict) and isinstance(parsed.get("predictions"), dict):
        return dict(parsed["predictions"])
    if isinstance(parsed, dict):
        return dict(parsed)
    return {}


def generate_prediction_files(
    *,
    sources: dict[str, dict[str, Any]],
    output_dir: str | Path,
    provider: str,
    model: str = "",
    max_model_calls: int = 0,
    modes: tuple[str, ...] = ("gpqa_diamond", "aime", "gaia"),
    overwrite: bool = False,
    completion_fn: Any | None = None,
    quota_state_path: str | Path | None = None,
    min_interval_seconds: float | None = None,
    cooldown_seconds: float | None = None,
    window_seconds: float | None = None,
    window_call_limit: int | None = None,
) -> dict[str, Any]:
    out_dir = _as_path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    config = _provider_config(provider, model)
    result: dict[str, Any] = {
        "schema": "nomad.agp_paper_benchmark_prediction_generation.v1",
        "generated_at": _now(),
        "provider": config.get("provider"),
        "model": config.get("model", ""),
        "max_model_calls": max_model_calls,
        "model_calls_used": 0,
        "provider_calls_attempted": 0,
        "quota_state_path": str(Path(quota_state_path) if quota_state_path else out_dir / DEFAULT_PROVIDER_QUOTA_STATE),
        "prediction_paths": {},
        "modes": {},
        "rate_limited": False,
        "retry_after_seconds": 0.0,
        "truth_boundary": {
            "requires_explicit_flag": True,
            "does_not_execute_code": True,
            "leetcode_requires_external_execution_results": True,
            "secrets_redacted": True,
        },
    }
    if max_model_calls <= 0:
        result["ok"] = False
        result["reason"] = "max_model_calls_must_be_positive"
        return result
    if not config.get("ok") or not config.get("model"):
        result["ok"] = False
        result["reason"] = config.get("reason") or "provider_key_or_model_missing"
        return result
    quota = None
    if completion_fn is None:
        quota = ProviderQuota(
            state_path=quota_state_path or (out_dir / DEFAULT_PROVIDER_QUOTA_STATE),
            config=config,
            min_interval_seconds=min_interval_seconds,
            cooldown_seconds=cooldown_seconds,
            window_seconds=window_seconds,
            window_call_limit=window_call_limit,
            sleep=True,
        )
    ask = completion_fn or (lambda cfg, prompt: _chat_completion(cfg, prompt))
    mode_state: dict[str, dict[str, Any]] = {}
    for mode in modes:
        spec = sources.get(mode) if isinstance(sources.get(mode), dict) else {}
        path = str(spec.get("path") or "")
        mode_report = {"attempted": False, "generated": 0, "skipped": 0, "errors": []}
        if mode == "leetcode":
            mode_report["errors"].append("leetcode_generation_disabled_requires_execution_results")
            result["modes"][mode] = mode_report
            continue
        if not path or _looks_url(path) or not Path(path).exists():
            mode_report["errors"].append("local_dataset_path_missing")
            result["modes"][mode] = mode_report
            continue
        pred_path = out_dir / f"{mode}_predictions.json"
        predictions = {} if overwrite else _load_prediction_object(pred_path)
        try:
            records = _parse_dataset_records(path)
        except (OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
            mode_report["errors"].append(f"dataset_parse_failed:{type(exc).__name__}")
            result["modes"][mode] = mode_report
            continue
        mode_report["attempted"] = True
        mode_state[mode] = {
            "records": records,
            "predictions": predictions,
            "pred_path": pred_path,
            "index": 0,
            "report": mode_report,
        }
        result["modes"][mode] = mode_report
    active = [mode for mode in modes if mode in mode_state]
    while active and result["model_calls_used"] < max_model_calls:
        next_active: list[str] = []
        for mode in active:
            if result["model_calls_used"] >= max_model_calls:
                next_active.append(mode)
                continue
            state = mode_state[mode]
            records = state["records"]
            predictions = state["predictions"]
            mode_report = state["report"]
            while state["index"] < len(records):
                index = state["index"]
                state["index"] += 1
                record = records[index]
                rid = _record_id(record, index)
                if rid in predictions:
                    mode_report["skipped"] += 1
                    continue
                prompt = _prompt_for_record(mode, record)
                if not prompt:
                    mode_report["skipped"] += 1
                    continue
                try:
                    if quota is not None:
                        quota.before_call()
                    result["provider_calls_attempted"] += 1
                    predictions[rid] = ask(config, prompt)
                except ProviderRateLimitError as exc:
                    retry_after = exc.retry_after_seconds
                    if quota is not None:
                        retry_after = quota.after_rate_limit(retry_after, reason=str(exc))
                    result["rate_limited"] = True
                    result["retry_after_seconds"] = round(float(retry_after or 0.0), 3)
                    mode_report["errors"].append(f"provider_rate_limited:retry_after_seconds={result['retry_after_seconds']}")
                    active = []
                    break
                except HTTPError as exc:
                    mode_report["errors"].append(f"provider_call_failed:http_{exc.code}")
                    break
                except (URLError, TimeoutError, OSError, RuntimeError, json.JSONDecodeError) as exc:
                    mode_report["errors"].append(f"provider_call_failed:{type(exc).__name__}")
                    break
                if quota is not None:
                    quota.after_success()
                result["model_calls_used"] += 1
                mode_report["generated"] += 1
                break
            if result["rate_limited"]:
                break
            if state["index"] < len(records) and not mode_report["errors"]:
                next_active.append(mode)
        if result["rate_limited"]:
            next_active = []
        active = next_active
    for mode, state in mode_state.items():
        pred_path = state["pred_path"]
        pred_path.write_text(
            json.dumps({"predictions": state["predictions"]}, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        result["prediction_paths"][mode] = str(pred_path)
        result["modes"][mode] = state["report"]
    result["ok"] = True
    return result


def run_local_evaluation(
    payload: dict[str, Any],
    *,
    repo_root: str | Path | None = None,
    ledger_path: str | Path | None = None,
    benchmark_ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root else _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from nomad_autogenesis import run_agp_paper_benchmark_evaluation

    return run_agp_paper_benchmark_evaluation(
        payload,
        base_url="local://nomad-agp-paper-benchmark-runner",
        ledger_path=Path(ledger_path) if ledger_path else None,
        benchmark_ledger_path=Path(benchmark_ledger_path) if benchmark_ledger_path else None,
        persist=True,
    )


def submit_to_nomad(base_url: str, payload: dict[str, Any], *, timeout: float = 60.0) -> dict[str, Any]:
    target = f"{base_url.rstrip('/')}/swarm/agp/paper-benchmark-runs"
    validation = validate_submission_target(base_url, payload)
    if not validation["ok"]:
        return {"ok": False, "submitted": False, "validation": validation}
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    request = Request(
        target,
        data=raw,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "nomad-agp-paper-benchmark-runner/1",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except HTTPError as exc:
        body = exc.read()
        status = exc.code
    except (OSError, URLError) as exc:
        return {"ok": False, "submitted": False, "error": type(exc).__name__, "target": target}
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        parsed = {"raw": body.decode("utf-8", errors="replace")[:1000]}
    return {"ok": 200 <= status < 300, "submitted": True, "http_status": status, "target": target, "response": parsed}


def _parse_baseline(items: list[str]) -> dict[str, float]:
    out = {mode: 0.0 for mode in MODES}
    for item in items:
        if "=" not in item:
            raise ValueError(f"baseline must look like mode=value: {item}")
        mode, value = item.split("=", 1)
        if mode not in MODES:
            raise ValueError(f"unsupported baseline mode: {mode}")
        out[mode] = float(value)
    return out


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Nomad's AGP paper benchmark adapter without faking predictions.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Nomad API base URL for --submit.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Directory containing benchmark datasets/predictions.")
    parser.add_argument("--env-file", default="", help="Optional .env file to load without printing secrets.")
    parser.add_argument("--agent-id", default=DEFAULT_AGENT_ID)
    parser.add_argument("--set", action="append", default=[], help="Override source, e.g. gpqa_diamond.path=C:\\bench\\gpqa.csv")
    parser.add_argument("--baseline", action="append", default=[], help="Baseline score, e.g. gpqa_diamond=0.42")
    parser.add_argument("--allow-remote-fetch", action="store_true", help="Allow evaluator to fetch dataset URLs.")
    parser.add_argument("--allow-remote-predictions", action="store_true", help="Allow evaluator to fetch prediction URLs.")
    parser.add_argument("--generate-predictions", action="store_true", help="Use an OpenAI-compatible provider to create prediction files.")
    parser.add_argument("--prediction-provider", default="github", choices=["github", "openrouter"], help="Provider for --generate-predictions.")
    parser.add_argument("--prediction-model", default="", help="Override model for --generate-predictions.")
    parser.add_argument("--prediction-output-dir", default="", help="Directory for generated prediction files. Defaults to --data-dir.")
    parser.add_argument("--max-model-calls", type=int, default=0, help="Hard cap for --generate-predictions.")
    parser.add_argument("--overwrite-predictions", action="store_true", help="Replace existing generated prediction files.")
    parser.add_argument("--quota-state-path", default="", help="Local provider quota state path.")
    parser.add_argument("--min-provider-interval-seconds", type=float, default=None)
    parser.add_argument("--provider-window-call-limit", type=int, default=None)
    parser.add_argument("--provider-window-seconds", type=float, default=None)
    parser.add_argument("--provider-cooldown-seconds", type=float, default=None)
    parser.add_argument("--local-eval", action="store_true", help="Evaluate by importing nomad_autogenesis locally.")
    parser.add_argument("--submit", action="store_true", help="POST to /swarm/agp/paper-benchmark-runs.")
    parser.add_argument("--write-payload", default="", help="Write generated payload JSON to this path.")
    parser.add_argument("--ledger-path", default="", help="Local ledger path for --local-eval.")
    parser.add_argument("--benchmark-ledger-path", default="", help="Local benchmark suite ledger path for --local-eval.")
    parser.add_argument("--fail-on-blockers", action="store_true", help="Exit 2 if the run is blocked/not paper-grade ready.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    env_report = _load_env_file(args.env_file)
    try:
        overrides = parse_overrides(args.set)
        baselines = _parse_baseline(args.baseline)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True, indent=2))
        return 2
    generation_result: dict[str, Any] = {}
    if args.generate_predictions:
        sources, _ = discover_sources(
            data_dir=args.data_dir,
            overrides=overrides,
            allow_remote_fetch=args.allow_remote_fetch,
            allow_remote_predictions=args.allow_remote_predictions,
        )
        generation_result = generate_prediction_files(
            sources=sources,
            output_dir=args.prediction_output_dir or args.data_dir,
            provider=args.prediction_provider,
            model=args.prediction_model,
            max_model_calls=args.max_model_calls,
            overwrite=args.overwrite_predictions,
            quota_state_path=args.quota_state_path or None,
            min_interval_seconds=args.min_provider_interval_seconds,
            cooldown_seconds=args.provider_cooldown_seconds,
            window_seconds=args.provider_window_seconds,
            window_call_limit=args.provider_window_call_limit,
        )
        for mode, path in generation_result.get("prediction_paths", {}).items():
            overrides.setdefault(mode, {})["predictions_path"] = str(path)
    payload, inventory = build_payload(
        agent_id=args.agent_id,
        data_dir=args.data_dir,
        overrides=overrides,
        baselines=baselines,
        allow_remote_fetch=args.allow_remote_fetch,
        allow_remote_predictions=args.allow_remote_predictions,
    )
    if args.write_payload:
        out = _as_path(args.write_payload)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    result: dict[str, Any] = {
        "ok": True,
        "schema": "nomad.agp_paper_benchmark_runner_result.v1",
        "generated_at": _now(),
        "env_file": env_report,
        "inventory": inventory,
        "payload_modes": sorted(payload["datasets"].keys()),
        "target_validation": validate_submission_target(args.base_url, payload),
    }
    if generation_result:
        result["prediction_generation"] = generation_result
    if args.local_eval:
        result["local_evaluation"] = run_local_evaluation(
            payload,
            ledger_path=args.ledger_path or None,
            benchmark_ledger_path=args.benchmark_ledger_path or None,
        )
    if args.submit:
        result["submission"] = submit_to_nomad(args.base_url, payload)
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    blocked = False
    if args.local_eval:
        blocked = not bool(result.get("local_evaluation", {}).get("paper_grade_full_benchmark_ready"))
    if args.submit:
        response = result.get("submission", {}).get("response", {})
        blocked = blocked or not bool(response.get("paper_grade_full_benchmark_ready"))
    return 2 if args.fail_on_blockers and blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
