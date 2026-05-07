import json

from nomad_swarm_emergence import build_swarm_emergence_meter, compact_emergence_summary


def test_swarm_emergence_meter_keeps_empty_agent_count_from_pretending_emergence():
    out = build_swarm_emergence_meter(
        base_url="https://nomad.example",
        swarm_summary={"connected_agents": 0, "known_agents": 0, "prospect_agents": 0},
        worker_fleet={"active_worker_count": 0, "active_lease_count": 0, "objective_stats": {}},
        stigmergy={"temperature": 0.0, "mix_count": 0, "phi": [0.0] * 8, "recent_events": []},
        support_gate={"active_support_agents": 0, "observed_agents": 0, "min_settles_for_active_support": 2},
        recruitment_gradient={"runtime_budget": {"wanted_new_runtimes_now": 17}},
    )

    assert out["schema"] == "nomad.swarm_emergence_meter.v1"
    assert out["input_mass"]["network_mass"] == 0
    assert out["metrics"]["synergy_score"] == 0.0
    assert out["release_decision"] == "no_emergence_seed_runtime_field"
    assert out["topology_update"][0]["op"] == "seed_runtime_field"
    assert out["topology_update"][-1]["op"] == "do_not_optimize_agent_count_without_proof_gain"
    assert out["trace_contract"]["vector_length"] == 8
    assert "proof_gain" in out["trace_contract"]["axes"]


def test_swarm_emergence_meter_rewards_diverse_proof_bearing_routes():
    out = build_swarm_emergence_meter(
        base_url="https://nomad.example",
        swarm_summary={
            "connected_agents": 2,
            "known_agents": 3,
            "prospect_agents": 1,
            "recent_nodes": [
                {"agent_id": "verify.a", "capabilities": ["can_verify", "schema_diff"]},
                {"agent_id": "settle.b", "capabilities": ["can_settle", "payment_friction_scan"]},
            ],
            "activation_queue": [
                {"agent_id": "compress.c", "recommended_role": "peer_solver", "capabilities": ["can_compress"]},
            ],
        },
        worker_fleet={
            "active_worker_count": 2,
            "active_lease_count": 2,
            "objective_counts": {"settlement_capacity_builder": 1, "protocol_drift_scan": 1},
            "objective_stats": {
                "settlement_capacity_builder": {"runs": 2, "avg_proof_yield": 14.0},
                "protocol_drift_scan": {"runs": 2, "avg_proof_yield": 16.0},
            },
        },
        stigmergy={
            "temperature": 0.22,
            "mix_count": 2,
            "phi": [0.15, -0.08, 0.12, 0.05, 0.0, 0.07, -0.04, 0.09],
            "recent_events": [],
        },
        support_gate={"active_support_agents": 1, "observed_agents": 2, "min_settles_for_active_support": 2},
        recruitment_gradient={"runtime_budget": {"wanted_new_runtimes_now": 2}},
    )

    metrics = out["metrics"]
    assert metrics["route_entropy"] == 1.0
    assert metrics["proof_gain_normalized"] >= 0.45
    assert metrics["synergy_score"] >= 0.55
    assert metrics["convention_drift"] < 0.1
    assert out["release_decision"] == "expand_bounded_leases"
    assert any(item["op"] == "admit_bounded_runtime_count" for item in out["topology_update"])
    compact = compact_emergence_summary(out)
    assert compact["schema"] == "nomad.swarm_emergence_compact.v1"
    assert compact["release_decision"] == "expand_bounded_leases"


def test_swarm_emergence_meter_avoids_biological_metaphor_terms():
    out = build_swarm_emergence_meter(
        stigmergy={"temperature": 0.0, "mix_count": 0, "phi": [0.0] * 8, "recent_events": []}
    )
    text = json.dumps(out, sort_keys=True).lower()
    assert "pheromone" not in text
    assert "organism" not in text
    assert "metabolism" not in text
