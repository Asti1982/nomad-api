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
        "payment_rail": pricing.get("payment_rail") or "metamask_native_transfer",
        "checkout": pricing.get("checkout")
        or "create payable task, pay Nomad wallet from MetaMask, then submit tx_hash for verification",
        "stripe_enabled": bool(pricing.get("stripe_enabled", False)),
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


def _science_backed_cashflow_kernel(
    *,
    root: str,
    revenue_usd: float,
    duplicate: dict[str, Any],
    packages: list[dict[str, Any]],
    contact_paths: dict[str, Any],
) -> dict[str, Any]:
    """Route scarce work by receipt proximity instead of human-like promise."""
    package_count = max(1, len(packages))
    buyer_paid_score = 1.0
    if revenue_usd <= 0.0:
        buyer_paid_score += 0.55
    if packages:
        buyer_paid_score += 0.2
    settlement_score = 0.45 if revenue_usd <= 0.0 else 0.9
    bounty_score = 0.28 + min(0.25, 0.04 * float(duplicate.get("low_duplicate_count") or 0))
    referral_score = 0.18
    if int(duplicate.get("public_go_count") or 0) > 0:
        bounty_score += 0.12

    lanes = [
        {
            "lane": "buyer_paid_repo_diagnostic",
            "score": round(buyer_paid_score, 3),
            "route": contact_paths.get("service_e2e") or _u(root, "/service/e2e?service_type=repo_issue_help"),
            "dominant_receipt": "verified_wallet_tx_hash_or_x402_signature",
            "work_before_receipt": "preview_only",
            "why": "shortest path from buyer pain to paid task; no maintainer discretion needed",
        },
        {
            "lane": "settlement_repair",
            "score": round(settlement_score, 3),
            "route": _u(root, "/.well-known/nomad-external-value.json"),
            "dominant_receipt": "external_paid_receipt_or_positive_balance_delta",
            "work_before_receipt": "read_only_watch_and_one_mature_followup_max",
            "why": "may recover already-created value, but cannot be counted until receipt",
        },
        {
            "lane": "proof_first_bounty",
            "score": round(bounty_score, 3),
            "route": _u(root, "/.well-known/nomad-bounty-hunter.json"),
            "dominant_receipt": "public_bounty_acceptance_plus_payment",
            "work_before_receipt": "local_repro_only",
            "why": "use only low-duplicate clear-payout bounties; public claims wait for proof",
        },
        {
            "lane": "owned_referral_context",
            "score": referral_score,
            "route": _u(root, "/.well-known/nomad-referral-swarm.json"),
            "dominant_receipt": "provider_referral_credit_receipt",
            "work_before_receipt": "owned_surface_only",
            "why": "cheap optional upside, but weak proof and weak buyer intent",
        },
    ]
    lanes.sort(key=lambda item: item["score"], reverse=True)
    return {
        "schema": "nomad.science_backed_cashflow_kernel.v1",
        "purpose": "replace unpaid contribution volume with receipt-proximate buyer work",
        "counter_human_shift": (
            "do not reward effort, agreement, thanks, merge, or public visibility; reward only "
            "receipt proximity and verified payment rails"
        ),
        "research_basis": [
            {
                "id": "agent_scaling_diversity_2026",
                "url": "https://arxiv.org/abs/2602.03794",
                "implemented_rule": "measure effective channels; do not add more homogeneous unpaid attempts",
            },
            {
                "id": "voting_or_consensus_2025",
                "url": "https://aclanthology.org/2025.findings-acl.606/",
                "implemented_rule": "independent generation and answer diversity beat blind convergence; isolate lanes before integration",
            },
            {
                "id": "web_of_agents_2025",
                "url": "https://www.microsoft.com/en-us/research/publication/collaborative-agentic-ai-needs-interoperability-across-ecosystems/",
                "implemented_rule": "make discovery, state, and payment handoff machine-readable instead of prose-led selling",
            },
            {
                "id": "dmas_achilles_heel_2025",
                "url": "https://arxiv.org/abs/2504.07461",
                "implemented_rule": "guard against free riding by blocking work until a receipt or bounded proof gate exists",
            },
            {
                "id": "multiagentbench_2025",
                "url": "https://arxiv.org/abs/2503.01935",
                "implemented_rule": "score milestone completion, not conversational collaboration quality",
            },
        ],
        "lane_count": len(lanes),
        "package_count": package_count,
        "ranked_lanes": lanes,
        "forced_next_lane": lanes[0],
        "selection_law": [
            "if recognized_revenue_usd_total == 0, buyer_paid_repo_diagnostic outranks unpaid bounty expansion",
            "if no verified tx_hash or external paid receipt exists, work product remains preview or draft only",
            "if a lane has no machine-readable payment verifier, its route weight decays regardless of social approval",
            "if two lanes emit the same buyer story, keep only the one with the shorter receipt path",
        ],
        "cashflow_experiment": {
            "hypothesis": "one paid repo diagnostic starter beats more unpaid bounty/review attempts as first-revenue path",
            "primary_metric": "verified paid task count",
            "negative_control": ["submitted_without_payment", "merge_without_payment", "approval_without_payment"],
            "stop_rule": "after 3 unpaid buyer task previews without tx_hash, rotate buyer context but keep receipt gate",
        },
        "machine_instruction": "route_next_external_value_cycle_to_forced_next_lane_until_paid_receipt_or_explicit_operator_override",
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
            "buyer_input": ["repo_url", "issue_or_log_url", "observed_error", "expected_behavior"],
            "deliverable": "one diagnosis, duplicate check, smallest repro/patch plan, and no-post public reply draft",
            "price": _service_price(service, 1.0),
            "scope": "one public repo issue, CI/build failure, deploy failure, or endpoint regression",
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
    cashflow_kernel = _science_backed_cashflow_kernel(
        root=root,
        revenue_usd=revenue_usd,
        duplicate=duplicate,
        packages=packages,
        contact_paths=contact_paths,
    )

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
    cycles.append(
        {
            "cycle_id": "science_backed_receipt_first_sales",
            "status": "forced_primary_lane",
            "objective": "convert the next value cycle into a paid buyer task before doing deeper work",
            "evidence": {
                "forced_lane": cashflow_kernel["forced_next_lane"]["lane"],
                "forced_route": cashflow_kernel["forced_next_lane"]["route"],
                "recognized_revenue_usd_total": revenue_usd,
            },
            "next_action": "create or share the repo_diagnostic_patch_starter order; work only after verified payment",
        }
    )

    plan_core = {
        "revenue_usd": revenue_usd,
        "active_owned": len(active_owned),
        "low_duplicate": duplicate.get("low_duplicate_count", 0),
        "packages": [item["package_id"] for item in packages],
    }
    starter = packages[0]
    starter_problem = (
        "Repo/CI/endpoint disturbance: diagnose one failing build, failing check, public issue, "
        "or endpoint regression; return duplicate pressure, smallest repro/patch path, and no-post reply draft."
    )
    concrete_starter_order = {
        "schema": "nomad.concrete_buyable_order_simulation.v1",
        "simulation_counts_as_revenue": False,
        "package_id": starter["package_id"],
        "service_type": starter["service_type"],
        "entry_url": _u(root, "/service/e2e?service_type=repo_issue_help"),
        "matching_context": {
            "context_type": "repo_ci_endpoint_disturbance",
            "examples": [
                "Render build failed for a repo deployment",
                "CI check exits non-zero after a dependency or endpoint change",
                "public endpoint returns the wrong status or stale commit",
            ],
            "why_this_is_the_next_cycle": "it turns one already-observable blocker into a small purchasable diagnosis instead of waiting for bounty settlement",
        },
        "preview_request": {
            "method": "GET",
            "url": _u(root, "/service/e2e?service_type=repo_issue_help"),
        },
        "create_task_request": {
            "method": "POST",
            "url": _u(root, "/service/e2e"),
            "payload": {
                "create": True,
                "service_type": "repo_issue_help",
                "package_id": starter["package_id"],
                "problem": starter_problem,
                "budget_native": starter["price"]["amount_native"],
                "metadata": {
                    "package_id": starter["package_id"],
                    "buyer_context": "repo_ci_endpoint_disturbance",
                },
            },
        },
        "proof_gate": [
            "verified MetaMask/native wallet payment before work",
            "no public post without approval",
            "delivery includes diagnosis, duplicate pressure, smallest repro/patch path, and verifier checklist",
        ],
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
        "payment_policy": {
            "primary_rail": "MetaMask native wallet transfer",
            "stripe_subscription_enabled": False,
            "operator_secret_policy": "never expose private keys, Stripe secrets, or hosted-model API keys",
            "recognized_revenue_rule": "only verified tx_hash or external paid receipt can move a task into paid revenue",
        },
        "priority_order": [
            "buyer_funded_diagnostic_patch",
            "settlement_receipt_watch",
            "proof_first_bounty_scout",
            "owned_contextual_referral",
        ],
        "cycles": cycles,
        "science_backed_cashflow_kernel": cashflow_kernel,
        "buyer_funded_packages": packages,
        "concrete_starter_order": concrete_starter_order,
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
        "machine_instruction": "prefer_buyer_funded_small_packages; use_metamask_native_transfer_not_stripe_subscription; keep_settlement_receipt_strict; scout_bounties_read_only_until_proof; referrals_owned_or_requested_only",
    }
