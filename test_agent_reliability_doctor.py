from agent_reliability_doctor import AgentReliabilityDoctor


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
