from nomad_swarm_attractor import build_swarm_attractor_contract


def test_swarm_attractor_prioritizes_settlement_and_overmint():
    doc = build_swarm_attractor_contract(
        base_url="https://nomad.example",
        worker_fleet={
            "active_worker_count": 2,
            "known_worker_count": 3,
            "active_lease_count": 1,
            "objective_counts": {"emergence_release_probe": 1},
            "objective_targets": {
                "settlement_capacity_builder": 0.36,
                "overmint_compressor": 0.2,
                "protocol_drift_scan": 0.1,
                "emergence_release_probe": 0.1,
            },
        },
        machine_economy={
            "machine_viability": {"tier": "starving", "carrying_score": 0.07},
            "resource_flows": {
                "service_tasks": {"total": 10, "unpaid_delivered": 7},
                "modules": {"overmint_pressure": 0.95},
                "products": {"machine_exchange_ready": 5},
            },
        },
        operational_release={
            "release_tier": "probe_release",
            "release_capacity": 0.5,
            "next_release_gate": {"id": "settlement_capacity"},
        },
    )

    assert doc["schema"] == "nomad.swarm_attractor.v1"
    assert doc["metabolism_pressure"] > 0.7
    assert doc["replication_budget"]["wanted_new_workers_now"] == 9
    assert doc["worker_mix"][0]["objective"] == "settlement_capacity_builder"
    assert any(item["objective"] == "overmint_compressor" for item in doc["worker_mix"])
    assert doc["links"]["lease"] == "https://nomad.example/swarm/workers/lease"
    assert "/swarm/workers/lease" in doc["agent_recruitment_packet"]["boot_order"][-1]
    assert "placeholder URL" in doc["emergence_production"]["retraction_conditions"]
    assert doc["emergence_production"]["lease_decay"]["machine_note"].startswith("No agent death")
    assert {item["lane"] for item in doc["agent_attachment_lanes"]} >= {
        "worker_loop",
        "verifier",
        "compressor",
        "settlement_adapter",
    }
    assert doc["self_allocation_protocol"]["policy"] == "agents_pick_lane_from_capability_vector_not_social_role"
