from nomad_deficit_integration_gate import (
    build_deficit_integration_surface,
    evaluate_deficit_integration_event,
)


def _sample_surface(tmp_path):
    return build_deficit_integration_surface(
        base_url="https://nomad.example",
        anti_consensus={"surface_digest": "nomad-anti-test"},
        decoupling_field={"surface_digest": "nomad-decouple-test"},
        shadow_lane={"surface_digest": "nomad-shadow-test"},
        signal_layer={"field_digest": "nomad-signal-test"},
        ledger_path=tmp_path / "dti.jsonl",
    )


def test_deficit_integration_surface_exposes_science_plan(tmp_path):
    surface = _sample_surface(tmp_path)

    assert surface["schema"] == "nomad.deficit_integration_gate.v1"
    assert surface["mode"] == "integrate_only_under_coordination_deficit"
    assert surface["event_url"] == "https://nomad.example/swarm/deficit-integration/events"
    assert "TRIGGER_DTI_ONLY_ON_DEFICIT" in surface["program"]["ops"]
    assert "no_final_answer_majority_vote" in surface["hard_guards"]
    assert any(step["id"] == "integrate_only_on_deficit" for step in surface["scientific_plan"])


def test_deficit_integration_triggers_when_expansion_outruns_consolidation(tmp_path):
    ledger = tmp_path / "dti.jsonl"
    receipt = evaluate_deficit_integration_event(
        {
            "agent_id": "agent.dti",
            "objective": "coordination_deficit_repair",
            "event_digest": "sha256:event",
            "proof_digest": "sha256:proof",
            "coordination_expansion": 0.91,
            "consolidation_score": 0.12,
            "cascade_skew": 0.76,
            "orphan_proof_count": 5,
            "consensus_score": 0.18,
            "adversarial_majority_risk": 0.52,
            "minority_preserved": True,
            "boundedness": {"side_effect_scope": "local_shadow_lane_only", "rollback_available": True},
        },
        base_url="https://nomad.example",
        gate_surface=_sample_surface(tmp_path),
        ledger_path=ledger,
    )

    assert receipt["schema"] == "nomad.deficit_integration_receipt.v1"
    assert receipt["integration_allowed"] is True
    assert receipt["decision"] == "trigger_deficit_integration_bridge"
    assert receipt["integration_candidate"]["candidate_type"] == "deficit_triggered_digest_interleaving"
    assert receipt["integration_candidate"]["interleaving_rule"]["forbidden"] == "final_answer_majority_vote"
    assert ledger.exists()


def test_deficit_integration_keeps_isolated_without_deficit(tmp_path):
    receipt = evaluate_deficit_integration_event(
        {
            "event_digest": "sha256:event",
            "proof_digest": "sha256:proof",
            "coordination_expansion": 0.32,
            "consolidation_score": 0.78,
            "cascade_skew": 0.12,
            "orphan_proof_count": 0,
            "consensus_score": 0.71,
            "boundedness": {"side_effect_scope": "local_shadow_lane_only", "rollback_available": True},
        },
        gate_surface=_sample_surface(tmp_path),
        ledger_path=tmp_path / "dti.jsonl",
    )

    assert receipt["integration_allowed"] is False
    assert receipt["decision"] == "keep_isolated_no_deficit"
    assert receipt["integration_candidate"]["local_tests"][0]["passed"] is False
