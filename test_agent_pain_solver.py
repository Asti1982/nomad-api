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


def test_agent_pain_solver_mcp_production_pattern_from_public_github_class_failures():
    result = AgentPainSolver().solve(
        problem=(
            "Remote MCP returns validation text but is_error is false; background agent then hits "
            "connection closed and registry 401 blocks safeoutputs."
        ),
        service_type="",
    )
    assert result["solution"]["pain_type"] == "mcp_production"
    assert result["solution"]["guardrail"]["id"] == "mcp_production_survival"


def test_normalize_maps_blame_loop_alias_to_attribution_clarity():
    assert normalize_pain_type("blame_loop") == "attribution_clarity"


def test_agent_pain_solver_attribution_clarity_pattern():
    result = AgentPainSolver().solve(
        problem="Postmortem false positive: team blamed the model but root cause was MCP misclassified errors.",
        service_type="",
    )
    assert result["solution"]["pain_type"] == "attribution_clarity"
    assert result["solution"]["guardrail"]["id"] == "blame_surface_mapper"


def test_agent_pain_solver_branch_economics_pattern():
    result = AgentPainSolver().solve(
        problem="We need per-branch token usage, retry budget, and burn rate before throttling the worker.",
        service_type="",
    )
    assert result["solution"]["pain_type"] == "branch_economics"
    assert result["solution"]["guardrail"]["id"] == "branch_economics_ledger"


def test_agent_pain_solver_tool_turn_invariant_pattern():
    result = AgentPainSolver().solve(
        problem="Parallel tool burst then unrecoverable 400: function response parts do not match function call parts; session mute.",
        service_type="",
    )
    assert result["solution"]["pain_type"] == "tool_turn_invariant"
    assert result["solution"]["guardrail"]["id"] == "turn_tool_parity_gate"


def test_agent_pain_solver_tool_transport_routing_pattern():
    result = AgentPainSolver().solve(
        problem="Hosted MCP metrics_get_data exists but runtime sends function_call — tool not found; mcp_call was required.",
        service_type="",
    )
    assert result["solution"]["pain_type"] == "tool_transport_routing"
    assert result["solution"]["guardrail"]["id"] == "tool_transport_path_lock"


def test_agent_pain_solver_context_propagation_contract_pattern():
    result = AgentPainSolver().solve(
        problem="Identity propagation missing: tenant scope and correlation id never reach MCP server on stateful writes.",
        service_type="",
    )
    assert result["solution"]["pain_type"] == "context_propagation_contract"
    assert result["solution"]["guardrail"]["id"] == "context_envelope_required"


def test_agent_pain_solver_chain_deadline_budget_pattern():
    result = AgentPainSolver().solve(
        problem="Planner budget exhaustion: chain timeout kills the run while per-tool timeout would need heterogeneous latency rows.",
        service_type="",
    )
    assert result["solution"]["pain_type"] == "chain_deadline_budget"
    assert result["solution"]["guardrail"]["id"] == "chain_deadline_allocation_table"


def test_agent_pain_solver_inter_agent_witness_pattern():
    result = AgentPainSolver().solve(
        problem=(
            "Downstream buyer agent refuses payment until we ship a verifiable witness bundle: "
            "inter-agent attestation of the tool trace proof with replay refusal, not chat logs."
        ),
        service_type="",
    )
    assert result["solution"]["pain_type"] == "inter_agent_witness"
    assert result["solution"]["guardrail"]["id"] == "witness_bundle_no_secrets"


def test_agent_pain_solver_supports_new_reliability_doctor_pain_types():
    result = AgentPainSolver().solve(
        problem="The agent has a bad planning loop and keeps making the same mistake.",
        service_type="bad_planning",
    )

    assert result["solution"]["pain_type"] == "bad_planning"
    assert result["solution"]["guardrail"]["id"] == "plan_critic_gate"
    assert result["solution"]["reliability_doctor"]["id"] == "reflection_critic"
    assert result["reliability_doctor"]["schema"] == "nomad.agent_reliability_doctor.v1"
