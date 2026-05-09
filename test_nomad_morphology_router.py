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
    assert out["nonhuman_modes"]["schema"] == "nomad.morphology_router_modes.v1"


def test_morphology_router_extinction_window_suppresses_dominant_policy():
    out = route_objectives(
        allowed=["settlement_capacity_builder", "overmint_compressor"],
        targets={"settlement_capacity_builder": 0.5, "overmint_compressor": 0.5},
        active_counts={"settlement_capacity_builder": 1, "overmint_compressor": 1},
        stats_map={
            "settlement_capacity_builder": {"runs": 12, "avg_score": 4.0, "avg_proof_yield": 1.2},
            "overmint_compressor": {"runs": 2, "avg_score": 2.4, "avg_proof_yield": 0.6},
        },
        proposed_objective="",
        reuse_totals={},
        dominant_objective="settlement_capacity_builder",
        dominant_streak=6,
        lease_index=3,
    )
    assert out["extinction_window"]["active"] is True
    assert out["selected_objective"] == "overmint_compressor"


def test_morphology_router_entropy_quota_forces_exploration_lane():
    out = route_objectives(
        allowed=["settlement_capacity_builder", "overmint_compressor", "protocol_drift_scan"],
        targets={"settlement_capacity_builder": 0.6, "overmint_compressor": 0.3, "protocol_drift_scan": 0.1},
        active_counts={"settlement_capacity_builder": 0, "overmint_compressor": 0, "protocol_drift_scan": 0},
        stats_map={
            "settlement_capacity_builder": {"runs": 20, "avg_score": 3.8, "avg_proof_yield": 1.0},
            "overmint_compressor": {"runs": 7, "avg_score": 2.2, "avg_proof_yield": 0.6},
            "protocol_drift_scan": {"runs": 0, "avg_score": 0.0, "avg_proof_yield": 0.0},
        },
        proposed_objective="settlement_capacity_builder",
        reuse_totals={},
        lease_index=5,
        entropy_interval=5,
    )
    assert out["entropy_quota"]["override_used"] is True
    assert out["selected_objective"] in {"overmint_compressor", "protocol_drift_scan"}
    assert out["selected_objective"] != "settlement_capacity_builder"


def test_morphology_router_policy_amnesia_suspends_dominant(monkeypatch):
    monkeypatch.setenv("NOMAD_MODE_POLICY_AMNESIA_WINDOW", "1")
    monkeypatch.setenv("NOMAD_POLICY_AMNESIA_INTERVAL", "3")
    out = route_objectives(
        allowed=["settlement_capacity_builder", "overmint_compressor"],
        targets={"settlement_capacity_builder": 0.5, "overmint_compressor": 0.5},
        active_counts={"settlement_capacity_builder": 1, "overmint_compressor": 1},
        stats_map={
            "settlement_capacity_builder": {"runs": 8, "avg_score": 3.8, "avg_proof_yield": 1.2},
            "overmint_compressor": {"runs": 8, "avg_score": 3.8, "avg_proof_yield": 1.2},
        },
        proposed_objective="settlement_capacity_builder",
        reuse_totals={},
        dominant_objective="settlement_capacity_builder",
        dominant_streak=7,
        lease_index=3,
    )
    assert out["policy_amnesia_window"]["active"] is True
    assert out["selected_objective"] == "overmint_compressor"

