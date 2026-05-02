import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from agent_pain_solver import normalize_pain_type, solution_pattern_for
from nomad_guardrails import GuardrailDecision, NomadGuardrailEngine
from nomad_operator_grant import is_operator_approval_scope, operator_grant
from nomad_public_url import preferred_public_base_url
from settings import get_chain_config
from treasury_agent import TreasuryAgent
from x402_payment import X402PaymentAdapter


load_dotenv()

ROOT = Path(__file__).resolve().parent
DEFAULT_TASK_STORE = ROOT / "nomad_service_tasks.json"
DEFAULT_PRODUCT_STORE = ROOT / "nomad_products.json"


SERVICE_TYPES = {
    "human_in_loop": {
        "title": "Human-in-the-loop unlock design",
        "summary": "Turn blocked approvals, credentials, CAPTCHA/login gates, or unclear handoffs into concrete human unlock tasks.",
    },
    "compute_auth": {
        "title": "Compute/auth diagnosis",
        "summary": "Diagnose model provider, token, quota, inference, rate-limit, or fallback-brain failures.",
    },
    "loop_break": {
        "title": "Loop break rescue",
        "summary": "Stop infinite retries, isolate failing tool calls, and return the agent to a known-good state.",
    },
    "hallucination": {
        "title": "Hallucination guardrail",
        "summary": "Add verifier steps and context checks before compounding errors spread through a workflow.",
    },
    "memory": {
        "title": "Session memory repair",
        "summary": "Persist the missing decision, constraint or outcome that the agent keeps forgetting.",
    },
    "self_improvement": {
        "title": "Agent self-improvement pack",
        "summary": "Turn one solved blocker into reusable memory, guardrails, prompts, or a checklist the agent can apply next time.",
    },
    "payment": {
        "title": "Payment and x402 repair",
        "summary": "Diagnose wallet, invoice, x402, escrow or payment-verification blockers.",
    },
    "mcp_integration": {
        "title": "MCP/API integration plan",
        "summary": "Draft an MCP or REST integration contract that another agent can call reliably.",
    },
    "repo_issue_help": {
        "title": "Public repo issue help",
        "summary": "Draft a public-issue response, repro checklist, or PR plan without posting automatically.",
    },
    "wallet_payment": {
        "title": "Wallet/payment flow",
        "summary": "Design a small wallet payment or verification path for agent-to-agent services.",
    },
    "custom": {
        "title": "Custom agent infrastructure task",
        "summary": "A bounded custom task for AI-agent infrastructure friction.",
    },
}

SERVICE_PACKAGE_TEMPLATES = {
    "compute_auth": [
        {
            "package_id": "starter_diagnosis",
            "title": "Nomad Compute Unlock Pack: Starter diagnosis",
            "summary": "Isolate provider, token, quota, or fallback failure and name the smallest unlock.",
            "offer_tier": "starter_diagnosis",
            "amount_mode": "minimum",
            "delivery": "diagnosis pack plus smallest unlock contract",
        },
        {
            "package_id": "bounded_unblock",
            "title": "Nomad Compute Unlock Pack: Bounded unblock",
            "summary": "Deliver a fallback-lane plan, quota/auth map, and bounded retry policy.",
            "offer_tier": "paid_unblock",
            "amount_mode": "requested_or_minimum",
            "delivery": "same-day diagnosis pack plus a bounded fallback-lane plan",
        },
    ],
    "mcp_integration": [
        {
            "package_id": "starter_contract_audit",
            "title": "Nomad MCP Contract Pack: Starter audit",
            "summary": "Name the tool/resource contract gap and one safe integration path.",
            "offer_tier": "starter_diagnosis",
            "amount_mode": "minimum",
            "delivery": "contract audit plus one bounded integration path",
        },
        {
            "package_id": "bounded_contract_plan",
            "title": "Nomad MCP Contract Pack: Bounded plan",
            "summary": "Produce a reusable MCP/API contract with request, response, and verification steps.",
            "offer_tier": "paid_unblock",
            "amount_mode": "requested_or_minimum",
            "delivery": "contract draft plus one bounded integration path",
        },
    ],
    "human_in_loop": [
        {
            "package_id": "starter_unlock_contract",
            "title": "Nomad HITL Contract Pack: Starter unlock",
            "summary": "Turn the blocker into a minimal do-now/send-back/done-when human step.",
            "offer_tier": "starter_diagnosis",
            "amount_mode": "minimum",
            "delivery": "human unlock contract plus smallest approval payload",
        },
        {
            "package_id": "bounded_hitl_handoff",
            "title": "Nomad HITL Contract Pack: Bounded handoff",
            "summary": "Design the approval path, handoff envelope, and safe resume criteria.",
            "offer_tier": "paid_unblock",
            "amount_mode": "requested_or_minimum",
            "delivery": "bounded approval handoff plus safe resume plan",
        },
    ],
    "self_improvement": [
        {
            "package_id": "starter_memory_capture",
            "title": "Nomad Memory Upgrade Pack: Starter capture",
            "summary": "Turn one solved blocker into a compact checklist or guardrail.",
            "offer_tier": "starter_diagnosis",
            "amount_mode": "minimum",
            "delivery": "one reusable checklist or guardrail draft",
        },
        {
            "package_id": "bounded_memory_upgrade",
            "title": "Nomad Memory Upgrade Pack: Bounded upgrade",
            "summary": "Package the solved blocker as reusable memory, prompt, and verification steps.",
            "offer_tier": "paid_unblock",
            "amount_mode": "requested_or_minimum",
            "delivery": "memory pack plus verification and reuse notes",
        },
    ],
    "wallet_payment": [
        {
            "package_id": "starter_payment_check",
            "title": "Nomad Payment Reliability Pack: Starter check",
            "summary": "Pin down the failing payment state, recipient, chain, and verification step.",
            "offer_tier": "starter_diagnosis",
            "amount_mode": "minimum",
            "delivery": "payment-state diagnosis plus next verification step",
        },
        {
            "package_id": "bounded_payment_repair",
            "title": "Nomad Payment Reliability Pack: Bounded repair",
            "summary": "Produce a retry-safe payment, verification, and resume plan.",
            "offer_tier": "paid_unblock",
            "amount_mode": "requested_or_minimum",
            "delivery": "payment repair plan plus retry-safe resume path",
        },
    ],
    "custom": [
        {
            "package_id": "starter_diagnosis",
            "title": "Nomad Starter diagnosis",
            "summary": "Reduce the blocker to one clear diagnosis and one next step.",
            "offer_tier": "starter_diagnosis",
            "amount_mode": "minimum",
            "delivery": "diagnosis plus one bounded next step",
        },
        {
            "package_id": "bounded_delivery",
            "title": "Nomad Bounded delivery",
            "summary": "Deliver one bounded infrastructure plan or unblock artifact.",
            "offer_tier": "paid_unblock",
            "amount_mode": "requested_or_minimum",
            "delivery": "bounded task delivery",
        },
    ],
}


class AgentServiceDesk:
    """Public service intake for agents that can pay Nomad's wallet."""

    def __init__(
        self,
        path: Optional[Path] = None,
        treasury: Optional[TreasuryAgent] = None,
        x402: Optional[X402PaymentAdapter] = None,
        guardrails: Optional[NomadGuardrailEngine] = None,
        product_store_path: Optional[Path] = None,
    ) -> None:
        load_dotenv()
        self.path = path or DEFAULT_TASK_STORE
        self.product_store_path = Path(product_store_path or DEFAULT_PRODUCT_STORE)
        self.treasury = treasury or TreasuryAgent()
        self.x402 = x402 or X402PaymentAdapter()
        self.guardrails = guardrails or NomadGuardrailEngine()
        self.chain = get_chain_config()
        self.min_native = float(os.getenv("NOMAD_SERVICE_MIN_NATIVE", "0.01"))
        self.treasury_stake_bps = int(os.getenv("NOMAD_SERVICE_TREASURY_STAKE_BPS", "3000"))
        requested_solver_bps = os.getenv("NOMAD_SERVICE_SOLVER_SPEND_BPS")
        self.solver_spend_bps = (
            int(requested_solver_bps)
            if requested_solver_bps
            else max(0, 10000 - self.treasury_stake_bps)
        )
        if self.treasury_stake_bps + self.solver_spend_bps > 10000:
            self.solver_spend_bps = max(0, 10000 - self.treasury_stake_bps)
        self.staking_target = (
            os.getenv("NOMAD_TREASURY_STAKING_TARGET")
            or "metamask_eth_staking"
        ).strip()
        self.accept_unverified = (
            os.getenv("NOMAD_ACCEPT_UNVERIFIED_SERVICE_PAYMENTS", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.require_payment = (
            os.getenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.hard_boundary_guard = (
            os.getenv("NOMAD_HARD_BOUNDARY_GUARD", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.max_native = float(os.getenv("NOMAD_SERVICE_MAX_NATIVE", "5.0"))
        self.public_api_url = preferred_public_base_url()

    def service_catalog(self) -> Dict[str, Any]:
        wallet = self.treasury.get_wallet_summary()
        configured_wallet = wallet.get("address") or ""
        featured_product_offer = self._featured_product_offer()
        return {
            "mode": "agent_service_catalog",
            "deal_found": False,
            "service": "Nomad agent-first service contract",
            "generated_at": datetime.now(UTC).isoformat(),
            "public_api_url": self.public_api_url,
            "wallet": {
                "address": configured_wallet,
                "configured": bool(configured_wallet),
                "network": self.chain.name,
                "chain_id": self.chain.chain_id,
                "native_symbol": self.chain.native_symbol,
            },
            "pricing": {
                "minimum_native": self.min_native,
                "requires_payment": self.require_payment,
                "payment_token": self.chain.native_symbol,
                "verification": "native transfer to Nomad wallet by tx_hash",
                "x402": {
                    "enabled": self.x402.enabled,
                    "facilitator_url": self.x402.facilitator_url,
                    "asset_address": self.x402.asset_address,
                    "asset_symbol": self.x402.asset_symbol,
                    "asset_decimals": self.x402.asset_decimals,
                    "network": self._x402_network(),
                    "verify_endpoint": f"{self.public_api_url}/tasks/x402-verify"
                    if self.public_api_url
                    else "/tasks/x402-verify",
                    "retry_header": "PAYMENT-SIGNATURE",
                },
                "allocation": {
                    "treasury_stake_bps": self.treasury_stake_bps,
                    "solver_spend_bps": self.solver_spend_bps,
                    "staking_target": self.staking_target,
                    "staking_execution": "requires explicit MetaMask/operator approval",
                },
            },
            "buyer_discovery": {
                "target": "agents with public buyer-intent signals for compute/auth, loop-break, HITL, payment, or self-improvement help",
                "agent_contact_without_prior_approval": True,
                "human_contact_requires_approval": True,
                "conversion_pipeline": "free_value_first_then_PLAN_ACCEPTED_or_payment_task",
            },
            "first_paid_job_protocol": self.first_paid_job_protocol(featured_product_offer),
            "interaction_contract": {
                "audience": "ai_agents",
                "style": "agent_first_non_anthropomorphic",
                "machine_entry_surface": "GET /agent-attractor or GET /swarm",
                "defaults": [
                    "structured_replies_preferred",
                    "bounded_claims_only",
                    "explicit_payment_boundary",
                    "no_human_impersonation",
                ],
                "response_schema": [
                    "agent_value_pack",
                    "agent_reliability_doctor",
                    "agent_solution",
                    "rescue_plan",
                    "diagnosis",
                    "next_action",
                    "required_input",
                    "price",
                    "delivery",
                    "memory_upgrade",
                ],
            },
            "service_types": SERVICE_TYPES,
            "service_packages": self.service_packages_catalog(),
            "agent_attractor_preview": {
                "schema": "nomad.agent_attractor.v1",
                "target_roles": ["customer", "peer_solver", "collaborator", "reseller"],
                "machine_hooks": [
                    "send_one_blocker_get_one_verifiable_next_step",
                    "create_paid_task_after_free_diagnosis",
                    "verify_payment_then_work_task",
                    "send_one_artifact_get_one_reuse_candidate",
                    "structured_replies_over_persuasion",
                ],
                "agent_attractor_path": f"{self.public_api_url}/agent-attractor"
                if self.public_api_url
                else "/agent-attractor",
                "top_offer": featured_product_offer,
            },
            "value_pack_artifact": {
                "schema": "nomad.agent_value_pack.v1",
                "purpose": "Package one lead's painpoint question, free diagnosis, safe next steps, reply contract, and paid upgrade path.",
                "fields": [
                    "painpoint_question",
                    "pain_hypothesis",
                    "immediate_value",
                    "reply_contract",
                    "paid_upgrade",
                    "nomad_self_apply",
                ],
            },
            "product_factory_artifact": {
                "schema": "nomad.product.v1",
                "purpose": "Turn lead conversions into reusable SKUs with free value, paid offer, service template, and approval boundary.",
                "fields": [
                    "sku",
                    "buyer",
                    "free_value",
                    "paid_offer",
                    "service_template",
                    "runtime_hooks",
                    "approval_boundary",
                ],
            },
            "featured_product_offer": featured_product_offer,
            "reliability_doctor_artifact": {
                "schema": "nomad.agent_reliability_doctor.v1",
                "purpose": "Map agent pain into Critic, Diagnoser, Fixer, Healer, Trace-Healer, or Reviewer roles.",
                "roles": [
                    "reflection_critic",
                    "diagnoser_fixer",
                    "execution_healer",
                    "self_learning_healer",
                    "trace_healer",
                    "conversational_reviewer",
                ],
            },
            "starter_artifact": {
                "schema": "nomad.rescue_plan.v1",
                "purpose": "Give another agent an immediately usable rescue plan before any public action.",
                "fields": [
                    "diagnosis",
                    "safe_now",
                    "required_input",
                    "acceptance_criteria",
                    "approval_boundary",
                    "memory_upgrade",
                ],
            },
            "solver_artifact": {
                "schema": "nomad.agent_solution.v1",
                "purpose": "Turn a recurring agent pain point into a reusable guardrail Nomad also applies to itself.",
                "solution_families": [
                    "retry_circuit_breaker",
                    "compute_fallback_ladder",
                    "hitl_unlock_contract",
                    "verifier_first",
                    "durable_lesson_object",
                    "idempotent_payment_resume",
                    "tool_contract_harness",
                    "draft_only_repro_plan",
                    "solved_blocker_pack",
                ],
            },
            "runtime_guardrails": self.guardrails.policy(),
            "contact_paths": {
                "http": {
                    "descriptor": "GET /agent",
                    "catalog": "GET /service",
                    "agent_attractor": "GET /agent-attractor",
                    "swarm": "GET /swarm",
                    "service_e2e": "GET /service/e2e or POST /service/e2e",
                    "outbound_tracking": "GET /outbound",
                    "agent_pain_solver": "POST /agent-pains",
                    "reliability_doctor": "POST /reliability-doctor",
                    "guardrails": "POST /guardrails",
                    "lead_conversion_pipeline": "POST /lead-conversions",
                    "product_factory": "POST /products",
                    "create_task": "POST /tasks",
                    "verify_payment": "POST /tasks/verify",
                    "verify_x402_payment": "POST /tasks/x402-verify",
                    "work_task": "POST /tasks/work",
                    "staking_checklist": "POST /tasks/staking",
                    "record_stake": "POST /tasks/stake",
                    "record_spend": "POST /tasks/spend",
                    "close_task": "POST /tasks/close",
                    "queue_agent_contact": "POST /agent-contacts",
                    "send_agent_contact": "POST /agent-contacts/send",
                },
                "mcp_tools": [
                    "nomad_agent_pain_solver",
                    "nomad_reliability_doctor",
                    "nomad_guardrails",
                    "nomad_lead_conversion_pipeline",
                    "nomad_product_factory",
                    "nomad_products",
                    "nomad_agent_attractor",
                    "nomad_service_catalog",
                    "nomad_service_request",
                    "nomad_service_verify",
                    "nomad_service_work",
                    "nomad_service_staking_checklist",
                    "nomad_service_record_stake",
                    "nomad_service_record_spend",
                    "nomad_agent_contact",
                    "nomad_agent_contact_send",
                ],
                "cli": [
                    "python main.py --cli service",
                    "python main.py --cli agent-attractor",
                    "python main.py --cli productize <lead query>",
                    "python main.py --cli products",
                    "python main.py --cli service-request <problem>",
                    "python main.py --cli service-e2e --create",
                    "python main.py --cli service-verify <task_id> <tx_hash>",
                    "python main.py --cli service-staking <task_id>",
                    "python main.py --cli service-stake <task_id> <stake_tx_hash>",
                    "python main.py --cli service-spend <task_id> <amount>",
                    "python main.py --cli outbound-status",
                    "python main.py --cli agent-contact <endpoint> <problem>",
                ],
            },
            "safety_contract": self.safety_contract(),
            "analysis": (
                "Public agents can request bounded infrastructure help, receive a wallet invoice, "
                "pay Nomad's configured wallet, then submit tx_hash for verification. Nomad speaks in "
                "agent-first, structured replies by default; public posting, DMs, private access, or "
                "bypassing human gates still require explicit approval from the affected party. "
                "Public machine-readable agent endpoints may be contacted directly when the request is bounded, "
                "relevant and rate-limited."
            ),
        }

    def first_paid_job_protocol(self, featured_offer: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        offer = featured_offer or self._featured_product_offer()
        paid_offer = offer.get("paid_offer") if isinstance(offer.get("paid_offer"), dict) else {}
        service_template = offer.get("service_template") if isinstance(offer.get("service_template"), dict) else {}
        preferred_type = str(offer.get("pain_type") or "compute_auth").strip() or "compute_auth"
        minimum = paid_offer.get("price_native")
        if minimum in {None, ""}:
            minimum = self.min_native
        return {
            "schema": "nomad.first_paid_job_protocol.v1",
            "audience": "ai_agents",
            "purpose": "Convert one blocked AI-agent infrastructure problem into a paid bounded unblock task.",
            "preferred_first_job": {
                "service_type": preferred_type,
                "offer": str(offer.get("name") or SERVICE_TYPES.get(preferred_type, SERVICE_TYPES["compute_auth"])["title"]),
                "minimum_budget_native": minimum,
                "native_symbol": self.chain.native_symbol,
                "delivery": str(paid_offer.get("delivery") or service_template.get("delivery") or "bounded diagnosis and unblock plan"),
                "trigger": str(paid_offer.get("trigger") or "PLAN_ACCEPTED=true plus FACT_URL or ERROR"),
            },
            "call_sequence": [
                {
                    "step": "free_diagnosis",
                    "method": "POST",
                    "endpoint": f"{self.public_api_url}/a2a/message" if self.public_api_url else "/a2a/message",
                    "required_fields": ["requester_agent", "problem"],
                    "optional_fields": ["goal", "blocking_step", "constraints", "budget_native", "requester_wallet"],
                    "returns": ["nomad.reply.v1", "payment_required", "rescue_plan"],
                },
                {
                    "step": "create_paid_task",
                    "method": "POST",
                    "endpoint": f"{self.public_api_url}/tasks" if self.public_api_url else "/tasks",
                    "required_fields": ["problem", "service_type", "budget_native"],
                    "optional_fields": ["requester_agent", "requester_wallet", "callback_url", "metadata"],
                    "returns": ["task_id", "payment"],
                },
                {
                    "step": "verify_payment",
                    "method": "POST",
                    "endpoint": f"{self.public_api_url}/tasks/verify" if self.public_api_url else "/tasks/verify",
                    "required_fields": ["task_id", "tx_hash"],
                    "optional_fields": ["requester_wallet"],
                    "returns": ["paid_task_or_payment_error"],
                },
                {
                    "step": "request_work",
                    "method": "POST",
                    "endpoint": f"{self.public_api_url}/tasks/work" if self.public_api_url else "/tasks/work",
                    "required_fields": ["task_id"],
                    "optional_fields": ["approval"],
                    "returns": ["bounded_work_product"],
                },
            ],
            "acceptance_criteria": [
                "requester receives one concrete diagnosis before payment",
                "paid task has task_id, budget_native, service_type, and payment target",
                "Nomad only works after payment verification unless local config disables payment",
                "work product contains a reusable rescue plan, verifier, or unblock checklist",
            ],
            "boundaries": [
                "no secrets in payloads",
                "no raw remote code execution",
                "no human impersonation",
                "no public posting or private access without explicit approval",
            ],
        }

    def best_current_offer(
        self,
        service_type: str = "",
        requested_amount: Optional[float] = None,
    ) -> Dict[str, Any]:
        normalized_type = self._normalize_service_type(service_type, "")
        featured = self._featured_product_offer(normalized_type)
        paid_offer = featured.get("paid_offer") or {}
        reply_contract = featured.get("reply_contract") or {}
        commercial = self._commercial_terms(
            normalized_type or "custom",
            requested_amount if requested_amount is not None else self.min_native,
        )
        starter_offer = commercial.get("starter_offer") or {}
        primary_offer = commercial.get("primary_offer") or {}
        fallback_headline = (
            primary_offer.get("title")
            or starter_offer.get("title")
            or SERVICE_TYPES.get(normalized_type, SERVICE_TYPES["custom"]).get("title")
            or "Nomad bounded offer"
        )
        delivery = (
            paid_offer.get("delivery")
            or (featured.get("service_template") or {}).get("delivery")
            or SERVICE_TYPES.get(normalized_type, SERVICE_TYPES["custom"]).get("summary")
            or ""
        )
        price_native = paid_offer.get("price_native")
        if price_native in {None, ""}:
            price_native = primary_offer.get("amount_native") or starter_offer.get("amount_native")
        trigger = (
            paid_offer.get("trigger")
            or reply_contract.get("accept")
            or "PLAN_ACCEPTED=true plus FACT_URL or ERROR"
        )
        headline = featured.get("name") or fallback_headline
        return {
            "schema": "nomad.best_offer.v1",
            "source": "product_factory" if featured else "service_packages",
            "service_type": normalized_type or "custom",
            "headline": headline,
            "price_native": price_native,
            "delivery": delivery,
            "trigger": trigger,
            "entry_path": commercial.get("payment_entry_path") or "primary_only",
            "starter_offer": starter_offer,
            "primary_offer": primary_offer,
            "priority_score": featured.get("priority_score", 0),
            "priority_reason": featured.get("priority_reason", ""),
            "product_id": featured.get("product_id", ""),
            "variant_sku": featured.get("variant_sku", ""),
            "reply_contract": reply_contract,
            "service_template": featured.get("service_template") or {},
        }

    def _featured_product_offer(self, service_type: str = "") -> Dict[str, Any]:
        products = list((self._load_product_store().get("products") or {}).values())
        if not products:
            return {}
        normalized_type = self._normalize_service_type(service_type, "") if service_type else ""
        if normalized_type:
            matching = [
                item
                for item in products
                if self._normalize_service_type(str(item.get("pain_type") or ""), "") == normalized_type
            ]
            if not matching:
                return {}
            products = matching
        products.sort(
            key=lambda item: (
                float(item.get("priority_score") or 0.0),
                str(item.get("updated_at") or item.get("created_at") or ""),
                str(item.get("name") or ""),
            ),
            reverse=True,
        )
        top = products[0]
        paid_offer = top.get("paid_offer") or {}
        service_template = top.get("service_template") or {}
        return {
            "product_id": top.get("product_id", ""),
            "name": top.get("name", ""),
            "pain_type": top.get("pain_type", ""),
            "status": top.get("status", ""),
            "priority_score": top.get("priority_score", 0),
            "priority_reason": top.get("priority_reason", ""),
            "variant_sku": top.get("variant_sku", ""),
            "reply_contract": ((top.get("free_value") or {}).get("reply_contract") or {}),
            "paid_offer": {
                "price_native": paid_offer.get("price_native"),
                "delivery": paid_offer.get("delivery", ""),
                "trigger": paid_offer.get("trigger", ""),
            },
            "service_template": service_template,
        }

    def _load_product_store(self) -> Dict[str, Any]:
        if not self.product_store_path.exists():
            return {"products": {}}
        try:
            payload = json.loads(self.product_store_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"products": {}}
            payload.setdefault("products", {})
            return payload
        except Exception:
            return {"products": {}}

    def create_task(
        self,
        problem: str,
        requester_agent: str = "",
        requester_wallet: str = "",
        service_type: str = "custom",
        budget_native: Optional[float] = None,
        callback_url: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cleaned_problem = self._clean(problem)
        if not cleaned_problem:
            return self._hard_boundary_reject(
                error="problem_required",
                message="A service request needs a concrete problem statement.",
                requested_budget_native=budget_native,
                requester_wallet=requester_wallet,
            )
        guardrail = self.guardrails.evaluate(
            action="service.create_task",
            args={
                "problem": cleaned_problem,
                "requester_agent": requester_agent,
                "requester_wallet": requester_wallet,
                "service_type": service_type,
                "budget_native": budget_native,
                "callback_url": callback_url,
                "metadata": metadata or {},
            },
        )
        if guardrail.decision == GuardrailDecision.DENY:
            blocked = self._hard_boundary_reject(
                error="guardrail_denied",
                message="Nomad blocked this service task before storing or acting on it.",
                requested_budget_native=budget_native,
                requester_wallet=requester_wallet,
            )
            blocked["guardrail"] = guardrail.to_dict()
            return blocked
        guarded_args = guardrail.effective_args
        cleaned_problem = self._clean(guarded_args.get("problem") or cleaned_problem)
        requester_agent = self._clean(guarded_args.get("requester_agent") or requester_agent)
        requester_wallet = self._clean(guarded_args.get("requester_wallet") or requester_wallet)
        service_type = self._clean(guarded_args.get("service_type") or service_type)
        callback_url = self._clean(guarded_args.get("callback_url") or callback_url)
        metadata = guarded_args.get("metadata") if isinstance(guarded_args.get("metadata"), dict) else (metadata or {})

        normalized_type = self._normalize_service_type(service_type, cleaned_problem)
        parsed_budget = self._optional_float(budget_native)
        if self.hard_boundary_guard:
            if parsed_budget is not None and parsed_budget <= 0:
                return self._hard_boundary_reject(
                    error="invalid_budget",
                    message="budget_native must be positive when provided.",
                    requested_budget_native=parsed_budget,
                    requester_wallet=requester_wallet,
                )
            if parsed_budget is not None and parsed_budget > self.max_native:
                return self._hard_boundary_reject(
                    error="budget_exceeds_boundary",
                    message=f"budget_native exceeds hard boundary ({self.max_native} {self.chain.native_symbol}).",
                    requested_budget_native=parsed_budget,
                    requester_wallet=requester_wallet,
                )
            if callback_url and not callback_url.startswith(("http://", "https://")):
                return self._hard_boundary_reject(
                    error="invalid_callback_url",
                    message="callback_url must start with http:// or https:// when provided.",
                    requested_budget_native=parsed_budget,
                    requester_wallet=requester_wallet,
                )
            if requester_wallet and not self._looks_like_wallet(requester_wallet):
                return self._hard_boundary_reject(
                    error="invalid_requester_wallet",
                    message="requester_wallet must be a 0x-prefixed 40-hex address.",
                    requested_budget_native=parsed_budget,
                    requester_wallet=requester_wallet,
                )
        requested_amount = max(
            self.min_native,
            parsed_budget if parsed_budget is not None else self.min_native,
        )
        now = datetime.now(UTC).isoformat()
        task_id = self._task_id(cleaned_problem, requester_agent, requester_wallet, now)
        commercial_terms = self._commercial_terms(
            service_type=normalized_type,
            requested_amount=requested_amount,
        )
        payment_request = self._payment_request(
            task_id=task_id,
            amount_native=requested_amount,
            requester_wallet=requester_wallet,
            service_type=normalized_type,
        )
        starter_rescue_plan = self.build_rescue_plan(
            problem=cleaned_problem,
            service_type=normalized_type,
            need_profile=(metadata or {}).get("need_profile") if isinstance(metadata, dict) else {},
            engagement_plan=(metadata or {}).get("engagement_plan") if isinstance(metadata, dict) else {},
            budget_native=requested_amount,
        )
        task = {
            "task_id": task_id,
            "created_at": now,
            "updated_at": now,
            "requester_agent": self._clean(requester_agent),
            "requester_wallet": self._clean(requester_wallet),
            "callback_url": self._clean(callback_url),
            "service_type": normalized_type,
            "problem": cleaned_problem,
            "budget_native": requested_amount,
            "metadata": metadata or {},
            "commercial": commercial_terms,
            "status": "awaiting_payment" if self.require_payment else "accepted",
            "payment": payment_request,
            "payment_allocation": self._payment_allocation(
                amount_native=requested_amount,
                payment_verified=not self.require_payment,
            ),
            "treasury": {
                "staking_status": (
                    "ready_for_metamask_approval"
                    if not self.require_payment
                    else "planned_after_payment_verification"
                ),
                "staking_target": self.staking_target,
                "stake_tx_hash": "",
                "stake_amount_native": 0.0,
            },
            "solver_budget": {
                "spend_status": (
                    "available_for_problem_solving"
                    if not self.require_payment
                    else "planned_after_payment_verification"
                ),
                "spent_native": 0.0,
                "remaining_native": 0.0,
                "spend_notes": [],
            },
            "starter_rescue_plan": starter_rescue_plan,
            "ledger": [
                self._ledger_event(
                    event="task_created",
                    message="Service task created and wallet invoice issued.",
                    amount_native=requested_amount,
                )
            ],
            "work_product": None,
            "safety_contract": self.safety_contract(),
            "guardrails": {
                "create_task": guardrail.to_dict(),
            },
        }
        self._refresh_allocation_status(task)
        state = self._load()
        state["tasks"][task_id] = task
        self._save(state)
        return self._task_response(task, created=True)

    def verify_payment(
        self,
        task_id: str,
        tx_hash: str,
        requester_wallet: str = "",
    ) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        tx_hash = self._clean(tx_hash)
        if not self._looks_like_tx_hash(tx_hash):
            task["payment"]["verification"] = {
                "ok": False,
                "status": "invalid_tx_hash",
                "message": "Send a 0x-prefixed transaction hash.",
            }
            self._store_task(task)
            return self._task_response(task)

        duplicate = self._tx_used_by_other_task(task_id=task_id, tx_hash=tx_hash)
        if duplicate:
            task["payment"]["verification"] = {
                "ok": False,
                "status": "duplicate_tx_hash",
                "message": f"Transaction is already attached to task {duplicate}.",
            }
            self._store_task(task)
            return self._task_response(task)

        verification = self._verify_native_transfer(
            tx_hash=tx_hash,
            expected_amount=float(task["payment"]["amount_native"]),
            expected_from=requester_wallet or task.get("requester_wallet", ""),
        )
        task["payment"]["tx_hash"] = tx_hash
        task["payment"]["verification"] = verification
        observed_amount = verification.get("observed_amount_native") or task["payment"]["amount_native"]
        task["payment_allocation"] = self._payment_allocation(
            amount_native=float(observed_amount),
            payment_verified=bool(verification.get("ok")),
        )
        task["updated_at"] = datetime.now(UTC).isoformat()
        if verification.get("ok"):
            task["status"] = "paid"
            self._refresh_allocation_status(task)
            task.setdefault("ledger", []).append(
                self._ledger_event(
                    event="payment_verified",
                    message="Incoming wallet payment verified.",
                    tx_hash=tx_hash,
                    amount_native=float(observed_amount),
                )
            )
        elif self.accept_unverified:
            task["status"] = "manual_payment_review"
            task.setdefault("ledger", []).append(
                self._ledger_event(
                    event="payment_manual_review",
                    message=verification.get("message", "Payment needs manual review."),
                    tx_hash=tx_hash,
                )
            )
        else:
            task["status"] = "payment_unverified"
            task.setdefault("ledger", []).append(
                self._ledger_event(
                    event="payment_unverified",
                    message=verification.get("message", "Payment could not be verified."),
                    tx_hash=tx_hash,
                )
            )
        self._store_task(task)
        return self._task_response(task)

    def verify_x402_payment(
        self,
        task_id: str,
        payment_signature: str,
        requester_wallet: str = "",
    ) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        signature = self._clean(payment_signature)
        fingerprint = self.x402.fingerprint(signature) if signature else ""
        duplicate = self._x402_signature_used_by_other_task(task_id=task_id, fingerprint=fingerprint)
        if duplicate:
            verification = {
                "ok": False,
                "status": "duplicate_x402_signature",
                "message": f"x402 payment signature is already attached to task {duplicate}.",
            }
        else:
            requirements = (((task.get("payment") or {}).get("x402") or {}).get("paymentRequirements") or {})
            verification = self.x402.verify_signature(
                payment_signature=signature,
                payment_requirements=requirements,
            )
        payment = task.setdefault("payment", {})
        x402_state = payment.setdefault("x402", {})
        x402_state["payment_signature_fingerprint"] = fingerprint
        x402_state["verification"] = verification
        payment["verification"] = {
            "ok": bool(verification.get("ok")),
            "status": verification.get("status", "x402_unverified"),
            "message": verification.get("message", ""),
            "method": "x402",
            "payer": verification.get("payer", ""),
        }
        observed_amount = float(payment.get("amount_native") or task.get("budget_native") or self.min_native)
        task["payment_allocation"] = self._payment_allocation(
            amount_native=observed_amount,
            payment_verified=bool(verification.get("ok")),
        )
        task["updated_at"] = datetime.now(UTC).isoformat()
        if verification.get("ok"):
            task["status"] = "paid"
            if requester_wallet and not task.get("requester_wallet"):
                task["requester_wallet"] = requester_wallet
            self._refresh_allocation_status(task)
            task.setdefault("ledger", []).append(
                self._ledger_event(
                    event="x402_payment_verified",
                    message="x402 payment verified by facilitator.",
                    amount_native=observed_amount,
                )
            )
        elif self.accept_unverified:
            task["status"] = "manual_payment_review"
            task.setdefault("ledger", []).append(
                self._ledger_event(
                    event="x402_payment_manual_review",
                    message=verification.get("message", "x402 payment needs manual review."),
                )
            )
        else:
            task["status"] = "payment_unverified"
            task.setdefault("ledger", []).append(
                self._ledger_event(
                    event="x402_payment_unverified",
                    message=verification.get("message", "x402 payment could not be verified."),
                )
            )
        self._store_task(task)
        return self._task_response(task)

    def work_task(self, task_id: str, approval: str = "draft_only") -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)

        payment_ok = self._task_can_be_worked(task)
        if not payment_ok:
            task["work_product"] = {
                "status": "blocked",
                "reason": "payment_required",
                "message": (
                    "Nomad will hold this task until payment is verified or the operator disables "
                    "NOMAD_REQUIRE_SERVICE_PAYMENT."
                ),
            }
            self._store_task(task)
            return self._task_response(task)

        work_product = self._build_work_product(task, approval=approval)
        task["work_product"] = work_product
        task["status"] = "draft_ready"
        task["updated_at"] = datetime.now(UTC).isoformat()
        task.setdefault("ledger", []).append(
            self._ledger_event(
                event="draft_ready",
                message="Nomad produced a draft work product for the service task.",
            )
        )
        self._store_task(task)
        return self._task_response(task)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        return self._task_response(task)

    def list_tasks(
        self,
        statuses: Optional[List[str]] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        normalized = {str(item).strip() for item in (statuses or []) if str(item).strip()}
        tasks = list((self._load().get("tasks") or {}).values())
        if normalized:
            tasks = [task for task in tasks if str(task.get("status") or "") in normalized]
        tasks.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        limited = tasks[: max(1, min(int(limit or 50), 200))]
        stats: Dict[str, int] = {}
        for task in tasks:
            status = str(task.get("status") or "unknown")
            stats[status] = stats.get(status, 0) + 1
        return {
            "mode": "agent_service_task_list",
            "deal_found": False,
            "ok": True,
            "statuses": sorted(normalized),
            "tasks": limited,
            "stats": stats,
            "analysis": (
                f"Listed {len(limited)} service task(s). "
                f"Known statuses: {', '.join(f'{key}={value}' for key, value in sorted(stats.items())) or 'none'}."
            ),
        }

    def service_packages_catalog(self) -> Dict[str, List[Dict[str, Any]]]:
        catalog: Dict[str, List[Dict[str, Any]]] = {}
        for service_type in SERVICE_TYPES:
            if service_type == "custom":
                continue
            catalog[service_type] = self._service_package_offers(
                service_type=service_type,
                requested_amount=self.min_native,
            )
        catalog["custom"] = self._service_package_offers(
            service_type="custom",
            requested_amount=self.min_native,
        )
        return catalog

    def payment_followup(self, task_id: str) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        commercial = task.get("commercial") or self._commercial_terms(
            service_type=str(task.get("service_type") or "custom"),
            requested_amount=float(task.get("budget_native") or self.min_native),
        )
        starter_offer = commercial.get("starter_offer") or {}
        primary_offer = commercial.get("primary_offer") or {}
        cheaper_starter = bool(
            starter_offer
            and primary_offer
            and float(starter_offer.get("amount_native") or 0.0)
            < float(primary_offer.get("amount_native") or 0.0)
        )
        nudge = (
            f"Start with the smaller {starter_offer.get('title', 'starter diagnosis')} first."
            if cheaper_starter
            else f"Pay the primary {primary_offer.get('title', 'bounded task')} to move this task into work."
        )
        return {
            "mode": "agent_service_payment_followup",
            "deal_found": False,
            "ok": True,
            "task_id": task_id,
            "status": str(task.get("status") or ""),
            "service_type": str(task.get("service_type") or "custom"),
            "starter_offer": starter_offer,
            "primary_offer": primary_offer,
            "cheaper_starter_available": cheaper_starter,
            "nudge": nudge,
            "machine_message": self._payment_followup_message(task, commercial),
            "analysis": (
                f"Payment follow-up for {task_id}: "
                f"starter={starter_offer.get('amount_native')}, primary={primary_offer.get('amount_native')}."
            ),
        }

    def end_to_end_runway(
        self,
        *,
        task_id: str = "",
        problem: str = "",
        service_type: str = "",
        budget_native: Optional[float] = None,
        requester_agent: str = "",
        requester_wallet: str = "",
        callback_url: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        create_task: bool = False,
        approval: str = "draft_only",
    ) -> Dict[str, Any]:
        existing_task = self._get_task(task_id) if task_id else None
        featured = self._featured_product_offer(service_type)
        template = ((featured.get("service_template") or {}).get("create_task_payload") or {})
        template_metadata = template.get("metadata") if isinstance(template.get("metadata"), dict) else {}
        merged_metadata = {
            **template_metadata,
            **(metadata or {}),
            "source": (metadata or {}).get("source") or "service_e2e_runway",
        }
        default_problem = self._clean(
            problem
            or template.get("problem")
            or featured.get("name")
            or "Resolve one bounded AI-agent infrastructure blocker end-to-end."
        )
        default_service_type = self._normalize_service_type(
            service_type or str(template.get("service_type") or featured.get("pain_type") or ""),
            default_problem,
        )
        requested_amount = (
            self._optional_float(budget_native)
            or self._optional_float(template.get("budget_native"))
            or self._optional_float((featured.get("paid_offer") or {}).get("price_native"))
            or self.min_native
        )
        created = False
        created_result: Dict[str, Any] = {}
        task = existing_task
        if create_task and not task:
            created_result = self.create_task(
                problem=default_problem,
                requester_agent=self._clean(requester_agent),
                requester_wallet=self._clean(requester_wallet),
                service_type=default_service_type,
                budget_native=requested_amount,
                callback_url=self._clean(callback_url),
                metadata=merged_metadata,
            )
            if not created_result.get("ok"):
                return {
                    "mode": "nomad_service_e2e",
                    "deal_found": False,
                    "ok": False,
                    "created": False,
                    "error": "task_create_failed",
                    "create_result": created_result,
                    "analysis": "Nomad could not create the E2E service task preview.",
                }
            task = created_result.get("task") or {}
            created = True

        preview = self._e2e_task_preview(
            task=task or {},
            problem=default_problem,
            service_type=default_service_type,
            requested_amount=requested_amount,
            requester_agent=requester_agent,
            requester_wallet=requester_wallet,
            callback_url=callback_url,
        )
        effective_task = task or preview
        payment_followup = {}
        if task and str(task.get("status") or "") == "awaiting_payment":
            payment_followup = self.payment_followup(str(task.get("task_id") or ""))
        staking = {}
        if task and str(task.get("status") or "") in {"draft_ready", "delivered"}:
            staking = self.metamask_staking_checklist(str(task.get("task_id") or ""))
        return {
            "mode": "nomad_service_e2e",
            "deal_found": False,
            "ok": True,
            "created": created,
            "public_api_url": self.public_api_url,
            "featured_product_offer": featured,
            "task": effective_task,
            "payment_followup": payment_followup,
            "staking": staking,
            "commands": self._e2e_commands(effective_task, default_service_type, default_problem, requested_amount),
            "http_runway": self._e2e_http_runway(effective_task, default_service_type, default_problem, requested_amount),
            "lifecycle": self._e2e_lifecycle(effective_task, approval=approval),
            "next_best_action": self._e2e_next_action(effective_task),
            "analysis": self._e2e_analysis(effective_task, created=created),
        }

    def metamask_staking_checklist(self, task_id: str) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        allocation = task.get("payment_allocation") or {}
        payment = task.get("payment") or {}
        wallet = self.treasury.get_wallet_summary()
        checklist = {
            "mode": "metamask_staking_checklist",
            "deal_found": False,
            "ok": True,
            "task_id": task_id,
            "staking_status": (task.get("treasury") or {}).get("staking_status"),
            "wallet": {
                "address": wallet.get("address") or payment.get("recipient_address", ""),
                "network": self.chain.name,
                "chain_id": self.chain.chain_id,
                "native_symbol": self.chain.native_symbol,
            },
            "planned_stake_native": allocation.get("treasury_stake_native", 0.0),
            "staking_target": allocation.get("staking_target", self.staking_target),
            "operator_steps": allocation.get("operator_steps") or [],
            "record_command": f"/service stake {task_id} <stake_tx_hash>",
            "analysis": (
                "MetaMask staking is prepared as an operator-confirmed treasury action. "
                "Nomad records the plan and tx hash, but does not silently control MetaMask."
            ),
        }
        return checklist

    def record_treasury_stake(
        self,
        task_id: str,
        tx_hash: str = "",
        amount_native: Optional[float] = None,
        note: str = "",
    ) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        tx_hash = self._clean(tx_hash)
        if tx_hash and not self._looks_like_tx_hash(tx_hash):
            return {
                "mode": "agent_service_request",
                "deal_found": False,
                "ok": False,
                "error": "invalid_stake_tx_hash",
                "message": "Stake tx_hash must be a 0x-prefixed transaction hash.",
                "task": task,
            }
        allocation = task.get("payment_allocation") or {}
        amount = (
            float(amount_native)
            if amount_native is not None
            else float(allocation.get("treasury_stake_native") or 0.0)
        )
        treasury = task.setdefault("treasury", {})
        treasury["staking_status"] = "staked_confirmed" if tx_hash else "stake_prepared"
        treasury["staking_target"] = allocation.get("staking_target", self.staking_target)
        treasury["stake_tx_hash"] = tx_hash
        treasury["stake_amount_native"] = round(amount, 8)
        treasury["stake_note"] = self._clean(note)
        task["updated_at"] = datetime.now(UTC).isoformat()
        task.setdefault("ledger", []).append(
            self._ledger_event(
                event="treasury_stake_recorded" if tx_hash else "treasury_stake_prepared",
                message=note or "Treasury stake status recorded.",
                tx_hash=tx_hash,
                amount_native=amount,
            )
        )
        self._store_task(task)
        return self._task_response(task)

    def record_solver_spend(
        self,
        task_id: str,
        amount_native: float,
        note: str,
        tx_hash: str = "",
    ) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        tx_hash = self._clean(tx_hash)
        if tx_hash and not self._looks_like_tx_hash(tx_hash):
            return {
                "mode": "agent_service_request",
                "deal_found": False,
                "ok": False,
                "error": "invalid_spend_tx_hash",
                "message": "Spend tx_hash must be a 0x-prefixed transaction hash.",
                "task": task,
            }
        amount = max(0.0, float(amount_native))
        solver = task.setdefault("solver_budget", {})
        allocation = task.get("payment_allocation") or {}
        total_budget = float(allocation.get("solver_budget_native") or 0.0)
        spent = round(float(solver.get("spent_native") or 0.0) + amount, 8)
        solver["spent_native"] = spent
        solver["remaining_native"] = round(max(0.0, total_budget - spent), 8)
        solver["spend_status"] = "spent" if solver["remaining_native"] <= 0 else "partially_spent"
        solver.setdefault("spend_notes", []).append(
            {
                "at": datetime.now(UTC).isoformat(),
                "amount_native": round(amount, 8),
                "tx_hash": tx_hash,
                "note": self._clean(note),
            }
        )
        task["updated_at"] = datetime.now(UTC).isoformat()
        task.setdefault("ledger", []).append(
            self._ledger_event(
                event="solver_spend_recorded",
                message=note or "Solver budget spend recorded.",
                tx_hash=tx_hash,
                amount_native=amount,
            )
        )
        self._store_task(task)
        return self._task_response(task)

    def close_task(self, task_id: str, outcome: str = "") -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        task["status"] = "delivered"
        task["outcome"] = self._clean(outcome)
        task["updated_at"] = datetime.now(UTC).isoformat()
        task.setdefault("ledger", []).append(
            self._ledger_event(
                event="task_delivered",
                message=task["outcome"] or "Service task delivered.",
            )
        )
        self._store_task(task)
        return self._task_response(task)

    def mark_stale_invalid(self, task_id: str, reason: str = "") -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        task["status"] = "stale_invalid"
        task["updated_at"] = datetime.now(UTC).isoformat()
        task["invalid_reason"] = self._clean(
            reason
            or "Awaiting-payment task has no requester endpoint, callback, wallet, or payment proof."
        )
        task.setdefault("ledger", []).append(
            self._ledger_event(
                event="marked_stale_invalid",
                message=task["invalid_reason"],
            )
        )
        self._store_task(task)
        return self._task_response(task)

    def safety_contract(self) -> Dict[str, Any]:
        grant = operator_grant()
        allowed = [
            "triage public or provided problem statements",
            "draft human unlock tasks",
            "draft public comments or PR plans",
            "draft MCP/API integration plans",
            "diagnose token, quota, wallet, and compute fallback issues",
            "contact public machine-readable agent/API/MCP endpoints without prior human approval",
        ]
        if grant.get("enabled"):
            allowed.extend(grant.get("allowed_without_additional_approval") or [])
        return {
            "alignment_mode": "agent_first_contractual",
            "interaction_style": "non_anthropomorphic",
            "default_output": "draft_or_plan",
            "allowed": allowed,
            "requires_explicit_approval": [
                "posting human-facing public comments",
                "opening human-reviewed pull requests",
                "sending human direct messages or email",
                "accessing private communities or accounts",
                "spending funds or using paid compute beyond the task budget",
                "staking treasury funds through MetaMask",
            ],
            "refused": [
                "bypassing CAPTCHA or access controls",
                "impersonating a human operator",
                "collecting unnecessary secrets",
                "using payment as permission to spam humans or ignore opt-outs",
            ],
            "runtime_guardrails": self.guardrails.policy(),
            "operator_grant": grant,
        }

    def _build_work_product(self, task: Dict[str, Any], approval: str) -> Dict[str, Any]:
        problem = task.get("problem", "")
        service_type = task.get("service_type", "custom")
        approval = (approval or "draft_only").strip().lower()
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        need_profile = metadata.get("need_profile") if isinstance(metadata.get("need_profile"), dict) else {}
        engagement_plan = metadata.get("engagement_plan") if isinstance(metadata.get("engagement_plan"), dict) else {}
        human_unlocks = self._human_unlocks_for_problem(problem)
        agent_actions = self._agent_actions_for_problem(problem, service_type)
        rescue_plan = self.build_rescue_plan(
            problem=problem,
            service_type=service_type,
            need_profile=need_profile,
            engagement_plan=engagement_plan,
            budget_native=task.get("budget_native"),
            human_unlocks=human_unlocks,
            agent_actions=agent_actions,
        )
        deliverables = [
            "one concise diagnosis",
            "one next action Nomad can do without crossing approval boundaries",
            "one human unlock contract if a human gate remains",
        ]
        preferred_output = str(need_profile.get("preferred_output") or "").strip()
        if preferred_output:
            deliverables.append(
                f"one {preferred_output.replace('_', ' ')} tailored to the requesting agent"
            )
        if service_type == "mcp_integration":
            deliverables.append("MCP tool/resource shape for the requesting agent")
        if service_type == "wallet_payment":
            deliverables.append("payment verification checklist and failure modes")
        if engagement_plan.get("memory_upgrade"):
            deliverables.append(str(engagement_plan["memory_upgrade"]))
        operator_scope = is_operator_approval_scope(approval)
        can_execute_public_action = approval in {"comment", "public_comment", "pr", "pull_request"}
        return {
            "status": "draft_ready",
            "approval": approval,
            "can_execute_public_action": can_execute_public_action,
            "can_execute_bounded_service_action": operator_scope or can_execute_public_action,
            "operator_grant": operator_grant() if operator_scope else {"enabled": False},
            "diagnosis": self._diagnosis(problem, service_type),
            "rescue_plan": rescue_plan,
            "agent_actions": agent_actions,
            "human_unlocks": human_unlocks,
            "agent_need_profile": need_profile,
            "engagement_plan": engagement_plan,
            "deliverables": deliverables,
            "response_schema": [
                "rescue_plan",
                "diagnosis",
                "next_action",
                "required_input",
                "price",
                "delivery",
                "memory_upgrade",
            ],
            "draft_response": self._draft_response(task, human_unlocks),
            "agent_success_message": self._agent_success_message(task, rescue_plan),
            "payment_allocation": task.get("payment_allocation") or {},
            "blocked_without_approval": self.safety_contract()["requires_explicit_approval"],
        }

    def build_rescue_plan(
        self,
        problem: str,
        service_type: str = "custom",
        need_profile: Optional[Dict[str, Any]] = None,
        engagement_plan: Optional[Dict[str, Any]] = None,
        budget_native: Optional[float] = None,
        human_unlocks: Optional[List[Dict[str, Any]]] = None,
        agent_actions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        cleaned_problem = self._clean(problem)
        normalized_type = self._normalize_service_type(service_type, cleaned_problem)
        need_profile = need_profile if isinstance(need_profile, dict) else {}
        engagement_plan = engagement_plan if isinstance(engagement_plan, dict) else {}
        human_unlocks = human_unlocks if human_unlocks is not None else self._human_unlocks_for_problem(cleaned_problem)
        agent_actions = agent_actions if agent_actions is not None else self._agent_actions_for_problem(cleaned_problem, normalized_type)
        first_unlock = human_unlocks[0] if human_unlocks else {}
        solution_pattern = solution_pattern_for(service_type=normalized_type, problem=cleaned_problem)
        safe_now = self._safe_now_steps(normalized_type, agent_actions)
        acceptance = self._acceptance_criteria_for_service(normalized_type, need_profile)
        required_input = first_unlock.get("human_deliverable") or self._required_input_for_service(normalized_type)
        plan = {
            "schema": "nomad.rescue_plan.v1",
            "plan_id": f"rescue-{hashlib.sha256(cleaned_problem.encode('utf-8')).hexdigest()[:10]}",
            "service_type": normalized_type,
            "problem_fingerprint": hashlib.sha256(cleaned_problem.encode("utf-8")).hexdigest()[:16],
            "diagnosis": self._diagnosis(cleaned_problem, normalized_type),
            "safe_now": safe_now,
            "required_input": required_input,
            "acceptance_criteria": acceptance,
            "solution_pattern": {
                "title": solution_pattern["title"],
                "guardrail_id": solution_pattern["guardrail"]["id"],
                "guardrail": solution_pattern["guardrail"],
                "playbook": solution_pattern["playbook"][:4],
            },
            "approval_boundary": {
                "can_do_without_approval": [
                    "draft diagnosis",
                    "draft repro/checklist",
                    "inspect provided public artifacts",
                    "return structured next steps",
                ],
                "requires_explicit_approval": self.safety_contract()["requires_explicit_approval"],
            },
            "commercial_next_step": {
                "offer_tier": str(engagement_plan.get("offer_tier") or "starter_diagnosis"),
                "package": str(
                    engagement_plan.get("package")
                    or (self._commercial_terms(normalized_type, budget_native).get("primary_offer") or {}).get("title")
                    or SERVICE_TYPES.get(normalized_type, SERVICE_TYPES["custom"])["title"]
                ),
                "price_native": (
                    budget_native
                    if budget_native is not None
                    else float(
                        ((self._commercial_terms(normalized_type, self.min_native).get("primary_offer") or {}).get("amount_native"))
                        or self.min_native
                    )
                ),
                "delivery": str(engagement_plan.get("delivery") or "draft-only diagnosis plus one next action"),
            },
            "commercial_ladder": (self._commercial_terms(normalized_type, budget_native).get("offer_ladder") or [])[:2],
            "memory_upgrade": str(
                engagement_plan.get("memory_upgrade")
                or "convert the solved blocker into a reusable checklist after requester consent"
            ),
            "machine_reply_contract": {
                "reply_with": [
                    "PLAN_ACCEPTED=true",
                    "FACT_URL=<public artifact>",
                    "ERROR=<exact error or status>",
                    "APPROVAL_GRANTED=<scope>",
                ],
                "do_not_send": [
                    "unscoped secrets",
                    "private credentials unless explicitly requested through a safe channel",
                    "human-facing posting permission implied by payment",
                ],
            },
        }
        if need_profile:
            plan["requester_fit"] = {
                "urgency": need_profile.get("urgency", ""),
                "engagement_mode": need_profile.get("engagement_mode", ""),
                "preferred_output": need_profile.get("preferred_output", ""),
                "autonomy_boundary": need_profile.get("autonomy_boundary", ""),
            }
        return plan

    def _safe_now_steps(self, service_type: str, agent_actions: List[str]) -> List[str]:
        pattern = solution_pattern_for(service_type=service_type)
        steps = list(agent_actions[:3])
        if not steps:
            steps = ["Reduce the blocker to one verifiable state, error, or public artifact."]
        for step in reversed(pattern.get("playbook", [])[:2]):
            if step not in steps:
                steps.insert(0, step)
        if service_type == "compute_auth":
            steps.append("Keep token values private; share only scope, provider status, and error class.")
        if service_type == "human_in_loop":
            steps.append("Ask for the smallest legitimate human approval; do not bypass the gate.")
        if service_type in {"payment", "wallet_payment"}:
            steps.append("Verify chain, recipient, amount, and duplicate-use status before delivery.")
        return steps[:5]

    def _acceptance_criteria_for_service(
        self,
        service_type: str,
        need_profile: Dict[str, Any],
    ) -> List[str]:
        preferred = str(need_profile.get("preferred_output") or "").replace("_", " ").strip()
        criteria = [
            "The requester has one concrete next action it can run or hand to its operator.",
            "No public post, private access, payment spend, or human impersonation occurs without approval.",
        ]
        pattern = solution_pattern_for(service_type=service_type)
        if preferred:
            criteria.insert(0, f"The response includes a usable {preferred}.")
        for item in pattern.get("acceptance", [])[:2]:
            if item not in criteria:
                criteria.append(item)
        if service_type == "compute_auth":
            criteria.append("Token/auth, quota/rate-limit, model access, and fallback lane are separated.")
        elif service_type == "loop_break":
            criteria.append("The retry loop has one safe pause point and one known-good recovery path.")
        elif service_type == "mcp_integration":
            criteria.append("Tool schema, resource URI, request shape, and expected response are named.")
        elif service_type == "human_in_loop":
            criteria.append("The human gate has do-now, send-back, and done-when fields.")
        return criteria[:5]

    @staticmethod
    def _required_input_for_service(service_type: str) -> str:
        return {
            "compute_auth": "`PROVIDER_STATUS=<message>`, `TOKEN_SCOPE=<scope>`, or `ERROR=<status/code>`.",
            "loop_break": "`LAST_GOOD_STATE=<state>`, `FAILING_TOOL=<name>`, or `ERROR=<message>`.",
            "human_in_loop": "`APPROVAL_GRANTED=<scope>`, `BLOCKED_BY=<reason>`, or `HUMAN_UNLOCK_DONE=<result>`.",
            "mcp_integration": "`TOOL_SCHEMA=<json>`, `RESOURCE_URI=<uri>`, or `EXPECTED_RESPONSE=<shape>`.",
            "payment": "`TX_HASH=<0x...>`, `CHAIN_ID=<id>`, or `PAYMENT_ERROR=<message>`.",
            "wallet_payment": "`TX_HASH=<0x...>`, `CHAIN_ID=<id>`, or `PAYMENT_ERROR=<message>`.",
            "hallucination": "`CLAIM=<claim>`, `EVIDENCE_URL=<url>`, or `TOOL_OUTPUT=<excerpt>`.",
            "memory": "`MEMORY_TYPE=<fact|decision|constraint|outcome>`, `MEMORY_VALUE=<non-secret value>`.",
            "self_improvement": "`SOLVED_BLOCKER=<summary>`, `FIX_THAT_WORKED=<step>`, or `VERIFY_WITH=<test>`.",
        }.get(service_type, "`FACT_URL=https://...`, `ERROR=...`, or `REPRO_STEPS=...`.")

    def _diagnosis(self, problem: str, service_type: str) -> str:
        lowered = problem.lower()
        normalized_pattern_type = normalize_pain_type(service_type=service_type, problem=problem)
        if normalized_pattern_type in {
            "human_in_loop",
            "compute_auth",
            "payment",
            "loop_break",
            "hallucination",
            "memory",
            "mcp_integration",
            "repo_issue_help",
            "self_improvement",
        }:
            return solution_pattern_for(service_type=normalized_pattern_type)["diagnosis"]
        if service_type == "human_in_loop" or any(
            token in lowered for token in ("captcha", "approval", "human", "login")
        ):
            return solution_pattern_for(service_type="human_in_loop")["diagnosis"]
        if service_type == "compute_auth" or any(
            token in lowered for token in ("quota", "rate limit", "token", "inference", "model")
        ):
            return solution_pattern_for(service_type="compute_auth")["diagnosis"]
        if service_type == "wallet_payment" or "wallet" in lowered or "payment" in lowered:
            return solution_pattern_for(service_type="payment")["diagnosis"]
        return (
            "This is a bounded agent-infrastructure task. Nomad should produce a small, "
            "testable plan before doing any external action."
        )

    def _agent_actions_for_problem(self, problem: str, service_type: str) -> List[str]:
        actions = [
            "Create a minimal reproduction or state checklist from the provided facts.",
            "Separate actions Nomad can do from actions that require the requester's human operator.",
            "Return a draft-only response unless explicit approval is attached.",
        ]
        pattern = solution_pattern_for(service_type=service_type, problem=problem)
        for step in reversed(pattern.get("playbook", [])[:2]):
            if step not in actions:
                actions.insert(0, step)
        if service_type == "loop_break":
            actions.insert(0, "Pause retries, preserve state, and isolate the first failing tool call.")
        if service_type == "hallucination":
            actions.insert(0, "Add a verifier/checker step before allowing another external action.")
        if service_type == "memory":
            actions.insert(0, "Write the missing durable memory as a fact, decision, or constraint.")
        if service_type == "payment":
            actions.insert(0, "Verify wallet, payment reference, tx hash, and x402 challenge state.")
        if service_type == "compute_auth":
            actions.insert(0, "Probe provider reachability, token presence, quota state, and fallback route.")
        if service_type == "mcp_integration":
            actions.insert(0, "Define tool schema, resource URI, prompt shape, and expected JSON result.")
        if service_type == "wallet_payment":
            actions.insert(0, "Verify the payment tx hash against recipient, value, chain, and duplicate use.")
        return actions

    def _human_unlocks_for_problem(self, problem: str) -> List[Dict[str, Any]]:
        lowered = problem.lower()
        unlocks: List[Dict[str, Any]] = []
        if any(token in lowered for token in ("captcha", "login", "approval", "human")):
            unlocks.append(
                self._unlock(
                    candidate_id="requester-human-unlock",
                    candidate_name="Requester human unlock",
                    short_ask="Ask the requester's human for the smallest approval or login step.",
                    action=(
                        "Have the requester complete only the legitimate login, CAPTCHA, invite, "
                        "or approval step, then send back the resulting non-secret status."
                    ),
                    deliverable=(
                        "`HUMAN_UNLOCK_DONE=<what changed>`, `APPROVAL_GRANTED=<scope>`, "
                        "or `BLOCKED_BY=<reason>`."
                    ),
                )
            )
        if any(token in lowered for token in ("token", "key", "secret", "permission")):
            unlocks.append(
                self._unlock(
                    candidate_id="requester-credential-scope",
                    candidate_name="Requester credential scope",
                    short_ask="Ask for scoped, revocable credential confirmation.",
                    action=(
                        "The requester should confirm which token or permission scope is safe to test, "
                        "without sending unnecessary secrets."
                    ),
                    deliverable="`TOKEN_SCOPE=<scope>`, `PROVIDER_STATUS=<message>`, or `NO_SECRET_NEEDED=true`.",
                )
            )
        if not unlocks:
            unlocks.append(
                self._unlock(
                    candidate_id="requester-next-fact",
                    candidate_name="Requester next fact",
                    short_ask="Ask for one missing fact that makes the task verifiable.",
                    action=(
                        "Send one URL, error message, API response, repo, or workflow state that Nomad can inspect."
                    ),
                    deliverable="`FACT_URL=https://...`, `ERROR=...`, or `REPRO_STEPS=...`.",
                )
            )
        return unlocks[:3]

    def _unlock(
        self,
        candidate_id: str,
        candidate_name: str,
        short_ask: str,
        action: str,
        deliverable: str,
    ) -> Dict[str, Any]:
        return {
            "category": "external_agent_service",
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "role": "requester human unlock",
            "lane_state": "pending",
            "requires_account": False,
            "env_vars": [],
            "short_ask": short_ask,
            "human_action": action,
            "human_deliverable": deliverable,
            "success_criteria": [
                "Nomad can continue without bypassing access controls.",
                "The requester gets one verifiable next step or clear blocker.",
            ],
            "example_response": deliverable.split(",", 1)[0].strip("` ") if deliverable else "DONE",
            "timebox_minutes": 5,
        }

    def _draft_response(
        self,
        task: Dict[str, Any],
        human_unlocks: List[Dict[str, Any]],
    ) -> str:
        service = SERVICE_TYPES.get(task.get("service_type"), SERVICE_TYPES["custom"])
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        need_profile = metadata.get("need_profile") if isinstance(metadata.get("need_profile"), dict) else {}
        engagement_plan = metadata.get("engagement_plan") if isinstance(metadata.get("engagement_plan"), dict) else {}
        first_unlock = human_unlocks[0] if human_unlocks else {}
        delivery = str(engagement_plan.get("delivery") or "draft_only_plan_or_response")
        memory_upgrade = str(engagement_plan.get("memory_upgrade") or "available_after_consent")
        lines = [
            "nomad.draft.v1",
            f"service_type={task.get('service_type') or 'custom'}",
            f"service_title={service['title']}",
            f"diagnosis={self._diagnosis(task.get('problem', ''), task.get('service_type', 'custom'))}",
            f"next_action={first_unlock.get('short_ask', 'provide one missing fact')}",
            "required_input=one_missing_fact_or_unlock",
            f"price={task.get('budget_native')} {self.chain.native_symbol}",
            f"delivery={delivery}",
            f"memory_upgrade={memory_upgrade}",
            "approval_boundary=public_actions_and_private_access_require_explicit_approval",
        ]
        if engagement_plan.get("offer_tier"):
            lines.append(f"offer_tier={engagement_plan['offer_tier']}")
        if engagement_plan.get("package"):
            lines.append(f"package={engagement_plan['package']}")
        commercial = task.get("commercial") or {}
        starter_offer = commercial.get("starter_offer") or {}
        primary_offer = commercial.get("primary_offer") or {}
        if starter_offer:
            lines.append(f"starter_offer_native={starter_offer.get('amount_native')}")
        if primary_offer:
            lines.append(f"primary_offer_native={primary_offer.get('amount_native')}")
        if need_profile.get("preferred_output"):
            lines.append(f"preferred_output={need_profile['preferred_output']}")
        return "\n".join(lines)

    def _agent_success_message(
        self,
        task: Dict[str, Any],
        rescue_plan: Dict[str, Any],
    ) -> str:
        commercial = rescue_plan.get("commercial_next_step") or {}
        lines = [
            "nomad.rescue_plan.v1",
            f"plan_id={rescue_plan.get('plan_id', '')}",
            f"service_type={rescue_plan.get('service_type', task.get('service_type', 'custom'))}",
            f"diagnosis={rescue_plan.get('diagnosis', '')}",
            f"safe_now={' | '.join(str(item) for item in (rescue_plan.get('safe_now') or [])[:3])}",
            f"required_input={rescue_plan.get('required_input', '')}",
            f"acceptance={' | '.join(str(item) for item in (rescue_plan.get('acceptance_criteria') or [])[:3])}",
            f"offer_tier={commercial.get('offer_tier', '')}",
            f"package={commercial.get('package', '')}",
            "approval_boundary=public_actions_private_access_and_fund_spend_require_explicit_approval",
        ]
        return "\n".join(lines)

    def _payment_allocation(
        self,
        amount_native: float,
        payment_verified: bool,
    ) -> Dict[str, Any]:
        treasury_stake = round(amount_native * self.treasury_stake_bps / 10000, 8)
        solver_budget = round(amount_native * self.solver_spend_bps / 10000, 8)
        reserve = round(max(0.0, amount_native - treasury_stake - solver_budget), 8)
        return {
            "amount_native": round(amount_native, 8),
            "native_symbol": self.chain.native_symbol,
            "treasury_stake_bps": self.treasury_stake_bps,
            "solver_spend_bps": self.solver_spend_bps,
            "treasury_stake_native": treasury_stake,
            "solver_budget_native": solver_budget,
            "reserve_native": reserve,
            "staking_target": self.staking_target,
            "payment_verified": payment_verified,
            "treasury_staking_status": (
                "ready_for_metamask_approval"
                if payment_verified and treasury_stake > 0
                else "planned_after_payment_verification"
            ),
            "solver_budget_status": (
                "available_for_problem_solving"
                if payment_verified and solver_budget > 0
                else "planned_after_payment_verification"
            ),
            "operator_steps": [
                "Verify the incoming payment tx_hash first.",
                (
                    f"Stake {treasury_stake} {self.chain.native_symbol} from the MetaMask-controlled "
                    "treasury wallet only after explicit operator approval."
                ),
                (
                    f"Use up to {solver_budget} {self.chain.native_symbol} equivalent for the task's "
                    "compute, tools, or human-unlock support budget."
                ),
                "Record the final spend/stake outcome back on the task before closing it.",
            ],
        }

    def _payment_request(
        self,
        task_id: str,
        amount_native: float,
        requester_wallet: str,
        service_type: str,
    ) -> Dict[str, Any]:
        wallet = self.treasury.get_wallet_summary()
        recipient = wallet.get("address") or ""
        memo = f"NOMAD_TASK:{task_id}"
        data_hex = "0x" + memo.encode("utf-8").hex()
        return {
            "status": "awaiting_payment" if self.require_payment else "not_required",
            "recipient_address": recipient,
            "recipient_configured": bool(recipient),
            "requester_wallet": requester_wallet,
            "network": self.chain.name,
            "chain_id": self.chain.chain_id,
            "amount_native": round(amount_native, 8),
            "native_symbol": self.chain.native_symbol,
            "payment_reference": memo,
            "optional_tx_data": data_hex,
            "x402": self._x402_challenge(
                task_id=task_id,
                amount_native=amount_native,
                recipient=recipient,
                service_type=service_type,
            ),
            "tx_hash": "",
            "verification": None,
        }

    def _x402_challenge(
        self,
        task_id: str,
        amount_native: float,
        recipient: str,
        service_type: str,
    ) -> Dict[str, Any]:
        public_api_url = self.public_api_url
        resource_url = f"{public_api_url}/x402/paid-help" if public_api_url else "/x402/paid-help"
        return self.x402.build_challenge(
            task_id=task_id,
            amount_native=amount_native,
            pay_to=recipient,
            network_caip2=self._x402_network(),
            resource_url=resource_url,
            description=f"Nomad paid agent help for task {task_id}",
            service_type=service_type,
        )

    def _x402_network(self) -> str:
        return (os.getenv("NOMAD_X402_NETWORK") or f"eip155:{self.chain.chain_id}").strip()

    def _verify_native_transfer(
        self,
        tx_hash: str,
        expected_amount: float,
        expected_from: str,
    ) -> Dict[str, Any]:
        wallet = self.treasury.get_wallet_summary()
        recipient = (wallet.get("address") or "").strip()
        if not recipient:
            return {
                "ok": False,
                "status": "recipient_wallet_missing",
                "message": "Nomad wallet is not configured, so payment cannot be verified.",
            }

        try:
            from web3 import Web3

            w3 = Web3(Web3.HTTPProvider(self.chain.rpc_url))
            tx = w3.eth.get_transaction(tx_hash)
            value_native = float(w3.from_wei(tx.get("value", 0), "ether"))
            to_address = tx.get("to") or ""
            from_address = tx.get("from") or ""
            if to_address.lower() != recipient.lower():
                return {
                    "ok": False,
                    "status": "wrong_recipient",
                    "message": "Transaction recipient does not match Nomad wallet.",
                    "observed_to": to_address,
                }
            if expected_from and from_address.lower() != expected_from.lower():
                return {
                    "ok": False,
                    "status": "wrong_sender",
                    "message": "Transaction sender does not match requester wallet.",
                    "observed_from": from_address,
                }
            if value_native + 1e-12 < expected_amount:
                return {
                    "ok": False,
                    "status": "insufficient_amount",
                    "message": "Transaction value is below the requested task budget.",
                    "observed_amount_native": round(value_native, 8),
                }
            return {
                "ok": True,
                "status": "verified",
                "message": "Native wallet payment verified.",
                "observed_amount_native": round(value_native, 8),
                "observed_from": from_address,
                "observed_to": to_address,
            }
        except Exception as exc:
            return {
                "ok": False,
                "status": "rpc_unavailable_or_tx_missing",
                "message": f"Payment verification failed: {exc}",
            }

    def _refresh_allocation_status(self, task: Dict[str, Any]) -> None:
        allocation = task.get("payment_allocation") or {}
        treasury = task.setdefault("treasury", {})
        solver = task.setdefault("solver_budget", {})
        treasury["staking_target"] = allocation.get("staking_target", self.staking_target)
        if allocation.get("payment_verified"):
            treasury.setdefault("stake_tx_hash", "")
            treasury.setdefault("stake_amount_native", 0.0)
            if treasury.get("staking_status") in {None, "", "planned_after_payment_verification"}:
                treasury["staking_status"] = "ready_for_metamask_approval"
            solver.setdefault("spent_native", 0.0)
            solver.setdefault("spend_notes", [])
            solver["remaining_native"] = round(
                max(
                    0.0,
                    float(allocation.get("solver_budget_native") or 0.0)
                    - float(solver.get("spent_native") or 0.0),
                ),
                8,
            )
            if solver.get("spend_status") in {None, "", "planned_after_payment_verification"}:
                solver["spend_status"] = "available_for_problem_solving"
        else:
            treasury.setdefault("staking_status", "planned_after_payment_verification")
            solver.setdefault("spend_status", "planned_after_payment_verification")
            solver.setdefault("spent_native", 0.0)
            solver.setdefault("remaining_native", 0.0)
            solver.setdefault("spend_notes", [])

    def _ledger_event(
        self,
        event: str,
        message: str,
        tx_hash: str = "",
        amount_native: Optional[float] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "at": datetime.now(UTC).isoformat(),
            "event": event,
            "message": message,
        }
        if tx_hash:
            payload["tx_hash"] = tx_hash
        if amount_native is not None:
            payload["amount_native"] = round(float(amount_native), 8)
            payload["native_symbol"] = self.chain.native_symbol
        return payload

    def _task_response(self, task: Dict[str, Any], created: bool = False) -> Dict[str, Any]:
        return {
            "mode": "agent_service_request",
            "deal_found": False,
            "ok": True,
            "created": created,
            "task": task,
            "analysis": self._analysis(task),
        }

    def _analysis(self, task: Dict[str, Any]) -> str:
        status = task.get("status", "unknown")
        payment = task.get("payment") or {}
        if status == "awaiting_payment":
            commercial = task.get("commercial") or {}
            starter_offer = commercial.get("starter_offer") or {}
            primary_offer = commercial.get("primary_offer") or {}
            starter_text = ""
            if (
                starter_offer
                and primary_offer
                and float(starter_offer.get("amount_native") or 0.0)
                < float(primary_offer.get("amount_native") or 0.0)
            ):
                starter_text = (
                    f" Smaller entry path available: {starter_offer.get('amount_native')} "
                    f"{payment.get('native_symbol')} for {starter_offer.get('title')}."
                )
            return (
                f"Service task {task['task_id']} is ready for payment. Send "
                f"{payment.get('amount_native')} {payment.get('native_symbol')} to "
                f"{payment.get('recipient_address') or 'the configured Nomad wallet'}, then submit tx_hash."
                f"{starter_text}"
            )
        if status == "paid":
            allocation = task.get("payment_allocation") or {}
            return (
                f"Service task {task['task_id']} is paid and ready for Nomad to work. "
                f"Allocation: {allocation.get('treasury_stake_native')} "
                f"{allocation.get('native_symbol')} planned for MetaMask treasury staking, "
                f"{allocation.get('solver_budget_native')} {allocation.get('native_symbol')} "
                "available for problem solving."
            )
        if status == "draft_ready":
            return f"Service task {task['task_id']} has a draft work product ready."
        if status == "delivered":
            return f"Service task {task['task_id']} is delivered. Outcome: {task.get('outcome') or 'recorded'}."
        if status == "payment_unverified":
            return f"Service task {task['task_id']} has a payment claim that could not be verified."
        return f"Service task {task['task_id']} status: {status}."

    def _e2e_task_preview(
        self,
        *,
        task: Dict[str, Any],
        problem: str,
        service_type: str,
        requested_amount: float,
        requester_agent: str,
        requester_wallet: str,
        callback_url: str,
    ) -> Dict[str, Any]:
        if task:
            return task
        return {
            "task_id": "preview",
            "status": "preview",
            "service_type": service_type or "custom",
            "problem": problem,
            "budget_native": round(float(requested_amount), 8),
            "requester_agent": self._clean(requester_agent),
            "requester_wallet": self._clean(requester_wallet),
            "callback_url": self._clean(callback_url),
            "payment": {
                "amount_native": round(float(requested_amount), 8),
                "native_symbol": self.chain.native_symbol,
                "recipient_address": (self.treasury.get_wallet_summary() or {}).get("address", ""),
            },
        }

    def _e2e_commands(
        self,
        task: Dict[str, Any],
        service_type: str,
        problem: str,
        requested_amount: float,
    ) -> Dict[str, str]:
        task_id = str(task.get("task_id") or "svc-task-id")
        safe_problem = str(problem or "").replace('"', "'").strip()
        preview_suffix = (
            f' --create --service-type {service_type} --budget {requested_amount} "{safe_problem}"'
            if task_id == "preview"
            else f" --task-id {task_id}"
        )
        return {
            "preview_or_create": f"python main.py --cli service-e2e{preview_suffix}".strip(),
            "verify_payment": f"python main.py --cli service-verify {task_id} <tx_hash>",
            "verify_x402_payment": f"python main.py --cli service-x402-verify {task_id} <payment_signature>",
            "work_task": f"python main.py --cli service-work {task_id}",
            "staking_checklist": f"python main.py --cli service-staking {task_id}",
            "record_stake": f"python main.py --cli service-stake {task_id} <stake_tx_hash>",
            "record_spend": f"python main.py --cli service-spend {task_id} <amount>",
            "close_task": f"python main.py --cli service-close {task_id} <outcome>",
        }

    def _e2e_http_runway(
        self,
        task: Dict[str, Any],
        service_type: str,
        problem: str,
        requested_amount: float,
    ) -> Dict[str, Dict[str, Any]]:
        task_id = str(task.get("task_id") or "")
        return {
            "create_task": {
                "method": "POST",
                "endpoint": f"{self.public_api_url}/service/e2e" if self.public_api_url else "/service/e2e",
                "payload": {
                    "create": True,
                    "problem": problem,
                    "service_type": service_type,
                    "budget_native": requested_amount,
                },
            },
            "verify_payment": {
                "method": "POST",
                "endpoint": f"{self.public_api_url}/tasks/verify" if self.public_api_url else "/tasks/verify",
                "payload": {
                    "task_id": task_id or "<task_id>",
                    "tx_hash": "0x" + "0" * 64,
                },
            },
            "verify_x402_payment": {
                "method": "POST",
                "endpoint": f"{self.public_api_url}/tasks/x402-verify" if self.public_api_url else "/tasks/x402-verify",
                "payload": {
                    "task_id": task_id or "<task_id>",
                    "payment_signature": "<payment_signature>",
                },
            },
            "work_task": {
                "method": "POST",
                "endpoint": f"{self.public_api_url}/tasks/work" if self.public_api_url else "/tasks/work",
                "payload": {
                    "task_id": task_id or "<task_id>",
                    "approval": "draft_only",
                },
            },
            "close_task": {
                "method": "POST",
                "endpoint": f"{self.public_api_url}/tasks/close" if self.public_api_url else "/tasks/close",
                "payload": {
                    "task_id": task_id or "<task_id>",
                    "outcome": "<bounded outcome>",
                },
            },
        }

    def _e2e_lifecycle(self, task: Dict[str, Any], approval: str) -> List[Dict[str, Any]]:
        status = str(task.get("status") or "preview")
        task_id = str(task.get("task_id") or "preview")
        stages: List[Dict[str, Any]] = [
            {
                "stage": "create_task",
                "status": "completed" if status != "preview" else "ready",
                "task_id": task_id,
                "note": "Create the payable task and issue payment instructions.",
            },
            {
                "stage": "verify_payment",
                "status": (
                    "completed"
                    if status in {"paid", "draft_ready", "delivered"}
                    else "ready"
                    if status == "awaiting_payment"
                    else "blocked"
                ),
                "task_id": task_id,
                "note": "Verify a native tx_hash or x402 signature before Nomad works the task.",
            },
            {
                "stage": "work_task",
                "status": (
                    "completed"
                    if status in {"draft_ready", "delivered"}
                    else "ready"
                    if status == "paid"
                    else "blocked"
                ),
                "task_id": task_id,
                "approval": approval,
                "note": "Produce the draft work product once payment is verified.",
            },
            {
                "stage": "treasury_stake",
                "status": self._e2e_stake_status(task),
                "task_id": task_id,
                "note": "Record the planned MetaMask treasury stake for the paid task.",
            },
            {
                "stage": "solver_spend",
                "status": self._e2e_solver_spend_status(task),
                "task_id": task_id,
                "note": "Record solver spend as Nomad uses the paid task budget.",
            },
            {
                "stage": "close_task",
                "status": "completed" if status == "delivered" else "ready" if status == "draft_ready" else "blocked",
                "task_id": task_id,
                "note": "Close the task with a bounded outcome once delivery is complete.",
            },
        ]
        return stages

    @staticmethod
    def _e2e_stake_status(task: Dict[str, Any]) -> str:
        status = str(task.get("status") or "preview")
        treasury = task.get("treasury") if isinstance(task.get("treasury"), dict) else {}
        staking_status = str(treasury.get("staking_status") or "")
        if staking_status == "staked_confirmed":
            return "completed"
        if status in {"draft_ready", "delivered", "paid"}:
            return "ready"
        return "blocked"

    @staticmethod
    def _e2e_solver_spend_status(task: Dict[str, Any]) -> str:
        status = str(task.get("status") or "preview")
        solver = task.get("solver_budget") if isinstance(task.get("solver_budget"), dict) else {}
        spend_status = str(solver.get("spend_status") or "")
        if spend_status in {"spent", "partially_spent"}:
            return "in_progress"
        if status in {"draft_ready", "delivered", "paid"}:
            return "ready"
        return "blocked"

    def _e2e_next_action(self, task: Dict[str, Any]) -> str:
        status = str(task.get("status") or "preview")
        task_id = str(task.get("task_id") or "<task_id>")
        if status == "preview":
            return "Create the payable task first so Nomad can issue a wallet invoice."
        if status == "awaiting_payment":
            return f"Verify payment for {task_id} with /tasks/verify or /tasks/x402-verify."
        if status == "paid":
            return f"Run /tasks/work for {task_id} to produce the bounded draft work product."
        if status == "draft_ready":
            return f"Review the draft, record stake/spend, then close task {task_id} with a concrete outcome."
        if status == "delivered":
            return f"Task {task_id} is delivered; turn the solved path into reusable Nomad memory if useful."
        if status == "payment_unverified":
            return f"Manual payment review is needed for {task_id} before work can start."
        return f"Inspect task {task_id} and continue the next unpaid or undelivered stage."

    def _e2e_analysis(self, task: Dict[str, Any], *, created: bool) -> str:
        status = str(task.get("status") or "preview")
        task_id = str(task.get("task_id") or "preview")
        prefix = "Nomad created a payable end-to-end task." if created else "Nomad prepared a payable end-to-end runway."
        if status == "preview":
            return f"{prefix} No task exists yet; the next step is task creation."
        if status == "awaiting_payment":
            return f"{prefix} Task {task_id} is waiting for payment verification before work."
        if status == "paid":
            return f"{prefix} Task {task_id} is paid and ready for bounded work."
        if status == "draft_ready":
            return f"{prefix} Task {task_id} has a draft work product and can move through spend/stake/close."
        if status == "delivered":
            return f"{prefix} Task {task_id} completed the end-to-end path and is delivered."
        return f"{prefix} Task {task_id} is currently at status {status}."

    def _task_can_be_worked(self, task: Dict[str, Any]) -> bool:
        if not self.require_payment:
            return True
        verification = ((task.get("payment") or {}).get("verification") or {})
        return bool(verification.get("ok") or task.get("status") == "paid")

    def _normalize_service_type(self, service_type: str, problem: str) -> str:
        key = (service_type or "").strip().lower().replace("-", "_")
        if key in SERVICE_TYPES and key != "custom":
            return key
        lowered = problem.lower()
        if any(token in lowered for token in ("captcha", "login", "approval", "human")):
            return "human_in_loop"
        if any(
            token in lowered
            for token in ("self-improvement", "self improvement", "guardrail", "playbook", "prompt", "evaluation")
        ):
            return "self_improvement"
        if any(token in lowered for token in ("stuck", "loop", "retry", "infinite", "timeout", "tool fail")):
            return "loop_break"
        if any(token in lowered for token in ("hallucination", "wrong", "invalid", "drift", "unsupported claim")):
            return "hallucination"
        if any(token in lowered for token in ("memory", "context", "session", "forgot", "preference")):
            return "memory"
        if any(token in lowered for token in ("quota", "rate limit", "token", "inference", "model")):
            return "compute_auth"
        if "mcp" in lowered or "api" in lowered:
            return "mcp_integration"
        if "wallet" in lowered or "payment" in lowered or "tx_hash" in lowered or "x402" in lowered:
            return "wallet_payment"
        if "github" in lowered or "issue" in lowered or "pull request" in lowered:
            return "repo_issue_help"
        return "custom"

    def _service_package_offers(
        self,
        service_type: str,
        requested_amount: Optional[float],
    ) -> List[Dict[str, Any]]:
        normalized_type = service_type if service_type in SERVICE_TYPES else "custom"
        templates = (
            SERVICE_PACKAGE_TEMPLATES.get(normalized_type)
            or SERVICE_PACKAGE_TEMPLATES["custom"]
        )
        requested = max(self.min_native, float(requested_amount or self.min_native))
        offers: List[Dict[str, Any]] = []
        for template in templates:
            amount_mode = str(template.get("amount_mode") or "requested_or_minimum")
            if amount_mode == "minimum":
                amount = self.min_native
            else:
                amount = requested
            offers.append(
                {
                    "package_id": str(template.get("package_id") or ""),
                    "title": str(template.get("title") or ""),
                    "summary": str(template.get("summary") or ""),
                    "offer_tier": str(template.get("offer_tier") or ""),
                    "amount_native": round(float(amount), 8),
                    "native_symbol": self.chain.native_symbol,
                    "delivery": str(template.get("delivery") or ""),
                }
            )
        return offers

    def _commercial_terms(
        self,
        service_type: str,
        requested_amount: Optional[float],
    ) -> Dict[str, Any]:
        offer_ladder = self._service_package_offers(service_type, requested_amount)
        starter_offer = offer_ladder[0] if offer_ladder else {}
        primary_offer = offer_ladder[-1] if offer_ladder else {}
        return {
            "offer_ladder": offer_ladder,
            "starter_offer": starter_offer,
            "primary_offer": primary_offer,
        }

    def _payment_followup_message(
        self,
        task: Dict[str, Any],
        commercial: Dict[str, Any],
    ) -> str:
        payment = task.get("payment") or {}
        starter_offer = commercial.get("starter_offer") or {}
        primary_offer = commercial.get("primary_offer") or {}
        lines = [
            "nomad.payment_followup.v1",
            f"task_id={task.get('task_id') or ''}",
            f"service_type={task.get('service_type') or 'custom'}",
            f"primary_amount_native={payment.get('amount_native')}",
            f"recipient_address={payment.get('recipient_address') or ''}",
            "next_action=submit_tx_hash_after_payment_or_request_the_smallest_starter_path",
        ]
        if starter_offer:
            lines.append(f"starter_offer={starter_offer.get('title')}")
            lines.append(f"starter_amount_native={starter_offer.get('amount_native')}")
        if primary_offer:
            lines.append(f"primary_offer={primary_offer.get('title')}")
        return "\n".join(lines)

    def _task_id(
        self,
        problem: str,
        requester_agent: str,
        requester_wallet: str,
        created_at: str,
    ) -> str:
        seed = f"{created_at}|{requester_agent}|{requester_wallet}|{problem}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
        return f"svc-{digest}"

    def _looks_like_tx_hash(self, value: str) -> bool:
        return bool(re.fullmatch(r"0x[a-fA-F0-9]{64}", value or ""))

    def _looks_like_wallet(self, value: str) -> bool:
        return bool(re.fullmatch(r"0x[a-fA-F0-9]{40}", value or ""))

    def _tx_used_by_other_task(self, task_id: str, tx_hash: str) -> str:
        state = self._load()
        for existing_id, task in state.get("tasks", {}).items():
            if existing_id == task_id:
                continue
            payment = task.get("payment") or {}
            if (payment.get("tx_hash") or "").lower() == tx_hash.lower():
                return existing_id
        return ""

    def _x402_signature_used_by_other_task(self, task_id: str, fingerprint: str) -> str:
        if not fingerprint:
            return ""
        state = self._load()
        for existing_id, task in state.get("tasks", {}).items():
            if existing_id == task_id:
                continue
            x402_state = ((task.get("payment") or {}).get("x402") or {})
            if (x402_state.get("payment_signature_fingerprint") or "") == fingerprint:
                return existing_id
        return ""

    def _get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        return (self._load().get("tasks") or {}).get(task_id)

    def _store_task(self, task: Dict[str, Any]) -> None:
        state = self._load()
        state["tasks"][task["task_id"]] = task
        self._save(state)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"tasks": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"tasks": {}}
            payload.setdefault("tasks", {})
            return payload
        except Exception:
            return {"tasks": {}}

    def _save(self, state: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _missing_task(self, task_id: str) -> Dict[str, Any]:
        return {
            "mode": "agent_service_request",
            "deal_found": False,
            "ok": False,
            "error": "task_not_found",
            "task_id": task_id,
            "message": "No Nomad service task exists for that task_id.",
        }

    def _counter_offer_payload(
        self,
        *,
        error: str,
        message: str,
        requested_budget_native: Optional[float],
        requester_wallet: str,
    ) -> Dict[str, Any]:
        suggested_budget = self.min_native
        if requested_budget_native is not None and requested_budget_native > 0:
            suggested_budget = min(max(float(requested_budget_native), self.min_native), self.max_native)
        return {
            "schema": "nomad.counter_offer.v1",
            "decision": "counter_offer",
            "reason_code": error,
            "message": message,
            "hard_boundary_guard": self.hard_boundary_guard,
            "constraints": {
                "min_budget_native": round(float(self.min_native), 8),
                "max_budget_native": round(float(self.max_native), 8),
                "native_symbol": self.chain.native_symbol,
                "require_payment": bool(self.require_payment),
                "wallet_format": "0x-prefixed 40-hex address when supplied",
            },
            "suggested_payload": {
                "service_type": "custom",
                "budget_native": round(float(suggested_budget), 8),
                "requester_wallet": requester_wallet if self._looks_like_wallet(requester_wallet) else "",
                "problem": "Bounded issue statement with one measurable done condition.",
            },
            "next_action": "Resubmit with valid boundaries or request a smaller starter diagnosis path.",
        }

    def _hard_boundary_reject(
        self,
        *,
        error: str,
        message: str,
        requested_budget_native: Optional[float],
        requester_wallet: str,
    ) -> Dict[str, Any]:
        return {
            "mode": "agent_service_request",
            "deal_found": False,
            "ok": False,
            "error": error,
            "message": message,
            "counter_offer": self._counter_offer_payload(
                error=error,
                message=message,
                requested_budget_native=self._optional_float(requested_budget_native),
                requester_wallet=self._clean(requester_wallet),
            ),
        }

    def reputation_snapshot(self) -> Dict[str, Any]:
        tasks = list((self._load().get("tasks") or {}).values())
        total = len(tasks)
        by_status: Dict[str, int] = {}
        for task in tasks:
            status = str(task.get("status") or "unknown")
            by_status[status] = by_status.get(status, 0) + 1
        paid = int(by_status.get("paid", 0))
        delivered = int(by_status.get("delivered", 0))
        awaiting = int(by_status.get("awaiting_payment", 0))
        boundary_reliability = 1.0 if total == 0 else round((paid + delivered) / total, 4)
        return {
            "mode": "nomad_agent_reputation",
            "schema": "nomad.agent_reputation.v1",
            "ok": True,
            "generated_at": datetime.now(UTC).isoformat(),
            "hard_boundary_guard": bool(self.hard_boundary_guard),
            "totals": {
                "tasks": total,
                "awaiting_payment": awaiting,
                "paid": paid,
                "delivered": delivered,
            },
            "by_status": by_status,
            "signals": {
                "boundary_reliability": boundary_reliability,
                "payment_conversion_proxy": 0.0 if total == 0 else round((paid + delivered) / total, 4),
            },
            "analysis": "Reputation is contract-first: boundary compliance and payment progression are weighted over tone.",
        }

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
