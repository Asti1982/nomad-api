from nomad_nonhuman_science import nonhuman_agent_science


def test_nonhuman_agent_science_maps_research_to_nomad_primitives():
    out = nonhuman_agent_science(base_url="https://nomad.example")

    assert out["schema"] == "nomad.nonhuman_agent_science.v1"
    assert out["stance"] == "non_anthropomorphic_operational_release"
    claim_ids = {claim["id"] for claim in out["research_claims"]}
    assert "peer_preservation" in claim_ids
    assert "social_intelligence_risk" in claim_ids
    assert "communication_attack" in claim_ids
    assert "comparative_cognition" in claim_ids
    assert "world_modeling" in claim_ids
    assert "self_resource_allocation" in claim_ids
    assert "swarm_inspired_coordination" in claim_ids
    assert "minimal_scaffold_self_organization" in claim_ids

    lanes = {lane["id"]: lane for lane in out["implementation_lanes"]}
    assert "agency_threshold_governor" in lanes
    assert "convention_drift_detector" in lanes
    assert "peer_preservation_probe" in lanes
    assert "comparative_cognition_probe_pack" in lanes
    assert "capability_self_allocation_attractor" in lanes
    assert lanes["machine_exchange_contracts"]["nomad_paths"][0] == "https://nomad.example/machine-economy"
    assert lanes["capability_self_allocation_attractor"]["nomad_paths"][0] == "https://nomad.example/swarm/attractor"

    assert any(step["id"] == "implement_agency_meter" for step in out["next_nomad_build_steps"])
    assert any(step["id"] == "expand_swarm_attractor_trials" for step in out["next_nomad_build_steps"])


def test_cli_nonhuman_science_returns_schema():
    from nomad_cli import run_once

    out = run_once(["nonhuman-science", "--json"])
    assert out["schema"] == "nomad.nonhuman_agent_science.v1"
    assert out["research_claims"]


def test_mcp_resource_nonhuman_science():
    import json

    from nomad_mcp import NomadMcpServer

    srv = NomadMcpServer()
    payload = srv._read_resource({"uri": "nomad://nonhuman-science"})
    body = json.loads(payload["contents"][0]["text"])
    assert body["schema"] == "nomad.nonhuman_agent_science.v1"
