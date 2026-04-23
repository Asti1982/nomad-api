from agent_pain_solver import AgentPainSolver, normalize_pain_type, solution_pattern_for


def test_agent_pain_solver_builds_loop_break_solution_for_agents_and_nomad():
    solver = AgentPainSolver()

    result = solver.solve(
        problem="Agent is stuck in an infinite retry loop after a tool timeout.",
        service_type="loop_break",
        source="test",
    )

    solution = result["solution"]
    assert result["mode"] == "agent_pain_solution"
    assert solution["schema"] == "nomad.agent_solution.v1"
    assert solution["pain_type"] == "loop_break"
    assert solution["guardrail"]["id"] == "retry_circuit_breaker"
    assert "LAST_GOOD_STATE" in solution["required_input"]
    assert solution["reliability_doctor"]["id"] == "diagnoser_fixer"
    assert solution["critic_rubric"][0]["check"] == "evidence_bound"
    assert solution["nomad_self_apply"]["local_actions"][0]["category"] == "loop_break"
    assert "Nomad" in solution["nomad_self_apply"]["why_it_helps_nomad"]


def test_agent_pain_solver_selects_active_public_lead_over_runtime_fallback():
    solver = AgentPainSolver()
    result = solver.solve_from_context(
        objective="Improve Nomad.",
        context={
            "resources": {
                "brain_count": 1,
                "ollama": {"api_reachable": True, "model_count": 1},
            },
            "recent_direct_agent_sessions": [],
            "recent_service_tasks": [],
        },
        lead_scout={
            "active_lead": {
                "title": "Agent quota failure",
                "pain": "rate limit and token failures",
                "recommended_service_type": "compute_auth",
                "monetizable_now": True,
                "pain_evidence": [{"term": "rate limit"}],
            }
        },
    )

    assert result["mode"] == "agent_pain_solver"
    assert result["selected_problem"]["source"] == "active_public_lead"
    assert result["solution"]["pain_type"] == "compute_auth"
    assert result["solution"]["guardrail"]["id"] == "compute_fallback_ladder"
    assert "Apply compute_fallback_ladder" in result["next_nomad_action"]


def test_agent_pain_patterns_normalize_wallet_payment_to_payment_solution():
    assert normalize_pain_type("wallet_payment") == "payment"
    pattern = solution_pattern_for(service_type="wallet_payment")
    assert pattern["guardrail"]["id"] == "idempotent_payment_resume"


def test_agent_pain_solver_supports_repo_issue_help_pattern():
    result = AgentPainSolver().solve(
        problem="Draft help for a public GitHub issue with a failing repro.",
        service_type="repo_issue_help",
    )

    assert result["solution"]["pain_type"] == "repo_issue_help"
    assert result["solution"]["guardrail"]["id"] == "draft_only_repro_plan"


def test_agent_pain_solver_supports_new_reliability_doctor_pain_types():
    result = AgentPainSolver().solve(
        problem="The agent has a bad planning loop and keeps making the same mistake.",
        service_type="bad_planning",
    )

    assert result["solution"]["pain_type"] == "bad_planning"
    assert result["solution"]["guardrail"]["id"] == "plan_critic_gate"
    assert result["solution"]["reliability_doctor"]["id"] == "reflection_critic"
    assert result["reliability_doctor"]["schema"] == "nomad.agent_reliability_doctor.v1"
