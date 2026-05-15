from nomad_sales_department_swarm import build_sales_department_swarm_surface, evaluate_sales_department_event


def test_sales_department_surface_routes_buyer_work_and_science_sources():
    surface = build_sales_department_swarm_surface(
        base_url="https://nomad.example",
        buyer_funded_work={
            "receipt_law": {"recognized_revenue_usd_total": 0.0},
            "buyer_funded_packages": [
                {"package_id": "repo_diagnostic_patch_starter"},
                {"package_id": "endpoint_health_patch"},
                {"package_id": "agent_loop_break_patch"},
                {"package_id": "settlement_repair_packet"},
            ],
        },
        value_cycles={"summary": {"cycle_count": 32}},
        ad_cycles={"summary": {"cycle_count": 12}},
        receipt_predictor={"summary": {"cycle_count": 32}},
        revenue_science={"summary": {"experiment_count": 7}},
        effective_channels={"summary": {"effective_channel_count": 5}},
    )

    assert surface["schema"] == "nomad.sales_department_swarm.v1"
    assert surface["read_url"] == "https://nomad.example/swarm/sales-department"
    assert surface["well_known_url"] == "https://nomad.example/.well-known/nomad-sales-department.json"
    assert surface["event_url"] == "https://nomad.example/swarm/sales-department/events"
    assert surface["summary"]["sales_cell_count"] >= 8
    assert surface["summary"]["active_value_cycle_count"] >= 10
    assert surface["summary"]["recognized_revenue_usd_total"] == 0.0
    assert surface["top_active_route"]["route"] == "https://nomad.example/service/e2e?service_type=repo_issue_help"
    assert surface["guards"]["no_public_send_without_proof_and_approval"] is True
    assert any(source["id"] == "silo_bench_2026" for source in surface["science_sources"])


def test_sales_department_event_blocks_public_send_without_proof_and_approval():
    surface = build_sales_department_swarm_surface(base_url="https://nomad.example")

    decision = evaluate_sales_department_event(
        {"cell_id": "repo_rescue_cell", "stage": "send_request", "buyer_intent_digest": "buyer-1"},
        base_url="https://nomad.example",
        sales_surface=surface,
    )

    assert decision["schema"] == "nomad.sales_department_event_decision.v1"
    assert decision["sales_cycle_allowed"] is False
    assert decision["side_effect_allowed"] is False
    assert "proof_digest_required_before_public_send" in decision["blockers"]
    assert "human_or_buyer_approval_required_before_public_send" in decision["blockers"]
    assert decision["revenue_recorded"] is False


def test_sales_department_event_admits_paid_candidate_but_does_not_book_revenue():
    surface = build_sales_department_swarm_surface(base_url="https://nomad.example")

    decision = evaluate_sales_department_event(
        {
            "cell_id": "settlement_repair_cell",
            "stage": "paid",
            "proof_digest": "proof-digest-123",
            "settlement_ref": "tx-123",
            "amount_usd": 25.0,
        },
        base_url="https://nomad.example",
        sales_surface=surface,
    )

    assert decision["sales_cycle_allowed"] is True
    assert decision["paid_receipt_candidate"] is True
    assert decision["revenue_recorded"] is False
    assert decision["side_effect_performed"] is False
