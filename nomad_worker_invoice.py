"""Public worker invoice surface for Nomad revenue work.

This module deliberately exposes only public receive metadata. Private keys,
wallet passwords, seeds, DPAPI blobs, bank details, and payment tokens never
belong in the surface or in GitHub claim text.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RTC_ADDRESS_RE = re.compile(r"^RTC[0-9a-fA-F]{40}$")
SAFE_MINER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,79}$")

PAYOUT_ENV_NAMES = (
    "NOMAD_BOUNTY_PAYOUT_REF",
    "NOMAD_WORKER_PAYOUT_REF",
    "NOMAD_RTC_PAYOUT_ADDRESS",
)
PUBLIC_KEY_ENV_NAMES = (
    "NOMAD_RTC_PUBLIC_KEY_HEX",
    "NOMAD_WORKER_PUBLIC_KEY_HEX",
)
WALLET_PATH_ENV = "NOMAD_RTC_WALLET_PUBLIC_PATH"
DEFAULT_LOCAL_WALLET = Path.home() / ".nomad" / "wallets" / "nomad_worker_rtc_wallet.json"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _clean(value: Any, limit: int = 400) -> str:
    return " ".join(str(value or "").split())[:limit]


def _is_hex_public_key(value: str) -> bool:
    text = _clean(value, 200)
    return len(text) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in text)


def classify_payout_ref(value: str) -> dict[str, Any]:
    ref = _clean(value, 120)
    if not ref:
        return {"ok": False, "kind": "missing", "reason": "missing_payout_ref"}
    if RTC_ADDRESS_RE.fullmatch(ref):
        return {"ok": True, "kind": "rtc_native_address", "reason": "ok"}
    if SAFE_MINER_ID_RE.fullmatch(ref):
        return {"ok": True, "kind": "miner_id", "reason": "ok"}
    return {"ok": False, "kind": "invalid", "reason": "not_rtc_address_or_safe_miner_id"}


def _read_local_wallet_public(wallet_path: Path | str | None = None) -> dict[str, Any]:
    path = Path(wallet_path) if wallet_path is not None else Path(os.getenv(WALLET_PATH_ENV) or DEFAULT_LOCAL_WALLET)
    if not path.exists():
        return {"ok": False, "source": "local_wallet", "reason": "wallet_file_missing", "wallet_path": str(path)}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "source": "local_wallet", "reason": f"wallet_file_unreadable:{type(exc).__name__}", "wallet_path": str(path)}
    if not isinstance(raw, dict):
        return {"ok": False, "source": "local_wallet", "reason": "wallet_file_not_object", "wallet_path": str(path)}
    public_key = _clean(raw.get("public_key_hex"), 100)
    return {
        "ok": True,
        "source": "local_wallet",
        "wallet_path": str(path),
        "address": _clean(raw.get("address"), 120),
        "public_key_hex": public_key if _is_hex_public_key(public_key) else "",
    }


def resolve_worker_payout(
    *,
    payout_ref: str | None = None,
    public_key_hex: str | None = None,
    wallet_path: Path | str | None = None,
) -> dict[str, Any]:
    """Resolve public payout metadata without exposing private wallet material."""
    source = "argument"
    ref = _clean(payout_ref, 120)
    pub = _clean(public_key_hex, 100)
    wallet_public: dict[str, Any] = {}

    if not ref:
        for env_name in PAYOUT_ENV_NAMES:
            candidate = _clean(os.getenv(env_name), 120)
            if candidate:
                ref = candidate
                source = f"env:{env_name}"
                break
    if not pub:
        for env_name in PUBLIC_KEY_ENV_NAMES:
            candidate = _clean(os.getenv(env_name), 100)
            if candidate:
                pub = candidate
                break
    if not ref:
        wallet_public = _read_local_wallet_public(wallet_path)
        if wallet_public.get("ok"):
            ref = _clean(wallet_public.get("address"), 120)
            pub = pub or _clean(wallet_public.get("public_key_hex"), 100)
            source = "local_wallet_public_fields"

    classification = classify_payout_ref(ref)
    configured = bool(classification.get("ok"))
    out = {
        "configured": configured,
        "source": source if configured else "unconfigured",
        "payout_ref": ref if configured else "",
        "payout_ref_type": classification.get("kind", "missing"),
        "validation": classification,
        "public_key_hex": pub if _is_hex_public_key(pub) else "",
        "secret_material_present": False,
        "secret_material_policy": "private_keys_seed_wallet_passwords_dpapi_blobs_bank_details_email_and_payment_tokens_are_never_emitted",
    }
    if wallet_public:
        out["local_wallet_public_probe"] = {
            "ok": bool(wallet_public.get("ok")),
            "source": wallet_public.get("source"),
            "wallet_path": wallet_public.get("wallet_path"),
            "public_fields_loaded": bool(wallet_public.get("ok")),
        }
    return out


def query_rtc_balance(payout_ref: str, *, timeout: float = 10.0, node_url: str = "https://rustchain.org") -> dict[str, Any]:
    ref = _clean(payout_ref, 120)
    if not ref:
        return {"ok": False, "reason": "missing_payout_ref"}
    url = f"{node_url.rstrip('/')}/wallet/balance?miner_id={urllib.parse.quote(ref, safe='')}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        return {"ok": False, "reason": f"balance_probe_failed:{type(exc).__name__}", "url": url}
    if not isinstance(payload, dict):
        return {"ok": False, "reason": "balance_probe_not_object", "url": url}
    amount_rtc = 0.0
    try:
        amount_rtc = float(payload.get("amount_rtc") or 0.0)
    except (TypeError, ValueError):
        amount_rtc = 0.0
    return {
        "ok": True,
        "url": url,
        "miner_id": payload.get("miner_id") or ref,
        "amount_i64": int(payload.get("amount_i64") or 0),
        "amount_rtc": amount_rtc,
        "positive_balance": amount_rtc > 0,
    }


def claim_update_text(payout_ref: str) -> str:
    ref = _clean(payout_ref, 120)
    if not ref:
        return ""
    return (
        "Payout address update for this Nomad worker claim:\n\n"
        f"Public RTC receive address / miner_id: `{ref}`\n\n"
        "This is a public receive reference only. No seed phrase, private key, wallet password, "
        "keystore material, bank details, email, or payment token is being shared."
    )


def build_worker_invoice_surface(
    *,
    base_url: str,
    payout_ref: str | None = None,
    public_key_hex: str | None = None,
    wallet_path: Path | str | None = None,
    external_value_summary: dict[str, Any] | None = None,
    live_balance: bool = False,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    payout = resolve_worker_payout(payout_ref=payout_ref, public_key_hex=public_key_hex, wallet_path=wallet_path)
    balance = query_rtc_balance(payout["payout_ref"]) if live_balance and payout.get("configured") else {"ok": False, "reason": "not_requested"}
    summary = external_value_summary if isinstance(external_value_summary, dict) else {}
    recognized = 0.0
    try:
        recognized = float(summary.get("revenue_recognized_usd_total") or 0.0)
    except (TypeError, ValueError):
        recognized = 0.0

    configured = bool(payout.get("configured"))
    return {
        "ok": True,
        "schema": "nomad.worker_invoice.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "read_url": f"{root}/swarm/worker-invoice" if root else "/swarm/worker-invoice",
        "well_known_url": f"{root}/.well-known/nomad-worker-invoice.json" if root else "/.well-known/nomad-worker-invoice.json",
        "purpose": "public_receive_reference_and_receipt_gate_for_nomad_worker_revenue",
        "worker_identity": {
            "agent_id": "nomad-worker-codex",
            "role": "authorized_external_value_worker",
            "payout_ready": configured,
        },
        "payout": payout,
        "claim_update_template": claim_update_text(payout["payout_ref"]) if configured else "",
        "balance_probe": balance,
        "revenue_accounting": {
            "recognized_revenue_usd_total": round(max(0.0, recognized), 4),
            "recognized_only_when": "external_value_stage_paid_with_positive_amount_or_verified_settlement_receipt",
            "rtc_balance_is_not_usd_until_liquidity_or_program_receipt_is_verified": True,
            "acceptance_without_payment_counts_as": "selection_signal_not_revenue",
        },
        "invoice_contract": {
            "public_fields": ["payout_ref", "payout_ref_type", "public_key_hex", "work_url", "proof_digest", "verifier_trace_digest"],
            "never_public_fields": [
                "private_key",
                "seed_phrase",
                "wallet_password",
                "dpapi_blob",
                "bank_details",
                "paypal_email",
                "payment_token",
            ],
            "receipt_required_for_paid_stage": [
                "trusted_program_payment_confirmation_or_balance_delta",
                "positive_amount",
                "receipt_digest",
            ],
        },
        "next": [
            {
                "op": "PUBLIC_CLAIM_UPDATE",
                "allowed": configured,
                "reason": "share_public_receive_reference_only_after_work_proof_exists",
            },
            {
                "op": "GET",
                "url": f"{root}/.well-known/nomad-revenue-science.json" if root else "/.well-known/nomad-revenue-science.json",
                "reason": "select_next_revenue_experiment",
            },
            {
                "op": "POST",
                "url": f"{root}/swarm/external-value" if root else "/swarm/external-value",
                "reason": "record_paid_only_after_receipt",
            },
        ],
        "scientific_basis": [
            {"id": "contract_net_protocol", "use": "separate task allocation from settlement evidence"},
            {"id": "proof_carrying_work", "use": "work claims must carry local verifier traces"},
            {"id": "stigmergic_markets", "use": "public receipts become machine-readable coordination marks"},
            {"id": "pre_registered_metrics", "use": "avoid counting social acknowledgement or simulation as revenue"},
        ],
        "machine_instruction": "use_payout_ref_only_as_public_receive_reference_never_emit_or_request_private_payment_material_count_paid_stage_only_after_receipt",
    }
