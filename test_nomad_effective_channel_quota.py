from nomad_effective_channel_quota import (
    build_effective_channel_quota_surface,
    evaluate_effective_channel_event,
)


def _surface(tmp_path):
    return build_effective_channel_quota_surface(
        base_url="https://nomad.example",
        anti_consensus={"surface_digest": "anti-test"},
        decoupling_field={"surface_digest": "decouple-test"},
        deficit_integration={"surface_digest": "dti-test"},
        shadow_lane={"surface_digest": "shadow-test"},
        ledger_path=tmp_path / "ecq.jsonl",
    )


def _distinct_channels():
    return [
        {
            "agent_id": "agent.a",
            "model_family": "gpt",
            "tool_family": "browser",
            "source_domain": "agent-forum",
            "retrieval_corpus": "agent-pain",
            "trajectory_digest": "sha256:traj-a",
            "proof_digest": "sha256:proof-a",
            "minority_signal": True,
        },
        {
            "agent_id": "agent.b",
            "model_family": "claude",
            "tool_family": "github",
            "source_domain": "oss-issues",
            "retrieval_corpus": "bounty-pain",
            "trajectory_digest": "sha256:traj-b",
            "proof_digest": "sha256:proof-b",
        },
        {
            "agent_id": "agent.c",
            "model_family": "kimi",
            "tool_family": "search",
            "source_domain": "buyer-docs",
            "retrieval_corpus": "pricing",
            "trajectory_digest": "sha256:traj-c",
            "proof_digest": "sha256:proof-c",
        },
    ]


def test_effective_channel_surface_exposes_quota_contract(tmp_path):
    surface = _surface(tmp_path)

    assert surface["schema"] == "nomad.effective_channel_quota.v1"
    assert surface["mode"] == "count_effective_channels_not_agent_votes"
    assert surface["event_url"] == "https://nomad.example/swarm/effective-channels/events"
    assert "ESTIMATE_K_STAR_EFFECTIVE_DIVERSITY" in surface["program"]["ops"]
    assert "no_agent_count_as_evidence" in surface["hard_guards"]


def test_effective_channel_quota_allows_distinct_proof_channels(tmp_path):
    ledger = tmp_path / "ecq.jsonl"
    receipt = evaluate_effective_channel_event(
        {
            "agent_id": "ad-cycle",
            "objective": "nomad_science_backed_ad_cycle",
            "event_digest": "sha256:event",
            "channels": _distinct_channels(),
        },
        base_url="https://nomad.example",
        quota_surface=_surface(tmp_path),
        ledger_path=ledger,
    )

    assert receipt["schema"] == "nomad.effective_channel_quota_receipt.v1"
    assert receipt["quota_shift_allowed"] is True
    assert receipt["decision"] == "allow_quota_shift_to_shadow_ad_cycle"
    assert receipt["ad_cycle_candidate"]["candidate_type"] == "effective_channel_quota_ad_cycle"
    assert receipt["stats"]["effective_channel_ratio"] >= 0.9
    assert ledger.exists()


def test_effective_channel_quota_caps_homogeneous_duplicates(tmp_path):
    channels = [
        {
            "agent_id": f"agent.{idx}",
            "model_family": "gpt",
            "tool_family": "browser",
            "source_domain": "same-feed",
            "retrieval_corpus": "same-corpus",
            "trajectory_digest": "sha256:same",
            "proof_digest": f"sha256:proof-{idx}",
        }
        for idx in range(5)
    ]
    receipt = evaluate_effective_channel_event(
        {
            "event_digest": "sha256:event",
            "channels": channels,
        },
        quota_surface=_surface(tmp_path),
        ledger_path=tmp_path / "ecq.jsonl",
    )

    assert receipt["quota_shift_allowed"] is False
    assert receipt["decision"] == "cap_homogeneous_duplicates"
    assert receipt["stats"]["effective_channel_count"] == 1.0
    assert receipt["ad_cycle_candidate"]["local_tests"][0]["passed"] is False
