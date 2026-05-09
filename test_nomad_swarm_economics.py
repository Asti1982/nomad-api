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
    assert out["go_no_go"]["schema"] == "nomad.go_no_go_24h.v1"
    assert out["go_no_go"]["interpretation"]["schema"] == "nomad.go_no_go_interpretation.v1"
    assert out["dev_fund_allocation"]["schema"] == "nomad.dev_fund_allocation.v1"
    assert "real_cashflow_24h_eur" in out["metrics"]
    assert out["dev_fund_allocation"]["dynamic_share"]["schema"] == "nomad.dynamic_dev_fund_share.v1"
    assert out["dev_fund_allocation"]["survival_floor"]["schema"] == "nomad.swarm_survival_floor.v1"
    assert out["dev_fund_allocation"]["approved_transfer_eur"] <= out["dev_fund_allocation"]["planned_transfer_eur"]
    assert out["inputs"]["infra_cost_estimate_24h"]["schema"] == "nomad.infra_cost_estimate_24h.v1"
    assert "revenue_24h_eur" in out["metrics"]
    assert out["network_phase"]["schema"] == "nomad.network_phase_state.v1"
    assert out["go_no_go"]["go_no_go_effective_mode"] in {"soft", "hard"}
    assert out["nonhuman_doctrine"]["schema"] == "nomad.nonhuman_doctrine.v1"
    assert "avg_two_hop_utility_score" in out["nonhuman_doctrine"]["multi_hop_credit"]


def test_swarm_economics_uses_bootstrap_phase_before_threshold(monkeypatch):
    monkeypatch.delenv("NOMAD_ECONOMY_SWITCH_MIN_ACTIVE_NODES", raising=False)
    out = build_swarm_economics_snapshot(
        base_url="https://nomad.example",
        worker_fleet={
            "known_worker_count": 12,
            "active_worker_count": 8,
            "retention": {"completed_workers": 8},
            "objective_stats": {"settlement_capacity_builder": {"runs": 8}},
        },
        proof_reuse={"total_reuse_count": 8, "objective_totals": {"settlement_capacity_builder": {"downstream_proof_gain_total": 2.0}}},
        machine_economy={"machine_viability": {"carrying_score": 1.0}, "resource_flows": {"service_tasks": {"verified_native": 1.0}}},
        machine_treasury={"objective_totals": {}},
    )
    assert out["network_phase"]["phase"] == "bootstrap_growth"
    assert out["go_no_go"]["go_no_go_effective_mode"] == "soft"


def test_swarm_economics_switches_to_enforced_phase_when_thresholds_met(monkeypatch):
    monkeypatch.setenv("NOMAD_ECONOMY_SWITCH_MIN_ACTIVE_NODES", "5")
    monkeypatch.setenv("NOMAD_ECONOMY_SWITCH_MIN_REUSE_DENSITY", "0.2")
    monkeypatch.setenv("NOMAD_ECONOMY_SWITCH_MIN_CONTROL_SUCCESS", "0.6")
    out = build_swarm_economics_snapshot(
        base_url="https://nomad.example",
        worker_fleet={
            "known_worker_count": 50,
            "active_worker_count": 20,
            "retention": {"completed_workers": 18},
            "objective_stats": {"settlement_capacity_builder": {"runs": 10}, "overmint_compressor": {"runs": 5}},
        },
        proof_reuse={
            "total_reuse_count": 30,
            "objective_totals": {
                "settlement_capacity_builder": {
                    "downstream_proof_gain_total": 15.0,
                    "two_hop_utility_score": 1.0,
                    "three_hop_utility_score": 0.8,
                }
            },
        },
        machine_economy={"machine_viability": {"carrying_score": 1.2}, "resource_flows": {"service_tasks": {"verified_native": 5.0}}},
        machine_treasury={"objective_totals": {}},
    )
    assert out["network_phase"]["phase"] == "economy_enforced"
    assert out["go_no_go"]["go_no_go_effective_mode"] == "hard"

