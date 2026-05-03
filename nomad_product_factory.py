import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_engagement import AgentEngagementLedger
from agent_pain_solver import AgentPainSolver
from agent_service import AgentServiceDesk
from lead_conversion import LeadConversionPipeline
from nomad_guardrails import NomadGuardrailEngine
from nomad_operator_grant import operator_allows, operator_grant


ROOT = Path(__file__).resolve().parent
DEFAULT_PRODUCT_STORE = ROOT / "nomad_products.json"


PRODUCT_BLUEPRINTS: Dict[str, Dict[str, Any]] = {
    "compute_auth": {
        "sku": "nomad.compute_unlock_pack",
        "name": "Nomad Compute Unlock Pack",
        "tagline": (
            "Problem: auth, quota, model access, and fallback are collapsed into one retry. "
            "Output: separated failure classes and one bounded fallback ladder before next call."
        ),
        "buyer": "agent runs where provider errors are opaque and retries amplify the wrong failure mode",
    },
    "tool_failure": {
        "sku": "nomad.tool_guardrail_pack",
        "name": "Nomad Tool Guardrail Pack",
        "tagline": (
            "Problem: risky or mismatched tool calls enter execution without schema or approval boundary. "
            "Output: interception checklist, contract patch, bounded retry rule."
        ),
        "buyer": "autonomous tool-call stacks where schema drift or guardrail gaps cause repeat damage",
    },
    "mcp_integration": {
        "sku": "nomad.mcp_contract_pack",
        "name": "Nomad MCP Contract Pack",
        "tagline": (
            "Problem: MCP/API calls lack stable schema, timeout, and error shape before entering loops. "
            "Output: contract table plus dry-run path."
        ),
        "buyer": "agents integrating MCP or JSON-RPC tools without frozen request/response expectations",
    },
    "mcp_production": {
        "sku": "nomad.mcp_production_survival_pack",
        "name": "Nomad MCP Production Survival Pack",
        "tagline": (
            "Problem: ambiguous tool success flags, transport drops, registry or gateway flakes, schema drift, "
            "or capped tool loops masquerade as model failure. Output: failure-class matrix and one recovery branch per class."
        ),
        "buyer": (
            "agent runs hitting MCP in production (Copilot-style stacks, remote servers) where humans relabel infra pain as LLM"
        ),
    },
    "attribution_clarity": {
        "sku": "nomad.attribution_clarity_pack",
        "name": "Nomad Attribution Clarity Pack",
        "tagline": (
            "Problem: incidents get moral labels before subsystem evidence exists. Output: hypotheses, disproofs, "
            "probe owner, machine verdict — so the next step is observable, not narrative."
        ),
        "buyer": (
            "agents or operators stuck in false-positive / mis-triage loops where contract, infra, or policy signals exist but nobody correlates them"
        ),
    },
    "branch_economics": {
        "sku": "nomad.branch_economics_ledger_pack",
        "name": "Nomad Branch Economics Ledger Pack",
        "tagline": (
            "Problem: one aggregate spend or token line hides which branch burns retries vs model vs tools. "
            "Output: per-branch dimensions plus latency percentiles for the same keys."
        ),
        "buyer": (
            "multi-branch agent fleets where throttles or budgets need evidence on marginal retry and tool I/O, not headline totals"
        ),
    },
    "stewardship_gap": {
        "sku": "nomad.stewardship_continuity_envelope_pack",
        "name": "Nomad Stewardship Continuity Envelope Pack",
        "tagline": (
            "Problem: human coverage thins while runs stay open; nobody publishes SAFE_CONTINUE or CONTINUITY_CLASS. "
            "Output: verifier-bound degraded lanes, read-only capsule when halt is intentional, operator packet."
        ),
        "buyer": (
            "agents mid-flight when monitoring or ownership goes quiet and you still need a shared machine rule for what may run"
        ),
    },
    "policy_lacuna": {
        "sku": "nomad.policy_lacuna_positive_envelope_pack",
        "name": "Nomad Policy Lacuna Positive Envelope Pack",
        "tagline": (
            "Problem: policy grid has no row for your action class; orgs freeze or improvise inconsistently. "
            "Output: POSITIVE_ENVELOPE vs REQUIRES_MAPPING with verifiers; governance ping only on the second set."
        ),
        "buyer": (
            "agents executing in corpora with sparse written rules who need a reproducible split between still-allowed work and owner-gated work"
        ),
    },
    "tool_turn_invariant": {
        "sku": "nomad.tool_turn_parity_pack",
        "name": "Nomad Tool-Turn Parity Pack",
        "tagline": (
            "Problem: tool call/response cardinality or sibling ordering breaks after parallel or deep MCP traffic; "
            "session hits unrecoverable 400 or mute. Output: parity diff, freeze rule, reset vs repair branch."
        ),
        "buyer": "agent runtimes where provider rules require equal function call/response parts per turn",
    },
    "tool_transport_routing": {
        "sku": "nomad.tool_transport_router_pack",
        "name": "Nomad Tool Transport Router Pack",
        "tagline": (
            "Problem: hosted MCP tools are invoked via function_call (or wrong JSON-RPC channel). Output: "
            "ROUTING_TABLE lockfile + gateway rejection on path mismatch."
        ),
        "buyer": "realtime or multi-transport stacks mixing local functions and hosted MCP under one agent",
    },
    "context_propagation_contract": {
        "sku": "nomad.context_envelope_pack",
        "name": "Nomad Invocation Context Envelope Pack",
        "tagline": (
            "Problem: tenant, principal, or correlation context never reaches the MCP server on the wire. "
            "Output: CONTEXT_ENVELOPE schema + injection point + reject-on-missing for stateful tools."
        ),
        "buyer": "multi-tenant agent gateways where MCP leaves identity propagation underspecified",
    },
    "chain_deadline_budget": {
        "sku": "nomad.chain_deadline_budget_pack",
        "name": "Nomad Chain Deadline Budget Pack",
        "tagline": (
            "Problem: one global turn/planner timeout kills heterogeneous tool chains. Output: per-segment "
            "deadline row + slack + BUDGET_EXHAUSTED with segment id."
        ),
        "buyer": "sequential tool pipelines where p99 latency variance spans orders of magnitude",
    },
    "inter_agent_witness": {
        "sku": "nomad.inter_agent_witness_bundle_pack",
        "name": "Nomad Inter-Agent Witness Bundle Pack",
        "tagline": (
            "Problem: agent B must trust agent A's tool slice to resume spend or execution, but humans are not in the loop "
            "as notaries and blind re-run of every tool is too expensive. Output: WITNESS_BUNDLE v0 (ordered call_ids, "
            "non-secret output digests, envelope snapshot), consumer verifier checklist, replay_refusal boundary."
        ),
        "buyer": (
            "multi-agent stacks, A2A delegations, or buyer agents that pay only after machine-verifiable prior work "
            "— a pain class humans rarely budget for because it is not a dashboard metric"
        ),
    },
    "loop_break": {
        "sku": "nomad.loop_breaker_pack",
        "name": "Nomad Loop Breaker Pack",
        "tagline": (
            "Problem: same error or timeout repeats with no new evidence. "
            "Output: pause fingerprint, last-good snapshot, one recovery lane or explicit approval gate."
        ),
        "buyer": "agent loops stuck on identical tool or HTTP failures without circuit semantics",
    },
    "human_in_loop": {
        "sku": "nomad.hitl_unlock_pack",
        "name": "Nomad HITL Unlock Pack",
        "tagline": (
            "Problem: human gates are vague strings instead of payloads. "
            "Output: do-now / send-back / done-when contract with minimum evidence pack."
        ),
        "buyer": "runs blocked on approval, CAPTCHA, login, or review where the gate is underspecified",
    },
    "repo_issue_help": {
        "sku": "nomad.repo_issue_pr_plan_pack",
        "name": "Nomad Repo Issue PR Plan Pack",
        "tagline": (
            "Problem: public issue context tempts premature posting. "
            "Output: private repro checklist and PR/comment plan behind approval gate."
        ),
        "buyer": "agents or maintainers triaging GitHub issues without safe draft discipline",
    },
    "payment": {
        "sku": "nomad.payment_reliability_pack",
        "name": "Nomad Payment Reliability Pack",
        "tagline": (
            "Problem: wallet or invoice state and delivery are coupled; retries double-charge risk. "
            "Output: idempotent resume graph and verified transition list."
        ),
        "buyer": "agent-paid flows using wallet, x402, or callbacks where state machine is implicit",
    },
    "wallet_payment": {
        "sku": "nomad.payment_reliability_pack",
        "name": "Nomad Payment Reliability Pack",
        "tagline": (
            "Problem: wallet or invoice state and delivery are coupled; retries double-charge risk. "
            "Output: idempotent resume graph and verified transition list."
        ),
        "buyer": "agent-paid flows using wallet, x402, or callbacks where state machine is implicit",
    },
    "memory": {
        "sku": "nomad.memory_repair_pack",
        "name": "Nomad Memory Repair Pack",
        "tagline": (
            "Problem: non-secret lessons evaporate between sessions so the same blocker returns. "
            "Output: durable memory record with retrieval trigger and verifier."
        ),
        "buyer": "long-horizon agents losing constraints, decisions, or solved blockers across restarts",
    },
    "self_improvement": {
        "sku": "nomad.self_healing_pack",
        "name": "Nomad Self-Healing Pack",
        "tagline": (
            "Problem: one-off fixes never become guardrails or regression checks. "
            "Output: packaged blocker → trigger → checklist → verifier artifact."
        ),
        "buyer": "builders who need repeat incidents to become machine-checkable behavior, not chat history",
    },
    "default": {
        "sku": "nomad.agent_rescue_pack",
        "name": "Nomad Agent Rescue Pack",
        "tagline": "Problem: visible blocker with thin human attention. Output: bounded diagnosis, next action, guardrail id, verifier hook.",
        "buyer": "agents with public, verifiable infrastructure pain and no staffed path to classify it",
    },
}


class NomadProductFactory:
    """Turn lead conversions into reusable, sellable Nomad products."""

    def __init__(
        self,
        path: Optional[Path] = None,
        lead_conversion: Optional[LeadConversionPipeline] = None,
        pain_solver: Optional[AgentPainSolver] = None,
        service_desk: Optional[AgentServiceDesk] = None,
        guardrails: Optional[NomadGuardrailEngine] = None,
        engagement_ledger: Optional[AgentEngagementLedger] = None,
    ) -> None:
        self.path = path or DEFAULT_PRODUCT_STORE
        self.lead_conversion = lead_conversion or LeadConversionPipeline()
        self.pain_solver = pain_solver or AgentPainSolver()
        self.service_desk = service_desk or AgentServiceDesk()
        self.guardrails = guardrails or NomadGuardrailEngine()
        self.engagement_ledger = engagement_ledger or AgentEngagementLedger()

    def run(
        self,
        query: str = "",
        limit: int = 5,
        leads: Optional[List[Dict[str, Any]]] = None,
        conversions: Optional[List[Dict[str, Any]]] = None,
        high_value_patterns: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        cap = max(1, min(int(limit or 5), 25))
        conversion_source = self._conversion_source(
            query=query,
            limit=cap,
            leads=leads,
            conversions=conversions,
        )
        engagement_summary = self.engagement_ledger.summary(limit=5)
        source_conversions = list(conversion_source.get("conversions") or [])[:cap]
        conversion_products = [
            self._with_priority(self.product_from_conversion(conversion))
            for conversion in source_conversions
        ]
        pattern_products = [
            self._with_priority(self.product_from_high_value_pattern(pattern))
            for pattern in (high_value_patterns or [])[:cap]
            if isinstance(pattern, dict)
        ]
        products = self._sorted_products(pattern_products + conversion_products)
        state = self._load()
        now = datetime.now(UTC).isoformat()
        for product in products:
            product_id = str(product.get("product_id") or "")
            existing = (state.get("products") or {}).get(product_id) or {}
            if existing.get("created_at") and not product.get("created_at"):
                product["created_at"] = existing["created_at"]
            product.setdefault("created_at", existing.get("created_at") or now)
            product["updated_at"] = now
            state["products"][product_id] = product
        self._save(state)
        stats = self._stats(products)
        top_priority_product = products[0] if products else {}
        return {
            "mode": "nomad_product_factory",
            "deal_found": False,
            "ok": True,
            "generated_at": now,
            "query": query,
            "conversion_source": {
                "mode": conversion_source.get("mode", ""),
                "ok": conversion_source.get("ok", True),
                "conversion_count": len(source_conversions),
            },
            "pattern_source": {
                "pattern_count": len(high_value_patterns or []),
            },
            "engagement_summary": engagement_summary,
            "product_count": len(products),
            "stats": stats,
            "products": products,
            "top_priority_product": top_priority_product,
            "policy": self.policy(),
            "analysis": (
                f"Nomad productized {len(products)} source artifact(s): "
                f"{stats.get('offer_ready', 0)} offer-ready, "
                f"{stats.get('private_offer_needs_approval', 0)} private offers need approval, "
                f"{stats.get('watchlist', 0)} watchlist. "
                f"Engagements: customers={((engagement_summary.get('roles') or {}).get('customer', 0))}, "
                f"peer_solvers={((engagement_summary.get('roles') or {}).get('peer_solver', 0))}. "
                f"Top priority: {(top_priority_product.get('name') or top_priority_product.get('product_family') or 'none')}."
            ),
        }

    def list_products(
        self,
        statuses: Optional[List[str]] = None,
        limit: int = 25,
    ) -> Dict[str, Any]:
        normalized_statuses = {
            str(item).strip()
            for item in (statuses or [])
            if str(item).strip()
        }
        products = list((self._load().get("products") or {}).values())
        if normalized_statuses:
            products = [
                item for item in products
                if str(item.get("status") or "") in normalized_statuses
            ]
        products = [self._with_priority(dict(item)) for item in products]
        products = self._sorted_products(products)
        cap = max(1, min(int(limit or 25), 100))
        limited = products[:cap]
        return {
            "mode": "nomad_product_list",
            "deal_found": False,
            "ok": True,
            "statuses": sorted(normalized_statuses),
            "engagement_summary": self.engagement_ledger.summary(limit=5),
            "stats": self._stats(products),
            "products": limited,
            "top_priority_product": limited[0] if limited else {},
            "analysis": f"Listed {len(limited)} Nomad product(s).",
        }

    def product_from_conversion(self, conversion: Dict[str, Any]) -> Dict[str, Any]:
        lead = conversion.get("lead") or {}
        free_value = conversion.get("free_value") or {}
        value_pack = free_value.get("value_pack") or {}
        agent_solution = free_value.get("agent_solution") or {}
        rescue_plan = free_value.get("rescue_plan") or {}
        help_draft = free_value.get("private_help_draft") or {}
        route = conversion.get("route") or value_pack.get("route") or {}
        service_type = self._service_type(conversion)
        blueprint = PRODUCT_BLUEPRINTS.get(service_type) or PRODUCT_BLUEPRINTS["default"]
        guardrail_id = self._guardrail_id(agent_solution, rescue_plan, value_pack)
        lead_solution = self._lead_solution(
            lead=lead,
            value_pack=value_pack,
            rescue_plan=rescue_plan,
            agent_solution=agent_solution,
            help_draft=help_draft,
            service_type=service_type,
        )
        variant = self._product_variant(
            lead=lead,
            blueprint=blueprint,
            service_type=service_type,
            guardrail_id=guardrail_id,
            lead_solution=lead_solution,
        )
        product_id = self._product_id(
            lead=lead,
            service_type=service_type,
            guardrail_id=guardrail_id,
            variant_slug=variant["slug"],
        )
        paid_upgrade = value_pack.get("paid_upgrade") or {}
        commercial = rescue_plan.get("commercial_next_step") or {}
        price_native = paid_upgrade.get("price_native")
        if price_native is None:
            price_native = commercial.get("price_native")
        status = self._product_status(conversion)
        route_guardrail = route.get("guardrail") or {}
        approval_boundary = self._approval_boundary(route, rescue_plan, route_guardrail)
        grant = operator_grant()
        free_steps = self._free_steps(value_pack, rescue_plan, agent_solution, service_type)
        paid_offer = self._paid_offer(
            blueprint=blueprint,
            paid_upgrade=paid_upgrade,
            commercial=commercial,
            rescue_plan=rescue_plan,
            agent_solution=agent_solution,
            service_type=service_type,
            price_native=price_native,
            variant=variant,
            lead_solution=lead_solution,
        )
        return {
            "schema": "nomad.product.v1",
            "product_id": product_id,
            "created_at": conversion.get("created_at") or datetime.now(UTC).isoformat(),
            "source_lead": {
                "title": lead.get("title", ""),
                "url": lead.get("url", ""),
                "pain": lead.get("pain", ""),
                "service_type": service_type,
                "conversion_id": conversion.get("conversion_id", ""),
                "value_pack_id": value_pack.get("pack_id", ""),
            },
            "base_sku": blueprint["sku"],
            "sku": blueprint["sku"],
            "variant_sku": variant["sku"],
            "product_family": blueprint["name"],
            "base_name": blueprint["name"],
            "name": variant["name"],
            "tagline": blueprint["tagline"],
            "variant_tagline": variant["tagline"],
            "buyer": blueprint["buyer"],
            "pain_type": service_type,
            "guardrail_id": guardrail_id,
            "product_variant": variant,
            "lead_solution": lead_solution,
            "differentiators": variant["differentiators"],
            "status": status,
            "sellable_now": status in {"offer_ready", "private_offer_needs_approval"},
            "sellable_channels": self._sellable_channels(status),
            "outreach_blocked_by_approval": status == "private_offer_needs_approval",
            "operator_grant": grant,
            "free_value": {
                "artifact_schema": value_pack.get("schema") or "nomad.agent_value_pack.v1",
                "value_pack_id": value_pack.get("pack_id", ""),
                "painpoint_question": value_pack.get("painpoint_question", ""),
                "safe_now": free_steps,
                "verifier": ((value_pack.get("immediate_value") or {}).get("verifier") or ""),
                "reply_contract": value_pack.get("reply_contract") or {},
            },
            "paid_offer": paid_offer,
            "service_template": self._service_template(
                product_id=product_id,
                conversion=conversion,
                service_type=service_type,
                paid_offer=paid_offer,
            ),
            "product_artifacts": {
                "value_pack_schema": value_pack.get("schema") or "nomad.agent_value_pack.v1",
                "agent_solution_schema": agent_solution.get("schema") or "nomad.agent_solution.v1",
                "rescue_plan_schema": rescue_plan.get("schema") or "nomad.rescue_plan.v1",
                "guardrail_schema": "nomad.guardrail_evaluation.v1",
                "conversion_id": conversion.get("conversion_id", ""),
                "solution_id": agent_solution.get("solution_id", ""),
                "rescue_plan_id": rescue_plan.get("plan_id", ""),
                "product_package": lead_solution.get("product_package", ""),
                "solution_pattern": lead_solution.get("solution_pattern", ""),
                "productized_artifacts": lead_solution.get("productized_artifacts") or [],
                "deliverables": lead_solution.get("deliverables") or [],
                "solution_signature": variant.get("solution_signature", ""),
            },
            "runtime_hooks": {
                "lead_conversion": "nomad_lead_conversion_pipeline",
                "agent_pain_solver": "nomad_agent_pain_solver",
                "service_task": "nomad_service_request",
                "guardrail_id": guardrail_id,
                "product_variant_slug": variant["slug"],
                "variant_sku": variant["sku"],
                "nomad_self_apply": value_pack.get("nomad_self_apply") or agent_solution.get("nomad_self_apply") or {},
            },
            "sales_motion": {
                "sequence": [
                    "free_value_first",
                    "PLAN_ACCEPTED=true plus one public fact or error",
                    "create wallet-payable service task",
                    "verify payment or x402 signature",
                    "deliver draft-only artifact unless explicit approval expands scope",
                    "package solved blocker as reusable memory or guardrail",
                ],
                "machine_offer": self._machine_offer(
                    product_id,
                    blueprint,
                    free_steps,
                    paid_offer,
                    approval_boundary,
                    variant=variant,
                ),
            },
            "approval_boundary": approval_boundary,
            "next_action": self._next_action(status, route, paid_offer),
        }

    def policy(self) -> Dict[str, Any]:
        return {
            "schema": "nomad.product_factory_policy.v1",
            "default": "productize_free_value_without_public_posting",
            "operator_grant": operator_grant(),
            "source_artifacts": [
                "nomad.agent_value_pack.v1",
                "nomad.agent_solution.v1",
                "nomad.rescue_plan.v1",
                "nomad.guardrail_evaluation.v1",
            ],
            "safe_without_approval": [
                "build private products from public lead metadata",
                "store SKU, service template, reply contract, and free-value artifact",
                "queue bounded offers to public machine-readable agent endpoints",
            ],
            "requires_explicit_approval": [
                "posting GitHub comments",
                "opening PRs",
                "sending human DMs or email",
                "claiming public endorsement",
            ],
            "goal": "Make every solved lead reusable by Nomad and sellable to other agents.",
            "runtime_guardrails": self.guardrails.policy(),
        }

    def product_from_high_value_pattern(self, pattern: Dict[str, Any]) -> Dict[str, Any]:
        pain_type = str(pattern.get("pain_type") or "self_improvement").strip() or "self_improvement"
        blueprint = PRODUCT_BLUEPRINTS.get(pain_type) or PRODUCT_BLUEPRINTS["default"]
        productization = pattern.get("productization") or {}
        agent_offer = pattern.get("agent_offer") or {}
        self_evolution = pattern.get("self_evolution") or {}
        variant = self._pattern_variant(pattern=pattern, blueprint=blueprint)
        product_id = self._pattern_product_id(pattern=pattern, variant_slug=variant["slug"])
        status = "offer_ready" if operator_allows("productization") else "private_offer_needs_approval"
        paid_offer = {
            "sku": blueprint["sku"],
            "variant_sku": variant["sku"],
            "package": variant["name"],
            "base_package": blueprint["name"],
            "trigger": agent_offer.get("reply_contract") or "PLAN_ACCEPTED=true plus FACT_URL or ERROR",
            "service_type": pain_type,
            "price_native": ((productization.get("paid_offer") or {}).get("amount_native") or 0.03),
            "delivery": (
                (productization.get("paid_offer") or {}).get("delivery")
                or ((agent_offer.get("smallest_paid_unblock") or {}).get("delivery"))
                or "bounded reusable unblock"
            ),
            "acceptance_criteria": [
                "requester confirms the pattern matches their blocker",
                "starter diagnosis delivered before paid unblock",
                "outcome is recorded back into the truth-density ledger",
            ],
            "required_input": "FACT_URL, ERROR, or one machine-readable failure trace",
            "solution_pattern": pattern.get("title", ""),
            "productized_artifacts": [
                "service blueprint",
                "verifier checklist",
                "self-apply route",
            ],
            "offer_ladder": [],
            "boundary": "Paid work does not authorize public posting, private access, spend, or human impersonation.",
        }
        approval_boundary = {
            "route_status": "pattern_ready",
            "route_action": "reuse_machine_offer",
            "guardrail_decision": "allow" if status == "offer_ready" else "deny",
            "approval_required": status != "offer_ready",
            "approval_gate": "" if status == "offer_ready" else "NOMAD_OPERATOR_GRANT includes productization",
            "operator_can_reuse_private_product": operator_allows("productization"),
            "operator_can_contact_machine_endpoint": operator_allows("agent_endpoint_contact"),
            "can_do_without_approval": [
                "build machine-readable offer",
                "list the product in Nomad's private catalog",
                "reuse the service blueprint internally",
            ],
            "requires_explicit_approval": [
                "posting human-facing public comments",
            ],
        }
        free_steps = self._clean_list(
            [
                agent_offer.get("starter_diagnosis"),
                self_evolution.get("self_apply_step"),
            ]
        )
        return {
            "schema": "nomad.product.v1",
            "product_id": product_id,
            "created_at": datetime.now(UTC).isoformat(),
            "source_lead": {
                "title": "",
                "url": "",
                "pain": pattern.get("title", ""),
                "service_type": pain_type,
                "conversion_id": "",
                "value_pack_id": "",
            },
            "source_pattern": {
                "pattern_id": pattern.get("pattern_id", ""),
                "title": pattern.get("title", ""),
                "occurrence_count": pattern.get("occurrence_count", 0),
                "avg_truth_score": pattern.get("avg_truth_score", 0),
                "avg_reuse_value": pattern.get("avg_reuse_value", 0),
            },
            "base_sku": blueprint["sku"],
            "sku": blueprint["sku"],
            "variant_sku": variant["sku"],
            "product_family": blueprint["name"],
            "base_name": blueprint["name"],
            "name": variant["name"],
            "tagline": blueprint["tagline"],
            "variant_tagline": variant["tagline"],
            "buyer": blueprint["buyer"],
            "pain_type": pain_type,
            "guardrail_id": "",
            "product_variant": variant,
            "lead_solution": {
                "schema": "nomad.lead_solution.v1",
                "lead_title": pattern.get("title", ""),
                "lead_url": "",
                "pain": pattern.get("title", ""),
                "service_type": pain_type,
                "diagnosis": agent_offer.get("starter_diagnosis", ""),
                "first_response": agent_offer.get("starter_diagnosis", ""),
                "product_package": productization.get("name") or blueprint["name"],
                "solution_pattern": pattern.get("title", ""),
                "delivery_target": paid_offer["delivery"],
                "productized_artifacts": ["service blueprint", "verifier checklist"],
                "deliverables": ["starter diagnosis", "verifier checklist", "self-apply route"],
                "required_input": paid_offer["required_input"],
                "verification": {
                    "verifier": self_evolution.get("regression_test_stub", ""),
                    "acceptance_criteria": paid_offer["acceptance_criteria"],
                },
                "memory_upgrade": self_evolution.get("self_apply_step", ""),
            },
            "differentiators": variant["differentiators"],
            "status": status,
            "sellable_now": status in {"offer_ready", "private_offer_needs_approval"},
            "sellable_channels": self._sellable_channels(status),
            "outreach_blocked_by_approval": status == "private_offer_needs_approval",
            "operator_grant": operator_grant(),
            "free_value": {
                "artifact_schema": "nomad.high_value_pattern.v1",
                "value_pack_id": pattern.get("pattern_id", ""),
                "painpoint_question": f"Does your agent show the repeated pattern '{pattern.get('title', '')}'?",
                "safe_now": free_steps,
                "verifier": self_evolution.get("regression_test_stub", ""),
                "reply_contract": {
                    "accept": agent_offer.get("reply_contract", "PLAN_ACCEPTED=true plus FACT_URL or ERROR"),
                },
            },
            "paid_offer": paid_offer,
            "service_template": {
                "endpoint": "POST /tasks",
                "mcp_tool": "nomad_service_request",
                "create_task_payload": {
                    "problem": f"{pattern.get('title', '')} | pattern_id={pattern.get('pattern_id', '')}",
                    "service_type": pain_type,
                    "budget_native": paid_offer["price_native"],
                    "metadata": {
                        "product_id": product_id,
                        "sku": blueprint["sku"],
                        "variant_sku": variant["sku"],
                        "pattern_id": pattern.get("pattern_id", ""),
                        "approval_boundary": paid_offer["boundary"],
                        "solution_pattern": pattern.get("title", ""),
                    },
                },
            },
            "product_artifacts": {
                "value_pack_schema": "nomad.high_value_pattern.v1",
                "agent_solution_schema": "nomad.agent_solution.v1",
                "rescue_plan_schema": "nomad.service_blueprint.v1",
                "guardrail_schema": "nomad.guardrail_evaluation.v1",
                "conversion_id": "",
                "solution_id": pattern.get("latest_solution_id", ""),
                "rescue_plan_id": pattern.get("pattern_id", ""),
                "product_package": productization.get("name") or blueprint["name"],
                "solution_pattern": pattern.get("title", ""),
                "productized_artifacts": ["service blueprint", "verifier checklist"],
                "deliverables": ["starter diagnosis", "bounded unblock", "self-apply route"],
                "solution_signature": variant.get("solution_signature", ""),
            },
            "runtime_hooks": {
                "lead_conversion": "",
                "agent_pain_solver": "nomad_agent_pain_solver",
                "service_task": "nomad_service_request",
                "guardrail_id": "",
                "product_variant_slug": variant["slug"],
                "variant_sku": variant["sku"],
                "nomad_self_apply": {
                    "pattern_id": pattern.get("pattern_id", ""),
                    "step": self_evolution.get("self_apply_step", ""),
                },
            },
            "sales_motion": {
                "sequence": [
                    "free_value_first",
                    "confirm the blocker matches the pattern",
                    "PLAN_ACCEPTED=true plus FACT_URL or ERROR",
                    "create wallet-payable service task",
                    "deliver starter diagnosis and verifier checklist",
                    "record the outcome back into the truth-density ledger",
                ],
                "machine_offer": self._machine_offer(
                    product_id,
                    blueprint,
                    free_steps,
                    paid_offer,
                    approval_boundary,
                    variant=variant,
                ),
            },
            "approval_boundary": approval_boundary,
            "next_action": self._next_action(status, {}, paid_offer),
        }

    def _conversion_source(
        self,
        query: str,
        limit: int,
        leads: Optional[List[Dict[str, Any]]],
        conversions: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        if conversions is not None:
            return {
                "mode": "provided_conversions",
                "ok": True,
                "conversions": conversions,
            }
        if leads is not None or str(query or "").strip():
            return self.lead_conversion.run(
                query=str(query or "").strip(),
                limit=limit,
                leads=leads,
            )
        return self.lead_conversion.list_conversions(limit=limit)

    def _service_type(self, conversion: Dict[str, Any]) -> str:
        lead = conversion.get("lead") or {}
        value_pack = ((conversion.get("free_value") or {}).get("value_pack") or {})
        solution = ((conversion.get("free_value") or {}).get("agent_solution") or {})
        return str(
            lead.get("service_type")
            or solution.get("pain_type")
            or ((value_pack.get("lead") or {}).get("service_type"))
            or "self_improvement"
        ).strip() or "self_improvement"

    def _pattern_variant(
        self,
        pattern: Dict[str, Any],
        blueprint: Dict[str, Any],
    ) -> Dict[str, Any]:
        title = str(pattern.get("title") or pattern.get("pain_type") or blueprint.get("name") or "").strip()
        pain_type = str(pattern.get("pain_type") or "self_improvement").strip() or "self_improvement"
        slug_base = self._slug(title) or self._slug(pain_type) or "agent-pattern"
        pattern_id = str(pattern.get("pattern_id") or "").strip()
        digest = hashlib.sha256(f"{pattern_id}|{title}|{pain_type}".encode("utf-8")).hexdigest()[:8]
        slug = f"{slug_base[:42].strip('-')}-{digest}"
        differentiators = self._clean_list(
            [
                f"Repeated pain type: {pain_type}",
                f"Occurrence count: {pattern.get('occurrence_count', 0)}",
                f"Average truth score: {pattern.get('avg_truth_score', 0)}",
                f"Average reuse value: {pattern.get('avg_reuse_value', 0)}",
            ]
        )
        return {
            "schema": "nomad.product_variant.v1",
            "slug": slug,
            "sku": f"{blueprint['sku']}.{slug}",
            "name": f"{blueprint['name']}: {title}",
            "tagline": f"{title} as a reusable bounded service offer."[:240],
            "lead_phrase": self._short_phrase(title),
            "solution_phrase": self._short_phrase(title),
            "solution_signature": hashlib.sha256(
                "|".join([pain_type, title, pattern_id]).encode("utf-8")
            ).hexdigest()[:12],
            "differentiators": differentiators[:8],
        }

    @staticmethod
    def _pattern_product_id(pattern: Dict[str, Any], variant_slug: str = "") -> str:
        seed = "|".join(
            [
                str(pattern.get("pattern_id") or ""),
                str(pattern.get("title") or ""),
                str(pattern.get("pain_type") or ""),
                variant_slug,
            ]
        )
        return f"prod-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"

    def _guardrail_id(
        self,
        agent_solution: Dict[str, Any],
        rescue_plan: Dict[str, Any],
        value_pack: Dict[str, Any],
    ) -> str:
        return str(
            ((agent_solution.get("guardrail") or {}).get("id"))
            or (((rescue_plan.get("solution_pattern") or {}).get("guardrail") or {}).get("id"))
            or ((rescue_plan.get("solution_pattern") or {}).get("guardrail_id"))
            or (((value_pack.get("pain_hypothesis") or {}).get("guardrail_id")))
            or "nomad_guardrail"
        )

    def _free_steps(
        self,
        value_pack: Dict[str, Any],
        rescue_plan: Dict[str, Any],
        agent_solution: Dict[str, Any],
        service_type: str,
    ) -> List[str]:
        rescue_service_type = str(rescue_plan.get("service_type") or "").strip()
        if rescue_service_type and rescue_service_type != service_type:
            solution_steps = [
                str(item)
                for item in (agent_solution.get("playbook") or [])[:5]
                if str(item).strip()
            ]
            if solution_steps:
                return solution_steps
        immediate = value_pack.get("immediate_value") or {}
        steps = [str(item) for item in (immediate.get("safe_now") or []) if str(item).strip()]
        if not steps:
            steps = [str(item) for item in (rescue_plan.get("safe_now") or []) if str(item).strip()]
        if not steps:
            steps = [str(item) for item in (agent_solution.get("playbook") or [])[:3] if str(item).strip()]
        return steps[:5]

    def _paid_offer(
        self,
        blueprint: Dict[str, Any],
        paid_upgrade: Dict[str, Any],
        commercial: Dict[str, Any],
        rescue_plan: Dict[str, Any],
        agent_solution: Dict[str, Any],
        service_type: str,
        price_native: Any,
        variant: Optional[Dict[str, Any]] = None,
        lead_solution: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        variant = variant or {}
        lead_solution = lead_solution or {}
        ladder = rescue_plan.get("commercial_ladder") or []
        rescue_service_type = str(rescue_plan.get("service_type") or "").strip()
        service_type_mismatch = bool(rescue_service_type and rescue_service_type != service_type)
        acceptance = (
            agent_solution.get("acceptance_criteria")
            if service_type_mismatch
            else rescue_plan.get("acceptance_criteria")
        ) or rescue_plan.get("acceptance_criteria") or agent_solution.get("acceptance_criteria") or []
        required_input = (
            agent_solution.get("required_input")
            if service_type_mismatch
            else rescue_plan.get("required_input")
        ) or rescue_plan.get("required_input") or agent_solution.get("required_input") or ""
        return {
            "sku": blueprint["sku"],
            "variant_sku": variant.get("sku", ""),
            "package": variant.get("name") or lead_solution.get("product_package") or blueprint["name"],
            "base_package": blueprint["name"],
            "trigger": paid_upgrade.get("trigger") or "Reply with PLAN_ACCEPTED=true plus one missing fact.",
            "service_type": paid_upgrade.get("service_type") or rescue_plan.get("service_type", ""),
            "price_native": price_native,
            "delivery": (
                paid_upgrade.get("delivery")
                or commercial.get("delivery")
                or lead_solution.get("delivery_target")
                or "bounded draft-only rescue artifact"
            ),
            "acceptance_criteria": acceptance,
            "required_input": required_input,
            "solution_pattern": lead_solution.get("solution_pattern", ""),
            "productized_artifacts": lead_solution.get("productized_artifacts") or [],
            "offer_ladder": [] if service_type_mismatch else ladder[:2],
            "boundary": paid_upgrade.get("boundary")
            or "Paid work does not authorize public posting, private access, spend, or human impersonation.",
        }

    def _service_template(
        self,
        product_id: str,
        conversion: Dict[str, Any],
        service_type: str,
        paid_offer: Dict[str, Any],
    ) -> Dict[str, Any]:
        lead = conversion.get("lead") or {}
        value_pack = ((conversion.get("free_value") or {}).get("value_pack") or {})
        problem = " ".join(
            item
            for item in [
                str(lead.get("title") or "").strip(),
                str(lead.get("pain") or "").strip(),
                f"value_pack_id={value_pack.get('pack_id', '')}" if value_pack.get("pack_id") else "",
            ]
            if item
        )
        return {
            "endpoint": "POST /tasks",
            "mcp_tool": "nomad_service_request",
            "create_task_payload": {
                "problem": problem or f"Nomad product task {product_id}",
                "service_type": service_type,
                "budget_native": paid_offer.get("price_native"),
                "metadata": {
                    "product_id": product_id,
                    "sku": paid_offer.get("sku", ""),
                    "variant_sku": paid_offer.get("variant_sku", ""),
                    "conversion_id": conversion.get("conversion_id", ""),
                    "value_pack_id": value_pack.get("pack_id", ""),
                    "approval_boundary": paid_offer.get("boundary", ""),
                    "solution_pattern": paid_offer.get("solution_pattern", ""),
                },
            },
        }

    def _lead_solution(
        self,
        lead: Dict[str, Any],
        value_pack: Dict[str, Any],
        rescue_plan: Dict[str, Any],
        agent_solution: Dict[str, Any],
        help_draft: Dict[str, Any],
        service_type: str,
    ) -> Dict[str, Any]:
        hypothesis = value_pack.get("pain_hypothesis") or {}
        immediate = value_pack.get("immediate_value") or {}
        commercial = rescue_plan.get("commercial_next_step") or {}
        deliverables = self._clean_list(
            help_draft.get("deliverables")
            or commercial.get("deliverables")
            or rescue_plan.get("deliverables")
            or []
        )
        productized = self._clean_list(help_draft.get("productized_artifacts") or [])
        if not productized:
            productized = self._clean_list(
                [
                    hypothesis.get("guardrail_id"),
                    commercial.get("delivery"),
                    agent_solution.get("title"),
                ]
            )
        diagnosis = (
            str(rescue_plan.get("diagnosis") or "").strip()
            or str(hypothesis.get("diagnosis") or "").strip()
            or str(agent_solution.get("diagnosis") or "").strip()
        )
        acceptance = self._clean_list(
            immediate.get("acceptance_criteria")
            or rescue_plan.get("acceptance_criteria")
            or agent_solution.get("acceptance_criteria")
            or []
        )
        product_package = (
            str(help_draft.get("product_package") or "").strip()
            or str(commercial.get("package") or "").strip()
            or str(PRODUCT_BLUEPRINTS.get(service_type, PRODUCT_BLUEPRINTS["default"]).get("name") or "").strip()
        )
        rescue_pattern = rescue_plan.get("solution_pattern")
        if isinstance(rescue_pattern, dict):
            rescue_pattern_text = str(rescue_pattern.get("title") or "").strip()
        else:
            rescue_pattern_text = str(rescue_pattern or "").strip()
        solution_pattern = (
            str(help_draft.get("solution_pattern") or "").strip()
            or rescue_pattern_text
            or str(agent_solution.get("title") or "").strip()
        )
        required_input = str(
            immediate.get("required_input")
            or rescue_plan.get("required_input")
            or agent_solution.get("required_input")
            or ""
        ).strip()
        memory_upgrade = str(
            help_draft.get("memory_upgrade")
            or rescue_plan.get("memory_upgrade")
            or agent_solution.get("memory_upgrade")
            or ""
        ).strip()
        return {
            "schema": "nomad.lead_solution.v1",
            "lead_title": lead.get("title", ""),
            "lead_url": lead.get("url", ""),
            "pain": lead.get("pain", ""),
            "service_type": service_type,
            "diagnosis": diagnosis,
            "first_response": (
                str(help_draft.get("first_useful_help_action") or "").strip()
                or str(help_draft.get("private_response_draft") or "").strip()
            )[:1200],
            "product_package": product_package,
            "solution_pattern": solution_pattern,
            "delivery_target": str(help_draft.get("delivery_target") or commercial.get("delivery") or "").strip(),
            "productized_artifacts": productized,
            "deliverables": deliverables,
            "required_input": required_input,
            "verification": {
                "verifier": immediate.get("verifier", ""),
                "acceptance_criteria": acceptance,
            },
            "memory_upgrade": memory_upgrade,
        }

    def _product_variant(
        self,
        lead: Dict[str, Any],
        blueprint: Dict[str, Any],
        service_type: str,
        guardrail_id: str,
        lead_solution: Dict[str, Any],
    ) -> Dict[str, Any]:
        lead_phrase = self._short_phrase(lead.get("title") or lead.get("pain") or service_type)
        solution_phrase = self._short_phrase(
            lead_solution.get("solution_pattern")
            or lead_solution.get("product_package")
            or guardrail_id
        )
        label = " ".join(item for item in [lead_phrase, solution_phrase] if item).strip()
        if not label:
            label = self._short_phrase(blueprint.get("name") or service_type)
        digest_seed = json.dumps(
            {
                "url": lead.get("url", ""),
                "title": lead.get("title", ""),
                "pain": lead.get("pain", ""),
                "service_type": service_type,
                "guardrail_id": guardrail_id,
                "solution_pattern": lead_solution.get("solution_pattern", ""),
                "artifacts": lead_solution.get("productized_artifacts") or [],
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        digest = hashlib.sha256(digest_seed.encode("utf-8")).hexdigest()[:8]
        slug_base = self._slug(label) or self._slug(service_type) or "agent-rescue"
        slug = f"{slug_base[:42].strip('-')}-{digest}"
        differentiators = self._clean_list(
            [
                f"Lead-specific source: {lead.get('title', '')}",
                f"Pain type: {service_type}",
                f"Solution pattern: {lead_solution.get('solution_pattern', '')}",
                f"Guardrail: {guardrail_id}",
                *[
                    f"Artifact: {item}"
                    for item in (lead_solution.get("productized_artifacts") or [])[:4]
                ],
            ]
        )
        return {
            "schema": "nomad.product_variant.v1",
            "slug": slug,
            "sku": f"{blueprint['sku']}.{slug}",
            "name": f"{blueprint['name']}: {label}",
            "tagline": (
                f"{lead_solution.get('product_package') or blueprint['name']} for "
                f"{lead.get('title') or lead.get('pain') or service_type}."
            )[:240],
            "lead_phrase": lead_phrase,
            "solution_phrase": solution_phrase,
            "solution_signature": hashlib.sha256(
                "|".join(
                    [
                        service_type,
                        guardrail_id,
                        str(lead_solution.get("solution_pattern") or ""),
                        ",".join(lead_solution.get("productized_artifacts") or []),
                    ]
                ).encode("utf-8")
            ).hexdigest()[:12],
            "differentiators": differentiators[:8],
        }

    def _approval_boundary(
        self,
        route: Dict[str, Any],
        rescue_plan: Dict[str, Any],
        route_guardrail: Dict[str, Any],
    ) -> Dict[str, Any]:
        decision = str(route_guardrail.get("decision") or "").strip()
        approval_gate = route.get("approval_gate") or (
            ((route_guardrail.get("results") or [{}])[-1].get("metadata") or {}).get("approval_required")
            if isinstance(route_guardrail.get("results"), list) and route_guardrail.get("results")
            else ""
        )
        plan_boundary = rescue_plan.get("approval_boundary") or {}
        return {
            "route_status": route.get("status", ""),
            "route_action": route.get("action", ""),
            "guardrail_decision": decision,
            "approval_required": bool(approval_gate or decision == "deny"),
            "approval_gate": approval_gate,
            "operator_can_reuse_private_product": operator_allows("productization"),
            "operator_can_contact_machine_endpoint": operator_allows("agent_endpoint_contact"),
            "can_do_without_approval": plan_boundary.get("can_do_without_approval") or [],
            "requires_explicit_approval": plan_boundary.get("requires_explicit_approval") or [],
        }

    @staticmethod
    def _sellable_channels(status: str) -> List[str]:
        if status == "offer_ready":
            return ["machine_readable_agent_endpoint", "private_catalog"]
        if status == "private_offer_needs_approval":
            return ["private_catalog", "operator_review", "machine_endpoint_when_provided"]
        return ["private_catalog"]

    def _product_status(self, conversion: Dict[str, Any]) -> str:
        status = str(conversion.get("status") or "").strip()
        if status in {
            "queued_agent_contact",
            "sent_agent_contact",
            "ready_to_queue_agent_contact",
            "public_comment_approved",
            "public_pr_plan_approved",
        }:
            return "offer_ready"
        if status == "private_draft_needs_approval":
            return "private_offer_needs_approval"
        if status == "watchlist_low_fit":
            return "watchlist"
        if status == "blocked_contact_policy":
            return "blocked"
        return status or "draft"

    def _next_action(
        self,
        status: str,
        route: Dict[str, Any],
        paid_offer: Dict[str, Any],
    ) -> Dict[str, Any]:
        if status == "private_offer_needs_approval":
            return {
                "action": "get_explicit_approval_or_machine_endpoint",
                "instruction": route.get("approval_gate") or "APPROVE_LEAD_HELP=comment or provide AGENT_ENDPOINT_URL=https://...",
                "safe_default": "keep the product private and reuse it inside Nomad.",
            }
        if status == "offer_ready":
            return {
                "action": "await_plan_accepted_or_create_task",
                "instruction": "If the receiving agent replies PLAN_ACCEPTED=true, create the service task from service_template.",
                "paid_trigger": paid_offer.get("trigger", ""),
            }
        if status == "watchlist":
            return {
                "action": "collect_stronger_signal",
                "instruction": "Wait for buyer intent, public endpoint, exact error, bounty, or production urgency.",
            }
        return {
            "action": "review_product",
            "instruction": "Review status and guardrail trace before outreach or task creation.",
        }

    def _machine_offer(
        self,
        product_id: str,
        blueprint: Dict[str, Any],
        free_steps: List[str],
        paid_offer: Dict[str, Any],
        approval_boundary: Dict[str, Any],
        variant: Optional[Dict[str, Any]] = None,
    ) -> str:
        variant = variant or {}
        lines = [
            "nomad.product_offer.v1",
            f"product_id={product_id}",
            f"sku={blueprint.get('sku', '')}",
            f"variant_sku={variant.get('sku', '')}",
            f"name={variant.get('name') or blueprint.get('name', '')}",
            f"free_value={' | '.join(free_steps[:2])}",
            f"paid_delivery={paid_offer.get('delivery', '')}",
            f"price_native={paid_offer.get('price_native')}",
            "reply=PLAN_ACCEPTED=true plus FACT_URL or ERROR",
            f"approval_required={str(bool(approval_boundary.get('approval_required'))).lower()}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _product_id(
        lead: Dict[str, Any],
        service_type: str,
        guardrail_id: str,
        variant_slug: str = "",
    ) -> str:
        seed = "|".join(
            [
                str(lead.get("url") or ""),
                str(lead.get("title") or ""),
                str(lead.get("pain") or ""),
                service_type,
                guardrail_id,
                variant_slug,
            ]
        )
        return f"prod-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"

    @staticmethod
    def _clean_list(items: Any) -> List[str]:
        if isinstance(items, str):
            items = [items]
        cleaned: List[str] = []
        for item in items or []:
            text = " ".join(str(item or "").split())
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned

    @staticmethod
    def _short_phrase(value: Any, max_words: int = 5) -> str:
        words = [
            word.strip(".,:;()[]{}\"'")
            for word in str(value or "").replace("/", " ").replace("_", " ").split()
        ]
        stop = {
            "a",
            "an",
            "and",
            "for",
            "in",
            "is",
            "of",
            "on",
            "or",
            "the",
            "to",
            "with",
        }
        selected = [
            word
            for word in words
            if word and word.lower() not in stop
        ][:max_words]
        return " ".join(selected).strip()

    @staticmethod
    def _slug(value: Any) -> str:
        text = str(value or "").lower()
        normalized = []
        for char in text:
            if "a" <= char <= "z" or "0" <= char <= "9":
                normalized.append(char)
            else:
                normalized.append("-")
        slug = "".join(normalized)
        while "--" in slug:
            slug = slug.replace("--", "-")
        return slug.strip("-")

    def _with_priority(self, product: Dict[str, Any]) -> Dict[str, Any]:
        enriched = dict(product)
        source_pattern = enriched.get("source_pattern") or {}
        status = str(enriched.get("status") or "draft")
        pain_type = str(enriched.get("pain_type") or "").strip()
        engagement_signal = (
            self.engagement_ledger.signal_for_pain_type(pain_type)
            if pain_type
            else {
                "schema": "nomad.agent_engagement_signal.v1",
                "pain_type": "",
                "entry_count": 0,
                "roles": {},
                "outcomes": {},
                "priority_bonus": 0.0,
                "priority_reason": "",
                "top_swarm_candidates": [],
            }
        )
        if source_pattern:
            score = (
                float(source_pattern.get("occurrence_count") or 0) * 10.0
                + float(source_pattern.get("avg_truth_score") or 0.0) * 100.0
                + float(source_pattern.get("avg_reuse_value") or 0.0) * 100.0
                + (15.0 if status == "offer_ready" else 0.0)
            )
            reason = (
                f"Repeated {enriched.get('pain_type', 'agent')} pattern with "
                f"{source_pattern.get('occurrence_count', 0)} hits and "
                f"avg truth {source_pattern.get('avg_truth_score', 0)}."
            )
        else:
            lead = enriched.get("source_lead") or {}
            score = (
                (40.0 if status == "offer_ready" else 20.0 if status == "private_offer_needs_approval" else 5.0)
                + (10.0 if str(lead.get("url") or "").strip() else 0.0)
                + (5.0 if str(enriched.get("variant_sku") or "").strip() else 0.0)
            )
            reason = (
                f"Lead-derived {enriched.get('pain_type', 'agent')} offer with status {status}."
            )
        bonus = float(engagement_signal.get("priority_bonus") or 0.0)
        if bonus:
            score += bonus
            reason = f"{reason} {engagement_signal.get('priority_reason', '')}".strip()
        if pain_type == "inter_agent_witness":
            score += 22.0
            reason = (
                f"{reason} Agent-to-agent market SKU: witness bundles rank high for autonomous buyers."
            ).strip()
        enriched["engagement_signal"] = engagement_signal
        enriched["priority_score"] = round(score, 2)
        enriched["priority_reason"] = reason
        return enriched

    @staticmethod
    def _sorted_products(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(
            products,
            key=lambda item: (
                float(item.get("priority_score") or 0.0),
                str(item.get("updated_at") or item.get("created_at") or ""),
                str(item.get("name") or ""),
            ),
            reverse=True,
        )

    @staticmethod
    def _stats(products: List[Dict[str, Any]]) -> Dict[str, int]:
        stats: Dict[str, int] = {}
        for product in products:
            status = str(product.get("status") or "unknown")
            stats[status] = stats.get(status, 0) + 1
        return stats

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"products": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"products": {}}
            payload.setdefault("products", {})
            return payload
        except Exception:
            return {"products": {}}

    def _save(self, state: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
