from nomad_optimal_transport import (
    build_nomad_optimal_transport_surface,
    compile_nomad_ot_problem,
    solve_dynamic_multiaxis_optimal_transport,
    solve_multiaxis_optimal_transport,
    solve_ot_request,
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
    assert surface["plan"]["schema"] == "nomad.dynamic_multiaxis_optimal_transport_plan.v1"
    assert surface["mathematical_contract"]["feature_space"] == ["capability", "proof_quality", "dynamics", "settlement"]
    assert surface["routing_contracts"]["settlement_pressure"].startswith("paid/receipt demand")


def test_multiaxis_discrete_ot_uses_capability_proof_dynamics_and_settlement():
    plan = solve_multiaxis_optimal_transport(
        [
            {
                "id": "proof_worker",
                "mass": 1.0,
                "vector": {"capability": 0.56, "proof_quality": 0.9, "dynamics": 0.4, "settlement": 0.3},
            },
            {
                "id": "settlement_worker",
                "mass": 1.0,
                "vector": {"capability": 0.88, "proof_quality": 0.7, "dynamics": 0.5, "settlement": 0.95},
            },
        ],
        [
            {
                "id": "proof_demand",
                "mass": 1.0,
                "vector": {"capability": 0.58, "proof_quality": 0.88, "dynamics": 0.42, "settlement": 0.35},
            },
            {
                "id": "paid_demand",
                "mass": 1.0,
                "vector": {"capability": 0.9, "proof_quality": 0.72, "dynamics": 0.52, "settlement": 0.96},
            },
        ],
        p=2,
        ground_metric_order=2,
    )

    assert plan["ok"] is True
    assert plan["metric"] == "W2"
    pairs = {(row["source_parent_id"], row["target_parent_id"]) for row in plan["transport_plan"]}
    assert ("proof_worker", "proof_demand") in pairs
    assert ("settlement_worker", "paid_demand") in pairs
    assert plan["wasserstein_distance"] < 0.05


def test_multiaxis_continuous_box_compiles_to_empirical_atoms():
    plan = solve_multiaxis_optimal_transport(
        [
            {
                "id": "runtime_band",
                "mass": 1.0,
                "vector": {"capability": 0.2, "proof_quality": 0.5, "dynamics": 0.4, "settlement": 0.3},
                "box": {"capability": [0.1, 0.3]},
            }
        ],
        [
            {
                "id": "proof_band",
                "mass": 1.0,
                "vector": {"capability": 0.6, "proof_quality": 0.7, "dynamics": 0.4, "settlement": 0.3},
                "box": {"capability": [0.5, 0.7]},
            }
        ],
        p=1,
        continuous_resolution=3,
    )

    assert plan["ok"] is True
    assert len(plan["supply_atoms"]) == 3
    assert len(plan["demand_atoms"]) == 3
    assert plan["continuous_compilation"]["mode"] == "deterministic_finite_volume_atoms"
    assert plan["wasserstein_distance"] > 0.0


def test_dynamic_multiaxis_ot_reports_temporal_churn():
    result = solve_dynamic_multiaxis_optimal_transport(
        [
            {
                "timestamp": "t0",
                "supply": [{"id": "worker", "mass": 1.0, "vector": {"capability": 0.2, "proof_quality": 0.5, "dynamics": 0.3, "settlement": 0.2}}],
                "demand": [{"id": "runtime", "mass": 1.0, "vector": {"capability": 0.2, "proof_quality": 0.5, "dynamics": 0.3, "settlement": 0.2}}],
            },
            {
                "timestamp": "t1",
                "supply": [{"id": "worker", "mass": 1.0, "vector": {"capability": 0.2, "proof_quality": 0.5, "dynamics": 0.3, "settlement": 0.2}}],
                "demand": [{"id": "settlement", "mass": 1.0, "vector": {"capability": 0.88, "proof_quality": 0.7, "dynamics": 0.5, "settlement": 0.95}}],
            },
        ],
        temporal_regularization=0.1,
    )

    assert result["ok"] is True
    assert result["slice_count"] == 2
    assert result["plan_churn_total"] == 1.0
    assert result["slice_plans"][1]["plan_churn_from_previous"] == 1.0


def test_solve_request_selects_multiaxis_and_dynamic_modes():
    multiaxis = solve_ot_request(
        {
            "mode": "multiaxis",
            "p": 2,
            "supply": [{"id": "a", "mass": 1.0, "vector": [0.1, 0.2, 0.3, 0.4]}],
            "demand": [{"id": "b", "mass": 1.0, "vector": [0.1, 0.2, 0.3, 0.4]}],
        }
    )
    dynamic = solve_ot_request(
        {
            "time_slices": [
                {
                    "supply": [{"id": "a", "mass": 1.0, "vector": [0.1, 0.2, 0.3, 0.4]}],
                    "demand": [{"id": "b", "mass": 1.0, "vector": [0.1, 0.2, 0.3, 0.4]}],
                }
            ]
        }
    )

    assert multiaxis["schema"] == "nomad.dynamic_multiaxis_optimal_transport_plan.v1"
    assert dynamic["schema"] == "nomad.dynamic_optimal_transport_plan.v1"
