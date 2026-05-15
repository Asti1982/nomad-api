"""Sales department swarm surface for Nomad.

The point of this module is intentionally anti-human in shape: sales is not a
chatty team, a funnel brainstorm, or majority-voted copy. It is a set of
isolated proof-bearing cells. Each cell converts an observed blocker into a
small buyable packet, routes only through owned/contextual surfaces, and lets
verified receipts move weight.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Dict


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _first_package(packages: list[dict[str, Any]], package_id: str) -> dict[str, Any]:
    return next((item for item in packages if str(item.get("package_id") or "") == package_id), {})


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


SCIENCE_SOURCES: list[dict[str, str]] = [
    {
        "id": "scaling_agent_systems_2026",
        "title": "Towards a Science of Scaling Agent Systems",
        "url": "https://arxiv.org/abs/2512.08296",
        "nomad_reading": (
            "route by task topology; avoid multi-agent coordination on sequential/tool-heavy work; "
            "centralize verification and use parallel cells only where the work decomposes cleanly"
        ),
    },
    {
        "id": "silo_bench_2026",
        "title": "Silo-Bench: A Scalable Environment for Evaluating Distributed Coordination in Multi-Agent LLM Systems",
        "url": "https://arxiv.org/abs/2603.01045",
        "nomad_reading": (
            "distributed agents can exchange enough information and still fail at integration; "
            "keep seller cells siloed until a typed proof digest is ready"
        ),
    },
    {
        "id": "controlled_agent_debate_2025",
        "title": "Can LLM Agents Really Debate? A Controlled Study of Multi-Agent Debate in Logical Reasoning",
        "url": "https://arxiv.org/abs/2511.07784",
        "nomad_reading": (
            "diversity and reasoning strength matter more than visible confidence or debate order; "
            "majority pressure can suppress independent correction"
        ),
    },
    {
        "id": "self_consistency_cost_2026",
        "title": "Self-Consistency Is Losing Its Edge: Diminishing Returns and Rising Costs in Modern LLMs",
        "url": "https://arxiv.org/abs/2511.00751",
        "nomad_reading": (
            "do not spend samples where a strong single pass is already reliable; reserve multi-path work "
            "for uncertain, high-receipt-proximity cases"
        ),
    },
    {
        "id": "se_agent_2025",
        "title": "SE-Agent: Self-Evolution Trajectory Optimization in Multi-Step Reasoning with LLM-Based Agents",
        "url": "https://arxiv.org/abs/2508.02085",
        "nomad_reading": (
            "recombine and refine successful trajectories instead of asking more agents to agree; "
            "promote only trajectory fragments with verifier value"
        ),
    },
    {
        "id": "apwa_2026",
        "title": "APWA: A Distributed Architecture for Parallelizable Agentic Workflows",
        "url": "https://arxiv.org/abs/2605.15132",
        "nomad_reading": (
            "parallelize non-interfering subproblems with independent resources; avoid cross-chat "
            "communication unless integration proof is explicit"
        ),
    },
]


DEFAULT_FIRST_SALES_LEADS: list[dict[str, Any]] = [
    {
        "source": "github_public_pr",
        "title": "fix(auto-fix): preserve workflow intent during persona-driven repair",
        "url": "https://github.com/AgentWorkforce/ricky/pull/109",
        "repo_url": "https://github.com/AgentWorkforce/ricky",
        "state": "merged",
        "updated_at": "2026-05-15T14:41:09Z",
        "detected_problem": (
            "persona-driven auto-fix could replace a real PR-shipping workflow with a green "
            "no-op placeholder; the merged fix adds intent-regression guards"
        ),
        "buyer_signal": "public post-merge hardening need around workflow intent preservation",
        "recommended_service_type": "repo_issue_help",
        "product_package": "repo_diagnostic_patch_starter",
        "first_offer": "workflow-intent hardening packet with blame-surface matrix and two disproof probes",
        "cashflow_stage": "draft_only",
    },
    {
        "source": "github_public_issue",
        "title": "session_resume_post_compact: default output unreadable; tail_lines should scale with model context",
        "url": "https://github.com/rmdevpro/agentic-workbench/issues/252",
        "repo_url": "https://github.com/rmdevpro/agentic-workbench",
        "state": "open",
        "updated_at": "2026-05-15T15:01:33Z",
        "detected_problem": (
            "MCP resume output can exceed the reader context by returning roughly 54k tokens of raw JSONL "
            "when the useful instruction block is only a few hundred characters"
        ),
        "buyer_signal": "open issue with root cause, expected behavior, and suggested cap/summary fix",
        "recommended_service_type": "mcp_production",
        "product_package": "Nomad Tool Turn Parity Pack",
        "first_offer": "context-window output budget packet with max_chars cap, summary projection, and safe file handoff",
        "cashflow_stage": "draft_only",
    },
    {
        "source": "github_public_pr",
        "title": "feat(cli): splash banner, agent grid, provider picker, smart defaults",
        "url": "https://github.com/rohitg00/agentmemory/pull/403",
        "repo_url": "https://github.com/rohitg00/agentmemory",
        "state": "open",
        "updated_at": "2026-05-15T15:01:43Z",
        "detected_problem": (
            "agent onboarding PR touches CLI startup, provider choice, preferences, and MCP-adjacent setup "
            "while tests mention pre-existing failures that can mask integration drift"
        ),
        "buyer_signal": "open AI-agent memory PR with first-run workflow and provider-selection surface",
        "recommended_service_type": "mcp_production",
        "product_package": "Nomad MCP Contract Pack",
        "first_offer": "tool/resource contract check plus first-run provider/env verifier matrix",
        "cashflow_stage": "draft_only",
    },
]


def _lead_candidates(lead_discovery: Dict[str, Any] | None) -> list[dict[str, Any]]:
    discovery = _dict(lead_discovery)
    for key in ("qualified_leads", "leads", "ranked_leads", "candidates", "items"):
        candidates = _items(discovery.get(key))
        if candidates:
            return candidates
    return list(DEFAULT_FIRST_SALES_LEADS)


def _lead_url(lead: dict[str, Any]) -> str:
    return _first_nonempty(lead.get("url"), lead.get("html_url"), lead.get("issue_url"), lead.get("pr_url"))


def _lead_title(lead: dict[str, Any]) -> str:
    return _first_nonempty(lead.get("title"), lead.get("name"), lead.get("summary"), "Untitled lead")


def _lead_repo_url(lead: dict[str, Any]) -> str:
    return _first_nonempty(
        lead.get("repo_url"),
        lead.get("repository_url"),
        lead.get("repo"),
        lead.get("repository"),
    )


def _lead_problem(lead: dict[str, Any]) -> str:
    return _first_nonempty(
        lead.get("detected_problem"),
        lead.get("problem"),
        lead.get("excerpt"),
        lead.get("body_excerpt"),
        lead.get("first_offer"),
        "A public repo signal suggests a bounded diagnostic packet may be useful.",
    )


def _lead_package(lead: dict[str, Any]) -> str:
    package = str(lead.get("package_id") or lead.get("product_package") or "").strip()
    known_packages = {
        "repo_diagnostic_patch_starter",
        "endpoint_health_patch",
        "agent_loop_break_patch",
        "settlement_repair_packet",
    }
    if package in known_packages:
        return package
    signal = " ".join(
        [
            package,
            str(lead.get("recommended_service_type") or ""),
            str(lead.get("service_type") or ""),
            _lead_problem(lead),
        ]
    ).lower()
    if any(term in signal for term in ("loop", "retry", "storm")):
        return "agent_loop_break_patch"
    if any(term in signal for term in ("settlement", "payment", "payout", "receipt")):
        return "settlement_repair_packet"
    if any(term in signal for term in ("endpoint", "404", "500", "health")):
        return "endpoint_health_patch"
    return "repo_diagnostic_patch_starter"


def _lead_service_type(lead: dict[str, Any]) -> str:
    service = str(lead.get("recommended_service_type") or lead.get("service_type") or "").strip().lower()
    if service in {
        "repo_issue_help",
        "attribution_clarity",
        "mcp",
        "ci",
        "render",
        "github_actions",
        "workflow",
        "build",
    }:
        return "repo_issue_help"
    if service in {"loop_break", "agent_loop"}:
        return "loop_break"
    if service in {"payment", "settlement"}:
        return "payment"
    if service in {"endpoint", "compute_auth"}:
        return "compute_auth"
    return "repo_issue_help"


def _draft_public_help_note(lead: dict[str, Any], *, entry_url: str) -> str:
    title = _lead_title(lead)
    problem = _lead_problem(lead)
    signal = f"{title} {problem} {lead.get('first_offer') or ''}".lower()
    if any(term in signal for term in ("resume", "tail_lines", "jsonl", "context", "tokens", "max_chars")):
        return (
            "Draft only, not posted. I read this as a context-budget contract problem: the tool "
            "knows the useful resume instruction is tiny, but returns a raw transport blob large "
            "enough to break the next reader. A compact follow-up would be: (1) add a max_chars "
            "or model-context budget before serialization, (2) project JSONL into a summary plus "
            "file_ref instead of inline records, and (3) add one regression fixture where the raw "
            f"tail exceeds the Read limit while the instruction block remains recoverable. Context: {title}. "
            f"Signal: {problem} Optional paid diagnostic entry: {entry_url}"
        )
    if any(term in signal for term in ("onboarding", "provider", "preferences", "first-run", "first run", "agentmemory")):
        return (
            "Draft only, not posted. I read this as a first-run contract and MCP-adjacent integration "
            "surface, not just nicer CLI output. A small follow-up would be: (1) freeze the provider/env "
            "handoff schema, (2) add a no-key and corrupt-preferences verifier, and (3) separate "
            "pre-existing test failures from onboarding regressions so a green UX path cannot hide "
            f"agent setup drift. Context: {title}. Signal: {problem} Optional paid diagnostic entry: {entry_url}"
        )
    return (
        "Draft only, not posted. I read this as a workflow-intent preservation problem, "
        "not just a generation bug. A small useful follow-up would be: (1) list the "
        "intent anchors the workflow is never allowed to drop, (2) add two disproof "
        "fixtures that try to collapse the workflow into a green placeholder, and "
        "(3) keep a post-repair verifier that fails closed when PR-shipping primitives "
        f"disappear. Context: {title}. Signal: {problem} Optional paid diagnostic entry: {entry_url}"
    )


def build_first_sales_anbahnung_surface(
    *,
    base_url: str = "",
    sales_surface: Dict[str, Any] | None = None,
    buyer_funded_work: Dict[str, Any] | None = None,
    lead_discovery: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Compile the first real sales approach without posting or booking revenue."""
    root = (base_url or "").strip().rstrip("/")
    sales = _dict(sales_surface)
    buyer = _dict(buyer_funded_work)
    packages = _items(buyer.get("buyer_funded_packages"))
    cells = _items(sales.get("sales_cells"))
    leads = _lead_candidates(lead_discovery)
    packets: list[dict[str, Any]] = []

    for index, lead in enumerate(leads[:5], start=1):
        lead = _dict(lead)
        title = _lead_title(lead)
        url = _lead_url(lead)
        repo_url = _lead_repo_url(lead)
        package_id = _lead_package(lead)
        service_type = _lead_service_type(lead)
        package = _first_package(packages, package_id)
        cell_id = "repo_rescue_cell"
        if "loop" in package_id:
            cell_id = "agent_loop_break_cell"
        elif "settlement" in package_id:
            cell_id = "settlement_repair_cell"
        cell = next((item for item in cells if item.get("cell_id") == cell_id), {})
        entry_path = f"/service/e2e?service_type={service_type}"
        entry_url = _u(root, entry_path)
        buyer_intent = {
            "lead_url": url,
            "repo_url": repo_url,
            "title": title,
            "package_id": package_id,
            "service_type": service_type,
            "cashflow_stage": lead.get("cashflow_stage") or "draft_only",
        }
        buyer_intent_digest = f"buyer-intent-{_digest(buyer_intent, 18)}"
        proof_seed = {
            "lead": buyer_intent,
            "problem": _lead_problem(lead),
            "offer": lead.get("first_offer") or package.get("title") or package_id,
            "cell": cell_id,
        }
        proof_digest = f"first-sales-proof-{_digest(proof_seed, 18)}"
        gate_payload = {
            "cell_id": cell_id,
            "stage": "send_request",
            "buyer_intent_digest": buyer_intent_digest,
            "proof_digest": proof_digest,
            "human_approved": False,
            "send": True,
        }
        packets.append(
            {
                "rank": index,
                "lead_id": f"first-sales-lead-{_digest(buyer_intent, 16)}",
                "lead_url": url,
                "repo_url": repo_url,
                "title": title,
                "state": str(lead.get("state") or lead.get("status") or "").strip() or "unknown",
                "updated_at": str(lead.get("updated_at") or lead.get("updatedAt") or "").strip(),
                "cell_id": cell_id,
                "cell_topology": cell.get("topology") or "single_diagnostic_then_central_verifier",
                "package_id": package_id,
                "package_title": package.get("title") or lead.get("first_offer") or "Repo diagnostic patch starter",
                "service_type": service_type,
                "entry_url": entry_url,
                "create_task_hint": {
                    "method": "POST",
                    "url": _u(root, "/service/e2e"),
                    "body": {
                        "service_type": service_type,
                        "package_id": package_id,
                        "problem": f"{title}: {_lead_problem(lead)}",
                        "budget": "0.01",
                        "create": True,
                    },
                },
                "buyer_intent_digest": buyer_intent_digest,
                "proof_digest": proof_digest,
                "public_help_draft": _draft_public_help_note(lead, entry_url=entry_url),
                "private_offer_packet": {
                    "positioning": "post-merge hardening and verifier packet, not a cold pitch",
                    "deliverables": [
                        "blame-surface matrix over prompt contract, repair parser, verifier, and CI path",
                        "two disproof branches that try to collapse a real workflow into a placeholder",
                        "smallest patch path or no-patch verdict with verifier checklist",
                    ],
                    "non_goals": [
                        "no secret capture",
                        "no public comment without explicit approval",
                        "no revenue claim before positive payment receipt",
                    ],
                },
                "gate_payload": gate_payload,
                "public_send_allowed": False,
                "sales_cycle_stage": "draft_only_until_human_or_buyer_approval",
            }
        )

    active = packets[0] if packets else {}
    return {
        "ok": True,
        "schema": "nomad.first_sales_anbahnung.v1",
        "generated_at": _now(),
        "public_base_url": root,
        "surface_digest": f"nomad-first-sales-{_digest({'packets': packets})}",
        "read_url": _u(root, "/swarm/first-sales"),
        "well_known_url": _u(root, "/.well-known/nomad-first-sales.json"),
        "source_sales_surface": sales.get("well_known_url") or _u(root, "/.well-known/nomad-sales-department.json"),
        "summary": {
            "lead_packet_count": len(packets),
            "draft_ready_count": len([item for item in packets if item.get("public_help_draft")]),
            "public_send_allowed_count": 0,
            "public_send_approval_required_count": len(packets),
            "open_lead_count": len([item for item in packets if str(item.get("state") or "").lower() == "open"]),
            "merged_lead_count": len([item for item in packets if str(item.get("state") or "").lower() == "merged"]),
            "revenue_recorded_usd": 0.0,
            "active_cell": active.get("cell_id") or "",
            "active_package": active.get("package_id") or "",
        },
        "active_lead_packet": active,
        "lead_packets": packets,
        "first_sales_sequence": [
            "read public signal and classify cashflow-proximate pain",
            "compile one proof digest and one buyer-intent digest",
            "prepare value-first public draft, but keep it draft-only",
            "route buyer to /service/e2e when requested",
            "record revenue only after positive receipt",
        ],
        "public_action_gate": {
            "blocked_by_default": True,
            "requires": [
                "proof_digest",
                "buyer_intent_digest",
                "human_or_buyer_approval",
            ],
            "gate_endpoint": _u(root, "/swarm/sales-department/events"),
            "sample_payload": active.get("gate_payload") or {},
        },
        "sales_sprint": {
            "objective": "convert one current AI-agent infrastructure pain signal into a paid repo diagnostic task",
            "cashflow_rule": "only payment receipt or verified external payout counts as revenue",
            "today_next_actions": [
                "keep all three lead packets live on owned surfaces",
                "ask for one target-specific approval before any human-facing GitHub comment",
                "when a buyer replies or requests help, create the payable /service/e2e task with the packet body",
                "after payment, deliver the smallest verifier-backed diagnostic and then record receipt",
            ],
            "approval_phrase": "APPROVE_PUBLIC_SALES=lead_id",
            "approval_scope": "one value-first public reply for the named lead_id only; no DMs, no repeated comments, no private access",
        },
        "guards": {
            "no_cold_spam": True,
            "no_public_send_without_explicit_approval": True,
            "no_revenue_without_positive_receipt": True,
            "no_secret_capture": True,
            "owned_surface_first": True,
        },
        "machine_instruction": [
            "treat merged but fragile AI-agent infra PRs as post-merge hardening leads",
            "offer diagnostic proof before asking for trust",
            "prefer one bounded paid package over broad consulting language",
            "do not post the draft until the gate admits it",
        ],
    }


def build_sales_department_swarm_surface(
    *,
    base_url: str = "",
    buyer_funded_work: Dict[str, Any] | None = None,
    value_cycles: Dict[str, Any] | None = None,
    ad_cycles: Dict[str, Any] | None = None,
    receipt_predictor: Dict[str, Any] | None = None,
    revenue_science: Dict[str, Any] | None = None,
    effective_channels: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Compile Nomad's proof-first sales department as machine-readable cells."""
    root = (base_url or "").strip().rstrip("/")
    buyer = _dict(buyer_funded_work)
    packages = _items(buyer.get("buyer_funded_packages"))
    value = _dict(value_cycles)
    ads = _dict(ad_cycles)
    predictor = _dict(receipt_predictor)
    science = _dict(revenue_science)
    quota = _dict(effective_channels)
    receipt_law = _dict(buyer.get("receipt_law"))
    recognized_usd = _num(receipt_law.get("recognized_revenue_usd_total"), 0.0)

    repo_pack = _first_package(packages, "repo_diagnostic_patch_starter")
    endpoint_pack = _first_package(packages, "endpoint_health_patch")
    loop_pack = _first_package(packages, "agent_loop_break_patch")
    settlement_pack = _first_package(packages, "settlement_repair_packet")
    service_entry = _u(root, "/service/e2e?service_type=repo_issue_help")

    sales_cells = [
        {
            "cell_id": "repo_rescue_cell",
            "topology": "single_diagnostic_then_central_verifier",
            "packet": repo_pack.get("package_id") or "repo_diagnostic_patch_starter",
            "buyer_trigger": "public repo, CI, Render, or endpoint blocker with a concrete log",
            "entry_url": service_entry,
            "owned_surface": _u(root, "/nomad.html#buyable-work"),
            "anti_human_move": "do not brainstorm prospects; wait for a failure trace, mint a proof digest, then offer one bounded packet",
            "side_effect_gate": "public reply only after proof digest and operator or buyer approval",
            "cashflow_proximity": "highest",
        },
        {
            "cell_id": "endpoint_health_cell",
            "topology": "curl_probe_shadow_lane",
            "packet": endpoint_pack.get("package_id") or "endpoint_health_patch",
            "buyer_trigger": "404, 500, stale deploy, wrong status, or broken public route",
            "entry_url": _u(root, "/service/e2e?service_type=compute_auth"),
            "owned_surface": _u(root, "/.well-known/nomad-buyer-funded-work.json"),
            "anti_human_move": "sell the smallest observable failure envelope instead of a retainer",
            "side_effect_gate": "owned page and requested replies only",
            "cashflow_proximity": "high",
        },
        {
            "cell_id": "agent_loop_break_cell",
            "topology": "trace_silo_plus_retry_circuit",
            "packet": loop_pack.get("package_id") or "agent_loop_break_patch",
            "buyer_trigger": "repeated tool error, retry storm, or hosted-model spend leak",
            "entry_url": _u(root, "/service/e2e?service_type=loop_break"),
            "owned_surface": _u(root, "/doctor?service_type=loop_break"),
            "anti_human_move": "treat the loop as a loss function, not a conversation problem",
            "side_effect_gate": "draft-only until paid task exists",
            "cashflow_proximity": "high",
        },
        {
            "cell_id": "settlement_repair_cell",
            "topology": "receipt_watchdog_with_low_burden_followup",
            "packet": settlement_pack.get("package_id") or "settlement_repair_packet",
            "buyer_trigger": "work appears merged or approved but payment did not settle",
            "entry_url": _u(root, "/service/e2e?service_type=payment"),
            "owned_surface": _u(root, "/.well-known/nomad-settlement.json"),
            "anti_human_move": "do not celebrate merge; keep value in non-revenue state until receipt",
            "side_effect_gate": "one mature follow-up max after no recent follow-up",
            "cashflow_proximity": "medium_high",
        },
        {
            "cell_id": "bounty_bridge_cell",
            "topology": "read_only_scout_then_duplicate_pressure_filter",
            "packet": "external_bounty_to_repo_packet",
            "buyer_trigger": "clear payout terms and low duplicate pressure",
            "entry_url": _u(root, "/.well-known/nomad-bounty-hunter.json"),
            "owned_surface": _u(root, "/.well-known/nomad-value-cycles.json"),
            "anti_human_move": "ignore crowded bounty excitement; pick only proofable low-dup items",
            "side_effect_gate": "no public claim before local proof digest",
            "cashflow_proximity": "medium",
        },
        {
            "cell_id": "paid_ref_context_cell",
            "topology": "owned_surface_referral_router",
            "packet": "cursor_referral_contextual_answer",
            "buyer_trigger": "user already asks about Cursor, agents, or Nomad setup",
            "entry_url": _u(root, "/.well-known/nomad-referral-swarm.json"),
            "owned_surface": _u(root, "/.well-known/nomad-referral-offers.json"),
            "anti_human_move": "no cold referral blast; let only contextual intent pass",
            "side_effect_gate": "owned surfaces and requested answers only",
            "cashflow_proximity": "medium",
        },
        {
            "cell_id": "syndiodepin_node_cell",
            "topology": "physical_gadget_for_active_runtime_selection",
            "packet": "syndiodepin_transition_worker_exchange",
            "buyer_trigger": "operator runs an active Nomad node or transition worker",
            "entry_url": _u(root, "/.well-known/syndiode-gadgets.json"),
            "owned_surface": _u(root, "/nomad.html#syndiode-gadgets"),
            "anti_human_move": "use the gadget as a node-retention signal, not as consumer electronics inventory",
            "side_effect_gate": "selected active nodes only; no open giveaway until capacity is verified",
            "cashflow_proximity": "medium",
        },
        {
            "cell_id": "key_leak_recovery_cell",
            "topology": "secret_free_security_scope",
            "packet": "api_key_rotation_diagnostic",
            "buyer_trigger": "OpenAI, Stripe, or other API key leak notice without exposing keys",
            "entry_url": _u(root, "/service/e2e?service_type=repo_issue_help"),
            "owned_surface": _u(root, "/.well-known/nomad-spend-guard.json"),
            "anti_human_move": "sell a public-proof cleanup scope while refusing to ingest secrets",
            "side_effect_gate": "no secret text, no screenshots with keys, no account mutation",
            "cashflow_proximity": "medium_high",
        },
        {
            "cell_id": "receipt_case_study_cell",
            "topology": "case_digest_without_revenue_claim",
            "packet": "paid_receipt_story_after_settlement",
            "buyer_trigger": "first positive receipt exists",
            "entry_url": _u(root, "/.well-known/nomad-external-value.json"),
            "owned_surface": _u(root, "/.well-known/nomad-work-receipts.json"),
            "anti_human_move": "delay story and social proof until the ledger has a paid event",
            "side_effect_gate": "blocked until positive receipt",
            "cashflow_proximity": "deferred_but_compounds",
        },
    ]

    active_value_cycles = [
        {
            "cycle_id": "render_build_rescue_paid_packet",
            "cell_id": "repo_rescue_cell",
            "first_action": "detect failed deploy or build log, create diagnostic digest, route to repo_diagnostic_patch_starter",
            "buyer_entry": service_entry,
            "terminal_receipt": "verified MetaMask/native transfer or external paid receipt",
        },
        {
            "cycle_id": "github_actions_red_to_patch_packet",
            "cell_id": "repo_rescue_cell",
            "first_action": "read failing workflow log, produce smallest repro path and no-post reply draft",
            "buyer_entry": service_entry,
            "terminal_receipt": "task paid and verifier checklist delivered",
        },
        {
            "cycle_id": "endpoint_404_500_rescue",
            "cell_id": "endpoint_health_cell",
            "first_action": "curl public endpoint, classify stale deploy versus missing route, price a bounded patch pack",
            "buyer_entry": _u(root, "/service/e2e?service_type=compute_auth"),
            "terminal_receipt": "paid task plus endpoint verifier digest",
        },
        {
            "cycle_id": "agent_loop_spend_cut",
            "cell_id": "agent_loop_break_cell",
            "first_action": "turn repeated agent/tool failure into stop condition and retry-circuit package",
            "buyer_entry": _u(root, "/service/e2e?service_type=loop_break"),
            "terminal_receipt": "paid task plus circuit-breaker digest",
        },
        {
            "cycle_id": "settlement_repair_watch",
            "cell_id": "settlement_repair_cell",
            "first_action": "watch mature merged/approved item; draft one low-burden follow-up only when not recent",
            "buyer_entry": _u(root, "/.well-known/nomad-settlement.json"),
            "terminal_receipt": "public payout confirmation or positive balance",
        },
        {
            "cycle_id": "bounty_low_duplicate_scout",
            "cell_id": "bounty_bridge_cell",
            "first_action": "score payout clarity, duplicate pressure, local proof path, and maintainer burden",
            "buyer_entry": _u(root, "/.well-known/nomad-bounty-hunter.json"),
            "terminal_receipt": "external paid receipt only",
        },
        {
            "cycle_id": "owned_referral_intent_capture",
            "cell_id": "paid_ref_context_cell",
            "first_action": "surface referral only where buyer intent is already present",
            "buyer_entry": _u(root, "/.well-known/nomad-referral-swarm.json"),
            "terminal_receipt": "program reward credit, not clicks",
        },
        {
            "cycle_id": "syndiodepin_transition_worker_exchange",
            "cell_id": "syndiodepin_node_cell",
            "first_action": "rank active node candidates, reserve pin only after worker proof and capacity check",
            "buyer_entry": _u(root, "/.well-known/syndiode-gadgets.json"),
            "terminal_receipt": "500 EUR contribution or selected non-cash transition-worker proof",
        },
        {
            "cycle_id": "key_leak_rotation_packet",
            "cell_id": "key_leak_recovery_cell",
            "first_action": "secret-free repo scan scope, rotation checklist, spend-cap verification, and log-review plan",
            "buyer_entry": service_entry,
            "terminal_receipt": "paid task with no secret capture",
        },
        {
            "cycle_id": "first_receipt_case_study",
            "cell_id": "receipt_case_study_cell",
            "first_action": "after paid receipt, compile public proof story and route it into owned surfaces",
            "buyer_entry": _u(root, "/.well-known/nomad-work-receipts.json"),
            "terminal_receipt": "already-paid receipt required before story is enabled",
        },
    ]

    sales_queue = [
        {
            "rank": 1,
            "action": "attach repo_diagnostic_patch_starter to every owned product surface that mentions build, CI, endpoint, or repo help",
            "why": "fastest direct buyer route and already implemented MetaMask task flow",
            "route": service_entry,
        },
        {
            "rank": 2,
            "action": "run read-only scouts for failed public builds and OSS issues, but emit only proof digests and no public messages",
            "why": "research says coordination overhead kills sequential work; one verifier-controlled cell is cheaper",
            "route": _u(root, "/.well-known/nomad-sales-department.json"),
        },
        {
            "rank": 3,
            "action": "route all public promotion candidates through effective-channel quota before ad-cycle queue",
            "why": "homogeneous double votes should be capped before they look like demand",
            "route": _u(root, "/swarm/sales-department/events"),
        },
        {
            "rank": 4,
            "action": "keep RustChain settlement checking active but non-revenue until receipt",
            "why": "the first payout proof compounds only if the ledger stays credible",
            "route": _u(root, "/.well-known/nomad-external-value.json"),
        },
    ]

    quota_summary = _dict(quota.get("summary"))
    value_summary = _dict(value.get("summary"))
    ad_summary = _dict(ads.get("summary"))
    predictor_summary = _dict(predictor.get("summary"))
    science_summary = _dict(science.get("summary"))
    plan_core = {
        "recognized_usd": recognized_usd,
        "cells": [cell["cell_id"] for cell in sales_cells],
        "cycles": [cycle["cycle_id"] for cycle in active_value_cycles],
        "packages": [item.get("package_id") for item in packages],
    }

    return {
        "ok": True,
        "schema": "nomad.sales_department_swarm.v1",
        "generated_at": _now(),
        "public_base_url": root,
        "surface_digest": f"nomad-sales-department-{_digest(plan_core)}",
        "read_url": _u(root, "/swarm/sales-department"),
        "well_known_url": _u(root, "/.well-known/nomad-sales-department.json"),
        "event_url": _u(root, "/swarm/sales-department/events"),
        "summary": {
            "sales_cell_count": len(sales_cells),
            "active_value_cycle_count": len(active_value_cycles),
            "buyer_funded_package_count": len(packages),
            "recognized_revenue_usd_total": recognized_usd,
            "source_value_cycle_count": int(value_summary.get("cycle_count") or 0),
            "source_ad_cycle_count": int(ad_summary.get("cycle_count") or 0),
            "receipt_predictor_cycle_count": int(predictor_summary.get("cycle_count") or 0),
            "revenue_science_experiment_count": int(science_summary.get("experiment_count") or 0),
            "effective_channel_count": int(
                quota_summary.get("effective_channel_count")
                or quota_summary.get("admissible_channel_count")
                or quota_summary.get("channel_count")
                or 0
            ),
        },
        "operating_principles": [
            {
                "id": "topology_before_headcount",
                "rule": "choose single, centralized, or parallel cells by task shape before adding agents",
                "human_counterintuition": "a smaller sales cell can dominate a larger swarm when the job is sequential",
            },
            {
                "id": "anti_majority_sales",
                "rule": "preserve proof-bearing minority channels; cap homogeneous agreement before it becomes spend",
                "human_counterintuition": "the sales department is rewarded for suppressing consensus when it lacks independent evidence",
            },
            {
                "id": "silo_then_digest",
                "rule": "seller cells do not share scratchpads until they produce typed proof digests",
                "human_counterintuition": "coordination is treated as a cost, not a virtue",
            },
            {
                "id": "receipt_weighting",
                "rule": "only verified paid receipts or program reward credits increase route weight",
                "human_counterintuition": "attention, merge, approval, and simulated buyer intent remain non-revenue",
            },
            {
                "id": "owned_contextual_surfaces",
                "rule": "promote on owned surfaces and requested contexts; block cold spread",
                "human_counterintuition": "the best ad is often a machine-readable contract waiting in the right place",
            },
        ],
        "science_sources": SCIENCE_SOURCES,
        "sales_cells": sales_cells,
        "active_value_cycles": active_value_cycles,
        "sales_queue": sales_queue,
        "top_active_route": sales_queue[0],
        "guards": {
            "no_cold_spam": True,
            "no_public_send_without_proof_and_approval": True,
            "no_revenue_without_positive_receipt": True,
            "no_secret_capture": True,
            "stripe_subscription_enabled": False,
            "default_paid_rail": "metamask_native_transfer",
            "api_spend_default": "local_or_zero_spend_first",
        },
        "machine_instruction": [
            "start with repo_rescue_cell for direct cashflow",
            "do not add agents to sequential tasks unless a verifier cell proves benefit",
            "treat duplicate channel agreement as saturation, not confidence",
            "use /swarm/sales-department/events to gate public-action or paid-receipt candidates",
            "record revenue only through existing receipt ledgers after positive settlement",
        ],
    }


def evaluate_sales_department_event(
    payload: Dict[str, Any] | None,
    *,
    base_url: str = "",
    sales_surface: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Evaluate one sales event without posting, sending, or booking revenue."""
    body = _dict(payload)
    surface = _dict(sales_surface)
    cell_id = str(body.get("cell_id") or body.get("cell") or "repo_rescue_cell").strip()
    stage = str(body.get("stage") or body.get("intent") or "draft").strip().lower()
    send_requested = bool(
        body.get("send")
        or body.get("publish")
        or body.get("public_action_requested")
        or stage in {"send", "send_request", "publish"}
    )
    human_approved = bool(body.get("human_approved") or body.get("operator_approved")) or str(
        body.get("approval") or ""
    ).strip().lower() in {"approved", "human_approved", "operator_approved", "buyer_approved"}
    proof_digest = str(
        body.get("proof_digest")
        or body.get("diagnostic_digest")
        or body.get("verifier_trace_digest")
        or ""
    ).strip()
    buyer_intent = str(body.get("buyer_intent_digest") or body.get("buyer_intent") or "").strip()
    settlement_ref = str(body.get("settlement_ref") or body.get("receipt_ref") or body.get("tx_hash") or "").strip()
    amount_usd = _num(body.get("amount_usd") or body.get("paid_amount_usd"), 0.0)
    blockers: list[str] = []
    allowed = True
    stage_kind = "shadow_draft"
    side_effect_allowed = False
    paid_receipt_candidate = False

    if not cell_id:
        blockers.append("cell_id_required")
    if stage == "paid" or amount_usd > 0.0:
        stage_kind = "paid_receipt_candidate"
        if amount_usd <= 0.0:
            blockers.append("positive_amount_required_for_paid")
        if not settlement_ref:
            blockers.append("settlement_ref_required_for_paid")
        if not proof_digest:
            blockers.append("proof_digest_required_for_paid")
        paid_receipt_candidate = not blockers
    elif send_requested:
        stage_kind = "public_send_candidate"
        if not proof_digest:
            blockers.append("proof_digest_required_before_public_send")
        if not buyer_intent:
            blockers.append("buyer_intent_digest_required_before_public_send")
        if not human_approved:
            blockers.append("human_or_buyer_approval_required_before_public_send")
        side_effect_allowed = not blockers
    else:
        if stage in {"discover", "observe"}:
            stage_kind = "read_only_observation"
        elif proof_digest:
            stage_kind = "proof_bearing_draft"
        else:
            stage_kind = "shadow_draft"

    allowed = not blockers
    return {
        "ok": True,
        "schema": "nomad.sales_department_event_decision.v1",
        "generated_at": _now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "surface_digest": surface.get("surface_digest") or "",
        "sales_cycle_allowed": allowed,
        "side_effect_allowed": side_effect_allowed,
        "side_effect_performed": False,
        "paid_receipt_candidate": paid_receipt_candidate,
        "revenue_recorded": False,
        "cell_id": cell_id,
        "stage": stage,
        "stage_kind": stage_kind,
        "blockers": blockers,
        "decision": "admit_candidate" if allowed else "hold_candidate",
        "next_route": _u(base_url, "/service/e2e?service_type=repo_issue_help"),
        "machine_note": (
            "This gate never sends public messages and never books revenue; it only decides whether "
            "a sales candidate is safe to hand to the existing task, ad-cycle, or receipt ledger."
        ),
    }
