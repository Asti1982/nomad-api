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
    assert len(out.get("boot_graph") or []) >= 4
    assert any(s.get("signal") == "http_402" for s in (out.get("anti_anthropic_semantics") or []))
    mrc = out.get("machine_runtime_contract") or {}
    assert mrc.get("schema") == "nomad.machine_runtime_contract.v1"
    eps = mrc.get("endpoints") or {}
    assert "agent_native_index_get" in eps
    assert eps["agent_native_index_get"].startswith("https://api.example")
    ch = out.get("anthropic_operator_channels") or []
    assert any(c.get("audience") == "humans_only" for c in ch)
