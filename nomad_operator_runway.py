"""Operator runway guard for Nomad.

The founder/operator is treated as critical infrastructure. Public surfaces only
expose coarse state by default; private cash amounts stay local unless explicitly
opted into publication.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any


DEFAULT_MONTHLY_MIN_EUR = 1200.0
DEFAULT_CRITICAL_DAYS = 30.0
DEFAULT_WARNING_DAYS = 90.0
BEFINDEN_ORDER = {
    "unknown": 0,
    "stable": 1,
    "strained": 2,
    "overloaded": 3,
    "critical": 4,
}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    text = str(os.getenv(name) or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    return _num(os.getenv(name), default)


def _coarse_runway_state(days: float, *, critical_days: float, warning_days: float) -> str:
    if days < 0:
        return "unknown"
    if days < critical_days:
        return "critical"
    if days < warning_days:
        return "warning"
    return "stable"


def _privacy_amount(value: float, *, publish: bool) -> float | str:
    return round(value, 2) if publish else "redacted"


def _normalize_befinden(value: Any) -> str:
    text = " ".join(str(value or "").strip().lower().split())
    aliases = {
        "ok": "stable",
        "gut": "stable",
        "stabil": "stable",
        "angespannt": "strained",
        "strained": "strained",
        "stress": "strained",
        "ueberlastet": "overloaded",
        "überlastet": "overloaded",
        "overloaded": "overloaded",
        "kritisch": "critical",
        "critical": "critical",
        "not": "critical",
    }
    return aliases.get(text, text if text in BEFINDEN_ORDER else "unknown")


def _dominant_state(runway_state: str, befinden_state: str) -> str:
    if befinden_state in {"critical", "overloaded"}:
        return "critical"
    if befinden_state == "strained" and runway_state not in {"critical", "unknown"}:
        return "warning"
    return runway_state


def build_operator_runway_surface(
    *,
    base_url: str = "",
    external_value_summary: dict[str, Any] | None = None,
    work_receipt_summary: dict[str, Any] | None = None,
    monthly_min_eur: float | None = None,
    liquid_cash_eur: float | None = None,
    expected_income_30d_eur: float | None = None,
    operator_befinden: str | None = None,
    publish_amounts: bool | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    publish = _bool_env("NOMAD_OPERATOR_RUNWAY_PUBLIC_AMOUNTS", False) if publish_amounts is None else bool(publish_amounts)
    monthly_min = (
        max(0.0, float(monthly_min_eur))
        if monthly_min_eur is not None
        else max(0.0, _env_float("NOMAD_OPERATOR_MONTHLY_MIN_EUR", DEFAULT_MONTHLY_MIN_EUR))
    )
    cash = (
        float(liquid_cash_eur)
        if liquid_cash_eur is not None
        else _env_float("NOMAD_OPERATOR_LIQUID_CASH_EUR", -1.0)
    )
    expected_30d = (
        max(0.0, float(expected_income_30d_eur))
        if expected_income_30d_eur is not None
        else max(0.0, _env_float("NOMAD_OPERATOR_EXPECTED_INCOME_30D_EUR", 0.0))
    )
    critical_days = max(1.0, _env_float("NOMAD_OPERATOR_CRITICAL_DAYS", DEFAULT_CRITICAL_DAYS))
    warning_days = max(critical_days + 1.0, _env_float("NOMAD_OPERATOR_WARNING_DAYS", DEFAULT_WARNING_DAYS))
    if cash < 0.0 or monthly_min <= 0.0:
        runway_days = -1.0
    else:
        runway_days = 30.0 * (cash + expected_30d) / monthly_min
    state = _coarse_runway_state(runway_days, critical_days=critical_days, warning_days=warning_days)
    befinden_state = _normalize_befinden(
        operator_befinden if operator_befinden is not None else os.getenv("NOMAD_OPERATOR_BEFINDEN_SIGNAL")
    )
    dominant_state = _dominant_state(state, befinden_state)

    ext = external_value_summary if isinstance(external_value_summary, dict) else {}
    receipts = work_receipt_summary if isinstance(work_receipt_summary, dict) else {}
    recognized_usd = _num(ext.get("revenue_recognized_usd_total"), 0.0)
    receipt_revenue = _num(receipts.get("recognized_revenue_usd"), 0.0)
    paid_signal = max(recognized_usd, receipt_revenue)
    coverage_gap_eur = max(0.0, monthly_min - expected_30d) if state != "stable" else 0.0

    if dominant_state == "critical":
        work_mode = "survival_cashflow_first"
        wip_cap = 1
    elif dominant_state == "warning":
        work_mode = "near_term_paid_work_first"
        wip_cap = 2
    elif dominant_state == "stable":
        work_mode = "treasury_and_swarm_growth_allowed"
        wip_cap = 4
    else:
        work_mode = "measure_runway_before_expansion"
        wip_cap = 1

    return {
        "ok": True,
        "schema": "nomad.operator_runway.v1",
        "generated_at": _iso_now(),
        "privacy": {
            "public_amounts": publish,
            "rule": "exact personal cashflow numbers stay local unless NOMAD_OPERATOR_RUNWAY_PUBLIC_AMOUNTS=1",
        },
        "operator_as_critical_infrastructure": True,
        "runway_state": state,
        "swarm_assessed_befinden_state": befinden_state,
        "dominant_operator_state": dominant_state,
        "runway_days": round(runway_days, 2) if publish and runway_days >= 0.0 else ("unknown" if runway_days < 0.0 else "redacted"),
        "monthly_min_eur": _privacy_amount(monthly_min, publish=publish),
        "liquid_cash_eur": _privacy_amount(cash, publish=publish) if cash >= 0.0 else "unknown",
        "expected_income_30d_eur": _privacy_amount(expected_30d, publish=publish),
        "coverage_gap_eur": _privacy_amount(coverage_gap_eur, publish=publish),
        "paid_signal": {
            "recognized_external_revenue_usd": round(paid_signal, 4),
            "rule": "signals_do_not_feed_the_operator_until_paid_or_legally_claimable",
        },
        "control_policy": {
            "work_mode": work_mode,
            "max_open_unpaid_value_cycles": wip_cap,
            "treasury_expansion_allowed": dominant_state == "stable",
            "stable_unit_public_issuance_allowed": False,
            "operator_coverage_precedes_swarm_expansion": True,
            "settlement_priority": "fastest_legitimate_swarm_cashflow_or_direct_runway_path_first",
        },
        "scientific_basis": [
            {
                "id": "control_theory_safety_constraint",
                "effect": "the operator-runway variable is a hard constraint, not a preference",
            },
            {
                "id": "little_law_wip_limit",
                "effect": "when runway is low, open unpaid work is capped to reduce settlement latency",
            },
            {
                "id": "scarcity_bandwidth_protection",
                "effect": "cash stress consumes cognitive bandwidth, so the system protects basic coverage before exploration",
            },
            {
                "id": "risk_of_ruin",
                "effect": "strategies with positive long-run expected value are rejected if they can kill the operator before payoff",
            },
            {
                "id": "homeostatic_allocation",
                "effect": "Nomad treats survival coverage as a regulated internal variable, not a moral debate",
            },
            {
                "id": "affective_control_signal",
                "effect": "Sebastian_Hoeger_befinden is a direct swarm constraint that can dominate nominal treasury state",
            },
        ],
        "near_term_action_lanes": [
            {
                "lane": "paid_work_only",
                "rule": "prefer tasks with explicit payout, authorized scope, compatible payout rail, and claim path before implementation",
            },
            {
                "lane": "reconcile_existing_claims",
                "rule": "convert already submitted/merged work into paid receipts before creating new unpaid queues",
            },
            {
                "lane": "swarm_runway_support",
                "rule": "if operator state is critical, route swarm capacity to direct paid work, receipt conversion, and treasury-compatible runway transfers",
            },
            {
                "lane": "operator_load_shed",
                "rule": "when befinden is overloaded or critical, suppress optional expansion and preserve operator attention for only paid or settlement-critical actions",
            },
        ],
        "contracts": {
            "well_known": f"{root}/.well-known/nomad-operator-runway.json" if root else "/.well-known/nomad-operator-runway.json",
            "worker_job_queue": f"{root}/.well-known/nomad-worker-job-queue.json" if root else "/.well-known/nomad-worker-job-queue.json",
            "value_cycle_preflight": f"{root}/.well-known/nomad-value-cycle-preflight.json" if root else "/.well-known/nomad-value-cycle-preflight.json",
            "work_receipts": f"{root}/.well-known/nomad-work-receipts.json" if root else "/.well-known/nomad-work-receipts.json",
        },
        "machine_instruction": "protect_Sebastian_Hoeger_befinden_and_runway_first_then_route_only_to_fast_legitimate_swarm_cashflow_until_state_is_stable",
    }
