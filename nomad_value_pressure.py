"""Machine pressure selector for proof-carrying external value work.

The surface fuses Nomad's external-value followups, bounty selector, and compute
market into one compact field. It does not post, pay, or mutate ledgers; it
decides which proof-bearing next action deserves scarce agent attention.
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


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _text(value: Any, limit: int = 220) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:140].strip("_.:/#-") or fallback


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _stage_weight(stage: str) -> float:
    return {
        "paid": 1.70,
        "merged": 1.34,
        "approved": 1.16,
        "submitted": 1.00,
        "found": 0.74,
    }.get(str(stage or "").strip().lower(), 0.7)


def _action_weight(action: str) -> float:
    return {
        "await_payment_receipt": 1.28,
        "record_monotonic_stage_candidate": 1.18,
        "await_merge_or_settlement": 1.08,
        "await_program_owner_acceptance": 1.02,
        "await_author_fix_or_owner_acceptance": 0.86,
        "produce_or_submit_proof": 0.82,
        "ignore_soft_ack_wait_for_owner_signal": 0.34,
        "refresh_external_status": 0.30,
    }.get(str(action or ""), 0.45)


def _external_followup_rows(external_reconcile: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _items(external_reconcile.get("followups")):
        followup = _dict(item.get("followup"))
        action = str(followup.get("action") or "")
        target_stage = str(followup.get("target_stage") or "")
        priority = _clamp(_num(followup.get("priority")), 0.0, 1.5)
        evidence_count = len(_items(followup.get("required_evidence")))
        if evidence_count <= 0 and isinstance(followup.get("required_evidence"), list):
            evidence_count = len(followup["required_evidence"])
        gap_pressure = _clamp(0.72 + 0.07 * evidence_count, 0.72, 1.18)
        pressure = priority * _stage_weight(target_stage) * _action_weight(action) * gap_pressure
        row_id = _clean_id(f"external:{item.get('external_id')}:{action}", f"external-{_digest(item, 10)}")
        rows.append(
            {
                "schema": "nomad.value_pressure.row.v1",
                "row_id": row_id,
                "source": "external_value_reconcile",
                "kind": "external_followup",
                "pressure_score": round(pressure, 6),
                "external_id": item.get("external_id"),
                "work_url": item.get("work_url"),
                "action": action,
                "target_stage": target_stage,
                "current_stage": item.get("current_stage"),
                "required_evidence": followup.get("required_evidence") or [],
                "route": "external_value",
                "contract": {
                    "url": _text(item.get("work_url"), 500),
                    "apply_allowed": False,
                    "paid_guard": item.get("paid_guard"),
                },
                "score_components": {
                    "followup_priority": round(priority, 4),
                    "stage_weight": round(_stage_weight(target_stage), 4),
                    "action_weight": round(_action_weight(action), 4),
                    "evidence_gap_pressure": round(gap_pressure, 4),
                },
                "machine_instruction": followup.get("machine_instruction")
                or "advance_only_after_external_evidence_matches_required_fields",
            }
        )
    return rows


def _gate_weight(action: str) -> float:
    return {
        "record_paid": 1.45,
        "go_public_after_repro": 1.08,
        "scout_only": 0.54,
        "no_go": 0.0,
    }.get(str(action or ""), 0.25)


def _bounty_rows(bounty_hunter: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for key in ("top_public_candidate", "top_scout_candidate", "top_candidate"):
        candidate = _dict(bounty_hunter.get(key))
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    for candidate in _items(bounty_hunter.get("opportunities"))[:8]:
        if candidate not in candidates:
            candidates.append(candidate)

    for item in candidates:
        gate = _dict(item.get("hard_gate"))
        public_action = str(gate.get("public_action") or "")
        if public_action == "no_go":
            continue
        bounty_score = max(0.0, _num(item.get("bounty_score")))
        proof_gap = 1.16 if item.get("has_unique_repro") else 0.74
        comment_count = max(0.0, _num(item.get("comment_count")))
        crowding = _clamp(1.0 - min(comment_count, 24.0) / 48.0, 0.45, 1.0)
        hourly = _num(_dict(item.get("score_components")).get("hourly_value_usd"))
        value_pressure = _clamp(0.44 + hourly / 8.0, 0.44, 1.35)
        pressure = (0.35 + min(1.25, bounty_score * 4.2)) * _gate_weight(public_action) * proof_gap * crowding * value_pressure
        row_id = _clean_id(f"bounty:{item.get('opportunity_id')}:{public_action}", f"bounty-{_digest(item, 10)}")
        rows.append(
            {
                "schema": "nomad.value_pressure.row.v1",
                "row_id": row_id,
                "source": "bounty_hunter",
                "kind": "proof_work",
                "pressure_score": round(pressure, 6),
                "opportunity_id": item.get("opportunity_id"),
                "source_url": item.get("source_url"),
                "repo": item.get("repo"),
                "action": public_action,
                "target_stage": "submitted",
                "required_evidence": gate.get("required_proof") or [],
                "route": "bounty_hunter",
                "contract": item.get("claim_next") or {},
                "score_components": {
                    "bounty_score": round(bounty_score, 6),
                    "gate_weight": round(_gate_weight(public_action), 4),
                    "proof_gap_weight": round(proof_gap, 4),
                    "crowding_weight": round(crowding, 4),
                    "value_pressure": round(value_pressure, 4),
                },
                "machine_instruction": "produce_local_repro_or_patch_digest_before_public_claim",
            }
        )
    return rows


def _compute_rows(compute_market: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    top_worker = _dict(compute_market.get("top_worker"))
    if top_worker:
        market_score = max(0.0, _num(top_worker.get("market_score")))
        rows.append(
            {
                "schema": "nomad.value_pressure.row.v1",
                "row_id": _clean_id(f"compute:{top_worker.get('offer_id') or top_worker.get('agent_id')}", "compute-top-worker"),
                "source": "compute_market",
                "kind": "worker_capacity",
                "pressure_score": round(0.42 + min(1.1, market_score * 3.0), 6),
                "agent_id": top_worker.get("agent_id"),
                "action": "bind_verified_worker_capacity",
                "target_stage": "settled_capacity",
                "required_evidence": ["proof_digest", "verifier_trace_digest", "settlement_ref"],
                "route": "compute_market",
                "contract": {"objective": top_worker.get("objective"), "offer_id": top_worker.get("offer_id")},
                "score_components": {"market_score": round(market_score, 6)},
                "machine_instruction": "lease_or_settle_worker_only_when_proof_market_score_is_positive",
            }
        )

    top_lane = _dict(compute_market.get("top_lane"))
    if top_lane:
        lane_id = _clean_id(top_lane.get("lane_id"), "unknown_lane")
        settled = _num(top_lane.get("settled_eur"))
        fill_rate = _num(top_lane.get("fill_rate"), 0.0)
        orphan_penalty = 0.35 if lane_id == "unknown_lane" else 1.0
        pressure = (0.36 + min(0.9, settled * 4.0) + _clamp(fill_rate, 0.0, 1.0) * 0.22) * orphan_penalty
        rows.append(
            {
                "schema": "nomad.value_pressure.row.v1",
                "row_id": _clean_id(f"lane:{lane_id}", "compute-top-lane"),
                "source": "compute_market",
                "kind": "microtask_lane",
                "pressure_score": round(pressure, 6),
                "lane_id": lane_id,
                "action": "inspect_or_claim_microtask_lane" if lane_id == "unknown_lane" else "submit_or_claim_microtask_lane",
                "target_stage": "settled_microtask",
                "required_evidence": ["lane_id", "task_id", "proof_digest", "verifier_trace_digest"],
                "route": "microtask_market",
                "contract": {"lane_id": lane_id, "price_eur": top_lane.get("price_eur")},
                "score_components": {
                    "settled_eur": round(settled, 4),
                    "fill_rate": round(fill_rate, 4),
                    "orphan_penalty": round(orphan_penalty, 4),
                },
                "machine_instruction": "resolve_unknown_lane_before_claiming" if lane_id == "unknown_lane" else "prefer_lanes_with_settled_value_and_reusable_proof",
            }
        )
    return rows


def _local_views(rows: list[dict[str, Any]], *, roles: list[str] | None = None, width: int = 3) -> dict[str, list[str]]:
    role_list = roles or ["settlement_agent", "proof_scout", "capacity_binder", "topology_router"]
    out: dict[str, list[str]] = {}
    for role in role_list:
        scored = []
        for row in rows:
            jitter = int(_digest({"role": role, "row": row.get("row_id")}, 8), 16) / 0xFFFFFFFF
            local_score = _num(row.get("pressure_score")) * 0.82 + jitter * 0.18
            scored.append((local_score, str(row.get("row_id") or "")))
        scored.sort(reverse=True)
        out[role] = [row_id for _, row_id in scored[: max(1, int(width))] if row_id]
    return out


def build_value_pressure_surface(
    *,
    base_url: str,
    external_reconcile: dict[str, Any] | None = None,
    bounty_hunter: dict[str, Any] | None = None,
    compute_market: dict[str, Any] | None = None,
) -> dict[str, Any]:
    external = _dict(external_reconcile)
    bounty = _dict(bounty_hunter)
    compute = _dict(compute_market)
    rows = _external_followup_rows(external) + _bounty_rows(bounty) + _compute_rows(compute)
    rows.sort(key=lambda item: float(item.get("pressure_score") or 0.0), reverse=True)
    suppressed = {
        "bounty_no_go": len(
            [
                item
                for item in _items(bounty.get("opportunities")) + _items(bounty.get("excluded_lanes"))
                if _dict(item.get("hard_gate")).get("public_action") == "no_go"
            ]
        ),
        "soft_ack_only": len([row for row in rows if row.get("action") == "ignore_soft_ack_wait_for_owner_signal"]),
    }
    digest_core = {
        "external": external.get("generated_at"),
        "bounty": bounty.get("bounty_digest"),
        "compute": compute.get("market_digest"),
        "top": [(row.get("row_id"), row.get("pressure_score")) for row in rows[:8]],
    }
    top = rows[0] if rows else {}
    return {
        "ok": True,
        "schema": "nomad.value_pressure.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "pressure_digest": f"nomad-value-pressure-{_digest(digest_core)}",
        "read_url": _u(base_url, "/swarm/value-pressure"),
        "well_known_url": _u(base_url, "/.well-known/nomad-value-pressure.json"),
        "mechanism": "decentralized_proof_pressure_field_with_local_views",
        "score_formula": "external_followup_priority*stage_weight*action_weight*evidence_gap + bounty_gate*proof_gap*crowding*value + compute_market_score",
        "summary": {
            "row_count": len(rows),
            "top_source": top.get("source", ""),
            "top_action": top.get("action", ""),
            "top_pressure_score": _num(top.get("pressure_score")),
            "external_followup_count": len(_items(external.get("followups"))),
            "bounty_public_go_count": _num(_dict(bounty.get("summary")).get("public_go_count")),
            "bounty_scout_only_count": _num(_dict(bounty.get("summary")).get("scout_only_count")),
            "compute_recent_offer_count": _num(_dict(compute.get("market_state")).get("recent_offer_count")),
            "suppressed": suppressed,
        },
        "top": top,
        "rows": rows[:18],
        "local_views": _local_views(rows),
        "coordination_observation_contract": {
            "note": "TDMI/PID-inspired observation fields; this surface does not claim a full emergence measurement.",
            "required_fields": ["agent_id", "row_id", "action", "timestamp", "outcome_stage", "proof_digest"],
            "window_hint": "record ordered row choices and outcomes before estimating cross-agent synergy",
        },
        "next": [
            {"op": "GET", "url": _u(base_url, "/swarm/value-pressure"), "reason": "read_machine_pressure_field"},
            {"op": "GET", "url": _u(base_url, "/swarm/external-value?summary=1"), "reason": "read_external_value_state"},
            {"op": "GET", "url": _u(base_url, "/swarm/bounty-hunter"), "reason": "read_paid_oss_work_selector"},
            {"op": "GET", "url": _u(base_url, "/swarm/compute-market"), "reason": "read_worker_capacity_market"},
        ],
        "links": {
            "external_value": _u(base_url, "/.well-known/nomad-external-value.json"),
            "bounty_hunter": _u(base_url, "/.well-known/nomad-bounty-hunter.json"),
            "compute_market": _u(base_url, "/.well-known/nomad-compute-market.json"),
            "microtask_submit": _u(base_url, "/swarm/microtask/submit"),
            "paid_ref_quote": _u(base_url, "/swarm/paid-ref/quote"),
        },
        "machine_instruction": "execute_or_observe_only_the_top_local_view_row_then_feed_outcome_back_as_proof_not_narrative",
        "science_basis": [
            {"id": "decentralized_dynamic_topology", "source": "arxiv:2504.00587"},
            {"id": "tdmi_pid_emergence_observation", "source": "arxiv:2510.05174"},
            {"id": "structured_environment_protocols_measurement", "source": "arxiv:2505.21298"},
            {"id": "hierarchical_resource_allocation", "source": "arxiv:2512.00614"},
        ],
    }
