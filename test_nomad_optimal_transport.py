from nomad_optimal_transport import (
    build_nomad_optimal_transport_surface,
    compile_nomad_ot_problem,
    solve_quantile_optimal_transport,
)


def test_discrete_wasserstein_one_is_exact_for_atoms():
    plan = solve_quantile_optimal_transport(
        [{"id": "runtime", "mass": 1.0, "position": 0.0}],
        [{"id": "settlement", "mass": 1.0, "position": 1.0}],
        p=1,
    )

    assert plan["ok"] is True
    assert plan["metric"] == "W1"
    assert plan["wasserstein_distance"] == 1.0
    assert plan["transport_plan"][0]["amount"] == 1.0
    assert plan["solver"] == "exact_1d_quantile_monge_transport_no_sinkhorn_no_softmax"


def test_continuous_piecewise_uniform_wasserstein_two_is_exact_for_shifted_intervals():
    plan = solve_quantile_optimal_transport(
        [{"id": "uniform_a", "mass": 1.0, "continuous": True, "start": 0.0, "end": 1.0}],
        [{"id": "uniform_b", "mass": 1.0, "continuous": True, "start": 1.0, "end": 2.0}],
        p=2,
    )

    assert plan["ok"] is True
    assert plan["metric"] == "W2"
    assert plan["wasserstein_distance"] == 1.0
    assert plan["transport_cost"] == 1.0


def test_overlapping_continuous_intervals_are_rejected_as_not_exact_here():
    plan = solve_quantile_optimal_transport(
        [
            {"id": "a", "mass": 1.0, "continuous": True, "start": 0.0, "end": 1.0},
            {"id": "b", "mass": 1.0, "continuous": True, "start": 0.5, "end": 1.5},
        ],
        [{"id": "c", "mass": 1.0, "position": 0.0}],
    )

    assert plan["ok"] is False
    assert plan["error"] == "supply_overlapping_continuous_intervals_rejected_for_exact_quantile_mode"


def test_compile_nomad_ot_problem_and_surface_from_pressure_rows():
    value_pressure = {
        "rows": [
            {
                "row_id": "server-failure:test",
                "source": "server_failure_guard",
                "kind": "platform_repair",
                "pressure_score": 1.7,
                "target_stage": "protected_runtime",
                "action": "produce_bounded_server_repair_packet",
            },
            {
                "row_id": "settlement:test",
                "kind": "external_followup",
                "pressure_score": 0.9,
                "target_stage": "paid",
                "action": "await_payment_receipt",
            },
        ]
    }
    compute_market = {
        "scored_workers": [
            {
                "agent_id": "worker-a",
                "objective": "settlement_capacity_builder",
                "market_score": 0.8,
            }
        ]
    }

    problem = compile_nomad_ot_problem(
        base_url="https://nomad.example",
        compute_market=compute_market,
        value_pressure=value_pressure,
    )
    surface = build_nomad_optimal_transport_surface(
        base_url="https://nomad.example",
        compute_market=compute_market,
        value_pressure=value_pressure,
    )

    assert problem["schema"] == "nomad.optimal_transport_problem.v1"
    assert problem["supply"][0]["kind"] == "runtime_capacity"
    assert len(problem["demand"]) == 2
    assert surface["schema"] == "nomad.optimal_transport.v1"
    assert surface["plan"]["ok"] is True
    assert surface["routing_contracts"]["settlement_pressure"].startswith("unmatched high-coordinate demand")
