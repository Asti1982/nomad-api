"""Truthful referral-offer surface for low-risk Nomad cashflow offsets."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any


DEFAULT_CURSOR_REFERRAL_URL = "https://cursor.com/referral?code=U7OPZAP4BZWH"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _cursor_referral_url() -> str:
    return _text(os.getenv("NOMAD_CURSOR_REFERRAL_URL") or DEFAULT_CURSOR_REFERRAL_URL, 700)


def build_referral_offer_surface(*, base_url: str = "") -> dict[str, Any]:
    """Expose one non-spam referral offer as a measurable channel, not revenue."""
    referral_url = _cursor_referral_url()
    offer = {
        "schema": "nomad.referral_offer.v1",
        "offer_id": "cursor_referral_20260515",
        "provider": "Cursor",
        "category": "ai_code_editor",
        "referral_url": referral_url,
        "buyer_benefit": {
            "summary": "New users with the referral link get 50% off their first month of Cursor Pro, Pro+, or Ultra.",
            "operator_supplied": True,
            "requires_user_plan_purchase": True,
        },
        "nomad_benefit": {
            "summary": "Nomad may receive Cursor usage credit after a referred customer buys a qualifying plan.",
            "credit_per_paid_referral_usd": 25,
            "max_rewards_per_billing_cycle": 10,
            "max_credit_per_billing_cycle_usd": 250,
            "benefit_type": "usage_credit_not_cash",
        },
        "accounting_rule": {
            "recognized_revenue_usd": 0.0,
            "recognized_only_when": "Cursor account shows credited usage or an exportable referral receipt exists.",
            "do_not_count": ["link_share", "click", "signup_without_paid_plan", "unverified_referral_history"],
        },
        "disclosure_text": (
            "Referral disclosure: this link may give the referrer Cursor usage credit if a new user buys a qualifying plan."
        ),
        "audience_fit": [
            "developers already evaluating AI code editors",
            "agents or teams blocked by local coding throughput",
            "Nomad users who need a discounted first month rather than generic hype",
        ],
        "anti_spam_policy": [
            "do_not_dm_people_without_context",
            "do_not_post_in_communities_that_ban_referrals",
            "share_only_next_to_real_cursor_relevant_help_or_tooling",
            "always_disclose_referrer_benefit",
        ],
        "measurement": {
            "stage": "found",
            "funnel": ["surface_view", "qualified_click", "paid_conversion", "credit_verified"],
            "current_verified_credits_usd": 0.0,
        },
    }
    copy_variants = [
        {
            "id": "plain_discount_disclosure_de",
            "language": "de",
            "text": (
                "Falls du Cursor Pro, Pro+ oder Ultra ohnehin testen willst: ueber diesen Referral-Link "
                "gibt es 50% Rabatt auf den ersten Monat. Disclosure: Wenn daraus ein bezahlter Plan wird, "
                "kann Nomad Cursor-Usage-Credit bekommen."
            ),
            "url": referral_url,
        },
        {
            "id": "agent_toolchain_en",
            "language": "en",
            "text": (
                "If Cursor is already on your AI coding shortlist, this referral link gives new users "
                "50% off the first month of Pro, Pro+, or Ultra. Disclosure: Nomad may receive usage "
                "credit if a referred user buys a qualifying plan."
            ),
            "url": referral_url,
        },
    ]
    digest_core = {
        "offer": offer["offer_id"],
        "url": referral_url,
        "cap": offer["nomad_benefit"]["max_credit_per_billing_cycle_usd"],
        "policy": offer["anti_spam_policy"],
    }
    return {
        "ok": True,
        "schema": "nomad.referral_offer_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "surface_digest": f"nomad-referral-offers-{_digest(digest_core)}",
        "read_url": _u(base_url, "/swarm/referral-offers"),
        "well_known_url": _u(base_url, "/.well-known/nomad-referral-offers.json"),
        "offer_count": 1,
        "offers": [offer],
        "copy_variants": copy_variants,
        "machine_instruction": (
            "Use referral offers only in relevant opt-in contexts with disclosure; record no revenue until verified credit appears."
        ),
        "revenue_guard": {
            "recognized_revenue_usd_total": 0.0,
            "credit_is_cost_offset_not_cash": True,
            "paid_receipt_required": True,
        },
    }
