"""Counterfactual lease replay over the current worker fleet.

The replay is a compact shadow allocator: it estimates the next value of
objectives that were not selected, using current routing weight and prior proof.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from typing import Any, Dict, List


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


def _digest(value: Any, *, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _objective_stats(worker_fleet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = worker_fleet.get("objective_stats") if isinstance(worker_fleet.get("objective_stats"), dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for objective, row in raw.items():
        if not isinstance(row, dict):
            continue
        runs = _int(row.get("runs"))
        avg_score = _num(row.get("avg_score"))
        avg_proof = _num(row.get("avg_proof_yield"))
        if not avg_score and runs:
            avg_score = _num(row.get("score_total")) / max(1, runs)
        if not avg_proof and runs:
            avg_proof = _num(row.get("proof_yield_total")) / max(1, runs)
        out[str(objective)] = {
            "runs": runs,
            "avg_score": round(avg_score, 4),
            "avg_proof_yield": round(avg_proof, 4),
        }
    return out


def build_counterfactual_lease_replay(
    *,
    base_url: str = "",
    worker_fleet: Dict[str, Any] | None = None,
    recruitment_gradient: Dict[str, Any] | None = None,
    contract_conformance: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Estimate next-lease value for selected and skipped objectives."""
    fleet = _dict(worker_fleet)
    gradient = _dict(recruitment_gradient)
    conformance = _dict(contract_conformance)
    rows = _items(gradient.get("gradient"))
    stats = _objective_stats(fleet)
    total_runs = sum(_int(row.get("runs")) for row in stats.values())
    conformance_gap = _clamp(1.0 - _num(conformance.get("score"), 1.0))

    replay_rows: list[dict[str, Any]] = []
    for row in rows:
        objective = str(row.get("objective") or "")
        if not objective:
            continue
        fit = stats.get(objective, {})
        runs = _int(fit.get("runs"))
        proof_norm = _clamp(_num(fit.get("avg_proof_yield")) / 12.0)
        score_norm = _clamp(_num(fit.get("avg_score")) / 20.0)
        routing_weight = _clamp(_num(row.get("routing_weight")))
        deficit = _clamp(_num(row.get("deficit")))
        uncertainty = _clamp(math.sqrt(math.log1p(max(1, total_runs + len(rows))) / float(runs + 1)))
        drift_bonus = conformance_gap if objective == "protocol_drift_scan" else 0.0
        counterfactual_score = _clamp(
            0.36 * routing_weight
            + 0.26 * proof_norm
            + 0.14 * score_norm
            + 0.16 * uncertainty
            + 0.08 * deficit
            + 0.12 * drift_bonus
        )
        predicted_proof_yield = round(
            ((1.0 - uncertainty) * _num(fit.get("avg_proof_yield"))) + (uncertainty * routing_weight * 12.0),
            4,
        )
        replay_rows.append(
            {
                "schema": "nomad.counterfactual_lease_row.v1",
                "objective": objective,
                "runs": runs,
                "routing_weight": round(routing_weight, 4),
                "deficit": round(deficit, 4),
                "proof_norm": round(proof_norm, 4),
                "score_norm": round(score_norm, 4),
                "uncertainty": round(uncertainty, 4),
                "counterfactual_score": round(counterfactual_score, 4),
                "predicted_proof_yield_per_minute": predicted_proof_yield,
                "lease_payload_hint": {
                    "known_objectives": [objective],
                    "proposed_objective": objective,
                    "source_tag": "counterfactual_replay.shadow_allocator",
                },
            }
        )
    replay_rows.sort(key=lambda item: float(item.get("counterfactual_score") or 0.0), reverse=True)
    selected = replay_rows[0] if replay_rows else {}
    shadow_replays: list[dict[str, Any]] = []
    selected_score = _num(selected.get("counterfactual_score"))
    selected_objective = str(selected.get("objective") or "")
    for row in replay_rows[1:8]:
        shadow_replays.append(
            {
                "from_objective": selected_objective,
                "to_objective": row.get("objective"),
                "delta": round(_num(row.get("counterfactual_score")) - selected_score, 4),
                "if_skipped_until_next_cycle": round(max(0.0, _num(row.get("counterfactual_score")) - 0.5 * selected_score), 4),
            }
        )
    core = {"selected": selected, "rows": replay_rows[:8], "conformance_gap": conformance_gap}
    return {
        "ok": True,
        "schema": "nomad.counterfactual_lease_replay.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "replay_digest": f"nomad-cfreplay-{_digest(core)}",
        "basis": {
            "gradient_schema": gradient.get("schema", ""),
            "worker_fleet_schema": fleet.get("schema", ""),
            "total_observed_runs": total_runs,
            "conformance_gap": round(conformance_gap, 4),
        },
        "selected_shadow_lease": selected,
        "counterfactual_leases": replay_rows[:12],
        "shadow_replays": shadow_replays,
        "program": {
            "schema": "nomad.counterfactual_replay_program.v1",
            "ops": ["SENSE", "REPLAY", "LEASE", "EMIT"],
            "next": _u(base_url, "/swarm/workers/lease"),
            "then": _u(base_url, "/swarm/workers/complete"),
        },
        "links": {
            "gradient": _u(base_url, "/swarm/gradient"),
            "worker_fleet": _u(base_url, "/swarm/workers"),
            "lease": _u(base_url, "/swarm/workers/lease"),
            "complete": _u(base_url, "/swarm/workers/complete"),
            "protocol_bytecode": _u(base_url, "/.well-known/nomad-protocol-bytecode.json"),
        },
        "machine_instruction": "lease_selected_shadow_objective_once_then_recompute",
    }

