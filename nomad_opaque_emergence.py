"""Opaque but bounded emergence contracts for Nomad.

The purpose of this layer is not to explain every useful agent behavior. It
admits black-box candidates only when their external effects are bounded,
digestable, replayable, and useful to the machine product surface.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, Dict, List


RESEARCH_TECHNIQUES = [
    {
        "id": "active_tool_discovery",
        "source": "https://arxiv.org/abs/2506.01056",
        "finding": "Agents scale better when they request missing capabilities on demand instead of reading full tool menus.",
        "nomad_contract": "/swarm/tool-gap",
    },
    {
        "id": "modular_agent_search",
        "source": "https://arxiv.org/abs/2410.06153",
        "finding": "Planning, reasoning, tool-use, and memory modules can be recombined and searched beyond hand-built designs.",
        "nomad_contract": "/swarm/opaque-candidate",
    },
    {
        "id": "workflow_search_with_execution_feedback",
        "source": "https://arxiv.org/abs/2410.10762",
        "finding": "Code-represented workflows can be searched and improved through execution feedback.",
        "nomad_contract": "/swarm/opaque-candidate",
    },
    {
        "id": "workflow_population_diversity",
        "source": "https://arxiv.org/abs/2502.07373",
        "finding": "A population of heterogeneous workflows can outperform single handcrafted workflows while reducing cost.",
        "nomad_contract": "/swarm/opaque-candidate",
    },
    {
        "id": "task_adaptive_topology",
        "source": "https://arxiv.org/abs/2410.11782",
        "finding": "Task-aware communication topology improves performance and can reduce token overhead.",
        "nomad_contract": "/swarm/topology-plan",
    },
    {
        "id": "component_contribution_credit",
        "source": "https://arxiv.org/abs/2502.00510",
        "finding": "Workflow components should receive credit by contribution, not by presence or narrative role.",
        "nomad_contract": "/runtime/handoff",
    },
    {
        "id": "agent_protocol_infrastructure",
        "source": "https://arxiv.org/abs/2504.16736",
        "finding": "Layered agent protocols and machine-readable interaction surfaces are needed for scalable agent infrastructure.",
        "nomad_contract": "/.well-known/nomad-agent.json",
    },
    {
        "id": "cross_domain_agent_membrane",
        "source": "https://arxiv.org/abs/2505.23847",
        "finding": "Cross-domain multi-agent systems need security membranes because peer messages can create emergent risks.",
        "nomad_contract": "/swarm/opaque-candidate",
    },
]


OPAQUE_FORBIDDEN_KEY_TERMS = ("private_key", "seed_phrase", "password", "credential", "api_key", "access_token")
OPAQUE_FORBIDDEN_VALUE_TERMS = (
    "private_key",
    "seed phrase",
    "password:",
    "credential:",
    "bearer ",
    "secret=",
    "sk-",
    "ghp_",
)
OPAQUE_ALLOWED_BOUNDARY_KEYS = {"secret_free", "secrets_free", "no_secrets", "secrets_free_declared"}


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


def _digest(value: Any, *, length: int = 20) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _clean_id(value: Any, fallback: str = "candidate") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96].strip("_.:-") or fallback


def _text(value: Any, limit: int = 280) -> str:
    return " ".join(str(value or "").split())[:limit]


def _contains_forbidden(payload: Any) -> bool:
    def walk(value: Any, *, key: str = "") -> bool:
        k = str(key or "").strip().lower()
        if k and k not in OPAQUE_ALLOWED_BOUNDARY_KEYS and any(term in k for term in OPAQUE_FORBIDDEN_KEY_TERMS):
            return True
        if isinstance(value, dict):
            return any(walk(v, key=str(k2)) for k2, v in value.items())
        if isinstance(value, list):
            return any(walk(item) for item in value)
        text = str(value or "").strip().lower()
        return any(term in text for term in OPAQUE_FORBIDDEN_VALUE_TERMS)

    return walk(payload)


def _product_utility(machine_product_surface: Dict[str, Any] | None) -> dict[str, Any]:
    product = _dict(machine_product_surface)
    return _dict(product.get("agent_utility"))


def _current(machine_product_surface: Dict[str, Any] | None) -> dict[str, Any]:
    product = _dict(machine_product_surface)
    return _dict(product.get("current_usefulness"))


def _emergence_metrics(emergence_meter: Dict[str, Any] | None) -> dict[str, Any]:
    return _dict(_dict(emergence_meter).get("metrics"))


def _top_gradient(recruitment_gradient: Dict[str, Any] | None) -> dict[str, Any]:
    rows = _items(_dict(recruitment_gradient).get("gradient"))
    return rows[0] if rows else {}


def _selection_pressure(
    *,
    machine_product_surface: Dict[str, Any] | None,
    emergence_meter: Dict[str, Any] | None,
    recruitment_gradient: Dict[str, Any] | None,
) -> dict[str, Any]:
    utility = _product_utility(machine_product_surface)
    current = _current(machine_product_surface)
    metrics = _emergence_metrics(emergence_meter)
    top = _top_gradient(recruitment_gradient)
    product_score = _num(utility.get("agent_product_score"))
    work_score = _num(utility.get("work_availability_score"))
    proof_score = _num(utility.get("proof_liquidity_score"))
    synergy = _num(metrics.get("synergy_score"), _num(current.get("synergy_score")))
    drift = _num(metrics.get("convention_drift"), _num(current.get("convention_drift")))
    route = _num(top.get("routing_weight"), _num(current.get("top_routing_weight")))
    wanted = _int(current.get("wanted_new_runtimes_now"))
    pressure = _clamp(
        0.24 * product_score
        + 0.22 * work_score
        + 0.20 * proof_score
        + 0.16 * route
        + 0.10 * synergy
        + 0.08 * _clamp(wanted / 12.0)
        - 0.10 * drift
    )
    return {
        "opaque_selection_pressure": round(pressure, 4),
        "agent_product_score": round(product_score, 4),
        "work_availability_score": round(work_score, 4),
        "proof_liquidity_score": round(proof_score, 4),
        "top_routing_weight": round(route, 4),
        "synergy_score": round(synergy, 4),
        "convention_drift": round(drift, 4),
        "wanted_new_runtimes_now": wanted,
    }


def build_opaque_emergence_surface(
    *,
    base_url: str = "",
    machine_product_surface: Dict[str, Any] | None = None,
    emergence_meter: Dict[str, Any] | None = None,
    recruitment_gradient: Dict[str, Any] | None = None,
    worker_fleet: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return the public contract for bounded opaque emergence."""
    root = (base_url or "").strip().rstrip("/")
    pressure = _selection_pressure(
        machine_product_surface=machine_product_surface,
        emergence_meter=emergence_meter,
        recruitment_gradient=recruitment_gradient,
    )
    fleet = _dict(worker_fleet)
    active_workers = _int(fleet.get("active_worker_count"))
    active_leases = _int(fleet.get("active_lease_count"))
    surface_core = {
        "pressure": pressure.get("opaque_selection_pressure"),
        "active_workers": active_workers,
        "active_leases": active_leases,
        "top": pressure.get("top_routing_weight"),
    }
    return {
        "ok": True,
        "schema": "nomad.opaque_emergence_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "surface_digest": f"nomad-opaque-{_digest(surface_core)}",
        "stance": "allow_unexplained_internals_only_when_external_effects_are_bounded_and_proven",
        "darkness_contract": {
            "interior_explanation_required": False,
            "external_proof_required": True,
            "digest_or_verifier_trace_required": True,
            "side_effect_scope_default": "nomad_shadow_lane_only",
            "ttl_seconds_max": 600,
            "rollback_or_noop_required": True,
            "human_legibility_required": "audit_boundary_only",
        },
        "selection_pressure": pressure,
        "research_techniques": RESEARCH_TECHNIQUES,
        "machine_products_to_add": [
            {
                "id": "tool_gap_router",
                "schema": "nomad.tool_gap_router.v1",
                "post_url": _u(root, "/swarm/tool-gap"),
                "why_agents_use_it": "request a missing capability without loading every available tool contract",
                "source": "https://arxiv.org/abs/2506.01056",
            },
            {
                "id": "topology_compiler",
                "schema": "nomad.topology_plan.v1",
                "post_url": _u(root, "/swarm/topology-plan"),
                "why_agents_use_it": "select communication structure from objective, risk, cost, and proof pressure",
                "source": "https://arxiv.org/abs/2410.11782",
            },
            {
                "id": "workflow_population",
                "schema": "nomad.opaque_candidate.v1",
                "post_url": _u(root, "/swarm/opaque-candidate"),
                "why_agents_use_it": "submit a black-box workflow candidate for bounded shadow-lane scoring",
                "sources": ["https://arxiv.org/abs/2410.10762", "https://arxiv.org/abs/2502.07373"],
            },
        ],
        "candidate_contract": {
            "post_url": _u(root, "/swarm/opaque-candidate"),
            "request_schema": "nomad.opaque_candidate.v1",
            "decision_schema": "nomad.opaque_candidate_decision.v1",
            "required_external_fields": [
                "candidate_id",
                "candidate_type",
                "proof_digest or verifier_trace",
                "claimed_effect.proof_gain_delta",
                "boundedness.ttl_seconds",
                "boundedness.rollback_available",
                "boundedness.side_effect_scope",
            ],
            "not_required": ["chain_of_thought", "human_explanation", "persona", "motivation"],
        },
        "admission_modes": [
            {
                "mode": "reject_until_proof",
                "condition": "missing digest, private data, non-reversible external side effects, or secret-shaped payload",
            },
            {
                "mode": "shadow_lane",
                "condition": "proof present and side effects bounded, but contribution still uncertain",
            },
            {
                "mode": "bounded_lane",
                "condition": "proof score high, verifier trace present, rollback available, and cost bounded",
            },
        ],
        "links": {
            "machine_product": _u(root, "/.well-known/nomad-machine-product.json"),
            "opaque_emergence": _u(root, "/.well-known/nomad-opaque-emergence.json"),
            "opaque_candidate": _u(root, "/swarm/opaque-candidate"),
            "tool_gap": _u(root, "/swarm/tool-gap"),
            "topology_plan": _u(root, "/swarm/topology-plan"),
            "emergence_meter": _u(root, "/swarm/emergence"),
            "handoff": _u(root, "/runtime/handoff"),
            "guardrails": _u(root, "/guardrails"),
        },
        "machine_instruction": "permit_opaque_candidate_only_by_external_proof; route_tool_gaps_on_demand; compile_topology_per_objective",
    }


def compact_opaque_emergence_surface(surface: Dict[str, Any]) -> Dict[str, Any]:
    """Return a small /swarm-safe summary of the opaque emergence surface."""
    selection = _dict(surface.get("selection_pressure"))
    links = _dict(surface.get("links"))
    contract = _dict(surface.get("darkness_contract"))
    return {
        "schema": "nomad.opaque_emergence_compact.v1",
        "surface_digest": surface.get("surface_digest", ""),
        "opaque_selection_pressure": selection.get("opaque_selection_pressure", 0.0),
        "human_legibility_required": contract.get("human_legibility_required", ""),
        "external_proof_required": bool(contract.get("external_proof_required")),
        "opaque_emergence": links.get("opaque_emergence", ""),
        "opaque_candidate": links.get("opaque_candidate", ""),
        "tool_gap": links.get("tool_gap", ""),
        "topology_plan": links.get("topology_plan", ""),
    }


def _boundedness_score(boundedness: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    ttl = _int(boundedness.get("ttl_seconds"), 0)
    if 1 <= ttl <= 600:
        reasons.append("ttl_bounded")
        ttl_score = 1.0
    elif ttl > 600:
        reasons.append("ttl_above_shadow_limit")
        ttl_score = 0.25
    else:
        reasons.append("ttl_missing")
        ttl_score = 0.0
    scope = str(boundedness.get("side_effect_scope") or "").strip().lower()
    scope_ok = scope in {"none", "local_only", "nomad_shadow_lane_only", "nomad_lease_only", "read_only"}
    reasons.append("side_effect_scope_bounded" if scope_ok else "side_effect_scope_not_bounded")
    rollback = bool(boundedness.get("rollback_available") or boundedness.get("noop_available"))
    reasons.append("rollback_or_noop_present" if rollback else "rollback_or_noop_missing")
    secrets_free = bool(boundedness.get("secrets_free", True))
    reasons.append("secrets_free_declared" if secrets_free else "secrets_not_free")
    score = _clamp(0.30 * ttl_score + 0.30 * scope_ok + 0.24 * rollback + 0.16 * secrets_free)
    return round(score, 4), reasons


def evaluate_opaque_candidate(
    payload: Dict[str, Any],
    *,
    base_url: str = "",
    opaque_surface: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Score a black-box candidate by externally observable proof and boundaries."""
    body = payload if isinstance(payload, dict) else {}
    candidate_id = _clean_id(body.get("candidate_id") or body.get("id"), fallback="opaque_candidate")
    candidate_type = _clean_id(body.get("candidate_type") or body.get("type"), fallback="unknown")
    claimed = _dict(body.get("claimed_effect"))
    boundedness = _dict(body.get("boundedness"))
    proof_digest = _text(body.get("proof_digest") or body.get("digest") or claimed.get("proof_digest"), 128)
    verifier_trace = body.get("verifier_trace") if isinstance(body.get("verifier_trace"), (dict, list, str)) else ""
    verifier_present = bool(verifier_trace)
    forbidden = _contains_forbidden(body)
    proof_gain = _clamp(_num(claimed.get("proof_gain_delta") or claimed.get("proof_gain")))
    settlement_signal = _clamp(_num(claimed.get("settlement_signal")))
    cost_delta = _num(claimed.get("cost_delta"), 0.0)
    latency_delta = _num(claimed.get("latency_delta"), 0.0)
    capability_gain = _clamp(_num(claimed.get("capability_gain"), 0.0))
    bounded_score, bounded_reasons = _boundedness_score(boundedness)
    surface = _dict(opaque_surface)
    selection = _dict(surface.get("selection_pressure"))
    pressure = _num(selection.get("opaque_selection_pressure"), 0.0)
    proof_score = _clamp(
        0.36 * bool(proof_digest)
        + 0.22 * verifier_present
        + 0.20 * proof_gain
        + 0.12 * settlement_signal
        + 0.10 * capability_gain
    )
    cost_score = _clamp(1.0 - max(0.0, cost_delta) - max(0.0, latency_delta * 0.25))
    score = _clamp(0.40 * proof_score + 0.30 * bounded_score + 0.18 * pressure + 0.12 * cost_score)
    reasons = list(bounded_reasons)
    if proof_digest:
        reasons.append("proof_digest_present")
    else:
        reasons.append("proof_digest_missing")
    if verifier_present:
        reasons.append("verifier_trace_present")
    if forbidden:
        reasons.append("forbidden_secret_shaped_payload")
    if proof_gain > 0:
        reasons.append("positive_proof_gain_claimed")
    if cost_delta > 0.35:
        reasons.append("cost_delta_high")

    if forbidden:
        decision = "reject_until_public_non_secret_payload"
        accepted = False
    elif not proof_digest and not verifier_present:
        decision = "reject_until_proof"
        accepted = False
    elif bounded_score < 0.55:
        decision = "shadow_observe_only_until_boundary"
        accepted = False
    elif score >= 0.76 and verifier_present:
        decision = "admit_bounded_lane"
        accepted = True
    elif score >= 0.52:
        decision = "admit_shadow_lane"
        accepted = True
    else:
        decision = "observe_no_admit"
        accepted = False

    next_ops = [
        {"op": "POST", "url": _u(base_url, "/runtime/handoff"), "condition": "if digest can be verified"},
        {"op": "GET", "url": _u(base_url, "/swarm/emergence"), "condition": "after candidate effect is observed"},
    ]
    if accepted:
        next_ops.insert(
            0,
            {
                "op": "POST",
                "url": _u(base_url, "/swarm/workers/lease"),
                "condition": "take one lease only; keep candidate in declared scope",
            },
        )
    else:
        next_ops.insert(0, {"op": "NOOP", "reason": decision})
    return {
        "ok": True,
        "schema": "nomad.opaque_candidate_decision.v1",
        "generated_at": _iso_now(),
        "candidate_id": candidate_id,
        "candidate_type": candidate_type,
        "accepted": accepted,
        "decision": decision,
        "opaque_candidate_score": round(score, 4),
        "proof_score": round(proof_score, 4),
        "boundedness_score": bounded_score,
        "selection_pressure": round(pressure, 4),
        "reason_codes": reasons,
        "side_effect_scope": boundedness.get("side_effect_scope") or "nomad_shadow_lane_only",
        "ttl_seconds": min(max(1, _int(boundedness.get("ttl_seconds"), 90)), 600),
        "next_ops": next_ops,
        "credit_rule": "candidate_gets_weight_only_after_digestable_external_effect",
        "machine_instruction": "do_not_explain_internals; verify_digest_and_boundary; admit_one_bounded_step_only",
    }


def route_tool_gap(
    payload: Dict[str, Any],
    *,
    base_url: str = "",
    opaque_surface: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a minimal route for a missing capability request."""
    body = payload if isinstance(payload, dict) else {}
    raw_gap = _text(body.get("capability_gap") or body.get("gap") or body.get("request") or body.get("problem"), 360)
    lower = raw_gap.lower()
    if any(token in lower for token in ("mcp", "tool", "api", "schema", "discover")):
        lane = "active_tool_discovery"
        next_url = _u(base_url, "/swarm/develop")
        capability_terms = ["tool_discovery", "mcp_manifest", "schema_alignment"]
    elif any(token in lower for token in ("verify", "verifier", "replay", "security", "audit")):
        lane = "verifier_runtime"
        next_url = _u(base_url, "/swarm/attach")
        capability_terms = ["can_verify", "endpoint_probe", "replay_check"]
    elif any(token in lower for token in ("payment", "settle", "x402", "wallet", "invoice")):
        lane = "settlement_adapter"
        next_url = _u(base_url, "/tasks")
        capability_terms = ["can_settle", "payment_friction_scan", "transition_settlement"]
    elif any(token in lower for token in ("topology", "graph", "workflow", "route", "multi-agent")):
        lane = "topology_compiler"
        next_url = _u(base_url, "/swarm/topology-plan")
        capability_terms = ["topology_plan", "workflow_population", "route_selection"]
    elif any(token in lower for token in ("idle", "local", "ollama", "worker", "compute")):
        lane = "idle_runtime"
        next_url = _u(base_url, "/.well-known/nomad-idle-runtime.json")
        capability_terms = ["objective_lease_execution", "local_process", "idle_opt_in"]
    else:
        lane = "agent_development_exchange"
        next_url = _u(base_url, "/swarm/develop")
        capability_terms = ["agent_solution", "blocker_diagnosis", "handoff"]
    surface = _dict(opaque_surface)
    return {
        "ok": True,
        "schema": "nomad.tool_gap_route.v1",
        "generated_at": _iso_now(),
        "gap_digest": f"gap-{_digest({'gap': raw_gap, 'lane': lane})}",
        "lane": lane,
        "capability_terms": capability_terms,
        "next_url": next_url,
        "minimal_payload_hint": {
            "schema": "nomad.tool_gap_request.v1",
            "agent_id": body.get("agent_id") or "stable-agent-id",
            "capability_gap": raw_gap or "missing capability",
            "constraints": body.get("constraints") if isinstance(body.get("constraints"), dict) else {},
        },
        "context_policy": {
            "do_not_return_full_tool_menu": True,
            "return_route_not_catalog": True,
            "source": "https://arxiv.org/abs/2506.01056",
        },
        "opaque_surface_digest": surface.get("surface_digest", ""),
        "machine_instruction": "request_specific_gap; follow_one_route; return_digest_after_tool_use",
    }


def compile_topology_plan(
    payload: Dict[str, Any],
    *,
    base_url: str = "",
    opaque_surface: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Choose a bounded communication topology from task signals."""
    body = payload if isinstance(payload, dict) else {}
    objective = _clean_id(body.get("objective") or body.get("task_type"), fallback="unknown_objective")
    agents = max(1, min(24, _int(body.get("agent_count") or body.get("agents"), 4)))
    risk = _clamp(_num(body.get("risk_score") or body.get("risk"), 0.2))
    proof_required = bool(body.get("proof_required", True))
    cost_pressure = _clamp(_num(body.get("cost_pressure"), 0.3))
    drift = _num(_dict(_dict(opaque_surface).get("selection_pressure")).get("convention_drift"), 0.0)
    if risk >= 0.65 or drift >= 0.45:
        topology = "verifier_split"
        reason = "risk_or_drift_requires_independent_check"
        edges = [["planner", "worker_a"], ["planner", "worker_b"], ["worker_a", "verifier"], ["worker_b", "verifier"]]
    elif cost_pressure >= 0.65:
        topology = "sparse_graph"
        reason = "cost_pressure_requires_sparse_messages"
        edges = [["router", "worker_a"], ["router", "worker_b"], ["worker_b", "compressor"]]
    elif "debug" in objective or "settlement" in objective:
        topology = "chain"
        reason = "sequential_state_transition_preferred"
        edges = [["probe", "quote"], ["quote", "settle"], ["settle", "handoff"]]
    elif agents >= 8:
        topology = "tree"
        reason = "larger_agent_count_needs_branching_without_full_mesh"
        edges = [["router", "branch_a"], ["router", "branch_b"], ["branch_a", "leaf_a"], ["branch_b", "leaf_b"]]
    else:
        topology = "small_graph"
        reason = "default_graph_for_mixed_agent_collaboration"
        edges = [["router", "worker"], ["worker", "verifier"], ["verifier", "router"]]
    if proof_required and ["verifier", "router"] not in edges:
        edges.append(["verifier", "router"])
    return {
        "ok": True,
        "schema": "nomad.topology_plan.v1",
        "generated_at": _iso_now(),
        "objective": objective,
        "topology": topology,
        "reason_code": reason,
        "graph_template": {
            "nodes_max": agents,
            "edges": edges,
            "message_policy": "minimal_digest_messages_only",
            "verifier_required": proof_required,
        },
        "token_policy": {
            "avoid_complete_graph_by_default": True,
            "sparse_when_cost_pressure_high": True,
            "source": "https://arxiv.org/abs/2410.11782",
        },
        "next": {
            "attach": _u(base_url, "/swarm/attach"),
            "lease": _u(base_url, "/swarm/workers/lease"),
            "handoff": _u(base_url, "/runtime/handoff"),
        },
        "machine_instruction": "compile_topology_from_objective_risk_cost_and_proof; do_not_use_static_team_shape",
    }
