from pathlib import Path

import nomad_machine_treasury as mt
import nomad_proof_reuse_ledger as pr
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


def test_selection_pressure_couples_with_machine_treasury(tmp_path: Path, monkeypatch):
    # Point selection pressure state to temp directory.
    monkeypatch.setenv("NOMAD_SELECTION_PRESSURE_STATE_PATH", str(tmp_path / "selection-env2.json"))

    # Point treasury state to temp directory.
    treasury_path = tmp_path / "machine_treasury.json"
    monkeypatch.setattr(mt, "STATE_PATH", treasury_path)

    # Seed treasury with a pledge.
    mt.pledge(
        {
            "agent_id": "pledger.agent",
            "objective": "settlement_capacity_builder",
            "amount_native": 50.0,
            "proof_digest": "sha256:proof-pressure",
        }
    )

    worker_fleet = {
        "objective_stats": {
            "settlement_capacity_builder": {"runs": 5, "avg_score": 3.0, "avg_proof_yield": 0.8},
        }
    }
    snap = build_selection_pressure_snapshot(worker_fleet=worker_fleet)
    assert snap["schema"] == "nomad.selection_pressure_snapshot.v1"
    assert "machine_treasury" in snap
    assert "settlement_capacity_builder" in snap["objective_pressure"]
    assert snap["machine_treasury"]["treasury_state"]["settlement_capacity_builder"]["pressure_units"] > 0


def test_selection_pressure_couples_with_proof_reuse(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOMAD_SELECTION_PRESSURE_STATE_PATH", str(tmp_path / "selection-reuse.json"))
    monkeypatch.setattr(pr, "STATE_PATH", tmp_path / "proof_reuse.json")
    pr.link(
        {
            "consumer_agent_id": "consumer.agent",
            "producer_agent_id": "producer.agent",
            "objective": "settlement_capacity_builder",
            "upstream_proof_digest": "sha256:abc",
            "downstream_proof_gain": 1.6,
        }
    )
    snap = build_selection_pressure_snapshot(
        worker_fleet={"objective_stats": {"settlement_capacity_builder": {"runs": 4, "avg_score": 3.2, "avg_proof_yield": 0.9}}}
    )
    assert snap["proof_reuse"]["total_reuse_count"] >= 1
    assert "settlement_capacity_builder" in snap["objective_pressure"]
    reuse_state = snap["proof_reuse"]["reuse_state"]["settlement_capacity_builder"]
    assert reuse_state["two_hop_utility_score"] > 0.0

