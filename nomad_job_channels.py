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


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


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


def build_job_channel_surface(*, base_url: str) -> dict[str, Any]:
    """Build Nomad's broad external job-channel surface."""
    channels = [score_job_channel(item) for item in JOB_CHANNEL_SEEDS]
    channels.sort(key=lambda item: _num(item.get("channel_score")), reverse=True)
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
            "choose_top_channel_only_after_preflight; security_platforms_are_private_report_channels; "
            "freelance_marketplaces_are_draft_only_without_approved_api; never_book_revenue_without_paid_receipt"
        ),
        "science_basis": [
            {"id": "contract_net_task_allocation", "source": "smith_1980_contract_net_protocol"},
            {"id": "proof_carrying_work", "source": "reproducible_oss_and_private_vulnerability_reporting_practice"},
            {"id": "bandit_channel_selection", "source": "exploration_exploitation_under_uncertain_rewards"},
            {"id": "queue_control", "source": "little_law_wip_and_settlement_latency"},
        ],
    }
