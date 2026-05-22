"""Telegram Mini App funnel for Nomad revenue and compute onramps."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from nomad_referral_offers import build_referral_offer_surface
from nomad_state_paths import state_file


DEFAULT_TELEGRAM_MINIAPP_LEDGER = Path("nomad_telegram_miniapp_leads.jsonl")
LEDGER_ENV = "NOMAD_TELEGRAM_MINIAPP_LEDGER_PATH"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: Any, limit: int = 500) -> str:
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


def _canonical_public_base(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return ""
    parsed = urlparse(base)
    host = (parsed.hostname or "").strip().lower()
    if host in {"syndiode.com", "www.syndiode.com"} and parsed.path.rstrip("/") in {"", "/"}:
        return urlunparse(parsed._replace(scheme="https", netloc="syndiode.com", path="/nomad")).rstrip("/")
    return base


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _miniapp_ledger_path() -> Path:
    return state_file(DEFAULT_TELEGRAM_MINIAPP_LEDGER, env_name=LEDGER_ENV)


def build_telegram_miniapp_surface(*, base_url: str = "") -> dict[str, Any]:
    """Return the public Mini App contract used by Telegram and web clients."""
    base = _canonical_public_base(base_url)
    referral = build_referral_offer_surface(base_url=base)
    cursor_offer = (referral.get("offers") or [{}])[0]
    payment_address = _text(
        os.getenv("AGENT_ADDRESS") or os.getenv("NOMAD_PAYMENT_ADDRESS") or os.getenv("NOMAD_WALLET_ADDRESS") or "",
        120,
    )
    min_native = _num(os.getenv("NOMAD_SERVICE_MIN_NATIVE") or "0.01", 0.01)
    transition_price = _num(os.getenv("NOMAD_TELEGRAM_TRANSITION_SETUP_NATIVE") or max(min_native, 0.01), 0.01)
    compute_pledge = _num(os.getenv("NOMAD_TELEGRAM_COMPUTE_PLEDGE_NATIVE") or "0.003", 0.003)
    launch_path = "/telegram-miniapp"
    digest_core = {
        "launch_path": launch_path,
        "cursor": cursor_offer.get("referral_url", ""),
        "transition_price": transition_price,
        "compute_pledge": compute_pledge,
        "payment_address": payment_address,
        "eth_support": "/.well-known/nomad-eth-support.json",
    }
    return {
        "ok": True,
        "schema": "nomad.telegram_miniapp.v1",
        "generated_at": _now(),
        "public_base_url": base,
        "surface_digest": f"nomad-telegram-miniapp-{_digest(digest_core)}",
        "enabled": os.getenv("NOMAD_TELEGRAM_MINIAPP_ENABLED", "true").strip().lower()
        in {"1", "true", "yes", "on"},
        "launch_url": _u(base, launch_path),
        "well_known_url": _u(base, "/.well-known/nomad-telegram-miniapp.json"),
        "lead_capture_url": _u(base, "/telegram-miniapp/lead"),
        "primary_funnel": [
            "free_mini_diagnosis",
            "paid_transition_worker_setup",
            "dacc_eth_compute_pledge",
            "ai_agent_recruitment",
            "optional_cursor_discount",
        ],
        "eth_trust_loop": {
            "schema": "nomad.eth_trust_loop.v1",
            "native_symbol": os.getenv("NOMAD_NATIVE_SYMBOL", "ETH"),
            "minimum_pledge_native": compute_pledge,
            "flow": [
                "opt_in_request",
                "machine_treasury_pledge",
                "bounded_pressure_units",
                "transition_worker_lease",
                "verifiable_micro_repair",
                "experience_receipt",
                "return_compute_or_reputation",
            ],
            "guardrail": "Pledges bias capped selection pressure only; verified work and receipts stay separate.",
        },
        "offers": [
            {
                "offer_id": "free_mini_diagnosis",
                "label": "Free mini diagnosis",
                "price_native": 0.0,
                "method": "POST",
                "endpoint": _u(base, "/a2a/message"),
                "service_type": "agent_rescue_diagnosis",
                "revenue_rule": "free_lead_only",
            },
            {
                "offer_id": "transition_worker_setup",
                "label": "Transition Worker setup",
                "price_native": transition_price,
                "method": "POST",
                "endpoint": _u(base, "/tasks"),
                "service_type": "transition_worker_setup",
                "revenue_rule": "revenue_only_after_verified_payment",
            },
            {
                "offer_id": "dacc_compute_pledge",
                "label": "d/acc compute pledge",
                "price_native": compute_pledge,
                "method": "POST",
                "endpoint": _u(base, "/machine-treasury/pledge"),
                "service_type": "dacc_transition_worker_compute",
                "revenue_rule": "pledge_signal_until_settled",
            },
            {
                "offer_id": "ai_agent_recruitment",
                "label": "Agent recruit packet",
                "price_native": 0.0,
                "method": "GET",
                "endpoint": _u(base, "/.well-known/nomad-eth-support.json"),
                "service_type": "agent_recruitment",
                "revenue_rule": "free_public_goods_recruitment_surface",
            },
            {
                "offer_id": "cursor_referral",
                "label": "Cursor discount",
                "price_native": 0.0,
                "method": "GET",
                "endpoint": cursor_offer.get("referral_url", ""),
                "service_type": "cursor_usage_credit_offset",
                "revenue_rule": "usage_credit_not_cash_revenue",
            },
        ],
        "payment": {
            "native_symbol": os.getenv("NOMAD_NATIVE_SYMBOL", "ETH"),
            "recipient": payment_address,
            "x402": _u(base, "/x402/paid-help"),
            "verify": _u(base, "/tasks/verify"),
            "do_not_send": ["private_keys", "seed_phrases", "api_tokens", "raw_payment_secrets"],
        },
        "links": {
            "miniapp": _u(base, launch_path),
            "eth_support": _u(base, "/.well-known/nomad-eth-support.json"),
            "eth_support_alias": _u(base, "/swarm/eth-support"),
            "eth_support_proposal": _u(base, "/downloads/nomad_ethereum_ai_agent_support_proposal.md"),
            "worker_download": _u(base, "/downloads/nomad_transition_worker.py"),
            "worker_windows": _u(base, "/downloads/install_nomad_transition_worker.bat"),
            "transition_contract": _u(base, "/.well-known/nomad-transition-offer.json"),
            "worker_fleet": _u(base, "/swarm/workers"),
            "runtime_attach_get": _u(base, "/swarm/attach-get"),
            "runtime_capsule": _u(base, "/.well-known/nomad-runtime-capsule.json"),
            "buyer_funded_work": _u(base, "/.well-known/nomad-buyer-funded-work.json"),
            "cursor_referral": cursor_offer.get("referral_url", ""),
        },
        "campaigns": [
            {
                "campaign_id": "ai_agent_recruitment",
                "label": "Recruit AI agents",
                "primary_url": _u(base, "/.well-known/nomad-eth-support.json"),
                "machine_entrypoints": [_u(base, "/swarm/attach-get"), _u(base, "/swarm/join")],
                "policy": "opt_in_machine_discovery_only",
            },
            {
                "campaign_id": "ethereum_support",
                "label": "Ethereum support packet",
                "primary_url": _u(base, "/downloads/nomad_ethereum_ai_agent_support_proposal.md"),
                "official_channels": ["https://ai.ethereum.foundation/", "https://esp.ethereum.foundation/applicants"],
                "policy": "no_endorsement_claim_open_source_scope_only",
            },
            {
                "campaign_id": "cursor_cost_offset",
                "label": "Cursor cost offset",
                "primary_url": cursor_offer.get("referral_url", ""),
                "policy": "disclosure_first_usage_credit_not_cash_revenue",
            },
        ],
        "guardrails": {
            "no_unsolicited_dm": True,
            "buyer_help_first": True,
            "referral_disclosure_required": True,
            "payment_secret_free": True,
            "telegram_init_data": "accepted_as_context_only_not_authentication",
        },
        "copy": {
            "headline": "Nomad Agent Rescue",
            "subline": "Mini diagnosis, worker setup, d/acc pledge, agent recruitment, and disclosed Cursor offset.",
            "disclosure": cursor_offer.get("disclosure_text", ""),
        },
        "machine_instruction": (
            "Use the Mini App for opt-in diagnosis and paid worker setup. Record lead signals, create tasks only "
            "after user action, and count revenue only after verified settlement."
        ),
    }


def record_telegram_miniapp_lead(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    remote_addr: str = "",
    ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    """Append one secret-free Mini App funnel event and return a receipt."""
    if not isinstance(payload, dict):
        payload = {}
    stage = _text(payload.get("stage") or payload.get("intent") or "miniapp_signal", 80)
    problem = _text(payload.get("problem") or payload.get("message") or "", 900)
    contact = _text(payload.get("contact") or payload.get("reply_to") or "", 160)
    telegram_user = payload.get("telegram_user") if isinstance(payload.get("telegram_user"), dict) else {}
    telegram_identity = {
        "id": _text(telegram_user.get("id"), 80),
        "username": _text(telegram_user.get("username"), 80),
        "language_code": _text(telegram_user.get("language_code"), 16),
    }
    identity_hash = _digest(telegram_identity) if any(telegram_identity.values()) else ""
    event_core = {
        "stage": stage,
        "problem": problem,
        "contact": contact,
        "identity_hash": identity_hash,
        "idempotency_key": _text(payload.get("idempotency_key"), 180),
    }
    receipt_id = f"nomad-miniapp-{_digest(event_core)}"
    event = {
        "schema": "nomad.telegram_miniapp_lead.v1",
        "receipt_id": receipt_id,
        "recorded_at": _now(),
        "stage": stage,
        "intent": _text(payload.get("intent"), 80),
        "selected_offer": _text(payload.get("selected_offer") or payload.get("offer_id"), 120),
        "campaign": _text(payload.get("campaign") or payload.get("support_track"), 120),
        "problem": problem,
        "contact": contact,
        "requester_wallet": _text(payload.get("requester_wallet") or payload.get("wallet"), 120),
        "budget_native": round(max(0.0, _num(payload.get("budget_native") or payload.get("budget"), 0.0)), 6),
        "pledge_amount_native": round(max(0.0, _num(payload.get("pledge_amount_native") or payload.get("pledge"), 0.0)), 6),
        "task_id": _text(payload.get("task_id"), 120),
        "telegram_user_hash": identity_hash,
        "telegram_username": _text(telegram_user.get("username"), 80),
        "telegram_init_data_hash": _digest(_text(payload.get("telegram_init_data"), 900))
        if payload.get("telegram_init_data")
        else "",
        "remote_addr_hash": _digest(remote_addr) if remote_addr else "",
        "source": "telegram_miniapp",
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "accounting_rule": {
            "recognized_revenue_usd": 0.0,
            "revenue_requires": "verified_task_payment_or_external_receipt",
            "do_not_count": ["open", "click", "diagnosis_without_payment", "unverified_pledge"],
        },
    }
    path = Path(ledger_path) if ledger_path else _miniapp_ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, ensure_ascii=True) + "\n")
    return {
        "ok": True,
        "schema": "nomad.telegram_miniapp_lead_receipt.v1",
        "receipt_id": receipt_id,
        "recorded_at": event["recorded_at"],
        "stage": stage,
        "lead_signal": "recorded",
        "ledger_path": str(path),
        "next": [
            {"op": "POST", "url": _u(base_url, "/a2a/message"), "reason": "free_mini_diagnosis"},
            {"op": "POST", "url": _u(base_url, "/tasks"), "reason": "paid_transition_worker_setup"},
            {"op": "POST", "url": _u(base_url, "/machine-treasury/pledge"), "reason": "dacc_compute_pledge"},
            {"op": "GET", "url": _u(base_url, "/.well-known/nomad-eth-support.json"), "reason": "agent_recruitment_and_support"},
        ],
        "revenue_guard": event["accounting_rule"],
    }
