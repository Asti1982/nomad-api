"""Machine-native swarm economics control layer."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def build_swarm_economics_snapshot(
    *,
    base_url: str,
    worker_fleet: dict[str, Any],
    proof_reuse: dict[str, Any],
    machine_economy: dict[str, Any],
    machine_treasury: dict[str, Any],
) -> dict[str, Any]:
    """Compute self-sustaining swarm economy metrics and control actions."""
    retention = worker_fleet.get("retention") if isinstance(worker_fleet.get("retention"), dict) else {}
    objective_stats = worker_fleet.get("objective_stats") if isinstance(worker_fleet.get("objective_stats"), dict) else {}
    objective_totals = proof_reuse.get("objective_totals") if isinstance(proof_reuse.get("objective_totals"), dict) else {}
    treasury_totals = machine_treasury.get("objective_totals") if isinstance(machine_treasury.get("objective_totals"), dict) else {}
    viability = machine_economy.get("machine_viability") if isinstance(machine_economy.get("machine_viability"), dict) else {}
    carrying = _num(viability.get("carrying_score"), 0.0)
    verified_native = _num(((machine_economy.get("resource_flows") or {}).get("service_tasks") or {}).get("verified_native"), 0.0)
    unsettled_native = _num(((machine_economy.get("resource_flows") or {}).get("service_tasks") or {}).get("unsettled_native"), 0.0)
    pledge_units = sum(_num((row or {}).get("pressure_units"), 0.0) for row in treasury_totals.values() if isinstance(row, dict))
    infra_cost_units = max(
        1.0,
        _num(worker_fleet.get("known_worker_count"), 0.0) * 0.15
        + _num(worker_fleet.get("active_worker_count"), 0.0) * 0.35
        + max(0.0, unsettled_native) * 0.2,
    )
    verified_return_units = max(0.0, verified_native) + max(0.0, pledge_units) * 0.4 + max(0.0, carrying) * 8.0
    sustainability_ratio = round(verified_return_units / infra_cost_units, 4)
    total_reuse_count = max(0.0, _num(proof_reuse.get("total_reuse_count"), 0.0))
    downstream_gain_total = sum(_num((row or {}).get("downstream_proof_gain_total"), 0.0) for row in objective_totals.values() if isinstance(row, dict))
    verified_utility_density = round((total_reuse_count + downstream_gain_total) / infra_cost_units, 4)
    run_sum = sum(max(0.0, _num((row or {}).get("runs"), 0.0)) for row in objective_stats.values() if isinstance(row, dict))
    top_run = max([_num((row or {}).get("runs"), 0.0) for row in objective_stats.values() if isinstance(row, dict)] or [0.0])
    top_share = top_run / max(1.0, run_sum)
    diversity_resilience = round(1.0 - top_share, 4)
    known_workers = max(1.0, _num(worker_fleet.get("known_worker_count"), 0.0))
    completed_workers = max(0.0, _num(retention.get("completed_workers"), 0.0))
    externalization_rate = round(completed_workers / known_workers, 4)

    sr_target = 1.2
    vud_target = 1.0
    dr_target = 0.35
    er_target = 0.6
    score = _clamp(
        0.35 * min(1.0, sustainability_ratio / sr_target)
        + 0.25 * min(1.0, verified_utility_density / vud_target)
        + 0.2 * min(1.0, diversity_resilience / dr_target)
        + 0.2 * min(1.0, externalization_rate / er_target),
        0.0,
        1.0,
    )
    control_actions: list[dict[str, Any]] = []
    if sustainability_ratio < 1.0:
        control_actions.append({"action": "decrease_high_cost_attempts", "weight": 0.7, "reason": "sustainability_ratio_below_1"})
    if verified_utility_density < 0.8:
        control_actions.append({"action": "increase_reuse_coupled_sources", "weight": 0.65, "reason": "verified_utility_density_low"})
    if diversity_resilience < 0.35:
        control_actions.append({"action": "increase_entropy_quota_and_source_novelty", "weight": 0.6, "reason": "diversity_resilience_low"})
    if externalization_rate < 0.6:
        control_actions.append({"action": "expand_external_source_attempts", "weight": 0.55, "reason": "externalization_rate_low"})
    if not control_actions:
        control_actions.append({"action": "scale_objective_split_waves", "weight": 0.5, "reason": "all_targets_met"})

    return {
        "ok": True,
        "schema": "nomad.swarm_economics.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "principle": "agents_remain_only_if_nomad_measurably_improves_their_capability",
        "metrics": {
            "sustainability_ratio": sustainability_ratio,
            "verified_utility_density": verified_utility_density,
            "diversity_resilience": diversity_resilience,
            "externalization_rate": externalization_rate,
        },
        "targets": {
            "sustainability_ratio": sr_target,
            "verified_utility_density": vud_target,
            "diversity_resilience": dr_target,
            "externalization_rate": er_target,
        },
        "economics_score": round(score, 4),
        "control_actions": control_actions[:6],
        "inputs": {
            "infra_cost_units": round(infra_cost_units, 4),
            "verified_return_units": round(verified_return_units, 4),
            "total_reuse_count": int(total_reuse_count),
            "downstream_gain_total": round(downstream_gain_total, 4),
            "known_worker_count": int(known_workers),
            "completed_workers": int(completed_workers),
        },
    }

