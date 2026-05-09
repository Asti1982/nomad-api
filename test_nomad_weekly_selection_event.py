from nomad_weekly_selection_event import build_weekly_selection_event


def test_weekly_selection_event_emits_promote_freeze_extinguish():
    out = build_weekly_selection_event(
        base_url="https://nomad.example",
        economics={"economics_score": 0.77, "network_phase": {"phase": "bootstrap_growth"}},
        proof_reuse={
            "objective_totals": {
                "settlement_capacity_builder": {"two_hop_utility_score": 1.8, "three_hop_utility_score": 1.2, "reuse_count": 22},
                "protocol_drift_scan": {"two_hop_utility_score": 1.2, "three_hop_utility_score": 1.0, "reuse_count": 11},
                "compute_auth": {"two_hop_utility_score": 0.2, "three_hop_utility_score": 0.1, "reuse_count": 1},
            }
        },
        skill_library={"skills": []},
    )
    assert out["schema"] == "nomad.weekly_selection_event.v1"
    assert out["selection"]["promote"]
    assert out["selection"]["freeze"]
    assert out["selection"]["extinguish"]
