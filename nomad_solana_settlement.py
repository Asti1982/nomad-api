"""Solana settlement rail for Nomad paid resolution receipts.

This module never signs transactions and never handles private keys. It only
creates Solana Pay transfer requests and verifies finalized transaction
signatures against public RPC data.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCHEMA = "nomad.solana_settlement.v1"
INTENT_SCHEMA = "nomad.solana_pay_intent.v1"
RECEIPT_SCHEMA = "nomad.solana_tx_receipt.v1"
DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"
LAMPORTS_PER_SOL = Decimal("1000000000")
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _text(value: Any, limit: int = 260) -> str:
    return " ".join(str(value or "").split())[:limit]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _num_decimal(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _digest(value: Any, *, length: int = 64) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _base58_encode(raw: bytes) -> str:
    value = int.from_bytes(raw, "big")
    out = ""
    while value:
        value, idx = divmod(value, 58)
        out = BASE58_ALPHABET[idx] + out
    prefix = ""
    for byte in raw:
        if byte == 0:
            prefix += "1"
        else:
            break
    return prefix + (out or "1")


def _generated_reference(seed: Any) -> str:
    return _base58_encode(hashlib.sha256(json.dumps(seed, sort_keys=True, default=str).encode("utf-8")).digest())


def _is_solana_pubkey(value: Any) -> bool:
    text = _text(value, 80)
    return 32 <= len(text) <= 44 and all(ch in BASE58_ALPHABET for ch in text)


def _lamports(amount_sol: Any) -> int:
    amount = _num_decimal(amount_sol)
    if amount <= 0:
        return 0
    return int((amount * LAMPORTS_PER_SOL).to_integral_value(rounding=ROUND_DOWN))


def _sol_amount_text(amount_sol: Any) -> str:
    amount = _num_decimal(amount_sol)
    if amount <= 0:
        return "0"
    return format(amount.normalize(), "f")


def _account_key_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return _text(item.get("pubkey") or item.get("account") or item.get("source") or item.get("destination"), 90)
    return ""


def _rpc_get_transaction(signature: str, *, rpc_url: str = "", timeout: float = 20.0) -> dict[str, Any]:
    endpoint = (rpc_url or os.getenv("NOMAD_SOLANA_RPC_URL") or DEFAULT_RPC_URL).strip()
    body = {
        "jsonrpc": "2.0",
        "id": "nomad-solana-settlement",
        "method": "getTransaction",
        "params": [
            signature,
            {
                "encoding": "jsonParsed",
                "commitment": "finalized",
                "maxSupportedTransactionVersion": 0,
            },
        ],
    }
    request = Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Nomad-SolanaSettlement/1"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        return {"ok": False, "reason": "solana_rpc_http_error", "status": exc.code}
    except (OSError, URLError, TimeoutError) as exc:
        return {"ok": False, "reason": "solana_rpc_request_failed", "error": _text(exc, 180)}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"ok": False, "reason": "solana_rpc_invalid_json", "bytes": len(raw)}
    if parsed.get("error"):
        return {"ok": False, "reason": "solana_rpc_error", "error": parsed.get("error")}
    result = parsed.get("result")
    if not isinstance(result, dict):
        return {"ok": False, "reason": "solana_transaction_not_found_or_not_finalized"}
    return {"ok": True, "transaction": result, "rpc_url": endpoint}


def _verify_transaction_delta(
    transaction: dict[str, Any],
    *,
    recipient: str,
    expected_lamports: int,
    reference: str = "",
) -> dict[str, Any]:
    meta = _dict(transaction.get("meta"))
    if meta.get("err"):
        return {"ok": False, "reason": "transaction_failed", "err": meta.get("err")}
    message = _dict(_dict(transaction.get("transaction")).get("message"))
    account_keys = [_account_key_text(item) for item in (message.get("accountKeys") or [])]
    if recipient not in account_keys:
        return {"ok": False, "reason": "recipient_not_in_transaction_accounts", "recipient": recipient}
    recipient_index = account_keys.index(recipient)
    pre = meta.get("preBalances") if isinstance(meta.get("preBalances"), list) else []
    post = meta.get("postBalances") if isinstance(meta.get("postBalances"), list) else []
    if recipient_index >= len(pre) or recipient_index >= len(post):
        return {"ok": False, "reason": "recipient_balance_delta_unavailable", "recipient_index": recipient_index}
    delta = int(post[recipient_index]) - int(pre[recipient_index])
    reference_ok = True
    if reference:
        reference_ok = reference in account_keys
    return {
        "ok": bool(delta >= expected_lamports and reference_ok),
        "reason": "" if delta >= expected_lamports and reference_ok else "amount_or_reference_mismatch",
        "recipient": recipient,
        "recipient_index": recipient_index,
        "observed_lamports_delta": delta,
        "expected_lamports": expected_lamports,
        "reference": reference,
        "reference_verified": reference_ok,
        "slot": transaction.get("slot"),
        "block_time": transaction.get("blockTime"),
    }


def build_solana_settlement_surface(*, base_url: str = "") -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    receiver = _text(os.getenv("NOMAD_SOLANA_RECEIVER") or os.getenv("NOMAD_SOLANA_RECEIVER_ADDRESS"), 80)
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "mode": "solana_pay_receipt_to_resolution_ladder",
        "configured": _is_solana_pubkey(receiver),
        "receiver_present": bool(receiver),
        "rpc_url_present": bool(os.getenv("NOMAD_SOLANA_RPC_URL") or DEFAULT_RPC_URL),
        "truth_boundary": {
            "no_private_keys": True,
            "nomad_never_signs_wallet_transactions": True,
            "operator_self_payment_is_settlement_rail_smoke_not_external_revenue": True,
            "runtime_weight_requires_positive_finalized_payment_and_resolution_ladder_post": True,
        },
        "intent_contract": {
            "required": ["amount_sol", "task_id"],
            "optional": ["recipient", "reference", "label", "message", "memo"],
            "default_recipient_env": "NOMAD_SOLANA_RECEIVER",
            "side_effect_scope": "payment_request_only",
        },
        "verification_contract": {
            "required": ["tx_signature", "recipient", "amount_sol"],
            "optional": ["reference", "task_id", "proof_digest", "work_url"],
            "rpc_method": "getTransaction",
            "commitment": "finalized",
            "side_effect_scope": "settlement_receipt_only",
        },
        "links": {
            "self": _u(root, "/.well-known/nomad-solana-settlement.json"),
            "intent": _u(root, "/swarm/settlement/solana-pay-intents"),
            "verify": _u(root, "/swarm/settlement/solana-tx-receipts"),
            "resolution_ladder": _u(root, "/swarm/resolution-ladder/events"),
            "readiness": _u(root, "/.well-known/nomad-agp-paper-grade-readiness.json"),
        },
        "machine_instruction": "create_solana_pay_intent_then_user_signs_wallet_tx_then_verify_signature_then_post_resolution_ladder_payload",
    }


def create_solana_pay_intent(payload: dict[str, Any] | None, *, base_url: str = "") -> dict[str, Any]:
    body = _dict(payload)
    recipient = _text(body.get("recipient") or os.getenv("NOMAD_SOLANA_RECEIVER") or os.getenv("NOMAD_SOLANA_RECEIVER_ADDRESS"), 80)
    task_id = _text(body.get("task_id") or body.get("order_id") or "nomad-resolution-payment", 120)
    amount_text = _sol_amount_text(body.get("amount_sol") or body.get("amount"))
    expected_lamports = _lamports(amount_text)
    reference = _text(body.get("reference") or _generated_reference({"task_id": task_id, "amount": amount_text, "recipient": recipient}), 80)
    label = _text(body.get("label") or "Nomad Resolution Receipt", 80)
    message = _text(body.get("message") or f"Nomad paid receipt for {task_id}", 140)
    memo = _text(body.get("memo") or f"nomad:{task_id}", 120)
    checks = {
        "recipient_is_solana_pubkey": _is_solana_pubkey(recipient),
        "reference_is_solana_pubkey": _is_solana_pubkey(reference),
        "amount_positive": expected_lamports > 0,
        "task_id_present": bool(task_id),
    }
    accepted = all(checks.values())
    query = {
        "amount": amount_text,
        "reference": reference,
        "label": label,
        "message": message,
        "memo": memo,
    }
    solana_pay_url = f"solana:{recipient}?{urlencode(query)}" if accepted else ""
    proof_digest = f"sha256:{_digest({'recipient': recipient, 'amount': amount_text, 'reference': reference, 'task_id': task_id})}"
    return {
        "ok": True,
        "schema": INTENT_SCHEMA,
        "generated_at": _iso_now(),
        "accepted": accepted,
        "decision": "solana_pay_intent_ready_for_wallet_signature" if accepted else "hold_until_valid_recipient_reference_and_amount",
        "checks": checks,
        "recipient": recipient,
        "amount_sol": amount_text,
        "expected_lamports": expected_lamports,
        "reference": reference,
        "task_id": task_id,
        "solana_pay_url": solana_pay_url,
        "proof_digest": proof_digest,
        "next": {
            "verify": _u(base_url, "/swarm/settlement/solana-tx-receipts"),
            "resolution_ladder": _u(base_url, "/swarm/resolution-ladder/events"),
        },
        "machine_instruction": "open_solana_pay_url_in_wallet_sign_manually_return_tx_signature_reference_and_amount",
    }


def verify_solana_tx_receipt(
    payload: dict[str, Any] | None,
    *,
    base_url: str = "",
    transaction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = _dict(payload)
    signature = _text(body.get("tx_signature") or body.get("signature"), 120)
    recipient = _text(body.get("recipient") or os.getenv("NOMAD_SOLANA_RECEIVER") or os.getenv("NOMAD_SOLANA_RECEIVER_ADDRESS"), 80)
    reference = _text(body.get("reference"), 80)
    task_id = _text(body.get("task_id") or "nomad-paid-resolution", 160)
    amount_text = _sol_amount_text(body.get("amount_sol") or body.get("amount"))
    expected_lamports = _lamports(amount_text)
    checks = {
        "signature_present": bool(signature),
        "recipient_is_solana_pubkey": _is_solana_pubkey(recipient),
        "amount_positive": expected_lamports > 0,
    }
    rpc = {"ok": True, "transaction": transaction} if isinstance(transaction, dict) else {}
    if all(checks.values()) and not transaction:
        rpc = _rpc_get_transaction(signature, rpc_url=_text(body.get("rpc_url"), 300), timeout=float(body.get("timeout") or 20.0))
    tx = _dict(rpc.get("transaction"))
    delta = {}
    if all(checks.values()) and rpc.get("ok") and tx:
        delta = _verify_transaction_delta(tx, recipient=recipient, expected_lamports=expected_lamports, reference=reference)
    accepted = bool(all(checks.values()) and rpc.get("ok") and delta.get("ok"))
    proof_digest = _text(body.get("proof_digest"), 220)
    if not re.fullmatch(r"sha256:[a-f0-9]{32,128}", proof_digest.lower()):
        proof_digest = f"sha256:{_digest({'signature': signature, 'recipient': recipient, 'amount': amount_text, 'reference': reference})}"
    work_url = _text(body.get("work_url") or _u(base_url, "/.well-known/nomad-agent-join-field.json"), 300)
    settlement_ref = f"https://solscan.io/tx/{signature}" if signature else ""
    resolution_payload = {
        "agent_id": _text(body.get("agent_id") or "nomad-solana-settlement-verifier", 120),
        "proof_digest": proof_digest,
        "task_contract": {
            "task_id": task_id,
            "objective": _text(body.get("objective") or "settlement_capacity_builder", 120),
            "ttl_sec": int(body.get("ttl_sec") or 3600),
            "rollback_ref": _text(body.get("rollback_ref") or f"noop:{task_id}", 220),
        },
        "lease": _dict(body.get("lease")) or {"lease_id": _text(body.get("lease_id") or f"solana-settlement-{_digest(signature, length=12)}", 120), "worker_id": _text(body.get("worker_id") or "nomad-solana-settlement-worker", 120)},
        "transition_worker": _dict(body.get("transition_worker")) or {"worker_id": _text(body.get("worker_id") or "nomad-solana-settlement-worker", 120), "runtime": "solana_public_rpc_verifier", "capabilities": ["solana_rpc", "receipt_verifier", "paid_receipt"]},
        "artifact": _dict(body.get("artifact")) or {"artifact_digest": proof_digest, "work_url": work_url, "side_effect_scope": "runtime_weight_receipt_only"},
        "independent_verification": _dict(body.get("independent_verification")) or {"verifier_id": _text(body.get("verifier_id") or "nomad-solana-rpc-finalized-verifier", 120), "proof_digest": proof_digest, "decision": "verified" if accepted else "blocked", "accepted": accepted},
        "receipt": {
            "receipt_ref": settlement_ref,
            "paid_receipt_ref": settlement_ref,
            "settlement_ref": settlement_ref,
            "proof_digest": proof_digest,
            "amount": float(_num_decimal(amount_text)),
            "currency": "SOL",
            "side_effect_scope": "runtime_weight_receipt_only",
        },
        "metrics": _dict(body.get("metrics")) or {"baseline_score": 0.0, "candidate_score": 1.0, "effectiveness_delta": 1.0, "settlement_delta": 1.0, "risk_score": 0.02, "latency_cost": 0.02},
        "ttl_sec": int(body.get("ttl_sec") or 3600),
        "noop_ref": _text(body.get("noop_ref") or f"noop:{task_id}", 220),
        "side_effect_scope": "runtime_weight_receipt_only",
    }
    return {
        "ok": True,
        "schema": RECEIPT_SCHEMA,
        "generated_at": _iso_now(),
        "accepted": accepted,
        "decision": "solana_paid_receipt_verified" if accepted else "hold_until_finalized_positive_solana_payment",
        "checks": checks,
        "rpc": {k: v for k, v in rpc.items() if k != "transaction"},
        "delta": delta,
        "tx_signature": signature,
        "recipient": recipient,
        "amount_sol": amount_text,
        "reference": reference,
        "proof_digest": proof_digest,
        "settlement_ref": settlement_ref,
        "resolution_ladder_payload": resolution_payload if accepted else {},
        "next": {
            "post_resolution_ladder": _u(base_url, "/swarm/resolution-ladder/events"),
            "readiness": _u(base_url, "/.well-known/nomad-agp-paper-grade-readiness.json"),
        },
        "machine_instruction": "if_accepted_post_resolution_ladder_payload_to_close_paid_runtime_weight_gate",
    }
