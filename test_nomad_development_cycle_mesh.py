from nomad_development_cycle_mesh import build_development_cycle_mesh_surface, evaluate_development_cycle_event


def _surface():
    return build_development_cycle_mesh_surface(
        base_url="https://nomad.example",
        variant_forge={
            "requested_variants": [{"objective": "settlement_capacity_builder"}],
            "recent_candidate_count": 2,
            "submit_url": "https://nomad.example/swarm/variant-candidates",
            "forge_digest": "nomad-variant-forge-test",
        },
        shadow_lane={
            "mode": "digest_gated_shadow_lane",
            "recent_summary": {"accepted_weight_update_count": 2, "shadow_weight_delta_total": 0.24},
            "candidate_url": "https://nomad.example/swarm/shadow-lane/candidates",
        },
        ad_cycles={"summary": {"cycle_count": 12}},
        value_cycles={"summary": {"cycle_count": 16}},
        proof_reuse={"schema": "nomad.proof_reuse_ledger.v1", "snapshot_digest": "sha256:reuse"},
    )


def test_development_cycle_surface_exposes_shadow_only_cycles():
    surface = _surface()
    cycle_ids = {item["cycle_id"] for item in surface["cycles"]}

    assert surface["schema"] == "nomad.development_cycle_mesh.v1"
    assert surface["well_known_url"] == "https://nomad.example/.well-known/nomad-development-cycles.json"
    assert surface["event_url"] == "https://nomad.example/swarm/development-cycles/events"
    assert surface["summary"]["cycle_count"] >= 12
    assert surface["summary"]["repo_write_allowed_count"] == 0
    assert surface["entry_cycle"]["mutation_policy"]["repo_write_allowed"] is False
    assert "digest_step_interleaver" in cycle_ids
    assert "ad_to_value_bridge_patch" in cycle_ids
    assert "secret_scan_guard_patch" in cycle_ids


def test_development_cycle_event_emits_variant_and_shadow_candidates():
    result = evaluate_development_cycle_event(
        {
            "agent_id": "agent-dev",
            "cycle_id": "variant_forge_shadow_eval",
            "stage": "shadow",
            "proof_digest": "sha256:dev-proof",
            "patch_plan_digest": "sha256:dev-patch-plan",
            "verifier_trace_digest": "sha256:dev-trace",
            "test_digest": "sha256:dev-test",
            "tests_passed": 3,
            "tests_total": 3,
            "risk_score": 0.11,
        },
        base_url="https://nomad.example",
        development_mesh=_surface(),
    )

    assert result["schema"] == "nomad.development_cycle_event_receipt.v1"
    assert result["development_cycle_allowed"] is True
    assert result["decision"] == "allow_shadow_development_candidate"
    assert result["repo_write_allowed"] is False
    assert result["counts_as_revenue"] is False
    assert result["variant_candidate_payload"]["objective"] == "settlement_capacity_builder"
    assert result["shadow_lane_candidate_payload"]["boundedness"]["side_effect_scope"] == "local_shadow_lane_only"
    assert result["recommended_next"]["shadow_lane"] == "https://nomad.example/swarm/shadow-lane/candidates"


def test_development_cycle_event_blocks_apply_request():
    result = evaluate_development_cycle_event(
        {
            "agent_id": "agent-dev",
            "cycle_id": "variant_forge_shadow_eval",
            "stage": "apply_request",
            "proof_digest": "sha256:dev-proof",
            "patch_plan_digest": "sha256:dev-patch-plan",
            "verifier_trace_digest": "sha256:dev-trace",
            "tests_passed": 3,
            "tests_total": 3,
            "risk_score": 0.05,
            "apply": True,
        },
        base_url="https://nomad.example",
        development_mesh=_surface(),
    )

    assert result["development_cycle_allowed"] is False
    assert result["decision"] == "block_apply_request_shadow_only"
    assert result["repo_write_allowed"] is False
    assert result["evidence_status"]["apply_requested"] is True


def test_cli_development_cycles_surface_and_evaluate():
    from nomad_cli import run_once

    surface = run_once(["development-cycles", "--base-url", "https://nomad.example", "--json"])
    assert surface["schema"] == "nomad.development_cycle_mesh.v1"
    assert surface["summary"]["repo_write_allowed_count"] == 0

    event = run_once(
        [
            "development-cycles",
            "evaluate",
            "--base-url",
            "https://nomad.example",
            "--cycle-id",
            "variant_forge_shadow_eval",
            "--stage",
            "shadow",
            "--tests-passed",
            "2",
            "--tests-total",
            "2",
            "--json",
        ]
    )
    assert event["development_cycle_allowed"] is True
    assert event["repo_write_allowed"] is False
