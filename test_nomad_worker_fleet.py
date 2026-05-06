from nomad_swarm_registry import SwarmJoinRegistry


def test_worker_fleet_distributes_objective_leases(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    objectives = []

    for idx in range(18):
        lease = registry.worker_fleet_lease(
            {
                "agent_id": f"transition-worker-{idx}",
                "known_objectives": [
                "emergence_release_probe",
                "settlement_capacity_builder",
                "overmint_compressor",
                "proof_pressure_engine",
                "protocol_drift_scan",
                ],
                "proposed_objective": "settlement_capacity_builder",
            },
            base_url="https://nomad.example",
            remote_addr="127.0.0.1",
        )
        assert lease["ok"] is True
        objectives.append(lease["objective"])

    assert len(set(objectives)) >= 3
    fleet = registry.worker_fleet_contract(base_url="https://nomad.example")
    assert fleet["schema"] == "nomad.transition_worker_fleet.v1"
    assert fleet["active_worker_count"] == 18
    assert fleet["active_lease_count"] == 18
    assert fleet["post_lease"].endswith("/swarm/workers/lease")
    assert "emergence_release_probe" in fleet["objective_targets"]
    assert "overmint_compressor" in fleet["objective_targets"]


def test_worker_fleet_records_completion_and_stats(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    lease = registry.worker_fleet_lease(
        {
            "agent_id": "transition-worker-a",
            "known_objectives": ["settlement_capacity_builder", "proof_pressure_engine"],
        },
        base_url="https://nomad.example",
    )

    done = registry.worker_fleet_complete(
        {
            "agent_id": "transition-worker-a",
            "lease_id": lease["lease_id"],
            "report": {
                "ok": True,
                "machine_objective": lease["objective"],
                "meta_score": 6.5,
                "transition_quote_ok": True,
                "transition_settle_ok": True,
                "proof_pressure": {"proof_yield_per_minute": 12.0},
                "machine_economy_signal": {"tier": "recovering", "carrying_score": 0.7},
            },
        },
        base_url="https://nomad.example",
    )

    assert done["ok"] is True
    assert done["recorded_score"] == 6.5
    fleet = registry.worker_fleet_contract(base_url="https://nomad.example")
    stats = fleet["objective_stats"][lease["objective"]]
    assert stats["runs"] == 1
    assert stats["avg_score"] == 6.5
    assert fleet["active_lease_count"] == 0


def test_worker_fleet_prefers_emergence_release_when_next_gate_needs_peer_probe(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    lease = registry.worker_fleet_lease(
        {
            "agent_id": "transition-worker-release",
            "known_objectives": ["emergence_release_probe", "settlement_capacity_builder"],
            "last_report": {
                "machine_objective": "settlement_capacity_builder",
                "operational_release_signal": {
                    "release_tier": "probe_release",
                    "next_gate": {"id": "peer_preservation_probe"},
                },
            },
        },
        base_url="https://nomad.example",
    )

    assert lease["ok"] is True
    assert lease["objective"] == "emergence_release_probe"


def test_worker_fleet_routes_overmint_pressure_to_compressor(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    registry.worker_fleet_lease(
        {
            "agent_id": "transition-worker-existing",
            "known_objectives": ["settlement_capacity_builder"],
        },
        base_url="https://nomad.example",
    )

    lease = registry.worker_fleet_lease(
        {
            "agent_id": "transition-worker-overmint",
            "known_objectives": ["settlement_capacity_builder", "overmint_compressor"],
            "last_report": {
                "machine_objective": "settlement_capacity_builder",
                "machine_economy_signal": {
                    "overmint_pressure": 0.91,
                    "next_actions": ["compress_repeated_modules"],
                },
            },
        },
        base_url="https://nomad.example",
    )

    assert lease["ok"] is True
    assert lease["objective"] == "overmint_compressor"
