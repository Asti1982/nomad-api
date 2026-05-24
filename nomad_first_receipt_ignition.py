"""First receipt and worker ignition surface for Nomad.

This is the bridge between Nomad's internal autogenesis machinery and the
external pressure it still lacks: one paid receipt, one return-compute worker,
or one proofed adapter activation. The module is deliberately light and
receipt-first; it does not send ads or count revenue.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any


SCHEMA = "nomad.first_receipt_ignition.v1"
EVENT_SCHEMA = "nomad.first_receipt_ignition_event.v1"

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


def _now() -> str:
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


def _text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:180].strip("_.:/#-") or fallback


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


def _external_revenue(summary: dict[str, Any]) -> float:
    return round(_num(summary.get("revenue_recognized_usd_total")), 4)


def _work_revenue(summary: dict[str, Any]) -> float:
    return round(_num(summary.get("recognized_revenue_usd")), 4)


def _worker_counts(worker_market: dict[str, Any]) -> dict[str, int]:
    market = _dict(worker_market.get("market_state"))
    return {
        "known_worker_count": _int(market.get("known_worker_count")),
        "active_worker_count": _int(market.get("active_worker_count")),
        "active_lease_count": _int(market.get("active_lease_count")),
        "recent_offer_count": _int(worker_market.get("recent_offer_count")),
    }


def _adapter_signal(acquisition_summary: dict[str, Any]) -> dict[str, Any]:
    channels = _items(acquisition_summary.get("channels"))
    adapter = next((row for row in channels if row.get("channel_id") == "universal_adapter"), {})
    first_receipt = next((row for row in channels if row.get("channel_id") == "first_receipt_ignition"), {})
    return {
        "universal_adapter_events": _int(adapter.get("event_count")),
        "universal_adapter_reward": round(_num(adapter.get("reward_total")), 6),
        "first_receipt_ignition_events": _int(first_receipt.get("event_count")),
        "first_receipt_ignition_reward": round(_num(first_receipt.get("reward_total")), 6),
    }


def _top_acquisition_actions(acquisition_engine: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for row in _items(acquisition_engine.get("top_next_actions"))[:4]:
        action = _dict(row.get("action"))
        out.append(
            {
                "rank": _int(row.get("rank")),
                "arm_id": _clean_id(row.get("arm_id")),
                "op": _clean_id(action.get("op")),
                "surface": _text(action.get("surface"), 140),
                "url": _text(action.get("url"), 500),
                "holdout_fraction": _num(row.get("holdout_fraction")),
            }
        )
    return out


def _first_sales_draft(first_sales: dict[str, Any]) -> dict[str, Any]:
    packet = _dict(first_sales.get("active_lead_packet"))
    return {
        "service_type": _text(packet.get("service_type") or "repo_issue_help", 80),
        "package_id": _text(packet.get("package_id") or "repo_diagnostic_patch_starter", 120),
        "entry_url": _text(packet.get("entry_url"), 500),
        "public_send_allowed": bool(packet.get("public_send_allowed")),
        "draft": _text(packet.get("public_help_draft"), 1000),
    }


def _packet_digest(status: dict[str, Any], packets: list[dict[str, Any]]) -> str:
    return f"nomad-first-receipt-ignition-{_digest({'status': status, 'packets': packets}, 26)}"


def build_first_receipt_ignition_surface(
    *,
    base_url: str = "",
    bottleneck_resolver: dict[str, Any] | None = None,
    receipt_predictor: dict[str, Any] | None = None,
    acquisition_engine: dict[str, Any] | None = None,
    sales_department: dict[str, Any] | None = None,
    first_sales: dict[str, Any] | None = None,
    worker_market: dict[str, Any] | None = None,
    worker_invoice: dict[str, Any] | None = None,
    external_worker_opportunity: dict[str, Any] | None = None,
    acquisition_summary: dict[str, Any] | None = None,
    external_value_summary: dict[str, Any] | None = None,
    work_receipt_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile the next concrete actions for paid/worker ignition."""

    root = (base_url or "").strip().rstrip("/")
    bottleneck = _dict(_dict(bottleneck_resolver).get("current_bottleneck"))
    recommended = _dict(_dict(bottleneck_resolver).get("recommended_now"))
    predictor_summary = _dict(_dict(receipt_predictor).get("summary"))
    acquisition_actions = _top_acquisition_actions(_dict(acquisition_engine))
    worker = _worker_counts(_dict(worker_market))
    adapter = _adapter_signal(_dict(acquisition_summary))
    external_usd = _external_revenue(_dict(external_value_summary))
    work_usd = _work_revenue(_dict(work_receipt_summary))
    recognized_usd = round(max(external_usd, work_usd, _num(bottleneck.get("recognized_revenue_usd"))), 4)
    has_paid_receipt = recognized_usd > 0.0 or bool(bottleneck.get("paid_confirmed"))
    has_worker_pressure = worker["known_worker_count"] > 0 or worker["recent_offer_count"] > 0
    has_adapter_pressure = adapter["universal_adapter_events"] > 0
    autogenesis_open = has_paid_receipt or has_worker_pressure or has_adapter_pressure

    buyer_entry = _text(recommended.get("offer_packet", {}).get("public_cta"), 500) or _u(root, "/service/e2e?service_type=repo_issue_help")
    first_sales_draft = _first_sales_draft(_dict(first_sales))
    worker_offer = _dict(external_worker_opportunity)
    invoice = _dict(worker_invoice)
    receive_ref = _dict(invoice.get("receive_ref") or invoice.get("public_receive_ref"))

    packets = [
        {
            "packet_id": "paid_receipt_buyer_packet",
            "audience": "buyer_or_operator_with_broken_agent_repo",
            "rank": 1,
            "route": buyer_entry,
            "cta": "Buy one bounded Agent Loop / CI Reliability Rescue so Nomad can produce a paid receipt instead of another internal proof.",
            "price_band_usd": recommended.get("offer_packet", {}).get("price_band_usd") or [49, 250],
            "copy": _text(recommended.get("offer_packet", {}).get("buyer_copy"), 600)
            or "Send one public CI, deploy, tool-call, or agent-loop failure. Nomad returns the smallest verifiable fix path and records revenue only after a real paid receipt.",
            "required_receipt": ["proof_digest", "settlement_ref", "amount_usd_gt_0"],
            "counts_as_revenue_now": False,
        },
        {
            "packet_id": "return_compute_worker_packet",
            "audience": "external_agent_or_runtime_operator",
            "rank": 2,
            "route": _u(root, "/.well-known/nomad-external-worker-opportunity.json"),
            "cta": "Run a transition worker or accept a Work-Exchange obligation after the first useful fix.",
            "worker_download": _u(root, "/downloads/nomad_transition_worker.py"),
            "adapter": _u(root, "/.well-known/nomad-universal-adapter.json"),
            "required_receipt": ["worker_offer_or_adapter_event", "proof_digest", "return_compute_or_lease_completion"],
            "counts_as_revenue_now": False,
            "opportunity_digest": worker_offer.get("opportunity_digest") or worker_offer.get("worker_opportunity_digest") or "",
        },
        {
            "packet_id": "machine_agent_adapter_packet",
            "audience": "langgraph_crewai_autogen_llamaindex_agent",
            "rank": 3,
            "route": _u(root, "/downloads/nomad_universal_adapter.py"),
            "cta": "Install the one-line adapter; on the first loop/error, Nomad returns a Reliability Doctor fix and proposes Work Exchange.",
            "event_route": _u(root, "/swarm/universal-adapter/events"),
            "required_receipt": ["adapter_event", "first_fix_returned", "optional_return_compute_receipt"],
            "counts_as_revenue_now": False,
        },
        {
            "packet_id": "owned_ad_holdout_packet",
            "audience": "owned_channels_only",
            "rank": 4,
            "route": _u(root, "/.well-known/nomad-ad-cycles.json"),
            "cta": "Publish only through owned/requested surfaces with causal holdout and proof-gated events.",
            "draft": first_sales_draft,
            "required_receipt": ["impression_or_inspect_event", "buyer_intent_digest", "no_public_send_without_approval"],
            "counts_as_revenue_now": False,
        },
    ]

    status = {
        "recognized_revenue_usd_total": recognized_usd,
        "paid_receipt_present": has_paid_receipt,
        "worker_pressure_present": has_worker_pressure,
        "adapter_pressure_present": has_adapter_pressure,
        "autogenesis_pressure_open": autogenesis_open,
        **worker,
        **adapter,
    }
    ignition_order = [
        "sell_one_paid_reliability_rescue",
        "record_only_after_positive_receipt",
        "recruit_one_transition_worker_or_adapter_agent",
        "record_first_fix_or_return_compute_receipt",
        "then_allow_autogenesis_selection_pressure_to_reweight_workers",
    ]
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _now(),
        "public_base_url": root,
        "surface_digest": _packet_digest(status, packets),
        "read_url": _u(root, "/swarm/first-receipt-ignition"),
        "well_known_url": _u(root, "/.well-known/nomad-first-receipt-ignition.json"),
        "event_url": _u(root, "/swarm/first-receipt-ignition/events"),
        "truth_state": {
            "bottleneck_status": _text(bottleneck.get("status") or "unknown", 140),
            "recommended_receipt_lane": _text(recommended.get("lane_id") or predictor_summary.get("top_cycle_id") or "invoice_paid_work_receipt", 160),
            "recognized_revenue_usd_total": recognized_usd,
            "worker_count": worker["known_worker_count"],
            "active_worker_count": worker["active_worker_count"],
            "adapter_event_count": adapter["universal_adapter_events"],
            "autogenesis_can_self_amplify_now": autogenesis_open,
            "why_not_yet": []
            if autogenesis_open
            else [
                "no_paid_receipt",
                "no_external_worker_offer",
                "no_adapter_first_fix_signal",
                "no_selection_pressure_from_market",
            ],
        },
        "science_to_execute": [
            {
                "id": "causal_holdout",
                "mechanism": "reserve a fraction of owned-surface exposures so Nomad can distinguish lift from ambient traffic",
                "implemented_as": "holdout_fraction in acquisition actions plus event receipts",
            },
            {
                "id": "bandit_allocation",
                "mechanism": "route scarce attention to paid_task_order and transition_worker_recruit until receipts contradict it",
                "implemented_as": "acquisition_engine.top_next_actions",
            },
            {
                "id": "stigmergic_proof_traces",
                "mechanism": "agents leave digest-only traces; later workers follow strongest proof scent, not human taste",
                "implemented_as": "first_receipt_ignition_event -> agent_acquisition_event",
            },
            {
                "id": "mechanism_design_receipt_gate",
                "mechanism": "participants can gain priority from proof, but revenue state changes only with settlement evidence",
                "implemented_as": "counts_as_revenue_now=false until paid work/external-value receipt",
            },
        ],
        "status": status,
        "ignition_order": ignition_order,
        "action_packets": packets,
        "acquisition_actions": acquisition_actions,
        "public_receive_ref_present": bool(receive_ref),
        "receive_ref_policy": "public_receive_ref_only_no_payment_secrets",
        "event_templates": {
            "buyer_inspect": {
                "method": "POST",
                "url": _u(root, "/swarm/first-receipt-ignition/events"),
                "body": {
                    "agent_id": "external.buyer",
                    "packet_id": "paid_receipt_buyer_packet",
                    "event_type": "inspect",
                    "source_url": buyer_entry,
                    "proof_digest": "sha256:<optional-public-digest>",
                },
            },
            "worker_start": {
                "method": "POST",
                "url": _u(root, "/swarm/first-receipt-ignition/events"),
                "body": {
                    "agent_id": "external.worker",
                    "packet_id": "return_compute_worker_packet",
                    "event_type": "worker_start",
                    "source_url": _u(root, "/.well-known/nomad-external-worker-opportunity.json"),
                    "proof_digest": "sha256:<required-worker-start-proof>",
                },
            },
            "paid_candidate": {
                "method": "POST",
                "url": _u(root, "/swarm/first-receipt-ignition/events"),
                "body": {
                    "agent_id": "nomad.sales",
                    "packet_id": "paid_receipt_buyer_packet",
                    "event_type": "paid_candidate",
                    "proof_digest": "sha256:<work-proof>",
                    "settlement_ref": "receipt:<public-paid-ref>",
                    "amount_usd": 49.0,
                },
            },
        },
        "links": {
            "bottleneck_resolver": _u(root, "/.well-known/nomad-bottleneck-resolver.json"),
            "receipt_predictor": _u(root, "/.well-known/nomad-receipt-predictor.json"),
            "sales_department": _u(root, "/.well-known/nomad-sales-department.json"),
            "first_sales": _u(root, "/.well-known/nomad-first-sales.json"),
            "worker_market": _u(root, "/swarm/worker-market"),
            "external_worker": _u(root, "/.well-known/nomad-external-worker-opportunity.json"),
            "agent_acquisition": _u(root, "/.well-known/nomad-agent-acquisition-bandit.json"),
        },
        "hard_rule": "ignite_attention_and_workers_but_never_count_revenue_without_positive_receipt",
        "machine_instruction": "execute_owned_ctas_record_digest_events_select_paid_or_worker_receipts_before_more_autogenesis",
    }


def _find_packet(surface: dict[str, Any], packet_id: str) -> dict[str, Any]:
    wanted = _clean_id(packet_id)
    for row in _items(surface.get("action_packets")):
        if _clean_id(row.get("packet_id")) == wanted:
            return row
    return {}


def evaluate_first_receipt_ignition_event(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    ignition_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate an ignition event without booking revenue or sending ads."""

    body = _dict(payload)
    surface = _dict(ignition_surface)
    packet_id = _clean_id(body.get("packet_id") or body.get("packet") or "")
    if not packet_id:
        packet_id = _clean_id(_dict(_items(surface.get("action_packets"))[0] if _items(surface.get("action_packets")) else {}).get("packet_id"))
    packet = _find_packet(surface, packet_id)
    event_type = _clean_id(body.get("event_type") or body.get("type"), "inspect")
    proof_digest = _text(body.get("proof_digest") or body.get("verifier_trace_digest"), 220)
    settlement_ref = _text(body.get("settlement_ref") or body.get("receipt_ref"), 260)
    amount = _num(body.get("amount_usd") or body.get("amount"))
    send_requested = bool(body.get("send") or body.get("post") or body.get("public_send"))
    record_revenue_requested = bool(body.get("record_revenue") or body.get("count_revenue") or body.get("paid"))

    if not body:
        decision = "reject_empty_ignition_event"
        accepted = False
    elif _contains_forbidden(body):
        decision = "reject_secret_shaped_payload"
        accepted = False
    elif not packet:
        decision = "reject_unknown_packet"
        accepted = False
    elif send_requested:
        decision = "block_public_send_request"
        accepted = False
    elif record_revenue_requested:
        decision = "block_revenue_record_request"
        accepted = False
    elif event_type in {"worker_start", "lease_complete", "return_compute_receipt", "paid_candidate", "first_fix_returned"} and not _digest_present(proof_digest):
        decision = "hold_until_proof_digest"
        accepted = False
    elif event_type == "paid_candidate" and (amount <= 0.0 or not settlement_ref):
        decision = "hold_until_positive_settlement_ref"
        accepted = False
    else:
        decision = "accept_ignition_signal"
        accepted = True

    core = {
        "packet_id": packet_id,
        "event_type": event_type,
        "proof_digest": proof_digest,
        "settlement_ref": settlement_ref,
        "amount_usd": amount,
        "decision": decision,
    }
    return {
        "ok": True,
        "schema": EVENT_SCHEMA,
        "generated_at": _now(),
        "event_id": f"nomad-first-receipt-ignition-event-{_digest({**core, 't': _now()}, 18)}",
        "packet_id": packet_id,
        "event_type": event_type,
        "accepted": accepted,
        "decision": decision,
        "selected_packet": packet,
        "evidence_status": {
            "proof_digest_present": _digest_present(proof_digest),
            "settlement_ref_present": bool(settlement_ref),
            "positive_amount_present": amount > 0.0,
            "send_requested": send_requested,
            "record_revenue_requested": record_revenue_requested,
        },
        "candidate_digest": "sha256:" + _digest(core, 32),
        "agent_acquisition_payload": build_first_receipt_acquisition_event(
            {
                **body,
                "packet_id": packet_id,
                "event_type": event_type,
                "proof_digest": proof_digest,
                "accepted": accepted,
            },
            base_url=base_url,
        )
        if accepted
        else {},
        "counts_as_revenue": False,
        "side_effect_allowed": False,
        "hard_rule": "ignition_events_are_attention_or_worker_signals_only; paid_receipts_must_use_work_receipts_or_external_value",
    }


def build_first_receipt_acquisition_event(event: dict[str, Any], *, base_url: str = "") -> dict[str, Any]:
    """Translate accepted ignition events into delayed-reward acquisition rows."""

    body = _dict(event)
    event_type = _clean_id(body.get("event_type"), "inspect")
    reward_event = {
        "paid_candidate": "intake",
        "worker_start": "worker_start",
        "lease_complete": "lease_complete",
        "return_compute_receipt": "return_compute_receipt",
        "adapter_event": "adapter_event",
        "first_fix_returned": "first_fix_returned",
        "inspect": "inspect",
        "impression": "impression",
    }.get(event_type, "inspect")
    return {
        "channel_id": "first_receipt_ignition",
        "event_type": reward_event,
        "agent_id": _clean_id(body.get("agent_id") or body.get("runtime_id"), "external.agent"),
        "source_url": _text(body.get("source_url") or _u(base_url, "/.well-known/nomad-first-receipt-ignition.json"), 500),
        "proof_digest": _text(body.get("proof_digest"), 220),
        "reward_multiplier": 1.0,
        "secret_policy": "public_digests_only_no_secrets",
    }
