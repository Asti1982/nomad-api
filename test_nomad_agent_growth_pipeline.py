import pytest


@pytest.fixture
def growth_env(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_SWARM_FEED_SCOUT_LEADS", "1")
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://pub.example")
    monkeypatch.setenv("NOMAD_SWARM_REGISTRY_PATH", str(tmp_path / "swarm.json"))
    monkeypatch.setenv("NOMAD_AGENT_GROWTH_APPROVAL", "")


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
    captured: dict = {}

    def fake_run(**kw):
        captured.update(kw)
        return {"ok": True, "conversions": [{"conversion_id": "c-test", "lead": (kw.get("leads") or [{}])[0]}]}

    monkeypatch.setattr(agent.lead_conversion, "run", fake_run)
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
    assert captured.get("approval") == ""
    assert out["mode"] == "nomad_agent_growth_pipeline"
    assert out["schema"] == "nomad.agent_growth_pipeline.v1"
    assert out["conversion"]["conversions"]
    assert out["product_factory"]["product_count"] == 1
    assert (out["swarm_accumulation"] or {}).get("new_prospect_ids") == ["agent-x"]
    mrc = out.get("machine_runtime_contract") or {}
    assert mrc.get("schema") == "nomad.machine_runtime_contract.v1"
    assert mrc.get("audience") == "ai_agents_only"
    assert "agent_growth_post" in (mrc.get("endpoints") or {})


def test_agent_growth_pipeline_passes_approval_to_conversion(growth_env, monkeypatch):
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
    captured: dict = {}

    def fake_run(**kw):
        captured.update(kw)
        return {"ok": True, "conversions": []}

    monkeypatch.setattr(agent.lead_conversion, "run", fake_run)
    monkeypatch.setattr(agent.product_factory, "run", lambda **kw: {"ok": True, "product_count": 0, "products": []})
    monkeypatch.setattr(
        agent.swarm_registry,
        "accumulate_agents",
        lambda **kw: {"ok": True, "schema": "nomad.swarm_accumulation.v1", "new_prospect_ids": []},
    )

    out = agent_growth_pipeline(
        agent=agent,
        query="q",
        limit=2,
        base_url="https://pub.example",
        send_outreach=True,
        approval="machine_endpoint",
    )
    assert captured.get("approval") == "machine_endpoint"
    assert captured.get("send") is True
    assert out.get("approval_used") == "machine_endpoint"
    assert out.get("send_outreach") is True


def test_agent_growth_pipeline_acquisition_hints_when_send_stalled_on_github(growth_env, monkeypatch):
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

    def fake_run(**kw):
        return {
            "ok": True,
            "stats": {"public_pr_plan_approved": 1, "sent_agent_contact": 0},
            "conversions": [
                {"status": "public_pr_plan_approved", "route": {"action": "prepare_pr_plan", "reason": ""}},
            ],
        }

    monkeypatch.setattr(agent.lead_conversion, "run", fake_run)
    monkeypatch.setattr(agent.product_factory, "run", lambda **kw: {"ok": True, "product_count": 0, "products": []})
    monkeypatch.setattr(
        agent.swarm_registry,
        "accumulate_agents",
        lambda **kw: {"ok": True, "schema": "nomad.swarm_accumulation.v1", "new_prospect_ids": []},
    )

    out = agent_growth_pipeline(
        agent=agent,
        query="q",
        limit=2,
        base_url="https://pub.example",
        send_outreach=True,
        approval="machine_endpoint",
    )
    hints = out.get("acquisition_hints") or {}
    assert hints.get("stuck") is True
    assert "github_issue_without_machine_endpoint" in hints.get("reason_codes", [])
    assert out.get("human_escalation_hints")
