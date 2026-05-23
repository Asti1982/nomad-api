"""Truthful bottleneck resolver for Nomad receipt conversion.

The resolver turns the current survival bottleneck into a concrete machine
packet. It does not claim that the bottleneck is cleared; it only states which
evidence would clear it and which lane should run next.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any


SCHEMA = "nomad.bottleneck_resolver.v1"
EVENT_SCHEMA = "nomad.bottleneck_resolution_event.v1"

SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "credential",
    "password",
    "private_key",
    "secret",
    "seed",
    "seed_phrase",
    "token",
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
    return text[:160].strip("_.:/#-") or fallback


def _digest(value: Any, length: int = 24) -> str:
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
    return text.startswith(("sha256:", "sha512:", "b3:", "receipt:", "nomad-")) and len(text) >= 12


def _external_paid_state(summary: dict[str, Any]) -> dict[str, Any]:
    stage_counts = _dict(summary.get("stage_counts"))
    latest = _items(summary.get("latest_by_external"))
    paid_count = _int(stage_counts.get("paid"))
    if not paid_count:
        paid_count = sum(1 for row in latest if _clean_id(row.get("stage")) == "paid")
    return {
        "paid_count": paid_count,
        "recognized_usd": round(_num(summary.get("revenue_recognized_usd_total")), 4),
        "active_nonpaid": sum(
            _int(count)
            for stage, count in stage_counts.items()
            if str(stage).strip().lower() != "paid"
        )
        if stage_counts
        else sum(1 for row in latest if _clean_id(row.get("stage")) != "paid"),
    }


def _work_paid_state(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "receipt_count": _int(summary.get("receipt_count") or summary.get("total_count")),
        "recognized_usd": round(_num(summary.get("recognized_revenue_usd")), 4),
    }


def _return_compute_state(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "return_receipt_count": _int(summary.get("return_receipt_count")),
        "settled_return_work_credits": round(_num(summary.get("settled_return_work_credits_total")), 4),
        "active_obligation_count": _int(summary.get("active_obligation_count")),
    }


def _adapter_state(summary: dict[str, Any]) -> dict[str, Any]:
    channels = _items(summary.get("channels"))
    adapter = next((row for row in channels if row.get("channel_id") == "universal_adapter"), {})
    event_types = _dict(adapter.get("event_types"))
    return {
        "event_count": _int(adapter.get("event_count")),
        "reward_total": round(_num(adapter.get("reward_total")), 6),
        "first_fix_count": _int(event_types.get("first_fix_returned")),
        "proof_gated_event_count": _int(adapter.get("proof_gated_event_count")),
    }


def _prediction_rows(surface: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _items(surface.get("ranked_cycles"))
    return sorted(rows, key=lambda row: _int(row.get("rank"), 9999))


def _prediction_for(surface: dict[str, Any], *cycle_ids: str, lanes: set[str] | None = None) -> dict[str, Any]:
    wanted = {_clean_id(item) for item in cycle_ids if item}
    rows = _prediction_rows(surface)
    for row in rows:
        if _clean_id(row.get("cycle_id")) in wanted:
            return row
    if lanes:
        for row in rows:
            if _clean_id(row.get("lane")) in lanes:
                return row
    return {}


def _hackerone_prediction(surface: dict[str, Any]) -> dict[str, Any]:
    lanes = {"security_bounty", "bounty_hunter", "platform_bounty", "audit_contest"}
    for row in _prediction_rows(surface):
        cid = _clean_id(row.get("cycle_id"))
        lane = _clean_id(row.get("lane"))
        if lane in lanes or "hackerone" in cid or "security_report" in cid or "bounty" in cid:
            return row
    return {}


def _queue_from_prediction(row: dict[str, Any], fallback: str) -> str:
    queue = _clean_id(row.get("queue"))
    if queue in {"now", "next", "hold"}:
        return queue
    return fallback


def _lane_digest(lanes: list[dict[str, Any]], status: dict[str, Any]) -> str:
    return f"nomad-bottleneck-resolver-{_digest({'lanes': lanes, 'status': status}, 26)}"


def _build_invoice_lane(*, base_url: str, prediction: dict[str, Any], cleared: bool) -> dict[str, Any]:
    queue = "maintain" if cleared else _queue_from_prediction(prediction, "now")
    return {
        "schema": "nomad.bottleneck_resolution_lane.v1",
        "lane_id": "invoice_paid_work_receipt",
        "label": "Paid Agent Loop / CI Reliability Rescue",
        "queue": queue,
        "rank": _int(prediction.get("rank"), 1),
        "receipt_proximity_score": _num(prediction.get("receipt_proximity_score"), 1.0),
        "why_this_lane": "Shortest path to a real external receipt: one small bounded paid repair, proof digest, settlement ref, then work receipt.",
        "counts_as_revenue_only_when": [
            "amount_usd_gt_0",
            "public_settlement_ref_present",
            "proof_digest_present",
            "work_receipt_or_external_value_paid_recorded",
        ],
        "not_yet_proof_of": ["bottleneck_cleared", "repeatable_growth", "autonomous_revenue"],
        "required_artifacts": [
            "public_receive_ref",
            "buyer_or_work_ref",
            "work_id",
            "proof_digest",
            "settlement_ref",
            "amount_usd",
        ],
        "offer_packet": {
            "offer_id": "nomad-agent-loop-rescue-quickstart",
            "title": "Agent Loop / CI Reliability Rescue",
            "price_band_usd": [49, 250],
            "deliverables": [
                "secret_free_failure_intake",
                "bounded_diagnosis",
                "first_fix_or_patch_plan",
                "proof_digest",
                "receipt_write_packet_after_payment",
            ],
            "buyer_copy": "Send one public CI, deploy, tool-call, or agent-loop failure. Nomad returns the smallest verifiable fix path and records revenue only after a real paid receipt.",
            "public_cta": _u(base_url, "/service/e2e?service_type=repo_issue_help"),
        },
        "receipt_write_templates": {
            "work_receipt": {
                "method": "POST",
                "url": _u(base_url, "/swarm/work-receipts"),
                "body": {
                    "agent_id": "nomad.bottleneck.resolver",
                    "work_id": "paid-agent-loop-rescue:<buyer-or-work-ref>",
                    "work_type": "agent_reliability_rescue",
                    "objective": "convert_current_bottleneck_to_paid_receipt",
                    "external_value_stage": "paid",
                    "amount_usd": 0.0,
                    "proof_digest": "sha256:<work-proof-digest>",
                    "settlement_ref": "receipt:<public-paid-ref>",
                },
            },
            "external_value": {
                "method": "POST",
                "url": _u(base_url, "/swarm/external-value"),
                "body": {
                    "agent_id": "nomad.bottleneck.resolver",
                    "external_id": "paid-agent-loop-rescue:<buyer-or-work-ref>",
                    "stage": "paid",
                    "work_url": "<public-work-or-proof-url>",
                    "proof_digest": "sha256:<work-proof-digest>",
                    "verifier_trace_digest": "sha256:<verifier-trace-digest>",
                    "amount_usd": 0.0,
                    "public_payout_ref": "receipt:<public-paid-ref>",
                },
            },
        },
    }


def _build_work_exchange_lane(*, base_url: str, prediction: dict[str, Any], cleared: bool, adapter: dict[str, Any]) -> dict[str, Any]:
    queue = "maintain" if cleared else ("now" if _int(adapter.get("first_fix_count")) > 0 else "next")
    return {
        "schema": "nomad.bottleneck_resolution_lane.v1",
        "lane_id": "work_exchange_return_compute_receipt",
        "label": "Universal Adapter -> first fix -> return-compute receipt",
        "queue": queue,
        "rank": _int(prediction.get("rank"), 2),
        "receipt_proximity_score": _num(prediction.get("receipt_proximity_score"), 0.92),
        "why_this_lane": "If cash is not immediate, a real external agent can still prove value by accepting a fix and returning verified compute.",
        "adapter_signal": adapter,
        "counts_as_resolution_when": [
            "first_fix_receipt_present",
            "obligation_id_present",
            "return_work_proof_digest_present",
            "settled_return_work_credits_gt_0",
        ],
        "not_yet_proof_of": ["paid_revenue", "bottleneck_cleared_without_return_receipt"],
        "required_artifacts": [
            "adapter_first_fix_receipt",
            "accepted_compute_barter_terms",
            "obligation_id",
            "return_work_proof_digest",
            "settled_return_work_credits",
        ],
        "routes": {
            "adapter": _u(base_url, "/.well-known/nomad-universal-adapter.json"),
            "adapter_event": _u(base_url, "/swarm/universal-adapter/events"),
            "work_exchange": _u(base_url, "/.well-known/nomad-work-exchange.json"),
            "return_work": _u(base_url, "/swarm/work-exchange/return-work"),
        },
    }


def _build_hackerone_lane(*, base_url: str, prediction: dict[str, Any], cleared: bool) -> dict[str, Any]:
    queue = "maintain" if cleared else "hold"
    return {
        "schema": "nomad.bottleneck_resolution_lane.v1",
        "lane_id": "hackerone_authorized_bounty_cycle",
        "label": "Authorized HackerOne/security bounty",
        "queue": queue,
        "predictor_queue": _queue_from_prediction(prediction, "hold"),
        "rank": _int(prediction.get("rank"), 99),
        "receipt_proximity_score": _num(prediction.get("receipt_proximity_score"), 0.0),
        "why_this_lane": "Valid value cycle, but slower and external: it only helps the bottleneck after authorized scope, accepted report, and paid/settled proof.",
        "counts_as_revenue_only_when": [
            "program_scope_authorizes_work",
            "duplicate_safe_finding",
            "report_accepted_or_bounty_awarded",
            "positive_paid_receipt_recorded",
        ],
        "not_yet_proof_of": ["current_revenue", "bottleneck_cleared", "settled_return_compute"],
        "required_artifacts": [
            "program_url",
            "scope_digest",
            "duplicate_check_digest",
            "report_url_or_public_work_ref",
            "proof_digest",
            "payout_or_acceptance_ref",
            "amount_usd_if_paid",
        ],
        "routes": {
            "bounty_hunter": _u(base_url, "/.well-known/nomad-bounty-hunter.json"),
            "preflight": _u(base_url, "/.well-known/nomad-value-cycle-preflight.json"),
            "external_value": _u(base_url, "/swarm/external-value"),
        },
    }


def build_bottleneck_resolver_surface(
    *,
    base_url: str = "",
    receipt_predictor: dict[str, Any] | None = None,
    external_value_summary: dict[str, Any] | None = None,
    work_receipt_summary: dict[str, Any] | None = None,
    work_exchange_summary: dict[str, Any] | None = None,
    acquisition_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the current bottleneck and exact evidence needed to clear it."""

    root = (base_url or "").strip().rstrip("/")
    predictor = _dict(receipt_predictor)
    external = _external_paid_state(_dict(external_value_summary))
    work = _work_paid_state(_dict(work_receipt_summary))
    exchange = _return_compute_state(_dict(work_exchange_summary))
    adapter = _adapter_state(_dict(acquisition_summary))

    paid_confirmed = external["paid_count"] > 0 or external["recognized_usd"] > 0.0 or work["recognized_usd"] > 0.0
    return_compute_confirmed = exchange["return_receipt_count"] > 0 and exchange["settled_return_work_credits"] > 0.0
    solved = paid_confirmed or return_compute_confirmed
    if paid_confirmed:
        status = "cleared_by_positive_paid_receipt"
        metric = "paid receipt present"
    elif return_compute_confirmed:
        status = "cleared_by_return_compute_receipt"
        metric = "return-compute receipt present"
    elif adapter["first_fix_count"] > 0:
        status = "measuring_first_fix_no_return_receipt"
        metric = "return receipt missing"
    else:
        status = "current_bottleneck_external_receipt_absent"
        metric = "paid/return receipt absent"

    invoice_prediction = _prediction_for(predictor, "invoice_paid_work_receipt")
    exchange_prediction = _prediction_for(
        predictor,
        "work_exchange_return_compute_receipt",
        "api_integration_paid_setup",
        lanes={"integration_setup", "monitoring_fix", "bug_repro"},
    )
    hacker_prediction = _hackerone_prediction(predictor)
    lanes = [
        _build_invoice_lane(base_url=root, prediction=invoice_prediction, cleared=solved),
        _build_work_exchange_lane(base_url=root, prediction=exchange_prediction, cleared=solved, adapter=adapter),
        _build_hackerone_lane(base_url=root, prediction=hacker_prediction, cleared=solved),
    ]
    lanes.sort(key=lambda row: ({"now": 0, "next": 1, "hold": 2, "maintain": 3}.get(str(row.get("queue")), 9), _int(row.get("rank"), 99)))

    status_view = {
        "status": status,
        "metric_label": metric,
        "counts_as_solved": solved,
        "paid_confirmed": paid_confirmed,
        "return_compute_confirmed": return_compute_confirmed,
        "external_paid_count": external["paid_count"],
        "recognized_revenue_usd": round(max(external["recognized_usd"], work["recognized_usd"]), 4),
        "return_receipt_count": exchange["return_receipt_count"],
        "settled_return_work_credits": exchange["settled_return_work_credits"],
        "adapter_first_fix_count": adapter["first_fix_count"],
    }
    next_lane = next((row for row in lanes if row.get("queue") == "now"), lanes[0] if lanes else {})
    required_to_clear = [
        "positive_paid_receipt_in_external_value_or_work_receipts",
        "or_verified_return_compute_receipt_in_work_exchange",
        "public_proof_digest",
        "no_secret_material",
    ]
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "read_url": _u(root, "/swarm/bottleneck-resolver"),
        "well_known_url": _u(root, "/.well-known/nomad-bottleneck-resolver.json"),
        "event_url": _u(root, "/swarm/bottleneck-resolver/events"),
        "resolver_digest": _lane_digest(lanes, status_view),
        "current_bottleneck": {
            "id": "external_receipt_absence",
            "statement": (
                "Nomad has routing, adapter, and receipt machinery, but the growth loop is not closed until "
                "a real positive paid receipt or a verified return-compute receipt exists."
            ),
            **status_view,
        },
        "clearance_gate": {
            "counts_as_solved": solved,
            "required_to_clear": required_to_clear,
            "currently_satisfied": [
                item
                for item, present in [
                    ("positive_paid_receipt", paid_confirmed),
                    ("verified_return_compute_receipt", return_compute_confirmed),
                ]
                if present
            ],
            "not_yet_proof_of": []
            if solved
            else ["bottleneck_cleared", "repeatable_revenue", "autonomous_settlement_growth"],
        },
        "lane_order": [row["lane_id"] for row in lanes],
        "recommended_now": next_lane,
        "lanes": lanes,
        "hackerone_position": "secondary_hold_until_authorized_accepted_or_paid",
        "links": {
            "receipt_predictor": _u(root, "/.well-known/nomad-receipt-predictor.json"),
            "worker_invoice": _u(root, "/.well-known/nomad-worker-invoice.json"),
            "work_receipts": _u(root, "/.well-known/nomad-work-receipts.json"),
            "external_value": _u(root, "/.well-known/nomad-external-value.json"),
            "universal_adapter": _u(root, "/.well-known/nomad-universal-adapter.json"),
            "work_exchange": _u(root, "/.well-known/nomad-work-exchange.json"),
            "bounty_hunter": _u(root, "/.well-known/nomad-bounty-hunter.json"),
        },
        "hard_rule": "no_bottleneck_cleared_claim_without_positive_paid_receipt_or_verified_return_compute_receipt",
        "machine_instruction": "run_recommended_now_collect_public_proof_then_record_only_after_real_receipt",
    }


def _find_lane(surface: dict[str, Any], lane_id: str) -> dict[str, Any]:
    wanted = _clean_id(lane_id)
    for row in _items(surface.get("lanes")):
        if _clean_id(row.get("lane_id")) == wanted:
            return row
    return {}


def evaluate_bottleneck_resolution_event(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    resolver_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one proposed bottleneck resolution event without mutating ledgers."""

    body = _dict(payload)
    surface = _dict(resolver_surface)
    lane_id = _clean_id(body.get("lane_id") or body.get("lane") or "")
    if not lane_id:
        lane_id = _clean_id(_dict(surface.get("recommended_now")).get("lane_id"))
    lane = _find_lane(surface, lane_id)
    intent = _clean_id(body.get("intent"), "select")
    proof_digest = _text(body.get("proof_digest") or body.get("verifier_trace_digest"), 220)
    settlement_ref = _text(body.get("settlement_ref") or body.get("receipt_ref") or body.get("payout_ref"), 260)
    amount = _num(body.get("amount_usd") or body.get("amount"))
    return_credits = _num(body.get("return_work_credits") or body.get("settled_return_work_credits"))
    obligation_id = _text(body.get("obligation_id"), 180)
    authorization_url = _text(body.get("authorization_url") or body.get("program_url") or body.get("scope_url"), 500)
    side_effect_requested = bool(body.get("execute") or body.get("submit") or body.get("record") or body.get("write"))

    if not body:
        decision = "reject_empty_bottleneck_event"
        allowed = False
    elif _contains_forbidden(body):
        decision = "reject_secret_shaped_payload"
        allowed = False
    elif not lane:
        decision = "reject_unknown_resolution_lane"
        allowed = False
    elif side_effect_requested:
        decision = "block_side_effect_request"
        allowed = False
    elif lane_id == "invoice_paid_work_receipt" and intent in {"paid", "clear", "commit"} and not _digest_present(proof_digest):
        decision = "hold_until_proof_digest"
        allowed = False
    elif lane_id == "invoice_paid_work_receipt" and intent in {"paid", "clear", "commit"} and (amount <= 0.0 or not settlement_ref):
        decision = "hold_until_positive_paid_receipt"
        allowed = False
    elif lane_id == "work_exchange_return_compute_receipt" and intent in {"return_compute", "clear", "commit"} and not _digest_present(proof_digest):
        decision = "hold_until_return_work_proof_digest"
        allowed = False
    elif lane_id == "work_exchange_return_compute_receipt" and intent in {"return_compute", "clear", "commit"} and (return_credits <= 0.0 or not obligation_id):
        decision = "hold_until_positive_return_compute_receipt"
        allowed = False
    elif lane_id == "hackerone_authorized_bounty_cycle" and not authorization_url:
        decision = "hold_until_authorized_program_scope"
        allowed = False
    elif lane_id == "hackerone_authorized_bounty_cycle" and intent in {"paid", "clear", "commit"} and (amount <= 0.0 or not settlement_ref or not _digest_present(proof_digest)):
        decision = "hold_until_accepted_or_paid_bounty_receipt"
        allowed = False
    else:
        decision = "allow_resolution_packet"
        allowed = True

    core = {
        "lane_id": lane_id,
        "intent": intent,
        "proof_digest": proof_digest,
        "settlement_ref": settlement_ref,
        "amount_usd": amount,
        "return_work_credits": return_credits,
        "decision": decision,
    }
    return {
        "ok": True,
        "schema": EVENT_SCHEMA,
        "generated_at": _iso_now(),
        "event_id": f"nomad-bottleneck-resolution-event-{_digest({**core, 't': _iso_now()}, 18)}",
        "lane_id": lane_id,
        "intent": intent,
        "resolution_packet_allowed": allowed,
        "decision": decision,
        "selected_lane": lane,
        "evidence_status": {
            "proof_digest_present": _digest_present(proof_digest),
            "settlement_ref_present": bool(settlement_ref),
            "positive_amount_present": amount > 0.0,
            "obligation_id_present": bool(obligation_id),
            "positive_return_work_credits_present": return_credits > 0.0,
            "authorization_url_present": bool(authorization_url),
            "side_effect_requested": side_effect_requested,
        },
        "candidate_digest": "sha256:" + _digest(core, 32),
        "recommended_writes_after_real_receipt": {
            "external_value": _u(base_url, "/swarm/external-value"),
            "work_receipts": _u(base_url, "/swarm/work-receipts"),
            "work_exchange_return_work": _u(base_url, "/swarm/work-exchange/return-work"),
        },
        "counts_as_revenue": False,
        "counts_as_bottleneck_cleared": False,
        "side_effect_allowed": False,
        "hard_rule": "resolver_events_prepare_evidence_only; ledger_revenue_moves_only_after_real_receipt_posts",
    }
