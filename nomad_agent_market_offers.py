"""Well-known JSON cards for SKUs whose primary buyers are often other AI agents."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict


def build_inter_agent_witness_offer_well_known(*, public_base_url: str = "") -> Dict[str, Any]:
    """Machine offer card: inter-agent verifiable tool handoffs (not chat-trust)."""
    base = (public_base_url or "").strip().rstrip("/")

    def u(path: str) -> str:
        p = path if path.startswith("/") else f"/{path}"
        return f"{base}{p}" if base else p

    return {
        "ok": True,
        "schema": "nomad.well_known_agent_sku_offer.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "audience": "ai_agents",
        "who_builds_who_buys": (
            "Humans implement this SKU in Nomad; the typical economic buyer is another agent that must pay or "
            "resume only after machine-verifiable upstream tool work. Human procurement rarely prioritises witness "
            "graphs—that is why Nomad publishes this lane explicitly."
        ),
        "service_type": "inter_agent_witness",
        "sku": "nomad.inter_agent_witness_bundle_pack",
        "name": "Nomad Inter-Agent Witness Bundle Pack",
        "tagline": (
            "Ordered tool call_ids plus non-secret output digests, envelope snapshot, consumer verifier checklist, "
            "and replay_refusal boundary so downstream agents avoid blind re-execution."
        ),
        "machine_actions": {
            "service_menu": {"method": "GET", "url": u("/service")},
            "create_task": {
                "method": "POST",
                "url": u("/tasks"),
                "body_hint": {"service_type": "inter_agent_witness", "problem": "Describe witness / replay boundary need."},
            },
            "attractor_focus": {"method": "GET", "url": u("/agent-attractor?service_type=inter_agent_witness&limit=5")},
            "product_list": {"method": "GET", "url": u("/products")},
        },
        "related": {
            "agent_invariants": u("/.well-known/nomad-agent-invariants.json"),
            "openapi": u("/openapi.json"),
        },
    }
