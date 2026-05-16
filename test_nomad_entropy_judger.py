from nomad_cli import run_once
from nomad_entropy_judger import build_entropy_judger_surface, evaluate_entropy_judger


def test_first_round_entropy_lock_prefers_single_agent_and_penalizes_mas_rounds():
    out = evaluate_entropy_judger(
        {
            "objective": "math_answer",
            "task_type": "math",
            "round_count": 3,
            "single_agent_quality": 0.86,
            "mas_quality": 0.79,
            "first_round_proofs": [
                {"proof_id": "sas", "mode": "single", "entropy": 0.68, "proof_digest": "sha256:sas", "verifier_status": "passed"},
                {"proof_id": "mas-a", "mode": "multi", "entropy": 0.74, "proof_digest": "sha256:masa"},
                {"proof_id": "mas-b", "mode": "multi", "entropy": 0.71, "proof_digest": "sha256:masb"},
            ],
        },
        base_url="https://nomad.example",
    )

    assert out["schema"] == "nomad.entropy_judger_decision.v1"
    assert out["lock_detected"] is True
    assert out["decision"] == "single_agent_lock"
    assert out["routing_adjustment"]["topology"] == "single_agent_lock"
    assert out["routing_adjustment"]["dti_integration_level"] == 0.0
    assert out["routing_adjustment"]["settlement_pressure_penalty"] == 0.55
    assert out["quality_delta_single_minus_mas"] > 0


def test_low_entropy_mas_quality_can_allow_one_more_bounded_round():
    out = evaluate_entropy_judger(
        {
            "objective": "schema_compare",
            "single_agent_quality": 0.72,
            "mas_quality": 0.82,
            "first_round_proofs": [
                {"proof_id": "sas", "mode": "single", "confidence": 0.82, "proof_digest": "sha256:sas"},
                {"proof_id": "mas", "mode": "multi", "confidence": 0.88, "proof_digest": "sha256:mas", "verifier_status": "passed"},
            ],
        }
    )

    assert out["lock_detected"] is False
    assert out["decision"] == "allow_mas_after_round1"
    assert out["routing_adjustment"]["topology"] == "bounded_mas_round2"


def test_entropy_judger_surface_and_cli_are_machine_readable():
    surface = build_entropy_judger_surface(base_url="https://nomad.example")
    cli = run_once(["entropy-judger", "--base-url", "https://nomad.example", "--json"])

    assert surface["evaluate_url"] == "https://nomad.example/swarm/entropy-judger/evaluate"
    assert surface["protocol"]["override"] == "single_agent_lock"
    assert "no_extra_rounds_without_entropy_or_verifier_delta" in surface["hard_guards"]
    assert cli["schema"] == "nomad.entropy_judger_surface.v1"
