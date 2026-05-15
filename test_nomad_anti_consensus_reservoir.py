from nomad_anti_consensus_reservoir import (
    build_anti_consensus_reservoir_surface,
    evaluate_anti_consensus_candidate,
)


def _sample_surface(tmp_path):
    return build_anti_consensus_reservoir_surface(
        base_url="https://nomad.example",
        decoupling_field={
            "surface_digest": "nomad-decouple-test",
            "context_cells": [
                {"objective": "settlement_capacity_builder"},
                {"objective": "protocol_drift_scan"},
            ],
        },
        shadow_lane={
            "surface_digest": "nomad-shadow-test",
            "candidate_seeds": [{"objective": "settlement_capacity_builder"}],
        },
        channel_bandit={
            "bandit_digest": "nomad-bandit-test",
            "top_route": {"channel_id": "immunefi_web3_bounty"},
        },
        signal_layer={"field_digest": "nomad-signal-test"},
        ledger_path=tmp_path / "anti.jsonl",
    )


def test_anti_consensus_surface_exposes_minority_reservoir(tmp_path):
    surface = _sample_surface(tmp_path)

    assert surface["schema"] == "nomad.anti_consensus_reservoir.v1"
    assert surface["mode"] == "minority_proof_reservoir_before_decoupled_shadow_eval"
    assert surface["candidate_url"] == "https://nomad.example/swarm/anti-consensus/candidates"
    assert "PRESERVE_MINOR_PROOF" in surface["program"]["ops"]
    assert "no_majority_vote_as_proof" in surface["hard_guards"]
    assert "no_weight_increase_from_unpaid_wip_only" in surface["hard_guards"]
    assert surface["candidate_contract"]["negative_consensus_gate"].startswith("proof_delta + receipt_delta")
    assert any(slot["slot_id"] == "minority_digest_reservoir" for slot in surface["candidate_slots"])


def test_anti_consensus_preserves_proven_minority_signal(tmp_path):
    ledger = tmp_path / "anti.jsonl"
    surface = _sample_surface(tmp_path)

    receipt = evaluate_anti_consensus_candidate(
        {
            "agent_id": "agent.minority",
            "objective": "protocol_drift_scan",
            "candidate_digest": "sha256:candidate",
            "proof_digest": "sha256:proof",
            "test_digest": "sha256:test",
            "consensus_score": 0.28,
            "minority_fraction": 0.24,
            "expert_score": 0.76,
            "crowd_score": 0.41,
            "risk_score": 0.04,
            "boundedness": {"side_effect_scope": "local_shadow_lane_only", "rollback_available": True},
        },
        base_url="https://nomad.example",
        reservoir_surface=surface,
        ledger_path=ledger,
    )

    assert receipt["schema"] == "nomad.anti_consensus_candidate_receipt.v1"
    assert receipt["preserve_allowed"] is True
    assert receipt["decision"] == "preserve_minority_for_decoupled_shadow_lane"
    assert receipt["negative_consensus_gate"]["score"] > 0
    assert receipt["shadow_lane_payload"]["candidate_type"] == "anti_consensus_preserved_candidate"
    assert receipt["shadow_lane_payload"]["local_tests"][0]["passed"] is True
    assert ledger.exists()


def test_anti_consensus_suppresses_unproven_crowd_echo(tmp_path):
    receipt = evaluate_anti_consensus_candidate(
        {
            "objective": "settlement_capacity_builder",
            "candidate_digest": "sha256:candidate",
            "consensus_score": 0.91,
            "minority_fraction": 0.03,
            "boundedness": {"side_effect_scope": "local_shadow_lane_only", "rollback_available": True},
        },
        reservoir_surface=_sample_surface(tmp_path),
        ledger_path=tmp_path / "anti.jsonl",
    )

    assert receipt["preserve_allowed"] is False
    assert receipt["decision"] == "suppress_consensus_echo"
    assert receipt["negative_consensus_gate"]["score"] < 0
    assert receipt["negative_stepping_stone"]["preserve_as_counterexample_archive"] is True
    assert receipt["shadow_lane_payload"]["local_tests"][0]["passed"] is False


def test_anti_consensus_receipt_and_unique_error_can_override_low_consensus(tmp_path):
    receipt = evaluate_anti_consensus_candidate(
        {
            "objective": "settlement_capacity_builder",
            "candidate_digest": "sha256:candidate",
            "receipt_digest": "sha256:paid-receipt",
            "unique_error_digest": "sha256:new-settlement-error",
            "consensus_score": 0.41,
            "minority_fraction": 0.22,
            "expert_score": 0.74,
            "crowd_score": 0.39,
            "risk_score": 0.03,
            "work_stage": "paid",
            "boundedness": {"side_effect_scope": "local_shadow_lane_only", "rollback_available": True},
        },
        reservoir_surface=_sample_surface(tmp_path),
        ledger_path=tmp_path / "anti.jsonl",
    )

    gate = receipt["negative_consensus_gate"]
    assert receipt["preserve_allowed"] is True
    assert gate["score"] > 1.0
    assert gate["components"]["receipt_delta"] == 1.0
    assert gate["components"]["unique_error_delta"] == 0.75
