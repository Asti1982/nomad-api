from lead_discovery import LeadDiscoveryScout


class FakeResponse:
    ok = True

    def json(self):
        return {
            "items": [
                {
                    "title": "Agent hits rate limit during inference",
                    "body": (
                        "The AI agent cannot continue after token quota and human approval failures. "
                        "We have a paid bounty and budget for urgent production help."
                    ),
                    "html_url": "https://github.com/example/agent/issues/7",
                    "repository_url": "https://api.github.com/repos/example/agent",
                    "updated_at": "2026-04-18T00:00:00Z",
                    "user": {"login": "builder"},
                }
            ]
        }


class FakeSession:
    def get(self, *args, **kwargs):
        return FakeResponse()


def test_public_lead_discovery_returns_draft_only_lead():
    scout = LeadDiscoveryScout(session=FakeSession())
    result = scout.scout_public_leads(query='"AI agent" "rate limit"', limit=1)

    assert result["mode"] == "lead_discovery"
    assert len(result["leads"]) == 1
    lead = result["leads"][0]
    assert lead["url"] == "https://github.com/example/agent/issues/7"
    assert "rate limit" in lead["pain_terms"]
    assert lead["contact_policy"] == "agent_endpoint_contact_allowed_human_outreach_requires_approval"
    assert lead["agent_contact_allowed_without_approval"] is True
    assert lead["buyer_fit"] == "strong"
    assert "bounty" in lead["buyer_intent_terms"]
    assert "post human-facing public comments" in result["outreach_policy"]["blocked_without_approval"]
    assert "send bounded requests to public machine-readable agent/API/MCP endpoints" in result["outreach_policy"]["allowed_without_approval"]
    assert result["human_unlocks"][0]["candidate_id"] == "approve-public-lead-help"


def test_help_action_draft_does_not_publish_without_approval():
    scout = LeadDiscoveryScout(session=FakeSession())
    draft = scout.draft_first_help_action(
        {
            "title": "Blocked agent",
            "url": "https://github.com/example/agent/issues/8",
            "pain": "quota and approval",
        }
    )

    assert draft["mode"] == "lead_help_draft"
    assert draft["draft_only"] is True
    assert draft["can_publish"] is False
