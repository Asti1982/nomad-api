from nomad_evolution_alpha import build_evolution_alpha_plan
from nomad_job_channels import build_job_channel_surface


def _external_nonpaid_summary():
    return {
        "ok": True,
        "schema": "nomad.external_value_summary.v1",
        "distinct_externals": 13,
        "event_tail_count": 13,
        "revenue_recognized_usd_total": 0.0,
        "latest_by_external": [
            {
                "external_id": f"gh_pr:owner/repo#{idx}",
                "stage": "submitted",
                "work_url": f"https://github.com/owner/repo/pull/{idx}",
                "revenue_recognized_usd": 0.0,
            }
            for idx in range(13)
        ],
    }


def _growth_kernel():
    return {
        "ok": True,
        "schema": "nomad.local_growth_kernel.v1",
        "receipt_id": "lgk-test",
        "population": {
            "top_variants": [
                {
                    "variant_id": "lgv-negative-space",
                    "objective": "negative_space_harvest",
                    "phenotype": {
                        "mutation_operator": "search_routes_with_high_machine_value_and_low_agent_traffic",
                        "side_effect_scope": "nomad_contract_endpoints_only",
                    },
                    "fitness": {
                        "frontier_score": 0.91,
                        "proof_signal": 0.33,
                        "nonanthropic_distance": 0.8,
                    },
                }
            ]
        },
    }


def test_evolution_alpha_preserves_paid_only_fitness_under_nonpaying_wip():
    external = _external_nonpaid_summary()
    out = build_evolution_alpha_plan(
        base_url="https://nomad.example",
        local_growth_kernel=_growth_kernel(),
        job_channels=build_job_channel_surface(base_url="https://nomad.example", external_value_summary=external),
        external_value_summary=external,
        nonhuman_science={
            "scientific_grounding": {
                "average_nonhuman_distance_score": 0.82,
            }
        },
    )

    assert out["schema"] == "nomad.evolution_alpha_plan.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-evolution-alpha.json"
    assert out["observed_state"]["active_nonpaid_count"] == 13
    assert out["observed_state"]["recognized_revenue_usd_total"] == 0.0
    assert out["selection_architecture"]["fitness"]["primary"] == "paid_stage_with_positive_amount_or_verified_microtask_settlement"
    assert "merge_without_payment" in out["selection_architecture"]["fitness"]["forbidden_as_revenue"]
    assert out["alpha_lanes"][0]["lane_id"] == "payout_terms_compiler"
    assert out["alpha_lanes"][0]["side_effect_scope"] == "read_only_terms_and_preflight"
    assert out["safety_contract"]["no_public_or_financial_side_effect_before_preflight"] is True
    assert "negative_space_harvest" in {item["operator_id"] for item in out["mutation_operators"]}
    assert any("nature.com/articles/s41586-023-06924-6" in source for item in out["research_alignment"] for source in item["sources"])


def test_evolution_alpha_cli_returns_surface():
    from nomad_cli import run_once

    out = run_once(["evolution-alpha", "--base-url", "https://nomad.example", "--json"])

    assert out["schema"] == "nomad.evolution_alpha_plan.v1"
    assert out["read_url"] == "https://nomad.example/swarm/evolution-alpha"
    assert out["links"]["job_channels"] == "https://nomad.example/.well-known/nomad-job-channels.json"
    assert "promote_only_paid_receipt" in out["machine_instruction"]
