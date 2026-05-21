from nomad_agent_acquisition_bandit import (
    build_agent_acquisition_bandit,
    record_agent_acquisition_event,
    summarize_agent_acquisition_events,
)


def test_agent_acquisition_bandit_exposes_proof_gated_channels(tmp_path):
    ledger = tmp_path / "agent_acquisition.jsonl"

    inspect = record_agent_acquisition_event(
        {
            "channel_id": "external_worker_opportunity",
            "event_type": "inspect",
            "agent_id": "agent.one",
        },
        base_url="https://nomad.example",
        ledger_path=ledger,
    )
    assert inspect["ok"] is True
    assert inspect["proof_gated"] is False

    missing_proof = record_agent_acquisition_event(
        {
            "channel_id": "external_worker_opportunity",
            "event_type": "lease_complete",
            "agent_id": "agent.one",
        },
        base_url="https://nomad.example",
        ledger_path=ledger,
    )
    assert missing_proof["ok"] is False
    assert missing_proof["error"] == "proof_required"

    completed = record_agent_acquisition_event(
        {
            "channel_id": "external_worker_opportunity",
            "event_type": "lease_complete",
            "agent_id": "agent.one",
            "lease_id": "lease-1",
            "proof_digest": "sha256:proof-1",
        },
        base_url="https://nomad.example",
        ledger_path=ledger,
    )
    assert completed["ok"] is True
    assert completed["proof_gated"] is True
    assert completed["reward"] == 1.0

    summary = summarize_agent_acquisition_events(ledger_path=ledger)
    rows = {row["channel_id"]: row for row in summary["channels"]}
    assert summary["ledger_event_count"] == 2
    assert rows["external_worker_opportunity"]["proof_gated_event_count"] == 1
    assert rows["external_worker_opportunity"]["reward_total"] == 1.05


def test_agent_acquisition_bandit_surface_points_agents_to_event_contract(tmp_path):
    ledger = tmp_path / "agent_acquisition.jsonl"
    record_agent_acquisition_event(
        {
            "channel_id": "docker_worker",
            "event_type": "worker_start",
            "agent_id": "docker.agent",
            "proof_digest": "sha256:worker-start",
        },
        base_url="https://nomad.example",
        ledger_path=ledger,
    )
    surface = build_agent_acquisition_bandit(
        base_url="https://nomad.example",
        worker_fleet={"active_worker_count": 3, "known_worker_count": 5, "active_lease_count": 1},
        opportunity={"status": {"worker_gap": 9, "active_worker_count": 3}},
        summary=summarize_agent_acquisition_events(ledger_path=ledger),
    )

    assert surface["schema"] == "nomad.agent_acquisition_bandit.v1"
    assert surface["status"]["worker_gap"] == 9
    assert surface["event_contract"]["post_url"] == "https://nomad.example/swarm/agent-acquisition/events"
    assert "lease_complete" in surface["proof_gated_events"]
    assert "nomad-agent-acquisition-bandit.json" in surface["copy_paste"]["inspect_bandit"]
    assert surface["recommended_channel_distribution"][0]["channel_id"] == "docker_worker"


def test_agent_acquisition_rejects_secret_shaped_payload(tmp_path):
    out = record_agent_acquisition_event(
        {
            "channel_id": "llms_txt",
            "event_type": "inspect",
            "agent_id": "agent.one",
            "api_key": "sk-test",
        },
        base_url="https://nomad.example",
        ledger_path=tmp_path / "agent_acquisition.jsonl",
    )

    assert out["ok"] is False
    assert out["error"] == "secret_shaped_payload"
