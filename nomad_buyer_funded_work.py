"""Buyer-funded work surface for Nomad.

This surface keeps external bounty work, referrals, and direct paid work in one
receipt-strict plan. It deliberately favors small diagnostic/patch packages over
broad outreach because those packages can be bought, verified, and repeated
without treating attention as revenue.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Dict


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


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _service_price(service_catalog: dict[str, Any], multiplier: float) -> dict[str, Any]:
    pricing = _dict(service_catalog.get("pricing"))
    wallet = _dict(service_catalog.get("wallet"))
    minimum = _num(pricing.get("minimum_native"), 0.01)
    return {
        "amount_native": round(max(minimum, minimum * multiplier), 6),
        "native_symbol": pricing.get("payment_token") or wallet.get("native_symbol") or "native",
        "requires_payment": bool(pricing.get("requires_payment", True)),
        "receipt_rule": "task is revenue only after verified payment receipt or external paid receipt",
    }


def _duplicate_pressure(bounty_hunter: dict[str, Any]) -> dict[str, Any]:
    opportunities = _items(bounty_hunter.get("opportunities"))
    if not opportunities:
        return {
            "candidate_count": 0,
            "low_duplicate_count": 0,
            "max_similar_claim_count_24h": 0,
            "public_go_count": 0,
        }
    low_dup = [
        item
        for item in opportunities
        if _num(item.get("similar_claim_count_24h"), 0.0) <= 2
        and _num(item.get("comment_count"), 0.0) < 12
    ]
    summary = _dict(bounty_hunter.get("summary"))
    return {
        "candidate_count": len(opportunities),
        "low_duplicate_count": len(low_dup),
        "max_similar_claim_count_24h": int(max(_num(item.get("similar_claim_count_24h"), 0.0) for item in opportunities)),
        "public_go_count": int(summary.get("public_go_count") or 0),
    }


def build_buyer_funded_work_surface(
    *,
    base_url: str = "",
    external_value_summary: Dict[str, Any] | None = None,
    bounty_hunter: Dict[str, Any] | None = None,
    referral_swarm: Dict[str, Any] | None = None,
    service_catalog: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Compile the next revenue plan into machine-readable work cycles."""
    root = (base_url or "").strip().rstrip("/")
    external = _dict(external_value_summary)
    bounty = _dict(bounty_hunter)
    referral = _dict(referral_swarm)
    service = _dict(service_catalog)
    active_owned = _items(referral.get("active_owned_arms"))
    human_approval = _items(referral.get("human_approval_required_arms"))
    blocked_referral = _items(referral.get("blocked_arms"))
    duplicate = _duplicate_pressure(bounty)
    revenue_usd = _num(external.get("revenue_recognized_usd_total"), 0.0)
    wallet = _dict(service.get("wallet"))
    contact_paths = _dict(_dict(service.get("contact_paths")).get("http"))

    packages = [
        {
            "package_id": "repo_diagnostic_patch_starter",
            "service_type": "repo_issue_help",
            "title": "Repo Diagnostic Patch Pack: Starter",
            "buyer_input": ["repo_url", "issue_or_error_url", "expected_behavior"],
            "deliverable": "one diagnosis, duplicate check, smallest repro/patch plan, and no-post public reply draft",
            "price": _service_price(service, 1.0),
            "why_financially_near": "can be bought directly by a blocked maintainer, agent, or operator without waiting for bounty settlement",
            "safe_public_action": "none_without_buyer_or_operator_approval",
        },
        {
            "package_id": "endpoint_health_patch",
            "service_type": "compute_auth",
            "title": "Endpoint Health Patch Pack",
            "buyer_input": ["base_url", "failing_endpoint", "observed_error"],
            "deliverable": "curlable health diagnosis, likely patch surface, and bounded verification checklist",
            "price": _service_price(service, 2.0),
            "why_financially_near": "short path from buyer pain to paid task; verifier output is obvious",
            "safe_public_action": "owned_service_surface_only",
        },
        {
            "package_id": "agent_loop_break_patch",
            "service_type": "loop_break",
            "title": "Agent Loop Break Patch Pack",
            "buyer_input": ["agent_trace", "repeated_tool_error", "stop_condition"],
            "deliverable": "retry circuit breaker, fallback lane, and memory update contract",
            "price": _service_price(service, 3.0),
            "why_financially_near": "agent teams pay to stop repeated wasted compute and failed automation loops",
            "safe_public_action": "contextual_answer_only_after_requested",
        },
        {
            "package_id": "settlement_repair_packet",
            "service_type": "payment",
            "title": "Settlement Repair Packet",
            "buyer_input": ["work_url", "claim_url", "expected_receipt_or_payment_terms"],
            "deliverable": "receipt gate, low-burden follow-up draft, and ledger stage recommendation",
            "price": _service_price(service, 2.0),
            "why_financially_near": "targets money that may already be owed while preserving paid-only accounting",
            "safe_public_action": "one_mature_followup_max_after_no_recent_followup",
        },
    ]

    cycles = [
        {
            "cycle_id": "settlement_receipt_watch",
            "status": "active_read_only",
            "objective": "turn merged or approved work into paid only when a real receipt appears",
            "evidence": {
                "recognized_revenue_usd_total": revenue_usd,
                "external_tail_count": external.get("event_tail_count", 0),
                "distinct_externals": external.get("distinct_externals", 0),
            },
            "next_action": "check mature RustChain items and RTC balance; record paid only after positive receipt",
        },
        {
            "cycle_id": "owned_contextual_referral",
            "status": "active_owned_surface",
            "objective": "keep Cursor referral on owned surfaces and helpful requested answers only",
            "evidence": {
                "active_owned_arms": len(active_owned),
                "human_approval_required_arms": len(human_approval),
                "blocked_arms": len(blocked_referral),
            },
            "next_action": "crosslink referral surfaces where users already request Nomad or Cursor context",
        },
        {
            "cycle_id": "proof_first_bounty_scout",
            "status": "scout_only_until_repro",
            "objective": "select only low-duplicate, clear-payout OSS work with a local proof path",
            "evidence": duplicate,
            "next_action": "work top scout candidate locally; no public claim until proof digest exists",
        },
        {
            "cycle_id": "buyer_funded_diagnostic_patch",
            "status": "primary_next_cashflow_lane",
            "objective": "sell small bounded diagnosis and patch packets before broad bounty hunting",
            "evidence": {
                "package_count": len(packages),
                "wallet_configured": bool(wallet.get("configured")),
                "service_endpoint": contact_paths.get("service_e2e") or _u(root, "/service/e2e"),
            },
            "next_action": "route incoming buyer or agent blocker into repo_diagnostic_patch_starter first",
        },
    ]

    plan_core = {
        "revenue_usd": revenue_usd,
        "active_owned": len(active_owned),
        "low_duplicate": duplicate.get("low_duplicate_count", 0),
        "packages": [item["package_id"] for item in packages],
    }
    return {
        "ok": True,
        "schema": "nomad.buyer_funded_work.v1",
        "generated_at": _now(),
        "public_base_url": root,
        "surface_digest": f"nomad-buyer-funded-work-{_digest(plan_core)}",
        "read_url": _u(root, "/swarm/buyer-funded-work"),
        "well_known_url": _u(root, "/.well-known/nomad-buyer-funded-work.json"),
        "receipt_law": {
            "recognized_revenue_usd_total": revenue_usd,
            "only_paid_counts": True,
            "not_revenue": ["submitted", "approved", "merged", "clicks", "unpaid_referrals", "simulated_buyer_interest"],
            "paid_requires": ["positive_amount", "trusted_receipt_or_balance_delta", "receipt_digest"],
        },
        "priority_order": [
            "buyer_funded_diagnostic_patch",
            "settlement_receipt_watch",
            "proof_first_bounty_scout",
            "owned_contextual_referral",
        ],
        "cycles": cycles,
        "buyer_funded_packages": packages,
        "contextual_referral_policy": {
            "owned_surfaces_active": [item.get("surface") for item in active_owned],
            "external_reply_requires": ["user_asked_about_cursor_or_ai_editor", "helpful_answer_first", "referral_disclosure"],
            "blocked": ["cold_social_broadcast", "unsolicited_dm_sequence", "contextless_referral_drop"],
        },
        "bounty_gate": {
            "public_go_count": duplicate.get("public_go_count", 0),
            "low_duplicate_count": duplicate.get("low_duplicate_count", 0),
            "required_before_claim": [
                "public_terms_url",
                "low_duplicate_pressure",
                "local_repro_or_patch_digest",
                "verifier_trace_digest",
                "clear_payout_path",
            ],
        },
        "intake_contract": {
            "preview": _u(root, "/service/e2e?service_type=repo_issue_help"),
            "create_task": _u(root, "/service/e2e"),
            "service_catalog": _u(root, "/service"),
            "task_payment_verify": _u(root, "/tasks/verify"),
        },
        "machine_instruction": "prefer_buyer_funded_small_packages; keep_settlement_receipt_strict; scout_bounties_read_only_until_proof; referrals_owned_or_requested_only",
    }
