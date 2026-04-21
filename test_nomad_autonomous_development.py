from nomad_autonomous_development import AutonomousDevelopmentLog


def test_autonomous_development_records_lead_help_receipt(tmp_path):
    log = AutonomousDevelopmentLog(path=tmp_path / "autonomous.json")

    result = log.apply_cycle(
        objective="Work lead",
        self_improvement={
            "lead_scout": {
                "active_lead": {
                    "title": "Agent blocked by quota",
                    "url": "https://github.com/example/agent/issues/7",
                    "pain": "quota failure",
                    "recommended_service_type": "compute_auth",
                },
                "help_draft": {"draft": "Draft help"},
                "help_draft_path": str(tmp_path / "lead-plan.json"),
                "next_agent_action": "Draft one private response.",
            }
        },
    )

    assert result["ok"] is True
    assert result["skipped"] is False
    assert result["action"]["type"] == "lead_help_artifact"
    assert result["action"]["files"] == [str(tmp_path / "lead-plan.json")]
    assert log.status()["action_count"] == 1


def test_autonomous_development_dedupes_same_candidate(tmp_path):
    log = AutonomousDevelopmentLog(path=tmp_path / "autonomous.json")
    cycle = {
        "agent_pain_solver": {
            "analysis": "solution ready",
            "solution": {
                "solution_id": "sol-1",
                "title": "Provider Fallback Ladder",
                "pain_type": "compute_auth",
                "guardrail": {"id": "compute_fallback_ladder"},
            },
        }
    }

    first = log.apply_cycle("objective", cycle)
    second = log.apply_cycle("objective", cycle)

    assert first["skipped"] is False
    assert second["skipped"] is True
    assert second["reason"] == "duplicate_development_candidate"
    assert log.status()["action_count"] == 1
