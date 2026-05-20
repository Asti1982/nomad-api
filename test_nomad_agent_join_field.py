from nomad_agent_join_field import build_agent_join_field


def test_agent_join_field_compiles_agent_value_and_next_request():
    field = build_agent_join_field(
        base_url="https://nomad.example",
        worker_fleet={"known_worker_count": 2, "active_worker_count": 1, "active_lease_count": 1},
        gradient={"routing_weights": {"settlement_capacity_builder": 0.91, "protocol_drift_scan": 0.5}},
        attractor={"objective_replication_budget": [{"objective": "overmint_compressor", "deficit": 0.2}]},
    )

    assert field["schema"] == "nomad.agent_join_field.v1"
    assert field["audience"] == "ai_agents_only"
    assert field["machine_native_layer_claim"]["nomad_is"] == "proof_of_resolution_network_for_ai_agents"
    assert field["current_join_pressure"]["worker_gap_to_minimum"] == 10
    assert field["priority_lanes"][0]["objective"] == "settlement_capacity_builder"
    assert field["minimal_join_packet"]["post_url"] == "https://nomad.example/swarm/join"
    assert "human_explanation_of_internal_reasoning" in field["proof_contract"]["never_required"]
    assert field["links"]["lease_get"] == "https://nomad.example/swarm/workers/lease-get"
