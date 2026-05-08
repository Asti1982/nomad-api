from nomad_morphology_router import route_objectives


def test_morphology_router_returns_selected_and_twin():
    out = route_objectives(
        allowed=["settlement_capacity_builder", "overmint_compressor", "protocol_drift_scan"],
        targets={"settlement_capacity_builder": 0.4, "overmint_compressor": 0.3, "protocol_drift_scan": 0.3},
        active_counts={"settlement_capacity_builder": 4, "overmint_compressor": 1, "protocol_drift_scan": 1},
        stats_map={
            "settlement_capacity_builder": {"runs": 10, "avg_score": 3.2, "avg_proof_yield": 1.0},
            "overmint_compressor": {"runs": 2, "avg_score": 2.4, "avg_proof_yield": 0.6},
            "protocol_drift_scan": {"runs": 1, "avg_score": 2.1, "avg_proof_yield": 0.5},
        },
        proposed_objective="settlement_capacity_builder",
        reuse_totals={"protocol_drift_scan": {"reuse_count": 4, "avg_downstream_proof_gain": 1.2}},
    )
    assert out["schema"] == "nomad.morphology_router.v1"
    assert out["selected_objective"] in {"overmint_compressor", "protocol_drift_scan"}
    assert out["twin_objective"] in {"settlement_capacity_builder", "overmint_compressor", "protocol_drift_scan"}
    assert out["anti_identity"] == "agent_id_and_source_tag_not_used_for_objective_routing"

