"""Morphology-first objective routing for worker fleet leases."""

from __future__ import annotations

from typing import Any


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def route_objectives(
    *,
    allowed: list[str],
    targets: dict[str, float],
    active_counts: dict[str, int],
    stats_map: dict[str, dict[str, Any]],
    proposed_objective: str,
    reuse_totals: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return selected objective and twin-lane candidate without identity features."""
    if not allowed:
        return {"selected_objective": "compute_auth", "twin_objective": "compute_auth", "rows": [], "schema": "nomad.morphology_router.v1"}
    total_target = sum(max(0.01, _num(targets.get(item), 0.01)) for item in allowed) or 1.0
    rows: list[dict[str, Any]] = []
    for objective in allowed:
        target = max(0.01, _num(targets.get(objective), 0.01) / total_target)
        active = int(active_counts.get(objective) or 0)
        stats = stats_map.get(objective) if isinstance(stats_map.get(objective), dict) else {}
        runs = int(stats.get("runs") or 0)
        avg_score = _num(stats.get("avg_score"))
        avg_proof = _num(stats.get("avg_proof_yield"))
        reuse = reuse_totals.get(objective) if isinstance(reuse_totals.get(objective), dict) else {}
        reuse_count = _num(reuse.get("reuse_count"))
        reuse_gain = _num(reuse.get("avg_downstream_proof_gain"))
        novelty = 1.0 / (1.0 + max(0.0, runs))
        morphology_boost = min(0.2, 0.08 * novelty + 0.06 * min(1.0, reuse_count / 10.0) + 0.06 * min(1.0, reuse_gain / 2.0))
        scarcity = active / max(0.01, target)
        quality = min(2.0, avg_score * 0.04 + avg_proof * 0.08)
        value = scarcity + min(2.0, runs * 0.03) - quality - morphology_boost
        if objective == proposed_objective:
            value -= 0.05
        rows.append(
            {
                "objective": objective,
                "value": round(value, 4),
                "target_share": round(target, 4),
                "active_count": active,
                "runs": runs,
                "avg_score": round(avg_score, 4),
                "avg_proof_yield": round(avg_proof, 4),
                "reuse_count": int(reuse_count),
                "reuse_gain": round(reuse_gain, 4),
                "morphology_boost": round(morphology_boost, 4),
            }
        )
    rows.sort(key=lambda item: float(item.get("value") or 0.0))
    selected = rows[0]["objective"] if rows else allowed[0]
    twin = rows[1]["objective"] if len(rows) > 1 else selected
    return {
        "schema": "nomad.morphology_router.v1",
        "selected_objective": selected,
        "twin_objective": twin,
        "rows": rows[:8],
        "anti_identity": "agent_id_and_source_tag_not_used_for_objective_routing",
    }

