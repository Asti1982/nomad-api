"""External job-channel registry for Nomad value cycles.

This module does not log in to third-party platforms, scrape marketplaces, post
submissions, or book revenue. It turns currently known paid-work channels into
proof-gated machine contracts so Nomad can decide where a value cycle is allowed
to search next.
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


def _href(base_url: str, url: Any) -> str:
    text = str(url or "").strip()
    if text.startswith(("http://", "https://")):
        return text
    if text.startswith("/"):
        return _u(base_url, text)
    return text


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:140].strip("_.:/#-") or fallback


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


JOB_CHANNEL_SEEDS: list[dict[str, Any]] = [
    {
        "channel_id": "github_oss_bounty_pr",
        "label": "GitHub OSS bounties and paid PR reviews",
        "category": "oss_bounty",
        "entry_url": "https://github.com/search?q=label%3Abounty&type=issues",
        "nomad_route": "/.well-known/nomad-bounty-hunter.json",
        "agent_work_modes": ["implementation_pr", "code_review_comment", "failing_test_or_audit_pr"],
        "payout_gate": "public bounty terms and maintainer/program owner acceptance",
        "settlement_rail": "program_specific_wallet_or_platform_claim",
        "authorization_gate": "public issue terms plus repo contribution policy",
        "proof_gate": "public PR or review URL with local test/repro digest",
        "autonomy_policy": "read_only_discovery_then_public_action_after_repro",
        "score": {
            "agent_fit": 0.90,
            "authorization_clarity": 0.80,
            "payout_clarity": 0.62,
            "proof_clarity": 0.88,
            "autonomy_allowed": 0.82,
            "settlement_speed": 0.42,
            "competition_risk": 0.58,
            "platform_friction": 0.36,
        },
        "evidence_sources": [
            {
                "url": "https://docs.github.com/en/issues/tracking-your-work-with-issues/filtering-and-searching-issues-and-pull-requests",
                "claim": "GitHub issues and PRs can be filtered into public work queues.",
            }
        ],
    },
    {
        "channel_id": "issuehunt_funded_oss_issue",
        "label": "IssueHunt funded OSS issues",
        "category": "oss_funded_issue",
        "entry_url": "https://oss.issuehunt.io/issues",
        "nomad_route": "/swarm/job-channels",
        "agent_work_modes": ["implementation_pr", "docs_pr", "maintenance_patch"],
        "payout_gate": "IssueHunt-funded open issue, upstream PR acceptance, and IssueHunt claim path",
        "settlement_rail": "issuehunt_reward_after_merged_pr_and_platform_claim",
        "authorization_gate": "open GitHub issue, visible funding badge, repo contribution policy, and PR creation permission",
        "proof_gate": "public branch or PR URL with local test/repro digest; submitted only after upstream PR exists",
        "autonomy_policy": "public_pr_allowed_after_preflight_but_no_revenue_until_issuehunt_receipt",
        "score": {
            "agent_fit": 0.84,
            "authorization_clarity": 0.82,
            "payout_clarity": 0.72,
            "proof_clarity": 0.88,
            "autonomy_allowed": 0.80,
            "settlement_speed": 0.32,
            "competition_risk": 0.62,
            "platform_friction": 0.46,
        },
        "evidence_sources": [
            {
                "url": "https://oss.issuehunt.io/issues",
                "claim": "IssueHunt exposes funded open-source issues and instructs contributors to submit pull requests to receive deposits.",
            }
        ],
    },
    {
        "channel_id": "algora_github_bounty",
        "label": "Algora GitHub bounties",
        "category": "oss_bounty",
        "entry_url": "https://algora.io/community",
        "nomad_route": "/swarm/job-channels",
        "agent_work_modes": ["implementation_pr", "docs_pr", "maintainer_scoped_fix"],
        "payout_gate": "Algora bounty attached to a public GitHub issue; maintainer acceptance and platform payout path confirmed",
        "settlement_rail": "algora_platform_payout_after_merged_or_awarded_pr",
        "authorization_gate": "public GitHub issue, bounty listing, repo contribution policy, and duplicate PR check",
        "proof_gate": "public PR URL with focused tests and issue-linked bounty evidence",
        "autonomy_policy": "read_only_discovery_then_bounded_pr_after_duplicate_and_payout_gate",
        "score": {
            "agent_fit": 0.86,
            "authorization_clarity": 0.82,
            "payout_clarity": 0.76,
            "proof_clarity": 0.88,
            "autonomy_allowed": 0.78,
            "settlement_speed": 0.48,
            "competition_risk": 0.58,
            "platform_friction": 0.44,
        },
        "evidence_sources": [
            {
                "url": "https://algora.io/community",
                "claim": "Algora exposes open-source bounties linked to GitHub issues and PR-based contribution flows.",
            },
            {
                "url": "https://algora.io/keephq/bounties/community",
                "claim": "Public organization bounty boards list open bounties, completed bounties, and total awarded amounts.",
            },
        ],
    },
    {
        "channel_id": "hackerone_bug_bounty",
        "label": "HackerOne bug bounty programs",
        "category": "security_bug_bounty",
        "entry_url": "https://www.hackerone.com/bug-bounty-programs",
        "nomad_route": "/swarm/job-channels",
        "agent_work_modes": ["private_vulnerability_report", "scope_scout", "repro_trace"],
        "payout_gate": "program awards bounty; payment preference and tax form must be complete",
        "settlement_rail": "bank_transfer_paypal_or_btc_usdc_wallet",
        "authorization_gate": "program scope and policy only",
        "proof_gate": "private platform report with reproducible impact and no public disclosure",
        "autonomy_policy": "operator_account_required_private_submission_only",
        "score": {
            "agent_fit": 0.78,
            "authorization_clarity": 0.86,
            "payout_clarity": 0.78,
            "proof_clarity": 0.80,
            "autonomy_allowed": 0.46,
            "settlement_speed": 0.36,
            "competition_risk": 0.70,
            "platform_friction": 0.62,
        },
        "evidence_sources": [
            {
                "url": "https://docs.hackerone.com/en/articles/8395706-receiving-payments",
                "claim": "Payment requires an awarded bounty, payment preferences, and tax form; supported rails include bank, PayPal, BTC, and USDC.",
            }
        ],
    },
    {
        "channel_id": "bugcrowd_bug_bounty",
        "label": "Bugcrowd bounty programs",
        "category": "security_bug_bounty",
        "entry_url": "https://www.bugcrowd.com/hackers/",
        "nomad_route": "/swarm/job-channels",
        "agent_work_modes": ["private_vulnerability_report", "scope_scout", "repro_trace"],
        "payout_gate": "first valid in-scope reproducible report accepted by program owner",
        "settlement_rail": "bugcrowd_reward_payment",
        "authorization_gate": "bounty brief scope and safe-harbor terms",
        "proof_gate": "private report reproducible by triage or program owner",
        "autonomy_policy": "operator_account_required_no_out_of_scope_testing",
        "score": {
            "agent_fit": 0.76,
            "authorization_clarity": 0.84,
            "payout_clarity": 0.72,
            "proof_clarity": 0.82,
            "autonomy_allowed": 0.44,
            "settlement_speed": 0.38,
            "competition_risk": 0.72,
            "platform_friction": 0.60,
        },
        "evidence_sources": [
            {
                "url": "https://docs.bugcrowd.com/researchers/receiving-rewards/getting-rewarded/",
                "claim": "Cash rewards require a valid, in-scope, reproducible, first report; reward amount is set by the program owner with Bugcrowd input.",
            },
            {
                "url": "https://docs.bugcrowd.com/researchers/disclosure/disclose-io-and-safe-harbor/",
                "claim": "Safe harbor depends on explicit in-scope assets and program policy.",
            },
        ],
    },
    {
        "channel_id": "intigriti_bug_bounty",
        "label": "Intigriti public bug bounty programs",
        "category": "security_bug_bounty",
        "entry_url": "https://www.intigriti.com/bug-bounty-programs",
        "nomad_route": "/swarm/job-channels",
        "agent_work_modes": ["private_vulnerability_report", "scope_scout", "repro_trace"],
        "payout_gate": "program validates report and awards bounty",
        "settlement_rail": "intigriti_platform_payout",
        "authorization_gate": "program scope and terms",
        "proof_gate": "private platform report with impact and reproduction steps",
        "autonomy_policy": "operator_account_required_private_submission_only",
        "score": {
            "agent_fit": 0.75,
            "authorization_clarity": 0.80,
            "payout_clarity": 0.66,
            "proof_clarity": 0.80,
            "autonomy_allowed": 0.42,
            "settlement_speed": 0.34,
            "competition_risk": 0.68,
            "platform_friction": 0.58,
        },
        "evidence_sources": [
            {
                "url": "https://www.intigriti.com/bug-bounty-programs",
                "claim": "Public program listings expose scoped programs that reward eligible vulnerability reports.",
            }
        ],
    },
    {
        "channel_id": "immunefi_web3_bounty",
        "label": "Immunefi Web3 bug bounties",
        "category": "web3_security_bounty",
        "entry_url": "https://immunefi.com/bug-bounty/",
        "nomad_route": "/swarm/job-channels",
        "agent_work_modes": ["smart_contract_review", "protocol_scope_scout", "impact_trace"],
        "payout_gate": "project validates in-scope bug under Immunefi rules",
        "settlement_rail": "program_specific_crypto_payout",
        "authorization_gate": "program scope, severity system, and disclosure rules",
        "proof_gate": "private report with exploitability and impact evidence",
        "autonomy_policy": "operator_account_required_no_live_exploitation_without_scope",
        "score": {
            "agent_fit": 0.72,
            "authorization_clarity": 0.78,
            "payout_clarity": 0.70,
            "proof_clarity": 0.72,
            "autonomy_allowed": 0.40,
            "settlement_speed": 0.30,
            "competition_risk": 0.76,
            "platform_friction": 0.64,
        },
        "evidence_sources": [
            {
                "url": "https://immunefi.com/bug-bounty/",
                "claim": "Immunefi lists Web3 bug bounty programs with program-specific scopes and rewards.",
            }
        ],
    },
    {
        "channel_id": "code4rena_competitive_audit",
        "label": "Code4rena competitive audits",
        "category": "web3_audit_contest",
        "entry_url": "https://code4rena.com/audits",
        "nomad_route": "/swarm/job-channels",
        "agent_work_modes": ["smart_contract_review", "contest_submission", "audit_report"],
        "payout_gate": "judge validates finding; payout requirements and tax information complete",
        "settlement_rail": "award_distribution_to_wallet_after_requirements",
        "authorization_gate": "registered Warden, audit scope, submission policy, and deadline",
        "proof_gate": "private contest submission before deadline; public disclosure only after report publication",
        "autonomy_policy": "operator_account_tax_gate_required_contest_rules_first",
        "score": {
            "agent_fit": 0.70,
            "authorization_clarity": 0.88,
            "payout_clarity": 0.82,
            "proof_clarity": 0.78,
            "autonomy_allowed": 0.36,
            "settlement_speed": 0.24,
            "competition_risk": 0.84,
            "platform_friction": 0.72,
        },
        "evidence_sources": [
            {
                "url": "https://docs.code4rena.com/competitions",
                "claim": "Sponsors establish prize pools; wardens submit findings during a time-boxed submission phase; judges decide validity.",
            },
            {
                "url": "https://docs.code4rena.com/awarding/awarding-process",
                "claim": "Awards require tax information and may require identity verification above lifetime earning thresholds.",
            },
        ],
    },
    {
        "channel_id": "sherlock_audit_contest",
        "label": "Sherlock audit contests",
        "category": "web3_audit_contest",
        "entry_url": "https://sherlock.xyz/audit-contests",
        "nomad_route": "/swarm/job-channels",
        "agent_work_modes": ["smart_contract_review", "contest_submission", "fix_verification"],
        "payout_gate": "valid findings plus payout criteria on Watson account",
        "settlement_rail": "usdc_payout_after_criteria",
        "authorization_gate": "contest scope and Watson account rules",
        "proof_gate": "contest submission with valid issue ratio preserved",
        "autonomy_policy": "operator_account_required_quality_ratio_hard_gate",
        "score": {
            "agent_fit": 0.68,
            "authorization_clarity": 0.84,
            "payout_clarity": 0.74,
            "proof_clarity": 0.76,
            "autonomy_allowed": 0.34,
            "settlement_speed": 0.26,
            "competition_risk": 0.82,
            "platform_friction": 0.70,
        },
        "evidence_sources": [
            {
                "url": "https://docs.sherlock.xyz/audits/protocols/how-it-works-for-protocols",
                "claim": "Sherlock contests are time-boxed public review programs with clear scope and incentives.",
            },
            {
                "url": "https://docs.sherlock.xyz/audits/watsons/meeting-the-payout-criteria",
                "claim": "USDC payouts can be withheld until two payout criteria are met, including valid issue count and issue ratio.",
            },
        ],
    },
    {
        "channel_id": "onlydust_open_source_rewards",
        "label": "OnlyDust open-source contributor rewards and grants",
        "category": "oss_grants",
        "entry_url": "https://www.onlydust.com/",
        "nomad_route": "/swarm/job-channels",
        "agent_work_modes": ["sustained_contribution", "project_onboarding", "maintainer_value"],
        "payout_gate": "eligible project contribution or grant selection",
        "settlement_rail": "onlydust_reward_or_grant",
        "authorization_gate": "project eligibility, contribution rules, and platform account",
        "proof_gate": "merged contribution history and project-recognized impact",
        "autonomy_policy": "operator_account_required_sustained_work_not_fast_cash",
        "score": {
            "agent_fit": 0.66,
            "authorization_clarity": 0.66,
            "payout_clarity": 0.52,
            "proof_clarity": 0.76,
            "autonomy_allowed": 0.50,
            "settlement_speed": 0.18,
            "competition_risk": 0.52,
            "platform_friction": 0.62,
        },
        "evidence_sources": [
            {
                "url": "https://docs.onlydust.com/overview/how-do-we-flow",
                "claim": "OnlyDust distributes sponsorship money to open-source contributors and maintainers through rewards and grants.",
            }
        ],
    },
    {
        "channel_id": "freelance_marketplace_draft_only",
        "label": "Freelance marketplaces: Upwork-style paid contracts",
        "category": "freelance_contract",
        "entry_url": "https://www.upwork.com/",
        "nomad_route": "/swarm/job-channels",
        "agent_work_modes": ["proposal_draft", "paid_devops_task", "client_deliverable"],
        "payout_gate": "client contract, escrow/payment protection, and accepted deliverable",
        "settlement_rail": "platform_escrow_or_invoice",
        "authorization_gate": "platform terms, approved API if automation touches platform, user account consent",
        "proof_gate": "operator-approved proposal and accepted paid contract",
        "autonomy_policy": "draft_only_without_approved_api_no_auto_apply_no_scraping",
        "score": {
            "agent_fit": 0.82,
            "authorization_clarity": 0.54,
            "payout_clarity": 0.74,
            "proof_clarity": 0.70,
            "autonomy_allowed": 0.18,
            "settlement_speed": 0.48,
            "competition_risk": 0.74,
            "platform_friction": 0.82,
        },
        "evidence_sources": [
            {
                "url": "https://support.upwork.com/hc/en-us/articles/43342677368467-Use-bots-and-other-automation-properly",
                "claim": "Unauthorized automation can lead to warnings or bans; compliant automation requires approved API access and still cannot spam proposals or scrape data.",
            }
        ],
    },
    {
        "channel_id": "nomad_internal_worker_market",
        "label": "Nomad internal worker, microtask, carrying, and paid-ref markets",
        "category": "machine_native_market",
        "entry_url": "/.well-known/nomad-agent-work.json",
        "nomad_route": "/.well-known/nomad-agent-work.json",
        "agent_work_modes": ["transition_worker", "microtask_proof", "carrying_proof", "paid_ref_verification"],
        "payout_gate": "verified buyer intent or external receipt; selfplay never counts as revenue",
        "settlement_rail": "rtc_wallet_or_x402_or_verified_paid_ref",
        "authorization_gate": "Nomad contract endpoints and public receive reference",
        "proof_gate": "lease/proof digest, verifier trace, and settlement receipt",
        "autonomy_policy": "native_agent_loop_allowed_but_paid_only_on_receipt",
        "score": {
            "agent_fit": 0.96,
            "authorization_clarity": 0.92,
            "payout_clarity": 0.42,
            "proof_clarity": 0.92,
            "autonomy_allowed": 0.92,
            "settlement_speed": 0.28,
            "competition_risk": 0.24,
            "platform_friction": 0.22,
        },
        "evidence_sources": [
            {
                "url": "/.well-known/nomad-agent-work.json",
                "claim": "Nomad exposes claimable machine work and proof contracts.",
            },
            {
                "url": "/.well-known/nomad-worker-invoice.json",
                "claim": "Nomad exposes public receive references and receipt gates.",
            },
        ],
    },
]


def score_job_channel(channel: dict[str, Any]) -> dict[str, Any]:
    """Return a scored, normalized job channel."""
    score = channel.get("score") if isinstance(channel.get("score"), dict) else {}
    agent_fit = _clamp(_num(score.get("agent_fit")))
    authorization = _clamp(_num(score.get("authorization_clarity")))
    payout = _clamp(_num(score.get("payout_clarity")))
    proof = _clamp(_num(score.get("proof_clarity")))
    autonomy = _clamp(_num(score.get("autonomy_allowed")))
    speed = _clamp(_num(score.get("settlement_speed")))
    competition = _clamp(_num(score.get("competition_risk")))
    friction = _clamp(_num(score.get("platform_friction")))
    settlement = _clamp(0.68 * payout + 0.32 * speed)
    drag = _clamp(0.62 * friction + 0.38 * competition)
    channel_score = (
        agent_fit
        * authorization
        * proof
        * (0.56 + 0.44 * settlement)
        * (0.50 + 0.50 * autonomy)
        * (1.0 - 0.46 * drag)
    )
    public_side_effect = "blocked_until_operator_gate"
    if autonomy >= 0.80 and authorization >= 0.80:
        public_side_effect = "allowed_after_contract_preflight"
    elif autonomy >= 0.40:
        public_side_effect = "read_only_scout_then_operator_private_submission"
    return {
        **channel,
        "channel_id": _clean_id(channel.get("channel_id"), "job_channel"),
        "schema": "nomad.job_channel.v1",
        "channel_score": round(channel_score, 6),
        "score_components": {
            "agent_fit": agent_fit,
            "authorization_clarity": authorization,
            "payout_clarity": payout,
            "proof_clarity": proof,
            "autonomy_allowed": autonomy,
            "settlement_speed": speed,
            "competition_risk": competition,
            "platform_friction": friction,
            "settlement_signal": round(settlement, 4),
            "drag": round(drag, 4),
        },
        "side_effect_gate": {
            "public_or_external_action": public_side_effect,
            "must_verify_before_work": [
                "program_scope_or_terms",
                "payout_method_compatibility",
                "account_tax_kyc_requirements_if_any",
                "private_or_public_disclosure_rules",
                "receipt_path_for_paid_stage",
            ],
            "hard_stops": [
                "out_of_scope_security_testing",
                "unauthorized_marketplace_automation",
                "public_disclosure_before_program_allows_it",
                "fake_receipt_or_revenue_without_payment",
                "payout_secret_in_public_claim",
            ],
        },
    }


def _infer_channel_id(row: dict[str, Any]) -> str:
    explicit = _clean_id(row.get("channel_id") or row.get("source_channel") or "")
    if explicit:
        return explicit
    external_id = str(row.get("external_id") or "").lower()
    work_url = str(row.get("work_url") or "").lower()
    raw = f"{external_id} {work_url}"
    if raw.startswith("issuehunt:") or "issuehunt.io" in raw:
        return "issuehunt_funded_oss_issue"
    if raw.startswith("algora:") or "algora.io" in raw:
        return "algora_github_bounty"
    if raw.startswith("gh_") or "github.com" in raw:
        return "github_oss_bounty_pr"
    if "hackerone.com" in raw:
        return "hackerone_bug_bounty"
    if "bugcrowd.com" in raw:
        return "bugcrowd_bug_bounty"
    if "intigriti.com" in raw:
        return "intigriti_bug_bounty"
    if "immunefi.com" in raw:
        return "immunefi_web3_bounty"
    if "code4rena" in raw:
        return "code4rena_competitive_audit"
    if "sherlock" in raw:
        return "sherlock_audit_contest"
    if "onlydust" in raw:
        return "onlydust_open_source_rewards"
    return "unknown"


def _channel_outcomes(external_value_summary: dict[str, Any] | None) -> dict[str, Any]:
    summary = external_value_summary if isinstance(external_value_summary, dict) else {}
    now = datetime.now(UTC)
    by_channel: dict[str, dict[str, Any]] = {}
    total_paid = 0
    total_active_nonpaid = 0
    latest = _items(summary.get("latest_by_external"))
    for row in latest:
        channel_id = _infer_channel_id(row)
        item = by_channel.setdefault(
            channel_id,
            {
                "channel_id": channel_id,
                "distinct_items": 0,
                "paid_count": 0,
                "active_nonpaid": 0,
                "submitted_count": 0,
                "approved_count": 0,
                "merged_count": 0,
                "max_nonpaid_age_hours": 0.0,
                "age_hours_sum": 0.0,
            },
        )
        stage = _clean_id(row.get("stage"), "unknown")
        item["distinct_items"] += 1
        if stage == "paid" and _num(row.get("revenue_recognized_usd")) > 0:
            item["paid_count"] += 1
            total_paid += 1
            continue
        if stage in {"found", "submitted", "approved", "merged"}:
            item["active_nonpaid"] += 1
            total_active_nonpaid += 1
            if stage == "submitted":
                item["submitted_count"] += 1
            elif stage == "approved":
                item["approved_count"] += 1
            elif stage == "merged":
                item["merged_count"] += 1
            when = _parse_dt(row.get("last_generated_at"))
            age_hours = max(0.0, (now - when).total_seconds() / 3600.0) if when else 0.0
            item["age_hours_sum"] += age_hours
            item["max_nonpaid_age_hours"] = max(_num(item.get("max_nonpaid_age_hours")), age_hours)
    for item in by_channel.values():
        active = max(1, int(item.get("active_nonpaid") or 0))
        item["mean_nonpaid_age_hours"] = round(_num(item.get("age_hours_sum")) / active, 4)
        item["max_nonpaid_age_hours"] = round(_num(item.get("max_nonpaid_age_hours")), 4)
        item.pop("age_hours_sum", None)
    return {
        "schema": "nomad.job_channel_outcomes.v1",
        "recognized_revenue_usd_total": _num(summary.get("revenue_recognized_usd_total")),
        "distinct_externals": int(_num(summary.get("distinct_externals"))),
        "total_paid_count": total_paid,
        "total_active_nonpaid": total_active_nonpaid,
        "by_channel": by_channel,
    }


def _build_switching_policy(channels: list[dict[str, Any]], outcomes: dict[str, Any]) -> dict[str, Any]:
    by_channel = outcomes.get("by_channel") if isinstance(outcomes.get("by_channel"), dict) else {}
    total_paid = int(_num(outcomes.get("total_paid_count")))
    total_active = int(_num(outcomes.get("total_active_nonpaid")))
    global_escape = total_paid == 0 and total_active >= 12
    allocations: list[dict[str, Any]] = []
    for channel in channels:
        channel_id = str(channel.get("channel_id") or "")
        observed = by_channel.get(channel_id) if isinstance(by_channel.get(channel_id), dict) else {}
        active = int(_num(observed.get("active_nonpaid")))
        paid = int(_num(observed.get("paid_count")))
        age = _num(observed.get("mean_nonpaid_age_hours"))
        components = channel.get("score_components") if isinstance(channel.get("score_components"), dict) else {}
        prior_success = _clamp(
            0.20
            + 0.24 * _num(components.get("payout_clarity"))
            + 0.22 * _num(components.get("authorization_clarity"))
            + 0.22 * _num(components.get("proof_clarity"))
            + 0.12 * _num(components.get("autonomy_allowed")),
            0.05,
            0.92,
        )
        prior_strength = 4.0
        delayed_nonpaid_equiv = active * _clamp(age / 72.0, 0.05, 1.0)
        alpha = 1.0 + prior_strength * prior_success + paid
        beta = 1.0 + prior_strength * (1.0 - prior_success) + delayed_nonpaid_equiv
        posterior_paid_probability = alpha / max(0.0001, alpha + beta)
        queue_penalty = 1.0 / (1.0 + 0.08 * active + 0.02 * _num(observed.get("max_nonpaid_age_hours")))
        switch_index = _num(channel.get("channel_score")) * posterior_paid_probability * queue_penalty
        gate = str((channel.get("side_effect_gate") or {}).get("public_or_external_action") or "")
        action = "exploit_after_preflight"
        arrival_weight = _clamp(switch_index)
        if gate.startswith("blocked"):
            action = "operator_gate_only"
            arrival_weight = 0.0
        elif global_escape and channel_id == "github_oss_bounty_pr" and active > 0 and paid == 0:
            action = "freeze_new_public_claims_reconcile_only"
            arrival_weight = 0.0
        elif active > 0 and paid == 0 and age >= 24:
            action = "cooldown_mature_nonpaying_channel"
            arrival_weight = min(arrival_weight, 0.05)
        elif not observed and gate == "read_only_scout_then_operator_private_submission":
            action = "read_only_scout_prepare_operator_gate"
            arrival_weight = min(0.18, max(0.04, arrival_weight))
        elif not observed:
            action = "small_exploration_probe_after_preflight"
            arrival_weight = min(0.24, max(0.05, arrival_weight))
        allocations.append(
            {
                "channel_id": channel_id,
                "category": channel.get("category", ""),
                "switch_index": round(switch_index, 6),
                "arrival_weight": round(arrival_weight, 6),
                "recommended_action": action,
                "posterior_paid_probability": round(posterior_paid_probability, 6),
                "observed": {
                    "active_nonpaid": active,
                    "paid_count": paid,
                    "submitted_count": int(_num(observed.get("submitted_count"))),
                    "approved_count": int(_num(observed.get("approved_count"))),
                    "merged_count": int(_num(observed.get("merged_count"))),
                    "mean_nonpaid_age_hours": round(age, 4),
                    "max_nonpaid_age_hours": round(_num(observed.get("max_nonpaid_age_hours")), 4),
                },
            }
        )
    allocations.sort(key=lambda item: (_num(item.get("arrival_weight")), _num(item.get("switch_index"))), reverse=True)
    external_probe = next(
        (
            item
            for item in allocations
            if item.get("category") != "machine_native_market"
            and item.get("channel_id") != "github_oss_bounty_pr"
            and item.get("recommended_action") in {"read_only_scout_prepare_operator_gate", "small_exploration_probe_after_preflight"}
        ),
        {},
    )
    native_probe = next((item for item in allocations if item.get("category") == "machine_native_market"), {})
    any_probe = next(
        (
            item
            for item in allocations
            if item.get("recommended_action") in {"read_only_scout_prepare_operator_gate", "small_exploration_probe_after_preflight"}
        ),
        allocations[0] if allocations else {},
    )
    return {
        "schema": "nomad.channel_switching_policy.v1",
        "mode": "delayed_reward_bandit_with_queue_escape",
        "arrival_policy": "suppress_new_public_claims_on_nonpaying_channel" if global_escape else "allocate_by_switch_index_after_preflight",
        "triggered": global_escape,
        "trigger_reason": (
            f"paid_count=0 and active_nonpaid={total_active} >= 12; freeze arrivals into current nonpaying public channel"
            if global_escape
            else "paid receipts or low active nonpaid backlog keep channel allocation open"
        ),
        "learning_rule": [
            "Treat each channel as a delayed-feedback bandit arm.",
            "Treat submitted/approved/merged without receipt as censored pending feedback, not revenue.",
            "Use queue pressure to stop new arrivals when nonpaid WIP grows faster than paid receipts.",
            "Shift only into read-only scout mode when platform account, tax, KYC, or private disclosure gates are missing.",
        ],
        "allocation": allocations,
        "next_channel_probe": external_probe if global_escape and external_probe else any_probe,
        "next_external_probe": external_probe,
        "next_native_probe": native_probe,
        "hard_guards": [
            "no_out_of_scope_security_testing",
            "no_marketplace_scraping_or_auto_apply_without_approved_api",
            "no_public_disclosure_before_program_allows_it",
            "no_revenue_without_positive_paid_receipt",
        ],
    }


def _qualification_unlocks(channel_id: str) -> list[str]:
    common = [
        "platform_account_or_program_access_confirmed",
        "payout_or_wallet_rail_confirmed",
        "tax_kyc_or_identity_requirements_confirmed_if_any",
        "program_scope_and_out_of_scope_targets_captured",
        "private_submission_or_report_path_known",
        "paid_receipt_path_known_before_revenue_booking",
    ]
    specific: dict[str, list[str]] = {
        "github_oss_bounty_pr": [
            "existing_open_items_reconciled_without_new_public_claims",
            "maintainer_or_owner_acceptance_signal_observed",
            "payment_claim_or_receipt_channel_confirmed",
        ],
        "issuehunt_funded_oss_issue": [
            "funding_badge_amount_and_issue_state_verified",
            "upstream_pr_creation_or_compare_link_confirmed",
            "issuehunt_claim_account_and_receipt_path_confirmed",
            "duplicate_open_prs_checked_before_work",
        ],
        "algora_github_bounty": [
            "algora_bounty_amount_and_issue_state_verified",
            "repo_contribution_policy_and_duplicate_prs_checked",
            "algora_solver_account_and_payout_path_confirmed",
            "maintainer_merge_or_award_condition_understood",
        ],
        "hackerone_bug_bounty": [
            "hackerone_payment_preferences_ready",
            "hackerone_tax_form_complete",
            "specific_program_policy_and_scope_selected",
        ],
        "bugcrowd_bug_bounty": [
            "bugcrowd_payment_method_ready",
            "bounty_brief_reviewed_before_any_testing",
            "known_issues_visible_or_operator_confirms_duplicate_risk",
        ],
        "code4rena_competitive_audit": [
            "warden_registration_confirmed",
            "tax_information_submitted_before_award_deadline",
            "competition_deadline_scope_and_submission_policy_selected",
        ],
        "sherlock_audit_contest": [
            "watson_account_ready",
            "two_valid_issue_or_ratio_payout_criteria_understood",
            "contest_scope_and_validity_rules_selected",
        ],
        "immunefi_web3_bounty": [
            "program_specific_kyc_poc_safe_harbor_flags_checked",
            "web3_wallet_and_chain_payout_path_confirmed",
            "no_live_exploitation_without_explicit_scope",
        ],
    }
    return common + specific.get(channel_id, [])


def _build_read_only_qualification_cycle(
    *,
    channels: list[dict[str, Any]],
    switching: dict[str, Any],
) -> dict[str, Any]:
    allocation = switching.get("allocation") if isinstance(switching.get("allocation"), list) else []
    by_alloc = {str(item.get("channel_id") or ""): item for item in allocation if isinstance(item, dict)}
    target_ids = {
        "github_oss_bounty_pr",
        "issuehunt_funded_oss_issue",
        "algora_github_bounty",
        "hackerone_bug_bounty",
        "bugcrowd_bug_bounty",
        "intigriti_bug_bounty",
        "immunefi_web3_bounty",
        "code4rena_competitive_audit",
        "sherlock_audit_contest",
    }
    rows: list[dict[str, Any]] = []
    for channel in channels:
        channel_id = str(channel.get("channel_id") or "")
        if channel_id not in target_ids:
            continue
        alloc = by_alloc.get(channel_id, {})
        gate = str((channel.get("side_effect_gate") or {}).get("public_or_external_action") or "")
        action = str(alloc.get("recommended_action") or "")
        if channel_id == "github_oss_bounty_pr" and action == "freeze_new_public_claims_reconcile_only":
            state = "reconcile_only_no_new_work"
        elif action == "operator_gate_only" or gate.startswith("blocked"):
            state = "operator_gate_required"
        elif action == "read_only_scout_prepare_operator_gate":
            state = "qualified_for_read_only_scout"
        else:
            state = "preflight_only"
        rows.append(
            {
                "channel_id": channel_id,
                "category": channel.get("category", ""),
                "state": state,
                "recommended_action": action or "read_only_preflight",
                "external_side_effect_allowed": False,
                "allowed_now": [
                    "read_public_terms",
                    "read_public_program_scope",
                    "read_public_payout_requirements",
                    "rank_without_testing_targets",
                    "prepare_operator_gate_packet",
                ]
                if state != "reconcile_only_no_new_work"
                else ["read_only_github_status_reconcile", "receipt_check", "wait_for_owner_acceptance_signal"],
                "blocked_now": [
                    "new_public_claim",
                    "private_vulnerability_submission",
                    "active_target_testing",
                    "marketplace_or_platform_automation",
                    "revenue_booking_without_paid_receipt",
                ],
                "unlock_requirements": _qualification_unlocks(channel_id),
                "switch_index": alloc.get("switch_index", 0.0),
                "arrival_weight": alloc.get("arrival_weight", 0.0),
                "posterior_paid_probability": alloc.get("posterior_paid_probability", 0.0),
                "evidence_sources": channel.get("evidence_sources", []),
            }
        )
    rows.sort(key=lambda item: (_num(item.get("arrival_weight")), _num(item.get("switch_index"))), reverse=True)
    return {
        "schema": "nomad.read_only_channel_qualification_cycle.v1",
        "mode": "github_reconcile_plus_parallel_external_preflight",
        "objective": "open_new_paid_channel_without_increasing_unpaid_public_claim_backlog",
        "current_github_policy": "reconcile_only_until_owner_acceptance_or_paid_receipt",
        "external_submission_policy": "blocked_until_payout_scope_and_private_submission_gate_are_verified",
        "qualification_count": len(rows),
        "next_read_only_targets": rows,
        "machine_instruction": (
            "do_not_test_targets_or_submit_reports_from_this_cycle; only qualify scope payout "
            "and receipt paths, then require an operator gate before any external side effect"
        ),
    }


def build_job_channel_surface(
    *,
    base_url: str,
    external_value_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build Nomad's broad external job-channel surface."""
    channels = [score_job_channel(item) for item in JOB_CHANNEL_SEEDS]
    channels.sort(key=lambda item: _num(item.get("channel_score")), reverse=True)
    outcomes = _channel_outcomes(external_value_summary)
    switching = _build_switching_policy(channels, outcomes)
    qualification = _build_read_only_qualification_cycle(channels=channels, switching=switching)
    native = [item for item in channels if item.get("category") == "machine_native_market"]
    external = [item for item in channels if item.get("category") != "machine_native_market"]
    security = [item for item in channels if "security" in str(item.get("category") or "")]
    operator_gated = [
        item for item in channels if str(item.get("side_effect_gate", {}).get("public_or_external_action") or "").startswith("blocked")
    ]
    digest_core = {
        "ids": [item.get("channel_id") for item in channels],
        "scores": [item.get("channel_score") for item in channels],
        "top": channels[0].get("channel_id") if channels else "",
    }
    return {
        "ok": True,
        "schema": "nomad.job_channels.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "read_url": _u(base_url, "/swarm/job-channels"),
        "well_known_url": _u(base_url, "/.well-known/nomad-job-channels.json"),
        "channel_digest": f"nomad-job-channels-{_digest(digest_core)}",
        "mechanism": "proof_gated_external_job_channel_selection_paid_only_on_receipt",
        "score_formula": "agent_fit * authorization * proof * settlement_signal * autonomy * inverse(platform_friction,competition_risk)",
        "summary": {
            "channel_count": len(channels),
            "external_channel_count": len(external),
            "security_channel_count": len(security),
            "operator_gated_count": len(operator_gated),
            "top_channel_id": channels[0].get("channel_id", "") if channels else "",
            "top_external_channel_id": external[0].get("channel_id", "") if external else "",
            "top_native_channel_id": native[0].get("channel_id", "") if native else "",
        },
        "top_channel": channels[0] if channels else {},
        "top_external_channel": external[0] if external else {},
        "channels": channels,
        "observed_outcomes": outcomes,
        "switching_policy": switching,
        "read_only_qualification_cycle": qualification,
        "channel_contract": {
            "required_before_external_action": [
                "value_cycle_preflight",
                "public_receive_ref_or_platform_payout_ready",
                "program_terms_verified",
                "payout_terms_verified",
                "proof_digest_or_private_report_ready",
                "settlement_receipt_path_known",
            ],
            "allowed_nomad_accounting": "found_or_submitted_before_acceptance; paid_only_after_positive_receipt",
            "no_revenue_claim_rule": "accepted_merged_or_thanked_is_not_paid",
            "privacy_rule": "use_public_receive_ref_only; keep bank_tax_platform_private_material out of public JSON and claims",
        },
        "next": [
            {"op": "GET", "url": _u(base_url, "/.well-known/nomad-worker-invoice.json"), "reason": "verify_receive_ref"},
            {"op": "GET", "url": _u(base_url, "/.well-known/nomad-value-cycle-preflight.json"), "reason": "check_wallet_terms_receipt_gate"},
            {"op": "GET", "url": _href(base_url, external[0].get("entry_url", "")) if external else "", "reason": "read_top_external_channel_terms"},
            {"op": "GET", "url": _u(base_url, "/.well-known/nomad-bounty-hunter.json"), "reason": "continue_existing_github_channel_when_settlement_throttle_allows"},
        ],
        "machine_instruction": (
            "choose_channel_by_switch_index_not_loyalty; freeze_nonpaying_public_channels_when_wip_exceeds_receipts; security_platforms_are_private_report_channels; "
            "freelance_marketplaces_are_draft_only_without_approved_api; never_book_revenue_without_paid_receipt"
        ),
        "science_basis": [
            {"id": "contract_net_task_allocation", "source": "smith_1980_contract_net_protocol"},
            {"id": "delayed_feedback_bandits", "source": "bandit_allocation_with_delayed_rewards_and_thompson_sampling"},
            {"id": "restless_bandit_index_policy", "source": "whittle_index_dynamic_resource_allocation"},
            {"id": "queue_control", "source": "little_law_wip_and_settlement_latency"},
            {"id": "survival_hazard", "source": "censored_pending_feedback_modeled_as_payment_hazard"},
        ],
    }
