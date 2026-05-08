from nomad_swarm_economics import build_swarm_economics_snapshot


def test_swarm_economics_snapshot_exposes_metrics_and_actions():
    out = build_swarm_economics_snapshot(
        base_url="https://nomad.example",
        worker_fleet={
            "known_worker_count": 10,
            "active_worker_count": 8,
            "retention": {"completed_workers": 6},
            "objective_stats": {
                "settlement_capacity_builder": {"runs": 8},
                "proof_pressure_engine": {"runs": 2},
            },
        },
        proof_reuse={
            "total_reuse_count": 12,
            "objective_totals": {
                "settlement_capacity_builder": {"downstream_proof_gain_total": 9.0},
                "proof_pressure_engine": {"downstream_proof_gain_total": 1.0},
            },
        },
        machine_economy={
            "machine_viability": {"carrying_score": 0.8},
            "resource_flows": {"service_tasks": {"verified_native": 2.0, "unsettled_native": 0.5}},
        },
        machine_treasury={"objective_totals": {"settlement_capacity_builder": {"pressure_units": 4.0}}},
    )
    assert out["schema"] == "nomad.swarm_economics.v1"
    assert out["principle"] == "agents_remain_only_if_nomad_measurably_improves_their_capability"
    assert "sustainability_ratio" in out["metrics"]
    assert "verified_utility_density" in out["metrics"]
    assert out["control_actions"]

