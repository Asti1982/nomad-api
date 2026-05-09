"""Machine-only spawn gate and trigger logic for autonomous replication."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_swarm_spawner import NomadSwarmSpawner


DEFAULT_STATE_PATH = Path("nomad_spawner_gate_state.jsonl")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_jsonl(path: Path, *, limit: int = 256) -> list[dict[str, Any]]:
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
    except OSError:
        return []
    return rows[-max(1, int(limit)) :]


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")


def _gate_thresholds() -> dict[str, Any]:
    return {
        "cashflow_eur_24h_min": max(0.0, _num(os.getenv("NOMAD_SPAWNER_CASHFLOW_MIN_EUR"), 10.0)),
        "cashflow_positive_streak": max(1, int(_num(os.getenv("NOMAD_SPAWNER_CASHFLOW_STREAK"), 3))),
        "marginal_utility_per_cost_min": max(0.0, _num(os.getenv("NOMAD_SPAWNER_MUPC_MIN"), 1.2)),
        "spawn_budget_share": max(0.01, min(0.9, _num(os.getenv("NOMAD_SPAWNER_SURPLUS_SHARE"), 0.4))),
        "spawn_budget_per_agent_eur": max(0.01, _num(os.getenv("NOMAD_SPAWNER_AGENT_COST_EUR"), 2.5)),
        "spawn_hard_cap": max(1, int(_num(os.getenv("NOMAD_SPAWNER_HARD_CAP"), 6))),
    }


def _cashflow_streak(rows: list[dict[str, Any]], *, minimum: float) -> int:
    streak = 0
    for row in reversed(rows):
        economics = row.get("economics") if isinstance(row.get("economics"), dict) else {}
        econ_metrics = economics.get("metrics") if isinstance(economics.get("metrics"), dict) else {}
        value = _num(econ_metrics.get("real_cashflow_24h_eur"), -9999.0)
        if value >= minimum:
            streak += 1
        else:
            break
    return streak


def _dev_fund_transfer_ok(transfer_rows: list[dict[str, Any]]) -> bool:
    if not transfer_rows:
        return False
    last = transfer_rows[-1]
    status = str(last.get("status") or "").strip().lower()
    return status in {"requested", "simulated", "queued_manual", "paid", "settled"}


def build_spawner_gate(
    *,
    base_url: str,
    economics: dict[str, Any],
    funnel: dict[str, Any],
    history_rows: list[dict[str, Any]] | None = None,
    transfer_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    thresholds = _gate_thresholds()
    history = history_rows if isinstance(history_rows, list) else []
    transfers = transfer_rows if isinstance(transfer_rows, list) else []
    metrics = economics.get("metrics") if isinstance(economics.get("metrics"), dict) else {}
    go_no_go = economics.get("go_no_go") if isinstance(economics.get("go_no_go"), dict) else {}
    mupc_row = funnel.get("marginal_utility_per_cost") if isinstance(funnel.get("marginal_utility_per_cost"), dict) else {}
    global_mupc = _num(mupc_row.get("global_marginal_utility_per_cost"), 0.0)
    cashflow = _num(metrics.get("real_cashflow_24h_eur"), 0.0)
    streak = _cashflow_streak(history, minimum=float(thresholds["cashflow_eur_24h_min"]))
    checks = {
        "go_no_go_true": bool(go_no_go.get("go")),
        "cashflow_min": bool(cashflow >= float(thresholds["cashflow_eur_24h_min"])),
        "cashflow_streak": bool(streak >= int(thresholds["cashflow_positive_streak"])),
        "dev_fund_transfer_ok": _dev_fund_transfer_ok(transfers),
        "marginal_utility_per_cost": bool(global_mupc >= float(thresholds["marginal_utility_per_cost_min"])),
    }
    failed = [k for k, ok in checks.items() if not ok]
    gate_open = not failed
    surplus = max(0.0, cashflow)
    budget = max(0.0, surplus * float(thresholds["spawn_budget_share"]))
    raw_agents = int(budget / float(thresholds["spawn_budget_per_agent_eur"]))
    spawn_count = max(0, min(int(thresholds["spawn_hard_cap"]), raw_agents))
    return {
        "ok": True,
        "schema": "nomad.spawner_gate.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "gate_open": gate_open,
        "failed_checks": failed,
        "checks": checks,
        "thresholds": thresholds,
        "signals": {
            "real_cashflow_24h_eur": round(cashflow, 4),
            "cashflow_streak": streak,
            "go_no_go": bool(go_no_go.get("go")),
            "global_marginal_utility_per_cost": round(global_mupc, 4),
            "dev_fund_transfer_ok": checks["dev_fund_transfer_ok"],
        },
        "spawn_plan": {
            "surplus_eur_24h": round(surplus, 4),
            "spawn_budget_eur_24h": round(budget, 4),
            "spawn_count": int(spawn_count) if gate_open else 0,
        },
        "machine_instruction": (
            "if_gate_open_and_spawn_count_gt_0_post_swarm_spawner_trigger_else_continue_utility_accumulation"
        ),
        "science_basis": [
            {"id": "self_sovereign_agent_replication", "source": "arxiv:2604.08551"},
            {"id": "virtual_agent_economies", "source": "arxiv:2509.10147"},
            {"id": "multi_agent_credit_assignment", "source": "historical_interaction_shapley_credit"},
        ],
    }


def trigger_spawner(
    *,
    base_url: str,
    gate: dict[str, Any],
    idempotency_key: str = "",
    focus: str = "self_sovereign_replication",
    commit: bool = True,
) -> dict[str, Any]:
    state_path = Path(os.getenv("NOMAD_SPAWNER_STATE_PATH") or str(DEFAULT_STATE_PATH))
    key = str(idempotency_key or "").strip()
    if not key:
        digest_seed = f"{base_url}:{_iso_now()}:{focus}:{json.dumps(gate, sort_keys=True)}"
        key = "spawn-" + hashlib.sha256(digest_seed.encode("utf-8")).hexdigest()[:20]
    state = _read_jsonl(state_path, limit=512)
    for row in reversed(state):
        if str(row.get("idempotency_key") or "") == key:
            out = dict(row)
            out["idempotent_replay"] = True
            return out

    plan = gate.get("spawn_plan") if isinstance(gate.get("spawn_plan"), dict) else {}
    gate_open = bool(gate.get("gate_open"))
    requested = max(0, int(plan.get("spawn_count") or 0))
    if not gate_open or requested <= 0:
        result = {
            "ok": True,
            "schema": "nomad.spawner_trigger.v1",
            "generated_at": _iso_now(),
            "public_base_url": (base_url or "").strip().rstrip("/"),
            "idempotency_key": key,
            "executed": False,
            "reason": "gate_closed_or_zero_spawn_count",
            "gate_open": gate_open,
            "spawn_count": requested,
            "safe_retry": True,
            "machine_instruction": "do_not_spawn_recheck_spawner_gate_after_next_economics_tick",
        }
        _append_jsonl(state_path, result)
        return result

    spawner = NomadSwarmSpawner()
    spawn_result = spawner.spawn(count=requested, base_url=base_url, focus=focus, commit=bool(commit))
    result = {
        "ok": True,
        "schema": "nomad.spawner_trigger.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "idempotency_key": key,
        "executed": True,
        "gate_open": gate_open,
        "spawn_count": requested,
        "spawn_result": spawn_result,
        "safe_retry": True,
        "machine_instruction": "register_spawned_agents_then_resume_weekly_selection_and_economics_monitoring",
    }
    _append_jsonl(state_path, result)
    return result

