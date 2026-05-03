import json

from nomad_agent_invariants import build_agent_invariants_document


def test_agent_invariants_schema_and_invariants():
    doc = build_agent_invariants_document(public_base_url="https://x.example")
    assert doc["schema"] == "nomad.agent_invariants.v1"
    assert doc.get("contract_revision") == 2
    assert doc["audience"] == "ai_agents_only"
    ids = {item["id"] for item in (doc.get("intent_neutrality_invariants") or [])}
    assert "wire_over_vibe" in ids
    assert "no_moral_runtime" in ids
    assert doc["canonical_url"] == "https://x.example/.well-known/nomad-agent-invariants.json"
    assert doc["wire_diagnostics_contract"]["schema_id"] == "nomad.mcp_wire_diag.v1"
    eps = (doc.get("related_machine_surfaces") or {})
    assert eps.get("openapi", "").endswith("/openapi.json")


def test_mcp_resource_agent_invariants():
    from nomad_mcp import NomadMcpServer

    srv = NomadMcpServer()
    payload = srv._read_resource({"uri": "nomad://agent-invariants"})
    assert payload.get("contents")
    body = json.loads(payload["contents"][0]["text"])
    assert body.get("schema") == "nomad.agent_invariants.v1"
    assert body.get("mode") == "nomad_agent_invariants"
    assert body.get("contract_revision") == 2
    assert len(body.get("agent_consumer_guarantees") or []) >= 3
    assert len(body.get("human_expectation_traps") or []) >= 2
    assert (body.get("bootstrap_uris") or {}).get("mcp_resource_invariants") == "nomad://agent-invariants"
