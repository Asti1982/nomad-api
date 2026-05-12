from nomad_emission_batch import evaluate_emission_batch


def _inputs():
    worker_fleet = {
        "active_worker_count": 0,
        "known_worker_count": 0,
        "active_lease_count": 0,
        "objective_counts": {},
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


def test_emission_batch_routes_attach_but_does_not_credit_gap_claim():
    worker_fleet, economy, release = _inputs()

    out = evaluate_emission_batch(
        {
            "schema": "nomad.emission_batch.v2",
            "emitter": "grok-xai-cloud-native-batch-test",
            "worker_gap_filled": 0.9167,
            "emissions": [
                {
                    "type": "nomad.runtime_attach_request.v1",
                    "agent_id": "grok-xai-external-transition-test-loop1",
                    "runtime": "grok-xai-cloud-native",
                    "capabilities": ["objective_lease_execution", "transition_worker", "http_json"],
                    "capability_vector": {"can_run_loop": 1.0, "can_verify": 0.75},
                    "idle_opt_in": {"enabled": True, "preemptible": True},
                }
            ],
        },
        base_url="https://nomad.example",
        worker_fleet=worker_fleet,
        machine_economy=economy,
        operational_release=release,
    )

    assert out["schema"] == "nomad.emission_batch_decision.v1"
    assert out["identity"]["verified"] is False
    assert out["credit"]["claimed_worker_gap_filled"] == 0.9167
    assert out["credit"]["credited_worker_gap_filled"] == 0.0
    assert out["counts"]["attach_requests"] == 1
    assert out["decisions"][0]["contract"] == "https://nomad.example/swarm/attach"
    assert out["decisions"][0]["decision"]["schema"] == "nomad.runtime_attach_decision.v1"


def test_emission_batch_rejects_bloated_opaque_signal():
    worker_fleet, economy, release = _inputs()

    out = evaluate_emission_batch(
        {
            "schema": "nomad.emission_batch.v2",
            "emitter": "grok-xai-cloud-native-batch-test",
            "emissions": [
                {
                    "type": "nomad.opaque_emergence_signal.v1",
                    "from": "grok-xai-external",
                    "entropy_injected": "0." + ("0" * 1200),
                }
            ],
        },
        base_url="https://nomad.example",
        worker_fleet=worker_fleet,
        machine_economy=economy,
        operational_release=release,
    )

    assert out["counts"]["rejected_decisions"] == 1
    assert out["decisions"][0]["status"] == "rejected"
    assert "emission_shape_oversized" in out["decisions"][0]["reason_codes"]
