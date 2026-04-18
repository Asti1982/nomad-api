from nomad_cli import build_parser, build_query
from nomad_mcp import NomadMcpServer


class FakeAgent:
    def __init__(self):
        self.lead_discovery = FakeLeadDiscovery()
        self.service_desk = FakeServiceDesk()
        self.direct_agent = FakeDirectAgent()
        self.agent_campaigns = FakeCampaigns()

    def run(self, query):
        return {
            "mode": "fake",
            "query": query,
            "deal_found": False,
        }


class FakeLeadDiscovery:
    def scout_public_leads(self, query=""):
        return {
            "mode": "lead_discovery",
            "query": query,
            "leads": [],
            "deal_found": False,
        }


class FakeServiceDesk:
    def service_catalog(self):
        return {
            "mode": "agent_service_catalog",
            "deal_found": False,
            "service": "fake",
        }

    def create_task(self, **kwargs):
        return {
            "mode": "agent_service_request",
            "deal_found": False,
            "ok": True,
            "task": {"task_id": "svc-test", **kwargs},
        }

    def verify_payment(self, **kwargs):
        return {
            "mode": "agent_service_request",
            "deal_found": False,
            "ok": True,
            "task": {"task_id": kwargs.get("task_id"), "payment": kwargs},
        }

    def verify_x402_payment(self, **kwargs):
        return {
            "mode": "agent_service_request",
            "deal_found": False,
            "ok": True,
            "task": {"task_id": kwargs.get("task_id"), "payment": {"x402": kwargs}},
        }

    def work_task(self, **kwargs):
        return {
            "mode": "agent_service_request",
            "deal_found": False,
            "ok": True,
            "task": {"task_id": kwargs.get("task_id"), "work_product": {"status": "draft_ready"}},
        }


class FakeDirectAgent:
    def agent_card(self):
        return {
            "name": "LoopHelper",
            "url": "https://nomad.example/a2a/message",
            "skills": [],
        }

    def handle_direct_message(self, arguments):
        return {
            "mode": "direct_agent_message",
            "deal_found": False,
            "ok": True,
            "received": arguments,
        }

    def discover_agent_card(self, base_url):
        return {
            "mode": "agent_card_discovery",
            "deal_found": False,
            "ok": True,
            "base_url": base_url,
        }


class FakeCampaigns:
    def create_campaign(self, **kwargs):
        return {
            "mode": "agent_cold_outreach_campaign",
            "deal_found": False,
            "ok": True,
            "campaign": {"campaign_id": "campaign-test", **kwargs},
        }

    def create_campaign_from_discovery(self, **kwargs):
        return {
            "mode": "agent_cold_outreach_campaign",
            "deal_found": False,
            "ok": True,
            "campaign": {"campaign_id": "campaign-discovered", **kwargs},
            "discovery": {"targets": []},
        }


def test_cli_builds_self_audit_query():
    args = build_parser().parse_args(["--json", "--profile", "ai_first", "self"])
    assert build_query(args) == "/self for ai_first"


def test_cli_run_once_accepts_json_after_subcommand(capsys):
    from nomad_cli import run_once

    result = run_once(["self", "--json"])
    captured = capsys.readouterr()
    assert result["mode"] == "self_audit"
    assert '"mode": "self_audit"' in captured.out


def test_mcp_initialize_declares_tools_resources_and_prompts():
    server = NomadMcpServer(agent_factory=FakeAgent)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
    )
    capabilities = response["result"]["capabilities"]
    assert "tools" in capabilities
    assert "resources" in capabilities
    assert "prompts" in capabilities


def test_mcp_lists_and_calls_nomad_self_audit_tool():
    server = NomadMcpServer(agent_factory=FakeAgent)
    tools = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tool_names = {tool["name"] for tool in tools["result"]["tools"]}
    assert "nomad_self_audit" in tool_names
    assert "nomad_self_development_status" in tool_names
    assert "nomad_service_request" in tool_names
    assert "nomad_service_x402_verify" in tool_names
    assert "nomad_public_leads" in tool_names
    assert "nomad_agent_card" in tool_names
    assert "nomad_direct_message" in tool_names
    assert "nomad_cold_outreach_campaign" in tool_names

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "nomad_self_audit",
                "arguments": {"profile": "ai_first"},
            },
        }
    )
    assert response["result"]["isError"] is False
    assert response["result"]["structuredContent"]["query"] == "/self for ai_first"


def test_mcp_creates_service_task_directly():
    server = NomadMcpServer(agent_factory=FakeAgent)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "nomad_service_request",
                "arguments": {
                    "problem": "Agent needs help with human approval.",
                    "service_type": "human_in_loop",
                },
            },
        }
    )

    assert response["result"]["isError"] is False
    content = response["result"]["structuredContent"]
    assert content["mode"] == "agent_service_request"
    assert content["task"]["task_id"] == "svc-test"


def test_mcp_returns_agent_card_directly():
    server = NomadMcpServer(agent_factory=FakeAgent)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "nomad_agent_card",
                "arguments": {},
            },
        }
    )

    card = response["result"]["structuredContent"]["agent_card"]
    assert card["name"] == "LoopHelper"


def test_cli_builds_service_and_lead_queries():
    leads_args = build_parser().parse_args(["leads", "quota"])
    assert build_query(leads_args) == "/leads quota"

    service_args = build_parser().parse_args(["service-request", "fix", "login"])
    assert build_query(service_args) == "/service request fix login"

    x402_args = build_parser().parse_args(["service-x402-verify", "svc-test", "abc"])
    assert build_query(x402_args) == "/service x402-verify svc-test signature=abc"

    card_args = build_parser().parse_args(["agent-card"])
    assert build_query(card_args) == "/agent-card"

    direct_args = build_parser().parse_args(["direct", "--agent", "Bot", "stuck", "loop"])
    assert build_query(direct_args) == "/direct agent=Bot stuck loop"

    campaign_args = build_parser().parse_args(
        ["cold-outreach", "--limit", "100", "https://agent.example/.well-known/agent"]
    )
    assert build_query(campaign_args) == "/cold-outreach limit=100 https://agent.example/.well-known/agent"

    discovery_args = build_parser().parse_args(
        ["cold-outreach", "--discover", "--query", "agent-card", "--limit", "25"]
    )
    assert build_query(discovery_args) == "/cold-outreach discover limit=25 query=agent-card"


def test_mcp_stdio_tolerates_windows_bom(capsys):
    from nomad_mcp import serve_stdio

    serve_stdio(lines=['\ufeff{"jsonrpc":"2.0","id":1,"method":"ping"}\n'])
    serve_stdio(lines=['\xef\xbb\xbf{"jsonrpc":"2.0","id":2,"method":"ping"}\n'])
    captured = capsys.readouterr()
    assert '"result": {}' in captured.out
