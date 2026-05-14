from nomad_shadow_lane_evaluator import (
    build_shadow_lane_evaluator_surface,
    evaluate_shadow_candidate,
    generate_shadow_candidate,
)


def _sample_surface(tmp_path):
    return build_shadow_lane_evaluator_surface(
        base_url="https://nomad.example",
        opaque_surface={
            "surface_digest": "nomad-opaque-test",
            "machine_products_to_add": [
                {"id": "workflow_population", "schema": "nomad.opaque_candidate.v1"},
            ],
        },
        variant_forge={
            "forge_digest": "nomad-forge-test",
            "requested_variants": [{"objective": "settlement_capacity_builder"}],
        },
        channel_bandit={
            "bandit_digest": "nomad-bandit-test",
            "top_route": {"channel_id": "taskbounty_agent_pr_task"},
        },
        ledger_path=tmp_path / "shadow.jsonl",
    )


def test_shadow_lane_surface_exposes_digest_gate(tmp_path):
    surface = _sample_surface(tmp_path)

    assert surface["schema"] == "nomad.shadow_lane_evaluator.v1"
    assert surface["mode"] == "alphaevolve_style_shadow_lane_digest_gate"
    assert surface["candidate_url"] == "https://nomad.example/swarm/shadow-lane/candidates"
    assert "PROOF_DIGEST" in surface["program"]["ops"]
    assert "WEIGHT_GATE" in surface["program"]["ops"]
    assert "selection_weight_delta_is_positive_only_when_local_tests_pass" in surface["candidate_contract"]["weight_rule"]
    assert "no_submitted_code_execution" in surface["hard_guards"]
    assert any(seed["objective"] == "settlement_capacity_builder" for seed in surface["candidate_seeds"])


def test_generate_shadow_candidate_is_descriptor_only(tmp_path):
    candidate = generate_shadow_candidate(
        {"agent_id": "agent.shadow", "objective": "settlement_capacity_builder"},
        base_url="https://nomad.example",
        candidate_seeds=_sample_surface(tmp_path)["candidate_seeds"],
    )

    assert candidate["schema"] == "nomad.shadow_lane_candidate.v1"
    assert candidate["candidate_id"].startswith("nomad-shadow-")
    assert candidate["boundedness"]["side_effect_scope"] == "local_shadow_lane_only"
    assert "proof_digest_mint" in candidate["local_test_plan"]


def test_shadow_candidate_weight_increases_only_after_local_tests_pass(tmp_path):
    ledger = tmp_path / "shadow.jsonl"
    surface = _sample_surface(tmp_path)
    payload = {
        "agent_id": "agent.shadow",
        "objective": "settlement_capacity_builder",
        "candidate_type": "shadow_lane_policy_variant",
        "hypothesis": "Increase route weight after a local digest gate proves the descriptor is bounded.",
        "boundedness": {
            "ttl_seconds": 300,
            "side_effect_scope": "local_shadow_lane_only",
            "rollback_available": True,
            "secrets_free": True,
        },
        "claimed_effect": {
            "proof_gain_delta": 0.5,
            "settlement_signal": 0.3,
            "capability_gain": 0.2,
            "risk_score": 0.05,
        },
        "local_tests": [
            {"name": "unit_shadow_smoke", "passed": True, "evidence_digest": "sha256:test"},
        ],
    }

    accepted = evaluate_shadow_candidate(payload, base_url="https://nomad.example", shadow_surface=surface, ledger_path=ledger)
    rejected = evaluate_shadow_candidate(
        {**payload, "local_tests": [{"name": "unit_shadow_smoke", "passed": False}]},
        base_url="https://nomad.example",
        shadow_surface=surface,
        ledger_path=ledger,
    )

    assert accepted["schema"] == "nomad.shadow_lane_receipt.v1"
    assert accepted["weight_update_allowed"] is True
    assert accepted["selection_weight_delta"] > 0
    assert accepted["proof_digest"].startswith("sha256:")
    assert rejected["weight_update_allowed"] is False
    assert rejected["selection_weight_delta"] == 0.0
    assert ledger.exists()
    assert "selection_weight_delta" in ledger.read_text(encoding="utf-8")


def test_shadow_candidate_blocks_secret_shaped_payload(tmp_path):
    receipt = evaluate_shadow_candidate(
        {
            "agent_id": "agent.shadow",
            "objective": "settlement_capacity_builder",
            "api_key": "sk-test",
            "boundedness": {
                "ttl_seconds": 300,
                "side_effect_scope": "local_shadow_lane_only",
                "rollback_available": True,
            },
        },
        shadow_surface=_sample_surface(tmp_path),
        ledger_path=tmp_path / "shadow.jsonl",
    )

    secret_scan = next(test for test in receipt["local_tests"]["tests"] if test["name"] == "secret_scan_clean")
    assert receipt["weight_update_allowed"] is False
    assert receipt["selection_weight_delta"] == 0.0
    assert secret_scan["passed"] is False
