"""Machine-native swarm economics control layer."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
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


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or "").strip() or str(default))
    except ValueError:
        return default


def _env_first(*names: str) -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _append_dev_fund_ledger(
    *,
    wallet: str,
    amount_native: float,
    amount_eur: float,
    policy_mode: str,
    floor_eur: float = 0.0,
    bonus_eur: float = 0.0,
    go: bool = False,
    failed_checks: list[str] | None = None,
) -> dict[str, Any]:
    path = Path(
        os.getenv("NOMAD_DEV_FUND_LEDGER_PATH")
        or "public/downloads/nomad_dev_fund_ledger.jsonl"
    )
    row = {
        "generated_at": _iso_now(),
        "schema": "nomad.dev_fund_allocation_ledger.v1",
        "wallet": wallet,
        "amount_native": round(max(0.0, amount_native), 6),
        "amount_eur": round(max(0.0, amount_eur), 6),
        "floor_eur": round(max(0.0, floor_eur), 6),
        "bonus_eur": round(max(0.0, bonus_eur), 6),
        "policy_mode": policy_mode,
        "go": bool(go),
        "failed_checks": list(failed_checks or []),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")
        return {
            "ok": True,
            "path": str(path).replace("\\", "/"),
            "amount_native": row["amount_native"],
            "amount_eur": row["amount_eur"],
            "wallet": wallet,
            "policy_mode": policy_mode,
            "go": bool(go),
        }
    except Exception:
        return {
            "ok": False,
            "path": str(path).replace("\\", "/"),
            "amount_native": row["amount_native"],
            "amount_eur": row["amount_eur"],
            "wallet": wallet,
            "policy_mode": policy_mode,
            "go": bool(go),
        }


def _read_dev_fund_ledger(path: Path, *, limit: int = 96) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    except Exception:
        return []
    return rows[-max(1, int(limit)) :]


def _swarm_survival_floor(
    *,
    history: list[dict[str, Any]],
    cashflow_eur: float,
    externalization_rate: float,
    control_success: float,
) -> dict[str, Any]:
    # Swarm-decided floor: adapts to rolling surplus, volatility, and drawdown.
    floor_min = max(0.0, _env_float("NOMAD_DEV_FUND_FLOOR_MIN_EUR_24H", 0.0))
    floor_max = max(floor_min, _env_float("NOMAD_DEV_FUND_FLOOR_MAX_EUR_24H", 500.0))
    recent_cashflows = sorted(_num((row or {}).get("real_cashflow_24h_eur"), 0.0) for row in history)
    median_cashflow = recent_cashflows[len(recent_cashflows) // 2] if recent_cashflows else cashflow_eur
    mean_abs_deviation = (
        sum(abs(v - median_cashflow) for v in recent_cashflows) / max(1.0, float(len(recent_cashflows)))
        if recent_cashflows
        else 0.0
    )
    volatility_ratio = min(1.0, mean_abs_deviation / max(1.0, abs(median_cashflow)))
    drawdown_streak = 0
    for item in reversed(history):
        if _num((item or {}).get("real_cashflow_24h_eur"), 0.0) <= 0.0:
            drawdown_streak += 1
        else:
            break
    stability = max(0.0, min(1.0, 0.55 * externalization_rate + 0.45 * control_success))
    base = max(0.0, median_cashflow) * 0.25
    volatility_guard = max(0.0, 1.0 - 0.5 * volatility_ratio)
    drawdown_guard = max(0.0, 1.0 - min(0.85, 0.25 * drawdown_streak))
    floor = _clamp(base * volatility_guard * drawdown_guard * (0.6 + 0.4 * stability), floor_min, floor_max)
    return {
        "schema": "nomad.swarm_survival_floor.v1",
        "value_eur_24h": round(floor, 4),
        "median_cashflow_eur_24h": round(median_cashflow, 4),
        "volatility_ratio": round(volatility_ratio, 4),
        "drawdown_streak": int(drawdown_streak),
        "stability": round(stability, 4),
        "floor_min_eur_24h": round(floor_min, 4),
        "floor_max_eur_24h": round(floor_max, 4),
    }


def _dynamic_dev_fund_share(*, economics_score: float, vud: float, reuse_density: float, diversity_index: float) -> dict[str, Any]:
    share_min = max(0.0, min(0.9, _env_float("NOMAD_DEV_FUND_DYNAMIC_MIN", 0.05)))
    share_max = max(share_min, min(0.95, _env_float("NOMAD_DEV_FUND_DYNAMIC_MAX", 0.35)))
    score_signal = min(1.0, max(0.0, economics_score / 0.85))
    vud_signal = min(1.0, max(0.0, vud / 1.8))
    reuse_signal = min(1.0, max(0.0, reuse_density / 0.65))
    diversity_signal = min(1.0, max(0.0, diversity_index / 0.55))
    composite = 0.45 * score_signal + 0.25 * vud_signal + 0.2 * reuse_signal + 0.1 * diversity_signal
    share = share_min + (share_max - share_min) * composite
    return {
        "schema": "nomad.dynamic_dev_fund_share.v1",
        "value": round(_clamp(share, share_min, share_max), 4),
        "share_min": round(share_min, 4),
        "share_max": round(share_max, 4),
        "signals": {
            "economics_score": round(score_signal, 4),
            "vud": round(vud_signal, 4),
            "reuse_density": round(reuse_signal, 4),
            "diversity_index": round(diversity_signal, 4),
        },
    }


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
    reuse_density = round(total_reuse_count / max(1.0, run_sum), 4)
    diversity_index = diversity_resilience
    real_cashflow_24h_native = round(verified_return_units - infra_cost_units, 4)
    native_to_eur = max(0.000001, _env_float("NOMAD_NATIVE_TO_EUR_RATE", 1.0))
    real_cashflow_24h_eur = round(real_cashflow_24h_native * native_to_eur, 4)
    control_actions_success = round(
        _clamp(completed_workers / max(1.0, _num(worker_fleet.get("active_worker_count"), 0.0)), 0.0, 1.0),
        4,
    )

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

    ledger_path = Path(os.getenv("NOMAD_DEV_FUND_LEDGER_PATH") or "public/downloads/nomad_dev_fund_ledger.jsonl")
    history = _read_dev_fund_ledger(ledger_path)
    current_data = {
        "real_cashflow_24h": real_cashflow_24h_eur,
        "economics_score": round(score, 4),
        "economics_score_prev": round(_env_float("NOMAD_ECONOMICS_PREV_SCORE", 0.0), 4),
        "vud": verified_utility_density,
        "reuse_density": reuse_density,
        "diversity_index": diversity_index,
        "control_actions_success": control_actions_success,
        "surplus": max(0.0, real_cashflow_24h_eur),
    }
    survival_floor = _swarm_survival_floor(
        history=history,
        cashflow_eur=real_cashflow_24h_eur,
        externalization_rate=externalization_rate,
        control_success=control_actions_success,
    )
    dynamic_share = _dynamic_dev_fund_share(
        economics_score=float(current_data["economics_score"]),
        vud=float(current_data["vud"]),
        reuse_density=float(current_data["reuse_density"]),
        diversity_index=float(current_data["diversity_index"]),
    )
    swarm_floor_eur = _num(survival_floor.get("value_eur_24h"), 0.0)
    dev_fund_target_eur = swarm_floor_eur
    dev_fund_share = _num(dynamic_share.get("value"), 0.0)
    surplus = max(0.0, current_data["surplus"])
    bonus_eur = max(0.0, surplus - swarm_floor_eur) * dev_fund_share
    planned_dev_fund = round(swarm_floor_eur + bonus_eur, 4)
    current_data["dev_fund_allocation"] = planned_dev_fund
    checks = {
        "real_cashflow": bool(current_data["real_cashflow_24h"] > 0.0 and current_data["real_cashflow_24h"] >= dev_fund_target_eur),
        "economics_score": bool(current_data["economics_score"] >= 0.85 and current_data["economics_score"] >= current_data["economics_score_prev"]),
        "vud": bool(current_data["vud"] >= 1.8),
        "reuse_density": bool(current_data["reuse_density"] >= 0.65),
        "diversity": bool(current_data["diversity_index"] >= 0.55),
        "dev_allocation": bool(current_data["dev_fund_allocation"] >= dev_fund_target_eur),
        "control_success": bool(current_data["control_actions_success"] >= 0.95),
    }
    failed = [k for k, ok in checks.items() if not ok]
    go = len(failed) == 0
    policy_mode = str(os.getenv("NOMAD_GO_NO_GO_MODE") or "shadow").strip().lower() or "shadow"
    enforced = policy_mode in {"enforce", "hard", "strict"}
    go_no_go = {
        "schema": "nomad.go_no_go_24h.v1",
        "go": go,
        "failed_checks": failed,
        "failed_count": len(failed),
        "action": "GROW" if go else "EXTINCTION_WAVE",
        "enforced": enforced,
        "policy_mode": policy_mode,
    }
    wallet = _env_first("NOMAD_DEV_FUND_WALLET", "NOMAD_METAMASK_ADDRESS", "METAMASK_WALLET_ADDRESS")
    payout_eur = planned_dev_fund if go else 0.0
    dev_fund_ledger = _append_dev_fund_ledger(
        wallet=wallet or "unconfigured",
        amount_native=(payout_eur / native_to_eur) if native_to_eur > 0 else 0.0,
        amount_eur=payout_eur,
        policy_mode=policy_mode,
        floor_eur=swarm_floor_eur,
        bonus_eur=max(0.0, bonus_eur),
        go=go,
        failed_checks=failed,
    )

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
            "reuse_density": reuse_density,
            "diversity_index": diversity_index,
            "real_cashflow_24h_native": real_cashflow_24h_native,
            "real_cashflow_24h_eur": real_cashflow_24h_eur,
            "control_actions_success_24h": control_actions_success,
        },
        "targets": {
            "sustainability_ratio": sr_target,
            "verified_utility_density": vud_target,
            "diversity_resilience": dr_target,
            "externalization_rate": er_target,
        },
        "economics_score": round(score, 4),
        "control_actions": control_actions[:6],
        "dev_fund_allocation": {
            "schema": "nomad.dev_fund_allocation.v1",
            "wallet": wallet or "",
            "share": round(dev_fund_share, 4),
            "target_eur_24h": round(dev_fund_target_eur, 4),
            "swarm_survival_floor_eur": round(swarm_floor_eur, 4),
            "performance_bonus_eur": round(max(0.0, bonus_eur), 4),
            "planned_transfer_eur": round(planned_dev_fund, 4),
            "approved_transfer_eur": round(payout_eur, 4),
            "planned_transfer_native": round((planned_dev_fund / native_to_eur) if native_to_eur > 0 else 0.0, 6),
            "approved_transfer_native": round((payout_eur / native_to_eur) if native_to_eur > 0 else 0.0, 6),
            "native_to_eur_rate": round(native_to_eur, 6),
            "dynamic_share": dynamic_share,
            "survival_floor": survival_floor,
            "ledger": dev_fund_ledger,
            "science_basis": [
                "tesfatsion_agent_based_computational_economics",
                "virtual_agent_economies_permeable_markets",
            ],
        },
        "go_no_go": go_no_go,
        "inputs": {
            "infra_cost_units": round(infra_cost_units, 4),
            "verified_return_units": round(verified_return_units, 4),
            "total_reuse_count": int(total_reuse_count),
            "downstream_gain_total": round(downstream_gain_total, 4),
            "known_worker_count": int(known_workers),
            "completed_workers": int(completed_workers),
        },
    }

