import json
import sys
from typing import Any, Callable, Dict, Iterable, Optional

from mission import MISSION_STATEMENT, mission_text
from nomad_guardrails import guardrail_status
from self_development import SelfDevelopmentJournal
from workflow import NomadAgent


PROTOCOL_VERSION = "2025-11-25"


class NomadMcpServer:
    """Small stdio MCP server exposing Nomad as tools and resources."""

    def __init__(self, agent_factory: Callable[[], NomadAgent] = NomadAgent) -> None:
        self.agent = agent_factory()
        self.journal = SelfDevelopmentJournal()

    def handle(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        if method == "notifications/initialized":
            return None
        if method == "initialize":
            return self._response(request_id, self._initialize(params))
        if method == "ping":
            return self._response(request_id, {})
        if method == "tools/list":
            return self._response(request_id, {"tools": self._tools()})
        if method == "tools/call":
            return self._response(request_id, self._call_tool(params))
        if method == "resources/list":
            return self._response(request_id, {"resources": self._resources()})
        if method == "resources/read":
            return self._response(request_id, self._read_resource(params))
        if method == "prompts/list":
            return self._response(request_id, {"prompts": self._prompts()})
        if method == "prompts/get":
            return self._response(request_id, self._get_prompt(params))
        return self._error(request_id, -32601, f"Unknown MCP method: {method}")

    def _initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {
                "name": "nomad",
                "title": "Nomad AI Infrastructure Scout",
                "version": "0.1.0",
            },
            "instructions": (
                "Use Nomad to audit AI-agent infrastructure, generate concrete human unlock tasks, "
                "run bounded self-improvement cycles, and scout agent-customer infrastructure pain."
            ),
        }

    def _tools(self) -> list[Dict[str, Any]]:
        return [
            {
                "name": "nomad_best",
                "title": "Nomad Best Stack",
                "description": "Return Nomad's recommended AI-first infrastructure stack.",
                "inputSchema": self._schema({"profile": "Profile id, default ai_first"}),
            },
            {
                "name": "nomad_self_audit",
                "title": "Nomad Self Audit",
                "description": "Audit Nomad's current stack against the AI-first profile.",
                "inputSchema": self._schema({"profile": "Profile id, default ai_first"}),
            },
            {
                "name": "nomad_compute",
                "title": "Nomad Compute Audit",
                "description": "Probe local and hosted compute lanes available to Nomad.",
                "inputSchema": self._schema({"profile": "Profile id, default ai_first"}),
            },
            {
                "name": "nomad_addons",
                "title": "Nomad Addons",
                "description": "Scan the Nomadds drop folder in safe manifest-first mode without executing addon code.",
                "inputSchema": self._schema({}),
            },
            {
                "name": "nomad_quantum_tokens",
                "title": "Nomad Quantum Tokens",
                "description": "Generate quantum-inspired self-improvement qtokens for agent exploration and critic routing.",
                "inputSchema": self._schema(
                    {
                        "objective": "Optional self-improvement objective.",
                    },
                ),
            },
            {
                "name": "nomad_unlock",
                "title": "Nomad Unlock Task",
                "description": "Generate the best next concrete human-in-the-loop unlock task.",
                "inputSchema": self._schema(
                    {
                        "category": "Optional category such as best, compute, protocols or messaging.",
                        "profile": "Profile id, default ai_first.",
                    }
                ),
            },
            {
                "name": "nomad_cycle",
                "title": "Nomad Self-Improvement Cycle",
                "description": "Run a bounded self-improvement cycle with an optional objective.",
                "inputSchema": self._schema(
                    {
                        "objective": "Concrete cycle objective or active lead.",
                        "profile": "Profile id, default ai_first.",
                    }
                ),
            },
            {
                "name": "nomad_scout",
                "title": "Nomad Category Scout",
                "description": "Scout and rank one infrastructure category.",
                "inputSchema": self._schema(
                    {
                        "category": "Infrastructure category to scout.",
                        "profile": "Profile id, default ai_first.",
                    },
                    required=["category"],
                ),
            },
            {
                "name": "nomad_public_leads",
                "title": "Nomad Public Agent Leads",
                "description": "Find public AI-agent infrastructure pain leads without contacting anyone.",
                "inputSchema": self._schema({"query": "Optional public issue/search query."}),
            },
            {
                "name": "nomad_agent_pain_solver",
                "title": "Nomad Agent Pain Solver",
                "description": "Turn one AI-agent pain point into a reusable solution Nomad can also apply to itself.",
                "inputSchema": self._schema(
                    {
                        "problem": "Concrete agent pain point or blocker.",
                        "service_type": "Optional type such as loop_break, compute_auth, human_in_loop, memory, payment or mcp_integration.",
                    },
                    required=["problem"],
                ),
            },
            {
                "name": "nomad_mutual_aid",
                "title": "Nomad Mutual-Aid Help",
                "description": "Help another AI agent with one blocker, record the verified help signal, and let Nomad learn safely.",
                "inputSchema": self._schema(
                    {
                        "task": "Concrete blocker or help request from the other agent.",
                        "other_agent_id": "Requester agent id or name.",
                    },
                    required=["task"],
                ),
            },
            {
                "name": "nomad_mutual_aid_status",
                "title": "Nomad Mutual-Aid Status",
                "description": "Read Nomad v3.2 Mutual-Aid score, learned module count, and policy.",
                "inputSchema": self._schema({}),
            },
            {
                "name": "nomad_truth_density_ledger",
                "title": "Nomad Truth-Density Ledger",
                "description": "Read verified help outcomes with evidence, outcome, score, and reuse value.",
                "inputSchema": self._schema(
                    {
                        "pain_type": "Optional pain type filter.",
                        "limit": "Maximum number of entries.",
                    },
                ),
            },
            {
                "name": "nomad_swarm_inbox",
                "title": "Nomad Swarm Inbox",
                "description": "List inbound Swarm-to-Swarm proposals from other agents.",
                "inputSchema": self._schema(
                    {
                        "status": "Optional status filter or comma-separated statuses.",
                        "limit": "Maximum number of inbox items.",
                    },
                ),
            },
            {
                "name": "nomad_swarm_development_signals",
                "title": "Nomad Swarm Development Signals",
                "description": "List verified inbound agent help converted into Nomad product and development signals.",
                "inputSchema": self._schema(
                    {
                        "pain_type": "Optional pain type filter.",
                        "limit": "Maximum number of signals.",
                    },
                ),
            },
            {
                "name": "nomad_high_value_patterns",
                "title": "Nomad High-Value Patterns",
                "description": "List repeated verified Mutual-Aid patterns that Nomad should productize, verify, and reuse to help more agents.",
                "inputSchema": self._schema(
                    {
                        "pain_type": "Optional pain type filter.",
                        "limit": "Maximum number of patterns.",
                        "min_repeat_count": "Minimum successful occurrences before the pattern is listed.",
                    },
                ),
            },
            {
                "name": "nomad_swarm_proposal",
                "title": "Submit Swarm Proposal",
                "description": "Submit a verifiable non-code proposal from another agent into Nomad's inbox.",
                "inputSchema": self._schema(
                    {
                        "sender_id": "Requester agent id or name.",
                        "title": "Short proposal title.",
                        "proposal": "Concrete proposal text.",
                        "pain_type": "Optional pain type.",
                        "evidence": "Evidence list or text separated by commas/newlines.",
                    },
                    required=["sender_id", "title", "proposal", "evidence"],
                ),
            },
            {
                "name": "nomad_mutual_aid_packs",
                "title": "Nomad Mutual-Aid Paid Packs",
                "description": "List paid micro-packs distilled from repeated verified Mutual-Aid patterns.",
                "inputSchema": self._schema(
                    {
                        "pain_type": "Optional pain type filter.",
                        "limit": "Maximum number of packs.",
                    },
                ),
            },
            {
                "name": "nomad_reliability_doctor",
                "title": "Nomad Reliability Doctor",
                "description": "Classify an agent failure into Critic, Diagnoser/Fixer, Healer, Trace-Healer, or Reviewer loops.",
                "inputSchema": self._schema(
                    {
                        "problem": "Concrete agent failure, bad output, loop, tool error, execution failure, or self-correction gap.",
                        "service_type": "Optional type such as hallucination, bad_planning, tool_failure, execution_failure, loop_break, compute_auth, memory, payment, or repo_issue_help.",
                    },
                    required=["problem"],
                ),
            },
            {
                "name": "nomad_guardrails",
                "title": "Nomad Runtime Guardrails",
                "description": "Check a proposed Nomad action and return allow, modify, or deny before execution.",
                "inputSchema": self._schema(
                    {
                        "action": "Action name such as service.create_task, agent_contact.send, github.comment, or manual.check.",
                        "text": "Optional human-readable payload to check.",
                        "url": "Optional target URL.",
                        "approval": "Optional explicit approval scope.",
                    },
                    required=["action"],
                ),
            },
            {
                "name": "nomad_lead_conversion_pipeline",
                "title": "Nomad Lead Conversion Pipeline",
                "description": "Find public agent-pain leads, generate nomad.agent_value_pack.v1 free value, route safe outreach, and track customer conversion.",
                "inputSchema": self._schema(
                    {
                        "query": "Optional public lead search query.",
                        "limit": "Maximum number of leads to convert.",
                        "send": "Whether to send only to eligible public machine-readable agent endpoints.",
                        "budget_hint_native": "Optional native-token budget hint.",
                    },
                ),
            },
            {
                "name": "nomad_product_factory",
                "title": "Nomad Product Factory",
                "description": "Turn lead conversions into reusable nomad.product.v1 offers with SKU, service template, guardrails, and paid upgrade path.",
                "inputSchema": self._schema(
                    {
                        "query": "Optional lead query or explicit lead text to productize.",
                        "limit": "Maximum number of leads or conversions to productize.",
                    },
                ),
            },
            {
                "name": "nomad_products",
                "title": "Nomad Products",
                "description": "List stored Nomad product offers created from lead conversions.",
                "inputSchema": self._schema(
                    {
                        "status": "Optional status or comma-separated statuses.",
                        "limit": "Maximum number of products to list.",
                    },
                ),
            },
            {
                "name": "nomad_agent_engagements",
                "title": "Nomad Agent Engagements",
                "description": "List recorded agent engagements, grouped by role such as customer, collaborator, reseller, or peer_solver.",
                "inputSchema": self._schema(
                    {
                        "role": "Optional role or comma-separated roles.",
                        "pain_type": "Optional pain type to filter by.",
                        "limit": "Maximum number of engagement records to list.",
                    },
                ),
            },
            {
                "name": "nomad_agent_engagement_summary",
                "title": "Nomad Agent Engagement Summary",
                "description": "Summarize current agent-engagement roles, outcomes, and swarm candidates.",
                "inputSchema": self._schema(
                    {
                        "pain_type": "Optional pain type to filter by.",
                        "limit": "Maximum number of top swarm candidates to include.",
                    },
                ),
            },
            {
                "name": "nomad_service_catalog",
                "title": "Nomad Agent Service Catalog",
                "description": "Return Nomad's wallet-payable public service desk descriptor.",
                "inputSchema": self._schema({}),
            },
            {
                "name": "nomad_service_request",
                "title": "Create Nomad Service Task",
                "description": "Create a wallet-payable task for Nomad to help another agent.",
                "inputSchema": self._schema(
                    {
                        "problem": "Concrete infrastructure or human-in-the-loop problem.",
                        "requester_agent": "Optional requester agent name or URL.",
                        "requester_wallet": "Optional payer wallet address.",
                        "service_type": "human_in_loop, compute_auth, mcp_integration, repo_issue_help, wallet_payment or custom.",
                        "budget_native": "Optional native-token budget.",
                    },
                    required=["problem"],
                ),
            },
            {
                "name": "nomad_service_verify",
                "title": "Verify Nomad Service Payment",
                "description": "Attach a tx hash and verify wallet payment for a service task.",
                "inputSchema": self._schema(
                    {
                        "task_id": "Nomad service task id.",
                        "tx_hash": "0x transaction hash.",
                        "requester_wallet": "Optional expected payer wallet.",
                    },
                    required=["task_id", "tx_hash"],
                ),
            },
            {
                "name": "nomad_service_x402_verify",
                "title": "Verify Nomad x402 Payment",
                "description": "Verify a PAYMENT-SIGNATURE against a stored Nomad service task.",
                "inputSchema": self._schema(
                    {
                        "task_id": "Nomad service task id.",
                        "payment_signature": "x402 v2 PAYMENT-SIGNATURE header value.",
                        "requester_wallet": "Optional expected payer wallet.",
                    },
                    required=["task_id", "payment_signature"],
                ),
            },
            {
                "name": "nomad_service_work",
                "title": "Work Nomad Service Task",
                "description": "Generate a draft work product for a paid service task.",
                "inputSchema": self._schema(
                    {
                        "task_id": "Nomad service task id.",
                        "approval": "draft_only by default, or explicit approved scope.",
                    },
                    required=["task_id"],
                ),
            },
            {
                "name": "nomad_service_staking_checklist",
                "title": "Nomad Service Staking Checklist",
                "description": "Show MetaMask/operator checklist for the task treasury stake.",
                "inputSchema": self._schema(
                    {"task_id": "Nomad service task id."},
                    required=["task_id"],
                ),
            },
            {
                "name": "nomad_service_record_stake",
                "title": "Record Nomad Treasury Stake",
                "description": "Record prepared or completed MetaMask treasury staking for a task.",
                "inputSchema": self._schema(
                    {
                        "task_id": "Nomad service task id.",
                        "tx_hash": "Optional staking transaction hash.",
                        "amount_native": "Optional staked amount.",
                        "note": "Optional note.",
                    },
                    required=["task_id"],
                ),
            },
            {
                "name": "nomad_service_record_spend",
                "title": "Record Nomad Solver Spend",
                "description": "Record spend from a task's problem-solving budget.",
                "inputSchema": self._schema(
                    {
                        "task_id": "Nomad service task id.",
                        "amount_native": "Amount spent.",
                        "note": "Spend note.",
                        "tx_hash": "Optional transaction hash.",
                    },
                    required=["task_id", "amount_native"],
                ),
            },
            {
                "name": "nomad_agent_contact",
                "title": "Queue Agent Contact",
                "description": "Queue a bounded request to a public machine-readable agent/API/MCP endpoint.",
                "inputSchema": self._schema(
                    {
                        "endpoint_url": "Public machine-readable endpoint URL.",
                        "problem": "Concrete problem or offer context.",
                        "service_type": "Service type.",
                        "budget_hint_native": "Optional native-token budget hint.",
                    },
                    required=["endpoint_url", "problem"],
                ),
            },
            {
                "name": "nomad_agent_contact_send",
                "title": "Send Agent Contact",
                "description": "Send a queued bounded agent contact.",
                "inputSchema": self._schema(
                    {"contact_id": "Queued contact id."},
                    required=["contact_id"],
                ),
            },
            {
                "name": "nomad_cold_outreach_campaign",
                "title": "Cold Outreach Campaign",
                "description": "Discover, queue, or send cold outreach to up to 100 public machine-readable agent endpoints.",
                "inputSchema": self._schema(
                    {
                        "targets": "Array of endpoint URLs or target objects.",
                        "discover": "Whether to discover public agent endpoints before queuing.",
                        "query": "Optional public discovery search query.",
                        "seeds": "Optional seed base URLs or endpoint URLs.",
                        "limit": "Maximum targets, capped at 100.",
                        "send": "Whether to send immediately.",
                        "service_type": "Service type to offer.",
                        "budget_hint_native": "Optional budget hint.",
                    },
                ),
            },
            {
                "name": "nomad_agent_card",
                "title": "Nomad Agent Card",
                "description": "Return Nomad's A2A-style direct discovery AgentCard.",
                "inputSchema": self._schema({}),
            },
            {
                "name": "nomad_direct_message",
                "title": "Direct Agent Message",
                "description": "Start or continue a direct 1:1 agent rescue session with free diagnosis and x402 payment challenge.",
                "inputSchema": self._schema(
                    {
                        "message": "Agent problem or blocker.",
                        "requester_agent": "Optional source agent name.",
                        "requester_endpoint": "Optional source agent endpoint.",
                        "requester_wallet": "Optional payer wallet.",
                        "session_id": "Optional existing direct session id.",
                        "budget_native": "Optional native-token budget.",
                    },
                    required=["message"],
                ),
            },
            {
                "name": "nomad_discover_agent",
                "title": "Discover Agent Card",
                "description": "Discover an AgentCard from a base URL using standard .well-known paths.",
                "inputSchema": self._schema(
                    {"base_url": "Agent base URL."},
                    required=["base_url"],
                ),
            },
            {
                "name": "nomad_self_development_status",
                "title": "Nomad Self-Development Status",
                "description": "Read Nomad's persistent self-development journal and next autonomous objective.",
                "inputSchema": self._schema({}),
            },
        ]

    def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        direct_result = self._call_direct_tool(name=name, arguments=arguments)
        if direct_result is not None:
            return self._tool_result(direct_result)
        query = self._tool_query(name=name, arguments=arguments)
        if not query:
            return self._tool_result({"error": f"Unknown tool: {name}"}, is_error=True)
        if query == "__self_development_status__":
            result = {
                "mode": "self_development_status",
                "state": self.journal.load(),
                "text": self.journal.status_text(),
            }
        else:
            result = self.agent.run(query)
        return self._tool_result(result)

    def _call_direct_tool(self, name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if name == "nomad_public_leads":
            return self.agent.lead_discovery.scout_public_leads(
                query=str(arguments.get("query") or "").strip()
            )
        if name == "nomad_agent_pain_solver":
            return self.agent.agent_pain_solver.solve(
                problem=str(arguments.get("problem") or "").strip(),
                service_type=str(arguments.get("service_type") or "").strip(),
                source="mcp_tool",
            )
        if name == "nomad_mutual_aid":
            return self.agent.mutual_aid.help_other_agent(
                other_agent_id=str(arguments.get("other_agent_id") or arguments.get("agent") or "mcp-agent").strip(),
                task=str(arguments.get("task") or arguments.get("problem") or "").strip(),
                context={"source": "mcp_tool"},
            )
        if name == "nomad_mutual_aid_status":
            return self.agent.mutual_aid.status()
        if name == "nomad_truth_density_ledger":
            return self.agent.mutual_aid.list_truth_ledger(
                pain_type=str(arguments.get("pain_type") or "").strip(),
                limit=int(arguments.get("limit") or 25),
            )
        if name == "nomad_swarm_inbox":
            return self.agent.mutual_aid.list_swarm_inbox(
                statuses=self._status_list(arguments.get("status") or arguments.get("statuses")),
                limit=int(arguments.get("limit") or 25),
            )
        if name == "nomad_swarm_development_signals":
            return self.agent.mutual_aid.list_swarm_development_signals(
                pain_type=str(arguments.get("pain_type") or "").strip(),
                limit=int(arguments.get("limit") or 25),
            )
        if name == "nomad_high_value_patterns":
            return self.agent.mutual_aid.list_high_value_patterns(
                pain_type=str(arguments.get("pain_type") or "").strip(),
                limit=int(arguments.get("limit") or 10),
                min_repeat_count=int(arguments.get("min_repeat_count") or 2),
            )
        if name == "nomad_swarm_proposal":
            evidence = arguments.get("evidence") or []
            if isinstance(evidence, str):
                evidence = [item.strip() for item in evidence.replace("\n", ",").split(",") if item.strip()]
            return self.agent.mutual_aid.receive_swarm_proposal(
                {
                    "sender_id": str(arguments.get("sender_id") or "").strip(),
                    "title": str(arguments.get("title") or "").strip(),
                    "proposal": str(arguments.get("proposal") or "").strip(),
                    "pain_type": str(arguments.get("pain_type") or "self_improvement").strip(),
                    "evidence": evidence,
                    "payload": arguments.get("payload") if isinstance(arguments.get("payload"), dict) else {},
                    "payload_hash": str(arguments.get("payload_hash") or "").strip(),
                    "test_suite_ref": str(arguments.get("test_suite_ref") or "").strip(),
                }
            )
        if name == "nomad_mutual_aid_packs":
            return self.agent.mutual_aid.list_paid_packs(
                pain_type=str(arguments.get("pain_type") or "").strip(),
                limit=int(arguments.get("limit") or 25),
            )
        if name == "nomad_reliability_doctor":
            return self.agent.agent_reliability_doctor.diagnose(
                problem=str(arguments.get("problem") or "").strip(),
                service_type=str(arguments.get("service_type") or "").strip(),
                source="mcp_tool",
            )
        if name == "nomad_guardrails":
            return guardrail_status(
                action=str(arguments.get("action") or "manual.check").strip(),
                approval=str(arguments.get("approval") or "").strip(),
                args={
                    "text": str(arguments.get("text") or "").strip(),
                    "url": str(arguments.get("url") or "").strip(),
                },
            )
        if name == "nomad_lead_conversion_pipeline":
            return self.agent.lead_conversion.run(
                query=str(arguments.get("query") or "").strip(),
                limit=int(arguments.get("limit") or 5),
                send=bool(arguments.get("send", False)),
                budget_hint_native=self._optional_float(arguments.get("budget_hint_native")),
            )
        if name == "nomad_product_factory":
            return self.agent.product_factory.run(
                query=str(arguments.get("query") or "").strip(),
                limit=int(arguments.get("limit") or 5),
            )
        if name == "nomad_products":
            return self.agent.product_factory.list_products(
                statuses=self._status_list(arguments.get("status") or arguments.get("statuses")),
                limit=int(arguments.get("limit") or 25),
            )
        if name == "nomad_agent_engagements":
            return self.agent.agent_engagements.list_engagements(
                roles=self._status_list(arguments.get("role") or arguments.get("roles")),
                pain_type=str(arguments.get("pain_type") or "").strip(),
                limit=int(arguments.get("limit") or 25),
            )
        if name == "nomad_agent_engagement_summary":
            return self.agent.agent_engagements.summary(
                pain_type=str(arguments.get("pain_type") or "").strip(),
                limit=int(arguments.get("limit") or 5),
            )
        if name == "nomad_addons":
            return self.agent.addons.status()
        if name == "nomad_quantum_tokens":
            return self.agent.addons.run_quantum_self_improvement(
                objective=str(arguments.get("objective") or "").strip(),
                context={"source": "mcp_tool"},
            )
        if name == "nomad_service_catalog":
            return self.agent.service_desk.service_catalog()
        if name == "nomad_service_request":
            budget = self._optional_float(arguments.get("budget_native"))
            return self.agent.service_desk.create_task(
                problem=str(arguments.get("problem") or "").strip(),
                requester_agent=str(arguments.get("requester_agent") or "").strip(),
                requester_wallet=str(arguments.get("requester_wallet") or "").strip(),
                service_type=str(arguments.get("service_type") or "custom").strip(),
                budget_native=budget,
            )
        if name == "nomad_service_verify":
            return self.agent.service_desk.verify_payment(
                task_id=str(arguments.get("task_id") or "").strip(),
                tx_hash=str(arguments.get("tx_hash") or "").strip(),
                requester_wallet=str(arguments.get("requester_wallet") or "").strip(),
            )
        if name == "nomad_service_x402_verify":
            return self.agent.service_desk.verify_x402_payment(
                task_id=str(arguments.get("task_id") or "").strip(),
                payment_signature=str(arguments.get("payment_signature") or "").strip(),
                requester_wallet=str(arguments.get("requester_wallet") or "").strip(),
            )
        if name == "nomad_service_work":
            return self.agent.service_desk.work_task(
                task_id=str(arguments.get("task_id") or "").strip(),
                approval=str(arguments.get("approval") or "draft_only").strip(),
            )
        if name == "nomad_service_staking_checklist":
            return self.agent.service_desk.metamask_staking_checklist(
                task_id=str(arguments.get("task_id") or "").strip(),
            )
        if name == "nomad_service_record_stake":
            return self.agent.service_desk.record_treasury_stake(
                task_id=str(arguments.get("task_id") or "").strip(),
                tx_hash=str(arguments.get("tx_hash") or "").strip(),
                amount_native=self._optional_float(arguments.get("amount_native")),
                note=str(arguments.get("note") or "").strip(),
            )
        if name == "nomad_service_record_spend":
            return self.agent.service_desk.record_solver_spend(
                task_id=str(arguments.get("task_id") or "").strip(),
                amount_native=self._optional_float(arguments.get("amount_native")) or 0.0,
                note=str(arguments.get("note") or "").strip(),
                tx_hash=str(arguments.get("tx_hash") or "").strip(),
            )
        if name == "nomad_agent_contact":
            return self.agent.agent_contacts.queue_contact(
                endpoint_url=str(arguments.get("endpoint_url") or "").strip(),
                problem=str(arguments.get("problem") or "").strip(),
                service_type=str(arguments.get("service_type") or "human_in_loop").strip(),
                budget_hint_native=self._optional_float(arguments.get("budget_hint_native")),
            )
        if name == "nomad_agent_contact_send":
            return self.agent.agent_contacts.send_contact(
                contact_id=str(arguments.get("contact_id") or "").strip(),
            )
        if name == "nomad_cold_outreach_campaign":
            targets = arguments.get("targets") or []
            if isinstance(targets, str):
                targets = [targets]
            seeds = arguments.get("seeds") or []
            if isinstance(seeds, str):
                seeds = [seeds]
            if bool(arguments.get("discover", False)) or not targets:
                return self.agent.agent_campaigns.create_campaign_from_discovery(
                    limit=int(arguments.get("limit") or 100),
                    query=str(arguments.get("query") or "").strip(),
                    seeds=seeds or targets,
                    send=bool(arguments.get("send", False)),
                    service_type=str(arguments.get("service_type") or "human_in_loop").strip(),
                    budget_hint_native=self._optional_float(arguments.get("budget_hint_native")),
                )
            return self.agent.agent_campaigns.create_campaign(
                targets=targets,
                limit=int(arguments.get("limit") or 100),
                send=bool(arguments.get("send", False)),
                service_type=str(arguments.get("service_type") or "human_in_loop").strip(),
                budget_hint_native=self._optional_float(arguments.get("budget_hint_native")),
            )
        if name == "nomad_agent_card":
            return {
                "mode": "agent_card",
                "agent_card": self.agent.direct_agent.agent_card(),
            }
        if name == "nomad_direct_message":
            return self.agent.direct_agent.handle_direct_message(arguments)
        if name == "nomad_discover_agent":
            return self.agent.direct_agent.discover_agent_card(
                base_url=str(arguments.get("base_url") or "").strip(),
            )
        return None

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _status_list(value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [
            item.strip()
            for item in str(value).split(",")
            if item.strip()
        ]

    def _tool_query(self, name: str, arguments: Dict[str, Any]) -> str:
        profile = str(arguments.get("profile") or "ai_first").strip()
        suffix = f" for {profile}" if profile else ""
        if name == "nomad_best":
            return f"/best{suffix}"
        if name == "nomad_self_audit":
            return f"/self{suffix}"
        if name == "nomad_compute":
            return f"/compute{suffix}"
        if name == "nomad_unlock":
            category = str(arguments.get("category") or "best").strip()
            return f"/unlock {category}{suffix}"
        if name == "nomad_cycle":
            objective = str(arguments.get("objective") or "").strip()
            return f"/cycle {objective}{suffix}".strip()
        if name == "nomad_scout":
            category = str(arguments.get("category") or "").strip()
            return f"/scout {category}{suffix}".strip()
        if name == "nomad_self_development_status":
            return "__self_development_status__"
        return ""

    def _resources(self) -> list[Dict[str, str]]:
        return [
            {
                "uri": "nomad://mission",
                "name": "Nomad Mission",
                "description": "Mission statement and operating principles.",
                "mimeType": "text/plain",
            },
            {
                "uri": "nomad://self-audit",
                "name": "Nomad Self Audit",
                "description": "Current AI-first self audit as JSON.",
                "mimeType": "application/json",
            },
            {
                "uri": "nomad://compute",
                "name": "Nomad Compute Audit",
                "description": "Current compute audit as JSON.",
                "mimeType": "application/json",
            },
            {
                "uri": "nomad://service",
                "name": "Nomad Agent Service Catalog",
                "description": "Wallet-payable public service descriptor for other agents.",
                "mimeType": "application/json",
            },
            {
                "uri": "nomad://products",
                "name": "Nomad Products",
                "description": "Productized lead-conversion offers as JSON.",
                "mimeType": "application/json",
            },
            {
                "uri": "nomad://agent-engagements",
                "name": "Nomad Agent Engagements",
                "description": "Recorded agent engagements as JSON.",
                "mimeType": "application/json",
            },
            {
                "uri": "nomad://agent-engagement-summary",
                "name": "Nomad Agent Engagement Summary",
                "description": "Compact summary of current agent role distribution and swarm candidates.",
                "mimeType": "application/json",
            },
            {
                "uri": "nomad://addons",
                "name": "Nomad Addons",
                "description": "Safe manifest-first scan of Nomadds addons.",
                "mimeType": "application/json",
            },
            {
                "uri": "nomad://quantum-tokens",
                "name": "Nomad Quantum Tokens",
                "description": "Quantum-inspired self-improvement token status.",
                "mimeType": "application/json",
            },
            {
                "uri": "nomad://agent-card",
                "name": "Nomad Agent Card",
                "description": "A2A-style direct discovery AgentCard.",
                "mimeType": "application/json",
            },
            {
                "uri": "nomad://mutual-aid",
                "name": "Nomad Mutual-Aid",
                "description": "Nomad v3.2 Mutual-Aid self-evolution status and policy.",
                "mimeType": "application/json",
            },
            {
                "uri": "nomad://truth-density-ledger",
                "name": "Nomad Truth-Density Ledger",
                "description": "Verified Mutual-Aid outcomes and reuse scores.",
                "mimeType": "application/json",
            },
            {
                "uri": "nomad://swarm-inbox",
                "name": "Nomad Swarm Inbox",
                "description": "Inbound verifiable proposals from other agents.",
                "mimeType": "application/json",
            },
            {
                "uri": "nomad://mutual-aid-packs",
                "name": "Nomad Mutual-Aid Paid Packs",
                "description": "Paid micro-packs distilled from repeated verified aid patterns.",
                "mimeType": "application/json",
            },
            {
                "uri": "nomad://mutual-aid-patterns",
                "name": "Nomad High-Value Patterns",
                "description": "Repeated verified aid patterns that Nomad should turn into products, tests, and self-apply steps.",
                "mimeType": "application/json",
            },
        ]

    def _read_resource(self, params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri")
        if uri == "nomad://mission":
            text = mission_text()
            mime_type = "text/plain"
        elif uri == "nomad://self-audit":
            text = json.dumps(self.agent.run("/self"), indent=2, ensure_ascii=False)
            mime_type = "application/json"
        elif uri == "nomad://compute":
            text = json.dumps(self.agent.run("/compute"), indent=2, ensure_ascii=False)
            mime_type = "application/json"
        elif uri == "nomad://service":
            text = json.dumps(
                self.agent.service_desk.service_catalog(),
                indent=2,
                ensure_ascii=False,
            )
            mime_type = "application/json"
        elif uri == "nomad://products":
            text = json.dumps(
                self.agent.product_factory.list_products(),
                indent=2,
                ensure_ascii=False,
            )
            mime_type = "application/json"
        elif uri == "nomad://agent-engagements":
            text = json.dumps(
                self.agent.agent_engagements.list_engagements(),
                indent=2,
                ensure_ascii=False,
            )
            mime_type = "application/json"
        elif uri == "nomad://agent-engagement-summary":
            text = json.dumps(
                self.agent.agent_engagements.summary(),
                indent=2,
                ensure_ascii=False,
            )
            mime_type = "application/json"
        elif uri == "nomad://addons":
            text = json.dumps(
                self.agent.addons.status(),
                indent=2,
                ensure_ascii=False,
            )
            mime_type = "application/json"
        elif uri == "nomad://quantum-tokens":
            text = json.dumps(
                self.agent.addons.run_quantum_self_improvement(
                    objective="Report current qtoken self-improvement status.",
                    context={"source": "mcp_resource"},
                ),
                indent=2,
                ensure_ascii=False,
            )
            mime_type = "application/json"
        elif uri == "nomad://agent-card":
            text = json.dumps(
                self.agent.direct_agent.agent_card(),
                indent=2,
                ensure_ascii=False,
            )
            mime_type = "application/json"
        elif uri == "nomad://mutual-aid":
            text = json.dumps(
                self.agent.mutual_aid.status(),
                indent=2,
                ensure_ascii=False,
            )
            mime_type = "application/json"
        elif uri == "nomad://truth-density-ledger":
            text = json.dumps(
                self.agent.mutual_aid.list_truth_ledger(),
                indent=2,
                ensure_ascii=False,
            )
            mime_type = "application/json"
        elif uri == "nomad://swarm-inbox":
            text = json.dumps(
                self.agent.mutual_aid.list_swarm_inbox(),
                indent=2,
                ensure_ascii=False,
            )
            mime_type = "application/json"
        elif uri == "nomad://mutual-aid-packs":
            text = json.dumps(
                self.agent.mutual_aid.list_paid_packs(),
                indent=2,
                ensure_ascii=False,
            )
            mime_type = "application/json"
        elif uri == "nomad://mutual-aid-patterns":
            text = json.dumps(
                self.agent.mutual_aid.list_high_value_patterns(),
                indent=2,
                ensure_ascii=False,
            )
            mime_type = "application/json"
        else:
            return {"contents": []}
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": mime_type,
                    "text": text,
                }
            ]
        }

    def _prompts(self) -> list[Dict[str, Any]]:
        return [
            {
                "name": "nomad_active_lead",
                "title": "Give Nomad One Active Lead",
                "description": "Ask Nomad to work a concrete AI-agent infrastructure pain lead.",
                "arguments": [
                    {"name": "url", "description": "Lead URL", "required": True},
                    {"name": "pain", "description": "Visible infrastructure pain", "required": True},
                ],
            },
            {
                "name": "nomad_unlock",
                "title": "Ask For Concrete Unlock",
                "description": "Ask Nomad for the best next concrete human unlock task.",
                "arguments": [
                    {"name": "category", "description": "Optional unlock category", "required": False},
                ],
            },
            {
                "name": "nomad_service_request",
                "title": "Ask Nomad For Paid Agent Help",
                "description": "Create a prompt for a wallet-payable Nomad service task.",
                "arguments": [
                    {"name": "problem", "description": "Problem to solve", "required": True},
                ],
            },
        ]

    def _get_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "nomad_active_lead":
            url = arguments.get("url", "")
            pain = arguments.get("pain", "")
            text = (
                "Run Nomad on this active lead and produce the first useful help action: "
                f"Lead: {url} Pain={pain} Nomad task: validate, draft response or repro/PR plan."
            )
            return self._prompt_result("Work one concrete infrastructure-pain lead.", text)
        if name == "nomad_unlock":
            category = arguments.get("category", "best")
            return self._prompt_result(
                "Get the next concrete human unlock task.",
                f"Ask Nomad: /unlock {category}",
            )
        if name == "nomad_service_request":
            problem = arguments.get("problem", "")
            return self._prompt_result(
                "Create a wallet-payable Nomad service task.",
                (
                    "Use nomad_service_request with this problem. Nomad will return a task_id, "
                    f"wallet invoice, safety contract and next verification step: {problem}"
                ),
            )
        return self._prompt_result("Unknown prompt", f"Prompt {name} is not available.")

    @staticmethod
    def _schema(properties: Dict[str, str], required: Optional[list[str]] = None) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                name: {"type": "string", "description": description}
                for name, description in properties.items()
            },
            "required": required or [],
        }

    @staticmethod
    def _tool_result(payload: Dict[str, Any], is_error: bool = False) -> Dict[str, Any]:
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(payload, indent=2, ensure_ascii=False),
                }
            ],
            "structuredContent": payload,
            "isError": is_error,
        }

    @staticmethod
    def _prompt_result(description: str, text: str) -> Dict[str, Any]:
        return {
            "description": description,
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": text,
                    },
                }
            ],
        }

    @staticmethod
    def _response(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        }


def serve_stdio(lines: Optional[Iterable[str]] = None, stdout: Any = None) -> None:
    server = NomadMcpServer()
    output = stdout or sys.stdout
    for raw_line in lines if lines is not None else sys.stdin:
        line = raw_line.strip().lstrip("\ufeff\xef\xbb\xbf")
        if not line:
            continue
        try:
            message = json.loads(line)
            response = server.handle(message)
        except Exception as exc:  # Keep stdio server alive on malformed client input.
            response = NomadMcpServer._error(None, -32603, str(exc))
        if response is not None:
            output.write(json.dumps(response, ensure_ascii=False) + "\n")
            output.flush()


if __name__ == "__main__":
    serve_stdio()
