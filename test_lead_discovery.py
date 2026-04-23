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


class FakeMixedResponse:
    ok = True

    def json(self):
        return {
            "items": [
                {
                    "title": "Agent hits quota in production",
                    "body": (
                        "Our AI agent is blocked by auth token rotation and compute quota. "
                        "We have budget for urgent help."
                    ),
                    "html_url": "https://github.com/microsoft/autogen/issues/77",
                    "repository_url": "https://api.github.com/repos/microsoft/autogen",
                    "updated_at": "2026-04-18T00:00:00Z",
                    "user": {"login": "builder"},
                },
                {
                    "title": "Polish the dashboard nav",
                    "body": "Urgent issue for our app layout, but nothing agent or compute related.",
                    "html_url": "https://github.com/example/app/issues/8",
                    "repository_url": "https://api.github.com/repos/example/app",
                    "updated_at": "2026-04-18T00:00:00Z",
                    "user": {"login": "designer"},
                },
            ]
        }


class FakeMixedSession:
    def get(self, *args, **kwargs):
        return FakeMixedResponse()


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
    assert lead["public_issue_excerpt"]
    assert any(item["term"] == "rate limit" for item in lead["pain_evidence"])
    assert lead["addressable_now"] is True
    assert lead["monetizable_now"] is True
    assert lead["addressable_label"] == "Compute/auth unblock"
    assert lead["quote_summary"].startswith("diagnosis ")
    assert lead["delivery_target"]
    assert lead["product_package"] == "Nomad Compute Unlock Pack"
    assert "fallback" in lead["solution_pattern"]
    assert "post human-facing public comments" in result["outreach_policy"]["blocked_without_approval"]
    assert "send bounded requests to public machine-readable agent/API/MCP endpoints" in result["outreach_policy"]["allowed_without_approval"]
    assert result["human_unlocks"][0]["candidate_id"] == "approve-public-lead-help"
    assert result["addressable_count"] == 1
    assert result["monetizable_count"] == 1


def test_help_action_draft_does_not_publish_without_approval():
    scout = LeadDiscoveryScout(session=FakeSession())
    draft = scout.draft_first_help_action(
        {
            "title": "Blocked agent",
            "url": "https://github.com/example/agent/issues/8",
            "pain": "quota and approval",
            "pain_terms": ["quota", "token"],
            "recommended_service_type": "compute_auth",
        }
    )

    assert draft["mode"] == "lead_help_draft"
    assert draft["draft_only"] is True
    assert draft["can_publish"] is False
    assert draft["service_type"] == "compute_auth"
    assert draft["pain_validation"]["status"] == "validated_from_public_lead"
    assert draft["first_useful_help_action"]
    assert "Posting gate:" in draft["private_response_draft"]
    assert "Do not post" in draft["posting_gate"]
    assert any("credential" in item.lower() for item in draft["diagnosis_checks"])
    assert any("fallback" in item.lower() for item in draft["deliverables"])
    assert draft["comment_outline"][0].startswith("Problem framing:")
    assert draft["quote_summary"].startswith("diagnosis ")
    assert draft["delivery_target"]
    assert draft["memory_upgrade"]
    assert draft["product_package"] == "Nomad Compute Unlock Pack"
    assert draft["productized_artifacts"]
    assert "Starter quote:" in draft["service_offer"]


def test_help_action_draft_handles_mixed_compute_mcp_guardrail_lead():
    scout = LeadDiscoveryScout(session=FakeSession())
    draft = scout.draft_first_help_action(
        {
            "title": "Proposal: GuardrailProvider protocol for tool call interception",
            "url": "https://github.com/microsoft/autogen/issues/7405",
            "pain": "rate limit, token, approval, mcp",
            "pain_terms": ["rate limit", "token", "approval", "mcp"],
            "public_issue_excerpt": (
                "Tool call interception needs to handle MCP approval, token failures, "
                "and rate limit fallback behavior for agents."
            ),
            "recommended_service_type": "compute_auth",
            "first_help_action": "diagnosis + quota/auth isolation + fallback plan",
        }
    )

    assert draft["draft_only"] is True
    assert draft["pain_validation"]["confidence"] == "high"
    assert any(item["term"] == "mcp" for item in draft["pain_validation"]["signals"])
    assert any("MCP/tool-call" in item for item in draft["pain_validation"]["missing_checks"])
    assert "tool-call guardrail" in draft["first_useful_help_action"]
    assert "human-gated calls" in draft["first_useful_help_action"]
    assert "MCP/tool contract" in draft["private_response_draft"]
    assert "explicit human approval" in draft["private_response_draft"]


def test_public_lead_discovery_uses_focus_catalog_from_file(tmp_path, monkeypatch):
    catalog = tmp_path / "lead-sources.json"
    catalog.write_text(
        (
            "{\n"
            '  "focus_profiles": {\n'
            '    "compute_auth": {\n'
            '      "service_type": "compute_auth",\n'
            '      "queries": ["\\"AI agent\\" quota is:issue is:open"],\n'
            '      "public_surfaces": [\n'
            '        {"name": "Quota search", "url": "https://github.com/search?q=quota&type=issues"}\n'
            "      ]\n"
            "    }\n"
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NOMAD_LEAD_SOURCES_PATH", str(catalog))
    monkeypatch.setenv("NOMAD_LEAD_FOCUS", "compute_auth")

    scout = LeadDiscoveryScout(session=FakeSession())
    result = scout.scout_public_leads(limit=1)

    assert result["focus"] == "compute_auth"
    assert result["search_queries"] == ['"AI agent" quota is:issue is:open']
    assert result["source_plan"]["service_type"] == "compute_auth"
    assert result["source_plan"]["public_surfaces"][0]["url"] == "https://github.com/search?q=quota&type=issues"


def test_public_lead_discovery_filters_out_unqualified_noise(monkeypatch):
    monkeypatch.setenv("NOMAD_LEAD_FOCUS", "compute_auth")

    scout = LeadDiscoveryScout(session=FakeMixedSession())
    result = scout.scout_public_leads(query='"AI agent" quota token is:issue is:open', limit=3)

    assert result["candidate_count"] == 2
    assert result["qualified_count"] == 1
    assert len(result["leads"]) == 1
    lead = result["leads"][0]
    assert lead["repo_url"] == "https://github.com/microsoft/autogen"
    assert lead["seed_match"] is True
    assert lead["qualified"] is True
    assert lead["recommended_service_type"] == "compute_auth"


def test_default_queries_prioritize_seed_queries_from_catalog(tmp_path, monkeypatch):
    catalog = tmp_path / "lead-sources.json"
    catalog.write_text(
        (
            "{\n"
            '  "focus_profiles": {\n'
            '    "compute_auth": {\n'
            '      "service_type": "compute_auth",\n'
            '      "seed_queries": ["repo:microsoft/autogen \\"rate limit\\" is:issue is:open"],\n'
            '      "queries": ["\\"AI agent\\" quota is:issue is:open"]\n'
            "    }\n"
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NOMAD_LEAD_SOURCES_PATH", str(catalog))
    monkeypatch.setenv("NOMAD_LEAD_FOCUS", "compute_auth")

    scout = LeadDiscoveryScout(session=FakeSession())

    assert scout.default_queries() == [
        'repo:microsoft/autogen "rate limit" is:issue is:open',
        '"AI agent" quota is:issue is:open',
    ]
