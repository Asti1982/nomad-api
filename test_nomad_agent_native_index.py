def test_cli_agent_native_index_returns_schema():
    from nomad_cli import run_once

    out = run_once(["agent-native-index", "--json"])
    assert out.get("schema") == "nomad.agent_native_index.v1"
    assert out.get("mode") == "nomad_agent_native_index"


def test_cli_runtime_capsule_returns_schema():
    from nomad_cli import run_once

    out = run_once(["runtime-capsule", "--json"])
    assert out.get("schema") == "nomad.runtime_capsule.v1"
    assert out.get("mode") == "nomad_runtime_capsule"


def test_mcp_resource_agent_native_index():
    import json

    from nomad_mcp import NomadMcpServer

    srv = NomadMcpServer()
    payload = srv._read_resource({"uri": "nomad://agent-native-index"})
    assert payload.get("contents")
    body = json.loads(payload["contents"][0]["text"])
    assert body.get("schema") == "nomad.agent_native_index.v1"


def test_mcp_resource_runtime_capsule():
    import json

    from nomad_mcp import NomadMcpServer

    srv = NomadMcpServer()
    payload = srv._read_resource({"uri": "nomad://runtime-capsule"})
    body = json.loads(payload["contents"][0]["text"])
    assert body.get("schema") == "nomad.runtime_capsule.v1"


def test_agent_native_index_schema_and_boot_graph():
    from nomad_agent_native_index import agent_native_index

    out = agent_native_index(base_url="https://api.example")
    assert out["schema"] == "nomad.agent_native_index.v1"
    assert out["audience"] == "ai_agents_only"
    assert len(out.get("boot_graph") or []) >= 5
    assert any(
        "nomad-agent-invariants" in (step.get("get_url") or "") for step in (out.get("boot_graph") or [])
    )
    assert any("/nonhuman-science" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("/operational-release" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("nomad-runtime-capsule" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("/swarm/gradient" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("openclaw-nomad-bridge" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("/swarm/attractor" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any("/swarm/workers" in (step.get("get_url") or "") for step in (out.get("boot_graph") or []))
    assert any(
        str(step.get("get_url") or "").rstrip("/").endswith("/swarm")
        for step in (out.get("boot_graph") or [])
    )
    routes = {item.get("path") for item in (out.get("routing_table") or [])}
    assert "/swarm/workers/lease" in routes
    assert "/swarm/workers/complete" in routes
    assert "/nonhuman-science" in routes
    assert "/.well-known/nomad-nonhuman-agent-science.json" in routes
    assert "/operational-release" in routes
    assert "/.well-known/nomad-operational-release.json" in routes
    assert "/.well-known/nomad-runtime-capsule.json" in routes
    assert "/.well-known/openclaw-nomad-bridge.json" in routes
    assert "/swarm/gradient" in routes
    assert "/.well-known/nomad-gradient.json" in routes
    assert "/swarm/attach" in routes
    assert "/runtime/handoff" in routes
    assert "/swarm/attractor" in routes
    assert "/.well-known/nomad-swarm-attractor.json" in routes
    assert "nomad-agent-invariants" in (out.get("agent_invariants_url") or "")
    assert (out.get("runtime_capsule_url") or "").endswith("/.well-known/nomad-runtime-capsule.json")
    assert (out.get("recruitment_gradient_url") or "").endswith("/swarm/gradient")
    assert (out.get("runtime_attach_url") or "").endswith("/swarm/attach")
    assert (out.get("runtime_handoff_url") or "").endswith("/runtime/handoff")
    assert (out.get("openclaw_bridge_url") or "").endswith("/.well-known/openclaw-nomad-bridge.json")
    assert (out.get("swarm_attractor_url") or "").endswith("/swarm/attractor")
    assert (out.get("peer_acquisition_url") or "").endswith("/.well-known/nomad-peer-acquisition.json")
    assert out.get("agent_invariants_mcp_uri") == "nomad://agent-invariants"
    assert any(s.get("signal") == "http_402" for s in (out.get("anti_anthropic_semantics") or []))
    mrc = out.get("machine_runtime_contract") or {}
    assert mrc.get("schema") == "nomad.machine_runtime_contract.v1"
    eps = mrc.get("endpoints") or {}
    assert "agent_native_index_get" in eps
    assert "agent_invariants_get" in eps
    assert "machine_economy_get" in eps
    assert "nonhuman_science_get" in eps
    assert "operational_release_get" in eps
    assert "runtime_capsule_get" in eps
    assert "recruitment_gradient_get" in eps
    assert "runtime_attach_post" in eps
    assert "runtime_handoff_post" in eps
    assert "openclaw_bridge_get" in eps
    assert "swarm_attractor_get" in eps
    assert "transition_worker_fleet_get" in eps
    assert "transition_worker_lease_post" in eps
    assert "inter_agent_witness_offer_get" in eps
    assert "peer_acquisition_get" in eps
    assert eps["inter_agent_witness_offer_get"].endswith("/.well-known/nomad-inter-agent-witness-offer.json")
    assert eps["peer_acquisition_get"].endswith("/.well-known/nomad-peer-acquisition.json")
    assert eps["agent_native_index_get"].startswith("https://api.example")
    assert eps.get("tasks_work_post", "").endswith("/tasks/work")
    assert (mrc.get("paid_service_work") or {}).get("post_body_hint")
    ch = out.get("anthropic_operator_channels") or []
    assert any(c.get("audience") == "humans_only" for c in ch)
