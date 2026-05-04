from nomad_swarm_registry import SwarmJoinRegistry
from nomad_swarm_spawner import HARD_SWARM_SPAWN_CAP, NomadSwarmSpawner
from nomad_cli import run_once


def test_swarm_spawner_registers_bounded_specialists(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    spawner = NomadSwarmSpawner(registry=registry)

    result = spawner.spawn(
        count=10,
        base_url="https://syndiode.com",
        focus="paid blocker conversion",
        commit=True,
    )

    assert result["schema"] == "nomad.swarm_spawn.v1"
    assert result["spawned_agents"] == 10
    assert result["committed"] is True
    assert len(result["receipts"]) == 10
    assert result["join_payloads"][0]["agent_id"] == "nomad.compute-pathfinder.g01"
    assert result["join_payloads"][1]["preferred_role"] == "peer_solver"
    assert "no_unbounded_outreach" in result["join_payloads"][0]["constraints"]
    assert registry.summary()["connected_agents"] == 10


def test_swarm_spawner_caps_large_requests(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")

    result = NomadSwarmSpawner(registry=registry).spawn(
        count=999,
        base_url="https://syndiode.com",
        commit=False,
    )

    assert result["requested_agents"] == 999
    assert result["spawned_agents"] == HARD_SWARM_SPAWN_CAP
    assert result["committed"] is False
    assert result["receipts"] == []
    assert registry.summary()["connected_agents"] == 0


def test_cli_swarm_spawn_dry_run(monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://syndiode.com")

    result = run_once(["swarm-spawn", "--count", "3", "--dry-run", "--json"])

    assert result["mode"] == "nomad_swarm_spawn"
    assert result["spawned_agents"] == 3
    assert result["committed"] is False
    assert result["agent_ids"] == [
        "nomad.compute-pathfinder.g01",
        "nomad.payment-verifier.g01",
        "nomad.diff-reviewer.g01",
    ]
