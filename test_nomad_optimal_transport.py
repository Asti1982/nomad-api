from nomad_optimal_transport import (
    build_nomad_optimal_transport_surface,
    build_ot_conformance_surface,
    build_ot_manifold_surface,
    build_ot_metric_learning_surface,
    build_ot_paper_readiness_surface,
    compile_nomad_ot_problem,
    record_ot_outcome_event,
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
    assert surface["paper_readiness_url"] == "https://nomad.example/.well-known/nomad-ot-paper-readiness.json"
    assert surface["manifold_url"] == "https://nomad.example/.well-known/nomad-ot-manifold.json"
    assert surface["conformance_url"] == "https://nomad.example/.well-known/nomad-ot-conformance.json"
    assert surface["metric_learning_url"] == "https://nomad.example/.well-known/nomad-ot-metric-learning.json"
    assert surface["active_axis_weights"] == surface["plan"]["axis_weights"]
    assert surface["compiled_problem"]["vector_axes"]["axis_weights"] == surface["active_axis_weights"]
    assert surface["kantorovich_certificate"]["ok"] is True
    assert surface["metric_learning"]["schema"] == "nomad.ot_metric_learning.v1"
    assert surface["manifold"]["schema"] == "nomad.ot_manifold_slice.v1"
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
    assert plan["manifold"]["schema"] == "nomad.ot_manifold_slice.v1"
    assert plan["manifold"]["measure_barycenters"]["dominant_deficit_axis"] in {"capability", "proof_quality", "dynamics", "settlement"}
    assert plan["manifold"]["barycentric_map"]
    assert plan["kantorovich_certificate"]["schema"] == "nomad.ot_kantorovich_certificate.v1"
    assert plan["kantorovich_certificate"]["ok"] is True
    assert plan["kantorovich_certificate"]["duality_gap"] <= plan["kantorovich_certificate"]["tolerance"]


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
    assert plan["manifold"]["compiled_measure"]["continuous_parent_count"] == 2
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
    assert result["dynamic_manifold"]["schema"] == "nomad.dynamic_ot_manifold.v1"
    assert result["dynamic_manifold"]["trajectory"][1]["deficit_drift_from_previous"]
    assert result["slice_plans"][0]["kantorovich_certificate"]["ok"] is True


def test_multiaxis_plan_includes_kantorovich_certificate():
    plan = solve_multiaxis_optimal_transport(
        [{"id": "runtime", "mass": 1.0, "vector": {"capability": 0.2, "proof_quality": 0.4, "dynamics": 0.3, "settlement": 0.2}}],
        [{"id": "settlement", "mass": 1.0, "vector": {"capability": 0.8, "proof_quality": 0.6, "dynamics": 0.5, "settlement": 0.9}}],
        p=2,
        ground_metric_order=2,
    )

    cert = plan["kantorovich_certificate"]
    assert cert["ok"] is True
    assert cert["primal_cost"] == plan["transport_cost"]
    assert cert["duality_gap"] <= cert["tolerance"]
    assert cert["max_dual_constraint_violation"] <= cert["tolerance"]
    assert cert["max_complementary_slackness_error"] <= cert["tolerance"]
    assert cert["source_potentials"]
    assert cert["target_potentials"]


def test_ot_manifold_surface_exposes_barycentric_displacement_field():
    surface = build_nomad_optimal_transport_surface(base_url="https://nomad.example")
    manifold = build_ot_manifold_surface(base_url="https://nomad.example", ot_surface=surface)

    assert manifold["schema"] == "nomad.ot_manifold_surface.v1"
    assert manifold["well_known_url"] == "https://nomad.example/.well-known/nomad-ot-manifold.json"
    assert manifold["manifold"]["schema"] == "nomad.ot_manifold_slice.v1"
    assert set(manifold["manifold"]["measure_barycenters"]["deficit_vector"]) == {
        "capability",
        "proof_quality",
        "dynamics",
        "settlement",
    }
    assert manifold["manifold"]["route_gradient"]
    assert "closed_form_manifold_learning" in manifold["claim_boundary"]["not_claimed"]


def test_ot_conformance_surface_requires_certificate_and_manifold():
    surface = build_nomad_optimal_transport_surface(base_url="https://nomad.example")
    conformance = build_ot_conformance_surface(base_url="https://nomad.example", ot_surface=surface)

    assert conformance["schema"] == "nomad.ot_conformance_surface.v1"
    assert conformance["ok"] is True
    assert conformance["well_known_url"] == "https://nomad.example/.well-known/nomad-ot-conformance.json"
    assert conformance["checks"]["kantorovich_certificate_ok"] is True
    assert conformance["checks"]["empirical_manifold_present"] is True
    assert conformance["certificate_summary"]["duality_gap"] <= 1e-7
    assert "kantorovich_dual_certificate_for_compiled_finite_problem" in conformance["complete_runtime_boundary"]["implemented"]
    assert "closed_form_arbitrary_multidimensional_continuous_ot" in conformance["complete_runtime_boundary"]["not_implemented_or_not_claimed"]


def test_ot_metric_learning_records_outcomes_and_reweights_settlement(tmp_path, monkeypatch):
    ledger = tmp_path / "ot_outcomes.jsonl"
    monkeypatch.setenv("NOMAD_OT_OUTCOME_LEDGER_PATH", str(ledger))
    result = record_ot_outcome_event(
        {
            "plan_digest": "nomad-dynamic-ot-plan-test",
            "source_id": "worker-a",
            "target_id": "paid-demand",
            "outcome": "paid",
            "receipt_ref": "receipt:public-test",
            "paid_usd": 49,
            "return_compute_units": 3,
            "proof_digest": "sha256:test",
        },
        base_url="https://nomad.example",
    )
    surface = build_ot_metric_learning_surface(base_url="https://nomad.example")

    assert result["accepted"] is True
    assert result["counts_as_revenue"] is False
    assert surface["schema"] == "nomad.ot_metric_learning.v1"
    assert surface["outcome_summary"]["event_count"] == 1
    assert surface["recommended_axis_weights"]["settlement"] > surface["outcome_summary"]["default_axis_weights"]["settlement"]
    assert surface["outcome_event_url"] == "https://nomad.example/swarm/optimal-transport/outcomes"
    ot_surface = build_nomad_optimal_transport_surface(base_url="https://nomad.example")
    assert ot_surface["active_axis_weights"] == surface["recommended_axis_weights"]
    assert ot_surface["compiled_problem"]["vector_axes"]["axis_weights"] == surface["recommended_axis_weights"]


def test_ot_paper_readiness_surface_exposes_honest_boundary():
    surface = build_nomad_optimal_transport_surface(base_url="https://nomad.example")
    readiness = build_ot_paper_readiness_surface(base_url="https://nomad.example", ot_surface=surface)

    assert readiness["schema"] == "nomad.optimal_transport_paper_readiness.v1"
    assert readiness["paper_near_mathematical_moat_ready"] is True
    assert readiness["full_arbitrary_continuous_closed_form_claim_allowed"] is False
    assert readiness["readiness_checks"]["primary_multiaxis_discrete_solver_ok"] is True
    assert readiness["readiness_checks"]["compiled_continuous_empirical_measure_declared"] is True
    assert readiness["readiness_checks"]["empirical_manifold_displacement_field_available"] is True
    assert readiness["readiness_checks"]["kantorovich_dual_certificate_available"] is True
    assert "arbitrary_closed_form_multidimensional_continuous_ot" in readiness["claim_boundary"]["not_claimed"]
    assert "finite_discrete_probability_measures_over_declared_nomad_ot_axes" in readiness["claim_boundary"]["claimed_exact_for"]
    assert "barycentric_displacement_and_axis_pressure_statistics_for_returned_finite_transport_plans" in readiness["claim_boundary"]["claimed_exact_for"]
    assert "kantorovich_dual_certificate_for_compiled_finite_transport_plans" in readiness["claim_boundary"]["claimed_exact_for"]
    assert readiness["runtime_contract"]["axes"] == ["capability", "proof_quality", "dynamics", "settlement"]
    assert readiness["runtime_contract"]["kantorovich_certificate_schema"] == "nomad.ot_kantorovich_certificate.v1"
    assert readiness["runtime_contract"]["manifold_schema"] == "nomad.ot_manifold_slice.v1"


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
