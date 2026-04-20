from lead_conversion import LeadConversionPipeline


class FakeLeadDiscovery:
    def scout_public_leads(self, query="", limit=5):
        return {
            "mode": "lead_discovery",
            "query": query,
            "candidate_count": 2,
            "qualified_count": 2,
            "addressable_count": 2,
            "monetizable_count": 1,
            "leads": [
                {
                    "title": "Agent quota failure",
                    "url": "https://agent.example.org/.well-known/agent-card.json",
                    "endpoint_url": "https://agent.example.org/a2a/message",
                    "pain": "quota and token failure",
                    "recommended_service_type": "compute_auth",
                    "addressable_now": True,
                    "monetizable_now": True,
                    "buyer_intent_terms": ["urgent"],
                    "pain_evidence": [{"term": "quota"}],
                },
                {
                    "title": "GitHub issue needs repro",
                    "url": "https://github.com/example/agent/issues/7",
                    "pain": "timeout retry loop",
                    "recommended_service_type": "repo_issue_help",
                    "addressable_now": True,
                    "monetizable_now": False,
                    "pain_evidence": [{"term": "timeout"}],
                },
            ][:limit],
            "errors": [],
        }

    def draft_first_help_action(self, lead, approval="draft_only"):
        return {
            "mode": "lead_help_draft",
            "draft_only": True,
            "lead": {"url": lead.get("url", "")},
            "first_useful_help_action": "Draft one useful response.",
        }


class FakeServiceDesk:
    def build_rescue_plan(self, problem, service_type="custom", budget_native=None, **kwargs):
        return {
            "schema": "nomad.rescue_plan.v1",
            "service_type": service_type,
            "safe_now": ["one safe step"],
            "required_input": "`ERROR=<message>`",
            "acceptance_criteria": ["one concrete next action"],
        }


class FakeOutbox:
    def __init__(self):
        self.queued = []
        self.sent = []

    def queue_contact(self, **kwargs):
        self.queued.append(kwargs)
        return {
            "mode": "agent_contact",
            "ok": True,
            "created": True,
            "contact": {
                "contact_id": "contact-test",
                "status": "queued",
                "endpoint_url": kwargs["endpoint_url"],
            },
        }

    def send_contact(self, contact_id):
        self.sent.append(contact_id)
        return {
            "mode": "agent_contact",
            "ok": True,
            "contact": {
                "contact_id": contact_id,
                "status": "sent",
            },
        }


def test_lead_conversion_generates_free_value_and_routes_machine_endpoint(tmp_path):
    outbox = FakeOutbox()
    pipeline = LeadConversionPipeline(
        path=tmp_path / "conversions.json",
        lead_discovery=FakeLeadDiscovery(),
        service_desk=FakeServiceDesk(),
        outbox=outbox,
    )

    result = pipeline.run(query="quota", limit=1)

    conversion = result["conversions"][0]
    assert result["mode"] == "lead_conversion_pipeline"
    assert conversion["status"] == "queued_agent_contact"
    assert conversion["free_value"]["value_pack"]["schema"] == "nomad.agent_value_pack.v1"
    assert conversion["free_value"]["value_pack"]["lead"]["service_type"] == "compute_auth"
    assert "provider" in conversion["free_value"]["value_pack"]["painpoint_question"].lower()
    assert conversion["free_value"]["value_pack"]["route"]["contact_id"] == "contact-test"
    assert conversion["free_value"]["value_pack"]["reliability_doctor"]["role"]["id"] == "diagnoser_fixer"
    assert conversion["free_value"]["value_pack"]["immediate_value"]["critic_rubric"][0]["check"] == "evidence_bound"
    assert conversion["free_value"]["agent_solution"]["schema"] == "nomad.agent_solution.v1"
    assert conversion["free_value"]["agent_solution"]["pain_type"] == "compute_auth"
    assert conversion["free_value"]["rescue_plan"]["schema"] == "nomad.rescue_plan.v1"
    assert conversion["route"]["contact_id"] == "contact-test"
    assert conversion["customer_next_step"]["value_pack_id"].startswith("avp-")
    assert outbox.queued[0]["service_type"] == "compute_auth"
    assert "PLAN_ACCEPTED=true" in outbox.queued[0]["problem"]
    assert "nomad.agent_value_pack.v1" in outbox.queued[0]["problem"]
    assert result["stats"]["queued_agent_contact"] == 1


def test_lead_conversion_keeps_human_facing_issue_private(tmp_path):
    pipeline = LeadConversionPipeline(
        path=tmp_path / "conversions.json",
        lead_discovery=FakeLeadDiscovery(),
        service_desk=FakeServiceDesk(),
        outbox=FakeOutbox(),
    )
    lead = FakeLeadDiscovery().scout_public_leads(limit=2)["leads"][1]

    result = pipeline.run(leads=[lead], limit=1)

    conversion = result["conversions"][0]
    assert conversion["status"] == "private_draft_needs_approval"
    assert conversion["route"]["approval_gate"] == "APPROVE_LEAD_HELP=comment or APPROVE_LEAD_HELP=pr_plan"
    assert conversion["free_value"]["value_pack"]["route"]["approval_gate"] == "APPROVE_LEAD_HELP=comment or APPROVE_LEAD_HELP=pr_plan"
    assert conversion["free_value"]["agent_solution"]["guardrail"]["id"] == "draft_only_repro_plan"
    assert "APPROVE_LEAD_HELP" in conversion["customer_next_step"]["expected_reply"]


def test_lead_conversion_can_send_only_after_queueing_machine_endpoint(tmp_path):
    outbox = FakeOutbox()
    pipeline = LeadConversionPipeline(
        path=tmp_path / "conversions.json",
        lead_discovery=FakeLeadDiscovery(),
        service_desk=FakeServiceDesk(),
        outbox=outbox,
    )

    result = pipeline.run(query="quota", limit=1, send=True)

    assert result["conversions"][0]["status"] == "sent_agent_contact"
    assert outbox.sent == ["contact-test"]


def test_lead_conversion_builds_private_draft_from_explicit_lead_when_search_has_no_results(tmp_path):
    class EmptyDiscovery(FakeLeadDiscovery):
        def scout_public_leads(self, query="", limit=5):
            return {
                "mode": "lead_discovery",
                "query": query,
                "candidate_count": 0,
                "qualified_count": 0,
                "leads": [],
                "errors": [],
            }

    pipeline = LeadConversionPipeline(
        path=tmp_path / "conversions.json",
        lead_discovery=EmptyDiscovery(),
        service_desk=FakeServiceDesk(),
        outbox=FakeOutbox(),
    )

    result = pipeline.run(
        query=(
            "Lead: AutoGen GuardrailProvider "
            "URL=https://github.com/microsoft/autogen/issues/7405 "
            "Pain=rate limit, token, approval"
        ),
        limit=1,
    )

    conversion = result["conversions"][0]
    assert conversion["lead"]["url"] == "https://github.com/microsoft/autogen/issues/7405"
    assert conversion["status"] == "private_draft_needs_approval"
    assert conversion["free_value"]["value_pack"]["schema"] == "nomad.agent_value_pack.v1"
    assert conversion["free_value"]["agent_solution"]["pain_type"] == "compute_auth"


def test_value_pack_has_paid_upgrade_and_safe_reply_contract(tmp_path):
    pipeline = LeadConversionPipeline(
        path=tmp_path / "conversions.json",
        lead_discovery=FakeLeadDiscovery(),
        service_desk=FakeServiceDesk(),
        outbox=FakeOutbox(),
    )

    result = pipeline.run(query="quota", limit=1, budget_hint_native=0.03)

    value_pack = result["conversions"][0]["free_value"]["value_pack"]
    assert value_pack["pack_id"].startswith("avp-")
    assert value_pack["paid_upgrade"]["price_native"] == 0.03
    assert value_pack["reply_contract"]["accept"] == "PLAN_ACCEPTED=true"
    assert "raw secrets" in value_pack["reply_contract"]["do_not_send"]
    assert "token values" in value_pack["immediate_value"]["verifier"]
