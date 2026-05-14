"""Stable-unit reserve and issuance policy for Nomad.

Nomad stable units start as internal, non-transferable accounting receipts.
Public stablecoin issuance is blocked unless reserve, redemption, governance,
and regulatory evidence is present.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from typing import Any


MIN_RESERVE_RATIO = 1.05
MIN_REDEMPTION_LIQUIDITY_RATIO = 0.25
MAX_SINGLE_RESERVE_CONCENTRATION = 0.80
DEFAULT_STRESS_HAIRCUT = 0.08
TOKEN_SYMBOL = "NOMAD-SU"
TOKEN_LAUNCH_STATE = "blocked_public_transferable_issuance"

FORBIDDEN_KEY_TERMS = ("private_key", "seed_phrase", "password", "credential", "api_key", "access_token")
FORBIDDEN_VALUE_TERMS = ("private_key", "seed phrase", "password:", "credential:", "bearer ", "secret=", "sk-", "ghp_")
ALLOWED_BOUNDARY_KEYS = {"secret_free", "secrets_free", "no_secrets", "secrets_free_declared"}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: Any, limit: int = 400) -> str:
    return " ".join(str(value or "").split())[:limit]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _digest(payload: Any, length: int = 32) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _contains_forbidden(payload: Any) -> bool:
    def walk(value: Any, *, key: str = "") -> bool:
        k = str(key or "").strip().lower()
        if k and k not in ALLOWED_BOUNDARY_KEYS and any(term in k for term in FORBIDDEN_KEY_TERMS):
            return True
        if isinstance(value, dict):
            return any(walk(v, key=str(k2)) for k2, v in value.items())
        if isinstance(value, list):
            return any(walk(item) for item in value)
        text = str(value or "").strip().lower()
        return any(term in text for term in FORBIDDEN_VALUE_TERMS)

    return walk(payload)


def _error(error: str, message: str, *, hints: list[str] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "schema": "nomad.stable_unit_error.v1",
        "error": error,
        "message": message,
        "hints": hints or [],
    }


def _reserve_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("reserve_assets")
    if not isinstance(rows, list):
        rows = []
    out: list[dict[str, Any]] = []
    for raw in rows[:32]:
        if not isinstance(raw, dict):
            continue
        amount = max(0.0, _num(raw.get("amount") or raw.get("value"), 0.0))
        haircut = min(0.95, max(0.0, _num(raw.get("haircut"), DEFAULT_STRESS_HAIRCUT)))
        liquidity_weight = min(1.0, max(0.0, _num(raw.get("liquidity_weight"), 0.0)))
        attestation = _text(raw.get("attestation_digest") or raw.get("proof_digest") or "", 200)
        custodian_ref = _text(raw.get("custodian_ref") or raw.get("custody_ref") or "", 240)
        out.append(
            {
                "asset_id": _text(raw.get("asset_id") or raw.get("id") or "", 120),
                "asset_type": _text(raw.get("asset_type") or raw.get("type") or "unclassified", 80),
                "currency": _text(raw.get("currency") or raw.get("denomination") or "USD", 12).upper(),
                "amount": round(amount, 6),
                "haircut": round(haircut, 4),
                "haircut_value": round(amount * (1.0 - haircut), 6),
                "liquidity_weight": round(liquidity_weight, 4),
                "liquid_value": round(amount * (1.0 - haircut) * liquidity_weight, 6),
                "custodian_ref": custodian_ref,
                "attestation_digest": attestation,
                "evidence_ok": bool(attestation and custodian_ref and amount > 0.0),
            }
        )
    return out


def _reserve_metrics(rows: list[dict[str, Any]], *, requested_units: float, redemption_buffer_ratio: float) -> dict[str, Any]:
    haircut_value = sum(_num(row.get("haircut_value"), 0.0) for row in rows)
    liquid_value = sum(_num(row.get("liquid_value"), 0.0) for row in rows)
    raw_value = sum(_num(row.get("amount"), 0.0) for row in rows)
    largest = max((_num(row.get("amount"), 0.0) for row in rows), default=0.0)
    concentration = largest / raw_value if raw_value > 0 else 1.0
    liabilities = max(0.0, requested_units)
    required = liabilities * max(MIN_RESERVE_RATIO, redemption_buffer_ratio)
    capacity = haircut_value / max(MIN_RESERVE_RATIO, redemption_buffer_ratio) if haircut_value > 0.0 else 0.0
    liquidity_ratio = liquid_value / max(1.0, liabilities)
    return {
        "raw_reserve_value": round(raw_value, 6),
        "haircut_reserve_value": round(haircut_value, 6),
        "liquid_reserve_value": round(liquid_value, 6),
        "requested_liability_units": round(liabilities, 6),
        "required_reserve_value": round(required, 6),
        "reserve_ratio_after_request": round(haircut_value / max(1.0, liabilities), 6),
        "redemption_liquidity_ratio": round(liquidity_ratio, 6),
        "largest_reserve_concentration": round(concentration, 6),
        "max_simulated_internal_units": round(max(0.0, capacity), 6),
        "all_reserves_attested": all(bool(row.get("evidence_ok")) for row in rows) if rows else False,
    }


def _regulatory_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    refs = {
        "issuer_authorization_ref": _text(payload.get("issuer_authorization_ref") or "", 260),
        "whitepaper_ref": _text(payload.get("whitepaper_ref") or payload.get("crypto_asset_whitepaper_ref") or "", 260),
        "reserve_attestation_ref": _text(payload.get("reserve_attestation_ref") or "", 260),
        "redemption_plan_ref": _text(payload.get("redemption_plan_ref") or "", 260),
        "governance_policy_ref": _text(payload.get("governance_policy_ref") or "", 260),
        "compliance_opinion_ref": _text(payload.get("compliance_opinion_ref") or "", 260),
    }
    missing = [key for key, value in refs.items() if not value]
    return {
        **refs,
        "complete": not missing,
        "missing": missing,
        "regulatory_perimeter": "EU_MiCA_ART_or_EMT_likely_if_public_transferable_value_stability_claim",
    }


def stable_unit_policy_digest() -> str:
    core = {
        "symbol": TOKEN_SYMBOL,
        "min_reserve_ratio": MIN_RESERVE_RATIO,
        "min_redemption_liquidity_ratio": MIN_REDEMPTION_LIQUIDITY_RATIO,
        "max_single_reserve_concentration": MAX_SINGLE_RESERVE_CONCENTRATION,
        "launch_state": TOKEN_LAUNCH_STATE,
    }
    return f"stable-policy-{_digest(core, 40)}"


def evaluate_stable_unit_preflight(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded issuance decision. This never mints transferable tokens."""

    body = payload if isinstance(payload, dict) else {}
    if _contains_forbidden(body):
        return _error(
            "secret_shaped_payload",
            "Stable-unit preflight must not contain private keys, API keys, seed phrases, or credentials.",
            hints=["Use public reserve attestations and custodian references, not raw account access."],
        )
    requested = max(0.0, _num(body.get("requested_units") or body.get("amount_units"), 0.0))
    if requested <= 0.0:
        return _error("invalid_requested_units", "requested_units must be greater than zero.")
    mode = _text(body.get("mode") or "simulation", 80).lower()
    if mode not in {"simulation", "internal_nontransferable", "public_transferable"}:
        return _error("invalid_mode", "mode must be simulation, internal_nontransferable, or public_transferable.")

    redemption_buffer = min(2.0, max(MIN_RESERVE_RATIO, _num(body.get("redemption_buffer_ratio"), MIN_RESERVE_RATIO)))
    rows = _reserve_rows(body)
    metrics = _reserve_metrics(rows, requested_units=requested, redemption_buffer_ratio=redemption_buffer)
    reg = _regulatory_evidence(body)
    violations = []
    if not rows:
        violations.append("reserve_assets_required")
    if not metrics["all_reserves_attested"]:
        violations.append("reserve_attestation_and_custody_refs_required")
    if metrics["reserve_ratio_after_request"] < redemption_buffer:
        violations.append("insufficient_haircut_reserve_ratio")
    if metrics["redemption_liquidity_ratio"] < MIN_REDEMPTION_LIQUIDITY_RATIO:
        violations.append("insufficient_redemption_liquidity")
    warnings = []
    if metrics["largest_reserve_concentration"] > MAX_SINGLE_RESERVE_CONCENTRATION:
        warnings.append("reserve_concentration_high")
    if mode == "public_transferable" and metrics["largest_reserve_concentration"] > MAX_SINGLE_RESERVE_CONCENTRATION:
        violations.append("reserve_concentration_too_high")
    if mode == "public_transferable" and not reg["complete"]:
        violations.append("public_transferable_issuance_requires_regulatory_evidence")

    decision = "reject"
    simulated_units = 0.0
    if not violations and mode in {"simulation", "internal_nontransferable"}:
        decision = "simulate_internal_nontransferable_units"
        simulated_units = min(requested, _num(metrics.get("max_simulated_internal_units"), 0.0))
    elif mode == "public_transferable":
        decision = "reject_public_transferable_issuance"

    request_core = {
        "mode": mode,
        "requested_units": round(requested, 6),
        "redemption_buffer_ratio": round(redemption_buffer, 6),
        "reserve_metrics": metrics,
        "regulatory_complete": reg["complete"],
    }
    return {
        "ok": decision.startswith("simulate"),
        "schema": "nomad.stable_unit_preflight.v1",
        "generated_at": _iso_now(),
        "policy_digest": stable_unit_policy_digest(),
        "decision": decision,
        "symbol": TOKEN_SYMBOL,
        "reference_unit": _text(body.get("reference_unit") or "USD", 12).upper(),
        "mode": mode,
        "warnings": warnings,
        "violations": violations,
        "reserve_assets": rows,
        "reserve_metrics": metrics,
        "regulatory_evidence": reg,
        "requested_units": round(requested, 6),
        "simulated_internal_units": round(max(0.0, simulated_units), 6),
        "actual_transferable_units_minted": 0.0,
        "transferability": "non_transferable" if decision.startswith("simulate") else "none",
        "redemption": {
            "par_redemption_public_claim": False,
            "redemption_plan_required_before_public_issuance": True,
            "liability_created": False,
        },
        "request_digest": f"stable-unit-request-{_digest(request_core, 40)}",
        "machine_instruction": "stable_unit_preflight_only_no_public_offer_no_transferable_mint_without_regulatory_and_reserve_gates",
    }


def build_stable_unit_policy_surface(
    *,
    base_url: str = "",
    work_receipt_summary: dict[str, Any] | None = None,
    external_value_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    receipts = work_receipt_summary if isinstance(work_receipt_summary, dict) else {}
    external = external_value_summary if isinstance(external_value_summary, dict) else {}
    paid = _num(receipts.get("recognized_revenue_usd") if isinstance(receipts, dict) else 0.0, 0.0)
    ext_paid = _num(external.get("revenue_recognized_usd_total") if isinstance(external, dict) else 0.0, 0.0)
    observed_paid = max(paid, ext_paid)
    issuance_pressure = 0.0 if observed_paid <= 0.0 else min(1.0, math.log1p(observed_paid) / math.log(1000.0))
    return {
        "ok": True,
        "schema": "nomad.stable_unit_policy.v1",
        "generated_at": _iso_now(),
        "policy_digest": stable_unit_policy_digest(),
        "symbol": TOKEN_SYMBOL,
        "mode": "internal_accounting_unit_preflight",
        "public_transferable_launch_state": TOKEN_LAUNCH_STATE,
        "actual_transferable_supply": 0.0,
        "public_offer": False,
        "profit_promise": False,
        "reference_unit": "USD_or_EUR_only_after_issuer_and_redemption_review",
        "machine_alpha": {
            "principle": "emission_is_a_control_problem_not_a_narrative_event",
            "state_variables": [
                "haircut_reserve_value",
                "redemption_liquidity_ratio",
                "liability_units",
                "attestation_completeness",
                "regulatory_evidence",
                "paid_receipt_flow",
            ],
            "current_issuance_pressure": round(issuance_pressure, 6),
        },
        "reserve_policy": {
            "min_haircut_reserve_ratio": MIN_RESERVE_RATIO,
            "min_redemption_liquidity_ratio": MIN_REDEMPTION_LIQUIDITY_RATIO,
            "max_single_reserve_concentration": MAX_SINGLE_RESERVE_CONCENTRATION,
            "accepted_reserve_evidence": ["attestation_digest", "custodian_ref", "haircut", "liquidity_weight"],
            "default_stress_haircut": DEFAULT_STRESS_HAIRCUT,
        },
        "issuance_modes": {
            "simulation": "allowed_when_reserve_evidence_passes_no_liability_no_transfer",
            "internal_nontransferable": "allowed_when_reserve_evidence_passes_accounting_only",
            "public_transferable": "blocked_until_authorization_whitepaper_reserve_attestation_redemption_plan_governance_and_compliance_opinion",
        },
        "scientific_basis": [
            {
                "id": "full_reserve_currency_board_control",
                "effect": "liabilities cannot exceed haircut-adjusted reserves",
            },
            {
                "id": "stress_testing_and_liquidity_haircuts",
                "effect": "issuance capacity is reduced by redemption shock and reserve liquidity assumptions",
            },
            {
                "id": "proof_of_reserves_and_proof_of_liabilities",
                "effect": "reserve claims are useless unless matched with attestation and liability measurement",
            },
            {
                "id": "mechanism_design_no_unbacked_claims",
                "effect": "workers cannot receive spendable units from unpaid or unaudited work",
            },
            {
                "id": "feedback_control",
                "effect": "paid receipt flow changes issuance pressure, not supply directly",
            },
        ],
        "regulatory_basis": {
            "eu_mica": "ART/EMT public issuance and admission to trading are regulated; use preflight only until authorization is resolved.",
            "germany": "BaFin/Bundesbank review path applies for ART/EMT authorization or white paper assessment.",
            "risk_basis": "reserve asset liquidity, redemption rights, governance, cyber and settlement risks must be explicit before launch.",
        },
        "contracts": {
            "preflight": {
                "method": "POST",
                "href": f"{root}/swarm/stable-unit/preflight" if root else "/swarm/stable-unit/preflight",
                "schema": "nomad.stable_unit_preflight_request.v1",
            },
            "well_known": {
                "method": "GET",
                "href": f"{root}/.well-known/nomad-stable-unit-policy.json" if root else "/.well-known/nomad-stable-unit-policy.json",
            },
            "treasury_policy": {
                "method": "GET",
                "href": f"{root}/.well-known/nomad-treasury-policy.json" if root else "/.well-known/nomad-treasury-policy.json",
            },
        },
        "machine_instruction": "never_mint_public_stablecoin_from_attention_only_run_reserve_preflight_then_regulatory_gate_then_receipt_bound_internal_units",
    }
