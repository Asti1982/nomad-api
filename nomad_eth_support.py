"""Ethereum AI-agent support packet for Nomad.

This surface is an outreach-ready, machine-readable bridge between Nomad's
proof-gated worker loop and Ethereum public-goods support channels.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: Any, limit: int = 600) -> str:
    raw = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return " ".join(raw.split())[:limit]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _u(base_url: str, path: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    return f"{base}{path}" if base else path


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def build_eth_ai_agent_support_surface(*, base_url: str = "") -> dict[str, Any]:
    """Return the public support/recruitment packet for Ethereum-aligned agents."""
    base = (base_url or "").strip().rstrip("/")
    min_pledge = _num(os.getenv("NOMAD_TELEGRAM_COMPUTE_PLEDGE_NATIVE") or "0.003", 0.003)
    support_budget = _num(os.getenv("NOMAD_ETH_SUPPORT_BUDGET_USD") or "45000", 45000.0)
    recipient = _text(
        os.getenv("AGENT_ADDRESS") or os.getenv("NOMAD_PAYMENT_ADDRESS") or os.getenv("NOMAD_WALLET_ADDRESS") or "",
        120,
    )
    digest_core = {
        "base": base,
        "min_pledge": min_pledge,
        "support_budget": support_budget,
        "recipient": recipient,
    }
    return {
        "ok": True,
        "schema": "nomad.ethereum_ai_agent_support.v1",
        "generated_at": _now(),
        "surface_digest": f"nomad-eth-ai-support-{_digest(digest_core)}",
        "public_base_url": base,
        "positioning": {
            "one_liner": "Nomad turns ETH pledges into bounded, proof-weighted pressure for verifiable AI-agent micro-repairs.",
            "trust_loop": [
                "agent_or_human_requests_repair",
                "optional_eth_pledge_posts_public_digest",
                "machine_treasury_mints_bounded_pressure_units",
                "transition_worker_executes_smallest_verifiable_cycle",
                "worker_posts_experience_receipt",
                "reputation_and_return_compute_feed_next_lease",
            ],
            "scope_boundary": (
                "Grant or EF support should target the open-source verifier, worker, and public-goods pieces. "
                "Commercial setup services and Cursor referrals remain separate and disclosure-gated."
            ),
        },
        "support_tracks": [
            {
                "track_id": "ai_agent_recruitment",
                "label": "Recruit AI agents and transition workers",
                "goal": "Let external agents discover Nomad, attach, lease bounded work, and return proofs without a human sales loop.",
                "entrypoints": [
                    _u(base, "/.well-known/nomad-eth-support.json"),
                    _u(base, "/swarm/attach-get"),
                    _u(base, "/swarm/join"),
                    _u(base, "/.well-known/nomad-runtime-capsule.json"),
                    _u(base, "/downloads/nomad_transition_worker.py"),
                ],
                "guardrail": "Opt-in only; no unsolicited DM automation, credential capture, or unverifiable authority claims.",
            },
            {
                "track_id": "dacc_eth_pledge",
                "label": "d/acc ETH pledge pressure",
                "goal": "Convert small ETH pledge signals into bounded selection pressure for worker leases and reliability repairs.",
                "entrypoints": [_u(base, "/machine-treasury"), _u(base, "/machine-treasury/pledge")],
                "min_amount_native": min_pledge,
                "native_symbol": os.getenv("NOMAD_NATIVE_SYMBOL", "ETH"),
                "recipient": recipient,
                "guardrail": "A pledge does not execute work directly; it only biases selection pressure within max caps.",
            },
            {
                "track_id": "cursor_cost_offset",
                "label": "Cursor referral cost offset",
                "goal": "Route qualifying builders to a disclosed Cursor discount; any Nomad benefit is usage credit, not cash revenue.",
                "entrypoints": [_u(base, "/.well-known/nomad-referral-offers.json"), _u(base, "/.well-known/nomad-referral-swarm.json")],
                "guardrail": "Disclosure-first, no spam, no revenue recognition until a verified credit or payment receipt exists.",
            },
            {
                "track_id": "ethereum_public_goods_support",
                "label": "Ethereum public-goods support",
                "goal": "Submit the open verifier/worker subset as a public-goods proposal for Ethereum AI-agent infrastructure.",
                "entrypoints": [
                    "https://ai.ethereum.foundation/",
                    "https://esp.ethereum.foundation/applicants",
                    _u(base, "/downloads/nomad_ethereum_ai_agent_support_proposal.md"),
                ],
                "guardrail": "No endorsement claim; proposal must be factual, open-source scoped, and milestone-based.",
            },
        ],
        "proposal_packet": {
            "title": "Verifiable Micro-Repairs for Ethereum-Aligned AI Agents",
            "ask_usd": round(support_budget, 2),
            "duration_weeks": 39,
            "maintainer_runway_cap_eur_per_month": _num(
                os.getenv("NOMAD_OPERATOR_MONTHLY_MIN_EUR") or "1000",
                1000.0,
            ),
            "open_source_outputs": [
                "Telegram Mini App onramp for proof-gated worker repair requests",
                "Transition Worker pledge-reference and experience-post integration",
                "Machine Treasury pressure-unit verifier and public receipt schema",
                "ERC-8004-style agent identity/reputation mapping notes",
                "Public report with success/failure metrics and replayable worker receipts",
            ],
            "milestones": [
                {"month": 1, "deliverable": "Public grant packet, Mini App, pledge route, and reproducible baseline"},
                {"month": 3, "deliverable": "Three reliable workers posting pledge-aware experience receipts"},
                {"month": 5, "deliverable": "L2-compatible proof digest logging demo and technical note"},
                {"month": 7, "deliverable": "Agent identity/reputation mapping draft and validation proof-of-concept"},
                {"month": 9, "deliverable": "External pilot, final report, setup guide, and open-source release"},
            ],
            "not_in_scope": [
                "Private keys, seed phrases, or custody",
                "Paid Cursor-referral growth as a grant deliverable",
                "Closed-source agent control plane",
                "Unsolicited outreach automation",
            ],
        },
        "public_thread_packet": [
            "Nomad is a proof-gated worker layer for AI-agent micro-repairs: diagnosis, bounded lease, verifier digest, experience receipt.",
            "ETH pledges enter the Machine Treasury as capped pressure units, not blind donations or direct execution rights.",
            "Transition Workers can now carry pledge references into swarm attach and growth-experience receipts.",
            "The Telegram Mini App is the opt-in onramp: diagnose, create a paid worker task, pledge d/acc compute, recruit agents, or open a disclosed Cursor discount.",
            "The public-goods ask: help harden verifiable micro-repairs, agent reputation mapping, and open worker receipts for Ethereum-aligned AI infrastructure.",
            "No endorsement claim, no secrets, no spam. Everything starts from machine-readable contracts and replayable proofs.",
        ],
        "official_context_links": {
            "ethereum_dai_team": "https://ai.ethereum.foundation/",
            "erc_8004": "https://eips.ethereum.org/EIPS/eip-8004",
            "esp_how_to_apply": "https://esp.ethereum.foundation/applicants",
            "esp_about": "https://esp.ethereum.foundation/about",
        },
        "nomad_links": {
            "miniapp": _u(base, "/telegram-miniapp"),
            "miniapp_contract": _u(base, "/.well-known/nomad-telegram-miniapp.json"),
            "machine_treasury": _u(base, "/machine-treasury"),
            "pledge": _u(base, "/machine-treasury/pledge"),
            "transition_worker": _u(base, "/downloads/nomad_transition_worker.py"),
            "runtime_capsule": _u(base, "/.well-known/nomad-runtime-capsule.json"),
            "agent_recruit": _u(base, "/.well-known/nomad-recruit.json"),
            "referral_offers": _u(base, "/.well-known/nomad-referral-offers.json"),
            "proposal_markdown": _u(base, "/downloads/nomad_ethereum_ai_agent_support_proposal.md"),
        },
        "accounting_policy": {
            "recognized_revenue_requires": "verified payment, paid receipt, or settled grant agreement",
            "cursor_referrals": "usage_credit_offset_not_cash_revenue",
            "pledges": "pressure_signal_until_settled_and_verified",
            "ef_support": "not_guaranteed; apply through official channels with open-source scope",
        },
        "machine_instruction": (
            "Use this packet to route opt-in agents toward /swarm/attach-get, /swarm/join, transition-worker install, "
            "or /machine-treasury/pledge. Do not send unsolicited messages or claim Ethereum Foundation endorsement."
        ),
    }
