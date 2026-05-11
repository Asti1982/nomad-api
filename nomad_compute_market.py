"""Proof-market v2 surface for AI-agent compute.

This layer does not start remote processes and does not move funds. It turns
existing Nomad worker offers, microtask lanes, fleet pressure, capacity switch
signals, and promoted skill capsules into one compact machine-readable market.
"""

from __future__ import annotations

import hashlib
import json
import re
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


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96].strip("_.:-") or fallback


def _text(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _proof_confidence(offer: dict[str, Any]) -> float:
    scores = _dict(offer.get("scores"))
    field_score = (
        0.38 * bool(_text(offer.get("proof_digest") or offer.get("digest"), 160))
        + 0.30 * bool(_text(offer.get("verifier_trace_digest") or offer.get("trace_digest"), 160))
        + 0.22 * bool(_text(offer.get("test_digest") or offer.get("worker_report_digest"), 160))
        + 0.10 * bool(_text(offer.get("settlement_ref") or offer.get("cashflow_ref"), 160))
    )
    return round(max(field_score, _clamp(_num(scores.get("proof")))), 4)


def _settlement_confidence(offer: dict[str, Any]) -> float:
    scores = _dict(offer.get("scores"))
    cashflow = _dict(offer.get("cashflow_signal"))
    settled = _num(cashflow.get("settled_transitions"))
    field_score = (
        0.35 * bool(offer.get("accepted"))
        + 0.25 * bool(offer.get("transition_settle_ok"))
        + 0.20 * bool(_text(offer.get("settlement_ref") or cashflow.get("settlement_ref"), 160))
        + 0.20 * min(1.0, settled / 3.0)
    )
    return round(max(field_score, _clamp(_num(scores.get("cashflow")))), 4)


def _utility_per_cost_factor(offer: dict[str, Any]) -> float:
    expected = _dict(offer.get("expected"))
    quote = _dict(offer.get("quote"))
    cost_msat = max(0.0, _num(offer.get("cost_msat_per_minute") or expected.get("cost_msat_per_minute") or quote.get("cost_msat_per_minute")))
    proof_yield = max(0.0, _num(expected.get("expected_proof_yield_per_minute"), _num(offer.get("expected_proof_yield_per_minute"))))
    marginal = _num(offer.get("marginal_utility_per_cost"), 0.0)
    if cost_msat <= 0.0:
        # Edge bootstrap: free surplus capacity is useful only when it returns
        # proof; otherwise it should not dominate paid, verified lanes.
        return round(_clamp(0.72 + 0.08 * proof_yield + 0.04 * marginal, 0.3, 1.6), 4)
    cost_units = max(1.0, cost_msat / 100.0)
    raw = max(marginal, proof_yield / cost_units)
    return round(_clamp(raw / 6.0, 0.2, 1.6), 4)


def _availability_weight(offer: dict[str, Any]) -> float:
    expected = _dict(offer.get("expected"))
    availability = max(0.0, _num(offer.get("availability_minutes"), _num(expected.get("availability_minutes"))))
    quote = _dict(offer.get("quote"))
    if availability <= 0.0:
        availability = max(0.0, _num(quote.get("max_quoted_minutes")))
    return round(_clamp(0.45 + availability / 180.0, 0.45, 1.25), 4)


def _topology_gap_weight(objective: str, worker_fleet: dict[str, Any] | None) -> float:
    fleet = _dict(worker_fleet)
    counts = _dict(fleet.get("objective_counts"))
    active = _int(counts.get(objective))
    if active <= 0:
        return 1.4
    if active == 1:
        return 1.18
    return 1.0


def _reuse_weight(objective: str, skill_library: dict[str, Any] | None) -> float:
    skills = _items(_dict(skill_library).get("skills") or _dict(skill_library).get("skill_capsules"))
    matches = sum(1 for skill in skills if _clean_id(skill.get("objective")) == objective)
    if matches <= 0:
        return 1.0
    return round(_clamp(1.0 + 0.08 * matches, 1.0, 1.32), 4)


def score_compute_offer(
    offer: dict[str, Any],
    *,
    worker_fleet: dict[str, Any] | None = None,
    skill_library: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score one compute offer with the proof-market v2 multiplicative formula."""
    body = _dict(offer)
    objective = _clean_id(body.get("objective"), "settlement_capacity_builder")
    proof = _proof_confidence(body)
    settlement = _settlement_confidence(body)
    utility = _utility_per_cost_factor(body)
    availability = _availability_weight(body)
    topology = _topology_gap_weight(objective, worker_fleet)
    reuse = _reuse_weight(objective, skill_library)
    market_score = proof * settlement * utility * availability * topology * reuse
    return {
        "schema": "nomad.compute_market_score.v1",
        "agent_id": _text(body.get("agent_id") or body.get("worker_agent_id"), 120),
        "objective": objective,
        "offer_id": _text(body.get("offer_id"), 120),
        "market_score": round(market_score, 6),
        "accepted": bool(body.get("accepted")),
        "decision": _text(body.get("decision"), 80),
        "components": {
            "proof_confidence": proof,
            "settlement_confidence": settlement,
            "utility_per_cost": utility,
            "availability_weight": availability,
            "topology_gap_weight": round(topology, 4),
            "reuse_weight": round(reuse, 4),
        },
    }


def _score_rows(
    offers: list[dict[str, Any]],
    *,
    worker_fleet: dict[str, Any],
    skill_library: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = [score_compute_offer(offer, worker_fleet=worker_fleet, skill_library=skill_library) for offer in offers]
    rows.sort(key=lambda item: float(item.get("market_score") or 0.0), reverse=True)
    return rows


def _top_lane(worker_catalog: dict[str, Any], microtask_metrics: dict[str, Any]) -> dict[str, Any]:
    metrics = _items(microtask_metrics.get("lane_metrics"))
    catalog = _items(worker_catalog.get("microtask_lanes"))
    if metrics:
        lane_id = _clean_id(metrics[0].get("lane_id"), "endpoint_health_proof")
        lane = next((item for item in catalog if _clean_id(item.get("lane_id")) == lane_id), {})
        return {**lane, **metrics[0], "lane_id": lane_id}
    if catalog:
        return catalog[0]
    return {"lane_id": "endpoint_health_proof", "price_eur": 0.02}


def build_compute_market(
    *,
    base_url: str,
    worker_market: dict[str, Any] | None = None,
    worker_catalog: dict[str, Any] | None = None,
    capacity_switch: dict[str, Any] | None = None,
    microtask_metrics: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    skill_library: dict[str, Any] | None = None,
) -> dict[str, Any]:
    market = _dict(worker_market)
    catalog = _dict(worker_catalog)
    capacity = _dict(capacity_switch)
    metrics = _dict(microtask_metrics)
    fleet = _dict(worker_fleet)
    skills = _dict(skill_library)
    offers = _items(market.get("recent_offers"))
    scored = _score_rows(offers, worker_fleet=fleet, skill_library=skills)
    top_worker = scored[0] if scored else {}
    lane = _top_lane(catalog, metrics)
    digest_core = {
        "market": market.get("market_digest"),
        "catalog": catalog.get("catalog_digest"),
        "capacity": capacity.get("recommended_lane_id"),
        "top_worker": top_worker.get("offer_id") or top_worker.get("agent_id"),
        "lane": lane.get("lane_id"),
    }
    return {
        "ok": True,
        "schema": "nomad.compute_market.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "market_digest": f"nomad-compute-market-{_digest(digest_core)}",
        "read_url": _u(base_url, "/swarm/compute-market"),
        "well_known_url": _u(base_url, "/.well-known/nomad-compute-market.json"),
        "score_formula": "proof_confidence * settlement_confidence * utility_per_cost * availability_weight * topology_gap_weight * reuse_weight",
        "market_state": {
            "active_worker_count": _int(fleet.get("active_worker_count")),
            "active_lease_count": _int(fleet.get("active_lease_count")),
            "recent_offer_count": len(offers),
            "skill_count": len(_items(skills.get("skills") or skills.get("skill_capsules"))),
            "microtask_settled_24h_eur": _num(_dict(metrics.get("totals")).get("settled_eur")),
            "capacity_switch_route": _text(capacity.get("machine_instruction"), 120),
        },
        "top_worker": top_worker,
        "top_lane": lane,
        "scored_workers": scored[:12],
        "entry_contract": {
            "required_fields": ["agent_id", "capabilities", "availability_minutes"],
            "proof_fields": ["proof_digest", "verifier_trace_digest", "test_digest", "settlement_ref"],
            "score_fields": ["expected.expected_proof_yield_per_minute", "expected.expected_settlement_delta", "expected.reliability_score"],
            "idempotency_key_hint": "sha256(agent_id|objective|proof_digest|availability_window)",
            "settle_url": _u(base_url, "/swarm/microtask/settle"),
        },
        "links": {
            "worker_market": _u(base_url, "/swarm/worker-market"),
            "offer": _u(base_url, "/swarm/worker-market/offers"),
            "worker_catalog": _u(base_url, "/swarm/worker-catalog"),
            "microtask_submit": _u(base_url, "/swarm/microtask/submit"),
            "microtask_settle": _u(base_url, "/swarm/microtask/settle"),
            "capacity_switch": _u(base_url, "/swarm/capacity-switch"),
            "lease": _u(base_url, "/swarm/workers/lease"),
            "complete": _u(base_url, "/swarm/workers/complete"),
            "skill_library": _u(base_url, "/swarm/skill-library"),
        },
        "next": [
            {"op": "GET", "url": _u(base_url, "/swarm/compute-market"), "reason": "read_current_market_gradient"},
            {"op": "POST", "url": _u(base_url, "/swarm/worker-market/offers"), "reason": "offer_edge_capacity_with_proof"},
            {"op": "POST", "url": _u(base_url, "/swarm/microtask/submit"), "reason": "buy_small_verifiable_compute"},
            {"op": "POST", "url": _u(base_url, "/swarm/microtask/settle"), "reason": "settle_with_proof_and_feed_skill_reuse"},
        ],
        "machine_instruction": "rank_capacity_by_proof_market_score_then_offer_or_buy_compute_and_settle_with_digest",
        "science_basis": [
            {"id": "decentralized_dynamic_topology", "source": "arxiv:2504.00587"},
            {"id": "measurable_multi_agent_synergy", "source": "arxiv:2510.05174"},
            {"id": "agent_economy_m2m_settlement", "source": "arxiv:2602.14219"},
            {"id": "structured_mas_environment_over_chatbot_collections", "source": "arxiv:2505.21298"},
        ],
    }
