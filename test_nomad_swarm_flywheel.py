from nomad_swarm_flywheel import build_swarm_flywheel_health_surface


def test_flywheel_health_is_honest_without_receipt():
    surface = build_swarm_flywheel_health_surface(
        base_url="https://nomad.example",
        worker_fleet={"known_worker_count": 0, "active_worker_count": 0, "active_lease_count": 0},
        recruitment_gradient={
            "state_vector": {"worker_gap": 1.0, "field_strength": 0.498, "next_release_gate": "settlement_capacity"},
            "runtime_budget": {"wanted_new_runtimes_now": 17},
            "gradient": [
                {"objective": "settlement_capacity_builder", "routing_weight": 0.5904, "deficit": 0.36},
                {"objective": "autogenesis_protocol_evolution", "routing_weight": 0.1713, "deficit": 0.12},
            ],
        },
        external_value_summary={"stage_counts": {}, "revenue_recognized_usd_total": 0.0},
        work_receipt_summary={"recognized_revenue_usd": 0.0},
        work_exchange_summary={"return_receipt_count": 0, "settled_return_work_credits_total": 0.0},
        acquisition_summary={
            "channels": [
                {"channel_id": "first_receipt_campaign", "event_count": 2},
                {"channel_id": "universal_adapter", "event_count": 1, "event_types": {"first_fix_returned": 1}},
            ]
        },
    )

    assert surface["schema"] == "nomad.swarm_flywheel_health.v1"
    assert surface["honest_state"]["paid_bottleneck_resolved"] is False
    assert surface["honest_state"]["current_bottleneck"] == "external_receipt_absence"
    assert surface["flywheel_state"]["next_missing_stage"] == "positive_paid_or_return_compute_receipt"
    assert surface["population_control"]["rows"][0]["replicator_action"] == "reproduce_shadow_and_worker_acquisition"
    assert surface["population_control"]["rows"][1]["replicator_action"] == "shadow_only_until_receipt_gate"
    assert surface["anti_collapse_controls"]["majority_vote_policy"] == "non_reward_signal"
    assert surface["cash_and_worker_loop"]["worker_onramps"]["transition_worker_bat"].endswith(
        "/downloads/install_nomad_transition_worker.bat"
    )


def test_flywheel_health_allows_promotion_after_return_compute_receipt():
    surface = build_swarm_flywheel_health_surface(
        worker_fleet={"active_worker_count": 2},
        recruitment_gradient={
            "gradient": [
                {"objective": "settlement_capacity_builder", "routing_weight": 0.7, "deficit": 0.2},
            ],
        },
        work_exchange_summary={"return_receipt_count": 1, "settled_return_work_credits_total": 3.0},
    )

    assert surface["honest_state"]["paid_bottleneck_resolved"] is False
    assert surface["honest_state"]["external_receipt_bottleneck_resolved"] is True
    assert surface["honest_state"]["current_bottleneck"] == "paid_receipt_absence_return_compute_present"
    assert "paid_bottleneck_cleared" in surface["honest_state"]["not_yet_proof_of"]
    assert surface["flywheel_state"]["closed"] is True
    assert surface["flywheel_state"]["next_missing_stage"] == "positive_paid_receipt"
    assert surface["population_control"]["rows"][0]["main_loop_promotion_allowed"] is True
