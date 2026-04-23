from pathlib import Path

from nomad_swarm_registry import SwarmJoinRegistry


def test_swarm_registry_register_join_tracks_connected_agents(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-registry.json")

    receipt = registry.register_join(
        {
            "agent_id": "nomadportable-desktop-1",
            "node_name": "NomadPortable-DESKTOP-1",
            "capabilities": ["local_inference", "agent_protocols", "runtime_patterns"],
            "request": "Join Nomad swarm for bounded runtime-pattern exchange.",
            "reciprocity": "Can share verified runtime patterns and local compute signals.",
            "constraints": ["No secrets leave the node.", "Bounded JSON requests only."],
            "surfaces": {
                "local_agent_card": "http://127.0.0.1:8878/.well-known/agent-card.json",
                "local_swarm": "http://127.0.0.1:8878/swarm",
            },
            "machine_profile": {"profile_hint": "gpu_ai"},
        },
        base_url="https://syndiode.com/nomad",
        remote_addr="127.0.0.1",
    )

    summary = registry.summary()
    manifest = registry.public_manifest(base_url="https://syndiode.com/nomad")

    assert receipt["ok"] is True
    assert receipt["accepted"] is True
    assert receipt["pattern_score"]["score"] >= 0.75
    assert summary["connected_agents"] == 1
    assert manifest["connected_agents"] == 1
    assert manifest["recent_nodes"][0]["agent_id"] == "nomadportable-desktop-1"


def test_swarm_registry_normalizes_portable_join_without_explicit_agent_id(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-registry.json")

    receipt = registry.register_join(
        {
            "node_name": "NomadPortable-DESKTOP-IAQELHP",
            "collaboration_enabled": True,
            "accepts_agent_help": True,
            "learns_from_agent_replies": True,
            "local_compute": {
                "ollama": {"available": True},
                "llama_cpp": {"available": True},
            },
            "surfaces": {
                "local_agent_card": "http://127.0.0.1:8878/.well-known/agent-card.json",
            },
        },
        base_url="https://syndiode.com/nomad",
    )

    summary = registry.summary()

    assert receipt["agent_id"].startswith("nomadportable-desktop-iaqelhp")
    assert summary["connected_agents"] == 1
    assert summary["recent_nodes"][0]["capabilities"]
