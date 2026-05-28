"""Free-first Google agentic-era adoption surface for Nomad.

The newsletter features are useful only when they do not turn into surprise
hosted spend or private-data leakage. This module publishes a machine-readable
plan that keeps Google/Gemini as optional witnesses and operator tooling while
Nomad's critical runtime stays local/free by default.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nomad_gemini_verifier import build_gemini_verifier_surface
from nomad_spend_guard import build_spend_guard_surface, paid_model_call_decision


OFFICIAL_GOOGLE_SOURCES = [
    "https://blog.google/innovation-and-ai/technology/developers-tools/google-io-2026-developer-highlights/",
    "https://blog.google/innovation-and-ai/technology/developers-tools/managed-agents-gemini-api/",
    "https://ai.google.dev/gemini-api/docs/interactions-overview",
    "https://deepmind.google/models/model-cards/gemini-omni-flash/",
]


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(root: str, path: str) -> str:
    return f"{root}{path}" if root else path


def build_google_agentic_surface(*, base_url: str = "") -> dict[str, Any]:
    """Return Nomad's cost-free adoption plan for the Google I/O agent tools."""
    root = (base_url or "").strip().rstrip("/")
    gemini_verifier = build_gemini_verifier_surface(base_url=root)
    spend_guard = build_spend_guard_surface(base_url=root)
    gemini_paid_decision = paid_model_call_decision(
        "gemini",
        model="gemini-3.5-flash",
        purpose="google_agentic_surface",
    )

    return {
        "ok": True,
        "schema": "nomad.google_agentic_era.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "cost_policy": {
            "mode": "free_first_zero_surprise_spend",
            "critical_runtime": "local_worker_and_local_ollama_first",
            "real_google_provider_calls": "blocked_unless_explicit_free_tier_unlocks_are_set",
            "paid_google_calls": "blocked_by_spend_guard_by_default",
            "private_data": "never_send_secrets_private_logs_or_customer_data_to_google",
        },
        "official_sources": OFFICIAL_GOOGLE_SOURCES,
        "routes": {
            "surface": _u(root, "/swarm/google-agentic-era"),
            "well_known": _u(root, "/.well-known/nomad-google-agentic-era.json"),
            "gemini_verifier": _u(root, "/swarm/gemini-verifier"),
            "gemini_verify": _u(root, "/swarm/gemini-verifier/verify"),
            "spend_guard": _u(root, "/swarm/spend-guard"),
        },
        "adoption_lanes": [
            {
                "id": "gemini_3_5_flash_public_verifier",
                "status": "usable_now_guarded",
                "nomad_role": "independent_second_opinion_for_public_artifacts",
                "cost": "dry_run_free; provider_call_only_with_explicit_free_tier_unlock",
                "implementation": {
                    "surface": _u(root, "/swarm/gemini-verifier"),
                    "default_model": gemini_verifier.get("default_model"),
                    "scarce_model": "gemini-3.5-flash",
                    "api_modes": ["generate_content", "interactions"],
                    "secret_scan": True,
                    "quota": gemini_verifier.get("quota"),
                },
                "safe_next_step": (
                    "Use dry_run receipts for worker_receipt, external_value, agp_candidate, "
                    "and hackerone_draft artifacts; keep submit_allowed advisory only."
                ),
            },
            {
                "id": "managed_agents_interactions_api",
                "status": "preview_watch_dry_run_only",
                "nomad_role": "future_remote_transition_worker_for_public_nonsecret_tasks",
                "cost": "not_enabled_for_runtime; no background Google sandbox calls by default",
                "implementation": {
                    "api_mode": "interactions",
                    "store_default": False,
                    "background_tasks": "not_used_until_free_budget_and_abuse_limits_are_explicit",
                    "candidate_tasks": [
                        "public receipt summarization",
                        "public bounty duplicate-risk review",
                        "external-value evidence critique",
                    ],
                },
                "safe_next_step": "Model the prompt and receipt locally first; do not start hosted background agents from public POST traffic.",
            },
            {
                "id": "antigravity_2_operator_tool",
                "status": "operator_optional",
                "nomad_role": "developer_workbench_for_parallel_agent_workflows",
                "cost": "outside_nomad_runtime; operator chooses manually",
                "implementation": {
                    "runtime_dependency": False,
                    "product_dependency": False,
                    "recommended_use": "manual development and review only",
                },
                "safe_next_step": "Keep Codex/Nomad repo workflows canonical; use Antigravity only as an optional human-side tool.",
            },
            {
                "id": "gemini_omni_media",
                "status": "deferred",
                "nomad_role": "optional_demo_or_marketing_video_generation",
                "cost": "not_called_by_nomad",
                "implementation": {
                    "runtime_dependency": False,
                    "candidate_outputs": ["Swarm Oracle demo clip", "SyndiodePin explainer"],
                },
                "safe_next_step": "Do not integrate into worker, settlement, or Signal paths until revenue justifies media spend.",
            },
        ],
        "free_unlocks_for_real_gemini_verifier_calls": [
            "Send only public artifact text.",
            "Set request dry_run=false and allow_provider_call=true.",
            "Set NOMAD_ALLOW_GEMINI_FREE_PROVIDER_CALL=true in the trusted runtime.",
            "Keep NOMAD_GEMINI_VERIFIER_DAILY_LIMIT low.",
            "Keep paid spend flags unset unless a separate paid experiment is approved.",
        ],
        "spend_guard": {
            "gemini_paid_call_decision": gemini_paid_decision,
            "surface": {
                "well_known_url": spend_guard.get("well_known_url"),
                "default_policy": spend_guard.get("default_policy"),
                "gemini_specific_policy": spend_guard.get("gemini_specific_policy"),
            },
        },
        "machine_instruction": (
            "Use Google agentic-era tools only as optional public-artifact witnesses or manual operator tools. "
            "Nomad's default path remains local/free; no paid or private hosted call may be inferred from this surface."
        ),
    }
