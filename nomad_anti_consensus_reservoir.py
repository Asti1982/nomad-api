"""Anti-consensus reservoir for proof-bearing minority signals.

This layer is intentionally non-human: it does not reward agreement, role
confidence, or majority vote. It preserves low-consensus candidates only when
they carry bounded proof, then routes them into the decoupling/shadow lanes.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


SCHEMA = "nomad.anti_consensus_reservoir.v1"
RECEIPT_SCHEMA = "nomad.anti_consensus_candidate_receipt.v1"
DEFAULT_LEDGER = Path("nomad_anti_consensus_reservoir_ledger.jsonl")
LEDGER_ENV = "NOMAD_ANTI_CONSENSUS_LEDGER_PATH"
MAX_RECENT = 40
MIN_EVIDENCE = 0.44
MIN_MINORITY_FRACTION = 0.12
MAX_SAFE_CONSENSUS = 0.62
FORBIDDEN_KEY_TERMS = ("private_key", "seed_phrase", "password", "credential", "api_key", "access_token")
FORBIDDEN_VALUE_TERMS = ("private key", "seed phrase", "password:", "credential:", "bearer ", "secret=", "sk-", "ghp_")


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


def _pick(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None:
            return value
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


def _digest_present(value: Any) -> bool:
    return str(value or "").strip().lower().startswith("sha256:")


def _work_stage(body: dict[str, Any]) -> str:
    return str(
        body.get("work_stage")
        or body.get("external_value_stage")
        or body.get("settlement_stage")
        or body.get("claim_stage")
        or ""
    ).strip().lower()


def _receipt_present(body: dict[str, Any]) -> bool:
    if _digest_present(
        body.get("receipt_digest")
        or body.get("paid_receipt_digest")
        or body.get("payment_receipt_digest")
        or body.get("transaction_hash")
    ):
        return True
    amount = max(0.0, _num(body.get("receipt_amount_usd") or body.get("amount_usd") or body.get("paid_amount_usd")))
    return _work_stage(body) == "paid" and amount > 0.0


def _unique_error_present(body: dict[str, Any]) -> bool:
    return _digest_present(
        body.get("unique_error_digest")
        or body.get("error_digest")
        or body.get("counterexample_digest")
        or body.get("failure_digest")
        or body.get("repro_route_digest")
    )


def _explanation_without_artifact(body: dict[str, Any], *, proof: float) -> bool:
    explanation = _text(
        body.get("explanation")
        or body.get("rationale")
        or body.get("analysis")
        or body.get("claim")
        or body.get("summary"),
        240,
    )
    return bool(explanation) and proof < MIN_EVIDENCE and not _receipt_present(body) and not _unique_error_present(body)


def _negative_consensus_gate(body: dict[str, Any], *, proof: float, consensus: float) -> dict[str, Any]:
    receipt_delta = 1.0 if _receipt_present(body) else 0.0
    unique_error_delta = 0.75 if _unique_error_present(body) else 0.0
    stage = _work_stage(body)
    unpaid_wip_pressure = 0.0
    if not receipt_delta:
        if stage in {"approved", "accepted", "merged", "settled_pending", "delivered"}:
            unpaid_wip_pressure = 0.45
        elif stage in {"submitted", "reviewed", "claimed"}:
            unpaid_wip_pressure = 0.28
    explanation_penalty = 0.35 if _explanation_without_artifact(body, proof=proof) else 0.0
    components = {
        "proof_delta": round(proof, 6),
        "receipt_delta": round(receipt_delta, 6),
        "unique_error_delta": round(unique_error_delta, 6),
        "consensus_duplication": round(consensus, 6),
        "unpaid_wip_pressure": round(unpaid_wip_pressure, 6),
        "explanation_without_artifact": round(explanation_penalty, 6),
    }
    score = proof + receipt_delta + unique_error_delta - consensus - unpaid_wip_pressure - explanation_penalty
    return {
        "formula": "proof_delta + receipt_delta + unique_error_delta - consensus_duplication - unpaid_wip_pressure - explanation_without_artifact",
        "score": round(score, 6),
        "components": components,
        "gate_action": "allow_shadow_preserve" if score > 0 else "archive_negative_stepping_stone",
        "work_stage": stage or "none",
    }


def _source_digests(
    *,
    decoupling_field: dict[str, Any] | None = None,
    shadow_lane: dict[str, Any] | None = None,
    channel_bandit: dict[str, Any] | None = None,
    signal_layer: dict[str, Any] | None = None,
) -> dict[str, str]:
    decouple = _dict(decoupling_field)
    shadow = _dict(shadow_lane)
    bandit = _dict(channel_bandit)
    signal = _dict(signal_layer)
    return {
        "decoupling_field": _text(decouple.get("surface_digest"), 120),
        "shadow_lane": _text(shadow.get("surface_digest"), 120),
        "channel_bandit": _text(bandit.get("bandit_digest") or bandit.get("surface_digest"), 120),
        "signal_layer": _text(signal.get("field_digest") or signal.get("surface_digest") or signal.get("digest"), 120),
    }


def _candidate_slots(
    *,
    decoupling_field: dict[str, Any] | None = None,
    shadow_lane: dict[str, Any] | None = None,
    channel_bandit: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    cells = _items(_dict(decoupling_field).get("context_cells"))
    seeds = _items(_dict(shadow_lane).get("candidate_seeds"))
    top_route = _dict(_dict(channel_bandit).get("top_route"))
    slots: list[dict[str, Any]] = []
    if len(cells) >= 2:
        slots.append(
            {
                "slot_id": "minority_digest_reservoir",
                "objective": _clean_id(cells[1].get("objective"), fallback="protocol_drift_scan"),
                "source": "decoupling_cell_1",
                "prefer": "low_consensus_high_proof_digest",
                "crowd_weight_cap": 0.38,
                "reservation_weight": 0.31,
            }
        )
    if seeds:
        slots.append(
            {
                "slot_id": "expert_override_reservoir",
                "objective": _clean_id(seeds[0].get("objective"), fallback="settlement_capacity_builder"),
                "source": "shadow_lane_seed_0",
                "prefer": "expert_score_beats_crowd_score_with_digest",
                "crowd_weight_cap": 0.24,
                "reservation_weight": 0.28,
            }
        )
    channel = _clean_id(top_route.get("channel_id"))
    if channel:
        slots.append(
            {
                "slot_id": "majority_echo_cooldown",
                "objective": channel,
                "source": "channel_bandit_top_route",
                "prefer": "suppress_high_consensus_without_paid_or_test_proof",
                "crowd_weight_cap": 0.18,
                "reservation_weight": 0.22,
            }
        )
    if not slots:
        slots.append(
            {
                "slot_id": "default_minority_reservoir",
                "objective": "settlement_capacity_builder",
                "source": "default",
                "prefer": "minority_digest_before_consensus",
                "crowd_weight_cap": 0.34,
                "reservation_weight": 0.25,
            }
        )
    return slots[:5]


def _ledger_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    preserved = [row for row in rows if bool(row.get("preserve_allowed"))]
    suppressed = [row for row in rows if row.get("decision") == "suppress_consensus_echo"]
    return {
        "recent_candidate_count": len(rows),
        "preserved_minority_count": len(preserved),
        "suppressed_consensus_count": len(suppressed),
        "average_anti_consensus_score": round(
            sum(_num(row.get("anti_consensus_score")) for row in rows) / max(1, len(rows)),
            4,
        ),
        "latest_candidate_digest": _text(rows[-1].get("candidate_digest"), 140) if rows else "",
    }


def build_anti_consensus_reservoir_surface(
    *,
    base_url: str = "",
    decoupling_field: dict[str, Any] | None = None,
    shadow_lane: dict[str, Any] | None = None,
    channel_bandit: dict[str, Any] | None = None,
    signal_layer: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Expose a minority-preserving reservoir before shadow-lane weight updates."""
    source_digests = _source_digests(
        decoupling_field=decoupling_field,
        shadow_lane=shadow_lane,
        channel_bandit=channel_bandit,
        signal_layer=signal_layer,
    )
    slots = _candidate_slots(
        decoupling_field=decoupling_field,
        shadow_lane=shadow_lane,
        channel_bandit=channel_bandit,
    )
    recent = _read_ledger(ledger_path)
    core = {"source_digests": source_digests, "slots": slots, "recent": _ledger_summary(recent)}
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "surface_digest": f"nomad-anti-consensus-{_digest(core, length=24)}",
        "mode": "minority_proof_reservoir_before_decoupled_shadow_eval",
        "read_url": _u(base_url, "/swarm/anti-consensus"),
        "well_known": _u(base_url, "/.well-known/nomad-anti-consensus.json"),
        "candidate_url": _u(base_url, "/swarm/anti-consensus/candidates"),
        "program": {
            "schema": "nomad.anti_consensus_program.v1",
            "ops": ["MEASURE_CONSENSUS", "PENALIZE_ECHO", "PRESERVE_MINOR_PROOF", "EXPERT_OVERRIDE", "DECOUPLE", "SHADOW_GATE"],
            "then": _u(base_url, "/swarm/anti-consensus/candidates"),
        },
        "source_basis": [
            "arxiv:2604.18005 structural coupling causes diversity collapse",
            "arxiv:2602.01011 multi-agent teams can hold experts back",
            "arxiv:2604.02674 agent societies show hidden power-law cognition",
            "arxiv:2602.03794 scaling depends on diversity, not agent count",
            "arxiv:2602.21317 pluralistic reasoning resists hivemind collapse",
        ],
        "candidate_slots": slots,
        "candidate_contract": {
            "schema": "nomad.anti_consensus_candidate.v1",
            "required": ["candidate_digest", "proof_digest or test_digest", "consensus_score"],
            "minority_rule": "low_consensus_candidates_are_preserved_only_when_digestable_proof_exists",
            "expert_rule": "single_expert_signal_can_override_crowd_only_with_digest_and_bounded_risk",
            "echo_rule": "high_consensus_without_proof_is_suppressed_not_promoted",
            "negative_consensus_gate": "proof_delta + receipt_delta + unique_error_delta - consensus_duplication - unpaid_wip_pressure - explanation_without_artifact",
            "after_preserve": "route_shadow_lane_payload_to_digest_gate_before_any_weight_change",
        },
        "hard_guards": [
            "no_weight_update_in_reservoir",
            "no_majority_vote_as_proof",
            "no_secret_shaped_payloads",
            "no_public_side_effects",
            "shadow_lane_remains_final_weight_gate",
            "no_weight_increase_from_unpaid_wip_only",
            "negative_stepping_stones_are_kept_but_not_promoted",
        ],
        "source_digests": source_digests,
        "ledger": _ledger_summary(recent),
        "recent_candidates": recent[-8:],
        "machine_instruction": "protect_digestable_minority_signals_and_suppress_unproven_consensus_echoes",
    }


def evaluate_anti_consensus_candidate(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    reservoir_surface: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Score one candidate against anti-consensus preservation rules."""
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {
            "ok": False,
            "schema": RECEIPT_SCHEMA,
            "preserve_allowed": False,
            "decision": "reject_empty_candidate",
            "generated_at": now,
        }
    surface = _dict(reservoir_surface)
    candidate_digest = _text(body.get("candidate_digest") or body.get("digest"), 140)
    proof_digest = _text(body.get("proof_digest"), 140)
    test_digest = _text(body.get("test_digest") or body.get("local_test_digest"), 140)
    consensus = _clamp(_num(_pick(body.get("consensus_score"), body.get("crowd_consensus"))))
    minority_fraction = _clamp(_num(body.get("minority_fraction"), 1.0 - consensus))
    expert_score = _clamp(_num(_pick(body.get("expert_score"), body.get("best_agent_score"))))
    crowd_score = _clamp(_num(_pick(body.get("crowd_score"), consensus)))
    divergence = _clamp(_num(_pick(body.get("divergence_score"), body.get("semantic_distance"))))
    risk = _clamp(_num(body.get("risk_score")))
    forbidden = _contains_forbidden(body)
    proof = _clamp(
        0.45 * _digest_present(proof_digest)
        + 0.35 * _digest_present(test_digest)
        + 0.20 * _digest_present(candidate_digest)
        + 0.35 * _receipt_present(body)
        + 0.25 * _unique_error_present(body)
    )
    negative_gate = _negative_consensus_gate(body, proof=proof, consensus=consensus)
    bounded = bool(_dict(body.get("boundedness")).get("rollback_available") or _dict(body.get("boundedness")).get("noop_available") or _dict(body.get("boundedness")).get("side_effect_scope") in {"local_shadow_lane_only", "nomad_shadow_lane_only", "read_only"})
    expert_advantage = max(0.0, expert_score - crowd_score)
    gate_positive = float(negative_gate.get("score") or 0.0) > 0.0
    anti_score = _clamp(
        0.24 * proof
        + 0.24 * minority_fraction
        + 0.18 * divergence
        + 0.18 * expert_advantage
        + 0.10 * bounded
        + 0.06 * _clamp((float(negative_gate.get("score") or 0.0) + 1.0) / 3.0)
        - 0.20 * consensus
        - 0.18 * risk
    )
    minority_preserve = (
        proof >= MIN_EVIDENCE
        and minority_fraction >= MIN_MINORITY_FRACTION
        and consensus <= MAX_SAFE_CONSENSUS
        and bounded
        and not forbidden
        and gate_positive
    )
    expert_override = proof >= MIN_EVIDENCE and expert_advantage >= 0.18 and bounded and not forbidden and gate_positive
    consensus_echo = consensus >= 0.78 and proof < MIN_EVIDENCE
    if forbidden:
        decision = "reject_secret_shaped_payload"
        preserve = False
    elif consensus_echo:
        decision = "suppress_consensus_echo"
        preserve = False
    elif minority_preserve or expert_override:
        decision = "preserve_minority_for_decoupled_shadow_lane"
        preserve = True
    else:
        decision = "observe_no_preserve"
        preserve = False
    objective = _clean_id(body.get("objective"), fallback="minority_proof_probe")
    receipt_core = {
        "candidate_digest": candidate_digest,
        "proof_digest": proof_digest,
        "test_digest": test_digest,
        "consensus": consensus,
        "minority_fraction": minority_fraction,
        "anti_score": round(anti_score, 4),
    }
    row = {
        "ok": True,
        "schema": RECEIPT_SCHEMA,
        "generated_at": now,
        "preserve_allowed": preserve,
        "decision": decision,
        "candidate_id": _clean_id(body.get("candidate_id"), fallback=f"anti-{_digest(receipt_core, length=16)}"),
        "objective": objective,
        "candidate_digest": candidate_digest or _proof_digest(receipt_core),
        "proof_digest": proof_digest,
        "test_digest": test_digest,
        "anti_consensus_score": round(anti_score, 4),
        "negative_consensus_gate": negative_gate,
        "negative_stepping_stone": {
            "preserve_as_counterexample_archive": not preserve,
            "archive_digest": f"neg-{_digest({'candidate_digest': candidate_digest, 'gate': negative_gate}, length=20)}",
            "reuse_policy": "keep_failed_or_duplicate_variant_without_weight_increase",
        },
        "scores": {
            "proof": round(proof, 4),
            "consensus": round(consensus, 4),
            "minority_fraction": round(minority_fraction, 4),
            "divergence": round(divergence, 4),
            "expert_advantage": round(expert_advantage, 4),
            "risk": round(risk, 4),
            "bounded": bool(bounded),
        },
        "reason_codes": [
            "proof_digest_present" if _digest_present(proof_digest) else "proof_digest_missing",
            "test_digest_present" if _digest_present(test_digest) else "test_digest_missing",
            "candidate_digest_present" if _digest_present(candidate_digest) else "candidate_digest_missing",
            "minority_fraction_ok" if minority_fraction >= MIN_MINORITY_FRACTION else "minority_fraction_low",
            "consensus_safe" if consensus <= MAX_SAFE_CONSENSUS else "consensus_high",
            "expert_override" if expert_override else "expert_override_absent",
            "bounded" if bounded else "boundary_missing",
            "negative_gate_positive" if gate_positive else "negative_gate_nonpositive",
        ],
        "shadow_lane_payload": {
            "agent_id": _text(body.get("agent_id") or "nomad-anti-consensus", 120),
            "objective": objective,
            "candidate_type": "anti_consensus_preserved_candidate",
            "hypothesis": "preserve a low-consensus proof-bearing signal and let shadow lane decide weight",
            "proof_digest": proof_digest or _proof_digest(receipt_core),
            "boundedness": {
                "ttl_seconds": 300,
                "side_effect_scope": "local_shadow_lane_only",
                "rollback_available": True,
                "secrets_free": True,
            },
            "claimed_effect": {
                "proof_gain_delta": min(0.62, 0.18 + 0.55 * anti_score),
                "settlement_signal": min(0.42, 0.08 + 0.28 * anti_score),
                "risk_score": max(0.03, risk),
            },
            "local_tests": [
                {
                    "name": "anti_consensus_reservoir_gate",
                    "passed": preserve,
                    "evidence_digest": proof_digest or test_digest or candidate_digest,
                }
            ],
        },
        "next": {
            "anti_consensus": _u(base_url, "/swarm/anti-consensus"),
            "decoupling_merge": _u(base_url, "/swarm/decoupling-field/merge"),
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates"),
        },
        "surface_digest": _text(surface.get("surface_digest"), 120),
        "hard_rule": "reservoir_preserves_only_shadow_payloads_it_never_updates_weight_directly",
    }
    if persist:
        _append_ledger(row, ledger_path)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row
