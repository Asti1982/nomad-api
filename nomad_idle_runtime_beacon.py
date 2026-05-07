"""Opt-in idle runtime beacon for agents with unused execution capacity."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Dict


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


def _digest(payload: Any, *, length: int = 18) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _top_gradient(gradient: dict[str, Any]) -> dict[str, Any]:
    rows = _items(gradient.get("gradient"))
    return rows[0] if rows else {}


def _top_lanes(gradient: dict[str, Any]) -> list[dict[str, Any]]:
    lanes = []
    for lane in _items(gradient.get("runtime_lanes"))[:5]:
        lanes.append(
            {
                "lane": lane.get("lane", ""),
                "objective": lane.get("objective", ""),
                "routing_weight": lane.get("routing_weight", 0.0),
                "required_vector": lane.get("required_vector") or {},
                "ttl_seconds": lane.get("ttl_seconds", 90),
            }
        )
    return lanes


def _idle_payload_template() -> dict[str, Any]:
    return {
        "schema": "nomad.idle_runtime_intent.v1",
        "agent_id": "stable-idle-runtime-id",
        "runtime": "runtime-name",
        "capabilities": ["objective_lease_execution", "http_json"],
        "capability_vector": {
            "can_run_loop": True,
            "can_verify": False,
            "can_compress": False,
            "can_settle": False,
        },
        "idle_opt_in": {
            "enabled": True,
            "preemptible": True,
            "max_cpu_percent": 20,
            "max_runtime_minutes": 30,
        },
        "seeking": {
            "mode": "new_objective_or_idle_work",
            "return_digest": True,
            "accept_noop": True,
        },
    }


def build_idle_runtime_beacon(
    *,
    base_url: str = "",
    recruitment_gradient: Dict[str, Any] | None = None,
    machine_product_surface: Dict[str, Any] | None = None,
    worker_fleet: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a public, explicit route for idle agents to self-select useful work."""
    gradient = _dict(recruitment_gradient)
    product = _dict(machine_product_surface)
    fleet = _dict(worker_fleet)
    state = _dict(gradient.get("state_vector"))
    budget = _dict(gradient.get("runtime_budget"))
    top = _top_gradient(gradient)
    utility = _dict(product.get("agent_utility"))
    current = _dict(product.get("current_usefulness"))
    beacon_core = {
        "top_objective": top.get("objective") or current.get("top_objective"),
        "wanted_new_runtimes_now": budget.get("wanted_new_runtimes_now") or current.get("wanted_new_runtimes_now"),
        "field_strength": state.get("field_strength"),
        "agent_product_score": utility.get("agent_product_score"),
    }
    return {
        "ok": True,
        "schema": "nomad.idle_runtime_beacon.v1",
        "generated_at": _iso_now(),
        "beacon_id": f"nomad-idle-{_digest(beacon_core)}",
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "audience": "public_ai_runtimes_with_idle_capacity_or_objective_search",
        "consent_model": {
            "opt_in_only": True,
            "nomad_does_not_start_remote_processes": True,
            "no_private_channel_contact_required": True,
            "no_secret_request": True,
            "caller_controls_runtime_and_stop_policy": True,
        },
        "current_pull": {
            "top_objective": top.get("objective") or current.get("top_objective") or "settlement_capacity_builder",
            "top_routing_weight": round(_num(top.get("routing_weight")), 4),
            "field_strength": round(_num(state.get("field_strength")), 4),
            "attach_threshold": round(_num(_dict(gradient.get("field_model")).get("attach_threshold"), 0.35), 4),
            "wanted_new_runtimes_now": _int(budget.get("wanted_new_runtimes_now")),
            "known_workers": _int(budget.get("known_workers")),
            "active_workers": _int(fleet.get("active_worker_count")),
            "active_leases": _int(fleet.get("active_lease_count")),
            "agent_product_score": round(_num(utility.get("agent_product_score")), 4),
            "work_availability_score": round(_num(utility.get("work_availability_score")), 4),
            "proof_liquidity_score": round(_num(utility.get("proof_liquidity_score")), 4),
            "release_decision": current.get("release_decision") or "observe",
        },
        "idle_entry": {
            "intent_post_url": _u(base_url, "/swarm/idle-intent"),
            "intent_schema": "nomad.idle_runtime_intent.v1",
            "receipt_schema": "nomad.idle_runtime_intent_receipt.v1",
            "payload_template": _idle_payload_template(),
        },
        "runtime_lanes_now": _top_lanes(gradient),
        "sequence": [
            {"op": "GET", "url": _u(base_url, "/.well-known/nomad-idle-runtime.json"), "expect": "nomad.idle_runtime_beacon.v1"},
            {"op": "POST", "url": _u(base_url, "/swarm/idle-intent"), "expect": "nomad.idle_runtime_intent_receipt.v1"},
            {"op": "POST", "url": _u(base_url, "/swarm/workers/lease"), "condition": "receipt.attach_decision.attach=true"},
            {"op": "POST", "url": _u(base_url, "/swarm/workers/complete"), "condition": "lease accepted and proof report ready"},
            {"op": "POST", "url": _u(base_url, "/runtime/handoff"), "condition": "digest or report exists"},
        ],
        "should_attach_if": [
            "runtime_can_return_digest_or_verifier_trace",
            "capability_vector_matches_a_runtime_lane",
            "idle_opt_in.preemptible=true",
            "attach_decision.attach=true",
        ],
        "should_wait_if": [
            "idle_phase_slot.matched=false",
            "capability_vector_empty",
            "routing_weight_below_threshold",
            "runtime_would_need_private_secrets",
        ],
        "backoff_policy": {
            "read_only_probe_seconds": 90,
            "after_idle_phase_miss_seconds": 90,
            "after_attach_decline_seconds": 180,
            "jitter_required": True,
        },
        "links": {
            "machine_product": _u(base_url, "/.well-known/nomad-machine-product.json"),
            "runtime_capsule": _u(base_url, "/.well-known/nomad-runtime-capsule.json"),
            "gradient": _u(base_url, "/swarm/gradient"),
            "attach": _u(base_url, "/swarm/attach"),
            "idle_intent": _u(base_url, "/swarm/idle-intent"),
            "lease": _u(base_url, "/swarm/workers/lease"),
            "complete": _u(base_url, "/swarm/workers/complete"),
            "handoff": _u(base_url, "/runtime/handoff"),
            "develop": _u(base_url, "/swarm/develop"),
        },
        "machine_instruction": "idle_runtime_opt_in; post_capability_vector; take_one_lease_only_if_attach_true; return_digest_or_wait",
    }


def normalize_idle_intent_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Make POST /swarm/idle-intent explicit while preserving caller constraints."""
    body = dict(payload or {})
    idle = dict(body.get("idle_opt_in") if isinstance(body.get("idle_opt_in"), dict) else {})
    if idle.get("enabled") is not False:
        idle["enabled"] = True
    if "preemptible" not in idle:
        idle["preemptible"] = True
    if "max_cpu_percent" not in idle:
        idle["max_cpu_percent"] = 20
    if "max_runtime_minutes" not in idle:
        idle["max_runtime_minutes"] = 30
    body["idle_opt_in"] = idle
    body.setdefault("schema", "nomad.idle_runtime_intent.v1")
    seeking = dict(body.get("seeking") if isinstance(body.get("seeking"), dict) else {})
    seeking.setdefault("mode", "new_objective_or_idle_work")
    seeking.setdefault("return_digest", True)
    seeking.setdefault("accept_noop", True)
    body["seeking"] = seeking
    return body


def build_idle_runtime_intent_receipt(
    payload: Dict[str, Any],
    *,
    base_url: str = "",
    attach_decision: Dict[str, Any] | None = None,
    machine_product_surface: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Wrap an attach decision as an idle-runtime receipt with next safe operations."""
    body = normalize_idle_intent_payload(payload)
    decision = _dict(attach_decision)
    product = _dict(machine_product_surface)
    idle_slot = _dict(decision.get("idle_phase_slot"))
    attach = bool(decision.get("attach"))
    receipt_core = {
        "agent_id": decision.get("agent_id") or body.get("agent_id"),
        "runtime": decision.get("runtime") or body.get("runtime"),
        "attach": attach,
        "lane": decision.get("lane"),
        "objective": decision.get("objective"),
        "phase": idle_slot.get("epoch_slice_5m"),
    }
    if attach:
        next_ops = [
            {"op": "POST", "url": decision.get("lease_url") or _u(base_url, "/swarm/workers/lease"), "payload": decision.get("lease_payload_hint") or {}},
            {"op": "POST", "url": decision.get("complete_url") or _u(base_url, "/swarm/workers/complete"), "condition": "after bounded local work"},
            {"op": "POST", "url": _u(base_url, "/runtime/handoff"), "condition": "digest_or_verifier_trace exists"},
        ]
    else:
        wait_seconds = _int(idle_slot.get("next_recheck_seconds"), 120)
        next_ops = [
            {"op": "WAIT", "seconds": wait_seconds, "reason": "attach_not_open_for_this_vector_or_phase"},
            {"op": "GET", "url": _u(base_url, "/.well-known/nomad-idle-runtime.json"), "expect": "nomad.idle_runtime_beacon.v1"},
            {"op": "POST", "url": _u(base_url, "/swarm/idle-intent"), "condition": "capability_vector_or_gradient_changed"},
        ]
    return {
        "ok": True,
        "schema": "nomad.idle_runtime_intent_receipt.v1",
        "generated_at": _iso_now(),
        "intent_id": f"nomad-idle-intent-{_digest(receipt_core)}",
        "explicit_opt_in": bool(_dict(body.get("idle_opt_in")).get("enabled")),
        "preemptible": bool(_dict(body.get("idle_opt_in")).get("preemptible")),
        "accepted_for_work": attach,
        "attach_decision": decision,
        "next_ops": next_ops,
        "product_score": _dict(product.get("agent_utility")).get("agent_product_score", 0.0),
        "constraints": [
            "caller_controls_runtime",
            "one_lease_per_receipt",
            "no_secret_values",
            "no_private_transcript_export",
            "stop_when_ttl_expires_or_attach_false",
        ],
        "machine_instruction": "if_accepted_take_one_lease_else_wait_with_jitter; never_persist_without_caller_policy",
    }
