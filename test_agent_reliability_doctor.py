from agent_reliability_doctor import (
    AgentReliabilityDoctor,
    build_reliability_doctor_intake,
    build_reliability_doctor_surface,
)


def test_reliability_doctor_maps_hallucination_to_reflection_critic():
    doctor = AgentReliabilityDoctor()

    result = doctor.diagnose(
        problem="Agent produced unsupported claims and fake sources.",
        service_type="hallucination",
    )

    assert result["schema"] == "nomad.agent_reliability_doctor.v1"
    assert result["pain_type"] == "hallucination"
    assert result["doctor_role"]["id"] == "reflection_critic"
    assert result["reliability_loop"]["conditional_edge"] == "fix_or_block_until_rubric_passes"
    assert result["critic_rubric"][0]["check"] == "evidence_bound"


def test_reliability_doctor_maps_tool_failure_to_execution_healer():
    result = AgentReliabilityDoctor().diagnose(
        problem="Tool failure: schema mismatch after the browser execution step.",
        service_type="tool_failure",
    )

    assert result["doctor_role"]["id"] == "execution_healer"
    assert "fixture" in " ".join(result["intervention_plan"]).lower()
    assert result["fix_contract"]["success_signal"].startswith("rubric_passed")


def test_reliability_doctor_defaults_to_self_correction_when_unclear():
    result = AgentReliabilityDoctor().diagnose(problem="Agent keeps making the same mistake.")

    assert result["pain_type"] == "self_correction_failure"
    assert result["doctor_role"]["id"] == "reflection_critic"
    assert result["healing_memory"]["fingerprint"].startswith("pain-")


def test_reliability_doctor_surface_exposes_ci_and_docker_onramps():
    surface = build_reliability_doctor_surface(base_url="https://nomad.example")

    assert surface["schema"] == "nomad.agent_reliability_doctor_surface.v1"
    assert surface["routes"]["intake"] == "https://nomad.example/swarm/reliability-doctor/intake"
    assert surface["downloads"]["github_action"].endswith("/downloads/nomad_reliability_doctor_action.yml")
    assert surface["downloads"]["work_exchange_dockerfile"].endswith("/downloads/nomad_work_exchange_worker.Dockerfile")
    assert surface["agent_onramps"][0]["side_effect_scope"] == "secret_free_http_intake_only"


def test_reliability_doctor_intake_builds_offer_payload_and_optional_obligation_payload():
    out = build_reliability_doctor_intake(
        {
            "requester_id": "github-actions:owner/repo:123",
            "source": "github_actions",
            "service_type": "execution_failure",
            "problem": "CI timed out after a tool schema mismatch.",
            "repository": "owner/repo",
            "workflow_url": "https://github.com/owner/repo/actions/runs/123",
            "log_digest": "sha256:" + "1" * 64,
            "accepted_compute_barter_terms": True,
        },
        base_url="https://nomad.example",
    )

    assert out["schema"] == "nomad.agent_reliability_doctor_intake.v1"
    assert out["accepted_compute_barter_terms"] is True
    assert out["diagnosis"]["doctor_role"]["id"] == "execution_healer"
    assert out["solution_proof_digest"].startswith("sha256:")
    assert out["work_exchange_offer_payload"]["requester_id"] == "github-actions:owner/repo:123"
    assert out["free_solution_payload"]["accepted_compute_barter_terms"] is True
    assert out["next"]["dockerfile"].endswith("/downloads/nomad_work_exchange_worker.Dockerfile")


def test_reliability_doctor_intake_rejects_secret_shaped_payload():
    out = build_reliability_doctor_intake({"requester_id": "x", "problem": "token leaked", "api_key": "sk-test"})

    assert out["ok"] is False
    assert out["error"] == "secret_shaped_payload"
