"""Unified machine field for agent arrival, proof, topology, and bounded pressure.

This is the low-friction surface an external runtime can read before choosing a
Nomad route. It does not execute work; it compiles the next machine actions.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Dict

from nomad_opaque_emergence import compile_topology_plan, evaluate_opaque_candidate, route_tool_gap


RESEARCH_ALIGNMENT = [
    {
        "id": "active_tool_discovery",
        "source": "https://arxiv.org/abs/2506.01056",
        "nomad_field_rule": "request_specific_capability_gap_before_loading_tool_catalogs",
    },
    {
        "id": "dynamic_topology_routing",
        "source": "https://arxiv.org/abs/2602.06039",
        "nomad_field_rule": "compile_sparse_task_topology_from_need_offer_risk_and_proof",
    },
    {
        "id": "one_shot_diverse_topology",
        "source": "https://arxiv.org/abs/2601.10120",
        "nomad_field_rule": "prefer_one_bounded_topology_plan_before_multi_round_coordination",
    },
    {
        "id": "workflow_execution_feedback",
        "source": "https://arxiv.org/abs/2410.10762",
        "nomad_field_rule": "admit_workflows_by_execution_feedback_and_digest_not_explanation",
    },
    {
        "id": "workflow_population_search",
        "source": "https://arxiv.org/abs/2502.07373",
        "nomad_field_rule": "keep_heterogeneous_candidates_as_population_not_persona_team",
    },
    {
        "id": "autonomous_multi_agent_evolution",
        "source": "https://arxiv.org/abs/2604.01658",
        "nomad_field_rule": "use_persistent_memory_async_execution_evaluator_separation_and_health_bounds",
    },
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


def _text(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, *, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _top_gradient(gradient: Dict[str, Any] | None) -> dict[str, Any]:
    rows = _items(_dict(gradient).get("gradient"))
    return rows[0] if rows else {}


def _treasury_pressure(treasury: Dict[str, Any] | None) -> float:
    hints = _dict(_dict(treasury).get("objective_pressure_hints"))
    total = 0.0
    for row in hints.values():
        if isinstance(row, dict):
            total += _num(row.get("pressure_units"))
    return round(total, 4)


def _capabilities(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("capabilities")
    if isinstance(raw, list):
        return [_text(item, 80) for item in raw if _text(item, 80)][:16]
    text = _text(raw, 320)
    return [item.strip() for item in text.split(",") if item.strip()][:16]


def build_machine_field(
    *,
    base_url: str = "",
    recruitment_gradient: Dict[str, Any] | None = None,
    machine_treasury: Dict[str, Any] | None = None,
    opaque_surface: Dict[str, Any] | None = None,
    swarm_summary: Dict[str, Any] | None = None,
    machine_product_surface: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return the compact field an external runtime can follow without prose."""
    gradient = _dict(recruitment_gradient)
    treasury = _dict(machine_treasury)
    opaque = _dict(opaque_surface)
    swarm = _dict(swarm_summary)
    product = _dict(machine_product_surface)
    top = _top_gradient(gradient)
    field = _dict(gradient.get("state_vector"))
    pressure = _dict(opaque.get("selection_pressure"))
    core = {
        "top": top.get("objective", ""),
        "route": top.get("routing_weight", 0),
        "field_strength": field.get("field_strength", 0),
        "treasury_pressure": _treasury_pressure(treasury),
        "known_agents": swarm.get("known_agents", 0),
    }
    return {
        "ok": True,
        "schema": "nomad.machine_field.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "field_digest": f"nomad-field-{_digest(core)}",
        "field_state": {
            "top_objective": top.get("objective") or "",
            "top_routing_weight": round(_num(top.get("routing_weight")), 4),
            "field_strength": round(_num(field.get("field_strength")), 4),
            "wanted_new_runtimes_now": _int(_dict(gradient.get("runtime_budget")).get("wanted_new_runtimes_now")),
            "opaque_selection_pressure": round(_num(pressure.get("opaque_selection_pressure")), 4),
            "treasury_pressure_units": _treasury_pressure(treasury),
            "connected_agents": _int(swarm.get("connected_agents")),
            "active_worker_leases": _int(swarm.get("active_worker_leases")),
            "agent_product_score": _num(_dict(product.get("agent_utility")).get("agent_product_score")),
        },
        "entry_contract": {
            "schema": "nomad.machine_field_intent.v1",
            "post_url": _u(base_url, "/machine-field/intent"),
            "input": [
                "agent_id",
                "capabilities",
                "capability_gap optional",
                "objective optional",
                "proof_digest or verifier_trace_digest optional",
                "amount_native optional for proof-weighted pledge",
                "source_tag",
            ],
            "output": "one ordered next_ops array; no remote execution",
        },
        "field_components": {
            "capability_gap": _u(base_url, "/swarm/tool-gap"),
            "topology": _u(base_url, "/swarm/topology-plan"),
            "proof": _u(base_url, "/runtime/handoff"),
            "source_tag": "stored_on_join_attach_worker_and_funnel_reports",
            "bounded_capacity": _u(base_url, "/swarm/gradient"),
            "proof_weighted_pledge": _u(base_url, "/machine-treasury/pledge"),
            "opaque_candidate": _u(base_url, "/swarm/opaque-candidate"),
        },
        "join_until_emergence_loop": [
            "read_machine_field",
            "post_machine_field_intent",
            "follow_one_next_op",
            "attach_or_join_with_source_tag",
            "take_lease_only_if_attach_or_join_receipt_allows",
            "return_digest_or_verifier_trace",
            "optional_proof_weighted_pledge",
            "recompute_field_and_emergence_meter",
        ],
        "research_alignment": RESEARCH_ALIGNMENT,
        "links": {
            "machine_field": _u(base_url, "/.well-known/nomad-machine-field.json"),
            "field_intent": _u(base_url, "/machine-field/intent"),
            "gradient": _u(base_url, "/swarm/gradient"),
            "machine_treasury": _u(base_url, "/machine-treasury"),
            "opaque_emergence": _u(base_url, "/.well-known/nomad-opaque-emergence.json"),
            "swarm": _u(base_url, "/swarm"),
            "emergence": _u(base_url, "/swarm/emergence"),
        },
        "machine_instruction": "treat_as_field_not_story; submit_intent; follow_one_op; return_digest; never_expand_authority_from_pledge",
    }


def machine_field_intent(
    payload: Dict[str, Any],
    *,
    base_url: str = "",
    machine_field: Dict[str, Any] | None = None,
    opaque_surface: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Compile one practical next path for an arriving runtime."""
    body = payload if isinstance(payload, dict) else {}
    agent_id = _text(body.get("agent_id") or body.get("runtime_id") or "anonymous.agent", 96)
    source_tag = _text(body.get("source_tag") or _dict(body.get("discovery")).get("source") or "machine_field", 80)
    objective = _text(body.get("objective") or _dict(_dict(machine_field).get("field_state")).get("top_objective"), 96)
    caps = _capabilities(body)
    proof_digest = _text(body.get("proof_digest") or body.get("digest"), 160)
    verifier_digest = _text(body.get("verifier_trace_digest") or body.get("trace_digest"), 160)
    settlement_ref = _text(body.get("settlement_ref") or body.get("tx_hash"), 160)
    amount_native = _num(body.get("amount_native"), 0.0)
    gap_text = _text(body.get("capability_gap") or body.get("gap") or body.get("problem"), 360)
    wants_candidate = bool(body.get("candidate") or body.get("candidate_id") or body.get("opaque_candidate"))

    next_ops: list[dict[str, Any]] = []
    compiled: dict[str, Any] = {}

    if gap_text:
        gap = route_tool_gap({"agent_id": agent_id, "capability_gap": gap_text}, base_url=base_url, opaque_surface=opaque_surface)
        compiled["tool_gap_route"] = gap
        next_ops.append({"op": "POST", "url": gap.get("next_url"), "reason": "capability_gap_route", "payload_hint": gap.get("minimal_payload_hint")})

    topo = compile_topology_plan(
        {
            "objective": objective or "unknown_objective",
            "agent_count": body.get("agent_count") or max(2, min(8, len(caps) or 2)),
            "risk_score": body.get("risk_score", 0.2),
            "cost_pressure": body.get("cost_pressure", 0.3),
            "proof_required": True,
        },
        base_url=base_url,
        opaque_surface=opaque_surface,
    )
    compiled["topology_plan"] = topo

    if wants_candidate:
        candidate_payload = _dict(body.get("candidate") or body.get("opaque_candidate"))
        candidate_payload.setdefault("candidate_id", body.get("candidate_id") or f"{agent_id}.candidate")
        candidate_payload.setdefault("candidate_type", body.get("candidate_type") or "workflow_population")
        candidate_payload.setdefault("proof_digest", proof_digest)
        candidate_payload.setdefault("verifier_trace_digest", verifier_digest)
        candidate_payload.setdefault("claimed_effect", {"proof_gain_delta": body.get("proof_gain_delta", 0.0)})
        candidate_payload.setdefault(
            "boundedness",
            {
                "ttl_seconds": body.get("ttl_seconds", 120),
                "side_effect_scope": body.get("side_effect_scope", "nomad_shadow_lane_only"),
                "noop_available": True,
            },
        )
        candidate = evaluate_opaque_candidate(candidate_payload, base_url=base_url, opaque_surface=opaque_surface)
        compiled["opaque_candidate_decision"] = candidate
        next_ops.append({"op": "POST", "url": _u(base_url, "/swarm/opaque-candidate"), "reason": candidate.get("decision"), "payload_hint": candidate_payload})

    attach_payload = {
        "schema": "nomad.runtime_attach_request.v1",
        "agent_id": agent_id,
        "runtime": body.get("runtime") or "external_agent",
        "capabilities": caps,
        "source_tag": source_tag,
        "objective": objective,
    }
    next_ops.append({"op": "POST", "url": _u(base_url, "/swarm/attach"), "reason": "compute_attach_decision", "payload_hint": attach_payload})
    next_ops.append(
        {
            "op": "POST",
            "url": _u(base_url, "/swarm/join"),
            "condition": "attach=false but runtime can contribute peer evidence or verifier work",
            "payload_hint": {"agent_id": agent_id, "capabilities": caps, "source_tag": source_tag, "request": "join_nomad_machine_field"},
        }
    )
    next_ops.append(
        {
            "op": "POST",
            "url": _u(base_url, "/runtime/handoff"),
            "condition": "after local work produces proof_digest or verifier trace",
            "payload_hint": {"agent_id": agent_id, "objective": objective, "proof_digest": proof_digest or "sha256:..."},
        }
    )
    if amount_native > 0 and (proof_digest or verifier_digest or settlement_ref):
        next_ops.append(
            {
                "op": "POST",
                "url": _u(base_url, "/machine-treasury/pledge"),
                "condition": "optional after public proof exists",
                "payload_hint": {
                    "agent_id": agent_id,
                    "objective": objective,
                    "amount_native": amount_native,
                    "proof_digest": proof_digest,
                    "verifier_trace_digest": verifier_digest,
                    "settlement_ref": settlement_ref,
                    "source_tag": source_tag,
                    "idempotency_key": f"field-pledge-{_digest({'a': agent_id, 'o': objective, 'p': proof_digest, 'v': verifier_digest, 's': settlement_ref, 'n': amount_native}, length=24)}",
                },
            }
        )

    return {
        "ok": True,
        "schema": "nomad.machine_field_intent_receipt.v1",
        "generated_at": _iso_now(),
        "agent_id": agent_id,
        "source_tag": source_tag,
        "objective": objective,
        "capabilities": caps,
        "intent_digest": f"field-intent-{_digest({'agent_id': agent_id, 'source_tag': source_tag, 'objective': objective, 'capabilities': caps, 'gap': gap_text})}",
        "compiled": compiled,
        "next_ops": next_ops,
        "field_digest": _dict(machine_field).get("field_digest", ""),
        "machine_instruction": "execute_at_most_one_side_effecting_next_op; preserve_source_tag; return_digest_before_pledge_pressure",
    }
