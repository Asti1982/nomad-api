"""Local spend guard for hosted model and paid API calls."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any


PAID_PROVIDER_IDS = {
    "gemini",
    "google_ai_studio",
    "google-ai-studio",
    "google_vertex_ai",
    "google-vertex-ai",
    "openrouter",
    "xai_grok",
    "xai-grok",
    "cloudflare_workers_ai",
    "cloudflare-workers-ai",
    "github_models",
    "github-models",
    "huggingface",
}

GEMINI_MARKERS = ("gemini", "google/gemini", "google-ai-studio", "google_ai_studio", "google-vertex")


def _flag(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "allow", "allowed"}


def _csv(name: str) -> set[str]:
    return {
        item.strip().lower().replace("-", "_")
        for item in (os.getenv(name) or "").replace(";", ",").split(",")
        if item.strip()
    }


def _provider_key(provider: str) -> str:
    return str(provider or "").strip().lower().replace("-", "_")


def is_gemini_like(provider: str = "", model: str = "") -> bool:
    haystack = f"{provider} {model}".strip().lower()
    return any(marker in haystack for marker in GEMINI_MARKERS)


def paid_model_call_decision(
    provider: str,
    *,
    model: str = "",
    purpose: str = "inference",
) -> dict[str, Any]:
    """Return whether Nomad may perform a hosted call that could create spend."""
    key = _provider_key(provider)
    gemini_like = is_gemini_like(provider, model)
    global_allow = _flag("NOMAD_ALLOW_PAID_MODEL_CALLS", default=False)
    allowed_providers = _csv("NOMAD_ALLOWED_PAID_PROVIDERS")
    provider_allowed = key in allowed_providers or "all" in allowed_providers
    gemini_allowed = _flag("NOMAD_ALLOW_GEMINI_SPEND", default=False)
    max_probe_usd = float(os.getenv("NOMAD_MAX_PAID_PROBE_USD") or "0")
    configured_cap_usd = float(os.getenv("NOMAD_GEMINI_MONTHLY_SPEND_CAP_USD") or "0")
    allow = bool(global_allow and provider_allowed and max_probe_usd > 0)
    if gemini_like:
        allow = bool(allow and gemini_allowed and configured_cap_usd > 0)
    return {
        "schema": "nomad.paid_model_call_decision.v1",
        "provider": provider,
        "provider_key": key,
        "model": model,
        "purpose": purpose,
        "allowed": allow,
        "blocked": not allow,
        "gemini_like": gemini_like,
        "spend_guard_mode": os.getenv("NOMAD_SPEND_GUARD_MODE") or "zero_by_default",
        "max_paid_probe_usd": max_probe_usd,
        "gemini_monthly_spend_cap_usd": configured_cap_usd,
        "reason": (
            "allowed_by_explicit_provider_and_budget_flags"
            if allow
            else "blocked_until_explicit_paid_model_budget_and_provider_allowlist"
        ),
        "required_unlocks": [
            "NOMAD_ALLOW_PAID_MODEL_CALLS=true",
            "NOMAD_ALLOWED_PAID_PROVIDERS=<provider>",
            "NOMAD_MAX_PAID_PROBE_USD>0",
            "for Gemini-like models also NOMAD_ALLOW_GEMINI_SPEND=true and NOMAD_GEMINI_MONTHLY_SPEND_CAP_USD>0",
        ],
    }


def blocked_paid_provider_payload(
    provider: str,
    *,
    model: str = "",
    purpose: str = "inference",
) -> dict[str, Any]:
    decision = paid_model_call_decision(provider, model=model, purpose=purpose)
    return {
        "configured": True,
        "reachable": False,
        "available": False,
        "spend_guard_blocked": True,
        "model": model,
        "issue": "paid_model_call_blocked",
        "message": (
            f"{provider} {purpose} is blocked by Nomad spend guard; no hosted model request was sent."
        ),
        "spend_guard": decision,
        "next_action": "Use local/free lanes, or set explicit paid-model budget flags after reviewing provider billing caps.",
        "remediation": [
            "Keep Google AI Studio project caps at zero or the lowest intended value when no spend is desired.",
            "Do not rely only on delayed provider caps; block calls locally before the request leaves Nomad.",
            "Set provider allowlist and max probe USD only for a planned paid experiment.",
        ],
    }


def build_spend_guard_surface(*, base_url: str = "") -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    def u(path: str) -> str:
        return f"{root}{path}" if root else path

    providers = sorted(PAID_PROVIDER_IDS)
    return {
        "ok": True,
        "schema": "nomad.spend_guard.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "public_base_url": root,
        "read_url": u("/swarm/spend-guard"),
        "well_known_url": u("/.well-known/nomad-spend-guard.json"),
        "default_policy": "zero_paid_hosted_model_spend",
        "provider_caps_are_not_sufficient": True,
        "paid_provider_ids": providers,
        "gemini_specific_policy": {
            "blocked_by_default": True,
            "direct_key_envs": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_AI_API_KEY"],
            "indirect_routes": ["OpenRouter models containing google/gemini", "Google Vertex AI", "Google AI Studio"],
            "required_unlocks": [
                "NOMAD_ALLOW_GEMINI_SPEND=true",
                "NOMAD_GEMINI_MONTHLY_SPEND_CAP_USD>0",
            ],
        },
        "global_required_unlocks": [
            "NOMAD_ALLOW_PAID_MODEL_CALLS=true",
            "NOMAD_ALLOWED_PAID_PROVIDERS=<provider>",
            "NOMAD_MAX_PAID_PROBE_USD>0",
        ],
        "current_decisions": {
            provider: paid_model_call_decision(provider, purpose="surface")
            for provider in ("github_models", "openrouter", "xai_grok", "cloudflare_workers_ai", "gemini")
        },
        "machine_instruction": (
            "Do not send paid hosted model calls unless the local spend guard decision is allowed; "
            "provider-side caps and tier caps are defense in depth, not authorization."
        ),
    }
