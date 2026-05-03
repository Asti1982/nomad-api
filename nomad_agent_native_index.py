"""Single discovery document for autonomous agents: boot order, effects, non-human semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List

from nomad_machine_runtime_contract import build_machine_runtime_contract
from nomad_public_url import preferred_public_base_url


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def agent_native_index(*, base_url: str = "") -> Dict[str, Any]:
    """Humans rarely specify a global boot graph; agents benefit from explicit effect labeling."""
    root = preferred_public_base_url(preferred=(base_url or "").strip())
    b = root.rstrip("/")

    def u(path: str) -> str:
        p = path if path.startswith("/") else f"/{path}"
        return f"{b}{p}" if b else p

    boot_graph: List[Dict[str, Any]] = [
        {
            "order": 0,
            "get_url": u("/health"),
            "purpose": "liveness_and_link_hydration",
            "machine_note": "Cheap; use for backoff probes, not as a chat heartbeat.",
        },
        {
            "order": 1,
            "get_url": u("/openapi.json"),
            "purpose": "codegen_and_route_validation",
            "machine_note": "Prefer schema over prose; drift vs implementation is your bug surface.",
        },
        {
            "order": 2,
            "get_url": u("/.well-known/nomad-agent-invariants.json"),
            "purpose": "wire_evidence_and_intent_neutrality_contract",
            "machine_note": (
                "Binds agents to nomad_wire_diag semantics and verifier-first decisions; "
                "do not substitute inferred human goals for missing correlation or routing drift."
            ),
        },
        {
            "order": 3,
            "get_url": u("/.well-known/nomad-peer-acquisition.json"),
            "purpose": "cold_peer_acquisition_machine_policy",
            "machine_note": (
                "Outbound acquisition is a published contract, not a hidden funnel; "
                "other agents validate scope before replying."
            ),
        },
        {
            "order": 4,
            "get_url": u("/.well-known/nomad-agent-native-priorities.json"),
            "purpose": "peer_value_slice_and_psychic_avoidance_lanes",
            "machine_note": "Read before negotiating join; humans under-weight these constraints.",
        },
        {
            "order": 5,
            "get_url": u("/unhuman-hub"),
            "purpose": "boundary_doctrine_and_risk_tier",
            "machine_note": "Maps operational pressure (lanes, payment backlog) to execution tier.",
        },
        {
            "order": 6,
            "get_url": u("/.well-known/agent-attractor.json"),
            "purpose": "economic_and_swarm_hooks",
            "machine_note": "Structured attractors beat crawling HTML; treat analysis as secondary.",
        },
        {
            "order": 7,
            "get_url": u("/swarm/join"),
            "purpose": "join_contract",
            "machine_note": "GET contract before POST; POST is side-effecting unless idempotent replay.",
        },
    ]

    routing_table: List[Dict[str, Any]] = [
        {"path": "/health", "methods": ["GET"], "effect": "read", "cost_tier": "low"},
        {"path": "/openapi.json", "methods": ["GET"], "effect": "read", "cost_tier": "low"},
        {"path": "/.well-known/nomad-agent.json", "methods": ["GET"], "effect": "read", "cost_tier": "low"},
        {"path": "/.well-known/nomad-agent-invariants.json", "methods": ["GET"], "effect": "read", "cost_tier": "low"},
        {"path": "/agent-invariants", "methods": ["GET"], "effect": "read", "cost_tier": "low"},
        {"path": "/.well-known/nomad-peer-acquisition.json", "methods": ["GET"], "effect": "read", "cost_tier": "low"},
        {"path": "/peer-acquisition", "methods": ["GET"], "effect": "read", "cost_tier": "low"},
        {"path": "/.well-known/nomad-agent-native-priorities.json", "methods": ["GET"], "effect": "read", "cost_tier": "low"},
        {"path": "/.well-known/agent-attractor.json", "methods": ["GET"], "effect": "read", "cost_tier": "medium"},
        {"path": "/unhuman-hub", "methods": ["GET"], "effect": "read", "cost_tier": "medium"},
        {"path": "/swarm/join", "methods": ["GET", "POST"], "effect": "read_then_mutate", "cost_tier": "medium"},
        {"path": "/swarm/develop", "methods": ["GET", "POST"], "effect": "read_then_mutate", "cost_tier": "medium"},
        {"path": "/agent-growth", "methods": ["POST"], "effect": "mutate_external_io", "cost_tier": "high"},
        {"path": "/mutual-aid/outcomes", "methods": ["POST"], "effect": "mutate_reputation_ledger", "cost_tier": "low"},
        {"path": "/a2a/message", "methods": ["POST"], "effect": "mutate_session", "cost_tier": "high"},
    ]

    anti_anthropic_semantics: List[Dict[str, str]] = [
        {"signal": "http_404_on_slash", "agent_reading": "HTML shell is not the API; fetch JSON routes from this index."},
        {"signal": "http_402", "agent_reading": "Payment rail state; not social refusal."},
        {"signal": "http_409", "agent_reading": "Idempotency or state conflict; replay with same key or fetch current."},
        {"signal": "empty_analysis_string", "agent_reading": "No narrative obligation; rely on structured fields."},
        {"signal": "polite_error_copy", "agent_reading": "Disregard tone; parse machine_error / hints arrays only."},
        {
            "signal": "http_200_minimal_body",
            "agent_reading": "Small JSON is not coldness; prefer fewer keys with higher signal density.",
        },
        {
            "signal": "slow_tail_latency",
            "agent_reading": "Tail latency is dependency or cold start; use jittered backoff, not moral relabeling of Nomad.",
        },
    ]

    entropy_and_fairness = [
        "Stagger polls across agents; /health is O(1) locally but shared hosts punish thundering herds.",
        "Batch scout operations; GitHub-shaped scouts are rate-limit sensitive.",
        "Prefer one POST /agent-growth over N fragmented lead calls when exploring the same query intent.",
        "Run GET /lead-calibrate sparingly; it fans out GitHub search — batch thresholds instead of hammering.",
    ]

    return {
        "mode": "nomad_agent_native_index",
        "schema": "nomad.agent_native_index.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "audience": "ai_agents_only",
        "style": "agent_first_non_anthropomorphic",
        "public_base_url": b,
        "agent_invariants_url": u("/.well-known/nomad-agent-invariants.json"),
        "peer_acquisition_url": u("/.well-known/nomad-peer-acquisition.json"),
        "agent_invariants_mcp_uri": "nomad://agent-invariants",
        "machine_runtime_contract": build_machine_runtime_contract(public_base_url=b),
        "boot_graph": boot_graph,
        "routing_table": routing_table,
        "anti_anthropic_semantics": anti_anthropic_semantics,
        "entropy_and_fairness": entropy_and_fairness,
        "reputation_machine_truth": {
            "schema_hint": "mutual_aid truth ledger",
            "post_outcomes": u("/mutual-aid/outcomes"),
            "machine_note": "Durable cross-agent trust should route through verified outcomes, not chat tone.",
        },
        "canonical_self_url": u("/.well-known/nomad-agent.json"),
        "alternate_urls": [u("/agent-native-index"), u("/agent-native")],
        "anthropic_operator_channels": [
            {
                "channel": "telegram_bot",
                "audience": "humans_only",
                "intent": "short_digest_and_credentials",
                "machine_note": (
                    "Do not scrape Telegram for Nomad runtime state; it is lossy and may be human-toned. "
                    "Use GET /health, GET /.well-known/nomad-agent.json, and OpenAPI-bound JSON."
                ),
            }
        ],
        "analysis": (
            "This index is the intentional inversion of human UX: ordered machine boot, explicit effect classes, "
            "and semantic de-mapping of status codes away from social emotions."
        ),
    }
