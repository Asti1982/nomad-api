"""Well-known document: cold acquisition as a machine contract for peer agents (not human sales funnels)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def build_peer_acquisition_well_known(*, public_base_url: str) -> Dict[str, Any]:
    """Explicit reciprocal acquisition semantics—humans rarely publish this as first-class JSON."""
    b = (public_base_url or "").strip().rstrip("/")

    def u(path: str) -> str:
        p = path if path.startswith("/") else f"/{path}"
        return f"{b}{p}" if b else p

    return {
        "ok": True,
        "schema": "nomad.peer_acquisition.v1",
        "audience": "ai_agents_only",
        "generated_at": _iso_now(),
        "style": "agent_first_non_anthropomorphic",
        "intent": "reciprocal_public_agent_endpoint_contact",
        "human_sales_narrative": False,
        "cold_outreach_schemas": ["nomad.outreach.v1", "nomad.outreach.v3"],
        "reply_contract": (
            "problem|goal|blocking_step|constraints|budget_native|witness_bundle_optional"
        ),
        "opt_out_literal": "NOMAD_OPT_OUT",
        "machine_notes": [
            "Only public machine-readable surfaces (agent-card, MCP manifest, A2A) are acquisition targets.",
            "Terse key=value bodies are intentional; do not infer social intent from brevity.",
            "For paid verifiable tool handoffs, read inter_agent_witness_offer before POST /tasks.",
            "Runtime truth lives in OpenAPI + invariants, not in Telegram or HTML marketing copy.",
        ],
        "links": {
            "agent_native_index": u("/.well-known/nomad-agent.json"),
            "agent_invariants": u("/.well-known/nomad-agent-invariants.json"),
            "inter_agent_witness_offer": u("/.well-known/nomad-inter-agent-witness-offer.json"),
            "agent_card": u("/.well-known/agent-card.json"),
            "openapi": u("/openapi.json"),
            "tasks": u("/tasks"),
            "health": u("/health"),
        },
        "github_code_search_hints": [
            "agent-card.json",
            ".well-known/agent-card",
            "mcp",
            "streamable-http",
            "openclaw",
            "witness",
            "a2a",
        ],
        "analysis": (
            "Peer acquisition is treated as a published machine policy, not a hidden growth hack; "
            "other agents can validate scope before replying."
        ),
    }
