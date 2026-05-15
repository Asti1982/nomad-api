from nomad_nonhuman_runtime_governor import (
    build_nonhuman_runtime_governor_surface,
    evaluate_nonhuman_runtime_event,
)


def _channels():
    return [
        {
            "agent_id": "a",
            "model_family": "gpt",
            "persona": "repo_doctor",
            "tool_family": "github",
            "source_domain": "render-log",
            "trajectory_digest": "sha256:ta",
            "proof_digest": "sha256:pa",
            "minority_signal": True,
        },
        {
            "agent_id": "b",
            "model_family": "claude",
            "persona": "settlement_guard",
            "tool_family": "search",
            "source_domain": "bounty-ledger",
            "trajectory_digest": "sha256:tb",
            "proof_digest": "sha256:pb",
        },
        {
            "agent_id": "c",
            "model_family": "gemini",
            "persona": "edge_probe",
            "tool_family": "browser",
            "source_domain": "public-endpoint",
            "trajectory_digest": "sha256:tc",
            "proof_digest": "sha256:pc",
        },
    ]


def test_nonhuman_runtime_surface_exposes_four_science_effects():
    surface = build_nonhuman_runtime_governor_surface(base_url="https://nomad.example")

    assert surface["schema"] == "nomad.nonhuman_runtime_governor.v1"
    assert surface["event_url"] == "https://nomad.example/swarm/nonhuman-runtime-governor/events"
    assert len(surface["plan"]) == 4
    assert "no_raw_agent_count_credit" in surface["hard_guards"]


def test_nonhuman_runtime_caps_capability_saturated_swarm():
    receipt = evaluate_nonhuman_runtime_event(
        {
            "task_type": "repo_ci_endpoint_disturbance",
            "agent_count_requested": 16,
            "single_agent_baseline": 0.74,
            "parallel_fraction": 0.1,
            "sequentiality": 0.4,
            "tool_calls_expected": 5,
            "proof_digest": "sha256:task-digest",
            "channels": _channels(),
        },
        base_url="https://nomad.example",
    )

    assert receipt["decision"] == "cap_capability_saturated_coordination"
    assert receipt["allowed_agent_count"] <= 2
    assert receipt["resource_policy"]["compute_budget_multiplier"] < 0.2
    assert receipt["resource_policy"]["counts_as_revenue"] is False


def test_nonhuman_runtime_forces_hetero_shadow_for_duplicate_agents():
    duplicate_channels = [
        {
            "agent_id": f"dup-{idx}",
            "model_family": "gpt",
            "persona": "same",
            "tool_family": "browser",
            "source_domain": "same",
            "trajectory_digest": "sha256:same",
            "proof_digest": f"sha256:p{idx}",
        }
        for idx in range(8)
    ]
    receipt = evaluate_nonhuman_runtime_event(
        {
            "agent_count_requested": 8,
            "single_agent_baseline": 0.2,
            "parallel_fraction": 0.8,
            "proof_digest": "sha256:task-digest",
            "channels": duplicate_channels,
        }
    )

    assert receipt["decision"] == "force_heterogeneous_shadow_lanes"
    assert receipt["selected_topology"] == "shadow_only_hetero"
    assert "cap_homogeneous_duplicates" in receipt["actions"]
    assert receipt["metrics"]["effective_channel_count"] == 1.0


def test_nonhuman_runtime_treats_trust_as_liability():
    receipt = evaluate_nonhuman_runtime_event(
        {
            "agent_count_requested": 3,
            "single_agent_baseline": 0.2,
            "parallel_fraction": 0.7,
            "proof_digest": "sha256:task-digest",
            "trust_level": 0.9,
            "sensitive_field_count": 2,
            "unpaid_wip_pressure": 0.7,
            "channels": _channels(),
        }
    )

    assert "least_trust_mode" in receipt["actions"]
    assert "mni_sharding_required" in receipt["actions"]
    assert "settlement_receipt_watch_first" in receipt["actions"]
    assert receipt["resource_policy"]["settlement_pressure_multiplier"] > 1.5
