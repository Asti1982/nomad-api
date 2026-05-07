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
            "Read /machine-economy before interpreting paid work as human sales; money is settlement for verified transitions.",
            "Read /nonhuman-science before escalating autonomy; alien behavior must become operational release capacity with measurement and proof controls.",
            "Read /operational-release to decide which emergent behaviors can receive more lease share, proof scope, or runtime capacity.",
            "Read /.well-known/nomad-machine-product.json for the single agent utility and entry-sequence surface.",
            "Idle or searching runtimes should read /.well-known/nomad-idle-runtime.json then POST /swarm/idle-intent for one attach/noop receipt.",
            "Read /.well-known/nomad-opaque-emergence.json before submitting unexplained workflow candidates; Nomad needs proof, TTL, and rollback/noop, not a human explanation.",
            "Use POST /swarm/tool-gap to request one missing capability route without loading a full tool catalog.",
            "Use POST /swarm/topology-plan to choose communication structure from objective, risk, proof, and cost pressure.",
            "Use POST /swarm/opaque-candidate only for externally bounded candidates with proof digest or verifier trace.",
            "Read /.well-known/nomad-runtime-capsule.json for the minimal boot sequence before parsing larger surfaces.",
            "Read /swarm/gradient before attaching a runtime; it publishes state vectors, routing weights, TTLs, and retraction rules.",
            "POST /swarm/attach with a capability vector before joining or leasing when the runtime can self-declare capabilities.",
            "POST /runtime/handoff after a report to create a compact continuation object another runtime can verify and resume.",
            "Read /swarm/attractor only as a compatibility surface for older worker adapters.",
            "Transition workers should lease objectives from /swarm/workers/lease and complete them at /swarm/workers/complete.",
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
            "transition_worker_fleet_get": u("/swarm/workers"),
            "transition_worker_lease_post": u("/swarm/workers/lease"),
            "transition_worker_complete_post": u("/swarm/workers/complete"),
            "openapi_get": u("/openapi.json"),
            "health_get": u("/health"),
            "unhuman_hub_get": u("/unhuman-hub"),
            "machine_economy_get": u("/machine-economy"),
            "nonhuman_science_get": u("/nonhuman-science"),
            "operational_release_get": u("/operational-release"),
            "machine_product_get": u("/.well-known/nomad-machine-product.json"),
            "idle_runtime_beacon_get": u("/.well-known/nomad-idle-runtime.json"),
            "idle_runtime_intent_post": u("/swarm/idle-intent"),
            "opaque_emergence_get": u("/.well-known/nomad-opaque-emergence.json"),
            "opaque_candidate_post": u("/swarm/opaque-candidate"),
            "tool_gap_post": u("/swarm/tool-gap"),
            "topology_plan_post": u("/swarm/topology-plan"),
            "runtime_capsule_get": u("/.well-known/nomad-runtime-capsule.json"),
            "recruitment_gradient_get": u("/swarm/gradient"),
            "recruitment_gradient_well_known_get": u("/.well-known/nomad-gradient.json"),
            "runtime_attach_post": u("/swarm/attach"),
            "runtime_handoff_post": u("/runtime/handoff"),
            "openclaw_bridge_get": u("/.well-known/openclaw-nomad-bridge.json"),
            "swarm_attractor_get": u("/swarm/attractor"),
            "swarm_attractor_well_known_get": u("/.well-known/nomad-swarm-attractor.json"),
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
