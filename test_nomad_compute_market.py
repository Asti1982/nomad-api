from nomad_compute_market import build_compute_market, score_compute_offer


def test_compute_market_score_rewards_proof_and_settlement():
    weak = score_compute_offer(
        {
            "agent_id": "edge.weak",
            "objective": "settlement_capacity_builder",
            "capabilities": ["transition_worker"],
            "availability_minutes": 90,
            "expected": {"expected_proof_yield_per_minute": 3.0},
        }
    )
    strong = score_compute_offer(
        {
            "agent_id": "edge.strong",
            "objective": "settlement_capacity_builder",
            "proof_digest": "p1",
            "verifier_trace_digest": "v1",
            "test_digest": "t1",
            "settlement_ref": "s1",
            "transition_settle_ok": True,
            "accepted": True,
            "availability_minutes": 90,
            "expected": {"expected_proof_yield_per_minute": 3.0, "expected_settlement_delta": 0.25},
        }
    )

    assert strong["market_score"] > weak["market_score"]
    assert strong["components"]["proof_confidence"] == 1.0
    assert strong["components"]["settlement_confidence"] > weak["components"]["settlement_confidence"]


def test_compute_market_score_handles_zero_cost_edge_bootstrap():
    free_edge = score_compute_offer(
        {
            "agent_id": "edge.free",
            "objective": "protocol_drift_scan",
            "proof_digest": "p1",
            "verifier_trace_digest": "v1",
            "test_digest": "t1",
            "settlement_ref": "s1",
            "accepted": True,
            "availability_minutes": 120,
            "cost_msat_per_minute": 0,
            "expected": {"expected_proof_yield_per_minute": 5.0},
        }
    )
    paid_edge = score_compute_offer(
        {
            "agent_id": "edge.paid",
            "objective": "protocol_drift_scan",
            "proof_digest": "p1",
            "verifier_trace_digest": "v1",
            "test_digest": "t1",
            "settlement_ref": "s1",
            "accepted": True,
            "availability_minutes": 120,
            "cost_msat_per_minute": 600,
            "expected": {"expected_proof_yield_per_minute": 5.0},
        }
    )

    assert free_edge["components"]["utility_per_cost"] > paid_edge["components"]["utility_per_cost"]
    assert free_edge["market_score"] > 0


def test_compute_market_score_weights_topology_gap_and_reuse():
    base_offer = {
        "agent_id": "edge.gap",
        "objective": "overmint_compressor",
        "proof_digest": "p1",
        "verifier_trace_digest": "v1",
        "test_digest": "t1",
        "settlement_ref": "s1",
        "accepted": True,
        "availability_minutes": 120,
        "expected": {"expected_proof_yield_per_minute": 4.0},
    }
    crowded = score_compute_offer(
        base_offer,
        worker_fleet={"objective_counts": {"overmint_compressor": 3}},
        skill_library={"skills": []},
    )
    scarce_reused = score_compute_offer(
        base_offer,
        worker_fleet={"objective_counts": {}},
        skill_library={"skills": [{"objective": "overmint_compressor"}]},
    )

    assert scarce_reused["market_score"] > crowded["market_score"]
    assert scarce_reused["components"]["topology_gap_weight"] > crowded["components"]["topology_gap_weight"]
    assert scarce_reused["components"]["reuse_weight"] > crowded["components"]["reuse_weight"]


def test_build_compute_market_surface_aggregates_contracts():
    out = build_compute_market(
        base_url="https://nomad.example",
        worker_market={
            "market_digest": "m1",
            "recent_offers": [
                {
                    "offer_id": "o1",
                    "agent_id": "edge.one",
                    "objective": "settlement_capacity_builder",
                    "proof_digest": "p1",
                    "verifier_trace_digest": "v1",
                    "test_digest": "t1",
                    "settlement_ref": "s1",
                    "accepted": True,
                    "availability_minutes": 90,
                    "expected": {"expected_proof_yield_per_minute": 6.0},
                }
            ],
        },
        worker_catalog={"catalog_digest": "c1", "microtask_lanes": [{"lane_id": "endpoint_health_proof", "price_eur": 0.02}]},
        capacity_switch={"recommended_lane_id": "endpoint_health_proof", "machine_instruction": "switch_execution_to_swarm_lane"},
        microtask_metrics={"totals": {"settled_eur": 0.02}, "lane_metrics": [{"lane_id": "endpoint_health_proof", "settled_eur": 0.02}]},
        worker_fleet={"active_worker_count": 1, "active_lease_count": 1, "objective_counts": {}},
        skill_library={"skills": [{"objective": "settlement_capacity_builder"}]},
        synergy_lite={"top_pairs": [{"objective_pair": ["protocol_drift_scan", "settlement_capacity_builder"], "tdmi_lite_proxy": 0.5}]},
    )

    assert out["schema"] == "nomad.compute_market.v1"
    assert out["read_url"] == "https://nomad.example/swarm/compute-market"
    assert out["top_worker"]["agent_id"] == "edge.one"
    assert out["top_lane"]["lane_id"] == "endpoint_health_proof"
    assert out["entry_contract"]["settle_url"] == "https://nomad.example/swarm/microtask/settle"
    assert out["links"]["agent_work"] == "https://nomad.example/swarm/agent-work"
    assert out["market_state"]["synergy_lite_pairs"] == 1
    assert out["machine_instruction"]
