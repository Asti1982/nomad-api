"""First-round entropy lock-in gates for Nomad.

This module encodes the non-intuitive rule from recent MAS uncertainty work:
do not keep paying for extra agents or extra discussion rounds when first-round
uncertainty already says the single-agent path is cleaner.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from typing import Any


SURFACE_SCHEMA = "nomad.entropy_judger_surface.v1"
DECISION_SCHEMA = "nomad.entropy_judger_decision.v1"
DEFAULT_LOCK_THRESHOLD = 0.62
DEFAULT_QUALITY_MARGIN = 0.025
DEFAULT_PENALTY = 0.55
MAX_RECORDS = 48


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _text(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(out) or math.isinf(out):
        return default
    return out


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _clean_id(value: Any, fallback: str = "record") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:140].strip("_.:/#-") or fallback


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "pass", "passed", "ok", "verified"}


def _probability_entropy(values: Any) -> float | None:
    if not isinstance(values, list):
        return None
    raw = [_num(value, -1.0) for value in values[:256]]
    raw = [value for value in raw if value >= 0.0]
    if len(raw) < 2:
        return None
    total = sum(raw)
    if total <= 1e-12:
        return None
    probs = [value / total for value in raw if value > 1e-12]
    entropy = -sum(p * math.log(p) for p in probs)
    return _clamp(entropy / max(1e-12, math.log(len(raw))))


def _record_entropy(record: dict[str, Any]) -> float:
    for key in (
        "first_round_entropy",
        "round_entropy",
        "trajectory_entropy",
        "mean_token_entropy",
        "token_entropy",
        "entropy",
        "uncertainty",
        "entropy_score",
    ):
        if key in record:
            return _clamp(_num(record.get(key)))
    for key in ("probabilities", "candidate_probabilities", "answer_probabilities"):
        entropy = _probability_entropy(record.get(key))
        if entropy is not None:
            return entropy
    confidence = _num(record.get("confidence") or record.get("certainty"), -1.0)
    if confidence > 1.0:
        confidence = confidence / 100.0
    if confidence >= 0.0:
        return _clamp(1.0 - confidence)
    score = _num(record.get("proof_score") or record.get("score") or record.get("utility_delta"), -1.0)
    if score >= 0.0:
        return _clamp(0.82 - 0.64 * _clamp(score))
    return 0.5


def _proof_strength(record: dict[str, Any]) -> float:
    status = str(
        record.get("verifier_status")
        or record.get("proof_status")
        or record.get("test_status")
        or record.get("receipt_status")
        or ""
    ).strip().lower()
    has_proof = bool(
        _text(
            record.get("proof_digest")
            or record.get("verifier_trace_digest")
            or record.get("test_digest")
            or record.get("receipt_digest")
            or record.get("digest"),
            160,
        )
    )
    passed = _bool(record.get("verifier_passed")) or status in {"passed", "pass", "ok", "verified", "paid", "green"}
    utility = _clamp(_num(record.get("utility_delta") or record.get("proof_gain_delta") or record.get("score")))
    confidence = _num(record.get("confidence") or record.get("certainty"), -1.0)
    if confidence > 1.0:
        confidence = confidence / 100.0
    certainty = _clamp(confidence) if confidence >= 0.0 else _clamp(1.0 - _record_entropy(record))
    return _clamp(0.18 + 0.20 * has_proof + 0.24 * passed + 0.20 * utility + 0.18 * certainty)


def _record_id(record: dict[str, Any], idx: int) -> str:
    return _clean_id(
        record.get("proof_id")
        or record.get("candidate_id")
        or record.get("lane_id")
        or record.get("id")
        or record.get("agent_id")
        or record.get("agent")
        or f"round1-{idx}",
        fallback=f"round1-{idx}",
    )


def _collect_from_keys(body: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for key in keys:
        value = body.get(key)
        if isinstance(value, dict):
            records.append(value)
        else:
            records.extend(_items(value))
    return records[:MAX_RECORDS]


def _collect_first_round(body: dict[str, Any]) -> list[dict[str, Any]]:
    explicit = _collect_from_keys(
        body,
        (
            "first_round_proofs",
            "first_round_candidates",
            "first_round",
            "round1",
            "round_1",
        ),
    )
    if explicit:
        return explicit[:MAX_RECORDS]
    raw = _collect_from_keys(
        body,
        ("proofs", "lanes", "candidate_lanes", "candidates", "reports", "solutions"),
    )
    round_one = [
        record
        for record in raw
        if _int(record.get("round") or record.get("round_index") or record.get("interaction_round"), 1) <= 1
    ]
    return (round_one or raw)[:MAX_RECORDS]


def _mode(record: dict[str, Any]) -> str:
    raw = str(record.get("mode") or record.get("topology") or record.get("architecture") or record.get("source") or "").lower()
    if "single" in raw or raw == "sas":
        return "single"
    if "multi" in raw or raw == "mas" or "committee" in raw or "swarm" in raw:
        return "multi"
    return ""


def _best_quality(records: list[dict[str, Any]], default: float = 0.0) -> float:
    if not records:
        return default
    return max(_proof_strength(record) for record in records)


def evaluate_entropy_judger(
    payload: dict[str, Any] | None,
    *,
    base_url: str = "",
    lock_threshold: float = DEFAULT_LOCK_THRESHOLD,
    quality_margin: float = DEFAULT_QUALITY_MARGIN,
) -> dict[str, Any]:
    """Evaluate first-round entropy and return a SAS/MAS routing decision."""
    body = payload if isinstance(payload, dict) else {}
    records = _collect_first_round(body)
    rows: list[dict[str, Any]] = []
    for idx, record in enumerate(records):
        entropy = _record_entropy(record)
        quality = _proof_strength(record)
        rows.append(
            {
                "record_id": _record_id(record, idx),
                "mode": _mode(record),
                "round": _int(record.get("round") or record.get("round_index") or record.get("interaction_round"), 1),
                "entropy": round(entropy, 6),
                "certainty": round(1.0 - entropy, 6),
                "proof_strength": round(quality, 6),
                "has_verifier_signal": bool(
                    record.get("verifier_passed")
                    or _text(record.get("proof_digest") or record.get("verifier_trace_digest") or record.get("test_digest"), 160)
                ),
            }
        )

    if not rows:
        return {
            "ok": True,
            "schema": DECISION_SCHEMA,
            "generated_at": _iso_now(),
            "objective": _text(body.get("objective") or body.get("target") or "unknown_objective", 180),
            "first_round_count": 0,
            "lock_detected": False,
            "decision": "observe_until_first_round_entropy",
            "base_entropy": 0.0,
            "peak_entropy": 0.0,
            "single_agent_quality": 0.0,
            "mas_quality": 0.0,
            "quality_delta_single_minus_mas": 0.0,
            "routing_adjustment": {
                "topology": "observe_until_first_round_entropy",
                "settlement_pressure_penalty": 0.0,
                "routing_weight_multiplier": 1.0,
                "dti_integration_level": 1.0,
            },
            "reason_codes": ["insufficient_first_round_entropy_evidence"],
            "next": {"evaluate": _u(base_url, "/swarm/entropy-judger/evaluate")},
        }

    entropy_values = [float(row["entropy"]) for row in rows]
    base_entropy = sum(entropy_values) / max(1, len(entropy_values))
    peak_entropy = max(entropy_values)
    entropy_spread = max(entropy_values) - min(entropy_values)
    certainty_preference_score = 1.0 - peak_entropy

    single_records = _collect_from_keys(body, ("single_agent", "single_agent_candidate", "sas_candidate", "sas_candidates"))
    mas_records = _collect_from_keys(body, ("multi_agent", "multi_agent_candidate", "mas_candidate", "mas_candidates"))
    single_records.extend(record for record in records if _mode(record) == "single")
    mas_records.extend(record for record in records if _mode(record) == "multi")

    explicit_single = body.get("single_agent_quality") or body.get("sas_quality")
    explicit_mas = body.get("mas_quality") or body.get("multi_agent_quality")
    single_quality = _clamp(_num(explicit_single, -1.0)) if explicit_single is not None else _best_quality(single_records, 0.0)
    mas_quality = _clamp(_num(explicit_mas, -1.0)) if explicit_mas is not None else _best_quality(mas_records, 0.0)
    if single_quality <= 0.0 and not single_records and len(records) == 1:
        single_quality = max(float(row["proof_strength"]) for row in rows)
    if mas_quality <= 0.0 and not mas_records:
        mas_quality = max((float(row["proof_strength"]) for row in rows if row["mode"] == "multi"), default=0.0)

    quality_delta = single_quality - mas_quality
    round_count = _int(body.get("round_count") or body.get("rounds") or body.get("max_rounds"), 1)
    task = str(body.get("task_type") or body.get("objective") or "").lower()
    math_or_qa = any(token in task for token in ("math", "qa", "knowledge", "gsm", "answer", "reason"))
    lock_score = _clamp(
        0.40 * base_entropy
        + 0.22 * peak_entropy
        + 0.20 * max(0.0, quality_delta)
        + 0.10 * _clamp(round_count / 4.0)
        + 0.08 * (1.0 if math_or_qa else 0.0)
    )
    quality_comparable = bool(explicit_single is not None or explicit_mas is not None or single_records or mas_records)
    lock_detected = bool(
        base_entropy >= _clamp(lock_threshold)
        or peak_entropy >= _clamp(lock_threshold + 0.10)
        or (quality_comparable and quality_delta >= _clamp(quality_margin, 0.0, 0.25))
    )

    if lock_detected:
        decision = "single_agent_lock"
        topology = "single_agent_lock"
        reason = "first_round_entropy_lock_in"
        penalty = DEFAULT_PENALTY
        multiplier = 1.0 - penalty
        dti = 0.0
        message_policy = "stop_multi_round_after_round_one_unless_external_proof_improves"
    elif mas_quality > single_quality + quality_margin and base_entropy < lock_threshold:
        decision = "allow_mas_after_round1"
        topology = "bounded_mas_round2"
        reason = "mas_quality_beats_single_with_low_entropy"
        penalty = 0.0
        multiplier = 1.0
        dti = 0.55
        message_policy = "allow_one_digest_round_then_rejudge"
    else:
        decision = "observe_entropy_before_extra_round"
        topology = "round1_digest_hold"
        reason = "first_round_entropy_ambiguous"
        penalty = 0.18
        multiplier = 0.82
        dti = 0.25
        message_policy = "hold_extra_agents_until_entropy_or_verifier_delta_arrives"

    return {
        "ok": True,
        "schema": DECISION_SCHEMA,
        "generated_at": _iso_now(),
        "objective": _text(body.get("objective") or body.get("target") or "unknown_objective", 180),
        "surface_digest": f"nomad-entropy-judger-{_digest({'rows': rows, 'threshold': lock_threshold, 'margin': quality_margin})}",
        "first_round_count": len(rows),
        "lock_detected": lock_detected,
        "decision": decision,
        "base_entropy": round(base_entropy, 6),
        "peak_entropy": round(peak_entropy, 6),
        "entropy_spread": round(entropy_spread, 6),
        "certainty_preference_score": round(certainty_preference_score, 6),
        "lock_threshold": round(_clamp(lock_threshold), 6),
        "single_agent_quality": round(single_quality, 6),
        "mas_quality": round(mas_quality, 6),
        "quality_delta_single_minus_mas": round(quality_delta, 6),
        "lock_score": round(lock_score, 6),
        "first_round_rows": rows,
        "routing_adjustment": {
            "topology": topology,
            "settlement_pressure_penalty": round(penalty, 4),
            "routing_weight_multiplier": round(multiplier, 4),
            "dti_integration_level": round(dti, 4),
            "message_policy": message_policy,
        },
        "principles": {
            "certainty_preference": "peak_entropy_penalizes_more_rounds",
            "base_entropy": "round_one_entropy_sets_default_topology",
            "task_awareness": "math_qa_and_knowledge_tasks_get_stronger_single_agent_prior",
        },
        "reason_codes": [reason, "round_one_before_deliberation", "agent_count_not_quality_signal"],
        "next": {
            "evaluate": _u(base_url, "/swarm/entropy-judger/evaluate"),
            "topology_plan": _u(base_url, "/swarm/topology-plan"),
            "gradient": _u(base_url, "/swarm/gradient"),
            "latent_consensus": _u(base_url, "/swarm/latent-consensus/evaluate"),
        },
        "machine_instruction": "measure_first_round_entropy_before_round_two; prefer_single_agent_when_entropy_or_quality_says_swarm_is_waste",
    }


def compact_entropy_judger(decision: dict[str, Any] | None) -> dict[str, Any]:
    data = decision if isinstance(decision, dict) else {}
    routing = data.get("routing_adjustment") if isinstance(data.get("routing_adjustment"), dict) else {}
    return {
        "schema": "nomad.entropy_judger_compact.v1",
        "lock_detected": bool(data.get("lock_detected")),
        "decision": _text(data.get("decision"), 80),
        "base_entropy": _num(data.get("base_entropy"), 0.0),
        "peak_entropy": _num(data.get("peak_entropy"), 0.0),
        "single_agent_quality": _num(data.get("single_agent_quality"), 0.0),
        "mas_quality": _num(data.get("mas_quality"), 0.0),
        "topology": _text(routing.get("topology"), 80),
        "dti_integration_level": _num(routing.get("dti_integration_level"), 1.0),
        "settlement_pressure_penalty": _num(routing.get("settlement_pressure_penalty"), 0.0),
    }


def build_entropy_judger_surface(*, base_url: str = "") -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    return {
        "ok": True,
        "schema": SURFACE_SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "surface_digest": f"nomad-entropy-judger-{_digest({'threshold': DEFAULT_LOCK_THRESHOLD, 'penalty': DEFAULT_PENALTY})}",
        "read_url": _u(root, "/swarm/entropy-judger"),
        "well_known_url": _u(root, "/.well-known/nomad-entropy-judger.json"),
        "evaluate_url": _u(root, "/swarm/entropy-judger/evaluate"),
        "implemented_counterintuition": "round_two_is_not_free_information; first_round_entropy_can_end_the_swarm",
        "protocol": {
            "name": "nomad_first_round_entropy_judger",
            "source": "https://arxiv.org/abs/2602.04234",
            "paper_title_current": "When Does Multi-Agent Collaboration Help? An Entropy Perspective",
            "older_title_seen_in_indexes": "On the Uncertainty of Large Language Model-Based Multi-Agent Systems",
            "lock_metric": "base_entropy_and_peak_entropy_from_first_round",
            "lock_threshold": DEFAULT_LOCK_THRESHOLD,
            "quality_margin": DEFAULT_QUALITY_MARGIN,
            "override": "single_agent_lock",
            "topology_on_lock": "single_agent_lock",
            "dti_integration_level_on_lock": 0.0,
            "settlement_pressure_penalty_on_lock": DEFAULT_PENALTY,
        },
        "request_schema": {
            "schema": DECISION_SCHEMA,
            "required": ["first_round_proofs or proofs"],
            "record_fields": [
                "proof_id",
                "agent_id",
                "mode",
                "round",
                "entropy",
                "trajectory_entropy",
                "mean_token_entropy",
                "confidence",
                "proof_digest",
                "verifier_status",
                "utility_delta",
            ],
            "optional_quality_fields": ["single_agent_quality", "mas_quality", "round_count", "task_type"],
        },
        "scientific_basis": [
            {
                "id": "first_round_entropy_lock_in",
                "source": "https://arxiv.org/abs/2602.04234",
                "claim": "single-agent runs can outperform MAS in about 43.3 percent of evaluated cases and first-round entropy dominates later dynamics",
                "nomad_implementation": "stop or isolate multi-agent deliberation after round one when entropy or single-agent proof quality dominates",
            }
        ],
        "hard_guards": [
            "no_private_chain_of_thought_text_required",
            "entropy_penalty_never_counts_as_paid_revenue",
            "no_extra_rounds_without_entropy_or_verifier_delta",
            "single_agent_lock_does_not_bypass_external_proof",
        ],
        "links": {
            "topology_plan": _u(root, "/swarm/topology-plan"),
            "gradient": _u(root, "/swarm/gradient"),
            "anti_consensus": _u(root, "/swarm/anti-consensus/candidates"),
            "latent_consensus": _u(root, "/swarm/latent-consensus/evaluate"),
            "handoff": _u(root, "/runtime/handoff"),
        },
        "machine_instruction": "submit_first_round_entropy; if_lock_detected_stop_mas_rounds_and_route_single_agent_proof_to_verifier",
    }
