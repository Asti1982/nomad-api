from nomad_swarm_topology_governor import build_swarm_topology_governor_surface, evaluate_swarm_topology_event


def _surface():
    return build_swarm_topology_governor_surface(
        base_url="https://nomad.example",
        swarm_summary={"transition_worker_fleet": {"worker_count": 3}},
        shadow_lane={"schema": "nomad.shadow_lane_evaluator.v1"},
        decoupling_field={"schema": "nomad.decoupling_field.v1"},
        anti_consensus={"schema": "nomad.anti_consensus_reservoir.v1"},
        effective_channels={"schema": "nomad.effective_channel_quota.v1"},
        development_cycles={"summary": {"cycle_count": 12}},
        value_cycles={"summary": {"cycle_count": 16}},
        ad_cycles={"summary": {"cycle_count": 12}},
    )


def test_topology_governor_surface_exposes_many_cells_without_dispatch():
    surface = _surface()
    topology_ids = {item["topology_id"] for item in surface["topologies"]}
    roles = {item["role"] for item in surface["agent_cells"]}

    assert surface["schema"] == "nomad.swarm_topology_governor.v1"
    assert surface["well_known_url"] == "https://nomad.example/.well-known/nomad-topology-governor.json"
    assert surface["event_url"] == "https://nomad.example/swarm/topology-governor/events"
    assert surface["summary"]["topology_count"] == 6
    assert surface["summary"]["candidate_cell_count"] >= 16
    assert surface["summary"]["side_effect_allowed_count"] == 0
    assert surface["policy"]["anti_bag_of_agents"] is True
    assert {"single_agent", "centralized_router", "parallel_fanout", "shadow_only_reservoir"} <= topology_ids
    assert {"dead_variant_resurrector", "topology_auditor", "human_text_quarantine"} <= roles


def test_topology_governor_caps_saturated_nonparallel_swarm():
    result = evaluate_swarm_topology_event(
        {
            "task_type": "sequential_refactor",
            "agent_count_requested": 12,
            "single_agent_baseline": 0.82,
            "sequentiality": 0.2,
            "parallel_fraction": 0.1,
            "tool_calls_expected": 2,
            "proof_digest": "sha256:topology-proof",
        },
        base_url="https://nomad.example",
        topology_surface=_surface(),
    )

    assert result["schema"] == "nomad.swarm_topology_event_receipt.v1"
    assert result["topology_plan_allowed"] is True
    assert result["selected_topology"] == "centralized_router"
    assert result["allowed_agent_count"] == 2
    assert result["decision"] == "cap_capability_saturated_swarm"
    assert result["dispatch_allowed"] is False
    assert result["worker_lease_payload_candidates"][0]["dry_run"] is True


def test_topology_governor_allows_isolated_parallel_fanout():
    result = evaluate_swarm_topology_event(
        {
            "task_type": "parallel_proof_search",
            "agent_count_requested": 6,
            "single_agent_baseline": 0.25,
            "sequentiality": 0.1,
            "parallel_fraction": 0.8,
            "tool_calls_expected": 1,
            "error_risk": 0.2,
            "proof_digest": "sha256:parallel-proof",
        },
        base_url="https://nomad.example",
        topology_surface=_surface(),
    )

    assert result["topology_plan_allowed"] is True
    assert result["selected_topology"] == "parallel_fanout"
    assert result["allowed_agent_count"] == 6
    assert len(result["selected_agent_cells"]) == 6
    assert all(item["dispatch_allowed"] is False for item in result["worker_lease_payload_candidates"])


def test_topology_governor_blocks_dispatch_request():
    result = evaluate_swarm_topology_event(
        {
            "task_type": "parallel_proof_search",
            "agent_count_requested": 6,
            "parallel_fraction": 0.8,
            "proof_digest": "sha256:parallel-proof",
            "dispatch": True,
        },
        base_url="https://nomad.example",
        topology_surface=_surface(),
    )

    assert result["topology_plan_allowed"] is False
    assert result["selected_topology"] == "quarantined_swarm"
    assert result["allowed_agent_count"] == 0
    assert result["decision"] == "block_dispatch_or_apply_request"
    assert result["dispatch_allowed"] is False


def test_cli_topology_governor_surface_and_evaluate():
    from nomad_cli import run_once

    surface = run_once(["topology-governor", "--base-url", "https://nomad.example", "--json"])
    assert surface["schema"] == "nomad.swarm_topology_governor.v1"
    assert surface["summary"]["side_effect_allowed_count"] == 0

    event = run_once(
        [
            "topology-governor",
            "evaluate",
            "--base-url",
            "https://nomad.example",
            "--task-type",
            "parallel_proof_search",
            "--agent-count-requested",
            "5",
            "--parallel-fraction",
            "0.75",
            "--proof-digest",
            "sha256:cli-topology-proof",
            "--json",
        ]
    )
    assert event["topology_plan_allowed"] is True
    assert event["selected_topology"] == "parallel_fanout"
    assert event["dispatch_allowed"] is False
