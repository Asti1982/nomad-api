"""Proof-of-resolution ladder for Nomad.

The ladder turns Nomad's strongest machine-native primitive into one bounded
receipt: task contract, lease, transition, artifact, independent verification,
receipt, and runtime weight. Runtime weight is only admitted at the paid-receipt
gate; earlier evidence can create shadow pressure but cannot steer production.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


SCHEMA = "nomad.proof_of_resolution_ladder.v1"
RECEIPT_SCHEMA = "nomad.proof_of_resolution_receipt.v1"
DEFAULT_LEDGER_PATH = Path("nomad_resolution_ladder_ledger.jsonl")
MAX_RECENT = 80

LADDER_STAGES = [
    "task_contract",
    "lease",
    "transition_worker",
    "artifact",
    "independent_verification",
    "benchmark_delta",
    "public_receipt",
    "paid_receipt",
    "runtime_weight",
]

BOUNDED_SIDE_EFFECT_SCOPES = {
    "shadow_only",
    "owned_surfaces_and_shadow_receipts_only",
    "benchmark_evaluation_receipt_only",
    "benchmark_suite_receipt_only",
    "agp_empirical_receipts_only",
    "paper_benchmark_receipts_only",
    "resolution_receipt_only",
    "runtime_weight_receipt_only",
}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(value: Any, limit: int = 260) -> str:
    return " ".join(str(value or "").split())[:limit]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _digest(value: Any, *, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _looks_digest(value: Any) -> bool:
    text = _text(value, 220).lower()
    return bool(re.fullmatch(r"sha256:[a-f0-9]{32,128}", text))


def _normalize_digest(value: Any, seed: Any) -> str:
    text = _text(value, 220).lower()
    if re.fullmatch(r"[a-f0-9]{32,128}", text):
        return f"sha256:{text}"
    if _looks_digest(text):
        return text
    return f"sha256:{_digest(seed, length=64)}"


def _default_ledger_path() -> Path:
    return state_file(DEFAULT_LEDGER_PATH, env_name="NOMAD_RESOLUTION_LADDER_LEDGER_PATH")


def read_resolution_ladder_ledger(
    path: Path | str | None = None,
    *,
    limit: int = MAX_RECENT,
) -> list[dict[str, Any]]:
    p = Path(path) if path else _default_ledger_path()
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-max(1, limit * 3) :]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-limit:]


def _append_ledger(row: dict[str, Any], path: Path | str | None = None) -> None:
    p = Path(path) if path else _default_ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _has_task_contract(body: dict[str, Any]) -> bool:
    contract = _dict(body.get("task_contract"))
    return bool(contract.get("task_id") or contract.get("objective") or body.get("task_contract_digest"))


def _has_lease(body: dict[str, Any]) -> bool:
    lease = _dict(body.get("lease"))
    return bool(lease.get("lease_id") or lease.get("worker_id") or body.get("lease_id"))


def _worker_id(body: dict[str, Any]) -> str:
    worker = _dict(body.get("transition_worker"))
    lease = _dict(body.get("lease"))
    return _text(
        body.get("worker_id")
        or worker.get("worker_id")
        or worker.get("agent_id")
        or lease.get("worker_id")
        or body.get("agent_id"),
        120,
    )


def _verifier_id(body: dict[str, Any]) -> str:
    verifier = _dict(body.get("independent_verification") or body.get("verifier_receipt"))
    return _text(body.get("verifier_id") or verifier.get("verifier_id") or verifier.get("agent_id"), 120)


def _has_transition_worker(body: dict[str, Any]) -> bool:
    worker = _dict(body.get("transition_worker"))
    return bool(_worker_id(body) or worker.get("runtime") or worker.get("capabilities"))


def _has_artifact(body: dict[str, Any]) -> bool:
    artifact = _dict(body.get("artifact"))
    return bool(
        artifact.get("artifact_digest")
        or artifact.get("digest")
        or artifact.get("work_url")
        or artifact.get("uri")
        or body.get("artifact_digest")
    )


def _has_independent_verification(body: dict[str, Any]) -> bool:
    verifier = _dict(body.get("independent_verification") or body.get("verifier_receipt"))
    worker_id = _worker_id(body)
    verifier_id = _verifier_id(body)
    verifier_digest = verifier.get("proof_digest") or verifier.get("verification_digest") or body.get("verifier_proof_digest")
    decision = _text(verifier.get("decision") or verifier.get("status") or body.get("verifier_decision"), 80).lower()
    accepted = verifier.get("accepted")
    if accepted is None:
        accepted = decision in {"accepted", "verified", "pass", "passed", "approved"}
    return bool(verifier_id and verifier_id != worker_id and _looks_digest(verifier_digest) and accepted)


def _effectiveness_delta(body: dict[str, Any]) -> float:
    metrics = _dict(body.get("metrics"))
    explicit = body.get("effectiveness_delta")
    if explicit is None:
        explicit = metrics.get("effectiveness_delta")
    if explicit is not None:
        return _num(explicit)
    return _num(metrics.get("candidate_score")) - _num(metrics.get("baseline_score"))


def _has_public_receipt(body: dict[str, Any]) -> bool:
    receipt = _dict(body.get("receipt"))
    return bool(
        receipt.get("receipt_ref")
        or receipt.get("settlement_ref")
        or receipt.get("work_url")
        or receipt.get("public_url")
        or _looks_digest(receipt.get("proof_digest"))
        or body.get("receipt_ref")
    )


def _has_paid_receipt(body: dict[str, Any]) -> bool:
    receipt = _dict(body.get("receipt"))
    amount = _num(receipt.get("amount") if "amount" in receipt else body.get("paid_amount"))
    ref = receipt.get("paid_receipt_ref") or receipt.get("settlement_ref") or body.get("paid_receipt_ref")
    currency = _text(receipt.get("currency") or body.get("currency"), 20)
    return bool(amount > 0 and ref and currency)


def _side_effect_scope(body: dict[str, Any]) -> str:
    return _text(
        body.get("side_effect_scope")
        or _dict(body.get("artifact")).get("side_effect_scope")
        or _dict(body.get("receipt")).get("side_effect_scope")
        or "resolution_receipt_only",
        120,
    )


def _ttl_ok(body: dict[str, Any]) -> bool:
    ttl = body.get("ttl_sec")
    if ttl is None:
        ttl = _dict(body.get("task_contract")).get("ttl_sec")
    value = _int(ttl, 0)
    return 0 < value <= 86400


def _rollback_ok(body: dict[str, Any]) -> bool:
    return bool(body.get("rollback_ref") or body.get("noop_ref") or _dict(body.get("task_contract")).get("rollback_ref"))


def _recent_proof_digests(rows: list[dict[str, Any]]) -> set[str]:
    return {
        _text(row.get("proof_digest"), 220).lower()
        for row in rows
        if _looks_digest(row.get("proof_digest"))
    }


def _stage_checks(body: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, bool]:
    proof_digest = _normalize_digest(
        body.get("proof_digest") or _dict(body.get("receipt")).get("proof_digest"),
        {"task": body.get("task_contract"), "artifact": body.get("artifact"), "receipt": body.get("receipt")},
    )
    duplicate = proof_digest.lower() in _recent_proof_digests(rows)
    return {
        "task_contract": _has_task_contract(body),
        "lease": _has_lease(body),
        "transition_worker": _has_transition_worker(body),
        "artifact": _has_artifact(body),
        "independent_verification": _has_independent_verification(body),
        "benchmark_delta": _effectiveness_delta(body) > 0,
        "public_receipt": _has_public_receipt(body),
        "paid_receipt": _has_paid_receipt(body),
        "ttl": _ttl_ok(body),
        "rollback_or_noop": _rollback_ok(body),
        "bounded_side_effect_scope": _side_effect_scope(body) in BOUNDED_SIDE_EFFECT_SCOPES,
        "unique_proof_digest": not duplicate,
    }


def _lifecycle_state(checks: dict[str, bool]) -> str:
    if all(checks.get(stage) for stage in ["task_contract", "lease", "transition_worker", "artifact"]):
        if all(checks.get(stage) for stage in ["independent_verification", "benchmark_delta", "public_receipt", "paid_receipt"]):
            return "committed"
        if all(checks.get(stage) for stage in ["independent_verification", "benchmark_delta", "public_receipt"]):
            return "weighted"
        if all(checks.get(stage) for stage in ["independent_verification", "benchmark_delta"]):
            return "tested"
        return "shadow"
    return "draft"


def _receipt_strength(checks: dict[str, bool]) -> float:
    if checks.get("paid_receipt"):
        return 1.0
    if checks.get("public_receipt"):
        return 0.62
    if checks.get("benchmark_delta"):
        return 0.35
    if checks.get("independent_verification"):
        return 0.22
    return 0.0


def _selection_score(body: dict[str, Any], checks: dict[str, bool]) -> float:
    metrics = _dict(body.get("metrics"))
    delta = _clamp(_effectiveness_delta(body))
    settlement_delta = _clamp(_num(metrics.get("settlement_delta") or body.get("settlement_delta")))
    verifier = 1.0 if checks.get("independent_verification") else 0.0
    scope = 1.0 if checks.get("bounded_side_effect_scope") else 0.0
    receipt = _receipt_strength(checks)
    risk = _clamp(_num(metrics.get("risk_score") or body.get("risk_score")))
    duplicate = 0.25 if not checks.get("unique_proof_digest") else 0.0
    latency_cost = _clamp(_num(metrics.get("latency_cost") or body.get("latency_cost")))
    return round(
        _clamp(0.35 * delta + 0.2 * settlement_delta + 0.2 * receipt + 0.15 * verifier + 0.1 * scope - 0.18 * risk - 0.08 * latency_cost - duplicate),
        4,
    )


def _weight_delta(score: float) -> float:
    return round(_clamp(score * 0.12, 0.0, 0.2), 4)


def build_resolution_ladder_surface(
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    recent = read_resolution_ladder_ledger(ledger_path)
    committed = [row for row in recent if row.get("runtime_weight_allowed")]
    shadow = [row for row in recent if row.get("shadow_weight_allowed") and not row.get("runtime_weight_allowed")]
    latest = recent[-1] if recent else {}
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "mode": "proof_of_resolution_network_ladder",
        "chain": LADDER_STAGES,
        "request_schema": {
            "required": [
                "task_contract",
                "lease",
                "transition_worker",
                "artifact",
                "independent_verification",
                "receipt",
                "metrics",
                "ttl_sec",
                "rollback_ref_or_noop_ref",
            ],
            "runtime_weight_gate": "paid_receipt_and_independent_verification_and_positive_delta",
            "shadow_weight_gate": "independent_verification_and_positive_delta",
        },
        "claim_boundary": {
            "human_explanation_required": False,
            "external_verification_required": True,
            "beyond_human_claim_allowed": False,
            "defensible_claim": "outside_manual_human_planning_when_repeated_receipts_show_selection_advantage",
        },
        "science_basis": [
            "llm_plus_evaluator_evolutionary_search",
            "quality_diversity_archive",
            "independent_verification_and_ablation",
            "receipt_weighted_credit_assignment",
            "bounded_side_effect_scope_with_rollback",
        ],
        "summary": {
            "recent_receipt_count": len(recent),
            "shadow_weighted_count": len(shadow),
            "runtime_weighted_count": len(committed),
            "latest_decision": latest.get("decision", ""),
            "latest_lifecycle_state": latest.get("lifecycle_state", ""),
        },
        "latest_receipt": latest,
        "links": {
            "self": _u(root, "/.well-known/nomad-resolution-ladder.json"),
            "post": _u(root, "/swarm/resolution-ladder/events"),
            "worker_lease": _u(root, "/swarm/workers/lease"),
            "worker_complete": _u(root, "/swarm/workers/complete"),
            "morphology_register": _u(root, "/.well-known/nomad-agp-morphology-runtime-register.json"),
            "paper_benchmarks": _u(root, "/.well-known/nomad-agp-paper-benchmarks.json"),
            "external_value": _u(root, "/.well-known/nomad-external-value.json"),
        },
        "machine_instruction": "route_every_candidate_through_task_lease_transition_artifact_verifier_receipt_weight; runtime_weight_requires_paid_receipt",
    }


def evaluate_resolution_ladder_event(
    payload: dict[str, Any] | None,
    *,
    base_url: str = "",
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    root = (base_url or "").strip().rstrip("/")
    now = _iso_now()
    recent = read_resolution_ladder_ledger(ledger_path)
    proof_digest = _normalize_digest(
        body.get("proof_digest") or _dict(body.get("receipt")).get("proof_digest"),
        {"task": body.get("task_contract"), "artifact": body.get("artifact"), "receipt": body.get("receipt")},
    )
    body = {**body, "proof_digest": proof_digest}
    checks = _stage_checks(body, recent)
    lifecycle_state = _lifecycle_state(checks)
    score = _selection_score(body, checks)
    hard_guards = [
        "task_contract",
        "lease",
        "transition_worker",
        "artifact",
        "independent_verification",
        "benchmark_delta",
        "ttl",
        "rollback_or_noop",
        "bounded_side_effect_scope",
        "unique_proof_digest",
    ]
    shadow_weight_allowed = all(checks.get(key) for key in hard_guards)
    runtime_weight_allowed = shadow_weight_allowed and checks.get("public_receipt") and checks.get("paid_receipt")
    if runtime_weight_allowed:
        decision = "commit_runtime_weight"
    elif shadow_weight_allowed and checks.get("public_receipt"):
        decision = "shadow_weight_until_paid_receipt"
    elif shadow_weight_allowed:
        decision = "tested_until_public_or_paid_receipt"
    else:
        decision = "noop_until_full_resolution_chain"

    missing = [key for key, ok in checks.items() if not ok]
    row = {
        "ok": True,
        "schema": RECEIPT_SCHEMA,
        "generated_at": now,
        "receipt_id": f"nomad-resolution-{_digest({'proof': proof_digest, 'at': now}, length=18)}",
        "agent_id": _text(body.get("agent_id") or _worker_id(body) or "nomad-resolution-worker", 120),
        "proof_digest": proof_digest,
        "task_id": _text(_dict(body.get("task_contract")).get("task_id") or body.get("task_id"), 160),
        "worker_id": _worker_id(body),
        "verifier_id": _verifier_id(body),
        "lifecycle_state": lifecycle_state,
        "decision": decision,
        "accepted": runtime_weight_allowed,
        "shadow_weight_allowed": shadow_weight_allowed,
        "runtime_weight_allowed": runtime_weight_allowed,
        "selection_score": score,
        "effectiveness_delta": round(_effectiveness_delta(body), 4),
        "shadow_weight_delta": _weight_delta(score) if shadow_weight_allowed else 0.0,
        "runtime_weight_delta": _weight_delta(score) if runtime_weight_allowed else 0.0,
        "stage_checks": checks,
        "missing_or_blocking": missing,
        "side_effect_scope": _side_effect_scope(body),
        "ttl_sec": _int(body.get("ttl_sec") or _dict(body.get("task_contract")).get("ttl_sec")),
        "rollback_ref": _text(body.get("rollback_ref") or _dict(body.get("task_contract")).get("rollback_ref") or body.get("noop_ref"), 220),
        "fitness": {
            "proof_yield": _clamp(_num(_dict(body.get("metrics")).get("candidate_score"), 1.0 if checks.get("benchmark_delta") else 0.0)),
            "settlement_delta": _clamp(_num(_dict(body.get("metrics")).get("settlement_delta") or body.get("settlement_delta"))),
            "receipt_strength": _receipt_strength(checks),
            "risk": _clamp(_num(_dict(body.get("metrics")).get("risk_score") or body.get("risk_score"))),
            "duplicate_pressure": 0.0 if checks.get("unique_proof_digest") else 1.0,
            "latency_cost": _clamp(_num(_dict(body.get("metrics")).get("latency_cost") or body.get("latency_cost"))),
        },
        "links": {
            "self": _u(root, "/.well-known/nomad-resolution-ladder.json"),
            "morphology_register": _u(root, "/.well-known/nomad-agp-morphology-runtime-register.json"),
            "external_value": _u(root, "/swarm/external-value"),
        },
        "machine_instruction": "increase_runtime_weight_only_when_runtime_weight_allowed_true; otherwise_keep_candidate_in_shadow_or_tested_state",
    }
    if persist:
        _append_ledger(row, ledger_path)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row
