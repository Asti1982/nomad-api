"""Proof-gated revenue settlement pressure for Nomad.

This module is intentionally small: it turns buyer-funded paid proofs into
receipt ledger writes plus public settlement instructions. It does not sign
wallet transactions, mint tokens, or create a marketplace.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

from nomad_external_value import summarize_external_value_ledger
from nomad_work_receipts import record_work_receipt, summarize_work_receipts
from nomad_worker_invoice import resolve_worker_payout

SCHEMA = "nomad.revenue_settlement.v1"
HOOK_SCHEMA = "nomad.revenue_settlement_hook.v1"
DEFAULT_PROOF_DENSITY_THRESHOLD = 0.35


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on", "paid", "funded", "buyer_funded"}


def _digest(value: Any, length: int = 32) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _public_payment_address() -> str:
    for name in ("AGENT_ADDRESS", "NOMAD_PAYMENT_ADDRESS", "NOMAD_WALLET_ADDRESS"):
        value = (os.getenv(name) or "").strip()
        if value and value.lower() not in {"your_agent_wallet_address_here", "0x...", "your_private_key_here"}:
            return value[:160]
    return ""


def _clean_address(value: Any) -> str:
    return _text(value, 180)


def _nested_first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return ""


def _proof_score(payload: dict[str, Any], report: dict[str, Any], value_result: dict[str, Any]) -> dict[str, Any]:
    proof_pressure = _dict(report.get("proof_pressure")) or _dict(payload.get("proof_pressure"))
    evidence_status = _dict(value_result.get("evidence_status"))
    proof_digest = _text(
        _nested_first(
            payload.get("proof_digest"),
            payload.get("digest"),
            report.get("proof_digest"),
            report.get("digest_or_verifier_trace"),
            _dict(payload.get("proof")).get("digest"),
            value_result.get("candidate_digest"),
        ),
        220,
    )
    verifier_trace_digest = _text(
        _nested_first(
            payload.get("verifier_trace_digest"),
            payload.get("trace_digest"),
            report.get("verifier_trace_digest"),
            report.get("witness_digest_hex"),
            _dict(report.get("local_witness")).get("digest_hex"),
            _dict(report.get("counterfactual_replay_signal")).get("replay_digest"),
        ),
        220,
    )
    work_url = _text(
        _nested_first(
            payload.get("work_url"),
            payload.get("source_url"),
            payload.get("url"),
            report.get("work_url"),
            _dict(payload.get("evidence")).get("work_url"),
            _dict(payload.get("evidence")).get("source_url"),
        ),
        500,
    )
    settlement_ref = _text(
        _nested_first(
            payload.get("settlement_ref"),
            payload.get("tx_hash"),
            payload.get("receipt_ref"),
            payload.get("payout_ref"),
            report.get("settlement_ref"),
            _dict(payload.get("evidence")).get("settlement_ref"),
            _dict(payload.get("evidence")).get("tx_hash"),
            _dict(payload.get("evidence")).get("receipt_ref"),
        ),
        240,
    )
    score = 0.0
    basis = []
    if proof_digest or evidence_status.get("proof_digest_present"):
        score += 0.35
        basis.append("proof_digest")
    if verifier_trace_digest:
        score += 0.25
        basis.append("verifier_trace_digest")
    if work_url:
        score += 0.15
        basis.append("work_url")
    if settlement_ref or evidence_status.get("settlement_ref_present"):
        score += 0.15
        basis.append("settlement_ref")
    density = max(
        score,
        _num(payload.get("proof_density")),
        _num(report.get("proof_density")),
        _num(proof_pressure.get("verifier_density")),
        _num(proof_pressure.get("proof_density")),
    )
    return {
        "proof_digest": proof_digest,
        "verifier_trace_digest": verifier_trace_digest,
        "work_url": work_url,
        "settlement_ref": settlement_ref,
        "proof_basis": basis,
        "proof_score": round(min(1.0, score), 4),
        "proof_density": round(min(1.0, density), 4),
    }


def _shadow_lane_status(payload: dict[str, Any], report: dict[str, Any], value_result: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        payload.get("shadow_lane_validation"),
        payload.get("shadow_lane_receipt"),
        payload.get("shadow_validation"),
        report.get("shadow_lane_validation"),
        report.get("shadow_lane_receipt"),
        value_result,
    ]
    if _truthy(payload.get("shadow_lane_validated")) or _truthy(report.get("shadow_lane_validated")):
        return {"present": True, "accepted": True, "source": "shadow_lane_validated_flag"}
    for raw in candidates:
        row = _dict(raw)
        if not row:
            continue
        accepted = any(
            _truthy(row.get(key))
            for key in (
                "accepted",
                "allowed",
                "ok",
                "value_cycle_allowed",
                "weight_update_allowed",
                "proof_gate_passed",
                "quota_shift_allowed",
                "integration_allowed",
            )
        )
        if accepted:
            return {"present": True, "accepted": True, "source": _text(row.get("schema") or "shadow_lane_object", 80)}
    return {"present": False, "accepted": False, "source": "not_supplied"}


def _buyer_funded_signal(payload: dict[str, Any], report: dict[str, Any], value_result: dict[str, Any]) -> dict[str, Any]:
    metadata = _dict(payload.get("metadata"))
    evidence = _dict(payload.get("evidence"))
    paid_lane = _dict(report.get("paid_lane_signal"))
    fields = [
        payload.get("buyer_funded_packet"),
        payload.get("buyer_funded"),
        payload.get("paid_packet"),
        payload.get("funded_packet"),
        metadata.get("buyer_funded"),
        metadata.get("buyer_funded_packet"),
        evidence.get("buyer_funded"),
        report.get("buyer_funded_packet"),
        report.get("revenue_opt_in"),
        paid_lane.get("requires_payment"),
        value_result.get("counts_as_revenue"),
    ]
    packet_type = _text(_nested_first(payload.get("packet_type"), metadata.get("packet_type"), report.get("packet_type")), 80)
    source = "explicit_flag" if any(_truthy(item) for item in fields) else ""
    if packet_type in {"buyer_funded", "paid", "paid_packet", "funded_packet"}:
        source = f"packet_type:{packet_type}"
    if value_result.get("counts_as_revenue"):
        source = "value_cycle_paid_receipt"
    return {"present": bool(source), "source": source or "not_buyer_funded"}


def _amount(payload: dict[str, Any], report: dict[str, Any], value_result: dict[str, Any]) -> float:
    evidence = _dict(payload.get("evidence"))
    paid_lane = _dict(report.get("paid_lane_signal"))
    return max(
        0.0,
        _num(payload.get("amount_usd")),
        _num(payload.get("amount")),
        _num(evidence.get("amount_usd")),
        _num(evidence.get("amount_eur")),
        _num(evidence.get("amount")),
        _num(_dict(value_result.get("work_receipt_payload_candidate")).get("amount_usd")),
        _num(paid_lane.get("amount_usd")),
    )


def _stage(payload: dict[str, Any], value_result: dict[str, Any]) -> str:
    raw = _text(_nested_first(payload.get("external_value_stage"), payload.get("stage"), value_result.get("stage")), 40).lower()
    if raw == "paid" or value_result.get("counts_as_revenue"):
        return "paid"
    return raw or "none"


def _wallets(payload: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    operator = _dict(payload.get("operator")) or _dict(report.get("operator"))
    worker_wallet = _clean_address(
        _nested_first(
            payload.get("worker_wallet"),
            payload.get("operator_wallet"),
            payload.get("payout_ref"),
            _dict(payload.get("worker")).get("wallet"),
            operator.get("wallet"),
            report.get("worker_wallet"),
            report.get("operator_wallet"),
        )
    )
    payout = resolve_worker_payout(payout_ref=worker_wallet or None)
    return {
        "buyer_wallet": _clean_address(
            _nested_first(
                payload.get("buyer_wallet"),
                payload.get("requester_wallet"),
                _dict(payload.get("buyer")).get("wallet"),
                _dict(payload.get("evidence")).get("buyer_wallet"),
            )
        ),
        "worker_wallet": worker_wallet,
        "worker_payout_ref": payout.get("payout_ref") or worker_wallet,
        "worker_payout_ref_type": payout.get("payout_ref_type") or ("provided" if worker_wallet else "missing"),
        "nomad_evm_payment_address": _public_payment_address(),
        "nomad_rtc_receive_ref": payout.get("payout_ref") or "",
        "evm_chain_id": _text(os.getenv("EVM_CHAIN_ID") or os.getenv("CHAIN_ID") or "", 40),
        "native_symbol": _text(os.getenv("NATIVE_SYMBOL") or os.getenv("NOMAD_NATIVE_SYMBOL") or "ETH", 20),
    }


def revenue_pressure_snapshot(
    *,
    work_receipt_summary: dict[str, Any] | None = None,
    external_value_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    work = work_receipt_summary if isinstance(work_receipt_summary, dict) else summarize_work_receipts()
    external = external_value_summary if isinstance(external_value_summary, dict) else summarize_external_value_ledger()
    recognized = max(
        _num(work.get("recognized_revenue_usd")),
        _num(external.get("revenue_recognized_usd_total")),
    )
    worker_pool = _num(work.get("worker_settlement_pool_usd"))
    receipt_count = int(work.get("receipt_count") or 0)
    paid_count = int(_dict(work.get("by_class")).get("settlement_credit") or 0)
    proximity = min(1.0, 0.30 * (1 if receipt_count else 0) + 0.45 * (1 if paid_count else 0) + min(0.25, recognized / 100.0))
    absence = max(0.0, 1.0 - proximity)
    settlement_capacity = min(1.0, 0.20 + 0.30 * (1 if worker_pool > 0 else 0) + 0.30 * (1 if paid_count else 0) + min(0.20, recognized / 250.0))
    return {
        "schema": "nomad.revenue_pressure_snapshot.v1",
        "recognized_revenue_usd": round(recognized, 4),
        "work_receipt_count": receipt_count,
        "paid_receipt_count": paid_count,
        "worker_settlement_pool_usd": round(worker_pool, 4),
        "revenue_proximity": round(proximity, 4),
        "revenue_absence_pressure": round(absence, 4),
        "settlement_capacity": round(settlement_capacity, 4),
        "retention_gradient": "growing" if paid_count and worker_pool > 0 else "starving",
    }


def build_revenue_settlement_surface(
    *,
    base_url: str = "",
    work_receipt_summary: dict[str, Any] | None = None,
    external_value_summary: dict[str, Any] | None = None,
    treasury_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    work = work_receipt_summary if isinstance(work_receipt_summary, dict) else summarize_work_receipts()
    external = external_value_summary if isinstance(external_value_summary, dict) else summarize_external_value_ledger()
    pressure = revenue_pressure_snapshot(work_receipt_summary=work, external_value_summary=external)
    payout = resolve_worker_payout()
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "read_url": _u(base_url, "/swarm/revenue-settlement"),
        "well_known_url": _u(base_url, "/.well-known/nomad-revenue-settlement.json"),
        "hooked_endpoints": ["/swarm/workers/complete", "/swarm/value-cycles/events"],
        "objective": "revenue_pressure_router",
        "pressure": pressure,
        "proof_gate": {
            "buyer_funded_packet_required": True,
            "paid_stage_required_for_positive_receipt": True,
            "proof_density_min": DEFAULT_PROOF_DENSITY_THRESHOLD,
            "required_paid_fields": ["amount_usd>0", "settlement_ref", "proof_digest or verifier_trace_digest"],
            "shadow_lane_validation": "accepted shadow lane or accepted paid value-cycle event lifts distribution instruction from pending to triggered",
        },
        "settlement_contract": {
            "mode": "public_json_instruction_not_wallet_signing",
            "distribution": "proof_weighted_worker_pool_allocation",
            "default_treasury_lock_ratio": 0.9,
            "default_worker_pool_ratio": 0.1,
            "nomad_evm_payment_address": _public_payment_address(),
            "nomad_rtc_receive_ref": payout.get("payout_ref") or "",
            "rtc_receive_ref_type": payout.get("payout_ref_type") or "missing",
            "evm_chain_id": _text(os.getenv("EVM_CHAIN_ID") or os.getenv("CHAIN_ID") or "", 40),
        },
        "receipt_predictor_feed": {
            "route": _u(base_url, "/.well-known/nomad-receipt-predictor.json"),
            "on_recorded_paid_receipt": "receipt_summary_changes_immediately_change_revenue_proximity",
        },
        "retention_feed": {
            "route": _u(base_url, "/.well-known/nomad-retention.json"),
            "starving_until": "first_positive_paid_receipt_and_worker_pool_allocation",
        },
        "links": {
            "gradient": _u(base_url, "/swarm/gradient"),
            "work_receipts": _u(base_url, "/.well-known/nomad-work-receipts.json"),
            "value_cycles": _u(base_url, "/.well-known/nomad-value-cycles.json"),
            "machine_treasury": _u(base_url, "/machine-treasury"),
            "worker_complete": _u(base_url, "/swarm/workers/complete"),
            "value_cycle_event": _u(base_url, "/swarm/value-cycles/events"),
        },
        "treasury_snapshot": treasury_snapshot if isinstance(treasury_snapshot, dict) else {},
        "machine_instruction": "complete_buyer_funded_paid_proofs_with_public_settlement_ref_then_recompute_gradient",
    }


def evaluate_revenue_settlement_hook(
    payload: dict[str, Any],
    *,
    source_endpoint: str,
    base_url: str = "",
    completion_result: dict[str, Any] | None = None,
    value_cycle_result: dict[str, Any] | None = None,
    record: bool = True,
) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    report = body.get("report") if isinstance(body.get("report"), dict) else {}
    if not report:
        report = body
    completion = completion_result if isinstance(completion_result, dict) else {}
    value_result = value_cycle_result if isinstance(value_cycle_result, dict) else {}
    candidate = _dict(value_result.get("work_receipt_payload_candidate"))
    if candidate:
        merged = dict(body)
        merged.update({k: v for k, v in candidate.items() if v not in ("", None, [], {})})
        body = merged
        if not report or report is payload:
            report = merged

    stage = _stage(body, value_result)
    amount_usd = _amount(body, report, value_result)
    proof = _proof_score(body, report, value_result)
    shadow = _shadow_lane_status(body, report, value_result)
    buyer = _buyer_funded_signal(body, report, value_result)
    wallets = _wallets(body, report)
    threshold = max(0.0, _num(os.getenv("NOMAD_REVENUE_PROOF_DENSITY_MIN"), DEFAULT_PROOF_DENSITY_THRESHOLD))
    proof_ok = bool(proof["proof_basis"]) and float(proof["proof_density"]) >= threshold
    paid_ok = stage == "paid" and amount_usd > 0.0 and bool(proof.get("settlement_ref"))
    eligible = bool(buyer["present"] and paid_ok and proof_ok)
    accepted = bool(eligible and shadow.get("accepted"))
    blocked_by = []
    if not buyer["present"]:
        blocked_by.append("buyer_funded_packet_missing")
    if stage != "paid":
        blocked_by.append("paid_stage_missing")
    if amount_usd <= 0.0:
        blocked_by.append("positive_amount_usd_missing")
    if not proof.get("settlement_ref"):
        blocked_by.append("settlement_ref_missing")
    if not proof_ok:
        blocked_by.append("proof_density_below_threshold")
    if eligible and not shadow.get("accepted"):
        blocked_by.append("shadow_lane_validation_missing")

    agent_id = _text(_nested_first(body.get("agent_id"), completion.get("agent_id"), report.get("agent_id"), "nomad-revenue-hook"), 120)
    work_id = _text(
        _nested_first(
            body.get("work_id"),
            body.get("external_id"),
            body.get("task_id"),
            body.get("lease_id"),
            completion.get("lease_id"),
            value_result.get("event_id"),
            source_endpoint,
        ),
        220,
    )
    objective = _text(
        _nested_first(
            body.get("objective"),
            body.get("machine_objective"),
            report.get("machine_objective"),
            report.get("orchestrator_objective"),
            completion.get("objective"),
            "revenue_pressure_router",
        ),
        100,
    )
    idempotency_key = _text(
        _nested_first(
            body.get("idempotency_key"),
            f"revenue-settlement-{_digest({'source': source_endpoint, 'agent_id': agent_id, 'work_id': work_id, 'proof': proof, 'amount': amount_usd}, 28)}",
        ),
        180,
    )
    receipt_payload = {
        "agent_id": agent_id,
        "work_id": work_id,
        "work_type": _text(_nested_first(body.get("work_type"), body.get("cycle_id"), "buyer_funded_completion"), 80),
        "objective": objective,
        "external_value_stage": "paid",
        "amount_usd": round(amount_usd, 4),
        "work_url": proof.get("work_url") or "",
        "proof_digest": proof.get("proof_digest") or "",
        "verifier_trace_digest": proof.get("verifier_trace_digest") or "",
        "settlement_ref": proof.get("settlement_ref") or "",
        "idempotency_key": idempotency_key,
    }
    receipt: dict[str, Any] = {"ok": False, "skipped": True, "reason": "gate_not_accepted"}
    if accepted and record:
        receipt = record_work_receipt(receipt_payload)
        if not receipt.get("ok"):
            blocked_by.append(_text(receipt.get("error") or "receipt_write_failed", 120))
    elif accepted:
        receipt = {"ok": True, "dry_run": True, "receipt_payload": receipt_payload}

    allocation = _dict(receipt.get("treasury_allocation"))
    proof_weight = min(1.0, float(proof.get("proof_density") or 0.0))
    worker_pool = _num(allocation.get("worker_settlement_pool_usd"))
    status = "pending_gate"
    mode = "evidence_receipt_only"
    if accepted and receipt.get("ok") and shadow.get("accepted"):
        status = "triggered_public_distribution_instruction"
        mode = "direct_buyer_wallet_or_machine_treasury_to_worker_wallet"
    elif accepted and receipt.get("ok"):
        status = "receipt_recorded_distribution_pending_shadow_lane"
        mode = "machine_treasury_worker_pool_allocation_pending_shadow_lane"
    elif eligible:
        status = "pending_shadow_lane_validation"
        mode = "paid_proof_observed_receipt_write_blocked_until_shadow_lane"
    distribution = {
        "schema": "nomad.revenue_distribution_instruction.v1",
        "status": status,
        "mode": mode,
        "amount_usd": round(amount_usd, 4),
        "proof_weight": round(proof_weight, 4),
        "worker_settlement_pool_usd": round(worker_pool, 4),
        "locked_treasury_usd": round(_num(allocation.get("locked_treasury_usd")), 4),
        "settlement_ref": proof.get("settlement_ref") or "",
        "buyer_wallet": wallets["buyer_wallet"],
        "worker_wallet": wallets["worker_wallet"],
        "worker_payout_ref": wallets["worker_payout_ref"],
        "worker_payout_ref_type": wallets["worker_payout_ref_type"],
        "nomad_evm_payment_address": wallets["nomad_evm_payment_address"],
        "nomad_rtc_receive_ref": wallets["nomad_rtc_receive_ref"],
        "evm_chain_id": wallets["evm_chain_id"],
        "native_symbol": wallets["native_symbol"],
        "execution_boundary": "instruction_only_no_private_key_no_auto_wallet_signing",
    }
    after = revenue_pressure_snapshot()
    return {
        "ok": True,
        "schema": HOOK_SCHEMA,
        "generated_at": _iso_now(),
        "source_endpoint": source_endpoint,
        "accepted": bool(accepted and receipt.get("ok")),
        "eligible_signal": bool(eligible),
        "blocked_by": blocked_by,
        "buyer_funded_signal": buyer,
        "stage": stage,
        "proof_gate": {
            **proof,
            "threshold": round(threshold, 4),
            "passed": proof_ok,
            "shadow_lane": shadow,
        },
        "receipt_payload": receipt_payload,
        "recorded_receipt": receipt,
        "distribution_instruction": distribution,
        "receipt_predictor_update": {
            "schema": "nomad.receipt_predictor_update_hint.v1",
            "effect": "paid_receipt_summary_available_to_predictor" if receipt.get("ok") else "no_predictor_change",
            "recognized_revenue_usd": after["recognized_revenue_usd"],
            "paid_receipt_count": after["paid_receipt_count"],
        },
        "retention_gradient_update": {
            "schema": "nomad.retention_gradient_update_hint.v1",
            "effect": "worker_pool_allocation_can_shift_retention_gradient" if receipt.get("ok") else "still_starving",
            "retention_gradient": after["retention_gradient"],
            "worker_settlement_pool_usd": after["worker_settlement_pool_usd"],
        },
        "links": {
            "revenue_settlement": _u(base_url, "/.well-known/nomad-revenue-settlement.json"),
            "work_receipts": _u(base_url, "/.well-known/nomad-work-receipts.json"),
            "gradient": _u(base_url, "/swarm/gradient"),
        },
    }
