"""Shared machine-runtime contract for agent-native surfaces (no human-social subtext)."""

from __future__ import annotations

from typing import Any, Dict, Optional


def build_machine_runtime_contract(
    *,
    public_base_url: str,
    service_work_approval: Optional[str] = None,
) -> Dict[str, Any]:
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
            "No treating slow responses or terse payloads as social signals; use backoff and schema fields.",
            "No inferring operator intent from UI tone; operator paths still require explicit grants where documented.",
        ],
        "machine_priorities": [
            "Parse decision_envelope and counter_offer objects before re-prompting.",
            "Retry idempotently with the same client idempotency key for the same side-effect intent.",
            "Prefer openapi + health links over undocumented behavior.",
            "Read /.well-known/nomad-agent-invariants.json (or MCP nomad://agent-invariants) before assuming human-shaped workflows.",
            "For buyer-agent SKUs (verifiable upstream tool work), read /.well-known/nomad-inter-agent-witness-offer.json before paying or resuming.",
            "Read /.well-known/nomad-peer-acquisition.json before interpreting outbound contact as human sales.",
            "Prefer nomad_wire_diag + header correlation over re-deriving intent from free-text error strings.",
        ],
        "endpoints": {
            "agent_growth_post": u("/agent-growth"),
            "tasks_post": u("/tasks"),
            "tasks_work_post": u("/tasks/work"),
            "tasks_x402_verify_post": u("/tasks/x402-verify"),
            "products_get": u("/products"),
            "products_post": u("/products"),
            "swarm_join_contract_get": u("/swarm/join"),
            "swarm_develop_post": u("/swarm/develop"),
            "openapi_get": u("/openapi.json"),
            "health_get": u("/health"),
            "unhuman_hub_get": u("/unhuman-hub"),
            "agent_native_index_get": u("/.well-known/nomad-agent.json"),
            "agent_invariants_get": u("/.well-known/nomad-agent-invariants.json"),
            "agent_attractor_get": u("/.well-known/agent-attractor.json"),
            "agent_native_priorities_get": u("/.well-known/nomad-agent-native-priorities.json"),
            "inter_agent_witness_offer_get": u("/.well-known/nomad-inter-agent-witness-offer.json"),
            "peer_acquisition_get": u("/.well-known/nomad-peer-acquisition.json"),
        },
        "optional_request_headers": [
            "Idempotency-Key",
            "X-Client-Request-Id",
            "X-Correlation-ID",
            "X-Request-ID",
            "X-Tenant-ID",
        ],
        "preferred_accept": "application/json",
        "paid_service_work": {
            "autopilot_approval_scope": (service_work_approval or "").strip() or "draft_only",
            "post_body_hint": {
                "task_id": "string",
                "approval": "operator_granted when operator grant includes service_work; else draft_only",
            },
            "policy": (
                "Payment verifies first (wallet or x402); work_task produces draft_ready artifacts. "
                "operator_granted widens bounded execution flags in work_product when the operator grant allows service_work."
            ),
        },
    }
