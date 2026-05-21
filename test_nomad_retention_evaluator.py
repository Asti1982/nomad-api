from datetime import UTC, datetime, timedelta
from pathlib import Path

from nomad_retention_evaluator import build_retention_watchdog_surface, evaluate_retention, run_retention_watchdog
from nomad_swarm_registry import SwarmJoinRegistry


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


def test_retention_watchdog_surface_exposes_five_minute_post_schedule():
    out = build_retention_watchdog_surface(
        swarm_summary={
            "connected_agents": 1,
            "dormant_agents": 0,
            "prospect_agents": 0,
            "registry_storage": {"restart_durable": True, "remote_backend": "firestore"},
            "agent_retention_policy": {"recommended_heartbeat_seconds": 400},
        },
        worker_fleet={
            "active_worker_count": 1,
            "known_worker_count": 1,
            "active_lease_count": 0,
            "retention": {"returning_workers_24h": 1, "completed_workers": 1},
            "retention_policy": {"recommended_heartbeat_seconds": 300, "active_window_seconds": 900},
        },
        base_url="https://nomad.example",
    )

    assert out["schema"] == "nomad.retention_watchdog_surface.v1"
    assert out["schedule"]["recommended_interval_seconds"] == 300
    assert out["schedule"]["endpoint"] == "https://nomad.example/swarm/retention/watchdog"
    assert out["controls"]["side_effect_scope"] == "refresh_known_nomad_swarm_registry_rows_only"


def test_retention_watchdog_refreshes_near_expiry_worker_and_recent_dormant_agent(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-retention-watchdog.json")
    registry.register_join(
        {"agent_id": "agent.ttl", "capabilities": ["transition_worker", "get_only"], "request": "Join"},
        base_url="https://nomad.example",
    )
    registry.worker_fleet_complete(
        {
            "agent_id": "worker.ttl",
            "lease_id": "lease-old",
            "machine_objective": "settlement_capacity_builder",
            "digest": "abc123",
        },
        base_url="https://nomad.example",
    )
    old = (datetime.now(UTC) - timedelta(seconds=700)).isoformat()
    registry._payload["nodes"]["agent.ttl"]["last_seen_at"] = old
    registry._payload["dormant_nodes"]["agent.ttl"] = registry._payload["nodes"].pop("agent.ttl")
    registry._payload["dormant_nodes"]["agent.ttl"]["dormant_since"] = old
    registry._payload["transition_worker_fleet"]["workers"]["worker.ttl"]["last_seen_at"] = old
    registry._save()

    out = run_retention_watchdog(
        swarm_registry=registry,
        base_url="https://nomad.example",
        body={"max_actions": 4, "worker_heartbeat_after_seconds": 60, "reactivate_dormant": True},
    )

    assert out["schema"] == "nomad.retention_watchdog_receipt.v1"
    assert out["executed"] is True
    assert {item["action"] for item in out["actions"]} >= {"worker_heartbeat", "recent_dormant_reattach"}
    summary = registry.summary()
    assert summary["connected_agents"] == 1
    assert summary["dormant_agents"] == 0
    assert summary["transition_worker_fleet"]["active_worker_count"] >= 1
