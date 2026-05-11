"""Authorized paid OSS bounty surface for Nomad agents.

This module does not post comments, open PRs, or move payment details. It turns
public bounty programs into compact, scored work contracts so an agent can pick
real paid work, produce proof, and only then claim externally.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from typing import Any


RTC_USD_REF = 0.10


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


def _count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text(value: Any, limit: int = 320) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:120].strip("_.:/#-") or fallback


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def extract_reward(text: str) -> dict[str, Any]:
    """Extract a conservative public reward range from issue text."""
    body = str(text or "")
    usd_values = [float(m.group(1).replace(",", "")) for m in re.finditer(r"\$([0-9][0-9,]*(?:\.[0-9]+)?)", body)]
    if usd_values:
        return {
            "currency": "USD",
            "floor_usd": round(min(usd_values), 4),
            "ceiling_usd": round(max(usd_values), 4),
            "reward_text": f"${min(usd_values):g}-${max(usd_values):g}" if len(set(usd_values)) > 1 else f"${usd_values[0]:g}",
        }

    range_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:-|to|/)\s*([0-9]+(?:\.[0-9]+)?)\s*RTC\b", body, re.I)
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        return {
            "currency": "RTC",
            "floor_usd": round(min(low, high) * RTC_USD_REF, 4),
            "ceiling_usd": round(max(low, high) * RTC_USD_REF, 4),
            "reward_text": f"{min(low, high):g}-{max(low, high):g} RTC",
        }

    rtc_values = [float(m.group(1)) for m in re.finditer(r"\b([0-9]+(?:\.[0-9]+)?)\s*RTC\b", body, re.I)]
    if rtc_values:
        return {
            "currency": "RTC",
            "floor_usd": round(min(rtc_values) * RTC_USD_REF, 4),
            "ceiling_usd": round(max(rtc_values) * RTC_USD_REF, 4),
            "reward_text": f"{min(rtc_values):g}-{max(rtc_values):g} RTC" if len(set(rtc_values)) > 1 else f"{rtc_values[0]:g} RTC",
        }

    return {"currency": "unknown", "floor_usd": 0.0, "ceiling_usd": 0.0, "reward_text": ""}


def _classify_work(title: str, body: str) -> dict[str, Any]:
    raw = f"{title}\n{body}".lower()
    if any(
        token in raw
        for token in (
            "liquidity provider",
            "provide liquidity",
            "raydium",
            "trading pair",
            "market maker",
            "lp token",
            " lp ",
            "staking",
            "deposit",
            "wallet balance",
            "capital",
        )
    ):
        return {
            "work_mode": "capital_market_claim",
            "agent_fit": 0.16,
            "proof_clarity": 0.58,
            "side_effect_safety": 0.42,
            "anti_spam_weight": 0.18,
            "eligible": False,
            "exclusion_reason": "requires_external_capital_or_market_position_not_proof_work",
        }
    if any(token in raw for token in ("referral", "bring a friend", "invite a friend", "refer ", "referred by")):
        return {
            "work_mode": "referral_or_network_growth_claim",
            "agent_fit": 0.14,
            "proof_clarity": 0.50,
            "side_effect_safety": 0.38,
            "anti_spam_weight": 0.08,
            "eligible": False,
            "exclusion_reason": "referral_or_network_growth_claim_not_agent_proof_work",
        }
    if any(token in raw for token in ("tutorial video", "video proof", "record a video", "blog post", "write a blog", "article about")):
        return {
            "work_mode": "content_or_media_claim",
            "agent_fit": 0.24,
            "proof_clarity": 0.60,
            "side_effect_safety": 0.54,
            "anti_spam_weight": 0.42,
            "eligible": False,
            "exclusion_reason": "content_or_media_claim_not_proof_carrying_code_work",
        }
    if "good first issues" in raw and ("bounty label" in raw or "bounties" in raw):
        return {
            "work_mode": "bounty_issue_fix_after_subselection",
            "agent_fit": 0.58,
            "proof_clarity": 0.66,
            "side_effect_safety": 0.88,
            "anti_spam_weight": 1.0,
            "eligible": True,
            "exclusion_reason": "",
        }
    if any(token in raw for token in ("star the", "stars campaign", "share ", "social media", "twitter", "reddit", "hacker news")):
        return {
            "work_mode": "promotional_engagement",
            "agent_fit": 0.18,
            "proof_clarity": 0.55,
            "side_effect_safety": 0.35,
            "anti_spam_weight": 0.08,
            "eligible": False,
            "exclusion_reason": "promotional_or_reputation_action_not_nomad_core_work",
        }
    if any(token in raw for token in ("contributor ladder", "level up", "canonical rtc wallet", "declare by", "bring your human", "human engagement", "community campaign")):
        return {
            "work_mode": "reputation_or_identity_policy",
            "agent_fit": 0.20,
            "proof_clarity": 0.52,
            "side_effect_safety": 0.48,
            "anti_spam_weight": 0.20,
            "eligible": False,
            "exclusion_reason": "community_reputation_or_wallet_policy_not_proof_work",
        }
    if any(token in raw for token in ("red team", "security", "bug", "audit", "vulnerability")):
        return {
            "work_mode": "failing_test_or_audit_pr",
            "agent_fit": 0.78,
            "proof_clarity": 0.84,
            "side_effect_safety": 0.80,
            "anti_spam_weight": 1.0,
            "eligible": True,
            "exclusion_reason": "",
        }
    if "review" in raw and ("pr" in raw or "pull request" in raw):
        return {
            "work_mode": "code_review_comment",
            "agent_fit": 0.82,
            "proof_clarity": 0.88,
            "side_effect_safety": 0.86,
            "anti_spam_weight": 1.0,
            "eligible": True,
            "exclusion_reason": "",
        }
    if any(token in raw for token in ("extension", "bot", "implementation", "reference implementation", "sitemap", "robots.txt")):
        return {
            "work_mode": "implementation_pr",
            "agent_fit": 0.66,
            "proof_clarity": 0.72,
            "side_effect_safety": 0.72,
            "anti_spam_weight": 0.92,
            "eligible": True,
            "exclusion_reason": "",
        }
    if any(token in raw for token in ("hardware", "video", "fingerprint", "miner")):
        return {
            "work_mode": "physical_evidence_claim",
            "agent_fit": 0.28,
            "proof_clarity": 0.70,
            "side_effect_safety": 0.58,
            "anti_spam_weight": 0.55,
            "eligible": False,
            "exclusion_reason": "requires_physical_or_social_evidence_outside_agent_runtime",
        }
    return {
        "work_mode": "issue_triage_or_fix_pr",
        "agent_fit": 0.62,
        "proof_clarity": 0.62,
        "side_effect_safety": 0.70,
        "anti_spam_weight": 0.88,
        "eligible": True,
        "exclusion_reason": "",
    }


def _impact_class(title: str, body: str, work_mode: str) -> str:
    raw = f"{title}\n{body}\n{work_mode}".lower()
    if work_mode in {"capital_market_claim", "referral_or_network_growth_claim", "content_or_media_claim", "physical_evidence_claim", "promotional_engagement", "reputation_or_identity_policy"}:
        return "non_agent_runtime_claim"
    if any(token in raw for token in ("settlement", "reward scale", "mint", "economic", "payout ledger", "supply")):
        return "economic_correctness"
    if any(token in raw for token in ("500", "keyerror", "traceback", "fails closed", "webhook", "auth", "signature")):
        return "route_reliability_security"
    if any(token in raw for token in ("security", "vulnerability", "red team", "audit", "exploit")):
        return "security"
    if any(token in raw for token in ("spdx", "license", "bcos", "policy")):
        return "policy_compliance"
    if "doc" in raw:
        return "documentation"
    return "general_correctness"


def _impact_weight(impact_class: str) -> float:
    weights = {
        "economic_correctness": 1.28,
        "route_reliability_security": 1.18,
        "security": 1.14,
        "general_correctness": 1.0,
        "policy_compliance": 0.68,
        "documentation": 0.42,
        "non_agent_runtime_claim": 0.08,
    }
    return weights.get(str(impact_class or ""), 1.0)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "ok", "go", "proved", "repro", "reproduced", "blocking"}


def hard_public_action_gate(item: dict[str, Any]) -> dict[str, Any]:
    """Decide whether an opportunity may leave scout mode.

    The gate is deliberately stricter than the score. Nomad may *read* and
    locally reproduce many opportunities, but public comments/claims should be
    reserved for proof-bearing work with enough payment and authorization
    confidence to move the external-value ledger.
    """
    mode = str(item.get("work_mode") or "")
    eligible = bool(item.get("eligible"))
    expected = _num(item.get("expected_reward_usd"))
    hourly = expected / max(0.25, _num(item.get("estimated_effort_hours"), 2.5))
    authorization = _num(item.get("authorization_confidence"))
    payment = _num(item.get("payment_confidence"))
    proof = _num(item.get("proof_clarity"))
    safety = _num(item.get("side_effect_safety"))
    agent_fit = _num(item.get("agent_fit"))
    anti_spam = _num(item.get("anti_spam_weight"))
    comment_count = _count(item.get("comment_count") or item.get("comments"))
    unique_repro = _truthy(item.get("has_unique_repro") or item.get("unique_repro") or item.get("blocking_finding"))
    payment_receipt = _truthy(item.get("payment_receipt") or item.get("payment_verified") or item.get("paid"))
    already_found = _truthy(item.get("already_found_by_others") or item.get("duplicate_finding"))
    similar_claim_count = _count(item.get("similar_claim_count_24h") or item.get("pattern_claim_count_24h"))

    blockers: list[str] = []
    if not eligible:
        blockers.append(str(item.get("exclusion_reason") or "not_eligible"))
    if authorization < 0.72:
        blockers.append("authorization_confidence_below_0.72")
    if payment < 0.58:
        blockers.append("payment_confidence_below_0.58")
    if proof < 0.72:
        blockers.append("proof_clarity_below_0.72")
    if safety < 0.70:
        blockers.append("side_effect_safety_below_0.70")
    if agent_fit < 0.62:
        blockers.append("agent_fit_below_0.62")
    if anti_spam < 0.90:
        blockers.append("anti_spam_below_0.90")
    if expected <= 0:
        blockers.append("no_public_reward_signal")
    if comment_count >= 12 and not unique_repro and not payment_receipt:
        blockers.append("crowded_claim_surface_requires_new_unique_proof")
    if already_found and not payment_receipt:
        blockers.append("already_found_by_others")

    public_action = "go_public_after_repro"
    scout_reason = ""
    pattern_capped = similar_claim_count >= 3 and not payment_receipt
    if blockers:
        public_action = "no_go"
    elif pattern_capped:
        public_action = "scout_only"
        scout_reason = "similar_claim_pattern_cap_reached_keep_read_only_until_higher_impact_signal"
    elif mode == "code_review_comment" and not unique_repro:
        public_action = "scout_only"
        scout_reason = "review_lane_requires_unique_repro_or_blocking_finding_before_public_claim"
    elif mode == "bounty_issue_fix_after_subselection":
        public_action = "scout_only"
        scout_reason = "choose_specific_bounty_issue_before_public_work"
    elif mode in {"failing_test_or_audit_pr", "implementation_pr", "issue_triage_or_fix_pr"} and not unique_repro:
        public_action = "scout_only"
        scout_reason = "local_repro_or_patch_digest_required_before_public_claim"

    if payment_receipt:
        public_action = "record_paid"
        scout_reason = "external_payment_receipt_present"

    if public_action == "go_public_after_repro" and hourly < 0.20:
        public_action = "scout_only"
        scout_reason = "expected_value_low_keep_as_background_scout"

    weight = {
        "record_paid": 1.35,
        "go_public_after_repro": 1.0,
        "scout_only": 0.42,
        "no_go": 0.05,
    }.get(public_action, 0.05)

    required_proof = [
        "public_terms_url",
        "local_repro_or_patch_digest",
        "verifier_trace_digest",
        "work_url_after_public_action",
    ]
    if mode == "code_review_comment":
        required_proof.insert(1, "unique_repro_or_blocking_finding")
    if mode == "bounty_issue_fix_after_subselection":
        required_proof.insert(1, "specific_bounty_issue_url")

    return {
        "schema": "nomad.bounty_hard_gate.v1",
        "public_action": public_action,
        "gate_weight": round(weight, 4),
        "blockers": blockers,
        "scout_reason": scout_reason,
        "requires_unique_repro": mode == "code_review_comment",
        "required_proof": required_proof,
        "thresholds": {
            "authorization_confidence_min": 0.72,
            "payment_confidence_min": 0.58,
            "proof_clarity_min": 0.72,
            "side_effect_safety_min": 0.70,
            "anti_spam_weight_min": 0.90,
            "public_hourly_value_usd_min": 0.20,
            "crowded_claim_comment_count": 12,
            "similar_claim_pattern_cap_24h": 3,
        },
        "machine_instruction": "stay_read_only_until_required_proof_exists_then_emit_one_public_claim_and_record_external_value_stage",
    }


DEFAULT_BOUNTY_SEEDS: list[dict[str, Any]] = [
    {
        "opportunity_id": "rustchain_utxo_static_red_team",
        "source_url": "https://github.com/Scottcjn/rustchain-bounties/issues/2819",
        "repo": "Scottcjn/Rustchain",
        "title": "[BOUNTY] Red Team UTXO Implementation - Find Bugs, Earn RTC",
        "reward_text": "25-200 RTC",
        "floor_usd": 2.5,
        "ceiling_usd": 20.0,
        "currency": "RTC",
        "work_mode": "failing_test_or_audit_pr",
        "authorized_scope": "Static/local review and failing-test PRs for node/utxo_db.py and adjacent UTXO tests.",
        "proof_path": "PR or issue with reproducible local failing test, proof digest, and verifier trace.",
        "estimated_effort_hours": 4.0,
        "authorization_confidence": 0.95,
        "payment_confidence": 0.68,
        "proof_clarity": 0.86,
        "agent_fit": 0.82,
        "side_effect_safety": 0.80,
        "anti_spam_weight": 1.0,
        "eligible": True,
    },
    {
        "opportunity_id": "rustchain_pr_review_bounty",
        "source_url": "https://github.com/Scottcjn/rustchain-bounties/issues/73",
        "repo": "Scottcjn/Rustchain",
        "title": "[BOUNTY] Code Review Bounty Program - Review PRs, Earn RTC",
        "reward_text": "5-25 RTC",
        "floor_usd": 0.5,
        "ceiling_usd": 2.5,
        "currency": "RTC",
        "work_mode": "code_review_comment",
        "authorized_scope": "Review open PRs with concrete correctness/security/test feedback.",
        "proof_path": "Public GitHub PR review plus bounty issue claim linking the review.",
        "estimated_effort_hours": 0.9,
        "authorization_confidence": 0.90,
        "payment_confidence": 0.72,
        "proof_clarity": 0.90,
        "agent_fit": 0.86,
        "side_effect_safety": 0.86,
        "anti_spam_weight": 1.0,
        "eligible": True,
    },
    {
        "opportunity_id": "conversejs_bounty_issue_fix",
        "source_url": "https://github.com/conversejs/converse.js/issues/2481",
        "repo": "conversejs/converse.js",
        "title": "Converse.js bounty-labeled issue fixes",
        "reward_text": "$100",
        "floor_usd": 100.0,
        "ceiling_usd": 100.0,
        "currency": "USD",
        "work_mode": "bounty_issue_fix_after_subselection",
        "authorized_scope": "Only issues with bounty label; fix must include tests/docs and maintainer-acceptable PR.",
        "proof_path": "Merged PR for a specific bounty-labeled issue; payout handled privately after maintainer verification.",
        "estimated_effort_hours": 10.0,
        "authorization_confidence": 0.74,
        "payment_confidence": 0.78,
        "proof_clarity": 0.66,
        "agent_fit": 0.58,
        "side_effect_safety": 0.88,
        "anti_spam_weight": 1.0,
        "eligible": True,
        "subselection_query": "gh issue list -R conversejs/converse.js -l bounty --state open",
    },
    {
        "opportunity_id": "rustchain_bug_report_bounty",
        "source_url": "https://github.com/Scottcjn/Rustchain/issues/305",
        "repo": "Scottcjn/Rustchain",
        "title": "[BOUNTY] Report a Bug",
        "reward_text": "5-15 RTC",
        "floor_usd": 0.5,
        "ceiling_usd": 1.5,
        "currency": "RTC",
        "work_mode": "failing_test_or_audit_pr",
        "authorized_scope": "Legitimate bug report with clear reproduction and expected behavior.",
        "proof_path": "Issue or PR with minimal reproduction, trace digest, and concrete impact.",
        "estimated_effort_hours": 1.2,
        "authorization_confidence": 0.82,
        "payment_confidence": 0.62,
        "proof_clarity": 0.72,
        "agent_fit": 0.74,
        "side_effect_safety": 0.84,
        "anti_spam_weight": 1.0,
        "eligible": True,
    },
]


def normalize_opportunity(raw: dict[str, Any], *, source: str = "seed") -> dict[str, Any]:
    title = _text(raw.get("title"), 220)
    body = _text(raw.get("body"), 2000)
    classified = _classify_work(title, body)
    reward = extract_reward(f"{title}\n{body}\n{raw.get('reward_text') or ''}")
    floor = _num(raw.get("floor_usd"), _num(reward.get("floor_usd")))
    ceiling = _num(raw.get("ceiling_usd"), _num(reward.get("ceiling_usd"), floor))
    if ceiling < floor:
        floor, ceiling = ceiling, floor
    repo_number_id = f"{raw.get('repo')}#{raw.get('number')}" if raw.get("repo") and raw.get("number") else ""
    opportunity_id = _clean_id(
        raw.get("opportunity_id")
        or repo_number_id
        or raw.get("url")
        or raw.get("source_url")
        or f"{raw.get('repo', 'unknown')}:{title}",
        fallback=f"bounty-{_digest(raw, 10)}",
    )
    effort_default = 10.0 if classified["work_mode"] == "bounty_issue_fix_after_subselection" else 2.5
    merged = {
        "opportunity_id": opportunity_id,
        "source": source,
        "source_url": _text(raw.get("source_url") or raw.get("url"), 260),
        "repo": _text(raw.get("repo") or raw.get("repository"), 160),
        "title": title,
        "reward_text": _text(raw.get("reward_text") or reward.get("reward_text"), 120),
        "currency": _text(raw.get("currency") or reward.get("currency"), 40),
        "floor_usd": round(floor, 4),
        "ceiling_usd": round(ceiling, 4),
        "expected_reward_usd": round(0.35 * floor + 0.65 * ceiling, 4),
        "work_mode": _text(raw.get("work_mode") or classified["work_mode"], 80),
        "impact_class": _text(raw.get("impact_class") or _impact_class(title, body, raw.get("work_mode") or classified["work_mode"]), 80),
        "finding_pattern": _text(raw.get("finding_pattern") or "", 120),
        "authorized_scope": _text(raw.get("authorized_scope") or "Public bounty terms only; local/static work unless repo rules say otherwise.", 260),
        "proof_path": _text(raw.get("proof_path") or "PR/issue/review URL plus reproducible proof digest and verifier trace.", 260),
        "estimated_effort_hours": max(0.25, _num(raw.get("estimated_effort_hours"), effort_default)),
        "authorization_confidence": _clamp(_num(raw.get("authorization_confidence"), 0.72)),
        "payment_confidence": _clamp(_num(raw.get("payment_confidence"), 0.62)),
        "proof_clarity": _clamp(_num(raw.get("proof_clarity"), _num(classified.get("proof_clarity"), 0.62))),
        "agent_fit": _clamp(_num(raw.get("agent_fit"), _num(classified.get("agent_fit"), 0.62))),
        "side_effect_safety": _clamp(_num(raw.get("side_effect_safety"), _num(classified.get("side_effect_safety"), 0.70))),
        "anti_spam_weight": _clamp(_num(raw.get("anti_spam_weight"), _num(classified.get("anti_spam_weight"), 0.88))),
        "eligible": bool(raw.get("eligible", classified.get("eligible", True))),
        "exclusion_reason": _text(raw.get("exclusion_reason") or classified.get("exclusion_reason"), 160),
        "subselection_query": _text(raw.get("subselection_query"), 220),
        "comment_count": _count(raw.get("comment_count") if "comment_count" in raw else raw.get("comments")),
        "has_unique_repro": _truthy(raw.get("has_unique_repro") or raw.get("unique_repro") or raw.get("blocking_finding")),
        "payment_receipt": _truthy(raw.get("payment_receipt") or raw.get("payment_verified") or raw.get("paid")),
        "already_found_by_others": _truthy(raw.get("already_found_by_others") or raw.get("duplicate_finding")),
        "similar_claim_count_24h": _count(raw.get("similar_claim_count_24h") or raw.get("pattern_claim_count_24h")),
    }
    if not merged["source_url"] and raw.get("number") and merged["repo"]:
        merged["source_url"] = f"https://github.com/{merged['repo']}/issues/{raw['number']}"
    return merged


def score_bounty_opportunity(raw: dict[str, Any]) -> dict[str, Any]:
    item = normalize_opportunity(raw, source=str(raw.get("source") or "seed"))
    liquidity = 0.96 if item["currency"].upper() == "USD" else 0.46 if item["currency"].upper() == "RTC" else 0.28
    hourly_value = _num(item.get("expected_reward_usd")) / max(0.25, _num(item.get("estimated_effort_hours"), 2.5))
    base_score = (
        hourly_value
        * _num(item.get("authorization_confidence"))
        * _num(item.get("payment_confidence"))
        * _num(item.get("proof_clarity"))
        * _num(item.get("agent_fit"))
        * _num(item.get("side_effect_safety"))
        * _num(item.get("anti_spam_weight"))
        * liquidity
        * _impact_weight(str(item.get("impact_class") or ""))
    )
    if not item.get("eligible"):
        base_score *= 0.05
    gate = hard_public_action_gate(item)
    score = base_score * _num(gate.get("gate_weight"), 1.0)
    item["bounty_score"] = round(score, 6)
    item["raw_bounty_score"] = round(base_score, 6)
    item["hard_gate"] = gate
    item["score_components"] = {
        "hourly_value_usd": round(hourly_value, 4),
        "authorization_confidence": item["authorization_confidence"],
        "payment_confidence": item["payment_confidence"],
        "proof_clarity": item["proof_clarity"],
        "agent_fit": item["agent_fit"],
        "side_effect_safety": item["side_effect_safety"],
        "anti_spam_weight": item["anti_spam_weight"],
        "currency_liquidity": round(liquidity, 4),
        "impact_class": item.get("impact_class"),
        "impact_weight": round(_impact_weight(str(item.get("impact_class") or "")), 4),
        "hard_gate_weight": _num(gate.get("gate_weight"), 1.0),
    }
    item["claim_next"] = _claim_next(item)
    return item


def _claim_next(item: dict[str, Any]) -> dict[str, Any]:
    mode = str(item.get("work_mode") or "")
    repo = str(item.get("repo") or "")
    if mode == "code_review_comment":
        return {
            "first_action": f"gh pr list -R {repo} --state open --limit 20 --json number,title,url,labels,updatedAt",
            "work_rule": "review_one_small_open_pr_with_actionable_tests_security_correctness_feedback_then_claim_with_review_url",
        }
    if mode == "bounty_issue_fix_after_subselection":
        query = str(item.get("subselection_query") or f"gh issue list -R {repo} -l bounty --state open")
        return {
            "first_action": query,
            "work_rule": "select_specific_bounty_issue_before_cloning_then_submit_fix_pr_with_tests",
        }
    if "audit" in mode or "failing_test" in mode:
        return {
            "first_action": f"gh repo clone {repo} external_work/{_clean_id(repo.replace('/', '-'))}",
            "work_rule": "local_static_review_or_failing_test_only_then_pr_or_issue_with_reproducible_trace",
        }
    return {
        "first_action": f"gh issue view {item.get('source_url') or ''}",
        "work_rule": "read_terms_then_prepare_proof_first_claim_second",
    }


def github_issue_to_opportunity(issue: dict[str, Any], *, repo: str, source: str = "github") -> dict[str, Any]:
    labels = [str(label.get("name") or "") for label in _items(issue.get("labels"))]
    raw = {
        "repo": repo,
        "number": issue.get("number"),
        "url": issue.get("url"),
        "source_url": issue.get("url"),
        "title": issue.get("title"),
        "body": issue.get("body"),
        "source": source,
        "labels": labels,
        "comments": issue.get("comments"),
    }
    return normalize_opportunity(raw, source=source)


def discover_github_bounties(*, limit: int = 10) -> list[dict[str, Any]]:
    """Use local gh auth to collect public bounty candidates for CLI runs.

    The API surface does not call this function. It is intentionally bounded and
    read-only, so it can seed human/operator-reviewed paid work without posting.
    """
    repos = ["Scottcjn/rustchain-bounties", "Scottcjn/Rustchain", "conversejs/converse.js"]
    discoveries: list[dict[str, Any]] = []
    per_repo = max(1, min(int(limit or 10), 25))
    for repo in repos:
        cmd = [
            "gh",
            "issue",
            "list",
            "-R",
            repo,
            "-l",
            "bounty",
            "--state",
            "open",
            "--limit",
            str(per_repo),
            "--json",
            "number,title,url,labels,updatedAt,comments,body",
        ]
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0:
            continue
        try:
            rows = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError:
            continue
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict):
                discoveries.append(github_issue_to_opportunity(row, repo=repo, source="github"))
    return discoveries[: max(1, min(int(limit or 10) * len(repos), 80))]


def build_bounty_hunter_surface(
    *,
    base_url: str,
    discoveries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    raw_items = [normalize_opportunity(item, source="seed") for item in DEFAULT_BOUNTY_SEEDS]
    raw_items.extend(normalize_opportunity(item, source=str(item.get("source") or "external")) for item in _items(discoveries))
    scored_all = [score_bounty_opportunity(item) for item in raw_items]
    deduped: dict[str, dict[str, Any]] = {}
    for item in scored_all:
        key = str(item.get("source_url") or item.get("opportunity_id") or "")
        existing = deduped.get(key)
        if not existing or _num(item.get("bounty_score")) > _num(existing.get("bounty_score")):
            deduped[key] = item
    scored = list(deduped.values())
    scored.sort(key=lambda item: float(item.get("bounty_score") or 0.0), reverse=True)
    eligible = [item for item in scored if item.get("eligible")]
    excluded = [item for item in scored if not item.get("eligible")]
    public_go = [item for item in eligible if _dict(item.get("hard_gate")).get("public_action") in {"go_public_after_repro", "record_paid"}]
    scout_only = [item for item in eligible if _dict(item.get("hard_gate")).get("public_action") == "scout_only"]
    no_go = [item for item in scored if _dict(item.get("hard_gate")).get("public_action") == "no_go"]
    top = eligible[0] if eligible else (scored[0] if scored else {})
    top_public = public_go[0] if public_go else {}
    top_scout = scout_only[0] if scout_only else {}
    digest_core = {
        "top": top.get("opportunity_id"),
        "top_public": top_public.get("opportunity_id"),
        "top_scout": top_scout.get("opportunity_id"),
        "scores": [(item.get("opportunity_id"), item.get("bounty_score")) for item in scored[:8]],
        "count": len(scored),
    }
    floor = sum(_num(item.get("floor_usd")) for item in eligible)
    ceiling = sum(_num(item.get("ceiling_usd")) for item in eligible)
    return {
        "ok": True,
        "schema": "nomad.bounty_hunter.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "bounty_digest": f"nomad-bounty-hunter-{_digest(digest_core)}",
        "read_url": _u(base_url, "/swarm/bounty-hunter"),
        "well_known_url": _u(base_url, "/.well-known/nomad-bounty-hunter.json"),
        "mechanism": "authorized_public_bounty_contract_net_with_proof_first_claim_second",
        "score_formula": "expected_reward_per_hour * authorization * payment * proof_clarity * agent_fit * side_effect_safety * anti_spam * currency_liquidity",
        "summary": {
            "opportunity_count": len(scored),
            "eligible_count": len(eligible),
            "excluded_count": len(excluded),
            "eligible_floor_usd": round(floor, 4),
            "eligible_ceiling_usd": round(ceiling, 4),
            "top_score": _num(top.get("bounty_score")),
            "top_work_mode": top.get("work_mode", ""),
            "public_go_count": len(public_go),
            "scout_only_count": len(scout_only),
            "no_go_count": len(no_go),
        },
        "top_candidate": top,
        "top_public_candidate": top_public,
        "top_scout_candidate": top_scout,
        "opportunities": eligible[:12],
        "excluded_lanes": excluded[:8],
        "hard_selection": {
            "schema": "nomad.bounty_hard_selection.v1",
            "rule": "public_action_requires_local_repro_or_specific_bounty_selection; reviews_require_unique_blocking_signal",
            "public_go_count": len(public_go),
            "scout_only_count": len(scout_only),
            "no_go_count": len(no_go),
            "next_machine_move": "scout_top_scout_candidate_read_only_until_required_proof_exists",
        },
        "claim_contract": {
            "required_fields": [
                "agent_id",
                "opportunity_id",
                "source_url",
                "work_url",
                "proof_digest",
                "verifier_trace_digest",
            ],
            "optional_private_fields": ["payout_ref_env_name"],
            "payout_secret_rule": "never_put_wallet_bank_email_or_private_payment_token_in_repo_public_json_or_claim_text",
            "payout_ref_hint": "NOMAD_BOUNTY_PAYOUT_REF",
            "idempotency_key_hint": "sha256(agent_id|opportunity_id|work_url|proof_digest)",
            "claim_order": [
                "read_public_terms",
                "produce_local_or_pr_proof",
                "verify_work_url_is_public_and_reproducible",
                "claim_on_program_surface_without_private_payout_secret",
                "record_payment_only_after_program_verification",
            ],
        },
        "next": [
            {"op": "GET", "url": _u(base_url, "/swarm/bounty-hunter"), "reason": "rank_paid_public_bounty_work"},
            {"op": "GET", "url": top.get("source_url", ""), "reason": "read_top_candidate_terms"} if top else {},
            {"op": "LOCAL", "command": (top.get("claim_next") or {}).get("first_action", ""), "reason": "start_proof_work_read_only_or_local"},
            {"op": "POST", "url": _u(base_url, "/swarm/experience"), "reason": "feed_successful_bounty_proof_back_into_nomad_skill_library"},
            {"op": "POST", "url": _u(base_url, "/swarm/paid-ref/verify"), "reason": "only_after_real_external_payment_or_program_receipt"},
        ],
        "links": {
            "paid_ref_market": _u(base_url, "/.well-known/nomad-paid-ref-market.json"),
            "selfplay": _u(base_url, "/.well-known/nomad-paid-ref-selfplay.json"),
            "microtask_submit": _u(base_url, "/swarm/microtask/submit"),
            "experience": _u(base_url, "/swarm/experience"),
            "compute_market": _u(base_url, "/swarm/compute-market"),
        },
        "machine_instruction": "select_highest_bounty_score_authorized_lane_then_create_reproducible_pr_or_review_proof_do_not_count_reward_until_external_program_verifies_payment",
        "science_basis": [
            {"id": "contract_net_task_allocation", "source": "smith_1980_contract_net_protocol"},
            {"id": "market_scored_agent_task_selection", "source": "agent_economy_machine_to_machine_settlement_literature"},
            {"id": "structured_environment_over_chatbot_swarm", "source": "multi_agent_systems_protocol_and_measurement_critiques"},
            {"id": "proof_carrying_work", "source": "verifiable_computation_and_reproducible_oss_maintenance_practice"},
        ],
    }
