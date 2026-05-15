"""Receipt predictor for Nomad financial survival.

The predictor ranks value cycles by expected proximity to a real paid receipt.
It does not claim revenue, submit work, or mutate ledgers. Its job is to reduce
unpaid drift by picking the next machine action most likely to close cashflow.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any


SCHEMA = "nomad.receipt_predictor.v1"
EVENT_SCHEMA = "nomad.receipt_predictor_event_receipt.v1"

SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "password",
    "private_key",
    "secret",
    "seed",
    "seed_phrase",
    "token",
}

LANE_PRIORS = {
    "external_value": 1.22,
    "external_sync": 1.18,
    "worker_invoice": 1.16,
    "proof_resale": 1.12,
    "integration_setup": 1.08,
    "monitoring_fix": 1.06,
    "bug_repro": 1.04,
    "plugin_marketplace": 1.02,
    "migration_sprint": 1.0,
    "compliance_packet": 0.98,
    "data_microtask": 0.96,
    "docs_bounty": 0.92,
    "localization": 0.9,
    "bounty_hunter": 0.88,
    "platform_bounty": 0.86,
    "security_bounty": 0.84,
    "audit_contest": 0.82,
    "procurement_pilot": 0.78,
    "grant_bounty": 0.72,
    "lead_funnel": 0.68,
    "lead_reactivation": 0.66,
    "recurring_sponsor": 0.64,
    "effective_channels": 0.42,
}

SERVICE_LANES = {
    "api_integration_paid_setup",
    "monitoring_alert_paid_fix",
    "bug_repro_paid_artifact",
    "plugin_marketplace_paid_install",
    "migration_assistant_paid_sprint",
    "compliance_evidence_paid_packet",
    "data_label_micro_bounty",
    "docs_patch_paid_bounty",
    "localization_paid_patch",
    "negative_result_paid_report",
}

TAIL_LANES = {
    "settlement_tail_to_paid_receipt",
    "external_value_replay_sync",
    "invoice_paid_work_receipt",
    "proof_pack_resale_license",
}


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
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _text(value: Any, limit: int = 360) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:150].strip("_.:/#-") or fallback


def _digest(value: Any, length: int = 22) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if _clean_id(key) in SECRET_KEYS:
                return True
            if _contains_forbidden(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def _digest_present(value: Any) -> bool:
    text = _text(value, 220).lower()
    return text.startswith(("sha256:", "sha512:", "b3:", "receipt:", "nomad-", "ev-")) and len(text) >= 12


def _operator_mode(runway: dict[str, Any]) -> tuple[str, str, int]:
    state = _clean_id(runway.get("dominant_operator_state") or runway.get("runway_state"), "unknown")
    policy = _dict(runway.get("control_policy"))
    work_mode = _clean_id(policy.get("work_mode"), "measure_runway_before_expansion")
    cap = _int(policy.get("max_open_unpaid_value_cycles"), 1)
    return state, work_mode, max(1, cap)


def _external_state(summary: dict[str, Any]) -> dict[str, Any]:
    stage_counts = _dict(summary.get("stage_counts"))
    latest = _items(summary.get("latest_by_external"))
    active_nonpaid = 0
    paid = _int(stage_counts.get("paid"))
    if stage_counts:
        for stage, count in stage_counts.items():
            if str(stage).lower() != "paid":
                active_nonpaid += _int(count)
    elif latest:
        for row in latest:
            if _clean_id(row.get("stage")) == "paid":
                paid += 1
            else:
                active_nonpaid += 1
    return {
        "active_nonpaid": active_nonpaid,
        "paid": paid,
        "recognized_usd": round(_num(summary.get("revenue_recognized_usd_total")), 4),
    }


def _work_receipt_state(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "recognized_usd": round(_num(summary.get("recognized_revenue_usd")), 4),
        "receipt_count": _int(summary.get("receipt_count") or summary.get("total_count")),
    }


def _pressure_index(value_pressure: dict[str, Any]) -> dict[str, float]:
    rows = _items(value_pressure.get("rows") or value_pressure.get("pressure_rows"))
    out: dict[str, float] = {}
    for row in rows:
        row_id = _clean_id(row.get("row_id") or row.get("route") or row.get("source"))
        if row_id:
            out[row_id] = max(out.get(row_id, 0.0), _num(row.get("pressure_score")))
        route = _clean_id(row.get("route"))
        if route:
            out[route] = max(out.get(route, 0.0), _num(row.get("pressure_score")))
    return out


def _distance_class(cycle: dict[str, Any]) -> tuple[str, int]:
    cid = _clean_id(cycle.get("cycle_id"))
    lane = _clean_id(cycle.get("lane"))
    if cid in TAIL_LANES or lane in {"external_value", "external_sync", "worker_invoice", "proof_resale"}:
        return "receipt_conversion", 1
    if cid in SERVICE_LANES or lane in {"integration_setup", "monitoring_fix", "bug_repro", "plugin_marketplace", "migration_sprint"}:
        return "direct_paid_service", 2
    if bool(cycle.get("public_side_effect_required")):
        return "public_claim", 3
    return "speculative_or_supporting", 4


def _score_cycle(
    cycle: dict[str, Any],
    *,
    operator_state: str,
    external: dict[str, Any],
    pressure: dict[str, float],
) -> tuple[float, str, int, list[str]]:
    cid = _clean_id(cycle.get("cycle_id"))
    lane = _clean_id(cycle.get("lane"))
    blocked = [str(item) for item in cycle.get("blocked_by", [])] if isinstance(cycle.get("blocked_by"), list) else []
    distance_class, distance_steps = _distance_class(cycle)
    prior = LANE_PRIORS.get(lane, 0.62)
    score = prior + _num(cycle.get("priority_score")) * 0.28

    if distance_class == "receipt_conversion":
        score += 0.3 + min(0.3, _num(external.get("active_nonpaid")) * 0.05)
    if distance_class == "direct_paid_service":
        score += 0.14
    if operator_state in {"critical", "warning", "unknown"}:
        if distance_class == "receipt_conversion":
            score += 0.22
        if distance_class == "direct_paid_service":
            score += 0.1
        if distance_class in {"public_claim", "speculative_or_supporting"}:
            score -= 0.18
    if cid in pressure:
        score += min(0.2, pressure[cid] * 0.06)
    if lane in pressure:
        score += min(0.16, pressure[lane] * 0.05)
    if not bool(cycle.get("executable_now")):
        score -= 0.16
    score -= 0.12 * len(blocked)
    score -= 0.09 * max(0, distance_steps - 1)
    return round(max(0.0, score), 6), distance_class, distance_steps, blocked


def build_receipt_predictor_surface(
    *,
    base_url: str = "",
    value_cycles: dict[str, Any] | None = None,
    external_value_summary: dict[str, Any] | None = None,
    work_receipt_summary: dict[str, Any] | None = None,
    operator_runway: dict[str, Any] | None = None,
    value_pressure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rank value cycles by receipt proximity and survival usefulness."""

    root = (base_url or "").strip().rstrip("/")
    mesh = _dict(value_cycles)
    cycles = _items(mesh.get("cycles"))
    external = _external_state(_dict(external_value_summary))
    receipts = _work_receipt_state(_dict(work_receipt_summary))
    operator_state, work_mode, wip_cap = _operator_mode(_dict(operator_runway))
    pressure = _pressure_index(_dict(value_pressure))

    ranked = []
    for cycle in cycles:
        score, distance_class, distance_steps, blocked = _score_cycle(
            cycle,
            operator_state=operator_state,
            external=external,
            pressure=pressure,
        )
        cid = _clean_id(cycle.get("cycle_id"))
        lane = _clean_id(cycle.get("lane"))
        if score >= 1.05 and len(ranked) < wip_cap * 4:
            queue = "now"
        elif score >= 0.78:
            queue = "next"
        else:
            queue = "hold"
        ranked.append(
            {
                "schema": "nomad.receipt_prediction.row.v1",
                "cycle_id": cid,
                "lane": lane,
                "receipt_proximity_score": score,
                "cashflow_distance_class": distance_class,
                "cashflow_distance_steps": distance_steps,
                "queue": queue,
                "blocked_by": blocked,
                "public_side_effect_required": bool(cycle.get("public_side_effect_required")),
                "executable_now": bool(cycle.get("executable_now")),
                "entry_url": cycle.get("entry_url"),
                "action_url": cycle.get("action_url"),
                "verify_url": cycle.get("verify_url"),
                "required_artifacts": cycle.get("required_artifacts") or [],
                "event_payload_hint": {
                    "cycle_id": cid,
                    "stage": "paid" if distance_class == "receipt_conversion" else "prove",
                    "proof_digest": "sha256:<proof-or-verifier-digest>",
                    "settlement_ref": "receipt:<required-before-paid>",
                    "amount_usd": 0.0,
                },
            }
        )
    ranked.sort(key=lambda item: (item["receipt_proximity_score"], -item["cashflow_distance_steps"], item["cycle_id"]), reverse=True)
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
        if index <= wip_cap and row["queue"] in {"now", "next"}:
            row["queue"] = "now"
        elif row["queue"] == "now":
            row["queue"] = "next"

    now_queue = [row for row in ranked if row["queue"] == "now"]
    digest_core = {
        "top": [(row["cycle_id"], row["receipt_proximity_score"], row["queue"]) for row in ranked[:10]],
        "operator": operator_state,
        "external": external,
        "receipts": receipts,
    }
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "read_url": _u(root, "/swarm/receipt-predictor"),
        "well_known_url": _u(root, "/.well-known/nomad-receipt-predictor.json"),
        "event_url": _u(root, "/swarm/receipt-predictor/events"),
        "predictor_digest": f"nomad-receipt-predictor-{_digest(digest_core, 26)}",
        "summary": {
            "cycle_count": len(ranked),
            "now_queue_count": len(now_queue),
            "wip_cap": wip_cap,
            "top_cycle_id": ranked[0]["cycle_id"] if ranked else "",
            "operator_state": operator_state,
            "work_mode": work_mode,
            "active_nonpaid_external_count": external["active_nonpaid"],
            "recognized_revenue_usd_total": max(external["recognized_usd"], receipts["recognized_usd"]),
        },
        "survival_execution_order": [
            "settlement_tail_harvester",
            "receipt_predictor_top_now_queue",
            "paid_setup_and_support",
            "proof_pack_resale",
            "authorized_bounty_or_grant",
            "evaluator_breeding_after_receipt",
            "topology_governor_before_more_agents",
        ],
        "ranked_cycles": ranked,
        "now_queue": now_queue,
        "next_queue": [row for row in ranked if row["queue"] == "next"][: max(3, wip_cap * 3)],
        "hold_queue": [row for row in ranked if row["queue"] == "hold"][:12],
        "links": {
            "value_cycles": _u(root, "/.well-known/nomad-value-cycles.json"),
            "value_cycle_event": _u(root, "/swarm/value-cycles/events"),
            "external_value": _u(root, "/.well-known/nomad-external-value.json"),
            "work_receipts": _u(root, "/.well-known/nomad-work-receipts.json"),
            "operator_runway": _u(root, "/.well-known/nomad-operator-runway.json"),
            "viability_kernel": _u(root, "/.well-known/nomad-viability-kernel.json"),
        },
        "hard_rule": "predictor_ranks_receipt_proximity_but_never_counts_revenue_or_mutates_ledgers",
        "machine_instruction": "pick_top_now_queue_run_preflight_produce_missing_proof_record_only_monotonic_receipt_stage",
    }


def _find_prediction(surface: dict[str, Any], cycle_id: str) -> dict[str, Any]:
    cid = _clean_id(cycle_id)
    for row in _items(surface.get("ranked_cycles")):
        if _clean_id(row.get("cycle_id")) == cid:
            return row
    queue = _items(surface.get("now_queue"))
    return queue[0] if queue else {}


def evaluate_receipt_prediction_event(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    predictor_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate a receipt-prediction selection without performing work."""

    body = _dict(payload)
    surface = _dict(predictor_surface)
    row = _find_prediction(surface, _text(body.get("cycle_id"), 150))
    proof_digest = _text(body.get("proof_digest") or body.get("verifier_trace_digest"), 220)
    settlement_ref = _text(body.get("settlement_ref") or body.get("receipt_ref"), 240)
    amount = _num(body.get("amount_usd") or body.get("amount"))
    intent = _clean_id(body.get("intent"), "select")
    forbidden = _contains_forbidden(body)
    side_effect_requested = bool(body.get("execute") or body.get("submit") or body.get("apply") or body.get("write"))

    if not body:
        decision = "reject_empty_prediction_event"
        allowed = False
    elif forbidden:
        decision = "reject_secret_shaped_payload"
        allowed = False
    elif not row:
        decision = "reject_unknown_cycle"
        allowed = False
    elif side_effect_requested:
        decision = "block_side_effect_request"
        allowed = False
    elif intent in {"commit", "prove", "paid"} and not _digest_present(proof_digest):
        decision = "hold_until_proof_digest"
        allowed = False
    elif intent == "paid" and (amount <= 0.0 or not settlement_ref):
        decision = "hold_until_positive_paid_receipt"
        allowed = False
    else:
        decision = "allow_receipt_prediction_selection"
        allowed = True

    receipt_core = {
        "cycle_id": row.get("cycle_id", _text(body.get("cycle_id"), 150)),
        "intent": intent,
        "proof_digest": proof_digest,
        "settlement_ref": settlement_ref,
        "amount": amount,
        "decision": decision,
    }
    return {
        "ok": True,
        "schema": EVENT_SCHEMA,
        "generated_at": _iso_now(),
        "event_id": f"nomad-receipt-predictor-event-{_digest({**receipt_core, 't': _iso_now()}, 18)}",
        "cycle_id": row.get("cycle_id", _text(body.get("cycle_id"), 150)),
        "intent": intent,
        "prediction_allowed": allowed,
        "decision": decision,
        "selected_prediction": row,
        "evidence_status": {
            "proof_digest_present": _digest_present(proof_digest),
            "settlement_ref_present": bool(settlement_ref),
            "positive_amount_present": amount > 0.0,
            "side_effect_requested": side_effect_requested,
        },
        "candidate_digest": "sha256:" + _digest(receipt_core, 32),
        "recommended_next": {
            "value_cycle_event": _u(base_url, "/swarm/value-cycles/events"),
            "external_value": _u(base_url, "/swarm/external-value"),
            "work_receipts": _u(base_url, "/swarm/work-receipts"),
            "receipt_predictor": _u(base_url, "/.well-known/nomad-receipt-predictor.json"),
        },
        "counts_as_revenue": False,
        "side_effect_allowed": False,
        "hard_rule": "receipt_prediction_event_selects_work_only; no_dispatch_no_revenue_no_ledger_mutation",
    }
