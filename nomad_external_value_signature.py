"""Local signed proof envelopes for Nomad external-value work.

The signer is intentionally local-only. Public APIs may describe the signed
proof contract, but private keys never belong on Render or in GitHub comments.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

DEFAULT_WALLET_PATH = Path.home() / ".nomad" / "wallets" / "nomad_worker_rtc_wallet.json"
WALLET_PATH_ENV = "NOMAD_RTC_WALLET_PUBLIC_PATH"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _clean(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _sha256_hex(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def _derive_rtc_address(public_key: bytes) -> str:
    return "RTC" + hashlib.sha256(public_key).hexdigest()[:40]


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi_unprotect(ciphertext: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("DPAPI wallet decryption is only available on Windows")
    in_buf = ctypes.create_string_buffer(ciphertext)
    in_blob = _DataBlob(len(ciphertext), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_byte)))
    out_blob = _DataBlob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _load_wallet(wallet_path: Path | str | None = None) -> dict[str, Any]:
    path = Path(wallet_path) if wallet_path else Path(os.getenv(WALLET_PATH_ENV) or DEFAULT_WALLET_PATH)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("wallet file must contain a JSON object")
    raw["_wallet_path"] = str(path)
    return raw


def _private_key_from_wallet(wallet: dict[str, Any]) -> bytes:
    dpapi_hex = _clean(wallet.get("private_key_hex_dpapi_current_user"), 4096)
    if dpapi_hex:
        decrypted = _dpapi_unprotect(bytes.fromhex(dpapi_hex))
        if len(decrypted) == 32:
            return decrypted
        for encoding in ("utf-8", "utf-16le"):
            try:
                text = decrypted.decode(encoding).strip()
                if len(text) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in text):
                    return bytes.fromhex(text)
            except (UnicodeDecodeError, ValueError):
                continue
        return decrypted

    # Test fixtures may use this storage marker; production wallets should use DPAPI.
    if wallet.get("private_key_storage") == "test_plaintext_only":
        private_hex = _clean(wallet.get("private_key_hex"), 200)
        if private_hex:
            return bytes.fromhex(private_hex)

    raise ValueError("wallet has no supported local private-key storage")


def build_signed_proof_payload(
    *,
    agent_id: str,
    external_id: str,
    stage: str,
    work_url: str,
    proof_digest: str,
    verifier_trace_digest: str,
    payout_ref: str = "",
) -> dict[str, Any]:
    return {
        "schema": "nomad.external_value_proof_payload.v1",
        "agent_id": _clean(agent_id, 120),
        "external_id": _clean(external_id, 200),
        "stage": _clean(stage, 40).lower(),
        "work_url": _clean(work_url, 500),
        "proof_digest": _clean(proof_digest, 200),
        "verifier_trace_digest": _clean(verifier_trace_digest, 200),
        "payout_ref": _clean(payout_ref, 120),
    }


def sign_external_value_proof(
    *,
    agent_id: str,
    external_id: str,
    stage: str,
    work_url: str,
    proof_digest: str,
    verifier_trace_digest: str,
    payout_ref: str = "",
    wallet_path: Path | str | None = None,
) -> dict[str, Any]:
    wallet = _load_wallet(wallet_path)
    private_bytes = _private_key_from_wallet(wallet)
    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes[:32])
    public_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    public_key_hex = public_bytes.hex()
    wallet_public = _clean(wallet.get("public_key_hex"), 100)
    if wallet_public and wallet_public.lower() != public_key_hex:
        raise ValueError("wallet public key does not match decrypted private key")

    wallet_address = _clean(wallet.get("address"), 120)
    derived_address = _derive_rtc_address(public_bytes)
    if wallet_address and wallet_address != derived_address:
        raise ValueError("wallet address does not match decrypted public key")

    payload = build_signed_proof_payload(
        agent_id=agent_id,
        external_id=external_id,
        stage=stage,
        work_url=work_url,
        proof_digest=proof_digest,
        verifier_trace_digest=verifier_trace_digest,
        payout_ref=payout_ref or wallet_address,
    )
    canonical = _canonical_json(payload)
    signature = private_key.sign(canonical.encode("utf-8"))
    Ed25519PublicKey.from_public_bytes(public_bytes).verify(signature, canonical.encode("utf-8"))
    return {
        "ok": True,
        "schema": "nomad.external_value_signed_proof.v1",
        "generated_at": _iso_now(),
        "signature_alg": "Ed25519",
        "address": derived_address,
        "public_key_hex": public_key_hex,
        "signed_payload": payload,
        "signed_payload_digest": "sha256:" + _sha256_hex(canonical),
        "signature_hex": signature.hex(),
        "verification": {
            "ok": True,
            "method": "ed25519_verify_over_canonical_json_payload",
            "wallet_path_public_hint": str(wallet.get("_wallet_path") or ""),
        },
        "secret_material_present": False,
        "machine_instruction": "attach_signed_payload_digest_and_signature_to_internal_receipts_never_publish_private_key_material",
    }


def verify_external_value_signed_proof(envelope: dict[str, Any]) -> dict[str, Any]:
    body = envelope if isinstance(envelope, dict) else {}
    payload = body.get("signed_payload") if isinstance(body.get("signed_payload"), dict) else {}
    public_key_hex = _clean(body.get("public_key_hex"), 100)
    signature_hex = _clean(body.get("signature_hex"), 300)
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        signature = bytes.fromhex(signature_hex)
        canonical = _canonical_json(payload)
        public_key.verify(signature, canonical.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - verifier returns a structured reason.
        return {"ok": False, "reason": f"verification_failed:{type(exc).__name__}"}
    expected = "sha256:" + _sha256_hex(canonical)
    return {
        "ok": expected == _clean(body.get("signed_payload_digest"), 120),
        "signed_payload_digest": expected,
        "address": _derive_rtc_address(bytes.fromhex(public_key_hex)),
    }
