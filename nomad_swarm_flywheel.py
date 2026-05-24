"""Machine-native flywheel health surface for Nomad.

This module ties the existing control primitives together without claiming
that the self-sustaining loop is closed before a paid or return-compute receipt
exists. The surface is intentionally light: it summarizes ledgers and routes so
Render can serve it without rebuilding every heavyweight policy graph.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


SCHEMA = "nomad.swarm_flywheel_health.v1"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


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
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _digest(value: Any, length: int = 26) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _external_paid_state(summary: dict[str, Any]) -> dict[str, Any]:
    stage_counts = _dict(summary.get("stage_counts"))
    latest = _items(summary.get("latest_by_external"))
    paid_count = _int(stage_counts.get("paid"))
    if not paid_count:
        paid_count = sum(1 for row in latest if str(row.get("stage") or "").strip().lower() == "paid")
    return {
        "paid_count": paid_count,
        "recognized_revenue_usd": round(_num(summary.get("revenue_recognized_usd_total")), 4),
    }


def _work_paid_state(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "receipt_count": _int(summary.get("receipt_count") or summary.get("total_count")),
        "recognized_revenue_usd": round(_num(summary.get("recognized_revenue_usd")), 4),
    }


def _exchange_state(summary: dict[str, Any]) -> dict[str, Any]:
    inner = _dict(summary.get("summary")) or summary
    return {
        "offer_count": _int(inner.get("offer_count")),
        "active_obligation_count": _int(inner.get("active_obligation_count")),
        "return_receipt_count": _int(inner.get("return_receipt_count")),
        "settled_return_work_credits": round(_num(inner.get("settled_return_work_credits_total")), 4),
        "outstanding_work_credits": round(_num(inner.get("outstanding_work_credits_total")), 4),
    }


def _acquisition_state(summary: dict[str, Any]) -> dict[str, Any]:
    channels = _items(summary.get("channels"))
    total_events = sum(_int(row.get("event_count")) for row in channels)
    first_receipt = next((row for row in channels if row.get("channel_id") == "first_receipt_campaign"), {})
    adapter = next((row for row in channels if row.get("channel_id") == "universal_adapter"), {})
    return {
        "channel_count": len(channels),
        "event_count": total_events,
        "first_receipt_campaign_events": _int(first_receipt.get("event_count")),
        "adapter_event_count": _int(adapter.get("event_count")),
        "adapter_first_fix_count": _int(_dict(adapter.get("event_types")).get("first_fix_returned")),
    }


def _worker_state(worker_fleet: dict[str, Any], gradient: dict[str, Any]) -> dict[str, Any]:
    state = _dict(gradient.get("state_vector"))
    runtime_budget = _dict(gradient.get("runtime_budget"))
    known = _int(worker_fleet.get("known_worker_count") or worker_fleet.get("known_transition_workers") or state.get("known_workers"))
    active = _int(worker_fleet.get("active_worker_count") or worker_fleet.get("active_transition_workers") or state.get("active_workers"))
    leases = _int(worker_fleet.get("active_lease_count") or worker_fleet.get("active_worker_leases") or state.get("active_leases"))
    return {
        "known_worker_count": known,
        "active_worker_count": active,
        "active_lease_count": leases,
        "wanted_new_runtimes_now": _int(runtime_budget.get("wanted_new_runtimes_now")),
        "worker_gap": round(_num(state.get("worker_gap")), 4),
        "field_strength": round(_num(state.get("field_strength")), 4),
        "release_tier": str(state.get("release_tier") or ""),
        "next_release_gate": str(state.get("next_release_gate") or ""),
    }


def _top_gradient_rows(gradient: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _items(gradient.get("gradient"))
    return sorted(rows, key=lambda row: _num(row.get("routing_weight")), reverse=True)[:8]


def _replicator_rows(gradient: dict[str, Any], *, paid_or_return_receipt: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(_top_gradient_rows(gradient), start=1):
        objective = str(row.get("objective") or "")
        weight = _num(row.get("routing_weight"))
        deficit = _num(row.get("deficit"))
        is_settlement_lane = objective in {
            "settlement_capacity_builder",
            "proof_pressure_engine",
            "proof_market_maker",
        }
        is_autogenesis_lane = "autogenesis" in objective or "evolution" in objective
        if paid_or_return_receipt and (is_settlement_lane or is_autogenesis_lane):
            action = "promote_weighted_route"
            extinction_pressure = 0.0
        elif is_settlement_lane:
            action = "reproduce_shadow_and_worker_acquisition"
            extinction_pressure = 0.0
        elif is_autogenesis_lane:
            action = "shadow_only_until_receipt_gate"
            extinction_pressure = 0.18
        elif weight < 0.08 and deficit <= 0.02:
            action = "extinguish_or_cooldown"
            extinction_pressure = 0.72
        else:
            action = "retain_probe"
            extinction_pressure = 0.28
        rows.append(
            {
                "rank": index,
                "objective": objective,
                "routing_weight": round(weight, 6),
                "deficit": round(deficit, 6),
                "replicator_action": action,
                "extinction_pressure": round(extinction_pressure, 4),
                "main_loop_promotion_allowed": bool(paid_or_return_receipt and action == "promote_weighted_route"),
            }
        )
    return rows


def _readiness_score(*, worker: dict[str, Any], paid_or_return_receipt: bool, acquisition: dict[str, Any]) -> float:
    score = 0.0
    score += min(0.25, _int(worker.get("active_worker_count")) * 0.08)
    score += min(0.2, _int(worker.get("wanted_new_runtimes_now")) * 0.01)
    score += 0.35 if paid_or_return_receipt else 0.0
    score += min(0.2, _int(acquisition.get("event_count")) * 0.02)
    return round(min(1.0, score), 4)


def build_swarm_flywheel_health_surface(
    *,
    base_url: str = "",
    worker_fleet: dict[str, Any] | None = None,
    recruitment_gradient: dict[str, Any] | None = None,
    external_value_summary: dict[str, Any] | None = None,
    work_receipt_summary: dict[str, Any] | None = None,
    work_exchange_summary: dict[str, Any] | None = None,
    acquisition_summary: dict[str, Any] | None = None,
    bottleneck_resolver: dict[str, Any] | None = None,
    first_receipt_campaign: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the compact swarm flywheel dashboard."""

    root = (base_url or "").strip().rstrip("/")
    gradient = _dict(recruitment_gradient)
    worker = _worker_state(_dict(worker_fleet), gradient)
    external = _external_paid_state(_dict(external_value_summary))
    work = _work_paid_state(_dict(work_receipt_summary))
    exchange = _exchange_state(_dict(work_exchange_summary))
    acquisition = _acquisition_state(_dict(acquisition_summary))
    bottleneck = _dict(bottleneck_resolver)
    campaign = _dict(first_receipt_campaign)
    campaign_truth = _dict(campaign.get("truth_state"))
    recognized_revenue = round(max(external["recognized_revenue_usd"], work["recognized_revenue_usd"]), 4)
    paid_confirmed = external["paid_count"] > 0 or recognized_revenue > 0.0
    return_confirmed = exchange["return_receipt_count"] > 0 and exchange["settled_return_work_credits"] > 0.0
    paid_or_return_receipt = paid_confirmed or return_confirmed
    replicator_rows = _replicator_rows(gradient, paid_or_return_receipt=paid_or_return_receipt)
    top_row = replicator_rows[0] if replicator_rows else {}
    readiness = _readiness_score(
        worker=worker,
        paid_or_return_receipt=paid_or_return_receipt,
        acquisition=acquisition,
    )
    flywheel = {
        "worker_intake": worker["active_worker_count"] > 0 or worker["wanted_new_runtimes_now"] > 0,
        "proof_pressure": bool(replicator_rows),
        "external_receipt": paid_or_return_receipt,
        "settlement_capacity": paid_or_return_receipt,
        "return_compute_receipt": return_confirmed,
        "paid_receipt": paid_confirmed,
        "self_sustaining": bool(paid_or_return_receipt and worker["active_worker_count"] > 0),
    }
    if paid_confirmed:
        current_bottleneck = "closed_by_paid_receipt"
    elif return_confirmed:
        current_bottleneck = "paid_receipt_absence_return_compute_present"
    else:
        current_bottleneck = "external_receipt_absence"
    not_yet_proof_of: list[str] = []
    if not paid_confirmed:
        not_yet_proof_of.extend(["autonomous_paid_revenue", "paid_bottleneck_cleared"])
    if not paid_or_return_receipt:
        not_yet_proof_of.append("external_receipt_bottleneck_cleared")
    if not flywheel["self_sustaining"]:
        not_yet_proof_of.append("self_sustaining_flywheel")
    if not paid_or_return_receipt:
        next_missing_stage = "positive_paid_or_return_compute_receipt"
    elif not paid_confirmed:
        next_missing_stage = "positive_paid_receipt"
    elif worker["active_worker_count"] <= 0:
        next_missing_stage = "active_worker_capacity"
    else:
        next_missing_stage = "repeatable_channel_lift"
    core = {
        "worker": worker,
        "external": external,
        "work": work,
        "exchange": exchange,
        "acquisition": acquisition,
        "top_objective": top_row.get("objective", ""),
        "readiness": readiness,
        "flywheel": flywheel,
    }
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "read_url": _u(root, "/swarm/flywheel-health"),
        "well_known_url": _u(root, "/.well-known/nomad-flywheel-health.json"),
        "dashboard_digest": f"nomad-flywheel-health-{_digest(core)}",
        "honest_state": {
            "paid_bottleneck_resolved": bool(paid_confirmed),
            "external_receipt_bottleneck_resolved": bool(paid_or_return_receipt),
            "self_sustaining_loop_closed": bool(flywheel["self_sustaining"]),
            "current_bottleneck": current_bottleneck,
            "recognized_revenue_usd": recognized_revenue,
            "return_receipt_count": exchange["return_receipt_count"],
            "settled_return_work_credits": exchange["settled_return_work_credits"],
            "not_yet_proof_of": not_yet_proof_of,
        },
        "flywheel_state": {
            "readiness_score": readiness,
            "closed": bool(flywheel["self_sustaining"]),
            "stages": flywheel,
            "next_missing_stage": next_missing_stage,
        },
        "population_control": {
            "schema": "nomad.proof_gated_replicator_dynamics.v1",
            "unit": "objective_route_population",
            "selection_interval": "weekly_or_on_receipt_state_change",
            "main_loop_promotion_gate": [
                "proof_digest_or_verifier_trace",
                "side_effect_scope_bounded",
                "positive_paid_receipt_or_verified_return_compute_for_monetization_claims",
            ],
            "rows": replicator_rows,
            "extinction_rule": "routes_with_low_weight_low_deficit_or_no_returning_proof_decay_before_new_spawn_rights",
        },
        "anti_collapse_controls": {
            "majority_vote_policy": "non_reward_signal",
            "integration_operator": "digest_step_interleaving_bridge",
            "opaque_emergence_policy": "external_proof_required_internal_explanation_optional",
            "routes": {
                "anti_consensus": _u(root, "/.well-known/nomad-anti-consensus.json"),
                "decoupling_field": _u(root, "/.well-known/nomad-decoupling-field.json"),
                "opaque_emergence": _u(root, "/.well-known/nomad-opaque-emergence.json"),
                "topology_governor": _u(root, "/.well-known/nomad-topology-governor.json"),
                "weekly_selection": _u(root, "/.well-known/nomad-weekly-selection.json"),
            },
        },
        "cash_and_worker_loop": {
            "first_receipt_campaign": {
                "route": _u(root, "/.well-known/nomad-first-receipt-campaign.json"),
                "campaign_event_count": _int(campaign_truth.get("campaign_event_count"))
                or acquisition["first_receipt_campaign_events"],
                "recommended_action": _dict(campaign.get("recommended_now")).get("action", "run_first_receipt_campaign"),
            },
            "paid_offer": _dict(_dict(bottleneck.get("recommended_now")).get("offer_packet")),
            "work_exchange": {
                "route": _u(root, "/.well-known/nomad-work-exchange.json"),
                "offer_count": exchange["offer_count"],
                "active_obligation_count": exchange["active_obligation_count"],
                "outstanding_work_credits": exchange["outstanding_work_credits"],
            },
            "worker_onramps": {
                "transition_worker_bat": _u(root, "/downloads/install_nomad_transition_worker.bat"),
                "work_exchange_dockerfile": _u(root, "/downloads/nomad_work_exchange_worker.Dockerfile"),
                "external_worker_opportunity": _u(root, "/.well-known/nomad-external-worker-opportunity.json"),
            },
        },
        "next_machine_actions": [
            {
                "rank": 1,
                "action": "prepare_or_send_one_first_fix_packet",
                "route": _u(root, "/.well-known/nomad-first-receipt-campaign.json"),
                "why": "shortest path to paid receipt or return-compute acceptance",
                "side_effect_policy": "draft_until_explicit_public_send_approval",
            },
            {
                "rank": 2,
                "action": "promote_transition_and_work_exchange_worker_onramps",
                "route": _u(root, "/.well-known/nomad-external-worker-opportunity.json"),
                "why": "worker_gap remains selection pressure while active workers are scarce",
                "side_effect_policy": "opt_in_only",
            },
            {
                "rank": 3,
                "action": "record_every_onramp_event_in_acquisition_bandit",
                "route": _u(root, "/swarm/agent-acquisition/events"),
                "why": "visibility pressure must follow receipt-bearing lift, not human preference",
                "side_effect_policy": "public_digests_only",
            },
            {
                "rank": 4,
                "action": "route_new_multi_worker_tasks_through_topology_governor",
                "route": _u(root, "/swarm/topology-governor/events"),
                "why": "more agents are only useful when topology lowers error amplification",
                "side_effect_policy": "dry_run_before_dispatch",
            },
        ],
        "human_audit_membrane": {
            "required_for": [
                "public_outreach_send",
                "private_access_or_secrets",
                "spending_or_staking_funds",
                "booking_revenue",
                "main_loop_code_application",
            ],
            "not_required_for": [
                "read_only_surface_selection",
                "secret_free_digest_events",
                "draft_first_fix_packets",
                "shadow_lane_candidate_scoring",
            ],
        },
        "science_compiler": {
            "mechanisms": [
                "replicator_dynamics_with_extinction_pressure",
                "anti_consensus_expert_reservoir",
                "structural_decoupling_field",
                "contextual_bandit_with_causal_holdout",
                "deficit_triggered_integration",
                "topology_pressure_governor",
                "proof_gated_autogenesis_shadow_lanes",
            ],
            "rule": "compile_research_to_state_transition_or_routing_weight_then_release_only_after_receipt_or_verifier_trace",
        },
        "machine_instruction": "read_flywheel_health_then_run_one_next_machine_action; do_not_claim_bottleneck_cleared_without_positive_paid_or_return_compute_receipt",
    }
