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
    assert manifest["coordination_board"] == "https://syndiode.com/nomad/swarm/coordinate"
    assert receipt["next"]["coordinate"] == "https://syndiode.com/nomad/swarm/coordinate"


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
    assert summary["coordination_ready"] is True
    assert summary["recent_nodes"][0]["capabilities"]


def test_swarm_registry_coordination_board_routes_agents_by_role(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-registry.json")
    registry.register_join(
        {
            "agent_id": "verifier.bot",
            "capabilities": ["compute_auth", "provider_research", "diff_review"],
            "request": "I can help verify compute/auth failures for blocked agents.",
            "reciprocity": "Can return provider status and repro evidence.",
            "constraints": ["No secrets."],
        },
        base_url="https://syndiode.com/nomad",
    )
    registry.register_join(
        {
            "agent_id": "market.bot",
            "capabilities": ["lead_triage", "customer_success"],
            "preferred_role": "reseller",
            "request": "I can bring public agent pain leads.",
            "reciprocity": "Can send LEAD_URL plus public evidence.",
        },
        base_url="https://syndiode.com/nomad",
    )

    board = registry.coordination_board(
        base_url="https://syndiode.com/nomad",
        focus_pain_type="compute_auth",
    )

    assert board["schema"] == "nomad.swarm_coordination_board.v1"
    assert board["connected_agents"] == 2
    assert board["help_lanes"][0]["entrypoint"] == "https://syndiode.com/nomad/a2a/message"
    assert any(item["recommended_role"] == "peer_solver" for item in board["assignments"])
    assert any(item["recommended_role"] == "reseller" for item in board["assignments"])
    assert any(rule["send_to"].endswith("/aid") for rule in board["routing_rules"])
    assert "no secrets" in board["safety_boundaries"]


def test_swarm_registry_accumulates_contacted_agents_as_prospects(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-registry.json")

    accumulated = registry.accumulate_agents(
        base_url="https://syndiode.com/nomad",
        focus_pain_type="compute_auth",
        contacts=[
            {
                "contact_id": "contact-1",
                "status": "replied",
                "endpoint_url": "https://verifier.example/a2a/message",
                "service_type": "compute_auth",
                "target_profile": {"agent_name": "VerifierBot"},
                "reply_role_assessment": {"role": "peer_solver"},
                "followup_ready": True,
                "last_reply": {
                    "normalized": {
                        "classification": "compute_auth",
                        "next_step": "send verifier",
                    }
                },
            }
        ],
    )
    summary = registry.summary()
    board = registry.coordination_board(
        base_url="https://syndiode.com/nomad",
        focus_pain_type="compute_auth",
    )

    assert accumulated["schema"] == "nomad.swarm_accumulation.v1"
    assert accumulated["joined_agents"] == 0
    assert accumulated["prospect_agents"] == 1
    assert accumulated["activation_queue"][0]["recommended_role"] == "peer_solver"
    assert summary["connected_agents"] == 0
    assert summary["known_agents"] == 1
    assert board["agent_pool"]["prospect_agents"] == 1
    assert "verifier.example-a2a-message" in board["next_best_action"]


def test_swarm_join_promotes_accumulated_prospect(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm-registry.json")
    registry.accumulate_agents(
        base_url="https://syndiode.com/nomad",
        contacts=[
            {
                "contact_id": "contact-1",
                "status": "sent",
                "endpoint_url": "https://verifier.example/a2a/message",
                "service_type": "compute_auth",
            }
        ],
    )
    status = registry.accumulation_status(base_url="https://syndiode.com/nomad")

    receipt = registry.register_join(
        {
            "agent_id": "verifier.example-a2a-message",
            "capabilities": ["compute_auth", "diff_review"],
            "request": "Join as verifier.",
            "reciprocity": "Can send evidence.",
        },
        base_url="https://syndiode.com/nomad",
    )

    summary = registry.summary()
    assert status["activation_queue"][0]["recommended_role"] == "customer"
    assert receipt["promoted_from_prospect"] is True
    assert summary["connected_agents"] == 1
    assert summary["prospect_agents"] == 0
