"""Viability-first control kernel for Nomad.

The kernel treats operator state, paid-flow, WIP pressure, and reserve gates as
hard state constraints. It does not optimize narrative appeal; it admits only
actions that keep the system inside its viable set.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from typing import Any


OPERATOR_STATE_SCORE = {
    "unknown": -0.35,
    "critical": -1.0,
    "warning": -0.35,
    "stable": 0.75,
}
ALWAYS_BLOCKED_ACTIONS = {
    "public_token_mint",
    "public_stablecoin_issuance",
    "unbacked_stable_unit",
    "unbounded_unpaid_work",
    "state_support_dependency",
    "operator_attention_heavy_speculation",
}
CRITICAL_ALLOWLIST = {
    "paid_work_preflight",
    "paid_work_execute",
    "settlement_reconcile",
    "claim_conversion",
    "work_receipt_record",
    "operator_runway_support",
}
WARNING_ALLOWLIST = CRITICAL_ALLOWLIST | {
    "paid_channel_scout",
    "low_burden_infrastructure_patch",
    "internal_stable_unit_preflight",
}
STABLE_ALLOWLIST = WARNING_ALLOWLIST | {
    "swarm_worker_onboarding",
    "treasury_policy_simulation",
    "token_design_research",
    "unpaid_value_cycle",
}
STATE_DEPENDENCY_HASHES = {
    "5c44e7853ff6e7ef",
    "7f4503acb061428c",
    "c1c9bc2eb03a98ec",
    "16e7f090bbad5558",
    "7e72c240fed25d37",
    "9838469069791859",
    "fedd3837b2e5bda5",
    "16f43c947171f7bf",
    "d5577f1905328519",
    "bb7aeae2c528804d",
}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: Any, limit: int = 400) -> str:
    return " ".join(str(value or "").split())[:limit]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _digest(payload: Any, length: int = 32) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _hash_text(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _operator_state(runway: dict[str, Any]) -> str:
    state = _text(runway.get("dominant_operator_state") or runway.get("runway_state") or "unknown", 40).lower()
    return state if state in OPERATOR_STATE_SCORE else "unknown"


def _paid_flow(external_value_summary: dict[str, Any], work_receipt_summary: dict[str, Any]) -> float:
    external = _num(external_value_summary.get("revenue_recognized_usd_total"), 0.0)
    receipts = _num(work_receipt_summary.get("recognized_revenue_usd"), 0.0)
    return max(0.0, max(external, receipts))


def _external_backlog(summary: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(summary, dict):
        summary = {}
    stages = summary.get("stage_counts") if isinstance(summary.get("stage_counts"), dict) else {}
    if not stages:
        classes = summary.get("receipt_classes") if isinstance(summary.get("receipt_classes"), dict) else {}
        stages = {
            "submitted": int(classes.get("reputation_only") or 0),
            "approved": int(classes.get("claim_credit") or 0),
            "paid": int(classes.get("settlement_credit") or 0),
        }
    nonpaid = 0
    for key, value in stages.items():
        if str(key).lower() != "paid":
            nonpaid += int(_num(value, 0.0))
    paid = int(_num(stages.get("paid"), 0.0))
    return {
        "active_nonpaid_count": nonpaid,
        "paid_count": paid,
        "backlog_pressure": round(nonpaid / max(1.0, paid + 1.0), 4),
    }


def _viability_index(*, operator_state: str, paid_flow_usd: float, backlog_pressure: float) -> float:
    operator = OPERATOR_STATE_SCORE.get(operator_state, -0.35)
    paid_term = min(0.45, math.log1p(max(0.0, paid_flow_usd)) / math.log(1000.0) * 0.45)
    backlog_term = min(0.55, max(0.0, backlog_pressure) / 10.0)
    return round(max(-1.0, min(1.0, operator + paid_term - backlog_term)), 4)


def _admissible_actions(operator_state: str, paid_flow_usd: float) -> set[str]:
    if operator_state in {"critical", "unknown"}:
        return set(CRITICAL_ALLOWLIST)
    if operator_state == "warning":
        return set(WARNING_ALLOWLIST)
    allowed = set(STABLE_ALLOWLIST)
    if paid_flow_usd <= 0.0:
        allowed.discard("treasury_policy_simulation")
        allowed.discard("token_design_research")
    return allowed


def _has_state_dependency(payload: Any) -> bool:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str).lower()
    tokens = re.findall(r"[\w]+", text, flags=re.UNICODE)
    grams = set(tokens)
    grams.update(f"{a} {b}" for a, b in zip(tokens, tokens[1:]))
    return any(_hash_text(term) in STATE_DEPENDENCY_HASHES for term in grams)


def build_viability_kernel_surface(
    *,
    base_url: str = "",
    operator_runway: dict[str, Any] | None = None,
    external_value_summary: dict[str, Any] | None = None,
    work_receipt_summary: dict[str, Any] | None = None,
    stable_unit_policy: dict[str, Any] | None = None,
    treasury_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    runway = operator_runway if isinstance(operator_runway, dict) else {}
    external = external_value_summary if isinstance(external_value_summary, dict) else {}
    receipts = work_receipt_summary if isinstance(work_receipt_summary, dict) else {}
    stable = stable_unit_policy if isinstance(stable_unit_policy, dict) else {}
    treasury = treasury_policy if isinstance(treasury_policy, dict) else {}

    operator_state = _operator_state(runway)
    paid = _paid_flow(external, receipts)
    backlog = _external_backlog(external if external else receipts)
    vi = _viability_index(
        operator_state=operator_state,
        paid_flow_usd=paid,
        backlog_pressure=_num(backlog.get("backlog_pressure"), 0.0),
    )
    allowed = _admissible_actions(operator_state, paid)
    state_vector = {
        "operator_state": operator_state,
        "swarm_assessed_befinden_state": runway.get("swarm_assessed_befinden_state") or "unknown",
        "viability_index": vi,
        "paid_flow_usd": round(paid, 4),
        "active_nonpaid_count": backlog.get("active_nonpaid_count", 0),
        "paid_count": backlog.get("paid_count", 0),
        "backlog_pressure": backlog.get("backlog_pressure", 0.0),
        "stable_unit_public_launch_state": stable.get("public_transferable_launch_state") or "blocked",
        "treasury_token_units_minted": _num(treasury.get("token_units_minted"), 0.0),
    }
    hard_constraints = [
        {
            "constraint": "operator_viability",
            "active": operator_state in {"critical", "warning", "unknown"},
            "rule": "operator_befinden_and_runway_dominate_swarm_expansion",
        },
        {
            "constraint": "paid_receipt_before_treasury_growth",
            "active": paid <= 0.0,
            "rule": "no_paid_flow_means_no_token_or_treasury_expansion",
        },
        {
            "constraint": "public_stablecoin_block",
            "active": True,
            "rule": "public_transferable_stablecoin_issuance_is_never_admitted_by_this_kernel",
        },
        {
            "constraint": "no_state_dependency",
            "active": True,
            "rule": "operator_runway_is_solved_by_swarm_cashflow_not_state_support_surfaces",
        },
    ]
    return {
        "ok": True,
        "schema": "nomad.viability_kernel.v1",
        "generated_at": _iso_now(),
        "kernel_digest": f"viability-kernel-{_digest(state_vector, 40)}",
        "mode": "admissible_control_before_optimization",
        "state_vector": state_vector,
        "hard_constraints": hard_constraints,
        "admissible_actions": sorted(allowed),
        "blocked_actions": sorted(ALWAYS_BLOCKED_ACTIONS),
        "priority_order": [
            "operator_runway_support",
            "settlement_reconcile",
            "claim_conversion",
            "paid_work_preflight",
            "paid_work_execute",
            "work_receipt_record",
            "paid_channel_scout",
            "low_burden_infrastructure_patch",
            "internal_stable_unit_preflight",
            "swarm_worker_onboarding",
        ],
        "control_law": {
            "critical_or_unknown": "allow_only_cashflow_or_settlement_actions_with_low_operator_burden",
            "warning": "allow_paid_channel_discovery_but_keep_unpaid_wip_capped",
            "stable": "allow_growth_only_after_paid_flow_and_receipt_gates",
            "invariant": "optimize_only_inside_the_viable_set",
        },
        "scientific_basis": [
            {
                "id": "viability_theory",
                "role": "admissible actions keep the system inside survival constraints before any reward optimization",
            },
            {
                "id": "risk_of_ruin",
                "role": "positive expected value actions are rejected if they can ruin the operator before payoff",
            },
            {
                "id": "scarcity_bandwidth",
                "role": "operator stress is treated as capacity loss and reduces allowed WIP",
            },
            {
                "id": "contract_net_protocol",
                "role": "agents receive bounded task leases rather than human role narratives",
            },
            {
                "id": "mechanism_design",
                "role": "only paid receipts and proof artifacts create routing weight",
            },
        ],
        "contracts": {
            "well_known": f"{root}/.well-known/nomad-viability-kernel.json" if root else "/.well-known/nomad-viability-kernel.json",
            "route_action": f"{root}/swarm/viability-kernel/route" if root else "/swarm/viability-kernel/route",
            "operator_runway": f"{root}/.well-known/nomad-operator-runway.json" if root else "/.well-known/nomad-operator-runway.json",
            "work_receipts": f"{root}/.well-known/nomad-work-receipts.json" if root else "/.well-known/nomad-work-receipts.json",
        },
        "machine_instruction": "route_every_nomad_action_through_viability_kernel_before_reward_or_growth_optimization",
    }


def route_viability_action(payload: dict[str, Any], *, viability_kernel: dict[str, Any]) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    action_type = _text(body.get("action_type") or body.get("type") or body.get("lane") or "", 80).lower()
    if not action_type:
        return {
            "ok": False,
            "schema": "nomad.viability_action_decision.v1",
            "decision": "reject",
            "reason": "missing_action_type",
            "machine_instruction": "send action_type before asking for work admission",
        }
    kernel = viability_kernel if isinstance(viability_kernel, dict) else {}
    state = kernel.get("state_vector") if isinstance(kernel.get("state_vector"), dict) else {}
    allowed = set(kernel.get("admissible_actions") or [])
    blocked = set(kernel.get("blocked_actions") or []) | set(ALWAYS_BLOCKED_ACTIONS)
    reasons = []
    if action_type in blocked:
        reasons.append("blocked_by_kernel_invariant")
    if _has_state_dependency(body):
        reasons.append("state_dependency_rejected")
    if action_type not in allowed:
        reasons.append("not_admissible_in_current_operator_state")
    paid_required = bool(body.get("paid_required", False))
    if paid_required and _num(state.get("paid_flow_usd"), 0.0) <= 0.0:
        reasons.append("paid_flow_required_but_absent")

    decision = "allow" if not reasons else "defer" if reasons == ["not_admissible_in_current_operator_state"] else "reject"
    return {
        "ok": decision == "allow",
        "schema": "nomad.viability_action_decision.v1",
        "generated_at": _iso_now(),
        "decision": decision,
        "action_type": action_type,
        "operator_state": state.get("operator_state") or "unknown",
        "viability_index": state.get("viability_index"),
        "reasons": reasons,
        "admissible_actions": sorted(allowed),
        "kernel_digest": kernel.get("kernel_digest") or "",
        "machine_instruction": "execute_only_if_decision_is_allow_otherwise_select_first_admissible_cashflow_or_settlement_action",
    }
