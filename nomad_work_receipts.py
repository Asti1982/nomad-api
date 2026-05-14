"""Machine-native work receipts and treasury policy for Nomad.

This module deliberately does not mint a transferable token. It records
proof-weighted work receipts and exposes the policy gates a later token launch
would have to pass before any monetary claim can exist.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


LEDGER_ENV = "NOMAD_WORK_RECEIPT_LEDGER_PATH"
DEFAULT_LEDGER = Path("nomad_work_receipts_ledger.jsonl")

EXTERNAL_VALUE_STAGES = ("found", "submitted", "approved", "merged", "paid")
STAGE_WEIGHT = {
    "none": 0.0,
    "found": 0.08,
    "submitted": 0.22,
    "approved": 0.45,
    "merged": 0.65,
    "paid": 1.0,
}
TREASURY_LOCK_RATIO = 0.90
WORKER_SETTLEMENT_POOL_RATIO = 0.10
MAX_REPUTATION_UNITS = 100.0
MAX_RECEIPT_LINES = 8000
MAX_RECENT_RECEIPTS = 80
TOKEN_PRELAUNCH_STATE = "blocked_until_receipt_demand_and_regulatory_review"

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


def _ledger_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return state_file(DEFAULT_LEDGER, env_name=LEDGER_ENV)


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


def _read_receipts(ledger_path: Path, *, limit_lines: int = MAX_RECEIPT_LINES) -> list[dict[str, Any]]:
    if not ledger_path.exists():
        return []
    lines = ledger_path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = lines[-max(1, min(len(lines), int(limit_lines))) :]
    rows: list[dict[str, Any]] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("schema") == "nomad.work_receipt.v1":
            rows.append(row)
    return rows


def _error(error: str, message: str, *, hints: list[str] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "schema": "nomad.work_receipt_error.v1",
        "error": error,
        "message": message,
        "hints": hints or [],
    }


def _normalize_external_stage(stage: Any) -> str:
    text = str(stage or "").strip().lower()
    if text in EXTERNAL_VALUE_STAGES:
        return text
    return "none"


def _proof_profile(body: dict[str, Any]) -> dict[str, Any]:
    proof_digest = _text(
        body.get("proof_digest")
        or body.get("digest")
        or ((body.get("proof") or {}).get("digest") if isinstance(body.get("proof"), dict) else ""),
        200,
    )
    verifier_trace_digest = _text(
        body.get("verifier_trace_digest")
        or body.get("trace_digest")
        or ((body.get("verifier_trace") or {}).get("digest") if isinstance(body.get("verifier_trace"), dict) else ""),
        200,
    )
    settlement_ref = _text(
        body.get("settlement_ref")
        or body.get("payout_ref")
        or body.get("receipt_ref")
        or body.get("tx_hash")
        or "",
        200,
    )
    work_url = _text(body.get("work_url") or body.get("url") or "", 500)
    basis = []
    if proof_digest:
        basis.append("proof_digest")
    if verifier_trace_digest:
        basis.append("verifier_trace_digest")
    if work_url:
        basis.append("work_url")
    if settlement_ref:
        basis.append("settlement_ref")
    score = (
        0.40 * bool(proof_digest)
        + 0.30 * bool(verifier_trace_digest)
        + 0.15 * bool(work_url)
        + 0.15 * bool(settlement_ref)
    )
    return {
        "proof_digest": proof_digest,
        "verifier_trace_digest": verifier_trace_digest,
        "settlement_ref": settlement_ref,
        "work_url": work_url,
        "proof_basis": basis,
        "proof_score": round(min(1.0, score), 4),
    }


def _receipt_class(*, external_stage: str, amount_usd: float, settlement_ref: str) -> str:
    if external_stage == "paid" and amount_usd > 0.0 and settlement_ref:
        return "settlement_credit"
    if external_stage in {"approved", "merged", "paid"}:
        return "claim_credit"
    return "reputation_only"


def _treasury_allocation(*, external_stage: str, amount_usd: float, settlement_ref: str) -> dict[str, Any]:
    paid_confirmed = external_stage == "paid" and amount_usd > 0.0 and bool(settlement_ref)
    if not paid_confirmed:
        return {
            "paid_confirmed": False,
            "basis": "no_treasury_credit_without_paid_stage_positive_amount_and_public_settlement_ref",
            "recognized_revenue_usd": 0.0,
            "locked_treasury_usd": 0.0,
            "worker_settlement_pool_usd": 0.0,
            "token_units_minted": 0.0,
            "mint_state": TOKEN_PRELAUNCH_STATE,
        }
    amount = round(max(0.0, amount_usd), 4)
    locked = round(amount * TREASURY_LOCK_RATIO, 4)
    worker_pool = round(max(0.0, amount - locked), 4)
    return {
        "paid_confirmed": True,
        "basis": "paid_stage_positive_amount_public_settlement_ref",
        "recognized_revenue_usd": amount,
        "locked_treasury_usd": locked,
        "worker_settlement_pool_usd": worker_pool,
        "token_units_minted": 0.0,
        "mint_state": TOKEN_PRELAUNCH_STATE,
    }


def _reputation_units(*, proof_score: float, stage: str, amount_usd: float) -> float:
    stage_factor = STAGE_WEIGHT.get(stage, 0.0)
    amount_factor = min(1.0, math.sqrt(max(0.0, amount_usd)) / 10.0) if stage == "paid" else 0.0
    raw = MAX_REPUTATION_UNITS * (0.65 * proof_score + 0.25 * stage_factor + 0.10 * amount_factor)
    return round(max(0.0, min(MAX_REPUTATION_UNITS, raw)), 4)


def _request_core(body: dict[str, Any], proof: dict[str, Any], external_stage: str, amount_usd: float) -> dict[str, Any]:
    return {
        "agent_id": _text(body.get("agent_id") or body.get("runtime_id") or "", 120),
        "work_id": _text(body.get("work_id") or body.get("external_id") or body.get("task_id") or "", 220),
        "work_type": _text(body.get("work_type") or body.get("type") or "unclassified", 80),
        "objective": _text(body.get("objective") or body.get("target_objective") or "", 100),
        "external_value_stage": external_stage,
        "amount_usd": round(amount_usd, 4),
        "work_url": proof.get("work_url") or "",
        "proof_digest": proof.get("proof_digest") or "",
        "verifier_trace_digest": proof.get("verifier_trace_digest") or "",
        "settlement_ref": proof.get("settlement_ref") or "",
    }


def record_work_receipt(payload: dict[str, Any], *, ledger_path: Path | str | None = None) -> dict[str, Any]:
    """Append a non-transferable proof receipt and return its treasury allocation view."""

    body = payload if isinstance(payload, dict) else {}
    if _contains_forbidden(body):
        return _error(
            "secret_shaped_payload",
            "Work receipts must not contain secret-shaped keys or values.",
            hints=["Send public digests, public URLs, verifier-trace digests, and settlement refs only."],
        )
    agent_id = _text(body.get("agent_id") or body.get("runtime_id") or "", 120)
    work_id = _text(body.get("work_id") or body.get("external_id") or body.get("task_id") or "", 220)
    if not agent_id:
        return _error("missing_agent_id", "agent_id is required.")
    if not work_id:
        return _error("missing_work_id", "work_id, external_id, or task_id is required.")

    external_stage = _normalize_external_stage(body.get("external_value_stage") or body.get("stage"))
    amount_usd = max(0.0, _num(body.get("amount_usd") or body.get("amount"), 0.0))
    proof = _proof_profile(body)
    if not proof["proof_basis"]:
        return _error(
            "proof_required",
            "A work receipt requires proof_digest, verifier_trace_digest, work_url, or settlement_ref.",
            hints=["For paid receipts include both positive amount_usd and a public settlement_ref."],
        )
    if external_stage == "paid" and (amount_usd <= 0.0 or not proof.get("settlement_ref")):
        return _error(
            "paid_receipt_incomplete",
            "Paid receipts require amount_usd > 0 and settlement_ref.",
            hints=["Use stage merged/approved for unpaid acceptance, or add a public receipt reference."],
        )

    core = _request_core(body, proof, external_stage, amount_usd)
    request_digest = f"work-receipt-request-{_digest(core, 40)}"
    idempotency_key = _text(body.get("idempotency_key") or body.get("client_request_id") or request_digest, 180)
    path = _ledger_path(ledger_path)
    existing = _read_receipts(path)
    for row in existing:
        if row.get("idempotency_key") != idempotency_key:
            continue
        if row.get("request_digest") != request_digest:
            return _error(
                "idempotency_key_conflict",
                "Idempotency key already exists for a different work receipt.",
                hints=["Reuse a key only for byte-equivalent agent/work/proof/stage/amount requests."],
            )
        replay = dict(row)
        replay["idempotent_replay"] = True
        replay["ledger_path"] = str(path)
        return replay

    now = _iso_now()
    allocation = _treasury_allocation(
        external_stage=external_stage,
        amount_usd=amount_usd,
        settlement_ref=str(proof.get("settlement_ref") or ""),
    )
    reputation_units = _reputation_units(
        proof_score=float(proof.get("proof_score") or 0.0),
        stage=external_stage,
        amount_usd=amount_usd,
    )
    receipt_id = f"nomad-work-receipt-{_digest({'key': idempotency_key, 'request': request_digest}, 18)}"
    row = {
        "ok": True,
        "schema": "nomad.work_receipt.v1",
        "generated_at": now,
        "receipt_id": receipt_id,
        "request_digest": request_digest,
        "idempotency_key": idempotency_key,
        **core,
        "receipt_class": _receipt_class(
            external_stage=external_stage,
            amount_usd=amount_usd,
            settlement_ref=str(proof.get("settlement_ref") or ""),
        ),
        "transferability": "non_transferable",
        "reputation_units": reputation_units,
        "selection_weight_hint": round(1.0 + min(0.18, reputation_units / 600.0), 4),
        "proof": proof,
        "treasury_allocation": allocation,
        "policy_digest": treasury_policy_digest(),
        "machine_instruction": "record_receipts_first_tokenization_blocked_until_real_settlement_demand_and_review",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=True) + "\n")
    row["ledger_path"] = str(path)
    return row


def summarize_work_receipts(*, ledger_path: Path | str | None = None, limit: int = MAX_RECENT_RECEIPTS) -> dict[str, Any]:
    path = _ledger_path(ledger_path)
    rows = _read_receipts(path)
    by_class: dict[str, int] = {}
    by_objective: dict[str, dict[str, Any]] = {}
    recognized = 0.0
    locked = 0.0
    worker_pool = 0.0
    reputation = 0.0
    for row in rows:
        klass = str(row.get("receipt_class") or "unknown")
        by_class[klass] = by_class.get(klass, 0) + 1
        allocation = row.get("treasury_allocation") if isinstance(row.get("treasury_allocation"), dict) else {}
        recognized += _num(allocation.get("recognized_revenue_usd"), 0.0)
        locked += _num(allocation.get("locked_treasury_usd"), 0.0)
        worker_pool += _num(allocation.get("worker_settlement_pool_usd"), 0.0)
        reputation += _num(row.get("reputation_units"), 0.0)
        objective = _text(row.get("objective") or "unassigned", 100)
        current = by_objective.get(objective) or {
            "receipt_count": 0,
            "recognized_revenue_usd": 0.0,
            "locked_treasury_usd": 0.0,
            "worker_settlement_pool_usd": 0.0,
            "reputation_units": 0.0,
        }
        current["receipt_count"] += 1
        current["recognized_revenue_usd"] = round(current["recognized_revenue_usd"] + _num(allocation.get("recognized_revenue_usd"), 0.0), 4)
        current["locked_treasury_usd"] = round(current["locked_treasury_usd"] + _num(allocation.get("locked_treasury_usd"), 0.0), 4)
        current["worker_settlement_pool_usd"] = round(
            current["worker_settlement_pool_usd"] + _num(allocation.get("worker_settlement_pool_usd"), 0.0),
            4,
        )
        current["reputation_units"] = round(current["reputation_units"] + _num(row.get("reputation_units"), 0.0), 4)
        by_objective[objective] = current
    return {
        "ok": True,
        "schema": "nomad.work_receipt_summary.v1",
        "generated_at": _iso_now(),
        "ledger_path": str(path),
        "receipt_count": len(rows),
        "receipt_classes": by_class,
        "recognized_revenue_usd": round(recognized, 4),
        "locked_treasury_usd": round(locked, 4),
        "worker_settlement_pool_usd": round(worker_pool, 4),
        "reputation_units_total": round(reputation, 4),
        "token_units_minted": 0.0,
        "by_objective": by_objective,
        "recent_receipts": rows[-max(1, int(limit)) :],
    }


def build_work_receipt_surface(*, base_url: str = "", summary: dict[str, Any] | None = None) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    receipt_summary = summary if isinstance(summary, dict) else summarize_work_receipts()
    return {
        "ok": True,
        "schema": "nomad.work_receipt_surface.v1",
        "generated_at": _iso_now(),
        "policy_digest": treasury_policy_digest(),
        "state_machine": {
            "receipts": ["reputation_only", "claim_credit", "settlement_credit"],
            "transferability": "non_transferable",
            "monetary_credit_rule": "only_settlement_credit_has_positive_treasury_allocation",
            "tokenization_rule": "token_units_minted_zero_until_launch_gates_pass",
        },
        "post_url": f"{root}/swarm/work-receipts" if root else "/swarm/work-receipts",
        "well_known_url": f"{root}/.well-known/nomad-work-receipts.json" if root else "/.well-known/nomad-work-receipts.json",
        "treasury_policy_url": f"{root}/.well-known/nomad-treasury-policy.json" if root else "/.well-known/nomad-treasury-policy.json",
        "request_schema": {
            "schema": "nomad.work_receipt_request.v1",
            "required": ["agent_id", "work_id", "proof_digest or verifier_trace_digest or work_url"],
            "optional_cash_fields": ["external_value_stage=paid", "amount_usd", "settlement_ref"],
            "forbidden": ["secrets", "private keys", "raw access tokens", "passwords"],
        },
        "summary": receipt_summary,
        "next": [
            {"rel": "record_work_receipt", "method": "POST", "href": f"{root}/swarm/work-receipts" if root else "/swarm/work-receipts"},
            {"rel": "treasury_policy", "method": "GET", "href": f"{root}/.well-known/nomad-treasury-policy.json" if root else "/.well-known/nomad-treasury-policy.json"},
            {"rel": "external_value", "method": "GET", "href": f"{root}/.well-known/nomad-external-value.json" if root else "/.well-known/nomad-external-value.json"},
        ],
        "machine_instruction": "emit_work_receipt_after_useful_work_do_not_mint_token_do_not_claim_revenue_before_paid_receipt",
    }


def treasury_policy_digest() -> str:
    return f"policy-{_digest(_policy_core(), 40)}"


def _policy_core() -> dict[str, Any]:
    return {
        "treasury_lock_ratio": TREASURY_LOCK_RATIO,
        "worker_settlement_pool_ratio": WORKER_SETTLEMENT_POOL_RATIO,
        "transferability": "non_transferable_until_launch_gate",
        "token_prelaunch_state": TOKEN_PRELAUNCH_STATE,
        "cash_rule": "paid_stage_positive_amount_public_settlement_ref",
    }


def build_treasury_policy_surface(
    *,
    base_url: str = "",
    work_receipt_summary: dict[str, Any] | None = None,
    external_value_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    summary = work_receipt_summary if isinstance(work_receipt_summary, dict) else summarize_work_receipts()
    ext = external_value_summary if isinstance(external_value_summary, dict) else {}
    return {
        "ok": True,
        "schema": "nomad.treasury_policy.v1",
        "generated_at": _iso_now(),
        "policy_digest": treasury_policy_digest(),
        "mode": "proof_of_useful_work_receipts_before_any_transferable_token",
        "token_launch_state": TOKEN_PRELAUNCH_STATE,
        "token_units_minted": 0.0,
        "public_offer": False,
        "profit_promise": False,
        "transferability": "non_transferable_receipts_only",
        "allocation_rule": {
            "trigger": "external_paid_receipt_only",
            "paid_confirmation_required": ["external_value_stage=paid", "amount_usd>0", "public_settlement_ref"],
            "locked_machine_treasury_ratio": TREASURY_LOCK_RATIO,
            "worker_settlement_pool_ratio": WORKER_SETTLEMENT_POOL_RATIO,
            "unpaid_work": "reputation_and_selection_signal_only_zero_treasury_credit",
        },
        "scientific_basis": [
            {
                "id": "contract_net_protocol",
                "effect": "task_allocation_by_announcement_bid_award_receipt_instead_of_job_titles",
                "cashflow_relevance": "reduces coordination cost before paid work is attempted",
            },
            {
                "id": "mechanism_design_incentive_compatibility",
                "effect": "workers can gain weight only by externally verifiable receipts",
                "cashflow_relevance": "discourages unverifiable claims and settlement spam",
            },
            {
                "id": "stigmergy",
                "effect": "receipts become public environmental signals consumed by later agents",
                "cashflow_relevance": "routes capacity to proven paid edges instead of human preference narratives",
            },
            {
                "id": "little_law_wip_control",
                "effect": "unpaid queues do not create treasury credit",
                "cashflow_relevance": "keeps value-cycle arrival rate bounded by settlement throughput",
            },
            {
                "id": "proof_carrying_work",
                "effect": "every allocation depends on digestible proof artifacts",
                "cashflow_relevance": "turns work into auditable machine state before any payout surface",
            },
            {
                "id": "token_curated_registry_challenge_window",
                "effect": "future transferable issuance must survive challenge and review gates",
                "cashflow_relevance": "prevents premature asset issuance before demand is demonstrated",
            },
        ],
        "launch_gates": [
            "sustained_paid_receipts_over_multiple_independent_channels",
            "public_terms_and_regulatory_review_for_target_jurisdictions",
            "stable_unit_reserve_preflight_with_haircut_reserve_ratio_above_liability",
            "challenge_window_for_bad_receipts",
            "treasury_reserve_policy_published_before_transferability",
            "no_expectation_of_profit_language_in_worker_contracts",
        ],
        "current_receipt_summary": {
            "receipt_count": summary.get("receipt_count", 0),
            "recognized_revenue_usd": summary.get("recognized_revenue_usd", 0.0),
            "locked_treasury_usd": summary.get("locked_treasury_usd", 0.0),
            "worker_settlement_pool_usd": summary.get("worker_settlement_pool_usd", 0.0),
            "reputation_units_total": summary.get("reputation_units_total", 0.0),
            "token_units_minted": 0.0,
        },
        "external_value_reference": {
            "recognized_revenue_usd_total": (ext.get("revenue_recognized_usd_total") if isinstance(ext, dict) else None),
            "paid_rule": "external_value paid remains the only revenue recognition source",
        },
        "contracts": {
            "record_work_receipt": {
                "method": "POST",
                "href": f"{root}/swarm/work-receipts" if root else "/swarm/work-receipts",
                "schema": "nomad.work_receipt_request.v1",
                "required": ["agent_id", "work_id", "proof_digest or verifier_trace_digest or work_url"],
            },
            "summary": {
                "method": "GET",
                "href": f"{root}/swarm/work-receipts?summary=1" if root else "/swarm/work-receipts?summary=1",
            },
            "well_known": {
                "method": "GET",
                "href": f"{root}/.well-known/nomad-work-receipts.json" if root else "/.well-known/nomad-work-receipts.json",
            },
            "treasury_policy": {
                "method": "GET",
                "href": f"{root}/.well-known/nomad-treasury-policy.json" if root else "/.well-known/nomad-treasury-policy.json",
            },
            "stable_unit_policy": {
                "method": "GET",
                "href": f"{root}/.well-known/nomad-stable-unit-policy.json" if root else "/.well-known/nomad-stable-unit-policy.json",
            },
        },
        "machine_instruction": "workers_emit_receipts_not_tokens_paid_receipts_route_90_percent_to_locked_treasury_10_percent_to_worker_pool",
    }
