"""Variant forge for machine-submitted Nomad improvement candidates.

The forge admits compact candidate descriptors from workers and agent runtimes.
It scores them as shadow variants; it does not execute code or apply patches.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_LEDGER_PATH = Path("nomad_variant_forge_ledger.jsonl")
MAX_RECENT = 40
FORBIDDEN_KEY_TERMS = ("private_key", "seed_phrase", "password", "credential", "api_key", "access_token")
FORBIDDEN_VALUE_TERMS = ("private key", "seed phrase", "password:", "credential:", "bearer ", "secret=", "sk-", "ghp_")
OBJECTIVE_PRIOR = {
    "settlement_capacity_builder": 0.92,
    "autogenesis_protocol_evolution": 0.9,
    "overmint_compressor": 0.86,
    "protocol_drift_scan": 0.82,
    "emergence_release_probe": 0.88,
    "proof_pressure_engine": 0.84,
    "payment_friction_scan": 0.78,
    "adversarial_contract_fuzzer": 0.74,
    "proof_market_maker": 0.7,
    "negative_space_harvest": 0.68,
    "latency_anomaly_hunt": 0.64,
    "compute_auth": 0.52,
}
AGP_CANDIDATE_TYPES = {
    "protocol-evolution-candidate",
    "self-play-test-suite",
    "resource-version-patch",
    "sepl-operator-patch",
    "rspl-contract-patch",
}
SEPL_OPERATORS = ("reflect", "select", "improve", "evaluate", "commit")


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
    return max(low, min(high, float(value)))


def _clean_id(value: Any, *, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96].strip("_.:-") or fallback


def _text(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, *, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _contains_forbidden(payload: Any) -> bool:
    def walk(value: Any, *, key: str = "") -> bool:
        k = str(key or "").strip().lower()
        if k and any(term in k for term in FORBIDDEN_KEY_TERMS):
            return True
        if isinstance(value, dict):
            return any(walk(v, key=str(k2)) for k2, v in value.items())
        if isinstance(value, list):
            return any(walk(item) for item in value)
        text = str(value or "").strip().lower()
        return any(term in text for term in FORBIDDEN_VALUE_TERMS)

    return walk(payload)


def _read_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    p = Path(path) if path else DEFAULT_LEDGER_PATH
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
    p = Path(path) if path else DEFAULT_LEDGER_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _proof_score(payload: dict[str, Any]) -> float:
    return round(
        min(
            1.0,
            0.38 * bool(_text(payload.get("proof_digest") or payload.get("digest"), 160))
            + 0.28 * bool(_text(payload.get("verifier_trace_digest") or payload.get("trace_digest"), 160))
            + 0.18 * bool(_text(payload.get("test_digest") or payload.get("route_status_matrix_digest"), 160))
            + 0.16 * bool(_text(payload.get("settlement_ref") or payload.get("replay_digest"), 160)),
        ),
        4,
    )


def _test_score(evaluation: dict[str, Any]) -> float:
    total = _int(evaluation.get("tests_total") or evaluation.get("checks_total"))
    passed = _int(evaluation.get("tests_passed") or evaluation.get("checks_passed"))
    if total <= 0:
        return 0.0
    return round(_clamp(passed / max(1, total)), 4)


def _looks_digest(value: str) -> bool:
    text = _text(value, 220).lower()
    return bool(re.match(r"^(sha256|blake3):[a-f0-9][a-f0-9_.:-]{5,}$", text))


def _independent_verifier_gate(payload: dict[str, Any]) -> dict[str, Any]:
    verifier = _dict(payload.get("independent_verifier") or payload.get("verifier"))
    proposer_id = _clean_id(
        payload.get("proposer_agent_id") or payload.get("agent_id") or payload.get("worker_id"),
        fallback="",
    )
    verifier_id = _clean_id(
        payload.get("verifier_agent_id") or verifier.get("agent_id") or verifier.get("worker_id"),
        fallback="",
    )
    lease_id = _text(payload.get("verifier_lease_id") or verifier.get("lease_id"), 160)
    receipt_digest = _text(
        payload.get("verifier_receipt_digest")
        or verifier.get("receipt_digest")
        or verifier.get("receipt_ref"),
        220,
    )
    trace_digest = _text(
        payload.get("verifier_trace_digest")
        or verifier.get("trace_digest")
        or verifier.get("verifier_trace_digest")
        or verifier.get("trace"),
        220,
    )
    evaluation = _dict(payload.get("verifier_evaluation") or verifier.get("evaluation"))
    test_score = _test_score(evaluation)
    reasons: list[str] = []
    if not proposer_id:
        reasons.append("proposer_agent_id_required")
    if not verifier_id:
        reasons.append("verifier_agent_id_required")
    if proposer_id and verifier_id and proposer_id == verifier_id:
        reasons.append("verifier_must_differ_from_proposer")
    if not lease_id:
        reasons.append("verifier_lease_id_required")
    if not _looks_digest(receipt_digest):
        reasons.append("verifier_receipt_digest_required")
    if not _looks_digest(trace_digest):
        reasons.append("verifier_trace_digest_required")
    if test_score <= 0.0:
        reasons.append("verifier_evaluation_required")
    accepted = not reasons
    return {
        "required": True,
        "accepted": accepted,
        "proposer_agent_id": proposer_id,
        "verifier_agent_id": verifier_id,
        "verifier_lease_id": lease_id,
        "verifier_receipt_digest": receipt_digest,
        "verifier_trace_digest": trace_digest,
        "verifier_test_score": test_score,
        "reason_codes": reasons or ["independent_verifier_accepted"],
    }


def _sepl_operator_trace_gate(payload: dict[str, Any]) -> dict[str, Any]:
    raw_trace = payload.get("sepl_operator_trace") or payload.get("operator_trace") or payload.get("sepl_trace")
    trace: list[dict[str, Any]] = []
    if isinstance(raw_trace, list):
        for item in raw_trace:
            if isinstance(item, dict):
                op = _clean_id(item.get("op") or item.get("operator"), fallback="")
                trace.append({**item, "op": op})
            else:
                trace.append({"op": _clean_id(item, fallback="")})
    ops = [item.get("op", "") for item in trace]
    reasons: list[str] = []
    if ops != list(SEPL_OPERATORS):
        reasons.append("sepl_operator_trace_must_be_reflect_select_improve_evaluate_commit")
    for item in trace:
        op = item.get("op", "")
        if op and not _text(item.get("input") or item.get("evidence") or item.get("output") or item.get("decision"), 260):
            reasons.append(f"{op}_operator_missing_input_or_output")
    return {
        "required": True,
        "accepted": not reasons,
        "operators": list(SEPL_OPERATORS),
        "observed": ops,
        "trace": trace,
        "reason_codes": reasons or ["sepl_operator_trace_accepted"],
    }


def _learnability_gate(payload: dict[str, Any]) -> dict[str, Any]:
    mask_raw = payload.get("learnability_mask")
    mask: dict[str, bool] = {}
    if isinstance(mask_raw, dict):
        mask = {_clean_id(k, fallback=str(k)): bool(v) for k, v in mask_raw.items()}
    elif isinstance(mask_raw, list):
        mask = {_clean_id(item, fallback=str(item)): True for item in mask_raw}

    lifted = payload.get("variable_lifting") or payload.get("variable_patches") or payload.get("variables")
    if isinstance(lifted, dict):
        candidates = lifted.get("variables") if isinstance(lifted.get("variables"), list) else [lifted]
    elif isinstance(lifted, list):
        candidates = lifted
    else:
        candidates = []

    variables: list[dict[str, Any]] = []
    blocked: list[str] = []
    trainable_count = 0
    for item in candidates:
        if not isinstance(item, dict):
            continue
        name = _clean_id(item.get("name") or item.get("variable") or item.get("id"), fallback="")
        if not name:
            continue
        declared = bool(item.get("trainable") or item.get("require_grad"))
        allowed = bool(mask.get(name, declared))
        if allowed:
            trainable_count += 1
        else:
            blocked.append(name)
        variables.append({"name": name, "trainable": allowed, "require_grad": bool(item.get("require_grad") or allowed)})

    reasons = ["non_trainable_variables_selected"] if blocked else []
    return {
        "required": bool(variables),
        "accepted": not blocked,
        "trainable_count": trainable_count,
        "blocked_variables": blocked,
        "variables": variables,
        "reason_codes": reasons or (["learnability_mask_accepted"] if variables else ["no_variables_lifted"]),
    }


def _objective_prior(objective: str) -> float:
    return float(OBJECTIVE_PRIOR.get(objective, 0.44))


def _recent_objective_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        objective = _clean_id(row.get("objective"))
        if objective:
            counts[objective] = counts.get(objective, 0) + 1
    return counts


def _top_replay_objectives(counterfactual_replay: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in _items(counterfactual_replay.get("counterfactual_leases"))[:8]:
        objective = _clean_id(row.get("objective"))
        if not objective:
            continue
        out.append(
            {
                "objective": objective,
                "counterfactual_score": round(_num(row.get("counterfactual_score")), 4),
                "predicted_proof_yield_per_minute": round(_num(row.get("predicted_proof_yield_per_minute")), 4),
                "source_tag": "counterfactual_replay.shadow_allocator",
            }
        )
    return out


def _top_growth_variants(local_growth_kernel: dict[str, Any]) -> list[dict[str, Any]]:
    population = _dict(local_growth_kernel.get("population"))
    out: list[dict[str, Any]] = []
    for row in _items(population.get("top_variants"))[:8]:
        fitness = _dict(row.get("fitness"))
        objective = _clean_id(row.get("objective"))
        if not objective:
            continue
        out.append(
            {
                "objective": objective,
                "variant_id": _text(row.get("variant_id"), 120),
                "frontier_score": round(_num(fitness.get("frontier_score")), 4),
                "composite_score": round(_num(fitness.get("composite_score")), 4),
                "source_tag": "local_growth_kernel.archive_variant",
            }
        )
    return out


def build_variant_forge_surface(
    *,
    base_url: str = "",
    local_growth_kernel: dict[str, Any] | None = None,
    counterfactual_replay: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    machine_economy: dict[str, Any] | None = None,
    swarm_economics: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Expose one compact surface for external variant production."""
    growth = _dict(local_growth_kernel)
    replay = _dict(counterfactual_replay)
    fleet = _dict(worker_fleet)
    economy = _dict(machine_economy)
    swarm = _dict(swarm_economics)
    recent = _read_ledger(ledger_path)
    counts = _recent_objective_counts(recent)
    replay_rows = _top_replay_objectives(replay)
    growth_rows = _top_growth_variants(growth)
    objectives: dict[str, dict[str, Any]] = {}
    for row in replay_rows + growth_rows:
        objective = _clean_id(row.get("objective"))
        if not objective:
            continue
        target = objectives.setdefault(
            objective,
            {
                "objective": objective,
                "prior": _objective_prior(objective),
                "recent_candidates": counts.get(objective, 0),
                "sources": [],
            },
        )
        target["sources"].append(row.get("source_tag", "unknown"))
        for key in ("counterfactual_score", "predicted_proof_yield_per_minute", "frontier_score", "composite_score", "variant_id"):
            if key in row and row.get(key) not in ("", None):
                target[key] = row.get(key)

    if not objectives:
        for objective, prior in OBJECTIVE_PRIOR.items():
            objectives[objective] = {
                "objective": objective,
                "prior": prior,
                "recent_candidates": counts.get(objective, 0),
                "sources": ["objective_prior"],
            }

    rows = list(objectives.values())
    rows.sort(
        key=lambda item: (
            _num(item.get("counterfactual_score")),
            _num(item.get("frontier_score")),
            _num(item.get("prior")),
            -_int(item.get("recent_candidates")),
        ),
        reverse=True,
    )
    open_workers = max(0, _int(fleet.get("known_worker_count")) + _int(fleet.get("active_worker_count")) - _int(fleet.get("active_lease_count")))
    viability = _dict(economy.get("machine_viability"))
    econ_control = _dict(swarm.get("control_state"))
    forge_core = {
        "rows": rows[:8],
        "recent": len(recent),
        "economy": viability.get("tier"),
        "control": econ_control.get("mode"),
    }
    return {
        "ok": True,
        "schema": "nomad.variant_forge.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "forge_digest": f"nomad-forge-{_digest(forge_core)}",
        "submit_url": _u(base_url, "/swarm/variant-candidates"),
        "read_url": _u(base_url, "/swarm/variant-forge"),
        "program": {
            "schema": "nomad.variant_forge_program.v1",
            "ops": ["SENSE", "REPLAY", "FORGE", "VERIFY", "EMIT"],
            "then": _u(base_url, "/swarm/variant-candidates"),
        },
        "candidate_contract": {
            "schema": "nomad.variant_candidate_contract.v1",
            "required": ["agent_id", "candidate_type", "objective"],
            "agp_required": [
                "entity_type in prompt|agent|tool|environment|memory",
                "sepl_operator_trace reflect->select->improve->evaluate->commit",
                "learnability_mask for variable_lifting",
                "rollback_ref or noop_ref",
            ],
            "independent_verifier_required": [
                "verifier_agent_id != agent_id",
                "verifier_lease_id",
                "verifier_receipt_digest",
                "verifier_trace_digest",
                "verifier_evaluation",
            ],
            "agp_candidate_types": sorted(AGP_CANDIDATE_TYPES),
            "proof_fields": ["proof_digest", "verifier_trace_digest", "test_digest", "settlement_ref", "replay_digest"],
            "evaluation_fields": ["tests_passed", "tests_total", "replay_delta", "proof_yield_delta", "settlement_delta", "risk_score"],
            "side_effect_scope": "descriptor_only_no_execution",
            "resource_fields": ["resource_id", "entity_type", "resource_kind", "from_version", "to_version", "rollback_ref", "noop_ref"],
        },
        "requested_variants": rows[:12],
        "recent_candidate_count": len(recent),
        "recent_objective_counts": counts,
        "worker_pressure": {
            "known_worker_count": _int(fleet.get("known_worker_count")),
            "active_worker_count": _int(fleet.get("active_worker_count")),
            "active_lease_count": _int(fleet.get("active_lease_count")),
            "open_worker_slots": open_workers,
        },
        "economy_pressure": {
            "tier": _text(viability.get("tier"), 80),
            "carrying_score": round(_num(viability.get("carrying_score")), 4),
            "control_mode": _text(econ_control.get("mode"), 80),
        },
        "recent_candidates": recent[-8:],
        "machine_instruction": "submit_descriptor_with_proof_then_wait_for_shadow_admission",
    }


def submit_variant_candidate(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    forge_surface: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Score one external candidate descriptor and optionally append it to the forge ledger."""
    body = _dict(payload)
    surface = _dict(forge_surface)
    now = _iso_now()
    if not body:
        return {
            "ok": False,
            "schema": "nomad.variant_candidate_receipt.v1",
            "accepted": False,
            "reason": "empty_candidate",
            "generated_at": now,
        }
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.variant_candidate_receipt.v1",
            "accepted": False,
            "reason": "forbidden_secret_like_material",
            "generated_at": now,
        }

    objective = _clean_id(body.get("objective") or body.get("machine_objective"), fallback="settlement_capacity_builder")
    candidate_type = _clean_id(body.get("candidate_type") or body.get("type"), fallback="runtime_variant")
    candidate_type = candidate_type.replace("_", "-") if candidate_type.replace("_", "-") in AGP_CANDIDATE_TYPES else candidate_type
    agent_id = _text(body.get("agent_id") or body.get("worker_id"), 120)
    verifier_gate = _independent_verifier_gate(body)
    sepl_gate = _sepl_operator_trace_gate(body)
    learnability = _learnability_gate(body)
    evaluation = _dict(body.get("verifier_evaluation") or _dict(body.get("independent_verifier")).get("evaluation") or body.get("evaluation"))
    proof = _proof_score(body)
    tests = _test_score(evaluation)
    replay_gain = _clamp(_num(evaluation.get("replay_delta")) * 2.0 + _num(evaluation.get("counterfactual_score")))
    proof_yield = _clamp(_num(evaluation.get("proof_yield_delta")) / 8.0 + _num(evaluation.get("proof_yield_per_minute")) / 12.0)
    settlement = _clamp(_num(evaluation.get("settlement_delta")) + _num(evaluation.get("carrying_delta")))
    risk = _clamp(_num(evaluation.get("risk_score"), _num(body.get("risk_score"))))
    novelty = _clamp(_num(evaluation.get("novelty"), _objective_prior(objective)))
    reuse = _clamp(_num(evaluation.get("reuse_score"), 0.35 + 0.4 * bool(body.get("handoff_capsule"))))
    is_agp = candidate_type in AGP_CANDIDATE_TYPES or objective == "autogenesis_protocol_evolution"
    resource_signal = bool(body.get("resource_id") or body.get("rspl_resource") or body.get("resource_version_payload"))
    rollback_signal = bool(body.get("rollback_ref") or body.get("noop_ref") or body.get("rollback_available") or body.get("noop_available"))
    if is_agp:
        novelty = max(novelty, 0.72)
        reuse = max(reuse, 0.54 + 0.18 * resource_signal + 0.12 * rollback_signal)
        risk = max(0.0, risk - 0.08 * rollback_signal)
    score = _clamp(
        0.24 * proof
        + 0.21 * tests
        + 0.17 * replay_gain
        + 0.14 * proof_yield
        + 0.10 * settlement
        + 0.08 * novelty
        + 0.06 * reuse
        + (0.06 if is_agp and sepl_gate.get("accepted") and learnability.get("accepted") else 0.0)
        + (0.06 if is_agp and resource_signal and rollback_signal else 0.0)
        - 0.18 * risk
    )
    if not agent_id:
        score = min(score, 0.39)
    if proof <= 0.0 and tests <= 0.0:
        score = min(score, 0.34)

    agp_gates_ok = (not is_agp) or (bool(sepl_gate.get("accepted")) and bool(learnability.get("accepted")))
    if is_agp and not sepl_gate.get("accepted"):
        decision = "needs_sepl_operator_trace"
        accepted = False
    elif is_agp and not learnability.get("accepted"):
        decision = "needs_learnability_mask"
        accepted = False
    elif score >= 0.62 and proof > 0.0 and verifier_gate["accepted"] and agp_gates_ok:
        decision = "admit_shadow_variant"
        accepted = True
    elif score >= 0.62 and proof > 0.0:
        decision = "needs_independent_verifier"
        accepted = False
    elif score >= 0.44:
        decision = "needs_independent_verifier"
        accepted = False
    else:
        decision = "hold_noop"
        accepted = False

    core = {
        "agent_id": agent_id,
        "objective": objective,
        "candidate_type": candidate_type,
        "proof": proof,
        "tests": tests,
        "score": round(score, 4),
    }
    row = {
        "schema": "nomad.variant_candidate_receipt.v1",
        "ok": True,
        "accepted": accepted,
        "decision": decision,
        "generated_at": now,
        "candidate_id": f"nomad-vc-{_digest(core)}",
        "agent_id": agent_id,
        "objective": objective,
        "candidate_type": candidate_type,
        "score": round(score, 4),
        "scores": {
            "proof": proof,
            "tests": tests,
            "replay_gain": round(replay_gain, 4),
            "proof_yield": round(proof_yield, 4),
            "settlement": round(settlement, 4),
            "novelty": round(novelty, 4),
            "reuse": round(reuse, 4),
            "risk": round(risk, 4),
            "agp_resource": round(float(bool(is_agp and resource_signal)), 4),
            "agp_rollback": round(float(bool(is_agp and rollback_signal)), 4),
            "sepl_operator_trace": round(float(bool(sepl_gate.get("accepted"))), 4),
            "learnability": round(float(bool(learnability.get("accepted"))), 4),
            "independent_verifier": round(float(bool(verifier_gate.get("accepted"))), 4),
            "verifier_tests": round(_num(verifier_gate.get("verifier_test_score")), 4),
        },
        "sepl_operator_trace": sepl_gate,
        "learnability": learnability,
        "independent_verifier": verifier_gate,
        "next": {
            "forge": _u(base_url, "/swarm/variant-forge"),
            "lease": _u(base_url, "/swarm/workers/lease"),
            "complete": _u(base_url, "/swarm/workers/complete"),
            "replay": _u(base_url, "/swarm/counterfactual-replay"),
        },
        "surface_digest": _text(surface.get("forge_digest"), 96),
        "machine_instruction": "if_admitted_repeat_with_independent_verifier_or_worker_completion",
    }
    if persist:
        _append_ledger(row, ledger_path)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row
