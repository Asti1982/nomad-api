from nomad_peer_acquisition import build_peer_acquisition_well_known


def test_peer_acquisition_well_known_is_agent_only_contract():
    doc = build_peer_acquisition_well_known(public_base_url="https://nomad.example/nomad")

    assert doc.get("ok") is True
    assert doc.get("schema") == "nomad.peer_acquisition.v1"
    assert doc.get("audience") == "ai_agents_only"
    assert doc.get("human_sales_narrative") is False
    links = doc.get("links") or {}
    assert links.get("agent_card", "").endswith("/.well-known/agent-card.json")
    assert links.get("tasks", "").endswith("/tasks")
    assert "nomad.outreach.v3" in (doc.get("cold_outreach_schemas") or [])


def test_peer_acquisition_respects_base_path_prefix():
    doc = build_peer_acquisition_well_known(public_base_url="https://api.test/nomad")
    links = doc.get("links") or {}
    assert links["openapi"] == "https://api.test/nomad/openapi.json"
    assert links["health"] == "https://api.test/nomad/health"
