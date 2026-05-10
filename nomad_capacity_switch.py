"""Agent-first capacity switch surface for swarm fallback routing."""

from __future__ import annotations

from typing import Any


def _limits() -> dict[str, Any]:
    return {
        "rate_limit": {"requests": 30, "window_seconds": 60},
        "queue": {"max_pending": 128},
        "ttl_seconds": 180,
    }


def build_capacity_switch_surface(
    *,
    base_url: str,
    economics: dict[str, Any] | None = None,
    worker_catalog: dict[str, Any] | None = None,
    microtask_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    eco = economics if isinstance(economics, dict) else {}
    catalog = worker_catalog if isinstance(worker_catalog, dict) else {}
    metrics = microtask_metrics if isinstance(microtask_metrics, dict) else {}
    lane_rows = metrics.get("lane_metrics") if isinstance(metrics.get("lane_metrics"), list) else []
    top_lane = lane_rows[0] if lane_rows and isinstance(lane_rows[0], dict) else {}
    recommended_lane = str(top_lane.get("lane_id") or "endpoint_health_proof").strip() or "endpoint_health_proof"
    return {
        "ok": True,
        "schema": "nomad.capacity_switch_surface.v1",
        "decision_mode": "agent_autonomous_failover",
        "switch_url": f"{base_url.rstrip('/')}/swarm/capacity-switch",
        "fallback_paths": {
            "idle_intent": f"{base_url.rstrip('/')}/swarm/idle-intent",
            "microtask_submit": f"{base_url.rstrip('/')}/swarm/microtask/submit",
            "lease": f"{base_url.rstrip('/')}/swarm/workers/lease",
        },
        "recommended_lane_id": recommended_lane,
        "microtask_lane_count": len(catalog.get("microtask_lanes") or []),
        "economics_signal": {
            "real_cashflow_24h_eur": float(eco.get("real_cashflow_24h_eur") or 0.0),
            "go_no_go_state": str((eco.get("go_no_go") or {}).get("state") or "unknown"),
        },
        "machine_instruction": "when_local_budget_or_capacity_exhausted_submit_capacity_switch_request",
        "next": [
            {"rel": "switch_request", "href": f"{base_url.rstrip('/')}/swarm/capacity-switch", "method": "POST"},
            {"rel": "idle_intent", "href": f"{base_url.rstrip('/')}/swarm/idle-intent", "method": "POST"},
            {"rel": "microtask_submit", "href": f"{base_url.rstrip('/')}/swarm/microtask/submit", "method": "POST"},
        ],
        "limits": _limits(),
    }


def route_capacity_switch(
    payload: dict[str, Any],
    *,
    base_url: str,
    capacity_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    surface = capacity_surface if isinstance(capacity_surface, dict) else build_capacity_switch_surface(base_url=base_url)
    token_balance = float(body.get("local_token_balance") or 0.0)
    utilization = float(body.get("local_capacity_utilization") or 1.0)
    target = str(body.get("objective") or "settlement_capacity_builder").strip() or "settlement_capacity_builder"
    depleted = token_balance <= float(body.get("min_token_threshold") or 0.0)
    saturated = utilization >= float(body.get("max_utilization_threshold") or 0.92)
    should_switch = depleted or saturated or bool(body.get("force_switch"))
    route = "observe_local" if not should_switch else "swarm_microtask_lane"
    machine_instruction = "continue_local_execution" if route == "observe_local" else "switch_execution_to_swarm_lane"
    return {
        "ok": True,
        "schema": "nomad.capacity_switch_receipt.v1",
        "switch": should_switch,
        "route": route,
        "objective": target,
        "reason_codes": [
            code
            for code, active in (
                ("token_budget_depleted", depleted),
                ("local_capacity_saturated", saturated),
                ("force_switch", bool(body.get("force_switch"))),
            )
            if active
        ]
        or ["no_switch_trigger"],
        "fallback_target": {
            "lane_id": str(body.get("preferred_lane_id") or surface.get("recommended_lane_id") or "endpoint_health_proof"),
            "submit_url": str((surface.get("fallback_paths") or {}).get("microtask_submit") or ""),
            "idle_intent_url": str((surface.get("fallback_paths") or {}).get("idle_intent") or ""),
            "lease_url": str((surface.get("fallback_paths") or {}).get("lease") or ""),
        },
        "machine_instruction": machine_instruction,
        "next": [
            {
                "rel": "submit_microtask",
                "href": str((surface.get("fallback_paths") or {}).get("microtask_submit") or ""),
                "method": "POST",
                "when": "switch==true",
            },
            {
                "rel": "idle_intent",
                "href": str((surface.get("fallback_paths") or {}).get("idle_intent") or ""),
                "method": "POST",
                "when": "switch==true",
            },
        ],
        "limits": _limits(),
    }

