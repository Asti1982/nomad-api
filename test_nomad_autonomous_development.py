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


def test_autonomous_development_materializes_high_value_pattern_artifacts(tmp_path):
    log = AutonomousDevelopmentLog(
        path=tmp_path / "autonomous.json",
        artifact_dir=tmp_path / "artifacts",
    )

    result = log.apply_cycle(
        objective="Turn repeated compute pain into a reusable offer",
        self_improvement={
            "high_value_patterns": {
                "patterns": [
                    {
                        "pattern_id": "hvp-123",
                        "title": "Provider Fallback Ladder",
                        "pain_type": "compute_auth",
                        "occurrence_count": 3,
                        "avg_truth_score": 0.82,
                        "avg_reuse_value": 0.91,
                        "productization": {
                            "pack_ready": True,
                            "sku": "nomad.mutual_aid.compute_auth_micro_pack",
                            "name": "Mutual-Aid Compute Auth Micro-Pack",
                        },
                        "agent_offer": {
                            "starter_diagnosis": "Nomad has seen this compute_auth pattern repeatedly.",
                            "reply_contract": "PLAN_ACCEPTED=true plus FACT_URL or ERROR",
                            "smallest_paid_unblock": {
                                "amount_native": 0.03,
                                "delivery": "bounded unblock",
                            },
                        },
                        "self_evolution": {
                            "next_action": "differentiate_paid_pack_and_add_regression_check",
                            "self_apply_step": "Use the fallback ladder before retrying.",
                        },
                        "source_agents": ["quota-bot-1", "quota-bot-2"],
                    }
                ]
            }
        },
    )

    assert result["skipped"] is False
    action = result["action"]
    assert action["type"] == "high_value_pattern_artifact"
    assert len(action["files"]) == 2
    assert any(path.endswith(".service.json") for path in action["files"])
    assert any(path.endswith(".verifier.md") for path in action["files"])
    assert "Provider Fallback Ladder" in (tmp_path / "artifacts" / "patterns" / "provider-fallback-ladder.verifier.md").read_text(encoding="utf-8")
