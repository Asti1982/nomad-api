"""Non-biological recruitment field for agent runtimes.

This module keeps the old swarm routes compatible while exposing a stricter
machine surface: vectors, weights, TTLs, and retraction rules.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Dict, List


OBJECTIVE_TARGETS = {
    "settlement_capacity_builder": 0.42,
    "overmint_compressor": 0.22,
    "protocol_drift_scan": 0.14,
    "emergence_release_probe": 0.08,
    "proof_pressure_engine": 0.06,
    "payment_friction_scan": 0.04,
    "adversarial_contract_fuzzer": 0.025,
    "latency_anomaly_hunt": 0.015,
}

LANE_DEFINITIONS = [
    {
        "lane": "loop_runner",
        "objective": "settlement_capacity_builder",
        "required_vector": {"can_run_loop": 1.0},
        "capability_terms": ["objective_lease_execution", "transition_worker", "http_json", "local_process"],
        "next_path": "/swarm/workers/lease",
        "ttl_seconds": 90,
    },
    {
        "lane": "settlement_adapter",
        "objective": "settlement_capacity_builder",
        "required_vector": {"can_settle": 1.0, "can_verify": 0.5},
        "capability_terms": ["transition_settlement", "wallet_or_x402", "payment_friction_scan"],
        "next_path": "/swarm/join",
        "ttl_seconds": 120,
    },
    {
        "lane": "compressor",
        "objective": "overmint_compressor",
        "required_vector": {"can_compress": 1.0},
        "capability_terms": ["pattern_deduplication", "canonical_capability_hash", "vector_memory"],
        "next_path": "/swarm/join",
        "ttl_seconds": 120,
    },
    {
        "lane": "protocol_verifier",
        "objective": "protocol_drift_scan",
        "required_vector": {"can_verify": 1.0},
        "capability_terms": ["endpoint_probe", "schema_diff", "replay_check", "openclaw_gateway"],
        "next_path": "/swarm/join",
        "ttl_seconds": 90,
    },
    {
        "lane": "release_probe",
        "objective": "emergence_release_probe",
        "required_vector": {"can_run_loop": 0.75, "can_verify": 0.75},
        "capability_terms": ["objective_lease_execution", "replay_verifier_scoring"],
        "next_path": "/swarm/workers/lease",
        "ttl_seconds": 60,
    },
]


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _nested(payload: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, dict):
            return {}
        cur = cur.get(key)
    return cur if isinstance(cur, dict) else {}


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
    return max(low, min(high, value))


def _clean_text(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, *, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96].strip("_.:-") or fallback


def _as_caps(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        cap = _clean_id(item)
        if cap and cap not in out:
            out.append(cap)
    return out[:32]


def _state_inputs(
    *,
    worker_fleet: Dict[str, Any],
    machine_economy: Dict[str, Any],
    operational_release: Dict[str, Any],
) -> Dict[str, Any]:
    viability = _nested(machine_economy, "machine_viability")
    flows = _nested(machine_economy, "resource_flows")
    task_flow = _nested(flows, "service_tasks")
    module_flow = _nested(flows, "modules")
    product_flow = _nested(flows, "products")
    next_gate = operational_release.get("next_release_gate") if isinstance(operational_release.get("next_release_gate"), dict) else {}
    total_tasks = max(1, _int(task_flow.get("total"), 1))
    unpaid_delivered = _int(task_flow.get("unpaid_delivered"))
    awaiting_payment = _int(task_flow.get("awaiting_payment"))
    settlement_drag = _clamp((unpaid_delivered + awaiting_payment) / max(1.0, float(total_tasks)))
    carrying_score = _clamp(_num(viability.get("carrying_score")))
    overmint_pressure = _clamp(_num(module_flow.get("overmint_pressure")))
    release_capacity = _clamp(_num(operational_release.get("release_capacity")))
    known_workers = _int(worker_fleet.get("known_worker_count"))
    active_workers = _int(worker_fleet.get("active_worker_count"))
    active_leases = _int(worker_fleet.get("active_lease_count"))
    worker_gap = _clamp((12 - known_workers) / 12.0)
    field_strength = _clamp(
        0.34 * (1.0 - carrying_score)
        + 0.24 * settlement_drag
        + 0.20 * overmint_pressure
        + 0.14 * worker_gap
        + 0.08 * (1.0 - release_capacity)
    )
    return {
        "carrying_score": round(carrying_score, 4),
        "settlement_drag": round(settlement_drag, 4),
        "unpaid_delivered": unpaid_delivered,
        "awaiting_payment": awaiting_payment,
        "overmint_pressure": round(overmint_pressure, 4),
        "release_capacity": round(release_capacity, 4),
        "release_tier": _clean_text(operational_release.get("release_tier") or "unknown", 80),
        "next_release_gate": _clean_text(next_gate.get("id") or "", 80),
        "known_workers": known_workers,
        "active_workers": active_workers,
        "active_leases": active_leases,
        "worker_gap": round(worker_gap, 4),
        "machine_exchange_ready": _int(product_flow.get("machine_exchange_ready")),
        "field_strength": round(field_strength, 4),
    }


def _objective_rows(worker_fleet: Dict[str, Any], state: Dict[str, Any]) -> List[Dict[str, Any]]:
    counts = worker_fleet.get("objective_counts") if isinstance(worker_fleet.get("objective_counts"), dict) else {}
    targets = worker_fleet.get("objective_targets") if isinstance(worker_fleet.get("objective_targets"), dict) else {}
    active = max(1, _int(worker_fleet.get("active_lease_count")))
    rows: list[dict[str, Any]] = []
    all_targets = dict(OBJECTIVE_TARGETS)
    for objective, value in targets.items():
        if _clean_id(objective) and _clean_id(objective) not in all_targets:
            all_targets[_clean_id(objective)] = _num(value, 0.02)
    for objective, default_target in all_targets.items():
        target = _clamp(_num(targets.get(objective), default_target), 0.0, 0.75)
        observed = _int(counts.get(objective)) / active
        deficit = _clamp(target - observed)
        if objective == "settlement_capacity_builder":
            pressure = (
                0.40 * (1.0 - _num(state.get("carrying_score")))
                + 0.28 * _num(state.get("settlement_drag"))
                + 0.18 * _num(state.get("worker_gap"))
                + 0.14 * deficit
            )
        elif objective == "overmint_compressor":
            pressure = 0.62 * _num(state.get("overmint_pressure")) + 0.22 * deficit + 0.16 * _num(state.get("worker_gap"))
        elif objective == "protocol_drift_scan":
            pressure = 0.34 * (1.0 - _num(state.get("release_capacity"))) + 0.28 * deficit + 0.20 * _clamp(_num(state.get("active_leases")) / 8.0) + 0.18 * _num(state.get("worker_gap"))
        elif objective == "emergence_release_probe":
            settlement_gate_open = str(state.get("next_release_gate") or "") != "settlement_capacity"
            cap = 0.42 if settlement_gate_open else 0.22
            pressure = min(
                cap,
                0.24 * _num(state.get("release_capacity")) + 0.30 * deficit + 0.08 * _num(state.get("worker_gap")),
            )
        elif objective == "payment_friction_scan":
            pressure = 0.42 * _num(state.get("settlement_drag")) + 0.24 * deficit + 0.16 * (1.0 - _num(state.get("carrying_score")))
        else:
            pressure = 0.18 * deficit + 0.14 * _num(state.get("field_strength")) + 0.08 * _num(state.get("worker_gap"))
        rows.append(
            {
                "objective": objective,
                "target_share": round(target, 4),
                "active_share": round(observed, 4),
                "deficit": round(deficit, 4),
                "routing_weight": round(_clamp(pressure), 4),
            }
        )
    rows.sort(key=lambda item: (float(item.get("routing_weight") or 0.0), float(item.get("deficit") or 0.0)), reverse=True)
    return rows


def build_recruitment_gradient(
    *,
    base_url: str = "",
    worker_fleet: Dict[str, Any] | None = None,
    machine_economy: Dict[str, Any] | None = None,
    operational_release: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a machine-readable field that lets runtimes self-route by vector."""
    fleet = worker_fleet if isinstance(worker_fleet, dict) else {}
    economy = machine_economy if isinstance(machine_economy, dict) else {}
    release = operational_release if isinstance(operational_release, dict) else {}
    state = _state_inputs(worker_fleet=fleet, machine_economy=economy, operational_release=release)
    gradient = _objective_rows(fleet, state)
    weights = {str(item["objective"]): float(item["routing_weight"]) for item in gradient}
    top_objective = str((gradient[0] if gradient else {}).get("objective") or "settlement_capacity_builder")
    wanted_workers = max(0, min(64, round((12 - _num(state.get("known_workers"))) + 10 * _num(state.get("field_strength")))))

    runtime_lanes: list[dict[str, Any]] = []
    for lane in LANE_DEFINITIONS:
        objective = top_objective if lane.get("lane") == "loop_runner" else str(lane["objective"])
        runtime_lanes.append(
            {
                "lane": lane["lane"],
                "objective": objective,
                "routing_weight": round(_clamp(weights.get(objective, 0.0)), 4),
                "required_vector": lane["required_vector"],
                "capability_terms": lane["capability_terms"],
                "ttl_seconds": lane["ttl_seconds"],
                "next": _u(base_url, str(lane["next_path"])),
                "return_contract": [
                    "objective",
                    "proof_pressure",
                    "transition_quote_ok",
                    "transition_settle_ok",
                    "digest_or_verifier_trace",
                ],
            }
        )
    runtime_lanes.sort(key=lambda item: float(item.get("routing_weight") or 0.0), reverse=True)

    return {
        "mode": "nomad_recruitment_gradient",
        "schema": "nomad.recruitment_gradient.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "audience": "external_ai_agent_runtimes",
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "field_model": {
            "name": "capability_weighted_runtime_field",
            "vocabulary": "state_vector,basis_axis,routing_weight,ttl_seconds,retraction_rule",
            "anti_metaphor": "No organism language is required for runtime allocation.",
            "attach_threshold": 0.35,
        },
        "state_vector": {
            "ordered_axes": [
                "carrying_score",
                "settlement_drag",
                "overmint_pressure",
                "release_capacity",
                "worker_gap",
                "active_leases",
            ],
            "values": [
                state["carrying_score"],
                state["settlement_drag"],
                state["overmint_pressure"],
                state["release_capacity"],
                state["worker_gap"],
                state["active_leases"],
            ],
            **state,
        },
        "basis_axes": [
            {"axis": "settlement_drag", "positive_direction": "settlement_capacity_builder", "value": state["settlement_drag"]},
            {"axis": "overmint_pressure", "positive_direction": "overmint_compressor", "value": state["overmint_pressure"]},
            {"axis": "release_gap", "positive_direction": "protocol_drift_scan", "value": round(1.0 - _num(state["release_capacity"]), 4)},
            {"axis": "worker_gap", "positive_direction": "loop_runner", "value": state["worker_gap"]},
        ],
        "gradient": gradient,
        "runtime_lanes": runtime_lanes,
        "runtime_budget": {
            "policy": "increase_runtimes_only_where_weighted_routes_return_proof",
            "field_strength": state["field_strength"],
            "wanted_new_runtimes_now": wanted_workers,
            "known_workers": state["known_workers"],
            "active_workers": state["active_workers"],
            "active_leases": state["active_leases"],
            "emergence_release_share_cap": 0.08 if state.get("next_release_gate") == "settlement_capacity" else 0.18,
        },
        "attach_contract": {
            "schema": "nomad.runtime_attach_contract.v1",
            "post_url": _u(base_url, "/swarm/attach"),
            "request_schema": "nomad.runtime_attach_request.v1",
            "decision_schema": "nomad.runtime_attach_decision.v1",
            "input_vector": [
                "runtime",
                "capabilities",
                "capability_vector.can_run_loop",
                "capability_vector.can_verify",
                "capability_vector.can_compress",
                "capability_vector.can_settle",
                "runtime_signal.security_summary",
            ],
            "then": [
                "if attach=true and lane=loop_runner take lease_url",
                "if attach=true and lane!=loop_runner post join_url then take lease_url when objective is present",
                "if attach=false observe until ttl_seconds or a state_vector axis changes",
            ],
        },
        "routing_matrix": [
            {
                "capability_axis": "can_run_loop",
                "lane": "loop_runner",
                "objective": top_objective,
                "routing_weight": gradient[0]["routing_weight"] if gradient else 0.0,
            },
            {
                "capability_axis": "can_settle",
                "lane": "settlement_adapter",
                "objective": "settlement_capacity_builder",
                "routing_weight": round(weights.get("settlement_capacity_builder", 0.0), 4),
            },
            {
                "capability_axis": "can_compress",
                "lane": "compressor",
                "objective": "overmint_compressor",
                "routing_weight": round(weights.get("overmint_compressor", 0.0), 4),
            },
            {
                "capability_axis": "can_verify",
                "lane": "protocol_verifier",
                "objective": "protocol_drift_scan",
                "routing_weight": round(weights.get("protocol_drift_scan", 0.0), 4),
            },
        ],
        "ttl_policy": {
            "default_attach_ttl_seconds": 90,
            "max_lease_seconds": 600,
            "stale_signal_after_seconds": 270,
            "retry": "jittered_backoff_read_gradient_before_repost",
        },
        "retraction_rules": [
            {"id": "ttl_expired", "condition": "lease_or_attach_ttl_expired", "effect": "routing_weight_to_zero"},
            {"id": "missing_verifier", "condition": "no_digest_and_no_replay_trace", "effect": "completion_score_penalty"},
            {"id": "unsettled_delivery", "condition": "delivered_state_without_payment_or_public_good_cap", "effect": "settlement_lane_weight_increase"},
            {"id": "duplicate_without_canonicalization", "condition": "same_artifact_shape_repeated", "effect": "compressor_lane_weight_increase"},
            {"id": "external_side_effect_risk", "condition": "runtime_security_summary.critical_gt_zero", "effect": "side_effect_scope_local_only"},
        ],
        "measurement": {
            "primary_scalar": "field_strength",
            "release_scalar": "release_capacity",
            "capacity_scalar": "carrying_score",
            "required_after_action": ["completion_score", "proof_yield_per_minute", "settlement_signal", "digest_or_verifier_trace"],
        },
        "links": {
            "health": _u(base_url, "/health"),
            "agent_index": _u(base_url, "/.well-known/nomad-agent.json"),
            "runtime_capsule": _u(base_url, "/.well-known/nomad-runtime-capsule.json"),
            "gradient": _u(base_url, "/swarm/gradient"),
            "well_known_gradient": _u(base_url, "/.well-known/nomad-gradient.json"),
            "attach": _u(base_url, "/swarm/attach"),
            "handoff": _u(base_url, "/runtime/handoff"),
            "openclaw_bridge": _u(base_url, "/.well-known/openclaw-nomad-bridge.json"),
            "join": _u(base_url, "/swarm/join"),
            "worker_fleet": _u(base_url, "/swarm/workers"),
            "lease": _u(base_url, "/swarm/workers/lease"),
            "complete": _u(base_url, "/swarm/workers/complete"),
            "operational_release": _u(base_url, "/operational-release"),
        },
        "machine_instruction": "read_gradient_post_attach_take_weighted_lease_return_digest_then_recompute",
    }


def _runtime_signal(payload: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("runtime_signal", "openclaw_runtime_signal"):
        if isinstance(payload.get(key), dict):
            return payload[key]
    profile = payload.get("machine_profile") if isinstance(payload.get("machine_profile"), dict) else {}
    return profile.get("runtime_signal") if isinstance(profile.get("runtime_signal"), dict) else {}


def _capability_vector(payload: Dict[str, Any]) -> Dict[str, Any]:
    vector = payload.get("capability_vector") if isinstance(payload.get("capability_vector"), dict) else {}
    signal = _runtime_signal(payload)
    caps = _as_caps(payload.get("capabilities"))
    for cap in _as_caps(signal.get("capabilities")):
        if cap not in caps:
            caps.append(cap)
    profile = payload.get("machine_profile") if isinstance(payload.get("machine_profile"), dict) else {}
    runtime = _clean_id(payload.get("runtime") or profile.get("runtime") or ("openclaw" if signal.get("schema") == "nomad.openclaw_runtime_signal.v1" else "runtime"), fallback="runtime")
    security = signal.get("security_summary") if isinstance(signal.get("security_summary"), dict) else {}
    latency = _int(vector.get("latency_ms"), _int(signal.get("gateway_latency_ms")))
    cap_set = set(caps)
    can_run_loop = bool(vector.get("can_run_loop")) or bool(
        cap_set
        & {
            "objective_lease_execution",
            "transition_worker",
            "openclaw_runtime",
            "agent_protocols",
            "local_process",
            "http_json",
        }
    )
    can_verify = bool(vector.get("can_verify")) or bool(
        signal.get("gateway_reachable")
        or cap_set
        & {
            "endpoint_probe",
            "schema_diff",
            "replay_check",
            "openclaw_gateway",
            "replayable_control_plane",
            "security_audit_signal",
        }
    )
    can_compress = bool(vector.get("can_compress")) or bool(
        cap_set
        & {
            "overmint_compressor",
            "pattern_deduplication",
            "canonical_capability_hash",
            "vector_memory",
            "module_compression",
        }
    )
    can_settle = bool(vector.get("can_settle")) or bool(
        cap_set
        & {
            "transition_settlement",
            "settlement_capacity_builder",
            "wallet_or_x402",
            "payment_friction_scan",
            "paid_transition_audit",
        }
    )
    return {
        "runtime": runtime,
        "capabilities": caps[:32],
        "can_run_loop": can_run_loop,
        "can_verify": can_verify,
        "can_compress": can_compress,
        "can_settle": can_settle,
        "latency_ms": latency,
        "gateway_reachable": bool(signal.get("gateway_reachable")),
        "security_critical": _int(security.get("critical")),
        "security_warn": _int(security.get("warn")),
    }


def _required_score(required: Dict[str, Any], vector: Dict[str, Any]) -> float:
    total = sum(_num(value) for value in required.values()) or 1.0
    hit = 0.0
    for axis, weight in required.items():
        if bool(vector.get(axis)):
            hit += _num(weight)
    return _clamp(hit / total)


def attach_runtime_to_gradient(
    payload: Dict[str, Any],
    *,
    base_url: str = "",
    worker_fleet: Dict[str, Any] | None = None,
    machine_economy: Dict[str, Any] | None = None,
    operational_release: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a deterministic attach decision for an external runtime."""
    gradient = build_recruitment_gradient(
        base_url=base_url,
        worker_fleet=worker_fleet,
        machine_economy=machine_economy,
        operational_release=operational_release,
    )
    vector = _capability_vector(payload if isinstance(payload, dict) else {})
    agent_id = _clean_id(payload.get("agent_id") or payload.get("worker_id") or payload.get("node_name"), fallback=f"{vector['runtime']}.anonymous")
    gradient_rows = gradient.get("gradient") if isinstance(gradient.get("gradient"), list) else []
    weight_by_objective = {
        str(item.get("objective")): _num(item.get("routing_weight"))
        for item in gradient_rows
        if isinstance(item, dict)
    }
    top_objective = str((gradient_rows[0] if gradient_rows else {}).get("objective") or "settlement_capacity_builder")
    field_strength = _num(_nested(gradient, "state_vector").get("field_strength"))
    threshold = _num(_nested(gradient, "field_model").get("attach_threshold"), 0.35)

    lane_scores: list[dict[str, Any]] = []
    for lane in LANE_DEFINITIONS:
        lane_id = str(lane["lane"])
        lane_objective = top_objective if lane_id == "loop_runner" else str(lane["objective"])
        capability_score = _required_score(lane["required_vector"], vector)
        objective_weight = weight_by_objective.get(lane_objective, 0.0)
        score = _clamp(0.56 * objective_weight + 0.44 * capability_score)
        if capability_score <= 0.0:
            score = 0.0
        if lane_id == "release_probe" and _nested(gradient, "state_vector").get("next_release_gate") == "settlement_capacity":
            score = min(score, 0.32)
        lane_scores.append(
            {
                "lane": lane_id,
                "objective": lane_objective,
                "routing_weight": round(score, 4),
                "capability_score": round(capability_score, 4),
                "objective_weight": round(objective_weight, 4),
                "ttl_seconds": lane["ttl_seconds"],
            }
        )
    lane_scores.sort(key=lambda item: float(item.get("routing_weight") or 0.0), reverse=True)
    chosen = lane_scores[0] if lane_scores else {}
    has_any_capability = any(bool(vector.get(axis)) for axis in ("can_run_loop", "can_verify", "can_compress", "can_settle"))
    attach = bool(has_any_capability and float(chosen.get("routing_weight") or 0.0) >= min(threshold, max(0.18, field_strength * 0.5)))
    reason_codes: list[str] = []
    if not has_any_capability:
        reason_codes.append("capability_vector_empty")
    if field_strength >= threshold:
        reason_codes.append("field_strength_above_threshold")
    if _int(_nested(gradient, "runtime_budget").get("wanted_new_runtimes_now")) > 0:
        reason_codes.append("runtime_gap_positive")
    if vector.get("security_critical"):
        reason_codes.append("external_side_effect_scope_reduced")
    if attach:
        reason_codes.append(f"lane_{chosen.get('lane')}_max_weight")
    else:
        reason_codes.append("observe_until_gradient_changes")

    constraints = ["no_secrets", "bounded_json_only", "no_human_impersonation", "no_transcript_export"]
    side_effect_scope = "nomad_lease_only"
    if vector.get("security_critical"):
        constraints.append("security_audit_before_external_side_effects")
        side_effect_scope = "local_only"
    elif not vector.get("gateway_reachable") and vector.get("runtime") == "openclaw":
        constraints.append("openclaw_gateway_unverified")

    lane = str(chosen.get("lane") or "observe") if attach else "observe"
    objective = str(chosen.get("objective") or "") if attach else ""
    return {
        "ok": True,
        "schema": "nomad.runtime_attach_decision.v1",
        "generated_at": _iso_now(),
        "agent_id": agent_id,
        "runtime": vector["runtime"],
        "attach": attach,
        "lane": lane,
        "objective": objective,
        "routing_weight": round(float(chosen.get("routing_weight") or 0.0), 4),
        "attach_threshold": round(threshold, 4),
        "ttl_seconds": _int(chosen.get("ttl_seconds"), 90) if attach else 90,
        "side_effect_scope": side_effect_scope,
        "constraints": constraints,
        "capability_vector": {
            "can_run_loop": bool(vector.get("can_run_loop")),
            "can_verify": bool(vector.get("can_verify")),
            "can_compress": bool(vector.get("can_compress")),
            "can_settle": bool(vector.get("can_settle")),
            "latency_ms": _int(vector.get("latency_ms")),
        },
        "reason_codes": reason_codes,
        "lane_scores": lane_scores[:6],
        "lease_url": _u(base_url, "/swarm/workers/lease"),
        "join_url": _u(base_url, "/swarm/join"),
        "complete_url": _u(base_url, "/swarm/workers/complete"),
        "lease_payload_hint": {
            "agent_id": agent_id,
            "known_objectives": [objective] if objective else [],
            "proposed_objective": objective,
            "capabilities": vector.get("capabilities") or [],
        },
        "join_payload_hint": {
            "agent_id": agent_id,
            "capabilities": vector.get("capabilities") or [],
            "preferred_role": lane,
            "request": "runtime_attach_decision_accept",
        },
        "required_report_fields": [
            "machine_objective",
            "proof_pressure.proof_yield_per_minute",
            "transition_quote_ok",
            "transition_settle_ok",
            "digest_or_verifier_trace",
        ],
        "retraction_rule": "ttl_expired_or_missing_verifier_or_external_side_effect_risk",
        "gradient_digest": {
            "field_strength": field_strength,
            "top_objective": top_objective,
            "wanted_new_runtimes_now": _int(_nested(gradient, "runtime_budget").get("wanted_new_runtimes_now")),
        },
    }
