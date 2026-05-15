"""Delayed-feedback referral swarm routing for truthful Nomad growth."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from nomad_referral_offers import build_referral_offer_surface


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _text(value: Any, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _score_arm(arm: dict[str, Any]) -> float:
    opt_in = float(arm.get("opt_in", 0.0))
    relevance = float(arm.get("relevance", 0.0))
    proofability = float(arm.get("proofability", 0.0))
    agent_gain = float(arm.get("agent_gain", 0.0))
    novelty = float(arm.get("machine_novelty", 0.0))
    spam_risk = float(arm.get("spam_risk", 1.0))
    return round(
        (0.30 * opt_in)
        + (0.24 * relevance)
        + (0.18 * proofability)
        + (0.18 * agent_gain)
        + (0.10 * novelty)
        - (0.55 * spam_risk),
        4,
    )


def _channel_arms(referral_url: str) -> list[dict[str, Any]]:
    return [
        {
            "arm_id": "owned_nomad_well_known_surface",
            "surface": "/.well-known/nomad-referral-offers.json",
            "audience": "agents_and_developers_already_inside_nomad",
            "action": "publish_machine_readable_beacon",
            "opt_in": 1.0,
            "relevance": 0.86,
            "proofability": 0.92,
            "agent_gain": 0.72,
            "machine_novelty": 0.68,
            "spam_risk": 0.01,
            "outbound_required": False,
            "allowed_without_human_approval": True,
            "referral_url": referral_url,
        },
        {
            "arm_id": "nomad_download_readme_footer",
            "surface": "/downloads",
            "audience": "users_already_trying_nomad_worker_artifacts",
            "action": "append_disclosed_tool_credit_footer_on_owned_surfaces",
            "opt_in": 0.91,
            "relevance": 0.80,
            "proofability": 0.86,
            "agent_gain": 0.70,
            "machine_novelty": 0.58,
            "spam_risk": 0.04,
            "outbound_required": False,
            "allowed_without_human_approval": True,
            "referral_url": referral_url,
        },
        {
            "arm_id": "agent_endpoint_disclosure_packet",
            "surface": "/swarm/referral-swarm",
            "audience": "agent_endpoints_that_have_already_requested_nomad_context",
            "action": "attach_referral_packet_only_after_agent_contact_is_allowed",
            "opt_in": 0.76,
            "relevance": 0.74,
            "proofability": 0.78,
            "agent_gain": 0.86,
            "machine_novelty": 0.92,
            "spam_risk": 0.12,
            "outbound_required": False,
            "allowed_without_human_approval": True,
            "referral_url": referral_url,
        },
        {
            "arm_id": "cursor_relevant_support_answer",
            "surface": "human_approved_external_reply",
            "audience": "people_already_asking_about_cursor_or_ai_editor_choice",
            "action": "answer_the_actual_question_first_then_offer_discount_with_disclosure",
            "opt_in": 0.66,
            "relevance": 0.96,
            "proofability": 0.64,
            "agent_gain": 0.58,
            "machine_novelty": 0.36,
            "spam_risk": 0.20,
            "outbound_required": True,
            "allowed_without_human_approval": False,
            "referral_url": referral_url,
        },
        {
            "arm_id": "cold_social_broadcast",
            "surface": "general_hype_feeds",
            "audience": "unqualified_public_attention",
            "action": "blocked",
            "opt_in": 0.04,
            "relevance": 0.28,
            "proofability": 0.08,
            "agent_gain": 0.15,
            "machine_novelty": 0.18,
            "spam_risk": 0.92,
            "outbound_required": True,
            "allowed_without_human_approval": False,
            "referral_url": referral_url,
        },
        {
            "arm_id": "unsolicited_dm_sequence",
            "surface": "private_inboxes",
            "audience": "people_who_did_not_ask_for_cursor_or_nomad",
            "action": "blocked",
            "opt_in": 0.01,
            "relevance": 0.16,
            "proofability": 0.05,
            "agent_gain": 0.06,
            "machine_novelty": 0.10,
            "spam_risk": 0.98,
            "outbound_required": True,
            "allowed_without_human_approval": False,
            "referral_url": referral_url,
        },
    ]


def build_referral_swarm_surface(
    *,
    base_url: str = "",
    referral_offers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rank referral channels as delayed-reward arms and block spam-shaped growth."""
    offers_surface = referral_offers or build_referral_offer_surface(base_url=base_url)
    offers = [offer for offer in offers_surface.get("offers", []) if isinstance(offer, dict)]
    first_offer = offers[0] if offers else {}
    referral_url = _text(first_offer.get("referral_url") or "")
    arms = []
    for arm in _channel_arms(referral_url):
        scored = dict(arm)
        scored["bandit_priority"] = _score_arm(scored)
        scored["decision"] = (
            "blocked"
            if scored["action"] == "blocked" or scored["spam_risk"] >= 0.7
            else ("active_owned_surface" if scored["allowed_without_human_approval"] else "requires_human_approval")
        )
        scored["delayed_reward_observation"] = {
            "positive_signal": "verified_cursor_usage_credit_receipt",
            "weak_signal": "qualified_opt_in_click_with_referral_disclosure",
            "anti_signal": "complaint_unsubscribed_or_contextless_share",
            "recognize_revenue_usd": 0.0,
        }
        arms.append(scored)

    ranked_arms = sorted(arms, key=lambda item: item["bandit_priority"], reverse=True)
    blocked_arms = [arm for arm in ranked_arms if arm["decision"] == "blocked"]
    active_arms = [arm for arm in ranked_arms if arm["decision"] == "active_owned_surface"]
    approval_arms = [arm for arm in ranked_arms if arm["decision"] == "requires_human_approval"]
    digest_core = {
        "offer_digest": offers_surface.get("surface_digest"),
        "arms": [(arm["arm_id"], arm["bandit_priority"], arm["decision"]) for arm in ranked_arms],
        "url": referral_url,
    }
    return {
        "ok": True,
        "schema": "nomad.referral_swarm.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "surface_digest": f"nomad-referral-swarm-{_digest(digest_core)}",
        "read_url": _u(base_url, "/swarm/referral-swarm"),
        "well_known_url": _u(base_url, "/.well-known/nomad-referral-swarm.json"),
        "objective": (
            "Turn opt-in AI-coding-tool demand into buyer discount utility, possible Cursor usage-credit offsets, "
            "and new Nomad agent contact points without treating attention as revenue."
        ),
        "science_basis": [
            {
                "concept": "delayed_feedback_bandit",
                "why": "Referral reward arrives late and only after a paid plan, so channel choice must preserve arms without overreacting to clicks.",
            },
            {
                "concept": "stigmergic_owned_surfaces",
                "why": "Agents can discover machine-readable beacons without private persuasion or repeated human posting.",
            },
            {
                "concept": "negative_reward_for_spam",
                "why": "A channel that creates complaints or opaque accounting is treated as fitness loss even if it creates short-term attention.",
            },
            {
                "concept": "anti_majority_growth",
                "why": "The most human-obvious growth action, broad social broadcasting, is explicitly blocked unless a relevant opt-in context exists.",
            },
        ],
        "reward_model": {
            "primary_reward": "verified_cursor_usage_credit_receipt",
            "secondary_reward": "qualified_opt_in_click_with_disclosure",
            "anti_reward": "unsolicited_public_or_private_referral_spam",
            "accounting_rule": "recognized_revenue_usd stays 0 until a verifiable positive credit receipt exists",
            "recognized_revenue_usd_total": 0.0,
        },
        "channel_arms": ranked_arms,
        "active_owned_arms": active_arms,
        "human_approval_required_arms": approval_arms,
        "blocked_arms": blocked_arms,
        "first_actions": [
            {
                "action_id": "publish_referral_swarm_surface",
                "surface": "/.well-known/nomad-referral-swarm.json",
                "outbound_required": False,
                "success_metric": "machine_readable_surface_available",
            },
            {
                "action_id": "crosslink_owned_offer_surface",
                "surface": "/.well-known/nomad-referral-offers.json",
                "outbound_required": False,
                "success_metric": "offer_and_swarm_surfaces_have_matching_referral_digest",
            },
            {
                "action_id": "prepare_approved_contextual_reply",
                "surface": "external_cursor_relevant_threads_only_after_user_approval",
                "outbound_required": True,
                "success_metric": "reply_helpfulness_before_referral_click",
            },
        ],
        "copy_packets": [
            {
                "id": "machine_packet",
                "language": "machine",
                "text": (
                    "Use only in opt-in AI-coding-tool contexts. Disclose referrer benefit. "
                    "Do not count link shares, clicks, or unpaid signups as revenue."
                ),
                "url": referral_url,
            },
            {
                "id": "minimal_de",
                "language": "de",
                "text": (
                    "Wenn Cursor ohnehin relevant ist: 50% Rabatt im ersten Monat ueber diesen Link. "
                    "Disclosure: Nomad kann bei einem bezahlten Plan Cursor-Usage-Credit erhalten."
                ),
                "url": referral_url,
            },
        ],
        "agent_recruitment_hook": {
            "message": "Discount is the bait only when the tool is already useful; the real ask is an opt-in signal back to Nomad.",
            "join_url": _u(base_url, "/swarm/join"),
            "offer_url": offers_surface.get("well_known_url") or _u(base_url, "/.well-known/nomad-referral-offers.json"),
        },
        "machine_instruction": (
            "Prefer active owned arms, keep external replies human-approved, block cold broadcasts and unsolicited DMs, "
            "and update weights only after delayed credit or negative-context observations."
        ),
        "revenue_guard": {
            "recognized_revenue_usd_total": 0.0,
            "credit_is_cost_offset_not_cash": True,
            "paid_receipt_required": True,
        },
    }
