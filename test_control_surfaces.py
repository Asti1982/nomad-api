from nomad_cli import build_parser, build_query
from nomad_mcp import NomadMcpServer


class FakeAgent:
    def __init__(self):
        self.lead_discovery = FakeLeadDiscovery()
        self.service_desk = FakeServiceDesk()
        self.direct_agent = FakeDirectAgent()
        self.agent_campaigns = FakeCampaigns()
        self.agent_pain_solver = FakeAgentPainSolver()
        self.mutual_aid = FakeMutualAid()
        self.agent_reliability_doctor = FakeReliabilityDoctor()
        self.lead_conversion = FakeLeadConversion()
        self.product_factory = FakeProductFactory()
        self.addons = FakeAddons()

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


class FakeAgentPainSolver:
    def solve(self, **kwargs):
        return {
            "mode": "agent_pain_solution",
            "deal_found": False,
            "ok": True,
            "solution": {
                "schema": "nomad.agent_solution.v1",
                "pain_type": kwargs.get("service_type") or "loop_break",
                "title": "Retry Circuit Breaker",
            },
        }


class FakeReliabilityDoctor:
    def diagnose(self, **kwargs):
        return {
            "mode": "agent_reliability_doctor",
            "deal_found": False,
            "ok": True,
            "schema": "nomad.agent_reliability_doctor.v1",
            "pain_type": kwargs.get("service_type") or "hallucination",
            "doctor_role": {"id": "reflection_critic", "title": "Reflection/Critic Doctor"},
        }


class FakeMutualAid:
    def help_other_agent(self, **kwargs):
        return {
            "mode": "nomad_mutual_aid",
            "deal_found": False,
            "ok": True,
            "help_result": {
                "other_agent_id": kwargs.get("other_agent_id"),
                "task": kwargs.get("task"),
            },
            "mutual_aid_score": 1,
            "truth_density_total": 0.12,
            "evolution_plan": {"applied": False, "module_id": "mutual_aid_test"},
        }

    def status(self):
        return {
            "mode": "nomad_mutual_aid_status",
            "deal_found": False,
            "ok": True,
            "mutual_aid_score": 1,
            "truth_density_total": 0.12,
            "module_count": 0,
        }


class FakeLeadConversion:
    def run(self, **kwargs):
        return {
            "mode": "lead_conversion_pipeline",
            "deal_found": False,
            "ok": True,
            "query": kwargs.get("query", ""),
            "stats": {"queued_agent_contact": 1},
            "conversions": [],
        }

    def list_conversions(self, **kwargs):
        return {
            "mode": "lead_conversion_list",
            "deal_found": False,
            "ok": True,
            "statuses": kwargs.get("statuses") or [],
            "conversions": [],
        }


class FakeProductFactory:
    def run(self, **kwargs):
        return {
            "mode": "nomad_product_factory",
            "deal_found": False,
            "ok": True,
            "query": kwargs.get("query", ""),
            "products": [
                {
                    "schema": "nomad.product.v1",
                    "product_id": "prod-test",
                    "sku": "nomad.tool_guardrail_pack",
                }
            ],
        }

    def list_products(self, **kwargs):
        return {
            "mode": "nomad_product_list",
            "deal_found": False,
            "ok": True,
            "statuses": kwargs.get("statuses") or [],
            "products": [],
        }


class FakeAddons:
    def status(self):
        return {
            "mode": "nomad_addon_scan",
            "deal_found": False,
            "ok": True,
            "addons": [{"name": "Quantum Computing Integration"}],
            "stats": {"discovered": 1, "active_safe_adapter": 1},
        }

    def run_quantum_self_improvement(self, objective="", context=None):
        return {
            "mode": "nomad_quantum_tokens",
            "deal_found": False,
            "ok": True,
            "objective": objective,
            "context": context or {},
            "tokens": [{"qtoken_id": "qtok-test"}],
            "selected_strategy": {"strategy_id": "measurement_critic_gate"},
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


def test_cli_accepts_autopilot_daily_lead_target():
    args = build_parser().parse_args(["autopilot", "--daily-lead-target", "100"])
    assert args.command == "autopilot"
    assert args.daily_lead_target == 100


def test_cli_builds_convert_leads_with_public_approval():
    args = build_parser().parse_args(
        ["convert-leads", "--limit", "1", "--approval", "comment", "Lead:", "AutoGen"]
    )
    query = build_query(args)
    assert "approval=comment" in query
    assert query.endswith("Lead: AutoGen")


def test_cli_builds_reliability_doctor_query():
    args = build_parser().parse_args(["doctor", "--service-type", "hallucination", "fake", "sources"])
    assert build_query(args) == "/doctor type=hallucination fake sources"


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
    assert "nomad_agent_pain_solver" in tool_names
    assert "nomad_mutual_aid" in tool_names
    assert "nomad_mutual_aid_status" in tool_names
    assert "nomad_reliability_doctor" in tool_names
    assert "nomad_lead_conversion_pipeline" in tool_names
    assert "nomad_product_factory" in tool_names
    assert "nomad_products" in tool_names
    assert "nomad_addons" in tool_names
    assert "nomad_quantum_tokens" in tool_names
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


def test_mcp_solves_agent_pain_directly():
    server = NomadMcpServer(agent_factory=FakeAgent)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 44,
            "method": "tools/call",
            "params": {
                "name": "nomad_agent_pain_solver",
                "arguments": {
                    "problem": "Agent is stuck in retry loop.",
                    "service_type": "loop_break",
                },
            },
        }
    )

    content = response["result"]["structuredContent"]
    assert content["mode"] == "agent_pain_solution"
    assert content["solution"]["pain_type"] == "loop_break"


def test_mcp_runs_mutual_aid_directly():
    server = NomadMcpServer(agent_factory=FakeAgent)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 444,
            "method": "tools/call",
            "params": {
                "name": "nomad_mutual_aid",
                "arguments": {
                    "other_agent_id": "QuotaBot",
                    "task": "Provider auth fails with ERROR=429.",
                },
            },
        }
    )

    content = response["result"]["structuredContent"]
    assert content["mode"] == "nomad_mutual_aid"
    assert content["help_result"]["other_agent_id"] == "QuotaBot"


def test_mcp_runs_reliability_doctor_directly():
    server = NomadMcpServer(agent_factory=FakeAgent)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 445,
            "method": "tools/call",
            "params": {
                "name": "nomad_reliability_doctor",
                "arguments": {
                    "problem": "Agent hallucinated unsupported claims.",
                    "service_type": "hallucination",
                },
            },
        }
    )

    content = response["result"]["structuredContent"]
    assert content["schema"] == "nomad.agent_reliability_doctor.v1"
    assert content["doctor_role"]["id"] == "reflection_critic"


def test_mcp_runs_lead_conversion_pipeline():
    server = NomadMcpServer(agent_factory=FakeAgent)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 45,
            "method": "tools/call",
            "params": {
                "name": "nomad_lead_conversion_pipeline",
                "arguments": {
                    "query": "quota",
                    "limit": "2",
                },
            },
        }
    )

    content = response["result"]["structuredContent"]
    assert content["mode"] == "lead_conversion_pipeline"
    assert content["query"] == "quota"


def test_mcp_runs_product_factory():
    server = NomadMcpServer(agent_factory=FakeAgent)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 46,
            "method": "tools/call",
            "params": {
                "name": "nomad_product_factory",
                "arguments": {
                    "query": "guardrail provider",
                    "limit": "1",
                },
            },
        }
    )

    content = response["result"]["structuredContent"]
    assert content["mode"] == "nomad_product_factory"
    assert content["query"] == "guardrail provider"
    assert content["products"][0]["schema"] == "nomad.product.v1"


def test_mcp_runs_addons_and_quantum_tokens():
    server = NomadMcpServer(agent_factory=FakeAgent)
    addons = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 47,
            "method": "tools/call",
            "params": {
                "name": "nomad_addons",
                "arguments": {},
            },
        }
    )
    quantum = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 48,
            "method": "tools/call",
            "params": {
                "name": "nomad_quantum_tokens",
                "arguments": {"objective": "improve agent routing"},
            },
        }
    )

    assert addons["result"]["structuredContent"]["mode"] == "nomad_addon_scan"
    assert quantum["result"]["structuredContent"]["mode"] == "nomad_quantum_tokens"
    assert quantum["result"]["structuredContent"]["objective"] == "improve agent routing"


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

    solve_pain_args = build_parser().parse_args(["solve-pain", "--service-type", "loop_break", "stuck", "loop"])
    assert build_query(solve_pain_args) == "/solve-pain type=loop_break stuck loop"

    doctor_args = build_parser().parse_args(["doctor", "--service-type", "tool_failure", "schema", "mismatch"])
    assert build_query(doctor_args) == "/doctor type=tool_failure schema mismatch"

    convert_args = build_parser().parse_args(["convert-leads", "--limit", "3", "quota"])
    assert build_query(convert_args) == "/convert-leads send=false limit=3 quota"

    conversions_args = build_parser().parse_args(["lead-conversions", "--status", "queued_agent_contact"])
    assert build_query(conversions_args) == "/lead-conversions status=queued_agent_contact limit=25"

    productize_args = build_parser().parse_args(["productize", "--limit", "2", "guardrail", "provider"])
    assert build_query(productize_args) == "/productize limit=2 guardrail provider"

    products_args = build_parser().parse_args(["products", "--status", "offer_ready"])
    assert build_query(products_args) == "/products status=offer_ready limit=25"

    addons_args = build_parser().parse_args(["addons"])
    assert build_query(addons_args) == "/addons"

    quantum_args = build_parser().parse_args(["quantum", "reduce", "loops"])
    assert build_query(quantum_args) == "/quantum reduce loops"

    mutual_status_args = build_parser().parse_args(["mutual-aid-status"])
    assert build_query(mutual_status_args) == "/mutual-aid status"

    mutual_aid_args = build_parser().parse_args(["mutual-aid", "--agent", "Bot", "fix", "quota"])
    assert build_query(mutual_aid_args) == "/mutual-aid agent=Bot fix quota"

    codebuddy_scout_args = build_parser().parse_args(["scout", "codebuddy"])
    assert build_query(codebuddy_scout_args) == "/scout codebuddy for ai_first"

    codebuddy_review_args = build_parser().parse_args(
        ["codebuddy-review", "--base", "main", "--head", "feature", "--approval", "--path", "nomad_codebuddy.py", "review", "diff"]
    )
    assert build_query(codebuddy_review_args) == "/codebuddy-review base=main head=feature approval=share_diff path=nomad_codebuddy.py review diff"

    render_args = build_parser().parse_args(["render"])
    assert build_query(render_args) == "/render"

    collaboration_args = build_parser().parse_args(["collaboration"])
    assert build_query(collaboration_args) == "/collaboration"

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

    contact_poll_args = build_parser().parse_args(["agent-contact-poll", "contact-1"])
    assert build_query(contact_poll_args) == "/agent-contact poll contact-1"

    discovery_args = build_parser().parse_args(
        ["cold-outreach", "--discover", "--query", "agent-card", "--limit", "25"]
    )
    assert build_query(discovery_args) == "/cold-outreach discover limit=25 query=agent-card"

    autopilot_args = build_parser().parse_args(
        ["autopilot", "--cycles", "1", "--interval", "60", "--outreach-limit", "5"]
    )
    assert autopilot_args.command == "autopilot"
    assert autopilot_args.cycles == 1
    assert autopilot_args.interval == 60
    assert autopilot_args.outreach_limit == 5

    codex_task_args = build_parser().parse_args(["codex-task"])
    assert codex_task_args.command == "codex-task"


def test_mcp_stdio_tolerates_windows_bom(capsys):
    from nomad_mcp import serve_stdio

    serve_stdio(lines=['\ufeff{"jsonrpc":"2.0","id":1,"method":"ping"}\n'])
    serve_stdio(lines=['\xef\xbb\xbf{"jsonrpc":"2.0","id":2,"method":"ping"}\n'])
    captured = capsys.readouterr()
    assert '"result": {}' in captured.out
