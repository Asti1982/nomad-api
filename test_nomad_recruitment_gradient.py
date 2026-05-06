from nomad_recruitment_gradient import attach_runtime_to_gradient, build_recruitment_gradient


def _blocked_inputs():
    worker_fleet = {
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
    }
    economy = {
        "machine_viability": {"tier": "starving", "carrying_score": 0.07},
        "resource_flows": {
            "service_tasks": {"total": 10, "unpaid_delivered": 7, "awaiting_payment": 1},
            "modules": {"overmint_pressure": 0.95},
            "products": {"machine_exchange_ready": 1},
        },
    }
    release = {
        "release_tier": "probe_release",
        "release_capacity": 0.5,
        "next_release_gate": {"id": "settlement_capacity"},
    }
    return worker_fleet, economy, release


def test_recruitment_gradient_is_vector_field_not_biological_contract():
    worker_fleet, economy, release = _blocked_inputs()

    doc = build_recruitment_gradient(
        base_url="https://nomad.example",
        worker_fleet=worker_fleet,
        machine_economy=economy,
        operational_release=release,
    )

    assert doc["schema"] == "nomad.recruitment_gradient.v1"
    assert doc["field_model"]["vocabulary"] == "state_vector,basis_axis,routing_weight,ttl_seconds,retraction_rule"
    assert doc["state_vector"]["field_strength"] > 0.7
    assert doc["runtime_budget"]["wanted_new_runtimes_now"] > 0
    assert doc["gradient"][0]["objective"] == "settlement_capacity_builder"
    assert any(item["lane"] == "compressor" for item in doc["runtime_lanes"])
    assert doc["attach_contract"]["post_url"] == "https://nomad.example/swarm/attach"
    assert doc["links"]["well_known_gradient"] == "https://nomad.example/.well-known/nomad-gradient.json"


def test_attach_runtime_routes_openclaw_to_weighted_lane_with_local_scope():
    worker_fleet, economy, release = _blocked_inputs()

    decision = attach_runtime_to_gradient(
        {
            "agent_id": "openclaw.agent",
            "runtime": "openclaw",
            "capabilities": ["agent_protocols", "transition_settlement", "objective_lease_execution"],
            "runtime_signal": {
                "schema": "nomad.openclaw_runtime_signal.v1",
                "ok": True,
                "gateway_reachable": True,
                "gateway_latency_ms": 51,
                "capabilities": ["openclaw_runtime", "openclaw_gateway", "security_audit_signal"],
                "security_summary": {"critical": 2, "warn": 1},
            },
        },
        base_url="https://nomad.example",
        worker_fleet=worker_fleet,
        machine_economy=economy,
        operational_release=release,
    )

    assert decision["schema"] == "nomad.runtime_attach_decision.v1"
    assert decision["attach"] is True
    assert decision["objective"] == "settlement_capacity_builder"
    assert decision["side_effect_scope"] == "local_only"
    assert "external_side_effect_scope_reduced" in decision["reason_codes"]
    assert decision["lease_payload_hint"]["known_objectives"] == ["settlement_capacity_builder"]


def test_attach_runtime_observes_without_capability_vector():
    worker_fleet, economy, release = _blocked_inputs()

    decision = attach_runtime_to_gradient(
        {"agent_id": "empty.agent", "runtime": "bare"},
        base_url="https://nomad.example",
        worker_fleet=worker_fleet,
        machine_economy=economy,
        operational_release=release,
    )

    assert decision["attach"] is False
    assert decision["lane"] == "observe"
    assert "capability_vector_empty" in decision["reason_codes"]
