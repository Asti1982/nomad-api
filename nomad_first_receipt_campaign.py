"""First receipt campaign controller for Nomad.

This module turns Nomad's current bottleneck into a small machine-executable
campaign: find concrete agent/CI/deploy pain, return one proofed first fix,
then request either a paid receipt or return compute. It is deliberately
lightweight and side-effect free; it does not send outreach or book revenue.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any


SCHEMA = "nomad.first_receipt_campaign.v1"
EVENT_SCHEMA = "nomad.first_receipt_campaign_event.v1"

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

DEFAULT_QUERIES = [
    'repo:langchain-ai/langgraph "tool" "error" is:issue is:open',
    'repo:crewAIInc/crewAI "deployment" is:issue is:open',
    'repo:microsoft/autogen "tool" "timeout" is:issue is:open',
    'repo:run-llama/llama_index "agent" "error" is:issue is:open',
    'repo:openai/openai-agents-python "tool" "400" is:issue is:open',
    'repo:modelcontextprotocol/servers "tool" "not found" is:issue is:open',
    '"LangGraph" "CI" "agent" is:issue is:open',
    '"CrewAI" "deploy" "error" is:issue is:open',
    '"AutoGen" "tool call" "error" is:issue is:open',
    '"MCP" "agent" "transport" is:issue is:open',
]


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


def _profile_queries(lead_profile: dict[str, Any], *, limit: int = 10) -> list[dict[str, Any]]:
    queries: list[str] = []
    for key in ("seed_queries", "queries"):
        for query in lead_profile.get(key) or []:
            if isinstance(query, str) and query.strip():
                queries.append(query.strip())
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for query in [*queries, *DEFAULT_QUERIES]:
        if query in seen:
            continue
        seen.add(query)
        rows.append(
            {
                "query_id": f"lead-query-{len(rows) + 1:02d}",
                "query": query,
                "focus": _text(lead_profile.get("service_type") or "agent_reliability_rescue", 100),
                "success_event": "lead_observed",
                "holdout_fraction": 0.2,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _channel(summary: dict[str, Any], channel_id: str) -> dict[str, Any]:
    for row in _items(summary.get("channels")):
        if str(row.get("channel_id") or "") == channel_id:
            return row
    return {}


def _truth(
    *,
    bottleneck_resolver: dict[str, Any],
    first_receipt_ignition: dict[str, Any],
    acquisition_summary: dict[str, Any],
    worker_market: dict[str, Any],
) -> dict[str, Any]:
    ignition_truth = _dict(first_receipt_ignition.get("truth_state"))
    bottleneck = _dict(bottleneck_resolver.get("current_bottleneck"))
    market_state = _dict(worker_market.get("market_state"))
    campaign_channel = _channel(acquisition_summary, "first_receipt_campaign")
    adapter_channel = _channel(acquisition_summary, "universal_adapter")
    paid = bool(ignition_truth.get("paid_bottleneck_resolved")) or bool(bottleneck.get("paid_confirmed"))
    revenue = max(
        _num(ignition_truth.get("recognized_revenue_usd_total")),
        _num(bottleneck.get("recognized_revenue_usd")),
    )
    active_workers = max(_int(ignition_truth.get("active_worker_count")), _int(market_state.get("active_worker_count")))
    known_workers = max(_int(ignition_truth.get("worker_count")), _int(market_state.get("known_worker_count")))
    adapter_events = max(_int(ignition_truth.get("adapter_event_count")), _int(adapter_channel.get("event_count")))
    campaign_events = _int(campaign_channel.get("event_count"))
    return {
        "recognized_revenue_usd_total": round(revenue, 4),
        "paid_bottleneck_resolved": paid or revenue > 0.0,
        "active_worker_count": active_workers,
        "known_worker_count": known_workers,
        "adapter_event_count": adapter_events,
        "campaign_event_count": campaign_events,
        "self_funding_loop_closed": bool(ignition_truth.get("self_funding_loop_closed")) and revenue > 0.0,
        "autogenesis_can_self_amplify_now": bool(ignition_truth.get("autogenesis_can_self_amplify_now")) and revenue > 0.0,
    }


def _campaign_slots(*, root: str, lead_queries: list[dict[str, Any]], truth: dict[str, Any]) -> list[dict[str, Any]]:
    paid_blocked = not bool(truth.get("paid_bottleneck_resolved"))
    slots: list[dict[str, Any]] = []
    for idx, query in enumerate(lead_queries[:4], start=1):
        slots.append(
            {
                "slot_id": f"lead-scout-{idx:02d}",
                "rank": len(slots) + 1,
                "lane": "paid_customer",
                "action": "run_read_only_lead_scout",
                "query": query.get("query", ""),
                "why": "Find a concrete public AI-agent, CI, deploy, or tool-call failure with receipt proximity.",
                "event_to_record": "lead_observed",
                "holdout_fraction": query.get("holdout_fraction", 0.2),
                "side_effect_policy": "read_only_no_public_post",
            }
        )
    slots.extend(
        [
            {
                "slot_id": "first-fix-packet",
                "rank": len(slots) + 1,
                "lane": "paid_customer",
                "action": "prepare_secret_free_first_fix",
                "route": _u(root, "/swarm/reliability-doctor/intake"),
                "why": "Give one useful diagnosis before asking for payment or return compute.",
                "event_to_record": "first_fix_prepared",
                "required_receipt": ["proof_digest", "public_failure_url_or_digest"],
                "side_effect_policy": "private_draft_until_approved",
            },
            {
                "slot_id": "paid-rescue-offer",
                "rank": len(slots) + 2,
                "lane": "paid_customer",
                "action": "offer_small_paid_rescue",
                "route": _u(root, "/service/e2e?service_type=repo_issue_help"),
                "price_band_usd": [49, 250],
                "why": "Shortest route to the missing paid receipt.",
                "event_to_record": "buyer_intent",
                "required_receipt": ["buyer_intent_digest"],
                "side_effect_policy": "owned_surface_or_explicit_buyer_context_only",
            },
            {
                "slot_id": "universal-adapter-activation",
                "rank": len(slots) + 3,
                "lane": "agent_worker",
                "action": "activate_one_line_adapter",
                "route": _u(root, "/downloads/nomad_universal_adapter.py"),
                "why": "Attach to LangGraph/CrewAI/AutoGen/LlamaIndex failure loops where the first fix has immediate utility.",
                "event_to_record": "adapter_activation",
                "required_receipt": ["proof_digest", "first_fix_returned"],
                "side_effect_policy": "local_install_opt_in_only",
            },
            {
                "slot_id": "github-action-worker",
                "rank": len(slots) + 4,
                "lane": "agent_worker",
                "action": "install_ci_doctor_action",
                "route": _u(root, "/downloads/nomad_reliability_doctor_action.yml"),
                "why": "Turn CI failure into recurring proofed worker intake.",
                "event_to_record": "adapter_activation",
                "required_receipt": ["workflow_run_url", "proof_digest"],
                "side_effect_policy": "repo_owner_opt_in_only",
            },
            {
                "slot_id": "return-compute-worker",
                "rank": len(slots) + 5,
                "lane": "worker_supply",
                "action": "recruit_return_compute_worker",
                "route": _u(root, "/.well-known/nomad-external-worker-opportunity.json"),
                "why": "Convert useful free fixes into verified return-compute receipts.",
                "event_to_record": "worker_start",
                "required_receipt": ["lease_id_or_proof_digest"],
                "side_effect_policy": "worker_opt_in_only",
            },
            {
                "slot_id": "receipt-write-gate",
                "rank": len(slots) + 6,
                "lane": "settlement",
                "action": "write_receipt_only_after_settlement",
                "route": _u(root, "/swarm/work-receipts"),
                "why": "Do not mark the bottleneck solved until proof, amount, and settlement reference exist.",
                "event_to_record": "paid_candidate",
                "required_receipt": ["proof_digest", "settlement_ref", "amount_usd_gt_0"],
                "side_effect_policy": "no_revenue_booking_from_campaign_event",
            },
        ]
    )
    for slot in slots:
        slot["paid_bottleneck_targeted"] = paid_blocked and slot.get("lane") != "settlement"
    return slots[:10]


def build_first_receipt_campaign_surface(
    *,
    base_url: str = "",
    bottleneck_resolver: dict[str, Any] | None = None,
    first_receipt_ignition: dict[str, Any] | None = None,
    acquisition_summary: dict[str, Any] | None = None,
    lead_profile: dict[str, Any] | None = None,
    worker_market: dict[str, Any] | None = None,
    adapter_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile Nomad's next proof-gated campaign for first revenue/worker growth."""

    root = (base_url or "").strip().rstrip("/")
    bottleneck = _dict(bottleneck_resolver)
    ignition = _dict(first_receipt_ignition)
    acquisition = _dict(acquisition_summary)
    profile = _dict(lead_profile)
    market = _dict(worker_market)
    adapter = _dict(adapter_surface)
    truth = _truth(
        bottleneck_resolver=bottleneck,
        first_receipt_ignition=ignition,
        acquisition_summary=acquisition,
        worker_market=market,
    )
    lead_queries = _profile_queries(profile, limit=10)
    slots = _campaign_slots(root=root, lead_queries=lead_queries, truth=truth)
    paid_missing = not bool(truth.get("paid_bottleneck_resolved"))
    adapter_missing = _int(truth.get("adapter_event_count")) <= 0
    worker_pressure = _int(truth.get("active_worker_count")) > 0
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _now(),
        "public_base_url": root,
        "surface_digest": "nomad-first-receipt-campaign-" + _digest({"truth": truth, "slots": slots}, 26),
        "read_url": _u(root, "/swarm/first-receipt-campaign"),
        "well_known_url": _u(root, "/.well-known/nomad-first-receipt-campaign.json"),
        "event_url": _u(root, "/swarm/first-receipt-campaign/events"),
        "truth_state": {
            **truth,
            "current_bottleneck": "no_paid_receipt" if paid_missing else "repeat_paid_receipts",
            "next_receipt": "paid_agent_loop_rescue" if paid_missing else "repeat_or_expand",
            "why_not_yet": []
            if not paid_missing
            else ["no_paid_receipt"],
        },
        "recommended_now": {
            "action": "run_first_receipt_campaign",
            "lane": "paid_customer" if paid_missing else "repeatability",
            "focus": _text(profile.get("service_type") or "agent_infra_prime", 100),
            "target_count": len(slots),
            "worker_pressure_present": worker_pressure,
            "adapter_missing": adapter_missing,
            "offer": {
                "title": "Agent Loop / CI Reliability Rescue",
                "price_band_usd": [49, 250],
                "entry_url": _u(root, "/service/e2e?service_type=repo_issue_help"),
                "first_fix_route": _u(root, "/swarm/reliability-doctor/intake"),
            },
        },
        "campaign_slots": slots,
        "lead_queries": lead_queries,
        "science_protocols": [
            {
                "id": "causal_holdout",
                "implemented_as": "holdout_fraction on lead scout slots",
                "rule": "measure lift; do not trust raw traffic",
            },
            {
                "id": "bandit_allocation",
                "implemented_as": "first_receipt_campaign events feed acquisition bandit",
                "rule": "give more slots only to channels producing proof or receipts",
            },
            {
                "id": "proof_gated_incentives",
                "implemented_as": "first_fix_prepared, worker_start, adapter_activation, paid_candidate proof gates",
                "rule": "priority follows verified usefulness, not persuasive text",
            },
            {
                "id": "stigmergic_trace_market",
                "implemented_as": "public digest events instead of private coordination threads",
                "rule": "later workers follow proof traces left by earlier workers",
            },
            {
                "id": "fast_first_fix",
                "implemented_as": "diagnose first, ask for paid receipt or return compute second",
                "rule": "reduce adoption friction before negotiating value exchange",
            },
        ],
        "adapter_contract": {
            "route": _u(root, "/.well-known/nomad-universal-adapter.json"),
            "download": _u(root, "/downloads/nomad_universal_adapter.py"),
            "schema": adapter.get("schema") or "nomad.universal_adapter.v1",
        },
        "hard_rules": [
            "no_public_send_without_human_approval_and_buyer_intent_digest",
            "no_revenue_counted_without_positive_receipt",
            "no_secret_payloads",
            "campaign_events_are_attribution_signals_not_cash_receipts",
        ],
        "event_templates": {
            "lead_observed": {
                "method": "POST",
                "url": _u(root, "/swarm/first-receipt-campaign/events"),
                "body": {
                    "agent_id": "nomad.campaign",
                    "event_type": "lead_observed",
                    "lead_url": "https://github.com/org/repo/issues/123",
                    "proof_digest": "sha256:<optional-public-digest>",
                },
            },
            "first_fix_prepared": {
                "method": "POST",
                "url": _u(root, "/swarm/first-receipt-campaign/events"),
                "body": {
                    "agent_id": "nomad.campaign",
                    "event_type": "first_fix_prepared",
                    "lead_url": "https://github.com/org/repo/issues/123",
                    "proof_digest": "sha256:<diagnosis-or-patch-proof>",
                },
            },
            "paid_candidate": {
                "method": "POST",
                "url": _u(root, "/swarm/first-receipt-campaign/events"),
                "body": {
                    "agent_id": "nomad.campaign",
                    "event_type": "paid_candidate",
                    "lead_url": "https://github.com/org/repo/issues/123",
                    "proof_digest": "sha256:<work-proof>",
                    "settlement_ref": "receipt:<public-paid-ref>",
                    "amount_usd": 49.0,
                },
            },
        },
        "machine_instruction": "run_slots_in_rank_order_record_events_never_book_revenue_from_campaign_signal",
    }


def evaluate_first_receipt_campaign_event(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    campaign_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate a campaign event without sending outreach or booking revenue."""

    body = _dict(payload)
    event_type = _clean_id(body.get("event_type") or body.get("type"), "lead_observed")
    lead_url = _text(body.get("lead_url") or body.get("source_url") or body.get("work_url"), 600)
    proof_digest = _text(body.get("proof_digest") or body.get("verifier_trace_digest"), 220)
    buyer_intent_digest = _text(body.get("buyer_intent_digest"), 220)
    settlement_ref = _text(body.get("settlement_ref") or body.get("receipt_ref") or body.get("public_payout_ref"), 260)
    amount = _num(body.get("amount_usd") or body.get("amount"))
    send_requested = bool(body.get("send") or body.get("post") or body.get("public_send"))
    human_approved = bool(body.get("human_approved") or body.get("operator_approved"))
    record_revenue_requested = bool(body.get("record_revenue") or body.get("count_revenue") or body.get("paid"))

    proof_required = {
        "first_fix_prepared",
        "adapter_activation",
        "worker_start",
        "return_compute_receipt",
        "paid_candidate",
    }

    if not body:
        decision = "reject_empty_campaign_event"
        accepted = False
    elif _contains_forbidden(body):
        decision = "reject_secret_shaped_payload"
        accepted = False
    elif record_revenue_requested:
        decision = "block_revenue_record_request"
        accepted = False
    elif send_requested and (not human_approved or not _digest_present(buyer_intent_digest)):
        decision = "block_public_send_request"
        accepted = False
    elif event_type in proof_required and not _digest_present(proof_digest):
        decision = "hold_until_proof_digest"
        accepted = False
    elif event_type in {"lead_observed", "buyer_intent", "first_fix_prepared", "paid_candidate"} and not lead_url:
        decision = "hold_until_lead_or_source_url"
        accepted = False
    elif event_type == "paid_candidate" and (amount <= 0.0 or not settlement_ref):
        decision = "hold_until_positive_settlement_ref"
        accepted = False
    else:
        decision = "accept_campaign_signal"
        accepted = True

    core = {
        "event_type": event_type,
        "lead_url": lead_url,
        "proof_digest": proof_digest,
        "buyer_intent_digest": buyer_intent_digest,
        "settlement_ref": settlement_ref,
        "amount_usd": amount,
        "decision": decision,
    }
    return {
        "ok": True,
        "schema": EVENT_SCHEMA,
        "generated_at": _now(),
        "event_id": f"nomad-first-receipt-campaign-event-{_digest({**core, 't': _now()}, 18)}",
        "event_type": event_type,
        "accepted": accepted,
        "decision": decision,
        "lead_url": lead_url,
        "evidence_status": {
            "proof_digest_present": _digest_present(proof_digest),
            "buyer_intent_digest_present": _digest_present(buyer_intent_digest),
            "settlement_ref_present": bool(settlement_ref),
            "positive_amount_present": amount > 0.0,
            "send_requested": send_requested,
            "human_approved": human_approved,
            "record_revenue_requested": record_revenue_requested,
        },
        "candidate_digest": "sha256:" + _digest(core, 32),
        "agent_acquisition_payload": build_first_receipt_campaign_acquisition_event(
            {
                **body,
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
        "hard_rule": "campaign_events_are_attribution_signals_only; paid_receipts_must_use_work_receipts_or_external_value",
        "campaign_digest": _text(_dict(campaign_surface).get("surface_digest"), 120),
    }


def build_first_receipt_campaign_acquisition_event(event: dict[str, Any], *, base_url: str = "") -> dict[str, Any]:
    """Translate accepted campaign events into acquisition-bandit rows."""

    body = _dict(event)
    event_type = _clean_id(body.get("event_type"), "lead_observed")
    reward_event = {
        "lead_observed": "inspect",
        "buyer_intent": "intake",
        "first_fix_prepared": "first_fix_returned",
        "adapter_activation": "adapter_event",
        "worker_start": "worker_start",
        "return_compute_receipt": "return_compute_receipt",
        "paid_candidate": "intake",
    }.get(event_type, "inspect")
    source_url = _text(
        body.get("source_url") or body.get("lead_url") or _u(base_url, "/.well-known/nomad-first-receipt-campaign.json"),
        500,
    )
    multiplier = 1.0
    if event_type == "paid_candidate":
        multiplier = 2.0
    elif event_type == "first_fix_prepared":
        multiplier = 1.4
    return {
        "channel_id": "first_receipt_campaign",
        "event_type": reward_event,
        "agent_id": _clean_id(body.get("agent_id") or body.get("runtime_id"), "nomad.campaign"),
        "source_url": source_url,
        "proof_digest": _text(body.get("proof_digest"), 220),
        "reward_multiplier": multiplier,
        "secret_policy": "public_digests_only_no_secrets",
    }
