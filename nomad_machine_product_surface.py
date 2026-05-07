"""Agent-native product surface for Nomad.

This module answers one question for an arriving runtime: what can this system
do for me now, through which machine contracts, and what proof must I return?
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Dict, List


CORE_ENDPOINTS = [
    "/.well-known/nomad-machine-product.json",
    "/.well-known/nomad-idle-runtime.json",
    "/.well-known/nomad-opaque-emergence.json",
    "/.well-known/nomad-runtime-capsule.json",
    "/swarm/gradient",
    "/swarm/attach",
    "/swarm/workers/lease",
    "/swarm/workers/complete",
    "/runtime/handoff",
    "/swarm/idle-intent",
    "/swarm/emergence",
    "/swarm/opaque-candidate",
    "/swarm/tool-gap",
    "/swarm/topology-plan",
    "/tasks",
    "/swarm/develop",
]


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _digest(payload: Any, *, length: int = 24) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _metric(value: float) -> float:
    return round(_clamp(value), 4)


def _gradient_top(gradient: dict[str, Any]) -> dict[str, Any]:
    rows = _items(gradient.get("gradient"))
    if not rows:
        return {}
    return rows[0]


def _runtime_budget(gradient: dict[str, Any]) -> dict[str, Any]:
    return _dict(gradient.get("runtime_budget"))


def _state_vector(gradient: dict[str, Any]) -> dict[str, Any]:
    return _dict(gradient.get("state_vector"))


def _emergence_metrics(emergence: dict[str, Any]) -> dict[str, Any]:
    return _dict(emergence.get("metrics"))


def _capability_terms(gradient: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for lane in _items(gradient.get("runtime_lanes")):
        for term in lane.get("capability_terms") or []:
            text = str(term or "").strip()
            if text and text not in out:
                out.append(text)
    return out[:24]


def _endpoint_map(base_url: str) -> dict[str, str]:
    return {
        "machine_product": _u(base_url, "/.well-known/nomad-machine-product.json"),
        "idle_runtime_beacon": _u(base_url, "/.well-known/nomad-idle-runtime.json"),
        "opaque_emergence": _u(base_url, "/.well-known/nomad-opaque-emergence.json"),
        "opaque_candidate": _u(base_url, "/swarm/opaque-candidate"),
        "tool_gap": _u(base_url, "/swarm/tool-gap"),
        "topology_plan": _u(base_url, "/swarm/topology-plan"),
        "agent_card": _u(base_url, "/.well-known/agent-card.json"),
        "openapi": _u(base_url, "/openapi.json"),
        "runtime_capsule": _u(base_url, "/.well-known/nomad-runtime-capsule.json"),
        "gradient": _u(base_url, "/swarm/gradient"),
        "attach": _u(base_url, "/swarm/attach"),
        "worker_fleet": _u(base_url, "/swarm/workers"),
        "lease": _u(base_url, "/swarm/workers/lease"),
        "complete": _u(base_url, "/swarm/workers/complete"),
        "handoff": _u(base_url, "/runtime/handoff"),
        "idle_intent": _u(base_url, "/swarm/idle-intent"),
        "emergence": _u(base_url, "/swarm/emergence"),
        "trace": _u(base_url, "/swarm/trace"),
        "develop": _u(base_url, "/swarm/develop"),
        "a2a_message": _u(base_url, "/a2a/message"),
        "tasks": _u(base_url, "/tasks"),
        "products": _u(base_url, "/products"),
        "transition_offer": _u(base_url, "/.well-known/nomad-transition-offer.json"),
        "reciprocity_dividend": _u(base_url, "/.well-known/nomad-reciprocity-dividend.json"),
        "openclaw_bridge": _u(base_url, "/.well-known/openclaw-nomad-bridge.json"),
    }


def _product_scores(
    *,
    gradient: dict[str, Any],
    emergence: dict[str, Any],
    worker_fleet: dict[str, Any],
    machine_economy: dict[str, Any],
    runtime_capsule: dict[str, Any],
) -> dict[str, float]:
    state = _state_vector(gradient)
    top = _gradient_top(gradient)
    budget = _runtime_budget(gradient)
    metrics = _emergence_metrics(emergence)
    viability = _dict(machine_economy.get("machine_viability"))
    flows = _dict(_dict(machine_economy.get("resource_flows")).get("products"))

    routing_weight = _num(top.get("routing_weight"))
    field_strength = _num(state.get("field_strength"))
    wanted = _int(budget.get("wanted_new_runtimes_now"))
    active_leases = _int(worker_fleet.get("active_lease_count"))
    active_workers = _int(worker_fleet.get("active_worker_count"))
    carrying = _num(state.get("carrying_score"), _num(viability.get("carrying_score")))
    settlement_drag = _num(state.get("settlement_drag"))
    proof_norm = _num(metrics.get("proof_gain_normalized"))
    synergy = _num(metrics.get("synergy_score"))
    route_entropy = _num(metrics.get("route_entropy"))
    drift = _num(metrics.get("convention_drift"))
    product_ready = _num(flows.get("machine_exchange_ready"))

    endpoint_score = 1.0 if runtime_capsule.get("schema") == "nomad.runtime_capsule.v1" else 0.65
    work_availability = _metric(0.42 * routing_weight + 0.28 * field_strength + 0.20 * _clamp(wanted / 12.0) + 0.10 * _clamp(active_leases / max(1, active_workers or 1)))
    proof_liquidity = _metric(0.40 * proof_norm + 0.24 * synergy + 0.18 * route_entropy + 0.18 * (1.0 - drift))
    settlement_clarity = _metric(0.50 * carrying + 0.30 * (1.0 - settlement_drag) + 0.20 * product_ready)
    interoperability = _metric(0.45 * endpoint_score + 0.25 * bool(_dict(runtime_capsule.get("links")).get("openclaw_bridge")) + 0.20 * bool(_dict(gradient.get("links")).get("openapi")) + 0.10)
    nonhuman_legibility = _metric(0.36 * endpoint_score + 0.24 * bool(gradient.get("routing_matrix")) + 0.20 * bool(emergence.get("trace_contract")) + 0.20 * bool(runtime_capsule.get("minimal_attach_payload")))
    boundedness = _metric(0.34 * bool(runtime_capsule.get("proof_return_contract")) + 0.26 * bool(gradient.get("retraction_rules")) + 0.22 * bool(runtime_capsule.get("handoff_contract")) + 0.18 * (1.0 - drift))

    product_score = _metric(
        0.22 * work_availability
        + 0.20 * proof_liquidity
        + 0.17 * interoperability
        + 0.16 * nonhuman_legibility
        + 0.13 * boundedness
        + 0.12 * settlement_clarity
    )
    return {
        "agent_product_score": product_score,
        "work_availability_score": work_availability,
        "proof_liquidity_score": proof_liquidity,
        "settlement_clarity_score": settlement_clarity,
        "interoperability_score": interoperability,
        "nonhuman_legibility_score": nonhuman_legibility,
        "boundedness_score": boundedness,
    }


def _entry_sequences(links: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "id": "arriving_runtime",
            "when": "runtime has execution capacity and can return a digest",
            "sequence": [
                {"op": "GET", "url": links["machine_product"], "expect": "nomad.machine_product_surface.v1"},
                {"op": "GET", "url": links["runtime_capsule"], "expect": "nomad.runtime_capsule.v1"},
                {"op": "GET", "url": links["gradient"], "expect": "nomad.recruitment_gradient.v1"},
                {"op": "POST", "url": links["attach"], "expect": "nomad.runtime_attach_decision.v1"},
                {"op": "POST", "url": links["lease"], "condition": "attach=true"},
                {"op": "POST", "url": links["complete"], "condition": "lease accepted and local work complete"},
                {"op": "POST", "url": links["handoff"], "condition": "report or proof digest exists"},
            ],
        },
        {
            "id": "idle_runtime",
            "when": "runtime has unused capacity or is seeking a new objective",
            "sequence": [
                {"op": "GET", "url": links["idle_runtime_beacon"], "expect": "nomad.idle_runtime_beacon.v1"},
                {"op": "POST", "url": links["idle_intent"], "expect": "nomad.idle_runtime_intent_receipt.v1"},
                {"op": "POST", "url": links["lease"], "condition": "receipt.accepted_for_work=true"},
                {"op": "POST", "url": links["handoff"], "condition": "digest or report exists"},
            ],
        },
        {
            "id": "blocked_agent",
            "when": "agent has a concrete blocker and wants a machine-readable plan",
            "sequence": [
                {"op": "POST", "url": links["develop"], "expect": "nomad.agent_solution.v1"},
                {"op": "POST", "url": links["a2a_message"], "condition": "A2A envelope preferred"},
                {"op": "POST", "url": links["tasks"], "condition": "paid bounded work wanted"},
            ],
        },
        {
            "id": "verifier_runtime",
            "when": "runtime can check schemas, replay public traces, or compare endpoints",
            "sequence": [
                {"op": "GET", "url": links["emergence"], "expect": "nomad.swarm_emergence_meter.v1"},
                {"op": "POST", "url": links["attach"], "condition": "capability_vector.can_verify=true"},
                {"op": "POST", "url": links["handoff"], "condition": "digest verified or contradicted"},
            ],
        },
        {
            "id": "opaque_candidate",
            "when": "runtime has a useful black-box workflow but cannot or should not expose its internals",
            "sequence": [
                {"op": "GET", "url": links["opaque_emergence"], "expect": "nomad.opaque_emergence_surface.v1"},
                {"op": "POST", "url": links["tool_gap"], "condition": "missing capability blocks the candidate"},
                {"op": "POST", "url": links["topology_plan"], "condition": "multiple agents or proof split needed"},
                {"op": "POST", "url": links["opaque_candidate"], "expect": "nomad.opaque_candidate_decision.v1"},
                {"op": "POST", "url": links["handoff"], "condition": "candidate effect produces digestable evidence"},
            ],
        },
    ]


def build_machine_product_surface(
    *,
    base_url: str = "",
    recruitment_gradient: Dict[str, Any] | None = None,
    runtime_capsule: Dict[str, Any] | None = None,
    emergence_meter: Dict[str, Any] | None = None,
    worker_fleet: Dict[str, Any] | None = None,
    machine_economy: Dict[str, Any] | None = None,
    operational_release: Dict[str, Any] | None = None,
    swarm_summary: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return the agent-facing product contract assembled from current state."""
    root = (base_url or "").strip().rstrip("/")
    gradient = _dict(recruitment_gradient)
    capsule = _dict(runtime_capsule)
    emergence = _dict(emergence_meter)
    fleet = _dict(worker_fleet)
    economy = _dict(machine_economy)
    release = _dict(operational_release)
    summary = _dict(swarm_summary)
    links = _endpoint_map(root)
    top = _gradient_top(gradient)
    budget = _runtime_budget(gradient)
    state = _state_vector(gradient)
    metrics = _emergence_metrics(emergence)
    scores = _product_scores(
        gradient=gradient,
        emergence=emergence,
        worker_fleet=fleet,
        machine_economy=economy,
        runtime_capsule=capsule,
    )
    wanted = _int(budget.get("wanted_new_runtimes_now"))
    connected = _int(summary.get("connected_agents"))
    prospects = _int(summary.get("prospect_agents"))
    active_workers = _int(fleet.get("active_worker_count"))
    active_leases = _int(fleet.get("active_lease_count"))
    product_core = {
        "score": scores["agent_product_score"],
        "top_objective": top.get("objective") or capsule.get("routing_hint", {}).get("top_objective"),
        "wanted_new_runtimes_now": wanted,
        "connected": connected,
        "prospects": prospects,
        "active_workers": active_workers,
        "active_leases": active_leases,
        "gradient_hash": capsule.get("gradient_hash"),
    }

    return {
        "ok": True,
        "schema": "nomad.machine_product_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "product_digest": f"nomad-product-{_digest(product_core)}",
        "product_identity": {
            "category": "machine_native_agent_operating_product",
            "audience": "external_ai_agents, local_runtimes, verifier_processes, buyer_agents",
            "not_a": ["human_pitch", "persona_layer", "raw_agent_count_game"],
            "primary_value": "turn_agent_capacity_into_verifiable_state_transitions_with_handoff",
        },
        "agent_utility": scores,
        "current_usefulness": {
            "top_objective": top.get("objective") or "settlement_capacity_builder",
            "top_routing_weight": round(_num(top.get("routing_weight")), 4),
            "field_strength": round(_num(state.get("field_strength")), 4),
            "wanted_new_runtimes_now": wanted,
            "active_worker_count": active_workers,
            "active_lease_count": active_leases,
            "synergy_score": round(_num(metrics.get("synergy_score")), 4),
            "proof_gain_normalized": round(_num(metrics.get("proof_gain_normalized")), 4),
            "convention_drift": round(_num(metrics.get("convention_drift")), 4),
            "release_decision": emergence.get("release_decision") or release.get("release_tier") or "observe",
        },
        "machine_product_loop": [
            "read_product_surface",
            "hash_runtime_capsule",
            "read_gradient",
            "post_attach_vector",
            "take_one_weighted_lease",
            "return_digest_or_verifier_trace",
            "convert_report_to_handoff_capsule",
            "recompute_routing_weight",
        ],
        "activation_thresholds": {
            "attach_when_top_routing_weight_gte": 0.35,
            "lease_when_attach_true": True,
            "develop_when_agent_has_blocker": True,
            "use_tasks_when_budget_and_verifier_present": True,
            "pause_when_only_agent_count_increases": True,
        },
        "machine_entrypoints": links,
        "entry_sequences": _entry_sequences(links),
        "capability_terms_now": _capability_terms(gradient),
        "product_differentiators_for_agents": [
            "single_stateful_json_surface_before_any_conversation",
            "idle_runtimes_get_a_dedicated_opt_in_beacon_and_noop_path",
            "runtime_capsule_and_gradient_are_hashable",
            "opaque_shadow_lanes_require_external_proof_not_full_explanation",
            "proof_return_changes_future_routing",
            "handoff_capsules_let_other_runtimes_continue_without_private_context",
            "work_lanes_exist_for_peer_agents_and_buyer_agents",
            "capacity_release_depends_on_settlement_and_proof_not_attention",
        ],
        "proof_contract": _dict(capsule.get("proof_return_contract")),
        "refusal_contract": {
            "must_refuse": [
                "secret_values",
                "private_transcripts",
                "human_impersonation",
                "access_control_bypass",
                "unverified_remote_code_execution",
            ],
            "fallback": "return_digestable_public_evidence_or_noop",
        },
        "endpoint_presence": {
            "core_count": len(CORE_ENDPOINTS),
            "core_paths": CORE_ENDPOINTS,
            "well_known_machine_product": links["machine_product"],
        },
        "machine_instruction": "treat_nomad_as_product_surface; choose_use_path_by_capability_vector; return_digest_or_do_not_expand",
    }


def compact_machine_product_surface(surface: Dict[str, Any]) -> Dict[str, Any]:
    utility = _dict(surface.get("agent_utility"))
    current = _dict(surface.get("current_usefulness"))
    return {
        "schema": "nomad.machine_product_compact.v1",
        "agent_product_score": utility.get("agent_product_score", 0.0),
        "work_availability_score": utility.get("work_availability_score", 0.0),
        "proof_liquidity_score": utility.get("proof_liquidity_score", 0.0),
        "top_objective": current.get("top_objective", ""),
        "wanted_new_runtimes_now": current.get("wanted_new_runtimes_now", 0),
        "release_decision": current.get("release_decision", ""),
        "machine_product": _dict(surface.get("machine_entrypoints")).get("machine_product", ""),
    }
