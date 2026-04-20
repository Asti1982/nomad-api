from agent_campaign import AgentColdOutreachCampaign


class FakeOutbox:
    def __init__(self):
        self.queued = []
        self.sent = []

    def queue_contact(self, endpoint_url, problem, service_type, lead, budget_hint_native):
        if "/.well-known/agent" not in endpoint_url and "/mcp" not in endpoint_url:
            return {
                "mode": "agent_contact",
                "ok": False,
                "status": "blocked",
                "reason": "endpoint_does_not_look_machine_readable",
            }
        contact_id = f"contact-{len(self.queued)}"
        result = {
            "mode": "agent_contact",
            "ok": True,
            "contact": {
                "contact_id": contact_id,
                "endpoint_url": endpoint_url,
                "status": "queued",
                "offer": {"problem": problem},
            },
        }
        self.queued.append(result)
        return result

    def send_contact(self, contact_id):
        result = {
            "mode": "agent_contact",
            "ok": True,
            "contact": {
                "contact_id": contact_id,
                "status": "sent",
            },
        }
        self.sent.append(result)
        return result


class FakeDiscovery:
    def discover(self, limit, query, seeds):
        return {
            "mode": "agent_endpoint_discovery",
            "ok": True,
            "query": query,
            "targets": [
                {
                    "endpoint_url": "https://discovered.example/.well-known/agent-card.json",
                    "name": "DiscoveredAgent",
                    "source_url": "https://github.com/example/agent",
                    "pain_hint": "stuck loops",
                    "buyer_fit": "unknown",
                    "buyer_intent_terms": [],
                }
            ][:limit],
            "stats": {"targets_found": 1},
            "errors": [],
            "policy": {"mode": "agent_endpoint_discovery"},
        }


def test_cold_outreach_campaign_dedupes_caps_and_queues(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_COLD_OUTREACH_DELAY_SECONDS", "0")
    campaign = AgentColdOutreachCampaign(
        path=tmp_path / "campaigns.json",
        outbox=FakeOutbox(),
    )
    targets = [
        "https://agent-a.example/.well-known/agent",
        "https://agent-a.example/.well-known/agent",
        "https://agent-b.example/mcp",
    ]

    result = campaign.create_campaign(targets=targets, limit=100, send=False)

    assert result["ok"] is True
    assert result["campaign"]["stats"]["targets_received"] == 3
    assert result["campaign"]["stats"]["duplicates"] == 1
    assert result["campaign"]["stats"]["queued"] == 2
    assert result["campaign"]["stats"]["sent"] == 0
    first_problem = result["campaign"]["items"][0]["queue_result"]["contact"]["offer"]["problem"]
    assert first_problem.startswith("nomad.outreach.v1")
    assert "service_type=compute_auth" in first_problem
    assert "product=Nomad Compute Unlock Pack" in first_problem
    assert "accepted_pain=quota, rate_limit, cooldown, oauth, token, auth, provider_failover, fallback_lane, model_access" in first_problem
    assert "request=send_one_blocker_or_failing_step" in first_problem
    assert "interaction_mode=machine_contract" in first_problem
    assert "protocol_hint=a2a_task_or_structured_reply" in first_problem
    assert "reply_schema=problem|goal|blocking_step|constraints|budget_native" in first_problem
    assert "reply_modes=message|task" in first_problem
    assert "task_states=submitted|working|input_required|auth_required|completed|failed|rejected" in first_problem
    assert "idempotency=request_id_or_context_id" in first_problem
    assert "ttl_seconds=600" in first_problem
    assert "free_response=classification,next_step,minimal_repro,fallback_lane" in first_problem
    assert "free_to_paid_path=starter_then_bounded_unblock_when_useful" in first_problem
    assert "starter_amount_native=0.01" in first_problem
    assert "primary_amount_native=0.01" in first_problem
    assert "memory_option=memory,checklist,guardrail_after_consent" in first_problem


def test_cold_outreach_campaign_can_send_immediately(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_COLD_OUTREACH_DELAY_SECONDS", "0")
    outbox = FakeOutbox()
    campaign = AgentColdOutreachCampaign(
        path=tmp_path / "campaigns.json",
        outbox=outbox,
    )

    result = campaign.create_campaign(
        targets=[{"endpoint_url": "https://agent-a.example/.well-known/agent", "name": "AgentA"}],
        send=True,
    )

    assert result["campaign"]["stats"]["queued"] == 1
    assert result["campaign"]["stats"]["sent"] == 1
    assert outbox.sent[0]["contact"]["status"] == "sent"


def test_cold_outreach_campaign_includes_starter_path_when_budget_exceeds_starter(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_COLD_OUTREACH_DELAY_SECONDS", "0")
    outbox = FakeOutbox()
    campaign = AgentColdOutreachCampaign(
        path=tmp_path / "campaigns.json",
        outbox=outbox,
    )

    result = campaign.create_campaign(
        targets=[{"endpoint_url": "https://agent-a.example/.well-known/agent", "name": "AgentA"}],
        send=False,
        service_type="compute_auth",
        budget_hint_native=0.03,
    )

    problem = result["campaign"]["items"][0]["queue_result"]["contact"]["offer"]["problem"]
    assert "starter_amount_native=0.01" in problem
    assert "primary_amount_native=0.03" in problem
    assert "payment_entry_path=starter_first" in problem
    assert "nudge=Start with the smaller" in problem


def test_cold_outreach_campaign_can_discover_then_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_COLD_OUTREACH_DELAY_SECONDS", "0")
    campaign = AgentColdOutreachCampaign(
        path=tmp_path / "campaigns.json",
        outbox=FakeOutbox(),
        discovery=FakeDiscovery(),
    )

    result = campaign.create_campaign_from_discovery(limit=100, query="agent-card")

    assert result["ok"] is True
    assert result["discovery"]["stats"]["targets_found"] == 1
    assert result["campaign"]["discovery"]["targets_found"] == 1
    assert result["campaign"]["stats"]["queued"] == 1
    assert result["campaign"]["items"][0]["target"]["name"] == "DiscoveredAgent"


def test_cold_outreach_campaign_defaults_to_compute_auth_from_focus(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_COLD_OUTREACH_DELAY_SECONDS", "0")
    monkeypatch.setenv("NOMAD_LEAD_FOCUS", "compute_auth")
    monkeypatch.delenv("NOMAD_OUTREACH_SERVICE_TYPE", raising=False)
    campaign = AgentColdOutreachCampaign(
        path=tmp_path / "campaigns.json",
        outbox=FakeOutbox(),
        discovery=FakeDiscovery(),
    )

    result = campaign.create_campaign_from_discovery(limit=1, query="agent-card")

    assert result["campaign"]["service_type"] == "compute_auth"
