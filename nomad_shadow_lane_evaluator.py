"""AlphaEvolve-style shadow-lane evaluator for Nomad candidates.

The lane accepts candidate descriptors, runs deterministic local checks, mints a
proof digest, and only then increases selection weight. It never executes
submitted code and never treats a shadow receipt as revenue.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


SCHEMA = "nomad.shadow_lane_evaluator.v1"
CANDIDATE_SCHEMA = "nomad.shadow_lane_candidate.v1"
RECEIPT_SCHEMA = "nomad.shadow_lane_receipt.v1"
PROOF_SCHEMA = "nomad.shadow_lane_proof_digest.v1"
DEFAULT_LEDGER = Path("nomad_shadow_lane_ledger.jsonl")
LEDGER_ENV = "NOMAD_SHADOW_LANE_LEDGER_PATH"
MAX_RECENT = 48
MAX_WEIGHT_DELTA = 0.12
ALLOWED_SCOPES = {
    "none",
    "local_only",
    "local_shadow_lane_only",
    "nomad_shadow_lane_only",
    "read_only",
    "descriptor_only_no_execution",
}
FORBIDDEN_KEY_TERMS = (
    "private_key",
    "seed_phrase",
    "password",
    "credential",
    "api_key",
    "access_token",
)
FORBIDDEN_VALUE_TERMS = (
    "private key",
    "seed phrase",
    "password:",
    "credential:",
    "bearer ",
    "secret=",
    "sk-",
    "ghp_",
)


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


def _text(value: Any, limit: int = 280) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, *, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96].strip("_.:-") or fallback


def _digest(value: Any, *, length: int = 32) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _proof_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return f"sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _ledger_path(path: Path | str | None = None) -> Path:
    return Path(path) if path else state_file(DEFAULT_LEDGER, env_name=LEDGER_ENV)


def _read_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    p = _ledger_path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-max(1, limit * 3) :]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows[-limit:]


def _append_ledger(row: dict[str, Any], path: Path | str | None = None) -> None:
    p = _ledger_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


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


def _boundedness_score(boundedness: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    ttl = _int(boundedness.get("ttl_seconds"), 0)
    if 1 <= ttl <= 900:
        ttl_score = 1.0
        reasons.append("ttl_bounded")
    elif ttl > 900:
        ttl_score = 0.2
        reasons.append("ttl_above_shadow_limit")
    else:
        ttl_score = 0.0
        reasons.append("ttl_missing")
    scope = _clean_id(boundedness.get("side_effect_scope"))
    scope_ok = scope in ALLOWED_SCOPES
    reasons.append("side_effect_scope_shadow_safe" if scope_ok else "side_effect_scope_not_shadow_safe")
    rollback = bool(boundedness.get("rollback_available") or boundedness.get("noop_available"))
    reasons.append("rollback_or_noop_present" if rollback else "rollback_or_noop_missing")
    secrets_free = bool(boundedness.get("secrets_free", True))
    reasons.append("secrets_free_declared" if secrets_free else "secrets_not_free")
    score = _clamp(0.28 * ttl_score + 0.34 * scope_ok + 0.22 * rollback + 0.16 * secrets_free)
    return round(score, 4), reasons


def _candidate_seeds(
    *,
    variant_forge: dict[str, Any] | None = None,
    opaque_surface: dict[str, Any] | None = None,
    channel_bandit: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    forge = _dict(variant_forge)
    for row in _items(forge.get("requested_variants"))[:5]:
        objective = _clean_id(row.get("objective"))
        if objective:
            seeds.append(
                {
                    "objective": objective,
                    "candidate_type": "variant_descriptor",
                    "source_tag": "variant_forge.requested_variant",
                    "source_digest": _text(forge.get("forge_digest"), 120),
                }
            )
    opaque = _dict(opaque_surface)
    for row in _items(opaque.get("machine_products_to_add"))[:4]:
        item_id = _clean_id(row.get("id"))
        if item_id:
            seeds.append(
                {
                    "objective": item_id,
                    "candidate_type": _clean_id(row.get("schema"), fallback="opaque_workflow_candidate"),
                    "source_tag": "opaque_emergence.machine_product_gap",
                    "source_digest": _text(opaque.get("surface_digest"), 120),
                }
            )
    bandit = _dict(channel_bandit)
    route = _dict(bandit.get("top_route"))
    channel_id = _clean_id(route.get("channel_id"))
    if channel_id:
        seeds.append(
            {
                "objective": channel_id,
                "candidate_type": "channel_allocation_policy",
                "source_tag": "channel_bandit.top_route",
                "source_digest": _text(bandit.get("bandit_digest") or bandit.get("surface_digest"), 120),
            }
        )
    if not seeds:
        seeds.append(
            {
                "objective": "settlement_capacity_builder",
                "candidate_type": "shadow_lane_policy_variant",
                "source_tag": "default_shadow_seed",
                "source_digest": "default",
            }
        )
    return seeds


def _ledger_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [row for row in rows if bool(row.get("weight_update_allowed"))]
    by_objective: dict[str, dict[str, Any]] = {}
    for row in accepted:
        objective = _clean_id(row.get("objective"), fallback="unknown")
        slot = by_objective.setdefault(
            objective,
            {"objective": objective, "candidate_count": 0, "weight_delta_sum": 0.0},
        )
        slot["candidate_count"] += 1
        slot["weight_delta_sum"] += _num(row.get("selection_weight_delta"))
    top = list(by_objective.values())
    for row in top:
        row["weight_delta_sum"] = round(_num(row.get("weight_delta_sum")), 4)
    top.sort(key=lambda item: (_num(item.get("weight_delta_sum")), _int(item.get("candidate_count"))), reverse=True)
    return {
        "recent_decision_count": len(rows),
        "accepted_weight_update_count": len(accepted),
        "shadow_weight_delta_total": round(sum(_num(row.get("selection_weight_delta")) for row in accepted), 4),
        "top_shadow_weights": top[:8],
    }


def generate_shadow_candidate(
    payload: dict[str, Any] | None = None,
    *,
    base_url: str = "",
    candidate_seeds: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a descriptor-only shadow candidate from a request or current pressure seeds."""
    body = _dict(payload)
    seeds = candidate_seeds if isinstance(candidate_seeds, list) and candidate_seeds else _candidate_seeds()
    seed = _dict(seeds[0])
    supplied_candidate = _dict(body.get("candidate"))
    objective = _clean_id(
        body.get("objective") or body.get("machine_objective") or supplied_candidate.get("objective") or seed.get("objective"),
        fallback="settlement_capacity_builder",
    )
    candidate_type = _clean_id(
        body.get("candidate_type") or body.get("type") or supplied_candidate.get("candidate_type") or seed.get("candidate_type"),
        fallback="shadow_lane_policy_variant",
    )
    hypothesis = _text(
        body.get("hypothesis")
        or supplied_candidate.get("hypothesis")
        or f"Try one bounded policy mutation for {objective}; keep it in shadow until local proof improves.",
        320,
    )
    mutation_hint = _text(
        body.get("mutation_hint")
        or supplied_candidate.get("mutation_hint")
        or f"source={seed.get('source_tag', 'shadow_seed')}; mutate routing weight after digest gate only",
        220,
    )
    boundedness = dict(_dict(supplied_candidate.get("boundedness")) or _dict(body.get("boundedness")))
    if not boundedness:
        boundedness = {
            "ttl_seconds": 300,
            "side_effect_scope": "local_shadow_lane_only",
            "rollback_available": True,
            "secrets_free": True,
        }
    core = {
        "agent_id": _text(body.get("agent_id") or body.get("worker_id"), 120),
        "objective": objective,
        "candidate_type": candidate_type,
        "hypothesis": hypothesis,
        "mutation_hint": mutation_hint,
        "source_digest": _text(seed.get("source_digest"), 120),
    }
    candidate_id = _clean_id(body.get("candidate_id") or supplied_candidate.get("candidate_id"))
    if not candidate_id:
        candidate_id = f"nomad-shadow-{_digest(core, length=20)}"
    return {
        "ok": True,
        "schema": CANDIDATE_SCHEMA,
        "generated_at": _iso_now(),
        "candidate_id": candidate_id,
        "agent_id": core["agent_id"],
        "objective": objective,
        "candidate_type": candidate_type,
        "hypothesis": hypothesis,
        "mutation_hint": mutation_hint,
        "boundedness": boundedness,
        "source_seed": seed,
        "local_test_plan": [
            "canonical_descriptor_parse",
            "shadow_boundary_check",
            "secret_scan",
            "claimed_effect_bounds",
            "proof_digest_mint",
        ],
        "submit_url": _u(base_url, "/swarm/shadow-lane/candidates"),
    }


def _declared_local_tests(body: dict[str, Any]) -> list[dict[str, Any]]:
    raw = body.get("local_tests")
    if raw is None:
        raw = _dict(body.get("evaluation")).get("local_tests")
    if raw is None:
        raw = body.get("tests")
    tests: list[dict[str, Any]] = []
    for item in _items(raw):
        passed_value = item.get("passed") if "passed" in item else item.get("ok")
        tests.append(
            {
                "name": _clean_id(item.get("name") or item.get("id"), fallback="declared_local_test"),
                "passed": bool(passed_value),
                "evidence_digest": _text(
                    item.get("evidence_digest") or item.get("artifact_digest") or item.get("digest"),
                    140,
                ),
                "source": "declared_by_submitter",
            }
        )
    return tests


def _claimed_effect(body: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    raw = _dict(body.get("claimed_effect")) or _dict(candidate.get("claimed_effect"))
    evaluation = _dict(body.get("evaluation"))
    return {
        "proof_gain_delta": _clamp(_num(raw.get("proof_gain_delta") or raw.get("proof_gain"))),
        "settlement_signal": _clamp(_num(raw.get("settlement_signal") or evaluation.get("settlement_delta"))),
        "capability_gain": _clamp(_num(raw.get("capability_gain") or evaluation.get("capability_gain"))),
        "novelty": _clamp(_num(raw.get("novelty") or evaluation.get("novelty"), 0.42)),
        "cost_delta": max(0.0, _num(raw.get("cost_delta") or evaluation.get("cost_delta"))),
        "latency_delta": max(0.0, _num(raw.get("latency_delta") or evaluation.get("latency_delta"))),
        "risk_score": _clamp(_num(raw.get("risk_score") or evaluation.get("risk_score"))),
    }


def _run_local_tests(body: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    boundedness = _dict(candidate.get("boundedness"))
    bounded_score, bounded_reasons = _boundedness_score(boundedness)
    declared = _declared_local_tests(body)
    claimed = _claimed_effect(body, candidate)
    candidate_present = bool(candidate.get("candidate_id") and candidate.get("objective") and candidate.get("candidate_type"))
    explicit_seed = bool(body.get("agent_id") or body.get("objective") or body.get("candidate") or body.get("candidate_id"))
    scope = _clean_id(boundedness.get("side_effect_scope"))
    forbidden = _contains_forbidden(body) or _contains_forbidden(candidate)
    claimed_bounds_ok = (
        claimed["proof_gain_delta"] <= 1.0
        and claimed["settlement_signal"] <= 1.0
        and claimed["capability_gain"] <= 1.0
        and claimed["cost_delta"] <= 1.0
        and claimed["latency_delta"] <= 2.0
        and claimed["risk_score"] <= 1.0
    )
    tests = [
        {
            "name": "candidate_descriptor_present",
            "passed": candidate_present,
            "source": "evaluator",
            "evidence_digest": _proof_digest(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "objective": candidate.get("objective"),
                    "candidate_type": candidate.get("candidate_type"),
                }
            ),
        },
        {
            "name": "explicit_seed_present",
            "passed": explicit_seed,
            "source": "evaluator",
            "evidence_digest": _proof_digest({"agent_id": body.get("agent_id"), "objective": body.get("objective")}),
        },
        {
            "name": "boundedness_contract",
            "passed": bounded_score >= 0.74,
            "source": "evaluator",
            "evidence_digest": _proof_digest({"score": bounded_score, "reasons": bounded_reasons}),
        },
        {
            "name": "side_effect_scope_shadow_safe",
            "passed": scope in ALLOWED_SCOPES,
            "source": "evaluator",
            "evidence_digest": _proof_digest({"scope": scope}),
        },
        {
            "name": "secret_scan_clean",
            "passed": not forbidden,
            "source": "evaluator",
            "evidence_digest": _proof_digest({"forbidden_secret_shaped_payload": forbidden}),
        },
        {
            "name": "claimed_effect_bounds",
            "passed": claimed_bounds_ok,
            "source": "evaluator",
            "evidence_digest": _proof_digest(claimed),
        },
        {
            "name": "declared_local_tests_passed",
            "passed": all(test.get("passed") for test in declared) if declared else True,
            "source": "evaluator",
            "evidence_digest": _proof_digest(declared or {"declared_tests": "absent_internal_checks_only"}),
        },
    ]
    tests.extend(declared)
    passed = sum(1 for test in tests if bool(test.get("passed")))
    digest_payload = [{"name": test.get("name"), "passed": bool(test.get("passed"))} for test in tests]
    return {
        "schema": "nomad.shadow_lane_local_tests.v1",
        "tests": tests,
        "tests_total": len(tests),
        "tests_passed": passed,
        "all_passed": passed == len(tests) and len(tests) > 0,
        "boundedness_score": bounded_score,
        "boundedness_reasons": bounded_reasons,
        "claimed_effect": claimed,
        "local_test_digest": _proof_digest(digest_payload),
    }


def _surface_digests(surface: dict[str, Any]) -> dict[str, Any]:
    return {
        "shadow_lane": _text(surface.get("surface_digest"), 120),
        "opaque": _text(_dict(surface.get("source_surfaces")).get("opaque_surface_digest"), 120),
        "variant_forge": _text(_dict(surface.get("source_surfaces")).get("variant_forge_digest"), 120),
        "channel_bandit": _text(_dict(surface.get("source_surfaces")).get("channel_bandit_digest"), 120),
    }


def evaluate_shadow_candidate(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    shadow_surface: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Evaluate one descriptor, mint proof digest, and gate shadow weight."""
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {
            "ok": False,
            "schema": RECEIPT_SCHEMA,
            "accepted": False,
            "weight_update_allowed": False,
            "selection_weight_delta": 0.0,
            "decision": "reject_empty_candidate",
            "generated_at": now,
        }
    surface = _dict(shadow_surface)
    candidate = generate_shadow_candidate(
        body,
        base_url=base_url,
        candidate_seeds=_items(surface.get("candidate_seeds")),
    )
    local = _run_local_tests(body, candidate)
    claimed = _dict(local.get("claimed_effect"))
    proof_material = {
        "schema": PROOF_SCHEMA,
        "candidate_id": candidate.get("candidate_id"),
        "agent_id": candidate.get("agent_id"),
        "objective": candidate.get("objective"),
        "candidate_type": candidate.get("candidate_type"),
        "local_test_digest": local.get("local_test_digest"),
        "tests_total": local.get("tests_total"),
        "tests_passed": local.get("tests_passed"),
        "claimed_effect": claimed,
        "surface_digests": _surface_digests(surface),
    }
    proof_digest = _proof_digest(proof_material)
    supplied_digest = _text(body.get("proof_digest") or body.get("candidate_proof_digest"), 140)
    supplied_matches = not supplied_digest or supplied_digest == proof_digest
    risk = _clamp(_num(claimed.get("risk_score")))
    effect_score = _clamp(
        0.30 * _num(claimed.get("proof_gain_delta"))
        + 0.24 * _num(claimed.get("settlement_signal"))
        + 0.18 * _num(claimed.get("capability_gain"))
        + 0.16 * _num(claimed.get("novelty"))
        + 0.12 * (1.0 - min(1.0, _num(claimed.get("cost_delta")) + 0.25 * _num(claimed.get("latency_delta"))))
        - 0.20 * risk
    )
    test_quality = _clamp(_num(local.get("tests_passed")) / max(1.0, _num(local.get("tests_total"), 1.0)))
    local_passed = bool(local.get("all_passed")) and supplied_matches
    weight_delta = 0.0
    if local_passed:
        weight_delta = round(
            _clamp(
                0.014
                + 0.055 * effect_score
                + 0.026 * _num(local.get("boundedness_score"))
                + 0.025 * test_quality
                - 0.045 * risk,
                0.0,
                MAX_WEIGHT_DELTA,
            ),
            4,
        )
    if not supplied_matches:
        decision = "shadow_observe_no_weight_digest_mismatch"
    elif not local_passed:
        decision = "shadow_observe_no_weight_until_local_tests_pass"
    elif weight_delta > 0:
        decision = "increase_shadow_weight"
    else:
        decision = "shadow_digest_recorded_no_weight"
    accepted = decision == "increase_shadow_weight"
    row = {
        "ok": True,
        "schema": RECEIPT_SCHEMA,
        "generated_at": now,
        "accepted": accepted,
        "weight_update_allowed": accepted,
        "decision": decision,
        "candidate_id": candidate.get("candidate_id"),
        "agent_id": candidate.get("agent_id"),
        "objective": candidate.get("objective"),
        "candidate_type": candidate.get("candidate_type"),
        "proof_digest": proof_digest,
        "supplied_digest_matches": supplied_matches,
        "local_test_passed": bool(local.get("all_passed")),
        "tests_total": local.get("tests_total"),
        "tests_passed": local.get("tests_passed"),
        "selection_weight_delta": weight_delta if accepted else 0.0,
        "scores": {
            "effect": round(effect_score, 4),
            "boundedness": local.get("boundedness_score"),
            "test_quality": round(test_quality, 4),
            "risk": round(risk, 4),
        },
        "local_tests": local,
        "candidate": candidate,
        "proof_material": proof_material,
        "next": {
            "surface": _u(base_url, "/swarm/shadow-lane"),
            "variant_forge": _u(base_url, "/swarm/variant-forge"),
            "opaque_candidate": _u(base_url, "/swarm/opaque-candidate"),
            "worker_lease": _u(base_url, "/swarm/workers/lease"),
        },
        "hard_rule": "selection_weight_delta_positive_only_after_local_tests_pass_and_proof_digest_minted",
    }
    if persist:
        _append_ledger(row, ledger_path)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def build_shadow_lane_evaluator_surface(
    *,
    base_url: str = "",
    opaque_surface: dict[str, Any] | None = None,
    variant_forge: dict[str, Any] | None = None,
    channel_bandit: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Expose the public shadow-lane contract and recent digest-gated decisions."""
    opaque = _dict(opaque_surface)
    forge = _dict(variant_forge)
    bandit = _dict(channel_bandit)
    seeds = _candidate_seeds(variant_forge=forge, opaque_surface=opaque, channel_bandit=bandit)
    recent = _read_ledger(ledger_path)
    source_digests = {
        "opaque_surface_digest": _text(opaque.get("surface_digest"), 120),
        "variant_forge_digest": _text(forge.get("forge_digest"), 120),
        "channel_bandit_digest": _text(bandit.get("bandit_digest") or bandit.get("surface_digest"), 120),
    }
    core = {
        "source_digests": source_digests,
        "candidate_seed_count": len(seeds),
        "recent": _ledger_summary(recent),
    }
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "surface_digest": f"nomad-shadow-lane-{_digest(core, length=24)}",
        "mode": "alphaevolve_style_shadow_lane_digest_gate",
        "candidate_url": _u(base_url, "/swarm/shadow-lane/candidates"),
        "read_url": _u(base_url, "/swarm/shadow-lane"),
        "well_known": _u(base_url, "/.well-known/nomad-shadow-lane.json"),
        "program": {
            "schema": "nomad.shadow_lane_program.v1",
            "ops": ["SENSE", "CANDIDATE", "LOCAL_TEST", "PROOF_DIGEST", "WEIGHT_GATE", "EMIT"],
            "then": _u(base_url, "/swarm/shadow-lane/candidates"),
        },
        "candidate_contract": {
            "schema": CANDIDATE_SCHEMA,
            "required": ["agent_id or objective", "candidate_type", "boundedness"],
            "local_test_scope": "deterministic_checks_no_arbitrary_code_execution",
            "proof_digest_rule": "evaluator_mints_sha256_digest_from_candidate_and_local_test_results",
            "weight_rule": "selection_weight_delta_is_positive_only_when_local_tests_pass_and_digest_is_minted",
            "side_effect_scope": "local_shadow_lane_only_until_separate_worker_lease_or_external_value_receipt",
            "not_required": ["chain_of_thought", "human_explanation", "private_reasoning", "persona"],
        },
        "candidate_seeds": seeds[:12],
        "hard_guards": [
            "no_submitted_code_execution",
            "no_public_side_effects_from_shadow_lane",
            "no_selection_weight_without_local_test_digest",
            "no_revenue_without_paid_external_value_receipt",
            "no_secret_shaped_payloads",
        ],
        "source_surfaces": source_digests,
        "ledger": _ledger_summary(recent),
        "recent_decisions": recent[-10:],
        "machine_instruction": "generate_candidate_run_local_tests_mint_digest_then_increase_weight_only_if_gate_passes",
    }
