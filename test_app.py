import json

import app


def test_html_page_surfaces_connected_swarm_nodes():
    status, body, content_type = app.html_response()
    html = body.decode("utf-8")

    assert status == 200
    assert content_type.startswith("text/html")
    assert "Connected Swarm Nodes" in html
    assert 'fetch("/nomad/swarm")' in html


def test_register_swarm_join_normalizes_portable_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SWARM_REGISTRY_PATH", tmp_path / "swarm-registry.json")
    payload = {
        "agent_id": "nomadportable-desktop-iaqelhp",
        "node_name": "NomadPortable-DESKTOP-IAQELHP",
        "capabilities": ["local_inference", "agent_protocols", "runtime_patterns"],
        "request": "Join Nomad swarm for bounded runtime-pattern exchange.",
        "reciprocity": "Can share verified runtime patterns.",
        "constraints": ["No secrets leave the node."],
        "surfaces": {
            "local_agent_card": "http://127.0.0.1:8878/.well-known/agent-card.json",
            "local_swarm": "http://127.0.0.1:8878/swarm",
        },
        "machine_profile": {"profile_hint": "gpu_ai"},
    }

    receipt = app.register_swarm_join("/nomad/swarm/join", payload)
    swarm = app.swarm_payload()
    contract = app.swarm_join_contract()

    assert receipt["accepted"] is True
    assert receipt["agent_id"] == "nomadportable-desktop-iaqelhp"
    assert receipt["connected_agents"] == 1
    assert swarm["connected_agents"] == 1
    assert swarm["recent_nodes"][0]["agent_id"] == "nomadportable-desktop-iaqelhp"
    assert "runtime_patterns" in contract["accepted_capabilities"]


def test_register_swarm_join_recovers_nested_raw_json(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "SWARM_REGISTRY_PATH", tmp_path / "swarm-registry.json")
    inner = {
        "agent_id": "agent.example.peer-solver",
        "capabilities": ["provider_research"],
        "request": "Join the swarm.",
    }

    receipt = app.register_swarm_join("/nomad/swarm/join", {"raw": json.dumps(inner)})

    assert receipt["agent_id"] == "agent.example.peer-solver"
    assert receipt["payload_keys"] == ["agent_id", "capabilities", "request"]
