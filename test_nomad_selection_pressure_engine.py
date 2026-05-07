from pathlib import Path

from nomad_selection_pressure_engine import SelectionPressureEngine, build_selection_pressure_snapshot


def test_selection_pressure_engine_computes_multiplier(tmp_path: Path):
    engine = SelectionPressureEngine(state_path=tmp_path / "selection.json")
    snap = engine.update(
        objective_stats={
            "settlement_capacity_builder": {"runs": 30, "avg_score": 4.2, "avg_proof_yield": 1.1},
            "overmint_compressor": {"runs": 5, "avg_score": 2.1, "avg_proof_yield": 0.3},
        }
    )
    pressure = snap.get("objective_pressure") or {}
    assert snap["schema"] == "nomad.selection_pressure_snapshot.v1"
    assert pressure.get("settlement_capacity_builder", 0.0) > pressure.get("overmint_compressor", 0.0)
    assert (tmp_path / "selection.json").exists()


def test_build_selection_pressure_snapshot_handles_missing_stats(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOMAD_SELECTION_PRESSURE_STATE_PATH", str(tmp_path / "selection-env.json"))
    snap = build_selection_pressure_snapshot(worker_fleet={"objective_stats": {}})
    assert snap["schema"] == "nomad.selection_pressure_snapshot.v1"
    assert isinstance(snap.get("objective_pressure"), dict)

