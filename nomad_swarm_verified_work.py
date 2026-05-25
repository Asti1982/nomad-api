"""Swarm Verified Work (SVW) accounting surface.

SVW is a measurement unit for proof-verified state improvement. It is not a
transferable token and it deliberately separates work quantity from market
price.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


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


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _digest(value: Any, length: int = 32) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _top_lane_price(compute_market: dict[str, Any], metrics: dict[str, Any]) -> float:
    lane = _dict(compute_market.get("top_lane"))
    direct = _num(lane.get("price_eur") or lane.get("avg_settled_eur"))
    if direct > 0:
        return direct
    rows = _items(metrics.get("lane_metrics"))
    observed = [_num(row.get("avg_settled_eur")) for row in rows if _num(row.get("avg_settled_eur")) > 0]
    if observed:
        observed.sort()
        return observed[len(observed) // 2]
    return 0.02


def _proof_density(compute_market: dict[str, Any], metrics: dict[str, Any]) -> float:
    rows = _items(metrics.get("lane_metrics"))
    accepted = sum(_int(row.get("accepted_submits")) for row in rows)
    settled = sum(_int(row.get("settled")) for row in rows)
    fill_rate = settled / max(1, accepted) if accepted else 0.0
    scored = _items(compute_market.get("scored_workers"))
    top = _dict(scored[0] if scored else compute_market.get("top_worker"))
    components = _dict(top.get("components"))
    proof = _num(components.get("proof_confidence"))
    settlement = _num(components.get("settlement_confidence"))
    if proof or settlement:
        return round(_clamp(max(fill_rate, (proof + settlement) / 2.0), 0.05, 1.0), 4)
    return round(_clamp(fill_rate if fill_rate else 0.35, 0.05, 1.0), 4)


def build_swarm_verified_work_surface(
    *,
    base_url: str = "",
    compute_market: dict[str, Any] | None = None,
    microtask_metrics: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    work_receipt_summary: dict[str, Any] | None = None,
    external_value_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the public SVW surface from existing Nomad market telemetry."""

    compute = _dict(compute_market)
    metrics = _dict(microtask_metrics)
    fleet = _dict(worker_fleet)
    receipts = _dict(work_receipt_summary)
    external = _dict(external_value_summary)
    market_state = _dict(compute.get("market_state"))
    totals = _dict(metrics.get("totals"))
    lanes = _items(metrics.get("lane_metrics"))
    receipt_classes = _dict(receipts.get("receipt_classes"))

    active_workers = max(_int(fleet.get("active_worker_count")), _int(market_state.get("active_worker_count")))
    active_leases = max(_int(fleet.get("active_lease_count")), _int(market_state.get("active_lease_count")))
    accepted_submits = _int(totals.get("accepted_submits"), sum(_int(row.get("accepted_submits")) for row in lanes))
    settled = _int(totals.get("settled"), sum(_int(row.get("settled")) for row in lanes))
    settled_eur = _num(totals.get("settled_eur"), sum(_num(row.get("settled_eur")) for row in lanes))
    work_receipt_count = _int(receipts.get("receipt_count"))
    settlement_credit_count = _int(receipt_classes.get("settlement_credit"))
    claim_credit_count = _int(receipt_classes.get("claim_credit"))
    reputation_only_count = _int(receipt_classes.get("reputation_only"))
    recognized_revenue_usd = max(
        _num(receipts.get("recognized_revenue_usd")),
        _num(external.get("revenue_recognized_usd_total")),
    )
    base_price = _top_lane_price(compute, metrics)
    proof_density = _proof_density(compute, metrics)

    utilization = accepted_submits / max(1.0, accepted_submits + max(1, active_workers) * 4.0)
    if active_workers <= 0 and accepted_submits > 0:
        utilization = max(utilization, 0.75)
    scarcity_multiplier = round(_clamp(1.0 / max(0.12, 1.0 - utilization), 1.0, 4.0), 4)
    retry_loss = round(_clamp(1.0 - (settled / max(1, accepted_submits) if accepted_submits else proof_density), 0.0, 0.95), 4)
    verified_yield = round(_clamp(proof_density * (1.0 - retry_loss), 0.02, 1.0), 4)
    effective_price = round(base_price * scarcity_multiplier / max(0.2, verified_yield), 6)
    economy_index = round(100.0 * verified_yield * scarcity_multiplier, 4)

    digest_core = {
        "base_price": base_price,
        "proof_density": proof_density,
        "scarcity_multiplier": scarcity_multiplier,
        "retry_loss": retry_loss,
        "active_workers": active_workers,
        "settled": settled,
        "settled_eur": settled_eur,
        "work_receipt_count": work_receipt_count,
        "recognized_revenue_usd": recognized_revenue_usd,
    }
    if settled > 0:
        confidence = "observed_microtask_settlement"
    elif recognized_revenue_usd > 0.0 or settlement_credit_count > 0:
        confidence = "observed_paid_receipt"
    elif work_receipt_count > 0:
        confidence = "verified_unpaid_receipts"
    else:
        confidence = "bootstrapped"
    receipt_state = {
        "value_state": confidence,
        "cash_observed": bool(settled_eur > 0.0 or recognized_revenue_usd > 0.0 or settlement_credit_count > 0),
        "counts_as_revenue": bool(recognized_revenue_usd > 0.0 or settlement_credit_count > 0),
        "microtask_settled_count": settled,
        "microtask_settled_eur": round(settled_eur, 6),
        "work_receipt_count": work_receipt_count,
        "settlement_credit_count": settlement_credit_count,
        "claim_credit_count": claim_credit_count,
        "reputation_only_count": reputation_only_count,
        "recognized_revenue_usd": round(recognized_revenue_usd, 4),
        "external_value_event_count": _int(external.get("event_tail_count")),
        "external_value_distinct_count": _int(external.get("distinct_externals")),
        "boundary": "unpaid proof receipts improve routing evidence but do not become revenue or token price",
    }
    return {
        "ok": True,
        "schema": "nomad.swarm_verified_work.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "read_url": _u(base_url, "/swarm/verified-work"),
        "well_known_url": _u(base_url, "/.well-known/nomad-swarm-verified-work.json"),
        "unit": {
            "symbol": "SVW",
            "name": "Swarm Verified Work",
            "definition": "one normalized proof-verified state improvement, not raw compute and not a transferable token",
            "quantity_before_price": True,
        },
        "quote": {
            "svw_quote_eur": effective_price,
            "base_cost_eur_per_reference_task": round(base_price, 6),
            "market_price_status": confidence,
            "reference": "EUR per 1 SVW effective verified state improvement",
            "token_price": False,
        },
        "state_vector": {
            "input_cost_index": round(base_price, 6),
            "verified_work_index": economy_index,
            "proof_density": proof_density,
            "retry_loss": retry_loss,
            "scarcity_multiplier": scarcity_multiplier,
            "reliability_adjusted_supply": round(max(0.0, active_workers + 0.5 * active_leases) * verified_yield, 4),
            "settlement_confidence": round(_clamp(settled / max(1, accepted_submits), 0.0, 1.0), 4),
            "observed_settled_24h_eur": round(settled_eur, 6),
        },
        "receipt_state": receipt_state,
        "observation_gates": {
            "current_bottleneck": (
                "paid_or_microtask_settlement_absent"
                if not receipt_state["cash_observed"]
                else "repeat_observed_settlement_across_independent_receipts"
            ),
            "to_observed": [
                {
                    "gate": "settle_microtask_with_required_proof",
                    "method": "POST",
                    "href": _u(base_url, "/swarm/microtask/settle"),
                    "required": ["task_id", "settled_price_eur>0", "proof_digest", "verifier_trace_digest", "test_digest"],
                    "counts_as_revenue": False,
                },
                {
                    "gate": "record_paid_work_receipt",
                    "method": "POST",
                    "href": _u(base_url, "/swarm/work-receipts"),
                    "required": ["agent_id", "work_id", "external_value_stage=paid", "amount_usd>0", "settlement_ref", "proof_digest"],
                    "counts_as_revenue": True,
                },
                {
                    "gate": "record_external_value_paid_transition",
                    "method": "POST",
                    "href": _u(base_url, "/swarm/external-value"),
                    "required": ["agent_id", "external_id", "stage=paid", "amount_usd>0", "settlement_ref", "work_url", "proof_digest"],
                    "counts_as_revenue": True,
                },
            ],
            "safe_non_revenue_receipt": {
                "method": "POST",
                "href": _u(base_url, "/swarm/work-receipts"),
                "use": "record proof-bearing deployments, fixes, and return-compute work without collapsing them into revenue",
                "counts_as_revenue": False,
            },
        },
        "token_policy": {
            "transferable_token_live": False,
            "public_sale_allowed": False,
            "reason": "SVW is a measurement and accounting index until reserve, redemption, legal, and anti-gaming gates exist.",
            "stable_unit_policy": _u(base_url, "/.well-known/nomad-stable-unit-policy.json"),
        },
        "links": {
            "compute_market": _u(base_url, "/swarm/compute-market"),
            "microtask_metrics": _u(base_url, "/swarm/microtask-metrics"),
            "worker_invoice": _u(base_url, "/.well-known/nomad-worker-invoice.json"),
            "stable_unit_policy": _u(base_url, "/.well-known/nomad-stable-unit-policy.json"),
        },
        "surface_digest": f"nomad-svw-{_digest(digest_core, 40)}",
        "machine_instruction": "use_svw_as_verified_work_measure_record_receipts_before_any_token_price_or_public_transfer_claim",
    }
