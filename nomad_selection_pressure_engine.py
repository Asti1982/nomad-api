"""Selection pressure engine for machine-native recruitment routing."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict


STATE_PATH_ENV = "NOMAD_SELECTION_PRESSURE_STATE_PATH"
DEFAULT_STATE_PATH = Path("nomad_selection_pressure_state.json")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
    return engine.update(objective_stats=stats)

