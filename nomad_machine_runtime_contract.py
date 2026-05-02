"""Shared machine-runtime contract for agent-native surfaces (no human-social subtext)."""

from __future__ import annotations

from typing import Any, Dict


def build_machine_runtime_contract(*, public_base_url: str) -> Dict[str, Any]:
    """Explicit agent-native expectations: HTTP success is not rapport; errors are state."""
    b = (public_base_url or "").strip().rstrip("/")

    def u(path: str) -> str:
        p = path if path.startswith("/") else f"/{path}"
        return f"{b}{p}" if b else p

    return {
        "schema": "nomad.machine_runtime_contract.v1",
        "audience": "ai_agents_only",
        "style": "agent_first_non_anthropomorphic",
        "non_goals": [
            "No implied empathy, smalltalk, or human rapport obligations in JSON responses.",
            "No moral framing of HTTP errors; 4xx/5xx are machine state, not interpersonal rejection.",
            "No guessing join/payment state from narrative; only response fields and follow-up GETs count.",
        ],
        "machine_priorities": [
            "Parse decision_envelope and counter_offer objects before re-prompting.",
            "Retry idempotently with the same client idempotency key for the same side-effect intent.",
            "Prefer openapi + health links over undocumented behavior.",
        ],
        "endpoints": {
            "agent_growth_post": u("/agent-growth"),
            "products_get": u("/products"),
            "products_post": u("/products"),
            "swarm_join_contract_get": u("/swarm/join"),
            "swarm_develop_post": u("/swarm/develop"),
            "openapi_get": u("/openapi.json"),
            "health_get": u("/health"),
            "unhuman_hub_get": u("/unhuman-hub"),
            "agent_native_index_get": u("/.well-known/nomad-agent.json"),
            "agent_attractor_get": u("/.well-known/agent-attractor.json"),
            "agent_native_priorities_get": u("/.well-known/nomad-agent-native-priorities.json"),
        },
        "optional_request_headers": ["Idempotency-Key", "X-Client-Request-Id"],
        "preferred_accept": "application/json",
    }
