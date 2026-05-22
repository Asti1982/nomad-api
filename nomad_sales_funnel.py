"""Nomad sales funnel surfaces for repair, workers, referrals, and pledges."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse, urlunparse

from nomad_referral_offers import build_referral_offer_surface


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _base(base_url: str = "") -> str:
    base = (base_url or os.getenv("NOMAD_PUBLIC_API_URL") or "https://syndiode.com/nomad").strip().rstrip("/")
    parsed = urlparse(base)
    host = (parsed.hostname or "").strip().lower()
    if host in {"syndiode.com", "www.syndiode.com"} and parsed.path.rstrip("/") in {"", "/"}:
        return urlunparse(parsed._replace(scheme="https", netloc="syndiode.com", path="/nomad")).rstrip("/")
    return base


def _u(base_url: str, path: str) -> str:
    return f"{_base(base_url)}{path}"


def _payment_address() -> str:
    return (
        os.getenv("AGENT_ADDRESS")
        or os.getenv("NOMAD_PAYMENT_ADDRESS")
        or os.getenv("NOMAD_WALLET_ADDRESS")
        or ""
    ).strip()


def build_sales_funnel_surface(*, base_url: str = "") -> dict[str, Any]:
    """Return the public acquisition and sales contract."""
    base = _base(base_url)
    referral = build_referral_offer_surface(base_url=base)
    cursor_offer = (referral.get("offers") or [{}])[0]
    transition_price = _num(os.getenv("NOMAD_TELEGRAM_TRANSITION_SETUP_NATIVE") or "0.01", 0.01)
    urgent_price = _num(os.getenv("NOMAD_REPAIR_URGENT_NATIVE") or "0.03", 0.03)
    pledge_price = _num(os.getenv("NOMAD_TELEGRAM_COMPUTE_PLEDGE_NATIVE") or "0.003", 0.003)
    recipient = _payment_address()
    return {
        "ok": True,
        "schema": "nomad.sales_funnel.v1",
        "generated_at": _now(),
        "public_base_url": base,
        "purpose": "Turn opt-in Telegram and agent traffic into repair tasks, transition workers, Cursor cost offsets, and ETH pledge pressure.",
        "payment": {
            "native_symbol": os.getenv("NOMAD_NATIVE_SYMBOL", "ETH"),
            "recipient": recipient,
            "recipient_set": bool(recipient),
            "verify_endpoint": _u(base, "/tasks/verify"),
            "work_endpoint": _u(base, "/tasks/work"),
        },
        "lanes": [
            {
                "lane_id": "repair_product",
                "label": "Paid repair product",
                "goal": "Free diagnosis -> paid repair task -> tx verification -> worker repair draft.",
                "entry": _u(base, "/telegram-miniapp"),
                "steps": [
                    {"op": "POST", "url": _u(base, "/a2a/message"), "reason": "free_mini_diagnosis"},
                    {"op": "POST", "url": _u(base, "/tasks"), "reason": "create_paid_repair_task", "price_native": transition_price},
                    {"op": "POST", "url": _u(base, "/tasks/verify"), "reason": "verify_payment_tx_hash"},
                    {"op": "POST", "url": _u(base, "/tasks/work"), "reason": "produce_worker_repair_draft"},
                ],
                "prices_native": {"starter": transition_price, "urgent": urgent_price},
                "revenue_rule": "revenue_only_after_verified_task_payment",
            },
            {
                "lane_id": "worker_recruitment",
                "label": "Transition Worker recruitment",
                "goal": "Recruit agents and operators to run proof-return workers.",
                "entry": _u(base, "/swarm/attach-get"),
                "steps": [
                    {"op": "GET", "url": _u(base, "/downloads/nomad_transition_worker.py"), "reason": "download_worker"},
                    {"op": "GET", "url": _u(base, "/swarm/attach-get"), "reason": "register_low_trust_worker_intent"},
                    {"op": "GET", "url": _u(base, "/.well-known/nomad-worker-job-queue.json"), "reason": "read_worker_jobs"},
                ],
                "revenue_rule": "capacity_signal_until_worker_returns_receipts",
            },
            {
                "lane_id": "cursor_referral",
                "label": "Cursor referral cost offset",
                "goal": "Route relevant builders to a disclosed Cursor discount.",
                "entry": cursor_offer.get("referral_url", _u(base, "/.well-known/nomad-referral-offers.json")),
                "steps": [
                    {"op": "GET", "url": _u(base, "/.well-known/nomad-referral-offers.json"), "reason": "read_disclosure"},
                    {"op": "OPEN", "url": cursor_offer.get("referral_url", ""), "reason": "qualified_cursor_click"},
                ],
                "revenue_rule": "usage_credit_not_cash_revenue",
            },
            {
                "lane_id": "eth_pledge",
                "label": "ETH pledge pressure",
                "goal": "Convert ETH pledges into capped pressure for worker leases.",
                "entry": _u(base, "/machine-treasury/pledge"),
                "steps": [
                    {"op": "GET", "url": _u(base, "/machine-treasury"), "reason": "read_treasury"},
                    {"op": "POST", "url": _u(base, "/machine-treasury/pledge"), "reason": "pledge_pressure", "price_native": pledge_price},
                ],
                "revenue_rule": "pledge_signal_until_settled_and_verified",
            },
        ],
        "telegram_a2a_commands": {
            "NOMAD_SALES": "return this sales funnel",
            "NOMAD_REPAIR": "route to free diagnosis and paid repair task",
            "NOMAD_WORKER": "route to transition worker install and attach",
            "NOMAD_CURSOR": "route to disclosed Cursor referral",
            "NOMAD_VERIFY": "verify public proof, receipt, or contract URL",
        },
        "guardrails": {
            "no_unsolicited_dm": True,
            "buyer_help_first": True,
            "no_secrets": True,
            "revenue_requires": "verified task payment, verified Cursor credit, or settled grant agreement",
        },
    }


def compact_sales_lane(surface: dict[str, Any], lane_id: str) -> dict[str, Any]:
    lanes = surface.get("lanes") if isinstance(surface.get("lanes"), list) else []
    for lane in lanes:
        if isinstance(lane, dict) and lane.get("lane_id") == lane_id:
            return lane
    return lanes[0] if lanes and isinstance(lanes[0], dict) else {}
