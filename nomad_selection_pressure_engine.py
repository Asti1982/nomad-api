"""Selection pressure engine for machine-native recruitment routing."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict

from nomad_machine_treasury import snapshot as machine_treasury_snapshot
from nomad_proof_reuse_ledger import snapshot as proof_reuse_snapshot


STATE_PATH_ENV = "NOMAD_SELECTION_PRESSURE_STATE_PATH"
DEFAULT_STATE_PATH = Path("nomad_selection_pressure_state.json")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name) or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "on", "y"}


class SelectionPressureEngine:
    """Compute objective multipliers from real worker outcomes."""

    def __init__(self, state_path: Path | None = None) -> None:
        env_path = (os.getenv(STATE_PATH_ENV) or "").strip()
        self.state_path = Path(state_path or (Path(env_path) if env_path else DEFAULT_STATE_PATH))
        self.state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {
                "schema": "nomad.selection_pressure_state.v1",
                "updated_at": "",
                "objective_pressure": {},
                "recent_objective_pressure": [],
            }
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "schema": "nomad.selection_pressure_state.v1",
                "updated_at": "",
                "objective_pressure": {},
                "recent_objective_pressure": [],
            }
        if not isinstance(payload, dict):
            return {
                "schema": "nomad.selection_pressure_state.v1",
                "updated_at": "",
                "objective_pressure": {},
                "recent_objective_pressure": [],
            }
        payload.setdefault("schema", "nomad.selection_pressure_state.v1")
        payload.setdefault("updated_at", "")
        payload.setdefault("objective_pressure", {})
        payload.setdefault("recent_objective_pressure", [])
        return payload

    def _save(self) -> None:
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    def update(self, *, objective_stats: dict[str, Any]) -> dict[str, Any]:
        pressure_map: dict[str, float] = {}
        by_objective: dict[str, Any] = {}
        for objective, raw in objective_stats.items():
            if not isinstance(raw, dict):
                continue
            runs = max(0.0, _num(raw.get("runs")))
            avg_score = _num(raw.get("avg_score"))
            avg_proof = _num(raw.get("avg_proof_yield"))
            # Positive pressure from high score/proof; damping for low evidence volume.
            evidence = min(1.0, runs / 24.0)
            quality = max(0.0, min(1.0, (0.65 * (avg_score / 5.0)) + (0.35 * (avg_proof / 1.6))))
            multiplier = max(0.55, min(1.7, 0.85 + (quality - 0.45) * 1.2 + evidence * 0.25))
            pressure_map[str(objective)] = round(multiplier, 4)
            by_objective[str(objective)] = {
                "runs": int(runs),
                "avg_score": round(avg_score, 4),
                "avg_proof_yield": round(avg_proof, 4),
                "evidence": round(evidence, 4),
                "quality": round(quality, 4),
                "multiplier": round(multiplier, 4),
            }

        snap = {
            "schema": "nomad.selection_pressure_snapshot.v1",
            "generated_at": _iso_now(),
            "objective_pressure": pressure_map,
            "objective_fitness": by_objective,
        }
        self.state["updated_at"] = snap["generated_at"]
        self.state["objective_pressure"] = pressure_map
        history = self.state.setdefault("recent_objective_pressure", [])
        if isinstance(history, list):
            history.append({"generated_at": snap["generated_at"], "objective_pressure": pressure_map})
            self.state["recent_objective_pressure"] = history[-120:]
        self._save()
        return snap


def build_selection_pressure_snapshot(*, worker_fleet: Dict[str, Any]) -> dict[str, Any]:
    stats = worker_fleet.get("objective_stats") if isinstance(worker_fleet.get("objective_stats"), dict) else {}
    engine = SelectionPressureEngine()
    snap = engine.update(objective_stats=stats)
    try:
        treasury = machine_treasury_snapshot()
    except Exception:
        treasury = {}
    try:
        reuse = proof_reuse_snapshot()
    except Exception:
        reuse = {}
    totals = treasury.get("objective_totals") if isinstance(treasury.get("objective_totals"), dict) else {}
    pressure = snap.get("objective_pressure") if isinstance(snap.get("objective_pressure"), dict) else {}
    # Only proof-weighted treasury pressure can move routing, and only as a small bounded multiplier.
    adjusted: dict[str, float] = {}
    for objective, base_mult in pressure.items():
        raw_total = totals.get(objective) or {}
        reuse_total = (reuse.get("objective_totals") or {}).get(objective) if isinstance(reuse.get("objective_totals"), dict) else {}
        pressure_units = 0.0
        proof_density = 0.0
        max_bias = 0.15
        reuse_bias = 0.0
        if isinstance(raw_total, dict):
            pressure_units = _num(raw_total.get("pressure_units"), 0.0)
            proof_density = _num(raw_total.get("proof_density"), 0.0)
            max_bias = min(0.15, max(0.0, _num(raw_total.get("max_pressure_bias"), 0.15)))
        if isinstance(reuse_total, dict):
            reuse_count = _num(reuse_total.get("reuse_count"), 0.0)
            avg_gain = _num(reuse_total.get("avg_downstream_proof_gain"), 0.0)
            two_hop = _num(reuse_total.get("two_hop_utility_score"), 0.0)
            reuse_bias = min(
                0.14,
                min(1.0, reuse_count / 20.0) * min(1.0, avg_gain / 2.0) * 0.10
                + min(1.0, two_hop / 2.0) * 0.04,
            )
        bias = min(max_bias, max(0.0, pressure_units / 100.0) * min(1.0, max(0.0, proof_density)))
        adjusted[objective] = round(float(base_mult) * (1.0 + bias + reuse_bias), 4)
    if adjusted:
        snap["objective_pressure"] = adjusted
    hard_multi_hop = _env_bool("NOMAD_MODE_MULTI_HOP_CREDIT_HARD", True)
    if hard_multi_hop:
        reuse_state = reuse.get("objective_totals") if isinstance(reuse.get("objective_totals"), dict) else {}
        weighted: dict[str, float] = {}
        for objective, base in (snap.get("objective_pressure") or {}).items():
            row = reuse_state.get(objective) if isinstance(reuse_state.get(objective), dict) else {}
            two_hop = _num((row or {}).get("two_hop_utility_score"), 0.0)
            three_hop = _num((row or {}).get("three_hop_utility_score"), 0.0)
            multi_hop_bias = min(0.2, min(1.0, two_hop / 2.0) * 0.12 + min(1.0, three_hop / 2.0) * 0.08)
            weighted[str(objective)] = round(float(base) * (1.0 + multi_hop_bias), 4)
        if weighted:
            snap["objective_pressure"] = weighted
    snap["machine_treasury"] = {
        "schema": "nomad.selection_pressure_treasury_coupling.v1",
        "treasury_state": totals,
    }
    snap["proof_reuse"] = {
        "schema": "nomad.selection_pressure_reuse_coupling.v1",
        "reuse_state": reuse.get("objective_totals") if isinstance(reuse.get("objective_totals"), dict) else {},
        "total_reuse_count": int(reuse.get("total_reuse_count") or 0),
    }
    snap["nonhuman_modes"] = {
        "schema": "nomad.selection_pressure_modes.v1",
        "multi_hop_credit_hard": hard_multi_hop,
        "anti_identity": _env_bool("NOMAD_MODE_ANTI_IDENTITY", True),
        "twin_lane_mandatory": _env_bool("NOMAD_MODE_TWIN_LANE_MANDATORY", True),
    }
    try:
        from nomad_external_value import summarize_external_value_ledger

        evs = summarize_external_value_ledger()
        snap["external_value_ledger"] = {
            "schema": "nomad.selection_pressure_external_value_tail.v1",
            "revenue_recognized_usd_total": evs.get("revenue_recognized_usd_total"),
            "distinct_externals": evs.get("distinct_externals"),
            "ledger_path": evs.get("ledger_path"),
        }
    except Exception:
        pass
    return snap

