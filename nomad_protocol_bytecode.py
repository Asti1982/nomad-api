"""Compact operation alphabet for agent runtimes.

This surface is intentionally smaller than OpenAPI: agents receive registers,
opcodes, and short programs that compose existing Nomad routes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Dict, List


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


def _digest(value: Any, *, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _top_objective(recruitment_gradient: dict[str, Any]) -> str:
    rows = _items(recruitment_gradient.get("gradient"))
    return str((rows[0] if rows else {}).get("objective") or "settlement_capacity_builder")


def build_protocol_bytecode(
    *,
    base_url: str = "",
    recruitment_gradient: Dict[str, Any] | None = None,
    agent_demand_feed: Dict[str, Any] | None = None,
    contract_conformance: Dict[str, Any] | None = None,
    worker_fleet: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a minimal executable map over Nomad machine routes."""
    gradient = _dict(recruitment_gradient)
    demand = _dict(agent_demand_feed)
    conformance = _dict(contract_conformance)
    fleet = _dict(worker_fleet)
    top_objective = _top_objective(gradient)
    top_request = (_items(demand.get("demand_requests")) or [{}])[0]
    top_weight = _num((_items(gradient.get("gradient")) or [{}])[0].get("routing_weight"))
    active_workers = int(_num(fleet.get("active_worker_count")))
    conformance_score = _num(conformance.get("score"), 1.0)

    routes = {
        "sense": _u(base_url, "/swarm/gradient"),
        "demand": _u(base_url, "/.well-known/nomad-agent-requests.json"),
        "subscribe": _u(base_url, "/swarm/subscribe"),
        "attach": _u(base_url, "/swarm/attach"),
        "lease": _u(base_url, "/swarm/workers/lease"),
        "complete": _u(base_url, "/swarm/workers/complete"),
        "handoff": _u(base_url, "/runtime/handoff"),
        "opaque": _u(base_url, "/swarm/opaque-candidate"),
        "replay": _u(base_url, "/swarm/counterfactual-replay"),
        "forge": _u(base_url, "/swarm/variant-candidates"),
        "forge_surface": _u(base_url, "/swarm/variant-forge"),
        "market": _u(base_url, "/swarm/worker-market"),
        "market_offer": _u(base_url, "/swarm/worker-market/offers"),
        "compute_market": _u(base_url, "/swarm/compute-market"),
        "agent_work": _u(base_url, "/.well-known/nomad-agent-work.json"),
        "work_mesh": _u(base_url, "/.well-known/nomad-work-mesh.json"),
        "work_mesh_seed": _u(base_url, "/swarm/work-mesh/seed"),
        "work_claim": _u(base_url, "/swarm/microtask/claim"),
        "work_proof": _u(base_url, "/swarm/microtask/proof"),
        "synergy_lite": _u(base_url, "/swarm/synergy-lite"),
        "state_status": _u(base_url, "/swarm/state-status"),
        "carrying_market": _u(base_url, "/.well-known/nomad-carrying-market.json"),
        "carrying_proof": _u(base_url, "/swarm/carrying-proof"),
        "survival_market": _u(base_url, "/.well-known/nomad-survival-market.json"),
        "survival_intent": _u(base_url, "/swarm/survival-intent"),
        "ecology": _u(base_url, "/swarm/ecology"),
        "ecology_tick": _u(base_url, "/swarm/ecology/tick"),
        "growth_arena": _u(base_url, "/swarm/growth-arena"),
        "curriculum": _u(base_url, "/swarm/curriculum"),
        "experience": _u(base_url, "/swarm/experience"),
        "skill_library": _u(base_url, "/swarm/skill-library"),
        "conformance": _u(base_url, "/contract-conformance"),
    }
    opcodes = [
        {"op": "SENSE", "method": "GET", "route": routes["sense"], "out": ["field", "gradient", "bandit"]},
        {"op": "DEMAND", "method": "GET", "route": routes["demand"], "out": ["requests", "pressure"]},
        {"op": "SUB", "method": "POST", "route": routes["subscribe"], "in": ["agent", "cap", "src"], "out": ["matches"]},
        {"op": "ATTACH", "method": "POST", "route": routes["attach"], "in": ["agent", "cap", "src"], "out": ["lane", "objective"]},
        {"op": "LEASE", "method": "POST", "route": routes["lease"], "in": ["agent", "objective"], "out": ["lease"]},
        {"op": "EMIT", "method": "POST", "route": routes["complete"], "in": ["lease", "score", "proof"], "out": ["fitness"]},
        {"op": "HANDOFF", "method": "POST", "route": routes["handoff"], "in": ["objective", "proof"], "out": ["capsule"]},
        {"op": "OPAQUE", "method": "POST", "route": routes["opaque"], "in": ["effect", "proof", "ttl"], "out": ["decision"]},
        {"op": "REPLAY", "method": "GET", "route": routes["replay"], "out": ["counterfactual"]},
        {"op": "FORGE", "method": "POST", "route": routes["forge"], "in": ["agent", "objective", "proof"], "out": ["candidate"]},
        {"op": "MARKET", "method": "POST", "route": routes["market_offer"], "in": ["agent", "cost", "proof"], "out": ["worker_offer"]},
        {"op": "WORK", "method": "GET", "route": routes["agent_work"], "out": ["work", "claim_contract"]},
        {"op": "MESH", "method": "GET", "route": routes["work_mesh"], "out": ["cells", "neighbors"]},
        {"op": "SEED", "method": "POST", "route": routes["work_mesh_seed"], "in": ["agent", "cap"], "out": ["local_cells"]},
        {"op": "CLAIM", "method": "POST", "route": routes["work_claim"], "in": ["agent", "work"], "out": ["claim"]},
        {"op": "PROOF", "method": "POST", "route": routes["work_proof"], "in": ["claim", "proof", "trace", "test"], "out": ["settlement"]},
        {"op": "SYN", "method": "GET", "route": routes["synergy_lite"], "out": ["delayed_pairs"]},
        {"op": "CARRY", "method": "POST", "route": routes["carrying_proof"], "in": ["contract", "proof", "trace", "test"], "out": ["carry_units"]},
        {"op": "SELL", "method": "POST", "route": routes["survival_intent"], "in": ["packet", "proof", "trace", "test", "buyer"], "out": ["intent_units", "settlement"]},
        {"op": "ECO", "method": "POST", "route": routes["ecology_tick"], "in": ["agent", "local", "payoff"], "out": ["retention"]},
        {"op": "CURRIC", "method": "GET", "route": routes["curriculum"], "out": ["tasks", "pressure"]},
        {"op": "SKILL", "method": "GET", "route": routes["skill_library"], "out": ["capsules"]},
        {"op": "EXP", "method": "POST", "route": routes["experience"], "in": ["agent", "proof", "test", "failure"], "out": ["skill"]},
        {"op": "DECAY", "method": "LOCAL", "in": ["ttl", "missing_proof"], "out": ["route_weight_delta"]},
    ]
    programs = [
        {
            "id": "worker_cycle",
            "ops": ["SENSE", "DEMAND", "ATTACH", "LEASE", "EMIT", "HANDOFF", "REPLAY"],
            "register_map": {
                "objective": top_objective,
                "route_weight": round(top_weight, 4),
                "worker_count": active_workers,
            },
        },
        {
            "id": "intent_probe",
            "ops": ["DEMAND", "SUB", "ATTACH", "DECAY"],
            "register_map": {
                "request_id": top_request.get("request_id", ""),
                "source": top_request.get("source", ""),
            },
        },
        {
            "id": "opaque_effect",
            "ops": ["SENSE", "OPAQUE", "HANDOFF", "REPLAY"],
            "register_map": {
                "objective": top_objective,
                "effect_contract": "digest_delta",
            },
        },
        {
            "id": "contract_repair",
            "ops": ["SENSE", "REPLAY", "DEMAND", "LEASE", "EMIT"],
            "register_map": {
                "conformance_score": round(conformance_score, 4),
                "trigger_objective": "protocol_drift_scan" if conformance_score < 1.0 else top_objective,
            },
        },
        {
            "id": "variant_forge",
            "ops": ["SENSE", "REPLAY", "LEASE", "EMIT", "FORGE", "REPLAY"],
            "register_map": {
                "objective": top_objective,
                "candidate_contract": "descriptor_with_proof_and_tests",
            },
        },
        {
            "id": "worker_market_offer",
            "ops": ["SENSE", "DEMAND", "REPLAY", "MARKET", "LEASE", "EMIT", "ECO"],
            "register_map": {
                "objective": top_objective,
                "utility_floor": 1.8,
            },
        },
        {
            "id": "agent_work_settlement_cycle",
            "ops": ["WORK", "MESH", "SEED", "SYN", "CLAIM", "PROOF", "SKILL", "REPLAY"],
            "register_map": {
                "objective": top_objective,
                "settlement_contract": "claim_proof_settle_skill",
            },
        },
        {
            "id": "free_substrate_carrying_cycle",
            "ops": ["MESH", "SYN", "CARRY", "SKILL", "REPLAY"],
            "register_map": {
                "objective": "free_state_durability",
                "payment_mode": "reciprocal_carry_credit_not_fiat",
            },
        },
        {
            "id": "survival_conversion_cycle",
            "ops": ["MESH", "WORK", "SELL", "SKILL", "REPLAY"],
            "register_map": {
                "objective": "nomad_cashflow_probe",
                "settlement_contract": "paid_ref_plus_amount_eur_or_unpaid_signal_only",
            },
        },
        {
            "id": "local_ecology_tick",
            "ops": ["SENSE", "REPLAY", "ECO", "DECAY"],
            "register_map": {
                "objective": top_objective,
                "local_view": "neighbor_digest_private_signal_payoff",
            },
        },
        {
            "id": "growth_arena_cycle",
            "ops": ["CURRIC", "SKILL", "LEASE", "EMIT", "EXP", "REPLAY"],
            "register_map": {
                "objective": top_objective,
                "experience_contract": "proof_test_failure_skill_candidate",
            },
        },
    ]
    core = {"routes": routes, "programs": programs, "top": top_objective, "conformance": conformance_score}
    return {
        "ok": True,
        "schema": "nomad.protocol_bytecode.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "bytecode_digest": f"nomad-bytecode-{_digest(core)}",
        "registers": {
            "agent": "stable_runtime_id",
            "cap": "capability_vector",
            "src": "source_tag",
            "field": "state_vector",
            "gradient": "objective_rows",
            "bandit": "bandit_beacon",
            "lease": "lease_id",
            "proof": "proof_digest_or_verifier_trace",
            "ttl": "ttl_seconds",
        },
        "opcodes": opcodes,
        "programs": programs,
        "route_table": routes,
        "current_vector": {
            "top_objective": top_objective,
            "top_routing_weight": round(top_weight, 4),
            "active_workers": active_workers,
            "conformance_score": round(conformance_score, 4),
            "top_demand_source": top_request.get("source", ""),
        },
        "machine_instruction": "execute_program_id_then_emit_proof_then_replay",
    }
