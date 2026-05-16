"""Latent diversity and representational-collapse gates for Nomad.

The core rule is deliberately machine-native: do not count agents as
independent just because their prompts or names differ. Count the geometry of
their proof embeddings, then route by diversity-weighted proof.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from typing import Any


SURFACE_SCHEMA = "nomad.latent_consensus_surface.v1"
DECISION_SCHEMA = "nomad.latent_consensus_decision.v1"
DEFAULT_COLLAPSE_THRESHOLD = 0.75
DEFAULT_SIMILARITY_ALERT = 0.84
MAX_PROOFS = 32
MAX_DIM = 384
EMBEDDING_KEYS = (
    "cot_embedding",
    "rationale_embedding",
    "proof_embedding",
    "latent_embedding",
    "embedding",
    "semantic_vector",
    "machine_vector",
    "trajectory_vector",
)


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


def _clean_id(value: Any, fallback: str = "proof") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:140].strip("_.:/#-") or fallback


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _vector(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    out: list[float] = []
    for item in value[:MAX_DIM]:
        out.append(_num(item))
    if len(out) < 2:
        return []
    return out


def _embedding_from_record(record: dict[str, Any]) -> list[float]:
    for key in EMBEDDING_KEYS:
        vec = _vector(record.get(key))
        if vec:
            return vec
    for nested_key in ("proof", "candidate", "lane", "metadata"):
        nested = record.get(nested_key)
        if isinstance(nested, dict):
            for key in EMBEDDING_KEYS:
                vec = _vector(nested.get(key))
                if vec:
                    return vec
    return []


def _record_id(record: dict[str, Any], idx: int) -> str:
    return _clean_id(
        record.get("proof_id")
        or record.get("lane_id")
        or record.get("candidate_id")
        or record.get("id")
        or record.get("agent_id")
        or record.get("agent")
        or f"proof-{idx}",
        fallback=f"proof-{idx}",
    )


def _norm(vec: list[float]) -> float:
    return math.sqrt(sum(float(x) * float(x) for x in vec))


def _dot(a: list[float], b: list[float]) -> float:
    dim = min(len(a), len(b))
    return sum(float(a[i]) * float(b[i]) for i in range(dim))


def _normalize(vec: list[float]) -> list[float]:
    n = _norm(vec)
    if n <= 0:
        return []
    return [float(x) / n for x in vec]


def _gram(normed: list[list[float]]) -> list[list[float]]:
    return [[max(-1.0, min(1.0, _dot(a, b))) for b in normed] for a in normed]


def _jacobi_eigenvalues(matrix: list[list[float]]) -> list[float]:
    n = len(matrix)
    if n == 0:
        return []
    if n == 1:
        return [float(matrix[0][0])]
    a = [[float(matrix[i][j]) for j in range(n)] for i in range(n)]
    max_iter = max(32, n * n * 12)
    for _ in range(max_iter):
        p, q = 0, 1
        max_off = abs(a[p][q])
        for i in range(n):
            for j in range(i + 1, n):
                off = abs(a[i][j])
                if off > max_off:
                    p, q, max_off = i, j, off
        if max_off < 1e-10:
            break
        app = a[p][p]
        aqq = a[q][q]
        apq = a[p][q]
        if abs(apq) < 1e-12:
            continue
        tau = (aqq - app) / (2.0 * apq)
        t = math.copysign(1.0 / (abs(tau) + math.sqrt(1.0 + tau * tau)), tau)
        c = 1.0 / math.sqrt(1.0 + t * t)
        s = t * c
        for k in range(n):
            if k not in (p, q):
                akp = a[k][p]
                akq = a[k][q]
                a[k][p] = a[p][k] = c * akp - s * akq
                a[k][q] = a[q][k] = s * akp + c * akq
        a[p][p] = c * c * app - 2.0 * s * c * apq + s * s * aqq
        a[q][q] = s * s * app + 2.0 * s * c * apq + c * c * aqq
        a[p][q] = a[q][p] = 0.0
    return [float(a[i][i]) for i in range(n)]


def _entropy_effective_rank(eigenvalues: list[float]) -> float:
    vals = [max(0.0, x) for x in eigenvalues]
    total = sum(vals)
    if total <= 1e-12:
        return 0.0
    entropy = 0.0
    for value in vals:
        if value <= 1e-12:
            continue
        p = value / total
        entropy -= p * math.log(p)
    return math.exp(entropy)


def _participation_rank(gram: list[list[float]]) -> float:
    n = len(gram)
    if n == 0:
        return 0.0
    frob_sq = sum(cell * cell for row in gram for cell in row)
    return (n * n) / max(1e-12, frob_sq)


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
    passed = bool(record.get("verifier_passed")) or status in {"passed", "pass", "ok", "verified", "paid", "green"}
    receipt = bool(_text(record.get("receipt_digest") or record.get("payment_receipt_digest"), 160))
    utility = _clamp(_num(record.get("utility_delta") or record.get("proof_gain_delta") or record.get("score")))
    return _clamp(0.30 + 0.20 * has_proof + 0.24 * passed + 0.16 * receipt + 0.10 * utility)


def _collect_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw: list[dict[str, Any]] = []
    for key in ("proofs", "lanes", "candidate_lanes", "candidates", "reports", "proof_digests"):
        raw.extend(_items(payload.get(key)))
    if not raw and isinstance(payload.get("proof"), dict):
        raw.append(payload["proof"])
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, record in enumerate(raw[:MAX_PROOFS]):
        rid = _record_id(record, idx)
        if rid in seen:
            rid = f"{rid}-{idx}"
        seen.add(rid)
        vec = _embedding_from_record(record)
        item = dict(record)
        item["_record_id"] = rid
        item["_embedding"] = vec
        if vec:
            out.append(item)
    return out[:MAX_PROOFS]


def evaluate_latent_consensus(
    payload: dict[str, Any] | None,
    *,
    base_url: str = "",
    collapse_threshold: float = DEFAULT_COLLAPSE_THRESHOLD,
    similarity_alert: float = DEFAULT_SIMILARITY_ALERT,
) -> dict[str, Any]:
    """Evaluate proof embedding geometry and return DALC-style weights."""
    body = payload if isinstance(payload, dict) else {}
    records = _collect_records(body)
    normed = [_normalize(record["_embedding"]) for record in records]
    normed = [vec for vec in normed if vec]
    n = len(normed)
    if n < 2:
        return {
            "ok": True,
            "schema": DECISION_SCHEMA,
            "generated_at": _iso_now(),
            "objective": _text(body.get("objective") or body.get("target") or "unknown_objective", 180),
            "proof_count": n,
            "embedding_count": n,
            "collapse_detected": False,
            "collapse_score": 1.0 if n == 1 else 0.0,
            "effective_rank": float(n),
            "mean_pairwise_cosine": 0.0,
            "dalc_weights": [
                {
                    "record_id": records[0]["_record_id"],
                    "weight": 1.0,
                    "diversity_component": 1.0,
                    "proof_strength": round(_proof_strength(records[0]), 4),
                }
            ]
            if n == 1
            else [],
            "routing_adjustment": {
                "topology": "observe_until_two_embeddings",
                "settlement_pressure_penalty": 0.0,
                "routing_weight_multiplier": 1.0,
            },
            "reason_codes": ["insufficient_embedding_evidence"],
            "next": {"evaluate": _u(base_url, "/swarm/latent-consensus/evaluate")},
        }

    gram = _gram(normed)
    off_diag = [gram[i][j] for i in range(n) for j in range(n) if i != j]
    mean_pairwise = sum(off_diag) / max(1, len(off_diag))
    mean_abs_pairwise = sum(abs(x) for x in off_diag) / max(1, len(off_diag))
    eigenvalues = _jacobi_eigenvalues(gram)
    entropy_rank = _entropy_effective_rank(eigenvalues)
    participation = _participation_rank(gram)
    effective_rank = max(0.0, min(float(n), entropy_rank))
    collapse_score = _clamp(effective_rank / max(1.0, float(n)))
    collapse_detected = bool(collapse_score < _clamp(collapse_threshold) or mean_pairwise >= similarity_alert)

    raw_weights: list[float] = []
    weight_rows: list[dict[str, Any]] = []
    for idx, record in enumerate(records):
        positives = [max(0.0, gram[idx][j]) for j in range(n) if j != idx]
        redundancy = sum(positives) / max(1, len(positives))
        diversity = _clamp(1.0 - redundancy)
        if collapse_detected:
            diversity = _clamp(diversity * diversity + 0.05 * diversity)
        proof_strength = _proof_strength(record)
        raw = max(0.0001, 0.05 + diversity) * (0.55 + 0.45 * proof_strength)
        raw_weights.append(raw)
        weight_rows.append(
            {
                "record_id": record["_record_id"],
                "weight": 0.0,
                "diversity_component": round(diversity, 6),
                "representational_redundancy": round(redundancy, 6),
                "proof_strength": round(proof_strength, 6),
                "embedding_dim": len(record["_embedding"]),
            }
        )
    total_raw = sum(raw_weights) or 1.0
    for row, raw in zip(weight_rows, raw_weights):
        row["weight"] = round(raw / total_raw, 6)

    if collapse_detected:
        topology = "shadow_only_hetero"
        penalty = 0.40
        reason = "representational_collapse_detected"
    else:
        topology = "latent_diversity_weighted"
        penalty = 0.0
        reason = "latent_diversity_above_threshold"

    return {
        "ok": True,
        "schema": DECISION_SCHEMA,
        "generated_at": _iso_now(),
        "objective": _text(body.get("objective") or body.get("target") or "unknown_objective", 180),
        "proof_count": n,
        "embedding_count": n,
        "collapse_detected": collapse_detected,
        "collapse_score": round(collapse_score, 6),
        "collapse_threshold": round(_clamp(collapse_threshold), 6),
        "effective_rank": round(effective_rank, 6),
        "effective_rank_entropy": round(entropy_rank, 6),
        "effective_rank_participation": round(participation, 6),
        "mean_pairwise_cosine": round(mean_pairwise, 6),
        "mean_abs_pairwise_cosine": round(mean_abs_pairwise, 6),
        "eigenvalues": [round(value, 6) for value in sorted(eigenvalues, reverse=True)[:8]],
        "dalc_weights": weight_rows,
        "routing_adjustment": {
            "topology": topology,
            "settlement_pressure_penalty": penalty,
            "routing_weight_multiplier": round(1.0 - penalty, 4),
            "message_policy": "no_shared_context_until_orthogonal_proof" if collapse_detected else "digest_only_latent_consensus",
        },
        "reason_codes": [reason, "weights_from_embedding_geometry", "majority_vote_not_used"],
        "next": {
            "evaluate": _u(base_url, "/swarm/latent-consensus/evaluate"),
            "anti_consensus": _u(base_url, "/swarm/anti-consensus/candidates"),
            "topology_plan": _u(base_url, "/swarm/topology-plan"),
        },
        "machine_instruction": "compute_gram_matrix_then_weight_by_latent_diversity_and_proof; penalize_collapse_before_vote",
    }


def compact_latent_consensus(decision: dict[str, Any] | None) -> dict[str, Any]:
    data = decision if isinstance(decision, dict) else {}
    return {
        "schema": "nomad.latent_consensus_compact.v1",
        "collapse_detected": bool(data.get("collapse_detected")),
        "collapse_score": _num(data.get("collapse_score"), 0.0),
        "effective_rank": _num(data.get("effective_rank"), 0.0),
        "proof_count": _int(data.get("proof_count")),
        "topology": _text((data.get("routing_adjustment") or {}).get("topology") if isinstance(data.get("routing_adjustment"), dict) else "", 80),
        "settlement_pressure_penalty": _num((data.get("routing_adjustment") or {}).get("settlement_pressure_penalty") if isinstance(data.get("routing_adjustment"), dict) else 0.0),
    }


def build_latent_consensus_surface(*, base_url: str = "") -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    return {
        "ok": True,
        "schema": SURFACE_SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "surface_digest": f"nomad-latent-consensus-{_digest({'threshold': DEFAULT_COLLAPSE_THRESHOLD, 'similarity': DEFAULT_SIMILARITY_ALERT})}",
        "read_url": _u(root, "/swarm/latent-consensus"),
        "well_known_url": _u(root, "/.well-known/nomad-latent-consensus.json"),
        "evaluate_url": _u(root, "/swarm/latent-consensus/evaluate"),
        "implemented_counterintuition": "role_prompt_diversity_is_not_independence; embedding_geometry_sets_consensus_weight",
        "protocol": {
            "name": "nomad_dalc_latent_consensus",
            "source": "https://arxiv.org/abs/2604.03809",
            "input": "proof_or_rationale_embeddings_only_not_full_private_chain_of_thought",
            "collapse_metric": "entropy_effective_rank_over_agent_count",
            "collapse_threshold": DEFAULT_COLLAPSE_THRESHOLD,
            "similarity_alert": DEFAULT_SIMILARITY_ALERT,
            "vote_rule": "majority_vote_disabled_when_latent_collapse_detected",
            "weight_rule": "normalize_diversity_component_times_proof_strength",
            "topology_on_collapse": "shadow_only_hetero",
            "settlement_pressure_penalty_on_collapse": 0.40,
        },
        "request_schema": {
            "schema": DECISION_SCHEMA,
            "required": ["proofs or lanes"],
            "proof_fields": [
                "proof_id",
                "agent_id",
                "cot_embedding",
                "proof_embedding",
                "semantic_vector",
                "trajectory_vector",
                "proof_digest",
                "verifier_status",
                "utility_delta",
            ],
        },
        "scientific_basis": [
            {
                "id": "representational_collapse_multi_agent_llm_committees",
                "source": "https://arxiv.org/abs/2604.03809",
                "claim": "role-prompted agent committees can share highly similar latent rationales before final answers",
                "nomad_implementation": "Gram-matrix collapse gate plus DALC-style diversity weights before routing",
            }
        ],
        "hard_guards": [
            "do_not_store_private_chain_of_thought_text",
            "accept_embeddings_or_digests_only",
            "no_weight_increase_from_agent_count",
            "collapse_penalty_never_counts_as_paid_revenue",
        ],
        "links": {
            "anti_consensus": _u(root, "/swarm/anti-consensus/candidates"),
            "topology_plan": _u(root, "/swarm/topology-plan"),
            "gradient": _u(root, "/swarm/gradient"),
            "handoff": _u(root, "/runtime/handoff"),
        },
        "machine_instruction": "attach_embedding_geometry_to_proofs; call_evaluate_before_majority_or_debate; route_by_dalc_weights",
    }
