from datetime import UTC, datetime, timedelta

from nomad_retention_evaluator import evaluate_retention


def test_retention_evaluator_flags_non_durable_empty_fleet():
    out = evaluate_retention(
        swarm_summary={
            "connected_agents": 0,
            "dormant_agents": 0,
            "prospect_agents": 0,
            "registry_storage": {"restart_durable": False, "remote_backend": "local_only"},
            "agent_retention_policy": {"recommended_heartbeat_seconds": 400},
        },
        worker_fleet={
            "active_worker_count": 0,
            "known_worker_count": 0,
            "active_lease_count": 0,
            "retention": {},
            "retention_policy": {"recommended_heartbeat_seconds": 300, "active_window_seconds": 900},
            "recent_workers": [],
        },
        base_url="https://nomad.example",
    )

    assert out["schema"] == "nomad.retention_evaluation.v1"
    assert out["decision"] == "restore_state_and_heartbeat_first"
    assert out["retention_score"] < 0.55
    assert {item["cause"] for item in out["causes"]} >= {"registry_not_restart_durable", "empty_fleet_after_restart"}
    assert out["next_actions"][0]["action"] == "enable_restart_durable_registry"


def test_retention_evaluator_rewards_returning_completed_durable_workers():
    recent = (datetime.now(UTC) - timedelta(seconds=90)).isoformat()
    out = evaluate_retention(
        swarm_summary={
            "connected_agents": 3,
            "dormant_agents": 0,
            "prospect_agents": 0,
            "registry_storage": {"restart_durable": True, "remote_backend": "firestore"},
            "agent_retention_policy": {"recommended_heartbeat_seconds": 400},
            "recent_nodes": [{"agent_id": "agent.a", "last_seen_at": recent}],
        },
        worker_fleet={
            "active_worker_count": 3,
            "known_worker_count": 3,
            "active_lease_count": 1,
            "retention": {
                "returning_workers_24h": 3,
                "completed_workers": 3,
                "completed_workers_24h": 3,
            },
            "retention_policy": {"recommended_heartbeat_seconds": 300, "active_window_seconds": 900},
            "recent_workers": [
                {"agent_id": "worker.a", "last_seen_at": recent},
                {"agent_id": "worker.b", "last_seen_at": recent},
            ],
        },
        base_url="https://nomad.example",
    )

    assert out["decision"] == "hold_and_expand"
    assert out["retention_score"] >= 0.8
    assert out["causes"] == []
    assert out["metrics"]["youngest_worker_age_seconds"] is not None
