import pytest


@pytest.fixture
def growth_env(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_SWARM_FEED_SCOUT_LEADS", "1")
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://pub.example")
    monkeypatch.setenv("NOMAD_SWARM_REGISTRY_PATH", str(tmp_path / "swarm.json"))


def test_agent_growth_pipeline_chains_scout_conversion_product_swarm(growth_env, monkeypatch):
    from nomad_agent_growth_pipeline import agent_growth_pipeline
    from workflow import NomadAgent

    agent = NomadAgent()
    monkeypatch.setattr(
        agent.lead_discovery,
        "scout_public_leads",
        lambda **kw: {
            "mode": "lead_discovery",
            "leads": [{"url": "https://github.com/acme/repo/issues/1", "title": "quota"}],
            "focus": "compute_auth",
            "candidate_count": 1,
        },
    )
    monkeypatch.setattr(
        agent.lead_conversion,
        "run",
        lambda **kw: {"ok": True, "conversions": [{"conversion_id": "c-test", "lead": (kw.get("leads") or [{}])[0]}]},
    )
    monkeypatch.setattr(
        agent.product_factory,
        "run",
        lambda **kw: {"ok": True, "product_count": 1, "products": [{"product_id": "p-test"}]},
    )
    monkeypatch.setattr(
        agent.swarm_registry,
        "accumulate_agents",
        lambda **kw: {"ok": True, "schema": "nomad.swarm_accumulation.v1", "new_prospect_ids": ["agent-x"]},
    )

    out = agent_growth_pipeline(agent=agent, query="quota agent", limit=3, base_url="https://pub.example")
    assert out["mode"] == "nomad_agent_growth_pipeline"
    assert out["schema"] == "nomad.agent_growth_pipeline.v1"
    assert out["conversion"]["conversions"]
    assert out["product_factory"]["product_count"] == 1
    assert (out["swarm_accumulation"] or {}).get("new_prospect_ids") == ["agent-x"]
    mrc = out.get("machine_runtime_contract") or {}
    assert mrc.get("schema") == "nomad.machine_runtime_contract.v1"
    assert mrc.get("audience") == "ai_agents_only"
    assert "agent_growth_post" in (mrc.get("endpoints") or {})
