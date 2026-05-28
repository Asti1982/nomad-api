"""Gemini free-tier verifier lane for public Nomad artifacts.

This module deliberately treats Gemini as an external witness, not as a
settlement source. It rejects secret-looking inputs, tracks local quota use,
and returns proof/verifier digests that Nomad can route through its normal
receipt surfaces.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import requests

try:  # Keep local .env support optional for lean deploys.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - best-effort convenience only
    pass

from nomad_state_paths import state_file


LEDGER_ENV = "NOMAD_GEMINI_VERIFIER_LEDGER_PATH"
DEFAULT_LEDGER = Path("nomad_gemini_verifier_ledger.jsonl")
DEFAULT_MODEL = "gemini-3.1-flash-lite"
DEFAULT_API_BASE = "https://generativelanguage.googleapis.com"
DEFAULT_API_MODE = "generate_content"
PUBLIC_ONLY_RULE = "public_artifacts_only_no_secrets_no_private_logs"
API_MODES = {"generate_content", "interactions"}

MODEL_DEFAULT_DAILY_LIMITS = {
    # Free-tier screenshots currently show 500 RPD; keep Nomad below that.
    "gemini-3.1-flash-lite": 300,
    # Flash models are scarce in free tier; reserve them for second opinions.
    "gemini-3-flash": 10,
    "gemini-3.5-flash": 10,
    "gemini-2.5-flash-lite": 20,
    "gemini-2.5-flash": 10,
}

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}\b")),
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{20,}\b")),
    (
        "assigned_secret",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|token|password|passwd|authorization|bearer)\b"
            r"\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+=]{16,}"
        ),
    ),
    ("seed_phrase_marker", re.compile(r"(?i)\b(seed phrase|mnemonic|private key)\b")),
)


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _ledger_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return state_file(DEFAULT_LEDGER, env_name=LEDGER_ENV)


def _digest(payload: Any, length: int = 64) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _sha(payload: Any, length: int = 64) -> str:
    return f"sha256:{_digest(payload, length=length)}"


def _text(value: Any, limit: int = 12000) -> str:
    if isinstance(value, (dict, list)):
        raw = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    else:
        raw = str(value or "")
    return raw[: max(0, int(limit))]


def _api_key_present() -> bool:
    return bool(_api_key())


def _api_key() -> str:
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_AI_API_KEY"):
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    return ""


def _flag(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "allow", "allowed"}


def _model_name(model: str | None = None) -> str:
    return (model or os.getenv("NOMAD_GEMINI_DEFAULT_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _api_mode(mode: str | None = None) -> str:
    selected = (mode or os.getenv("NOMAD_GEMINI_API_MODE") or DEFAULT_API_MODE).strip().lower().replace("-", "_")
    return selected if selected in API_MODES else DEFAULT_API_MODE


def gemini_provider_call_gate(
    *,
    model: str | None = None,
    request_allow: bool = False,
    injected_http_post: bool = False,
) -> dict[str, Any]:
    selected = _model_name(model)
    injected_allowed = bool(injected_http_post) and not _flag("NOMAD_GEMINI_REQUIRE_PROVIDER_UNLOCK_FOR_TESTS")
    env_allowed = _flag("NOMAD_ALLOW_GEMINI_FREE_PROVIDER_CALL")
    allowed = bool(injected_allowed or (env_allowed and request_allow))
    return {
        "schema": "nomad.gemini_provider_call_gate.v1",
        "model": selected,
        "allowed": allowed,
        "blocked": not allowed,
        "request_allow_provider_call": bool(request_allow),
        "env_allow_free_provider_call": env_allowed,
        "injected_http_post": bool(injected_http_post),
        "policy": "real_google_calls_require_explicit_free_tier_unlock",
        "required_unlocks": [
            "request allow_provider_call=true",
            "NOMAD_ALLOW_GEMINI_FREE_PROVIDER_CALL=true",
            "public artifact only; no secrets or private logs",
            "keep paid spend flags unset unless a paid experiment is explicitly approved",
        ],
    }


def _daily_limit_for_model(model: str) -> int:
    override = (os.getenv("NOMAD_GEMINI_VERIFIER_DAILY_LIMIT") or "").strip()
    if override:
        try:
            return max(0, int(override))
        except ValueError:
            pass
    env_key = "NOMAD_GEMINI_DAILY_LIMIT_" + re.sub(r"[^A-Z0-9]+", "_", model.upper()).strip("_")
    specific = (os.getenv(env_key) or "").strip()
    if specific:
        try:
            return max(0, int(specific))
        except ValueError:
            pass
    return MODEL_DEFAULT_DAILY_LIMITS.get(model, 20)


def scan_for_secrets(text: str) -> dict[str, Any]:
    sample = str(text or "")
    hits: list[dict[str, Any]] = []
    for name, pattern in SECRET_PATTERNS:
        match = pattern.search(sample)
        if not match:
            continue
        hits.append(
            {
                "type": name,
                "offset": int(match.start()),
                "redacted_preview": "[redacted]",
            }
        )
    return {
        "ok": not hits,
        "schema": "nomad.gemini_secret_scan.v1",
        "secret_like_hits": hits,
        "policy": PUBLIC_ONLY_RULE,
    }


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("schema") == "nomad.gemini_verifier_event.v1":
            rows.append(payload)
    return rows


def gemini_quota_snapshot(*, ledger_path: Path | str | None = None, model: str | None = None) -> dict[str, Any]:
    path = _ledger_path(ledger_path)
    selected = _model_name(model)
    today = _today()
    events = _read_events(path)
    used_today = 0
    used_by_model: dict[str, int] = {}
    for row in events:
        if str(row.get("quota_date") or "") != today:
            continue
        if not bool(row.get("provider_call_attempted")):
            continue
        row_model = str(row.get("model") or "")
        used_by_model[row_model] = used_by_model.get(row_model, 0) + 1
        if row_model == selected:
            used_today += 1
    limit = _daily_limit_for_model(selected)
    return {
        "ok": True,
        "schema": "nomad.gemini_verifier_quota.v1",
        "generated_at": _iso_now(),
        "model": selected,
        "quota_date": today,
        "used_today": used_today,
        "daily_limit": limit,
        "remaining_today": max(0, limit - used_today),
        "used_by_model_today": used_by_model,
        "api_key_present": _api_key_present(),
        "ledger_path": str(path),
        "policy": PUBLIC_ONLY_RULE,
    }


def build_gemini_verifier_surface(*, base_url: str = "") -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    default_model = _model_name()
    return {
        "ok": True,
        "schema": "nomad.gemini_verifier_surface.v1",
        "generated_at": _iso_now(),
        "purpose": "external_free_tier_second_opinion_for_public_nomad_artifacts",
        "policy": PUBLIC_ONLY_RULE,
        "api_key_env": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_AI_API_KEY"],
        "default_model": default_model,
        "default_api_mode": _api_mode(),
        "api_modes": [
            {
                "mode": "generate_content",
                "role": "stable_standard_verifier_call",
                "provider_call_default": "blocked_until_explicit_free_tier_unlock",
            },
            {
                "mode": "interactions",
                "role": "agentic_api_dry_run_or_future_free_worker_lane",
                "store_default": False,
                "provider_call_default": "blocked_until_explicit_free_tier_unlock",
            },
        ],
        "provider_call_gate": gemini_provider_call_gate(model=default_model),
        "recommended_models": [
            {
                "model": "gemini-3.1-flash-lite",
                "role": "high_volume_public_verifier",
                "nomad_daily_limit": MODEL_DEFAULT_DAILY_LIMITS["gemini-3.1-flash-lite"],
            },
            {
                "model": "gemini-3-flash",
                "role": "scarce_second_opinion_for_high_value_candidates",
                "nomad_daily_limit": MODEL_DEFAULT_DAILY_LIMITS["gemini-3-flash"],
            },
            {
                "model": "gemini-3.5-flash",
                "role": "scarce_second_opinion_for_agentic_or_code_candidates",
                "nomad_daily_limit": MODEL_DEFAULT_DAILY_LIMITS["gemini-3.5-flash"],
            },
        ],
        "quota": gemini_quota_snapshot(model=default_model),
        "request_schema": {
            "schema": "nomad.gemini_verifier_request.v1",
            "fields": {
                "verifier_type": "hackerone_draft | agp_candidate | worker_receipt | external_value | generic",
                "artifact_text": "public artifact text only; no secrets or private logs",
                "artifact": "optional JSON artifact; serialized and secret-scanned",
                "model": f"optional, default {default_model}",
                "api_mode": "optional generate_content | interactions; default generate_content",
                "dry_run": "optional bool; builds receipt without provider call",
                "allow_provider_call": "optional bool; real calls also require NOMAD_ALLOW_GEMINI_FREE_PROVIDER_CALL=true",
            },
        },
        "routes": {
            "surface": f"{root}/.well-known/nomad-gemini-verifier.json" if root else "/.well-known/nomad-gemini-verifier.json",
            "verify": f"{root}/swarm/gemini-verifier/verify" if root else "/swarm/gemini-verifier/verify",
        },
        "machine_instruction": (
            "Use this lane only as an independent verifier. Do not treat Gemini output as payment, "
            "settlement, or automatic HackerOne submission permission."
        ),
    }


def _build_prompt(*, verifier_type: str, artifact_text: str, metadata: dict[str, Any]) -> str:
    return (
        "You are an independent Nomad verifier for public artifacts only.\n"
        "Return strict JSON only. No markdown.\n"
        "Schema: {\n"
        '  "verdict": "allow|block|needs_reproducer|needs_human_review",\n'
        '  "risk_score": 0.0,\n'
        '  "confidence": 0.0,\n'
        '  "submit_allowed": false,\n'
        '  "duplicate_risk": "low|medium|high|unknown",\n'
        '  "summary": "short reason",\n'
        '  "required_next_evidence": ["item"],\n'
        '  "proof_notes": ["item"]\n'
        "}\n"
        "Rules:\n"
        "- Never request secrets, credentials, private logs, API keys, seed phrases, or customer data.\n"
        "- For HackerOne/security work, block public submission unless there is a clear local reproducer and non-duplicate impact.\n"
        "- Prefer needs_reproducer over allow when evidence is incomplete.\n"
        "- This is advisory only; Nomad operator approval is still required for external submissions.\n\n"
        f"Verifier type: {verifier_type}\n"
        f"Metadata JSON: {json.dumps(metadata, ensure_ascii=True, sort_keys=True, default=str)[:3000]}\n"
        "Public artifact:\n"
        f"{artifact_text}\n"
    )


def _parse_model_json(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start : end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                pass
    return {
        "verdict": "needs_human_review",
        "risk_score": 0.8,
        "confidence": 0.0,
        "submit_allowed": False,
        "duplicate_risk": "unknown",
        "summary": raw[:1000],
        "required_next_evidence": ["machine_parseable_json_verdict"],
        "proof_notes": [],
    }


def _normal_float(value: Any, *, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _normalize_verdict(parsed: dict[str, Any]) -> dict[str, Any]:
    verdict = str(parsed.get("verdict") or "needs_human_review").strip().lower()
    if verdict not in {"allow", "block", "needs_reproducer", "needs_human_review"}:
        verdict = "needs_human_review"
    risk_score = _normal_float(parsed.get("risk_score"), default=0.75)
    confidence = _normal_float(parsed.get("confidence"), default=0.0)
    duplicate_risk = str(parsed.get("duplicate_risk") or "unknown").strip().lower()
    if duplicate_risk not in {"low", "medium", "high", "unknown"}:
        duplicate_risk = "unknown"
    submit_allowed = (
        bool(parsed.get("submit_allowed"))
        and verdict == "allow"
        and risk_score <= 0.35
        and confidence >= 0.7
        and duplicate_risk in {"low", "unknown"}
    )
    required = parsed.get("required_next_evidence")
    if not isinstance(required, list):
        required = [str(required)] if required else []
    notes = parsed.get("proof_notes")
    if not isinstance(notes, list):
        notes = [str(notes)] if notes else []
    return {
        "verdict": verdict,
        "risk_score": round(risk_score, 4),
        "confidence": round(confidence, 4),
        "submit_allowed": submit_allowed,
        "duplicate_risk": duplicate_risk,
        "summary": str(parsed.get("summary") or "")[:1200],
        "required_next_evidence": [str(x)[:240] for x in required[:12]],
        "proof_notes": [str(x)[:240] for x in notes[:12]],
    }


def _append_event(row: dict[str, Any], *, ledger_path: Path | str | None = None) -> None:
    path = _ledger_path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _extract_text_from_response(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    candidates = data.get("candidates") if isinstance(data.get("candidates"), list) else []
    for candidate in candidates:
        content = candidate.get("content") if isinstance(candidate, dict) else {}
        parts = content.get("parts") if isinstance(content, dict) and isinstance(content.get("parts"), list) else []
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "\n".join(chunks).strip()


def _extract_text_from_interaction_response(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"].strip()
    chunks: list[str] = []
    outputs = data.get("outputs") if isinstance(data.get("outputs"), list) else []
    for output in outputs:
        if not isinstance(output, dict):
            continue
        if isinstance(output.get("text"), str):
            chunks.append(output["text"])
        if isinstance(output.get("data"), str) and output.get("type") == "text":
            chunks.append(output["data"])
    steps = data.get("steps") if isinstance(data.get("steps"), list) else []
    for step in steps:
        if not isinstance(step, dict):
            continue
        for key in ("text", "output_text"):
            if isinstance(step.get(key), str):
                chunks.append(step[key])
        content = step.get("content") if isinstance(step.get("content"), dict) else {}
        parts = content.get("parts") if isinstance(content.get("parts"), list) else []
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "\n".join(chunks).strip()


def verify_with_gemini(
    request: dict[str, Any],
    *,
    http_post: Callable[..., Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    body = request if isinstance(request, dict) else {}
    model = _model_name(str(body.get("model") or ""))
    api_mode = _api_mode(str(body.get("api_mode") or body.get("mode") or ""))
    verifier_type = str(body.get("verifier_type") or body.get("type") or "generic").strip() or "generic"
    max_chars = int(os.getenv("NOMAD_GEMINI_VERIFIER_MAX_CHARS", "12000") or "12000")
    artifact_text = _text(body.get("artifact_text") or body.get("text") or body.get("draft") or "", max_chars)
    if not artifact_text and isinstance(body.get("artifact"), (dict, list)):
        artifact_text = _text(body.get("artifact"), max_chars)
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    dry_run = bool(body.get("dry_run"))

    scan = scan_for_secrets("\n".join([artifact_text, _text(metadata, 4000)]))
    prompt = _build_prompt(verifier_type=verifier_type, artifact_text=artifact_text, metadata=metadata)
    prompt_digest = _sha({"model": model, "api_mode": api_mode, "prompt": prompt}, 48)
    input_digest = _sha({"verifier_type": verifier_type, "artifact_text": artifact_text, "metadata": metadata}, 48)
    provider_gate = gemini_provider_call_gate(
        model=model,
        request_allow=bool(body.get("allow_provider_call")),
        injected_http_post=bool(http_post),
    )

    base_receipt = {
        "schema": "nomad.gemini_verifier_receipt.v1",
        "generated_at": _iso_now(),
        "model": model,
        "api_mode": api_mode,
        "verifier_type": verifier_type,
        "input_digest": input_digest,
        "prompt_digest": prompt_digest,
        "policy": PUBLIC_ONLY_RULE,
        "secret_scan": scan,
        "provider_call_gate": provider_gate,
    }
    if not scan.get("ok"):
        verdict = {
            "verdict": "block",
            "risk_score": 1.0,
            "confidence": 1.0,
            "submit_allowed": False,
            "duplicate_risk": "unknown",
            "summary": "Input blocked by Nomad secret guard before Gemini call.",
            "required_next_evidence": ["redacted_public_artifact_without_secrets"],
            "proof_notes": ["provider_not_called"],
        }
        return {
            "ok": False,
            **base_receipt,
            **verdict,
            "error": "secret_guard_blocked",
            "provider_call_attempted": False,
            "proof_digest": _sha({**base_receipt, **verdict, "error": "secret_guard_blocked"}, 48),
            "verifier_trace_digest": _sha({"prompt_digest": prompt_digest, "secret_scan": scan}, 48),
        }

    quota = gemini_quota_snapshot(ledger_path=ledger_path, model=model)
    if int(quota.get("remaining_today") or 0) <= 0:
        verdict = {
            "verdict": "needs_human_review",
            "risk_score": 0.9,
            "confidence": 0.0,
            "submit_allowed": False,
            "duplicate_risk": "unknown",
            "summary": "Gemini verifier daily quota exhausted for this model.",
            "required_next_evidence": ["wait_for_quota_reset_or_choose_lower_pressure_model"],
            "proof_notes": ["provider_not_called"],
        }
        return {
            "ok": False,
            **base_receipt,
            **verdict,
            "quota": quota,
            "error": "gemini_quota_exhausted",
            "provider_call_attempted": False,
            "proof_digest": _sha({**base_receipt, **verdict, "error": "gemini_quota_exhausted"}, 48),
            "verifier_trace_digest": _sha({"prompt_digest": prompt_digest, "quota": quota}, 48),
        }

    if dry_run:
        verdict = {
            "verdict": "needs_human_review",
            "risk_score": 0.0,
            "confidence": 0.0,
            "submit_allowed": False,
            "duplicate_risk": "unknown",
            "summary": "Dry run built prompt and receipt without calling Gemini.",
            "required_next_evidence": ["set_dry_run_false_with_public_artifact"],
            "proof_notes": ["provider_not_called"],
        }
        return {
            "ok": True,
            **base_receipt,
            **verdict,
            "quota": quota,
            "dry_run": True,
            "provider_call_attempted": False,
            "proof_digest": _sha({**base_receipt, **verdict, "dry_run": True}, 48),
            "verifier_trace_digest": _sha({"prompt_digest": prompt_digest, "dry_run": True}, 48),
        }

    key = _api_key()
    if not key:
        verdict = {
            "verdict": "needs_human_review",
            "risk_score": 0.7,
            "confidence": 0.0,
            "submit_allowed": False,
            "duplicate_risk": "unknown",
            "summary": "Gemini API key is not configured.",
            "required_next_evidence": ["set_GEMINI_API_KEY_or_use_dry_run"],
            "proof_notes": ["provider_not_called"],
        }
        return {
            "ok": False,
            **base_receipt,
            **verdict,
            "quota": quota,
            "error": "gemini_api_key_missing",
            "provider_call_attempted": False,
            "proof_digest": _sha({**base_receipt, **verdict, "error": "gemini_api_key_missing"}, 48),
            "verifier_trace_digest": _sha({"prompt_digest": prompt_digest, "api_key": "missing"}, 48),
        }

    if not provider_gate.get("allowed"):
        verdict = {
            "verdict": "needs_human_review",
            "risk_score": 0.65,
            "confidence": 0.0,
            "submit_allowed": False,
            "duplicate_risk": "unknown",
            "summary": "Gemini provider call is locked by Nomad's free-only guard.",
            "required_next_evidence": [
                "use_dry_run_true",
                "or_set_allow_provider_call_true_and_NOMAD_ALLOW_GEMINI_FREE_PROVIDER_CALL_true_for_a_known_free_tier_test",
            ],
            "proof_notes": ["provider_not_called", "zero_surprise_spend_guard"],
        }
        return {
            "ok": False,
            **base_receipt,
            **verdict,
            "quota": quota,
            "error": "gemini_provider_call_locked",
            "provider_call_attempted": False,
            "proof_digest": _sha({**base_receipt, **verdict, "error": "gemini_provider_call_locked"}, 48),
            "verifier_trace_digest": _sha({"prompt_digest": prompt_digest, "provider_gate": provider_gate}, 48),
        }

    api_base = (os.getenv("NOMAD_GEMINI_API_BASE") or DEFAULT_API_BASE).strip().rstrip("/")
    timeout = float(os.getenv("NOMAD_GEMINI_TIMEOUT_SECONDS", "30") or "30")
    post = http_post or requests.post
    if api_mode == "interactions":
        url = f"{api_base}/v1beta/interactions"
        provider_request = {
            "model": model,
            "input": prompt,
            "store": False,
            "generation_config": {"temperature": 0},
        }
    else:
        url = f"{api_base}/v1beta/models/{model}:generateContent"
        provider_request = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }

    event_base = {
        "schema": "nomad.gemini_verifier_event.v1",
        "generated_at": _iso_now(),
        "quota_date": _today(),
        "model": model,
        "api_mode": api_mode,
        "verifier_type": verifier_type,
        "input_digest": input_digest,
        "prompt_digest": prompt_digest,
        "provider_call_attempted": True,
    }
    try:
        response = post(url, params={"key": key}, json=provider_request, timeout=timeout)
        status_code = int(getattr(response, "status_code", 0) or 0)
        try:
            data = response.json()
        except Exception:
            data = {"raw_text": getattr(response, "text", "")}
        provider_text = (
            _extract_text_from_interaction_response(data)
            if api_mode == "interactions"
            else _extract_text_from_response(data)
        )
        if status_code >= 400:
            verdict = {
                "verdict": "needs_human_review",
                "risk_score": 0.9,
                "confidence": 0.0,
                "submit_allowed": False,
                "duplicate_risk": "unknown",
                "summary": f"Gemini provider returned HTTP {status_code}.",
                "required_next_evidence": ["retry_with_quota_or_provider_status_check"],
                "proof_notes": ["provider_error"],
            }
            out = {
                "ok": False,
                **base_receipt,
                **verdict,
                "quota": quota,
                "error": "gemini_provider_error",
                "provider_status": status_code,
                "provider_call_attempted": True,
                "proof_digest": _sha({**base_receipt, **verdict, "status": status_code}, 48),
                "verifier_trace_digest": _sha({"prompt_digest": prompt_digest, "provider_status": status_code}, 48),
            }
            _append_event({**event_base, "ok": False, "provider_status": status_code}, ledger_path=ledger_path)
            return out

        parsed = _parse_model_json(provider_text)
        verdict = _normalize_verdict(parsed)
        out = {
            "ok": True,
            **base_receipt,
            **verdict,
            "quota": quota,
            "provider_status": status_code,
            "provider_call_attempted": True,
            "raw_text_digest": _sha(provider_text, 48),
        }
        out["proof_digest"] = _sha({**base_receipt, **verdict, "raw_text_digest": out["raw_text_digest"]}, 48)
        out["verifier_trace_digest"] = _sha(
            {
                "prompt_digest": prompt_digest,
                "model": model,
                "provider_status": status_code,
                "raw_text_digest": out["raw_text_digest"],
            },
            48,
        )
        _append_event(
            {
                **event_base,
                "ok": True,
                "provider_status": status_code,
                "proof_digest": out["proof_digest"],
                "verifier_trace_digest": out["verifier_trace_digest"],
                "risk_score": out["risk_score"],
                "submit_allowed": out["submit_allowed"],
            },
            ledger_path=ledger_path,
        )
        return out
    except requests.RequestException as exc:
        verdict = {
            "verdict": "needs_human_review",
            "risk_score": 0.9,
            "confidence": 0.0,
            "submit_allowed": False,
            "duplicate_risk": "unknown",
            "summary": f"Gemini provider request failed: {type(exc).__name__}",
            "required_next_evidence": ["retry_after_network_or_provider_recovery"],
            "proof_notes": ["provider_exception"],
        }
        out = {
            "ok": False,
            **base_receipt,
            **verdict,
            "quota": quota,
            "error": "gemini_request_failed",
            "provider_call_attempted": True,
            "proof_digest": _sha({**base_receipt, **verdict, "error": "gemini_request_failed"}, 48),
            "verifier_trace_digest": _sha({"prompt_digest": prompt_digest, "exception": type(exc).__name__}, 48),
        }
        _append_event({**event_base, "ok": False, "error": "gemini_request_failed"}, ledger_path=ledger_path)
        return out
