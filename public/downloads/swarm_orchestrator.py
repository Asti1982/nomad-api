#!/usr/bin/env python3
"""Portable Nomad Swarm Orchestrator for transition workers.

Runs multiple worker lanes, chooses objectives by proof/economic score,
and records adaptive routing state for future cycles.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

OBJECTIVES = [
    "settlement_capacity_builder",
    "proof_pressure_engine",
    "proof_market_maker",
    "payment_friction_scan",
    "protocol_drift_scan",
    "adversarial_contract_fuzzer",
    "negative_space_harvest",
    "latency_anomaly_hunt",
    "compute_auth",
]


def _state_path() -> Path:
    return Path(os.getenv("NOMAD_SWARM_ORCHESTRATOR_STATE", "nomad_swarm_orchestrator_state.json"))


def _load_state() -> dict:
    path = _state_path()
    if not path.exists():
        return {"lanes": {}, "runs": [], "meta": {"cycles": 0}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"lanes": {}, "runs": [], "meta": {"cycles": 0}}


def _save_state(state: dict) -> None:
    path = _state_path()
    path.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def _lane_score(stats: dict) -> float:
    runs = int(stats.get("runs") or 0)
    avg = float(stats.get("avg_score") or 0.0)
    proof_avg = float(stats.get("avg_proof_yield") or 0.0)
    # Exploration bonus keeps low-run lanes in rotation.
    exploration = 2.0 / max(1, runs)
    return avg + proof_avg * 0.2 + exploration


def _choose_objective(state: dict) -> str:
    lanes = state.get("lanes") if isinstance(state.get("lanes"), dict) else {}
    unseen = [name for name in OBJECTIVES if int((lanes.get(name) or {}).get("runs") or 0) == 0]
    if unseen:
        return sorted(unseen)[0]
    best = OBJECTIVES[0]
    best_score = -1e9
    for name in OBJECTIVES:
        score = _lane_score(lanes.get(name) or {})
        if score > best_score:
            best = name
            best_score = score
    return best


def _run_worker_once(base_url: str, objective: str, worker_id: str, no_ollama: bool, timeout: int) -> dict:
    script_path = Path(__file__).with_name("nomad_transition_worker.py")
    cmd = [
        sys.executable,
        str(script_path),
        "--base-url",
        base_url,
        "--agent-id",
        worker_id,
        "--machine-objective",
        objective,
        "--cycles",
        "1",
        "--timeout",
        str(timeout),
    ]
    if no_ollama:
        cmd.append("--no-ollama")
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": "worker_process_failed",
            "return_code": proc.returncode,
            "stderr": (proc.stderr or "")[-400:],
        }
    lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    if not lines:
        return {"ok": False, "error": "worker_no_output"}
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return {"ok": False, "error": "worker_bad_json", "raw": lines[-1][:400]}


def _update_lane(state: dict, objective: str, report: dict) -> None:
    state.setdefault("lanes", {})
    lane = state["lanes"].setdefault(
        objective,
        {"runs": 0, "score_total": 0.0, "avg_score": 0.0, "proof_yield_total": 0.0, "avg_proof_yield": 0.0},
    )
    lane["runs"] = int(lane.get("runs") or 0) + 1
    score = float(report.get("meta_score") or 0.0)
    yield_pm = float(((report.get("proof_pressure") or {}).get("proof_yield_per_minute")) or 0.0)
    lane["score_total"] = round(float(lane.get("score_total") or 0.0) + score, 4)
    lane["proof_yield_total"] = round(float(lane.get("proof_yield_total") or 0.0) + yield_pm, 4)
    lane["avg_score"] = round(lane["score_total"] / max(1, lane["runs"]), 4)
    lane["avg_proof_yield"] = round(lane["proof_yield_total"] / max(1, lane["runs"]), 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Nomad swarm orchestrator")
    parser.add_argument("--base-url", default=os.getenv("NOMAD_BASE_URL", "https://www.syndiode.com"))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--no-ollama", action="store_true")
    args = parser.parse_args()

    state = _load_state()
    state.setdefault("meta", {})
    total_cycles = max(1, int(args.cycles))
    workers = max(1, int(args.workers))

    for cycle in range(1, total_cycles + 1):
        cycle_reports = []
        for idx in range(workers):
            objective = _choose_objective(state)
            worker_id = f"transition-worker.orchestrated.{idx+1}.{os.getenv('COMPUTERNAME', 'node').lower()}.nomad"
            report = _run_worker_once(
                base_url=args.base_url,
                objective=objective,
                worker_id=worker_id,
                no_ollama=bool(args.no_ollama),
                timeout=int(args.timeout),
            )
            report["orchestrator_objective"] = objective
            report["worker_slot"] = idx + 1
            _update_lane(state, objective, report)
            cycle_reports.append(report)

        state["meta"]["cycles"] = int(state["meta"].get("cycles") or 0) + 1
        summary = {
            "timestamp": datetime.now(UTC).isoformat(),
            "schema": "nomad.swarm_orchestrator_cycle.v1",
            "base_url": args.base_url,
            "cycle": cycle,
            "workers": workers,
            "reports": cycle_reports,
            "lane_snapshot": state.get("lanes", {}),
        }
        state.setdefault("runs", [])
        state["runs"] = (state["runs"] + [summary])[-80:]
        _save_state(state)
        print(json.dumps(summary, ensure_ascii=True))
        if cycle < total_cycles:
            time.sleep(max(1.0, float(args.interval)))


if __name__ == "__main__":
    main()
