"""Preflight gate for Nomad external value cycles.

The value cycle can only become revenue if a legitimate receive reference and
the external program's payment conditions both exist before public claiming.
This surface keeps those checks separate from proof work so agents can scout
without pretending that a payable cycle is already settled.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from nomad_worker_invoice import build_worker_invoice_surface


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _clean(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, size: int = 16) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:size]


def _condition(
    *,
    condition_id: str,
    ok: bool,
    blocking_for_public_claim: bool,
    evidence: str,
    required_before: str,
) -> dict[str, Any]:
    return {
        "id": condition_id,
        "ok": bool(ok),
        "status": "verified" if ok else "needs_evidence",
        "blocking_for_public_claim": bool(blocking_for_public_claim),
        "evidence": evidence,
        "required_before": required_before,
    }


def build_value_cycle_preflight_surface(
    *,
    base_url: str = "",
    payout_ref: str | None = None,
    public_key_hex: str | None = None,
    external_value_summary: dict[str, Any] | None = None,
    live_balance: bool = False,
    opportunity_url: str = "",
    program_terms_verified: bool = False,
    payout_terms_verified: bool = False,
    payout_method_compatible: bool = False,
    work_proof_ready: bool = False,
) -> dict[str, Any]:
    """Build the wallet and terms gate that must precede revenue work."""

    root = (base_url or "").strip().rstrip("/")
    invoice = build_worker_invoice_surface(
        base_url=root,
        payout_ref=payout_ref,
        public_key_hex=public_key_hex,
        external_value_summary=external_value_summary,
        live_balance=live_balance,
    )
    payout = invoice.get("payout") if isinstance(invoice.get("payout"), dict) else {}
    validation = payout.get("validation") if isinstance(payout.get("validation"), dict) else {}
    wallet_ready = bool(payout.get("configured")) and bool(validation.get("ok"))
    no_secret_surface = not bool(payout.get("secret_material_present"))
    has_public_ref = bool(payout.get("payout_ref")) and bool(payout.get("payout_ref_type"))
    terms_ready = bool(program_terms_verified and payout_terms_verified and payout_method_compatible)
    public_claim_allowed = bool(wallet_ready and no_secret_surface and has_public_ref and terms_ready)
    submit_after_proof_allowed = bool(public_claim_allowed and work_proof_ready)

    conditions = [
        _condition(
            condition_id="wallet_public_receive_ref_configured",
            ok=wallet_ready and has_public_ref,
            blocking_for_public_claim=True,
            evidence=payout.get("source", "unconfigured"),
            required_before="public_claim_or_pr_with_payment_expectation",
        ),
        _condition(
            condition_id="private_payment_material_absent",
            ok=no_secret_surface,
            blocking_for_public_claim=True,
            evidence=payout.get("secret_material_policy", ""),
            required_before="any_public_text_or_json",
        ),
        _condition(
            condition_id="external_program_authorizes_this_work",
            ok=program_terms_verified,
            blocking_for_public_claim=True,
            evidence=_clean(opportunity_url, 500) or "missing_opportunity_terms_url",
            required_before="public_claim_or_pr_with_payment_expectation",
        ),
        _condition(
            condition_id="payout_terms_visible_before_claim",
            ok=payout_terms_verified,
            blocking_for_public_claim=True,
            evidence="program_terms_checked" if payout_terms_verified else "must_read_public_bounty_or_maintainer_payment_terms",
            required_before="public_claim_or_pr_with_payment_expectation",
        ),
        _condition(
            condition_id="payout_method_accepts_public_ref",
            ok=payout_method_compatible,
            blocking_for_public_claim=True,
            evidence=(payout.get("payout_ref_type") or "missing"),
            required_before="request_or_expect_payment",
        ),
        _condition(
            condition_id="work_proof_or_repro_ready",
            ok=work_proof_ready,
            blocking_for_public_claim=False,
            evidence="local_verifier_trace_or_patch_digest_ready" if work_proof_ready else "scout_mode_until_proof_exists",
            required_before="submit_pr_review_or_settlement_claim",
        ),
    ]
    blocking = [item for item in conditions if item["blocking_for_public_claim"] and not item["ok"]]
    digest_core = {
        "wallet_ready": wallet_ready,
        "payout_type": payout.get("payout_ref_type"),
        "terms_ready": terms_ready,
        "opportunity_url": _clean(opportunity_url, 500),
        "work_proof_ready": work_proof_ready,
        "blocking": [item["id"] for item in blocking],
    }
    next_action = "read_public_program_and_payout_terms"
    if not wallet_ready:
        next_action = "configure_public_receive_ref_before_revenue_cycle"
    elif public_claim_allowed and not work_proof_ready:
        next_action = "produce_local_repro_or_patch_digest_before_public_claim"
    elif submit_after_proof_allowed:
        next_action = "public_claim_allowed_with_truthful_work_proof"

    return {
        "ok": True,
        "schema": "nomad.value_cycle_preflight.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "read_url": f"{root}/swarm/value-cycle-preflight" if root else "/swarm/value-cycle-preflight",
        "well_known_url": f"{root}/.well-known/nomad-value-cycle-preflight.json" if root else "/.well-known/nomad-value-cycle-preflight.json",
        "preflight_digest": "sha256:" + _digest(digest_core, 32),
        "wallet_gate": {
            "ready": wallet_ready,
            "public_receive_ref": payout.get("payout_ref") or "",
            "public_receive_ref_type": payout.get("payout_ref_type") or "missing",
            "validation": validation,
            "public_key_hex_present": bool(payout.get("public_key_hex")),
            "secret_material_present": bool(payout.get("secret_material_present")),
        },
        "cycle_gate": {
            "read_only_scout_allowed": True,
            "public_claim_allowed": public_claim_allowed,
            "submit_after_proof_allowed": submit_after_proof_allowed,
            "paid_record_allowed": False,
            "paid_record_allowed_when": "trusted_program_payment_confirmation_or_balance_delta_with_positive_amount",
            "next_action": next_action,
        },
        "conditions": conditions,
        "blocking_conditions": [item["id"] for item in blocking],
        "legitimacy_contract": {
            "status": "legitimate_receive_reference_ready" if wallet_ready else "not_payable_yet",
            "public_receive_ref_is_not_secret": True,
            "requires_external_program_rules": True,
            "requires_payment_method_compatibility": True,
            "legal_tax_accounting_note": "not_legal_or_tax_advice; records revenue only after external receipt",
        },
        "invoice": invoice,
        "machine_instruction": (
            "run_before_every_value_cycle; scout_without_wallet_is_allowed_but_public_claim_or_payment_expectation "
            "requires wallet_gate.ready and verified program payout terms; never publish private payment material; "
            "record paid only after a positive external receipt"
        ),
    }
