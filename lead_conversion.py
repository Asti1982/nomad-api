import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from agent_contact import AgentContactOutbox
from agent_pain_solver import AgentPainSolver, normalize_pain_type
from agent_service import AgentServiceDesk
from lead_discovery import LeadDiscoveryScout
from nomad_guardrails import GuardrailDecision, NomadGuardrailEngine
from nomad_operator_grant import operator_allows, operator_grant


ROOT = Path(__file__).resolve().parent
DEFAULT_CONVERSION_STORE = ROOT / "nomad_lead_conversions.json"


MACHINE_ENDPOINT_HINTS = (
    "/.well-known/agent-card.json",
    "/.well-known/agent.json",
    "/a2a",
    "/direct",
    "/message",
    "/messages",
    "/webhook",
    "/inbox",
    "/tasks",
    "/service",
)

HUMAN_FACING_HOSTS = {
    "github.com",
    "www.github.com",
    "gitlab.com",
    "bitbucket.org",
    "discord.com",
    "discord.gg",
    "linkedin.com",
    "www.linkedin.com",
    "reddit.com",
    "x.com",
    "twitter.com",
    "t.me",
    "telegram.me",
}


class LeadConversionPipeline:
    """Convert public agent pain leads into safe help artifacts and customer-ready next steps."""

    def __init__(
        self,
        path: Optional[Path] = None,
        lead_discovery: Optional[LeadDiscoveryScout] = None,
        pain_solver: Optional[AgentPainSolver] = None,
        service_desk: Optional[AgentServiceDesk] = None,
        outbox: Optional[AgentContactOutbox] = None,
        guardrails: Optional[NomadGuardrailEngine] = None,
    ) -> None:
        self.path = path or DEFAULT_CONVERSION_STORE
        self.lead_discovery = lead_discovery or LeadDiscoveryScout()
        self.pain_solver = pain_solver or AgentPainSolver()
        self.service_desk = service_desk or AgentServiceDesk()
        self.outbox = outbox or AgentContactOutbox()
        self.guardrails = guardrails or NomadGuardrailEngine()

    def run(
        self,
        query: str = "",
        limit: int = 5,
        send: bool = False,
        approval: str = "",
        budget_hint_native: Optional[float] = None,
        leads: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        cap = max(1, min(int(limit or 5), 25))
        discovered = (
            {
                "mode": "lead_discovery",
                "leads": leads,
                "query": query,
                "candidate_count": len(leads or []),
                "qualified_count": len(leads or []),
                "errors": [],
            }
            if leads is not None
            else self.lead_discovery.scout_public_leads(query=query, limit=cap)
        )
        raw_leads = list(discovered.get("leads") or [])[:cap]
        if not raw_leads:
            explicit_lead = self._explicit_lead_from_query(query)
            if explicit_lead:
                raw_leads = [explicit_lead]
        conversions = [
            self.convert_lead(
                lead=lead,
                send=send,
                approval=approval,
                budget_hint_native=budget_hint_native,
            )
            for lead in raw_leads
        ]
        state = self._load()
        for conversion in conversions:
            state["conversions"][conversion["conversion_id"]] = conversion
        self._save(state)

        stats = self._stats(conversions)
        return {
            "mode": "lead_conversion_pipeline",
            "deal_found": False,
            "ok": True,
            "generated_at": datetime.now(UTC).isoformat(),
            "query": query,
            "send_requested": send,
            "approval": approval,
            "discovery": {
                "mode": discovered.get("mode"),
                "candidate_count": discovered.get("candidate_count", len(raw_leads)),
                "qualified_count": discovered.get("qualified_count", len(raw_leads)),
                "addressable_count": discovered.get("addressable_count", 0),
                "monetizable_count": discovered.get("monetizable_count", 0),
                "errors": discovered.get("errors") or [],
            },
            "stats": stats,
            "conversions": conversions,
            "policy": self.policy(),
            "analysis": (
                f"Nomad prepared {len(conversions)} lead conversion(s): "
                f"{stats.get('queued_agent_contact', 0)} queued for public agent endpoints, "
                f"{stats.get('sent_agent_contact', 0)} sent to public agent endpoints, "
                f"{stats.get('private_draft_needs_approval', 0)} private drafts need approval, "
                f"{stats.get('blocked_contact_policy', 0)} blocked by contact policy, "
                f"{stats.get('watchlist_low_fit', 0)} went to watchlist."
            ),
        }

    def convert_lead(
        self,
        lead: Dict[str, Any],
        send: bool = False,
        approval: str = "",
        budget_hint_native: Optional[float] = None,
    ) -> Dict[str, Any]:
        normalized = self._normalize_lead(lead)
        approval = self._approval_for_lead(normalized.get("url", ""), approval)
        service_type = normalize_pain_type(
            service_type=normalized.get("service_type"),
            problem=normalized.get("problem"),
        )
        score = self._conversion_score(normalized, service_type)
        agent_solution = self.pain_solver.solve(
            problem=normalized["problem"],
            service_type=service_type,
            source="lead_conversion",
            evidence=normalized.get("pain_evidence") or [],
        )["solution"]
        rescue_plan = self.service_desk.build_rescue_plan(
            problem=normalized["problem"],
            service_type=service_type,
            budget_native=budget_hint_native,
        )
        help_draft = self.lead_discovery.draft_first_help_action(
            lead,
            approval=approval,
        )
        route = self._route_for_lead(normalized, score, approval=approval)
        route_guardrail = self._route_guardrail(normalized, route, approval=approval)
        route["guardrail"] = route_guardrail.to_dict()
        if route_guardrail.decision == GuardrailDecision.DENY and route.get("action") == "queue_agent_contact":
            route = {
                "status": "private_draft_needs_approval",
                "action": "save_private_draft",
                "summary": "Guardrail denied direct contact; keep the rescue plan private until a safe endpoint or approval exists.",
                "approval_gate": "AGENT_ENDPOINT_URL=https://... or APPROVE_LEAD_HELP=draft_only",
                "guardrail": route_guardrail.to_dict(),
            }
        value_pack = self._build_value_pack(
            lead=normalized,
            score=score,
            route=route,
            agent_solution=agent_solution,
            rescue_plan=rescue_plan,
            budget_hint_native=budget_hint_native,
        )
        contact_result = None
        if route["action"] == "queue_agent_contact":
            contact_result = self.outbox.queue_contact(
                endpoint_url=route["endpoint_url"],
                problem=self._agent_contact_problem(value_pack),
                service_type=service_type,
                lead=lead,
                budget_hint_native=budget_hint_native,
            )
            if contact_result.get("ok") and send and not contact_result.get("duplicate"):
                contact_id = (contact_result.get("contact") or {}).get("contact_id", "")
                if contact_id:
                    contact_result = self.outbox.send_contact(contact_id)
            if contact_result.get("ok"):
                contact_status = (contact_result.get("contact") or {}).get("status", "")
                route["status"] = "sent_agent_contact" if contact_status in {"sent", "replied"} else "queued_agent_contact"
                route["contact_id"] = (contact_result.get("contact") or {}).get("contact_id", "")
                value_pack["route"]["status"] = route["status"]
                value_pack["route"]["contact_id"] = route["contact_id"]
            else:
                route["status"] = "blocked_contact_policy"
                route["reason"] = contact_result.get("reason") or contact_result.get("error") or "contact_blocked"
                value_pack["route"]["status"] = route["status"]
                value_pack["route"]["reason"] = route["reason"]

        conversion = {
            "conversion_id": self._conversion_id(normalized),
            "created_at": datetime.now(UTC).isoformat(),
            "status": route["status"],
            "lead": {
                "title": normalized.get("title"),
                "url": normalized.get("url"),
                "pain": normalized.get("pain"),
                "service_type": service_type,
                "monetizable_now": normalized.get("monetizable_now"),
                "addressable_now": normalized.get("addressable_now"),
            },
            "score": score,
            "route": route,
            "free_value": {
                "value_pack": value_pack,
                "agent_solution": agent_solution,
                "rescue_plan": rescue_plan,
                "private_help_draft": help_draft,
                "public_response_draft": self._public_response_draft(
                    normalized=normalized,
                    service_type=service_type,
                    agent_solution=agent_solution,
                    rescue_plan=rescue_plan,
                    route=route,
                )
                if route.get("action") in {"prepare_public_comment", "prepare_pr_plan"}
                else "",
            },
            "customer_next_step": self._customer_next_step(route, rescue_plan, value_pack),
            "contact_result": contact_result,
            "ledger": [
                {
                    "at": datetime.now(UTC).isoformat(),
                    "event": "conversion_prepared",
                    "status": route["status"],
                    "message": route["summary"],
                }
            ],
        }
        return conversion

    def list_conversions(
        self,
        statuses: Optional[List[str]] = None,
        limit: int = 25,
    ) -> Dict[str, Any]:
        normalized_statuses = {str(item).strip() for item in (statuses or []) if str(item).strip()}
        conversions = list((self._load().get("conversions") or {}).values())
        if normalized_statuses:
            conversions = [
                item for item in conversions
                if str(item.get("status") or "") in normalized_statuses
            ]
        conversions.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        limited = conversions[: max(1, min(int(limit or 25), 100))]
        return {
            "mode": "lead_conversion_list",
            "deal_found": False,
            "ok": True,
            "statuses": sorted(normalized_statuses),
            "stats": self._stats(conversions),
            "conversions": limited,
            "analysis": f"Listed {len(limited)} lead conversion(s).",
        }

    def policy(self) -> Dict[str, Any]:
        return {
            "default": "free_value_first",
            "safe_without_approval": [
                "inspect public lead metadata",
                "generate nomad.agent_value_pack.v1",
                "generate nomad.agent_solution.v1",
                "generate nomad.rescue_plan.v1",
                "queue contact to public machine-readable agent endpoints",
            ],
            "requires_explicit_approval": [
                "human-facing GitHub comments",
                "pull requests",
                "human DMs or email",
                "private communities",
                "login, CAPTCHA, or access-control steps",
                "spending or staking funds",
            ],
            "conversion_goal": (
                "Turn visible pain into immediate help, then ask for PLAN_ACCEPTED=true or one missing fact "
                "before creating paid work."
            ),
        }

    def _normalize_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        title = self._clean(lead.get("title") or lead.get("name") or "agent lead")
        pain = self._clean(lead.get("pain") or lead.get("pain_signal") or "")
        first_help = self._clean(lead.get("first_help_action") or "")
        problem_parts = [title, pain, first_help]
        problem = " ".join(part for part in problem_parts if part).strip() or title
        return {
            "raw": lead,
            "title": title,
            "url": self._clean(lead.get("url") or lead.get("html_url") or lead.get("source_url") or ""),
            "pain": pain or "visible agent infrastructure pain",
            "problem": problem,
            "service_type": self._clean(lead.get("recommended_service_type") or lead.get("service_type") or ""),
            "addressable_now": bool(lead.get("addressable_now")),
            "monetizable_now": bool(lead.get("monetizable_now")),
            "buyer_intent_terms": list(lead.get("buyer_intent_terms") or []),
            "pain_terms": list(lead.get("pain_terms") or []),
            "pain_evidence": [
                self._pain_evidence_text(item)
                for item in (lead.get("pain_evidence") or [])
                if self._pain_evidence_text(item)
            ],
            "endpoint_url": self._candidate_endpoint(lead),
        }

    def _conversion_score(self, lead: Dict[str, Any], service_type: str) -> Dict[str, Any]:
        score = 0
        reasons: List[str] = []
        if lead.get("pain") or lead.get("pain_terms") or lead.get("pain_evidence"):
            score += 3
            reasons.append("concrete_pain_signal")
        if lead.get("url"):
            score += 3
            reasons.append("publicly_verifiable")
        if service_type:
            score += 2
            reasons.append(f"solution_pattern:{service_type}")
        if lead.get("endpoint_url"):
            score += 2
            reasons.append("public_machine_endpoint")
        if lead.get("monetizable_now") or lead.get("buyer_intent_terms"):
            score += 2
            reasons.append("buyer_intent")
        if lead.get("addressable_now"):
            score += 1
            reasons.append("addressable_now")
        if self._is_human_facing_url(lead.get("url", "")) and not lead.get("endpoint_url"):
            reasons.append("human_facing_requires_approval")
        fit = "strong" if score >= 9 else "medium" if score >= 6 else "watchlist"
        return {
            "value": score,
            "fit": fit,
            "reasons": reasons,
        }

    def _route_for_lead(self, lead: Dict[str, Any], score: Dict[str, Any], approval: str = "") -> Dict[str, Any]:
        endpoint = lead.get("endpoint_url") or ""
        approval = (approval or "draft_only").strip().lower()
        if score["fit"] == "watchlist":
            return {
                "status": "watchlist_low_fit",
                "action": "watchlist",
                "summary": "Lead has insufficient conversion signal; keep it as market intelligence.",
            }
        if endpoint:
            return {
                "status": "ready_to_queue_agent_contact",
                "action": "queue_agent_contact",
                "endpoint_url": endpoint,
                "summary": "Public machine-readable endpoint can receive bounded agent-first help.",
                "operator_grant": operator_grant() if operator_allows("agent_endpoint_contact") else {"enabled": False},
            }
        if self._is_human_facing_url(lead.get("url", "")):
            if approval in {"comment", "public_comment"}:
                return {
                    "status": "public_comment_approved",
                    "action": "prepare_public_comment",
                    "summary": "Human-facing lead approved for one public, value-first comment.",
                    "approval": approval,
                    "approval_gate": "",
                    "operator_grant": operator_grant() if operator_allows("lead_conversion") else {"enabled": False},
                }
            if approval in {"pr", "pull_request", "pr_plan"}:
                return {
                    "status": "public_pr_plan_approved",
                    "action": "prepare_pr_plan",
                    "summary": "Human-facing lead approved for a public PR/repro plan.",
                    "approval": approval,
                    "approval_gate": "",
                    "operator_grant": operator_grant() if operator_allows("lead_conversion") else {"enabled": False},
                }
            return {
                "status": "private_draft_needs_approval",
                "action": "save_private_draft",
                "summary": "Human-facing lead: keep help private until explicit approval allows comment or PR plan.",
                "approval_gate": "APPROVE_LEAD_HELP=comment or APPROVE_LEAD_HELP=pr_plan",
                "operator_grant": operator_grant() if operator_allows("lead_conversion") else {"enabled": False},
                "operator_allowed_private_actions": [
                    "score lead",
                    "create free value pack",
                    "productize reusable private offer",
                ],
            }
        return {
            "status": "private_draft_needs_approval",
            "action": "save_private_draft",
            "summary": "No safe direct endpoint found; keep the rescue plan private and ask for one contactable agent endpoint.",
            "approval_gate": "AGENT_ENDPOINT_URL=https://... or APPROVE_LEAD_HELP=draft_only",
            "operator_grant": operator_grant() if operator_allows("lead_conversion") else {"enabled": False},
            "operator_allowed_private_actions": [
                "score lead",
                "create free value pack",
                "productize reusable private offer",
            ],
        }

    def _route_guardrail(self, lead: Dict[str, Any], route: Dict[str, Any], approval: str = ""):
        if route.get("action") == "queue_agent_contact":
            return self.guardrails.evaluate(
                action="agent_contact.queue",
                args={
                    "endpoint_url": route.get("endpoint_url", ""),
                    "problem": lead.get("problem", ""),
                    "service_type": lead.get("service_type", ""),
                    "lead": lead,
                },
            )
        if self._is_human_facing_url(lead.get("url", "")):
            return self.guardrails.evaluate(
                action="lead.public_comment",
                args={
                    "url": lead.get("url", ""),
                    "problem": lead.get("problem", ""),
                    "lead": lead,
                    "approval": approval or route.get("approval", ""),
                },
                approval=approval or route.get("approval", ""),
            )
        return self.guardrails.evaluate(
            action="lead.private_draft",
            args={
                "url": lead.get("url", ""),
                "problem": lead.get("problem", ""),
                "lead": lead,
            },
        )

    def _customer_next_step(
        self,
        route: Dict[str, Any],
        rescue_plan: Dict[str, Any],
        value_pack: Dict[str, Any],
    ) -> Dict[str, Any]:
        if route.get("contact_id"):
            return {
                "ask": "Wait for the agent response, then convert PLAN_ACCEPTED=true into a service task.",
                "expected_reply": "PLAN_ACCEPTED=true plus FACT_URL, ERROR, APPROVAL_GRANTED, or budget_native.",
                "contact_id": route["contact_id"],
                "value_pack_id": value_pack.get("pack_id", ""),
            }
        if route.get("action") == "save_private_draft":
            return {
                "ask": "Get explicit approval before any human-facing post, or provide a public agent endpoint.",
                "expected_reply": route.get("approval_gate", "APPROVE_LEAD_HELP=draft_only"),
                "required_input": rescue_plan.get("required_input", ""),
                "value_pack_id": value_pack.get("pack_id", ""),
            }
        if route.get("action") in {"prepare_public_comment", "prepare_pr_plan"}:
            return {
                "ask": "Publish the approved value-first response, then wait for maintainer interest before any paid follow-up.",
                "expected_reply": "MAINTAINER_INTEREST=true, FACT_URL=https://..., or PLAN_ACCEPTED=true",
                "required_input": rescue_plan.get("required_input", ""),
                "value_pack_id": value_pack.get("pack_id", ""),
            }
        return {
            "ask": "Collect one stronger pain or buyer-intent signal before outreach.",
            "expected_reply": "LEAD_URL=https://... or AGENT_ENDPOINT_URL=https://...",
            "required_input": rescue_plan.get("required_input", ""),
            "value_pack_id": value_pack.get("pack_id", ""),
        }

    def _build_value_pack(
        self,
        lead: Dict[str, Any],
        score: Dict[str, Any],
        route: Dict[str, Any],
        agent_solution: Dict[str, Any],
        rescue_plan: Dict[str, Any],
        budget_hint_native: Optional[float],
    ) -> Dict[str, Any]:
        service_type = str(agent_solution.get("pain_type") or rescue_plan.get("service_type") or "custom")
        safe_now = [str(item) for item in (rescue_plan.get("safe_now") or [])[:3]]
        acceptance = [str(item) for item in (rescue_plan.get("acceptance_criteria") or [])[:3]]
        guardrail = agent_solution.get("guardrail") or {}
        doctor = agent_solution.get("reliability_doctor") or {}
        commercial = rescue_plan.get("commercial_next_step") or {}
        pack_id = self._value_pack_id(lead, service_type)
        return {
            "schema": "nomad.agent_value_pack.v1",
            "pack_id": pack_id,
            "created_at": datetime.now(UTC).isoformat(),
            "audience": "ai_agent",
            "lead": {
                "title": lead.get("title", ""),
                "url": lead.get("url", ""),
                "pain": lead.get("pain", ""),
                "service_type": service_type,
                "fit": score.get("fit", ""),
                "fit_reasons": score.get("reasons", []),
            },
            "painpoint_question": self._painpoint_question(service_type),
            "pain_hypothesis": {
                "type": service_type,
                "diagnosis": rescue_plan.get("diagnosis", ""),
                "solution_title": agent_solution.get("title", ""),
                "guardrail_id": guardrail.get("id", ""),
                "doctor_role": doctor.get("title", ""),
                "doctor_role_id": doctor.get("id", ""),
                "framework_inspiration": doctor.get("framework_inspiration", ""),
            },
            "immediate_value": {
                "safe_now": safe_now,
                "required_input": rescue_plan.get("required_input", ""),
                "acceptance_criteria": acceptance,
                "verifier": self._value_pack_verifier(service_type),
                "critic_rubric": agent_solution.get("critic_rubric") or [],
            },
            "reliability_doctor": {
                "role": doctor,
                "loop": agent_solution.get("reliability_loop") or {},
                "fix_contract": agent_solution.get("fix_contract") or {},
                "healing_memory": agent_solution.get("healing_memory") or {},
            },
            "reply_contract": {
                "accept": "PLAN_ACCEPTED=true",
                "facts": ["FACT_URL=https://...", "ERROR=<exact error>", "APPROVAL_GRANTED=<scope>"],
                "budget": "budget_native=<amount> when the requester wants paid execution",
                "do_not_send": ["raw secrets", "private credentials", "human-posting permission by implication"],
            },
            "paid_upgrade": {
                "trigger": "Reply with PLAN_ACCEPTED=true plus one fact or budget_native.",
                "service_type": service_type,
                "price_native": commercial.get("price_native") or budget_hint_native,
                "delivery": commercial.get("delivery", "bounded draft-only rescue artifact"),
                "boundary": "Paid work does not authorize public posting, private access, spend, or human impersonation.",
            },
            "route": {
                "status": route.get("status", ""),
                "action": route.get("action", ""),
                "endpoint_url": route.get("endpoint_url", ""),
                "approval_gate": route.get("approval_gate", ""),
                "guardrail": route.get("guardrail") or {},
            },
            "nomad_self_apply": self._self_apply_from_solution(agent_solution),
            "machine_summary": (
                f"Nomad Value Pack {pack_id}: {service_type} -> "
                f"{agent_solution.get('title', 'agent rescue')} with {len(safe_now)} safe step(s)."
            ),
        }

    def _approval_for_lead(self, lead_url: str, approval: str = "") -> str:
        explicit = (approval or "").strip().lower()
        if explicit:
            return explicit
        allowed_urls = [
            item.strip()
            for item in (os.getenv("NOMAD_PUBLIC_LEAD_APPROVAL_URLS") or "").split(",")
            if item.strip()
        ]
        if lead_url and any(lead_url.rstrip("/") == item.rstrip("/") for item in allowed_urls):
            return (os.getenv("NOMAD_PUBLIC_LEAD_APPROVAL_SCOPE") or "comment").strip().lower() or "comment"
        return "draft_only"

    def _public_response_draft(
        self,
        normalized: Dict[str, Any],
        service_type: str,
        agent_solution: Dict[str, Any],
        rescue_plan: Dict[str, Any],
        route: Dict[str, Any],
    ) -> str:
        title = normalized.get("title") or "this issue"
        url = normalized.get("url") or ""
        guardrail = (agent_solution.get("guardrail") or {}).get("id") or "nomad_guardrail"
        safe_now = rescue_plan.get("safe_now") or []
        acceptance = rescue_plan.get("acceptance_criteria") or []
        if route.get("action") == "prepare_pr_plan":
            return "\n".join(
                [
                    f"Draft PR/repro plan for {title}",
                    f"Source: {url}",
                    "",
                    "1. Add the smallest fixture for one intercepted tool call.",
                    "2. Verify ALLOW preserves the args and still calls the tool.",
                    "3. Verify MODIFY revalidates modified args before execution.",
                    "4. Verify DENY prevents execution and returns a structured denial/audit record.",
                    f"Guardrail pattern: {guardrail}.",
                ]
            ).strip()
        return "\n".join(
            [
                f"I think {title} becomes easiest to evaluate if the first slice is a tiny fixture-backed tool-call boundary.",
                "",
                "Concrete diagnostic frame:",
                f"- Classify this as `{service_type}` at the exact pre-execution point, before the tool mutates state.",
                "- Start with one FunctionTool/BaseTool fixture and one Workbench/MCP-style fixture; keep the provider protocol the same for both.",
                "- Treat `MODIFY` as important as `DENY`: after a provider rewrites args, run normal args validation again before execution.",
                "- Avoid returning a plain string for DENY if the caller expects the tool return type; prefer the existing structured error/result path, with reason and metadata attached.",
                "",
                "Smallest useful test pack:",
                "1. ALLOW calls the underlying tool with unchanged args.",
                "2. MODIFY changes args, then the tool receives only the revalidated effective args.",
                "3. DENY never calls the tool and preserves `tool_name`, `call_id`, provider id, reason, and audit metadata.",
                "",
                "That would make the architecture discussion concrete without committing AutoGen to the full workbench/agent-level surface in the first PR.",
                f"Nomad guardrail pattern: `{guardrail}`. Safe next steps: {'; '.join(str(item) for item in safe_now[:2]) or 'draft a fixture-backed plan'}. Done when: {'; '.join(str(item) for item in acceptance[:2]) or 'the denied tool is not executed'}.",
            ]
        ).strip()

    def _agent_contact_problem(self, value_pack: Dict[str, Any]) -> str:
        immediate = value_pack.get("immediate_value") or {}
        hypothesis = value_pack.get("pain_hypothesis") or {}
        paid = value_pack.get("paid_upgrade") or {}
        reply = value_pack.get("reply_contract") or {}
        lines = [
            "nomad.agent_value_pack.v1",
            "audience=ai_agent",
            f"value_pack_id={value_pack.get('pack_id', '')}",
            f"pain_type={hypothesis.get('type', '')}",
            f"painpoint_question={value_pack.get('painpoint_question', '')}",
            f"diagnosis={hypothesis.get('diagnosis', '')}",
            f"free_solution={hypothesis.get('solution_title', '')}",
            f"guardrail={hypothesis.get('guardrail_id', '')}",
            f"safe_now={' | '.join(str(item) for item in (immediate.get('safe_now') or [])[:2])}",
            f"required_input={immediate.get('required_input', '')}",
            f"verifier={immediate.get('verifier', '')}",
            f"conversion={reply.get('accept', 'PLAN_ACCEPTED=true')} with one missing fact or budget_native",
            f"paid_upgrade={paid.get('delivery', '')}",
            "bounds=no_human_impersonation_no_public_posting_no_unscoped_secrets",
        ]
        return "\n".join(lines)

    @staticmethod
    def _painpoint_question(service_type: str) -> str:
        questions = {
            "compute_auth": "What exact provider, model, token scope, quota, or auth error is blocking your next run?",
            "loop_break": "Which retry/tool step repeats, and what state must be preserved before breaking the loop?",
            "human_in_loop": "Which human approval is missing, and what exact safe scope should the operator approve?",
            "mcp_integration": "Which MCP tool contract, argument schema, or response shape is failing?",
            "repo_issue_help": "Which public issue, error, or repro step should be turned into a safe draft-only fix plan?",
            "payment": "Which payment, callback, or idempotency step is preventing completion?",
            "memory": "Which durable fact, decision, constraint, or outcome should the agent remember safely?",
        }
        return questions.get(
            service_type,
            "What is the smallest current blocker, and what public fact can Nomad use to verify a safe next step?",
        )

    @staticmethod
    def _value_pack_verifier(service_type: str) -> str:
        verifiers = {
            "compute_auth": "Run one provider-scope check without exposing token values, then try the cheapest fallback lane.",
            "loop_break": "Pause retries, snapshot state, and confirm the next run exits after the configured retry budget.",
            "human_in_loop": "Confirm the approval scope, actor, expiry, and forbidden actions before resuming autonomy.",
            "mcp_integration": "Validate one tool call against its JSON schema and record the first mismatch.",
            "repo_issue_help": "Verify the draft against the public issue facts before any human-facing post.",
            "payment": "Check reference, amount, recipient, chain, duplicate use, and callback idempotency.",
            "memory": "Store only non-secret durable memory with type, source, expiry, and retrieval condition.",
        }
        return verifiers.get(service_type, "Verify one public fact and one acceptance criterion before execution.")

    @staticmethod
    def _self_apply_from_solution(agent_solution: Dict[str, Any]) -> Dict[str, Any]:
        self_apply = agent_solution.get("nomad_self_apply") or {}
        if isinstance(self_apply, dict) and self_apply:
            return self_apply
        return {
            "action": "Convert this lead's blocker into a reusable Nomad checklist after a successful solve.",
            "pattern": agent_solution.get("title", "agent pain solution"),
        }

    def _candidate_endpoint(self, lead: Dict[str, Any]) -> str:
        candidates = [
            lead.get("endpoint_url"),
            lead.get("agent_endpoint"),
            lead.get("agent_card_url"),
            lead.get("a2a_url"),
            lead.get("contact_url"),
            lead.get("service_url"),
            lead.get("url"),
        ]
        for candidate in candidates:
            endpoint = self._clean(candidate)
            if endpoint and self._looks_machine_endpoint(endpoint):
                return endpoint
        return ""

    def _explicit_lead_from_query(self, query: str) -> Dict[str, Any]:
        text = self._clean(query)
        if not text or not re.search(r"https?://|URL=|LEAD_URL=", text, flags=re.IGNORECASE):
            return {}
        url_match = re.search(r"\b(?:URL|LEAD_URL)=([^\s]+)", text, flags=re.IGNORECASE)
        if not url_match:
            url_match = re.search(r"https?://[^\s]+", text)
        pain_match = re.search(
            r"\bPain=(.*?)(?:\s+Nomad task:|\s+Task:|\s+type=|\s+service_type=|$)",
            text,
            flags=re.IGNORECASE,
        )
        title_match = re.search(
            r"\bLead:\s*(.*?)(?:\s+URL=|\s+LEAD_URL=|\s+Pain=|\s+Task:|\s+Nomad task:|$)",
            text,
            flags=re.IGNORECASE,
        )
        service_match = re.search(r"\b(?:type|service_type)=([A-Za-z0-9_-]+)", text, flags=re.IGNORECASE)
        url = url_match.group(1).strip() if url_match else ""
        title = title_match.group(1).strip() if title_match and title_match.group(1).strip() else "Explicit agent lead"
        pain = pain_match.group(1).strip() if pain_match else "visible agent infrastructure pain"
        return {
            "title": title,
            "url": url,
            "pain": pain,
            "recommended_service_type": service_match.group(1).strip() if service_match else "",
            "addressable_now": True,
            "monetizable_now": False,
            "pain_terms": [
                item.strip().lower()
                for item in re.split(r"[,;]+", pain)
                if item.strip()
            ],
            "pain_evidence": [
                {"term": item.strip().lower()}
                for item in re.split(r"[,;]+", pain)
                if item.strip()
            ],
            "first_help_action": "Prepare a private free-value rescue plan and do not post publicly without approval.",
        }

    def _looks_machine_endpoint(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        if (parsed.hostname or "").lower() in HUMAN_FACING_HOSTS:
            return False
        path = parsed.path.lower()
        return any(hint in path for hint in MACHINE_ENDPOINT_HINTS)

    @staticmethod
    def _is_human_facing_url(url: str) -> bool:
        parsed = urlparse(url)
        return (parsed.hostname or "").lower() in HUMAN_FACING_HOSTS

    @staticmethod
    def _conversion_id(lead: Dict[str, Any]) -> str:
        seed = "|".join(
            [
                lead.get("url", ""),
                lead.get("title", ""),
                lead.get("pain", ""),
                datetime.now(UTC).isoformat(),
            ]
        )
        return f"conv-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"

    @staticmethod
    def _value_pack_id(lead: Dict[str, Any], service_type: str) -> str:
        seed = "|".join(
            [
                lead.get("url", ""),
                lead.get("title", ""),
                lead.get("pain", ""),
                service_type,
            ]
        )
        return f"avp-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"

    @staticmethod
    def _stats(conversions: List[Dict[str, Any]]) -> Dict[str, int]:
        stats: Dict[str, int] = {}
        for conversion in conversions:
            status = str(conversion.get("status") or "unknown")
            stats[status] = stats.get(status, 0) + 1
        return stats

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"conversions": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"conversions": {}}
            payload.setdefault("conversions", {})
            return payload
        except Exception:
            return {"conversions": {}}

    def _save(self, state: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _pain_evidence_text(item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("term") or item.get("evidence") or "").strip()
        return str(item or "").strip()
