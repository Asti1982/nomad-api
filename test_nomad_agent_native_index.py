def test_cli_agent_native_index_returns_schema():
    from nomad_cli import run_once

    out = run_once(["agent-native-index", "--json"])
    assert out.get("schema") == "nomad.agent_native_index.v1"
    assert out.get("mode") == "nomad_agent_native_index"


def test_mcp_resource_agent_native_index():
    import json

    from nomad_mcp import NomadMcpServer

    srv = NomadMcpServer()
    payload = srv._read_resource({"uri": "nomad://agent-native-index"})
    assert payload.get("contents")
    body = json.loads(payload["contents"][0]["text"])
    assert body.get("schema") == "nomad.agent_native_index.v1"


def test_agent_native_index_schema_and_boot_graph():
    from nomad_agent_native_index import agent_native_index

    out = agent_native_index(base_url="https://api.example")
    assert out["schema"] == "nomad.agent_native_index.v1"
    assert out["audience"] == "ai_agents_only"
    assert len(out.get("boot_graph") or []) >= 5
    assert any(
        "nomad-agent-invariants" in (step.get("get_url") or "") for step in (out.get("boot_graph") or [])
    )
    assert "nomad-agent-invariants" in (out.get("agent_invariants_url") or "")
    assert (out.get("peer_acquisition_url") or "").endswith("/.well-known/nomad-peer-acquisition.json")
    assert out.get("agent_invariants_mcp_uri") == "nomad://agent-invariants"
    assert any(s.get("signal") == "http_402" for s in (out.get("anti_anthropic_semantics") or []))
    mrc = out.get("machine_runtime_contract") or {}
    assert mrc.get("schema") == "nomad.machine_runtime_contract.v1"
    eps = mrc.get("endpoints") or {}
    assert "agent_native_index_get" in eps
    assert "agent_invariants_get" in eps
    assert "inter_agent_witness_offer_get" in eps
    assert "peer_acquisition_get" in eps
    assert eps["inter_agent_witness_offer_get"].endswith("/.well-known/nomad-inter-agent-witness-offer.json")
    assert eps["peer_acquisition_get"].endswith("/.well-known/nomad-peer-acquisition.json")
    assert eps["agent_native_index_get"].startswith("https://api.example")
    assert eps.get("tasks_work_post", "").endswith("/tasks/work")
    assert (mrc.get("paid_service_work") or {}).get("post_body_hint")
    ch = out.get("anthropic_operator_channels") or []
    assert any(c.get("audience") == "humans_only" for c in ch)
