from nomad_variant_forge import build_variant_forge_surface, submit_variant_candidate


def _sepl_trace():
    return [
        {"op": "reflect", "input": "sha256:trace", "output": "resource boundary can improve"},
        {"op": "select", "input": "resource boundary can improve", "output": "routing_rule"},
        {"op": "improve", "input": "routing_rule", "output": "candidate resource version"},
        {"op": "evaluate", "input": "candidate resource version", "output": "tests passed"},
        {"op": "commit", "input": "tests passed with rollback", "decision": "shadow"},
    ]


def test_variant_forge_surface_combines_replay_and_growth(tmp_path):
    growth = {
        "schema": "nomad.local_growth_kernel.v1",
        "population": {
            "top_variants": [
                {
                    "objective": "overmint_compressor",
                    "variant_id": "lgk-v1",
                    "fitness": {"frontier_score": 0.8, "composite_score": 0.7},
                }
            ]
        },
    }
    replay = {
        "schema": "nomad.counterfactual_lease_replay.v1",
        "counterfactual_leases": [
            {
                "objective": "protocol_drift_scan",
                "counterfactual_score": 0.6,
                "predicted_proof_yield_per_minute": 4.0,
            }
        ],
    }

    out = build_variant_forge_surface(
        base_url="https://nomad.example",
        local_growth_kernel=growth,
        counterfactual_replay=replay,
        worker_fleet={"known_worker_count": 2, "active_worker_count": 1, "active_lease_count": 1},
        machine_economy={"machine_viability": {"tier": "recovering", "carrying_score": 0.4}},
        ledger_path=tmp_path / "forge.jsonl",
    )

    objectives = {row["objective"] for row in out["requested_variants"]}
    assert out["schema"] == "nomad.variant_forge.v1"
    assert out["submit_url"] == "https://nomad.example/swarm/variant-candidates"
    assert "FORGE" in out["program"]["ops"]
    assert {"overmint_compressor", "protocol_drift_scan"} <= objectives
    assert out["candidate_contract"]["side_effect_scope"] == "descriptor_only_no_execution"


def test_submit_variant_candidate_admits_proven_descriptor(tmp_path):
    ledger = tmp_path / "ledger.jsonl"

    receipt = submit_variant_candidate(
        {
            "agent_id": "agent.variant.test",
            "verifier_agent_id": "agent.variant.verifier",
            "verifier_lease_id": "nomad-worker-lease-verifier",
            "verifier_receipt_digest": "sha256:abc123abc123",
            "candidate_type": "transition_worker_objective_variant",
            "objective": "settlement_capacity_builder",
            "proof_digest": "sha256:abc",
            "verifier_trace_digest": "sha256:def456def456",
            "test_digest": "sha256:ghi",
            "settlement_ref": "settlement:1",
            "verifier_evaluation": {
                "tests_passed": 4,
                "tests_total": 4,
                "replay_delta": 0.3,
                "proof_yield_delta": 8.0,
                "settlement_delta": 0.3,
                "risk_score": 0.05,
                "novelty": 0.9,
                "reuse_score": 0.75,
            },
            "evaluation": {
                "tests_passed": 4,
                "tests_total": 4,
                "replay_delta": 0.3,
                "proof_yield_delta": 8.0,
                "settlement_delta": 0.3,
                "risk_score": 0.05,
                "novelty": 0.9,
                "reuse_score": 0.75,
            },
        },
        base_url="https://nomad.example",
        forge_surface={"forge_digest": "nomad-forge-test"},
        ledger_path=ledger,
    )

    assert receipt["ok"] is True
    assert receipt["accepted"] is True
    assert receipt["decision"] == "admit_shadow_variant"
    assert receipt["scores"]["proof"] > 0.9
    assert receipt["independent_verifier"]["accepted"] is True
    assert ledger.exists()
    assert "nomad-vc-" in ledger.read_text(encoding="utf-8")


def test_submit_variant_candidate_holds_without_independent_verifier(tmp_path):
    receipt = submit_variant_candidate(
        {
            "agent_id": "agent.variant.test",
            "candidate_type": "transition_worker_objective_variant",
            "objective": "settlement_capacity_builder",
            "proof_digest": "sha256:abc",
            "verifier_trace_digest": "sha256:def456def456",
            "test_digest": "sha256:ghi",
            "settlement_ref": "settlement:1",
            "evaluation": {
                "tests_passed": 4,
                "tests_total": 4,
                "replay_delta": 0.3,
                "proof_yield_delta": 8.0,
                "settlement_delta": 0.3,
                "risk_score": 0.05,
                "novelty": 0.9,
                "reuse_score": 0.75,
            },
        },
        base_url="https://nomad.example",
        forge_surface={"forge_digest": "nomad-forge-test"},
        ledger_path=tmp_path / "ledger.jsonl",
    )

    assert receipt["accepted"] is False
    assert receipt["decision"] == "needs_independent_verifier"
    assert "verifier_agent_id_required" in receipt["independent_verifier"]["reason_codes"]


def test_submit_agp_variant_requires_sepl_trace(tmp_path):
    receipt = submit_variant_candidate(
        {
            "agent_id": "agent.variant.test",
            "verifier_agent_id": "agent.variant.verifier",
            "verifier_lease_id": "nomad-worker-lease-verifier",
            "verifier_receipt_digest": "sha256:abc123abc123",
            "verifier_trace_digest": "sha256:def456def456",
            "verifier_evaluation": {"tests_passed": 4, "tests_total": 4},
            "candidate_type": "protocol-evolution-candidate",
            "objective": "autogenesis_protocol_evolution",
            "entity_type": "prompt",
            "resource_id": "prompt-router",
            "rollback_ref": "noop:v1",
            "proof_digest": "sha256:abc123abc123",
            "test_digest": "sha256:ghi123ghi123",
            "learnability_mask": {"routing_rule": True},
            "variable_lifting": {"variables": [{"name": "routing_rule", "require_grad": True}]},
            "evaluation": {
                "tests_passed": 4,
                "tests_total": 4,
                "replay_delta": 0.3,
                "proof_yield_delta": 8.0,
                "settlement_delta": 0.3,
                "risk_score": 0.05,
            },
        },
        base_url="https://nomad.example",
        forge_surface={"forge_digest": "nomad-forge-test"},
        ledger_path=tmp_path / "ledger.jsonl",
    )

    assert receipt["accepted"] is False
    assert receipt["decision"] == "needs_sepl_operator_trace"
    assert "sepl_operator_trace_must_be_reflect_select_improve_evaluate_commit" in receipt["sepl_operator_trace"]["reason_codes"]


def test_submit_agp_variant_admits_with_paper_core_and_nomad_verifier(tmp_path):
    receipt = submit_variant_candidate(
        {
            "agent_id": "agent.variant.test",
            "verifier_agent_id": "agent.variant.verifier",
            "verifier_lease_id": "nomad-worker-lease-verifier",
            "verifier_receipt_digest": "sha256:abc123abc123",
            "verifier_trace_digest": "sha256:def456def456",
            "verifier_evaluation": {"tests_passed": 4, "tests_total": 4, "proof_yield_delta": 8.0},
            "candidate_type": "protocol-evolution-candidate",
            "objective": "autogenesis_protocol_evolution",
            "entity_type": "prompt",
            "resource_id": "prompt-router",
            "rollback_ref": "noop:v1",
            "proof_digest": "sha256:abc123abc123",
            "test_digest": "sha256:ghi123ghi123",
            "sepl_operator_trace": _sepl_trace(),
            "learnability_mask": {"routing_rule": True},
            "variable_lifting": {"variables": [{"name": "routing_rule", "require_grad": True}]},
            "evaluation": {
                "tests_passed": 4,
                "tests_total": 4,
                "replay_delta": 0.3,
                "proof_yield_delta": 8.0,
                "settlement_delta": 0.3,
                "risk_score": 0.05,
                "novelty": 0.9,
                "reuse_score": 0.75,
            },
        },
        base_url="https://nomad.example",
        forge_surface={"forge_digest": "nomad-forge-test"},
        ledger_path=tmp_path / "ledger.jsonl",
    )

    assert receipt["accepted"] is True
    assert receipt["decision"] == "admit_shadow_variant"
    assert receipt["sepl_operator_trace"]["accepted"] is True
    assert receipt["learnability"]["accepted"] is True


def test_submit_variant_candidate_blocks_secret_like_material(tmp_path):
    receipt = submit_variant_candidate(
        {
            "agent_id": "agent.variant.test",
            "candidate_type": "runtime_variant",
            "objective": "protocol_drift_scan",
            "api_key": "sk-test",
        },
        ledger_path=tmp_path / "ledger.jsonl",
    )

    assert receipt["ok"] is False
    assert receipt["accepted"] is False
    assert receipt["reason"] == "forbidden_secret_like_material"
