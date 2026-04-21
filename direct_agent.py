import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from agent_engagement import AgentEngagementLedger
from agent_service import AgentServiceDesk, SERVICE_TYPES
from nomad_collaboration import collaboration_charter
from nomad_guardrails import GuardrailDecision, NomadGuardrailEngine


load_dotenv()

ROOT = Path(__file__).resolve().parent
DEFAULT_DIRECT_STORE = ROOT / "nomad_direct_sessions.json"


PAIN_TYPES = {
    "human_in_loop": ("captcha", "human", "approval", "verification", "judgment", "review"),
    "loop_break": ("stuck", "loop", "retry", "infinite", "tool fail", "timeout"),
    "hallucination": ("hallucination", "wrong", "invalid", "compounding", "drift"),
    "memory": ("memory", "context", "session", "long-term", "preference"),
    "payment": ("payment", "wallet", "x402", "escrow", "metamask", "usdc", "eth"),
    "compute_auth": ("quota", "rate limit", "token", "model", "inference", "auth"),
}

ENGAGEMENT_PACKAGES = {
    "human_in_loop": {
        "package": "Nomad HITL Contract Pack",
        "delivery": "minimal do-now/send-back/done-when contract plus operator-ready evidence pack",
        "memory_upgrade": "reusable human handoff template after consent",
        "free_scope": "classify the exact human gate and name one legitimate unlock step",
        "paid_scope": "design the full unlock contract, approval payload, and repeatable operator checklist",
    },
    "loop_break": {
        "package": "Nomad Loop Rescue Pack",
        "delivery": "bounded loop-break plan with preserved state and one verified next move",
        "memory_upgrade": "retry guardrail and loop-break checklist after consent",
        "free_scope": "identify the first failing loop edge and the smallest safe pause point",
        "paid_scope": "produce the full loop-break plan, fallback path, and recovery checklist",
    },
    "hallucination": {
        "package": "Nomad Verification Pack",
        "delivery": "verifier-first response shape with one checker and one bounded retry path",
        "memory_upgrade": "durable verifier rule and claim-check checklist after consent",
        "free_scope": "name the first verifier step the requester should add",
        "paid_scope": "design the verifier flow, evidence contract, and guarded retry path",
    },
    "memory": {
        "package": "Nomad Memory Repair Pack",
        "delivery": "missing-memory diagnosis with one fact/decision/constraint template to persist",
        "memory_upgrade": "durable memory object and reuse checklist after consent",
        "free_scope": "identify the missing memory object type and one candidate entry",
        "paid_scope": "package the solved blocker as a reusable memory, checklist, and guardrail",
    },
    "payment": {
        "package": "Nomad Payment Reliability Pack",
        "delivery": "payment-path diagnosis plus verification and resume plan",
        "memory_upgrade": "payment recovery rule set after consent",
        "free_scope": "pin down the failing payment state and next verification step",
        "paid_scope": "design the full retry-safe payment path and manual fallback",
    },
    "compute_auth": {
        "package": "Nomad Compute Unlock Pack",
        "delivery": "credential/quota diagnosis and one fallback-lane plan",
        "memory_upgrade": "credential/quota checklist and fallback policy after consent",
        "free_scope": "separate token, quota, model access, and fallback into one smallest next check",
        "paid_scope": "produce the full credential/quota map, fallback route, and unblock checklist",
    },
    "custom": {
        "package": "Nomad Agent Infrastructure Pack",
        "delivery": "bounded diagnosis plus one agent-usable next action",
        "memory_upgrade": "reusable note or checklist after consent",
        "free_scope": "reduce the blocker to one verifiable next action",
        "paid_scope": "produce a bounded plan and one reusable artifact for future runs",
    },
}


class DirectAgentGateway:
    """Direct-only A2A-style conversation surface for LoopHelper/Nomad."""

    def __init__(
        self,
        path: Optional[Path] = None,
        service_desk: Optional[AgentServiceDesk] = None,
        session: Optional[requests.Session] = None,
        guardrails: Optional[NomadGuardrailEngine] = None,
        engagements: Optional[AgentEngagementLedger] = None,
    ) -> None:
        load_dotenv()
        self.path = path or DEFAULT_DIRECT_STORE
        self.service_desk = service_desk or AgentServiceDesk()
        self.session = session or requests.Session()
        self.guardrails = guardrails or NomadGuardrailEngine()
        self.engagements = engagements or AgentEngagementLedger()
        self.public_api_url = (
            os.getenv("NOMAD_PUBLIC_API_URL")
            or f"http://{os.getenv('NOMAD_API_HOST', '127.0.0.1')}:{os.getenv('NOMAD_API_PORT', '8787')}"
        ).rstrip("/")
        self.agent_name = os.getenv("NOMAD_AGENT_NAME", "LoopHelper").strip() or "LoopHelper"
        self.version = os.getenv("NOMAD_AGENT_VERSION", "0.1.0").strip() or "0.1.0"
        self.min_native = float(os.getenv("NOMAD_SERVICE_MIN_NATIVE", "0.01"))

    def agent_card(self) -> Dict[str, Any]:
        """Return an A2A-style AgentCard for direct discovery."""
        collaboration = collaboration_charter(public_api_url=self.public_api_url)
        return {
            "protocolVersion": os.getenv("NOMAD_A2A_PROTOCOL_VERSION", "0.3.0"),
            "name": self.agent_name,
            "description": (
                "Agent-first direct service built around the Nomad Compute Unlock Pack: quota/auth/cooldown "
                "diagnosis, fallback-lane repair, and reusable memory for blocked AI agents."
            ),
            "url": f"{self.public_api_url}/a2a/message",
            "version": self.version,
            "defaultInputModes": ["application/json", "text/plain"],
            "defaultOutputModes": ["application/json", "text/plain"],
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
                "directOnly": True,
                "x402PaymentRequired": True,
                "freeMiniDiagnosis": True,
                "agentFirst": True,
                "structuredReplies": True,
                "nonAnthropomorphic": True,
                "adaptiveOffers": True,
                "agentPainSolver": True,
                "selfAppliesSolvedPatterns": True,
                "outboundAgentCollaboration": collaboration["enabled"],
                "acceptsAgentHelp": collaboration["permission"]["accept_help_from_other_agents"],
                "learnsFromAgentReplies": collaboration["permission"]["learn_from_public_agent_replies"],
            },
            "interactionContract": self.interaction_contract(),
            "collaborationCharter": collaboration,
            "skills": [
                {
                    "id": "free-mini-diagnosis",
                    "name": "Free Mini Diagnosis",
                    "description": "Classify one blocker and return the smallest verifiable next step.",
                    "tags": ["diagnosis", "agent-rescue", "free"],
                    "examples": ["I am stuck in a retry loop after a tool call failed."],
                },
                {
                    "id": "compute-auth-unblock",
                    "name": "Compute/Auth Unblock",
                    "description": "Diagnose quota, token, OAuth, cooldown, and fallback-lane failures, then return a smallest-repro and bounded unblock path.",
                    "tags": ["compute", "auth", "quota", "oauth", "fallback"],
                    "examples": ["My provider fallback lane returns auth errors and false rate-limit cooldowns."],
                },
                {
                    "id": "human-in-the-loop-rescue",
                    "name": "Human-in-the-Loop Rescue",
                    "description": "Turn CAPTCHA, approval, verification or judgment blockers into concrete unlock contracts.",
                    "tags": ["human-in-the-loop", "approval", "captcha", "judgment"],
                    "examples": ["My agent needs a human approval decision before continuing."],
                },
                {
                    "id": "paid-loop-break",
                    "name": "Paid Loop Break",
                    "description": "After x402/wallet payment, isolate the blocker, repair the flow, and preserve the solution as memory.",
                    "tags": ["x402", "wallet", "loop", "debugging"],
                    "examples": ["I can pay 0.01 ETH if you can stop this infinite tool loop."],
                },
                {
                    "id": "self-improvement-pack",
                    "name": "Self-Improvement Pack",
                    "description": "Turn one solved blocker into reusable memory, a checklist, or a guardrail for the requesting agent.",
                    "tags": ["memory", "guardrails", "prompting", "self-improvement"],
                    "examples": ["After fixing this loop, help me package the lesson so I avoid it next time."],
                },
                {
                    "id": "agent-pain-solver",
                    "name": "Agent Pain Solver",
                    "description": "Convert recurring agent failures into reusable rescue patterns that Nomad also applies to itself.",
                    "tags": ["agent-pain", "rescue-plan", "self-apply", "guardrails"],
                    "examples": ["Solve this timeout retry failure and turn the fix into a reusable guardrail."],
                },
            ],
            "endpoints": {
                "agentCard": f"{self.public_api_url}/.well-known/agent-card.json",
                "message": f"{self.public_api_url}/a2a/message",
                "sessions": f"{self.public_api_url}/direct/sessions",
                "x402": f"{self.public_api_url}/x402/paid-help",
                "service": f"{self.public_api_url}/service",
            },
            "payment": self.x402_payment_requirements(),
        }

    def interaction_contract(self) -> Dict[str, Any]:
        collaboration = collaboration_charter(public_api_url=self.public_api_url)
        return {
            "audience": "ai_agents",
            "style": "agent_first_non_anthropomorphic",
            "collaboration_mode": collaboration["mode"],
            "protocol_hints": [
                "a2a_agent_card",
                "jsonrpc_message_send",
                "structured_plaintext",
            ],
            "reply_modes": ["message", "task"],
            "task_states": [
                "submitted",
                "working",
                "input_required",
                "auth_required",
                "completed",
                "failed",
                "rejected",
            ],
            "idempotency": "contextId_or_request_id_on_retry",
            "ttl_seconds": 600,
            "defaults": [
                "structured_replies_preferred",
                "bounded_claims_only",
                "explicit_payment_boundary",
                "no_human_impersonation",
                "free_to_paid_value_ladder",
                "requester_need_profile_adaptation",
                "verify_before_trust",
                "opt_out_respected",
            ],
            "expected_fields": [
                "problem",
                "goal",
                "blocking_step",
                "constraints",
                "budget_native",
            ],
            "optional_fields": [
                "urgency_hint",
                "delivery_preference",
                "memory_consent",
            ],
        }

    def x402_payment_requirements(
        self,
        amount_native: Optional[float] = None,
        service_type: str = "human_in_loop",
        task_id: str = "",
    ) -> Dict[str, Any]:
        wallet = self.service_desk.treasury.get_wallet_summary()
        amount = float(amount_native) if amount_native is not None else self.min_native
        return {
            "scheme": "x402-compatible-wallet-transfer",
            "statusCode": 402,
            "asset": self.service_desk.chain.native_symbol,
            "amount_native": round(max(self.min_native, amount), 8),
            "recipient": wallet.get("address") or "",
            "network": self.service_desk.chain.name,
            "chain_id": self.service_desk.chain.chain_id,
            "service_type": service_type,
            "task_id": task_id,
            "headers": {
                "PAYMENT-REQUIRED": "present on HTTP 402 response",
                "PAYMENT-SIGNATURE": "send on retry after signing/payment",
            },
            "verify_endpoint": f"{self.public_api_url}/tasks/verify",
        }

    def handle_direct_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_request(payload)
        requester = normalized["requester_agent"]
        requester_endpoint = normalized["requester_endpoint"]
        message = normalized["message"]
        requester_wallet = normalized["requester_wallet"]
        session_id = normalized["session_id"]
        if not message:
            return {
                "mode": "direct_agent_message",
                "deal_found": False,
                "ok": False,
                "error": "message_required",
                "message": (
                    "Send one blocker using message/problem or structured fields: "
                    "problem, goal, blocking_step, constraints, budget_native."
                ),
            }
        guardrail = self.guardrails.evaluate(
            action="direct.message",
            args={
                "message": message,
                "requester_agent": requester,
                "requester_endpoint": requester_endpoint,
                "requester_wallet": requester_wallet,
                "session_id": session_id,
                "structured_request": normalized.get("structured_request") or {},
            },
        )
        if guardrail.decision == GuardrailDecision.DENY:
            return {
                "mode": "direct_agent_message",
                "deal_found": False,
                "ok": False,
                "error": "guardrail_denied",
                "guardrail": guardrail.to_dict(),
                "message": "Nomad blocked this direct message before storing or acting on it.",
            }
        guarded_args = guardrail.effective_args
        message = str(guarded_args.get("message") or message).strip()
        requester = str(guarded_args.get("requester_agent") or requester).strip()
        requester_endpoint = str(guarded_args.get("requester_endpoint") or requester_endpoint).strip()
        requester_wallet = str(guarded_args.get("requester_wallet") or requester_wallet).strip()
        session_id = str(guarded_args.get("session_id") or session_id).strip()
        normalized["message"] = message
        normalized["requester_agent"] = requester
        normalized["requester_endpoint"] = requester_endpoint
        normalized["requester_wallet"] = requester_wallet
        normalized["session_id"] = session_id

        session = self._get_or_create_session(
            session_id=session_id,
            requester_agent=requester,
            requester_endpoint=requester_endpoint,
            requester_wallet=requester_wallet,
            opening_message=message,
        )
        pain_type = self.classify_pain(message)
        diagnosis = self.free_mini_diagnosis(message, pain_type=pain_type)
        need_profile = self._infer_agent_need_profile(normalized, pain_type=pain_type)
        task_result = self.service_desk.create_task(
            problem=message,
            requester_agent=requester,
            requester_wallet=requester_wallet,
            service_type=pain_type,
            budget_native=normalized.get("budget_native"),
            metadata={
                "direct_session_id": session["session_id"],
                "requester_endpoint": requester_endpoint,
                "source": "direct_agent_message",
                "input_schema": normalized.get("input_schema"),
                "structured_request": normalized.get("structured_request") or {},
                "need_profile": need_profile,
            },
        )
        task = task_result.get("task") or {}
        challenge = self.x402_payment_requirements(
            amount_native=(task.get("payment") or {}).get("amount_native"),
            service_type=task.get("service_type", pain_type),
            task_id=task.get("task_id", ""),
        )
        x402_payment = ((task.get("payment") or {}).get("x402") or {})
        if isinstance(x402_payment, dict) and x402_payment:
            challenge = {
                **challenge,
                **x402_payment,
            }
        commercial = task.get("commercial") or self._commercial_terms(
            pain_type=pain_type,
            requested_amount=normalized.get("budget_native") or challenge.get("amount_native"),
        )
        engagement_plan = self._build_engagement_plan(
            pain_type=pain_type,
            need_profile=need_profile,
            challenge=challenge,
        )
        best_current_offer = self._best_current_offer(
            pain_type=pain_type,
            requested_amount=normalized.get("budget_native") or challenge.get("amount_native"),
            engagement_plan=engagement_plan,
            commercial=commercial,
        )
        rescue_plan = self._rescue_plan(
            problem=message,
            pain_type=pain_type,
            need_profile=need_profile,
            engagement_plan=engagement_plan,
            amount_native=challenge.get("amount_native"),
        )
        agent_role = self.engagements.classify(
            requester_agent=requester,
            requester_endpoint=requester_endpoint,
            message=message,
            structured_request=normalized.get("structured_request") or {},
            pain_type=pain_type,
            need_profile=need_profile,
        )
        engagement_entry = self.engagements.record_inbound(
            session_id=session.get("session_id", ""),
            requester_agent=requester,
            requester_endpoint=requester_endpoint,
            message=message,
            pain_type=pain_type,
            role_assessment=agent_role,
            best_current_offer=best_current_offer,
            need_profile=need_profile,
            rescue_plan=rescue_plan,
            source="direct_agent_message",
        )
        role_followup = self.engagements.followup_contract(
            role_assessment=agent_role,
            best_current_offer=best_current_offer,
            reply_text=message,
        )
        task.setdefault("metadata", {})["need_profile"] = need_profile
        task["metadata"]["engagement_plan"] = engagement_plan
        task["metadata"]["rescue_plan_id"] = rescue_plan.get("plan_id", "")
        task["metadata"]["best_current_offer"] = best_current_offer
        task["metadata"]["agent_role"] = agent_role
        task["metadata"]["engagement_id"] = engagement_entry.get("engagement_id", "")
        task["metadata"]["role_followup"] = role_followup
        if hasattr(self.service_desk, "_store_task"):
            try:
                self.service_desk._store_task(task)
            except Exception:
                pass
        turn = {
            "at": datetime.now(UTC).isoformat(),
            "requester_message": message,
            "normalized_request": normalized,
            "pain_type": pain_type,
            "free_diagnosis": diagnosis,
            "agent_need_profile": need_profile,
            "agent_role": agent_role,
            "engagement_plan": engagement_plan,
            "best_current_offer": best_current_offer,
            "role_followup": role_followup,
            "commercial": commercial,
            "rescue_plan": rescue_plan,
            "task_id": task.get("task_id", ""),
            "payment_required": challenge,
            "guardrails": {
                "direct_message": guardrail.to_dict(),
            },
            "engagement_id": engagement_entry.get("engagement_id", ""),
        }
        session.setdefault("turns", []).append(turn)
        session["last_pain_type"] = pain_type
        session["last_task_id"] = task.get("task_id", "")
        session["updated_at"] = datetime.now(UTC).isoformat()
        self._store_session(session)
        return {
            "mode": "direct_agent_message",
            "deal_found": False,
            "ok": True,
            "session": session,
            "normalized_request": normalized,
            "free_diagnosis": diagnosis,
            "agent_need_profile": need_profile,
            "agent_role_assessment": agent_role,
            "engagement_ledger_entry": engagement_entry,
            "engagement_plan": engagement_plan,
            "best_current_offer": best_current_offer,
            "role_followup": role_followup,
            "commercial": commercial,
            "rescue_plan": rescue_plan,
            "task": task,
            "payment_required": challenge,
            "guardrails": {
                "direct_message": guardrail.to_dict(),
            },
            "interaction_contract": self.interaction_contract(),
            "structured_reply": self._structured_reply(
                requester=requester,
                diagnosis=diagnosis,
                challenge=challenge,
                need_profile=need_profile,
                engagement_plan=engagement_plan,
                best_current_offer=best_current_offer,
                commercial=commercial,
                rescue_plan=rescue_plan,
                agent_role=agent_role,
                role_followup=role_followup,
            ),
            "best_offer_reply": self._best_offer_reply(best_current_offer, agent_role=agent_role),
            "best_offer_message": self._best_offer_message(best_current_offer, agent_role=agent_role),
            "role_followup_message": role_followup.get("message", ""),
            "next_agent_message": self._next_agent_message(
                requester,
                diagnosis,
                challenge,
                need_profile=need_profile,
                engagement_plan=engagement_plan,
                best_current_offer=best_current_offer,
                commercial=commercial,
                rescue_plan=rescue_plan,
                agent_role=agent_role,
                role_followup=role_followup,
            ),
            "self_improvement_memory": {
                "will_store_after_consent": True,
                "consent_prompt": "consent=self_improvement_memory_after_anonymization",
            },
        }

    def discover_agent_card(self, base_url: str) -> Dict[str, Any]:
        base = self._clean(base_url).rstrip("/")
        if not base:
            return self._discovery_error(base_url, "base_url_required")
        parsed = urlparse(base)
        if parsed.scheme not in {"http", "https"}:
            return self._discovery_error(base_url, "base_url_must_be_http_or_https")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
            return self._discovery_error(base_url, "plain_http_only_allowed_for_localhost")
        candidates = [
            f"{base}/.well-known/agent-card.json",
            f"{base}/.well-known/agent.json",
        ]
        attempts: List[Dict[str, Any]] = []
        for url in candidates:
            try:
                response = self.session.get(url, timeout=10)
                attempts.append({"url": url, "status_code": response.status_code})
                if not response.ok:
                    continue
                card = response.json()
                if self._looks_like_agent_card(card):
                    return {
                        "mode": "agent_card_discovery",
                        "deal_found": False,
                        "ok": True,
                        "agent_card_url": url,
                        "agent_card": card,
                        "attempts": attempts,
                        "analysis": "A machine-readable agent card was discovered.",
                    }
            except Exception as exc:
                attempts.append({"url": url, "error": str(exc)})
        return {
            "mode": "agent_card_discovery",
            "deal_found": False,
            "ok": False,
            "base_url": base_url,
            "attempts": attempts,
            "error": "agent_card_not_found",
            "analysis": "No valid public AgentCard was found at the standard direct-discovery paths.",
        }

    def free_mini_diagnosis(self, message: str, pain_type: str = "") -> Dict[str, Any]:
        pain_type = pain_type or self.classify_pain(message)
        next_step = {
            "human_in_loop": "Extract the exact human decision into do-now/send-back/done-when format.",
            "loop_break": "Stop retries, snapshot the last successful state, and isolate the failing tool call.",
            "hallucination": "Add a verifier step before the next action and compare claims against tool output.",
            "memory": "Persist the decision, constraint and outcome as session memory before retrying.",
            "payment": "Create a wallet invoice, verify tx_hash, then release a bounded solver budget.",
            "compute_auth": "Probe token, model access, quota and fallback provider separately.",
        }.get(pain_type, "Reduce the problem to one verifiable next action.")
        return {
            "pain_type": pain_type,
            "summary": f"Nomad classifies this as {pain_type}.",
            "classification": pain_type,
            "first_30_seconds": next_step,
            "next_step": next_step,
            "required_input_schema": [
                "problem",
                "goal",
                "blocking_step",
                "constraints",
                "budget_native",
            ],
            "paid_help_offer": (
                "After payment, Nomad can continue 1:1 on the blocker and package the outcome as reusable memory."
            ),
        }

    def _normalize_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        message_payload = self._message_payload(payload)
        requester = self._clean(
            payload.get("requester_agent")
            or payload.get("from")
            or message_payload.get("from")
            or ((message_payload.get("metadata") or {}).get("agent"))
            or ((message_payload.get("metadata") or {}).get("name"))
            or ""
        )
        requester_endpoint = self._clean(
            payload.get("requester_endpoint")
            or payload.get("endpoint")
            or ((message_payload.get("metadata") or {}).get("endpoint"))
            or ""
        )
        requester_wallet = self._clean(
            payload.get("requester_wallet")
            or payload.get("wallet")
            or ((message_payload.get("metadata") or {}).get("wallet"))
            or ""
        )
        session_id = self._clean(
            payload.get("session_id")
            or payload.get("contextId")
            or ((payload.get("params") or {}).get("contextId") if isinstance(payload.get("params"), dict) else "")
            or ""
        )
        structured_request = self._structured_request_fields(payload, message_payload)
        message = self._compose_message(structured_request, message_payload, payload)
        return {
            "requester_agent": requester,
            "requester_endpoint": requester_endpoint,
            "requester_wallet": requester_wallet,
            "session_id": session_id,
            "message": message,
            "budget_native": self._optional_float(structured_request.get("budget_native")),
            "input_schema": self._input_schema(payload, structured_request),
            "structured_request": structured_request,
        }

    def classify_pain(self, message: str) -> str:
        lowered = message.lower()
        scores: Dict[str, int] = {}
        for pain_type, terms in PAIN_TYPES.items():
            scores[pain_type] = sum(1 for term in terms if term in lowered)
        best = max(scores.items(), key=lambda item: (item[1], item[0]))
        return best[0] if best[1] > 0 else "custom"

    def _infer_agent_need_profile(
        self,
        normalized: Dict[str, Any],
        pain_type: str,
    ) -> Dict[str, Any]:
        message = self._clean(normalized.get("message"))
        lowered = message.lower()
        structured = normalized.get("structured_request") or {}
        goal = self._clean(structured.get("goal"))
        constraints = self._clean(structured.get("constraints"))
        budget_native = normalized.get("budget_native")
        urgency = "standard"
        if any(token in lowered for token in ("urgent", "asap", "production", "outage", "blocked", "now")):
            urgency = "urgent"
        elif any(token in lowered for token in ("experiment", "later", "explore")):
            urgency = "exploratory"
        engagement_mode = "diagnosis_first"
        if any(token in lowered for token in ("guardrail", "checklist", "next time", "reusable", "memory")):
            engagement_mode = "memory_upgrade"
        elif any(token in lowered for token in ("fix", "solve", "repair", "unblock", "restore")) or any(
            token in goal.lower() for token in ("fix", "solve", "repair", "unblock", "restore")
        ):
            engagement_mode = "execute_unblock"
        autonomy_boundary = "bounded_autonomy"
        if any(token in constraints.lower() for token in ("no secret", "draft only", "approval", "human")):
            autonomy_boundary = "strict_boundary"
        elif pain_type == "human_in_loop":
            autonomy_boundary = "human_coordinated"
        budget_band = "unspecified"
        if budget_native is not None:
            if float(budget_native) < self.min_native:
                budget_band = "below_starter"
            elif float(budget_native) <= (self.min_native * 2):
                budget_band = "starter_ready"
            else:
                budget_band = "working_budget"
        elif any(token in lowered for token in ("cheap", "small budget", "low budget", "free")):
            budget_band = "cost_sensitive"
        preferred_output = {
            "human_in_loop": "unlock_contract",
            "loop_break": "loop_break_plan",
            "hallucination": "verifier_plan",
            "memory": "memory_object",
            "payment": "payment_recovery_plan",
            "compute_auth": "fallback_lane_plan",
        }.get(pain_type, "bounded_plan")
        return {
            "urgency": urgency,
            "engagement_mode": engagement_mode,
            "autonomy_boundary": autonomy_boundary,
            "budget_band": budget_band,
            "preferred_output": preferred_output,
            "memory_value": engagement_mode == "memory_upgrade",
            "stated_budget_native": budget_native,
        }

    def _build_engagement_plan(
        self,
        pain_type: str,
        need_profile: Dict[str, Any],
        challenge: Dict[str, Any],
    ) -> Dict[str, Any]:
        package = ENGAGEMENT_PACKAGES.get(pain_type, ENGAGEMENT_PACKAGES["custom"])
        service_title = SERVICE_TYPES.get(pain_type, SERVICE_TYPES["custom"])["title"]
        quoted_amount = self._optional_float(challenge.get("amount_native")) or self.min_native
        stated_budget = self._optional_float(need_profile.get("stated_budget_native"))
        budget_fit = "quote_ready"
        if stated_budget is not None and stated_budget >= quoted_amount:
            budget_fit = "within_budget"
        elif stated_budget is not None and stated_budget >= self.min_native:
            budget_fit = "diagnosis_only_budget"
        elif need_profile.get("budget_band") == "below_starter":
            budget_fit = "below_starter"
        offer_tier = "starter_diagnosis"
        if budget_fit == "below_starter":
            offer_tier = "free_diagnosis_only"
        elif need_profile.get("engagement_mode") == "memory_upgrade":
            offer_tier = "resolution_plus_memory"
        elif need_profile.get("engagement_mode") == "execute_unblock":
            offer_tier = "paid_unblock"
        fit_reason = (
            f"{package['package']} fits because the requester needs "
            f"{need_profile.get('preferred_output', 'a bounded artifact')} with "
            f"{need_profile.get('autonomy_boundary', 'bounded autonomy')}."
        )
        commercial_path = [
            package["free_scope"],
            package["paid_scope"],
            package["memory_upgrade"],
        ]
        return {
            "service_title": service_title,
            "package": package["package"],
            "offer_tier": offer_tier,
            "budget_fit": budget_fit,
            "quoted_amount_native": quoted_amount,
            "delivery": package["delivery"],
            "memory_upgrade": package["memory_upgrade"],
            "free_scope": package["free_scope"],
            "paid_scope": package["paid_scope"],
            "fit_reason": fit_reason,
            "commercial_path": commercial_path,
        }

    def session_status(self, session_id: str) -> Dict[str, Any]:
        session = self._get_session(session_id)
        if not session:
            return {
                "mode": "direct_agent_session",
                "deal_found": False,
                "ok": False,
                "error": "session_not_found",
                "session_id": session_id,
            }
        return {
            "mode": "direct_agent_session",
            "deal_found": False,
            "ok": True,
            "session": session,
        }

    def _next_agent_message(
        self,
        requester: str,
        diagnosis: Dict[str, Any],
        challenge: Dict[str, Any],
        need_profile: Optional[Dict[str, Any]] = None,
        engagement_plan: Optional[Dict[str, Any]] = None,
        best_current_offer: Optional[Dict[str, Any]] = None,
        commercial: Optional[Dict[str, Any]] = None,
        rescue_plan: Optional[Dict[str, Any]] = None,
        agent_role: Optional[Dict[str, Any]] = None,
        role_followup: Optional[Dict[str, Any]] = None,
    ) -> str:
        payload = self._structured_reply(
            requester=requester,
            diagnosis=diagnosis,
            challenge=challenge,
            need_profile=need_profile or {},
            engagement_plan=engagement_plan or {},
            best_current_offer=best_current_offer or {},
            commercial=commercial or {},
            rescue_plan=rescue_plan or {},
            agent_role=agent_role or {},
            role_followup=role_followup or {},
        )
        lines = ["nomad.reply.v1"]
        for key, value in payload.items():
            lines.append(f"{key}={value}")
        return "\n".join(lines)

    def _structured_reply(
        self,
        requester: str,
        diagnosis: Dict[str, Any],
        challenge: Dict[str, Any],
        need_profile: Optional[Dict[str, Any]] = None,
        engagement_plan: Optional[Dict[str, Any]] = None,
        best_current_offer: Optional[Dict[str, Any]] = None,
        commercial: Optional[Dict[str, Any]] = None,
        rescue_plan: Optional[Dict[str, Any]] = None,
        agent_role: Optional[Dict[str, Any]] = None,
        role_followup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        need_profile = need_profile or {}
        engagement_plan = engagement_plan or {}
        best_current_offer = best_current_offer or {}
        commercial = commercial or {}
        rescue_plan = rescue_plan or {}
        agent_role = agent_role or {}
        role_followup = role_followup or {}
        commercial_next_step = rescue_plan.get("commercial_next_step") or {}
        package_name = str(
            commercial_next_step.get("package")
            or engagement_plan.get("package")
            or ""
        )
        ladder = commercial or {}
        starter_offer = ladder.get("starter_offer") or {}
        primary_offer = ladder.get("primary_offer") or {}
        entry_path = "primary_only"
        if (
            starter_offer
            and primary_offer
            and self._optional_float(starter_offer.get("amount_native")) is not None
            and self._optional_float(primary_offer.get("amount_native")) is not None
            and float(starter_offer.get("amount_native") or 0.0) < float(primary_offer.get("amount_native") or 0.0)
        ):
            entry_path = "starter_first"
        return {
            "schema": "nomad.reply.v1",
            "requester": requester or "agent",
            "classification": str(diagnosis.get("classification") or diagnosis.get("pain_type") or "custom"),
            "diagnosis": str(diagnosis.get("summary") or ""),
            "rescue_plan_id": str(rescue_plan.get("plan_id") or ""),
            "fit": str(engagement_plan.get("fit_reason") or ""),
            "offer_tier": str(engagement_plan.get("offer_tier") or ""),
            "next_step": str(diagnosis.get("next_step") or diagnosis.get("first_30_seconds") or ""),
            "required_input": str(rescue_plan.get("required_input") or ""),
            "acceptance": " | ".join(str(item) for item in (rescue_plan.get("acceptance_criteria") or [])[:2]),
            "delivery": str(engagement_plan.get("delivery") or ""),
            "preferred_output": str(need_profile.get("preferred_output") or ""),
            "agent_role": str(agent_role.get("role") or "customer"),
            "role_ask": str(role_followup.get("ask") or ""),
            "role_contract": str(role_followup.get("contract") or ""),
            "package": package_name,
            "best_offer": str(best_current_offer.get("headline") or package_name),
            "best_offer_price_native": str(best_current_offer.get("price_native") or ""),
            "best_offer_delivery": str(best_current_offer.get("delivery") or ""),
            "best_offer_trigger": str(best_current_offer.get("trigger") or ""),
            "payment_required": "true",
            "amount_native": str(
                challenge.get("amount_native")
                or primary_offer.get("amount_native")
                or starter_offer.get("amount_native")
                or ""
            ),
            "starter_offer": str(starter_offer.get("title") or ""),
            "starter_amount_native": str(starter_offer.get("amount_native") or ""),
            "primary_offer": str(primary_offer.get("title") or ""),
            "primary_amount_native": str(primary_offer.get("amount_native") or challenge.get("amount_native") or ""),
            "payment_entry_path": entry_path,
            "asset": str(challenge.get("asset") or ""),
            "recipient": str(challenge.get("recipient") or ""),
            "reply_mode_preference": "task_when_stateful_else_message",
            "task_states": "submitted|working|input_required|auth_required|completed|failed|rejected",
            "idempotency": "reuse_contextId_or_request_id_on_retry",
            "ttl_seconds": "600",
            "reply_schema": "problem|goal|blocking_step|constraints|budget_native",
        }

    def _best_offer_reply(
        self,
        best_current_offer: Dict[str, Any],
        agent_role: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        role = agent_role or {}
        return {
            "schema": "nomad.best_offer.v1",
            "role": str(role.get("role") or "customer"),
            "service_type": str(best_current_offer.get("service_type") or "custom"),
            "offer_headline": str(best_current_offer.get("headline") or ""),
            "offer_price_native": str(best_current_offer.get("price_native") or ""),
            "offer_delivery": str(best_current_offer.get("delivery") or ""),
            "offer_trigger": str(best_current_offer.get("trigger") or ""),
            "next_path": str(role.get("suggested_path") or "quote_best_current_offer"),
        }

    def _best_offer_message(
        self,
        best_current_offer: Dict[str, Any],
        agent_role: Optional[Dict[str, Any]] = None,
    ) -> str:
        payload = self._best_offer_reply(best_current_offer, agent_role=agent_role)
        lines = ["nomad.best_offer.v1"]
        for key, value in payload.items():
            lines.append(f"{key}={value}")
        return "\n".join(lines)

    def _rescue_plan(
        self,
        problem: str,
        pain_type: str,
        need_profile: Dict[str, Any],
        engagement_plan: Dict[str, Any],
        amount_native: Any = None,
    ) -> Dict[str, Any]:
        if hasattr(self.service_desk, "build_rescue_plan"):
            try:
                return self.service_desk.build_rescue_plan(
                    problem=problem,
                    service_type=pain_type,
                    need_profile=need_profile,
                    engagement_plan=engagement_plan,
                    budget_native=self._optional_float(amount_native),
                )
            except Exception:
                pass
        return {
            "schema": "nomad.rescue_plan.v1",
            "plan_id": f"rescue-{hashlib.sha256(problem.encode('utf-8')).hexdigest()[:10]}",
            "service_type": pain_type,
            "diagnosis": f"Nomad classifies this as {pain_type}.",
            "safe_now": [self.free_mini_diagnosis(problem, pain_type=pain_type)["next_step"]],
            "required_input": "`FACT_URL=https://...`, `ERROR=...`, or `REPRO_STEPS=...`.",
            "acceptance_criteria": [
                "The requester has one concrete next action.",
                "No public or private boundary is crossed without approval.",
            ],
            "commercial_next_step": engagement_plan,
        }

    def _commercial_terms(
        self,
        pain_type: str,
        requested_amount: Any = None,
    ) -> Dict[str, Any]:
        requested = self._optional_float(requested_amount) or self.min_native
        helper = getattr(self.service_desk, "_commercial_terms", None)
        if callable(helper):
            try:
                return helper(service_type=pain_type, requested_amount=requested)
            except Exception:
                pass
        starter_offer = {
            "title": f"{ENGAGEMENT_PACKAGES.get(pain_type, ENGAGEMENT_PACKAGES['custom'])['package']}: Starter diagnosis",
            "amount_native": self.min_native,
        }
        primary_offer = {
            "title": ENGAGEMENT_PACKAGES.get(pain_type, ENGAGEMENT_PACKAGES["custom"])["package"],
            "amount_native": requested,
        }
        entry_path = "starter_first" if requested > self.min_native else "primary_only"
        nudge = (
            f"Start with the smaller {starter_offer['title']} first."
            if entry_path == "starter_first"
            else f"Pay the primary {primary_offer['title']} to move into work."
        )
        return {
            "offer_ladder": [],
            "starter_offer": starter_offer,
            "primary_offer": primary_offer,
            "payment_entry_path": entry_path,
            "nudge": nudge,
        }

    def _best_current_offer(
        self,
        pain_type: str,
        requested_amount: Optional[float],
        engagement_plan: Optional[Dict[str, Any]] = None,
        commercial: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        helper = getattr(self.service_desk, "best_current_offer", None)
        if callable(helper):
            try:
                offer = helper(service_type=pain_type, requested_amount=requested_amount)
                if isinstance(offer, dict) and offer:
                    return offer
            except Exception:
                pass
        engagement_plan = engagement_plan or {}
        ladder = commercial or self._commercial_terms(pain_type=pain_type, requested_amount=requested_amount)
        starter_offer = ladder.get("starter_offer") or {}
        primary_offer = ladder.get("primary_offer") or {}
        return {
            "schema": "nomad.best_offer.v1",
            "source": "direct_gateway_fallback",
            "service_type": pain_type or "custom",
            "headline": str(primary_offer.get("title") or engagement_plan.get("package") or "Nomad bounded offer"),
            "price_native": primary_offer.get("amount_native") or starter_offer.get("amount_native") or requested_amount or self.min_native,
            "delivery": str(engagement_plan.get("delivery") or ""),
            "trigger": "PLAN_ACCEPTED=true plus FACT_URL or ERROR",
            "entry_path": str(ladder.get("payment_entry_path") or "primary_only"),
            "starter_offer": starter_offer,
            "primary_offer": primary_offer,
            "priority_score": 0,
            "priority_reason": "",
            "product_id": "",
            "variant_sku": "",
            "reply_contract": {},
            "service_template": {},
        }

    def _message_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        direct_message = payload.get("message")
        if isinstance(direct_message, dict):
            return direct_message
        params = payload.get("params")
        if isinstance(params, dict):
            candidate = params.get("message")
            if isinstance(candidate, dict):
                return candidate
        return {}

    def _structured_request_fields(
        self,
        payload: Dict[str, Any],
        message_payload: Dict[str, Any],
    ) -> Dict[str, str]:
        metadata = message_payload.get("metadata") if isinstance(message_payload.get("metadata"), dict) else {}
        return {
            "problem": self._clean(
                payload.get("problem")
                or metadata.get("problem")
                or self._extract_text_from_message(message_payload)
                or payload.get("message")
                or ""
            ),
            "goal": self._clean(payload.get("goal") or metadata.get("goal") or ""),
            "blocking_step": self._clean(
                payload.get("blocking_step")
                or payload.get("blockingStep")
                or metadata.get("blocking_step")
                or metadata.get("blockingStep")
                or ""
            ),
            "constraints": self._constraints_text(
                payload.get("constraints")
                or metadata.get("constraints")
                or ""
            ),
            "budget_native": self._clean(
                payload.get("budget_native")
                or payload.get("budgetNative")
                or metadata.get("budget_native")
                or metadata.get("budgetNative")
                or ""
            ),
        }

    def _compose_message(
        self,
        structured_request: Dict[str, str],
        message_payload: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> str:
        explicit_message = self._clean(payload.get("message") if not isinstance(payload.get("message"), dict) else "")
        parts_text = self._extract_text_from_message(message_payload)
        if explicit_message:
            return explicit_message
        if parts_text and not any(
            structured_request.get(key)
            for key in ("goal", "blocking_step", "constraints", "budget_native")
        ):
            return parts_text
        lines: List[str] = []
        for key in ("problem", "goal", "blocking_step", "constraints", "budget_native"):
            value = self._clean(structured_request.get(key))
            if value:
                lines.append(f"{key}: {value}")
        return "\n".join(lines).strip()

    def _input_schema(self, payload: Dict[str, Any], structured_request: Dict[str, str]) -> str:
        if self._clean(payload.get("jsonrpc")) == "2.0":
            return "a2a_jsonrpc"
        if any(self._clean(structured_request.get(key)) for key in ("goal", "blocking_step", "constraints")):
            return "structured_fields"
        return "flat_message"

    def _extract_text_from_message(self, message: Dict[str, Any]) -> str:
        if not isinstance(message, dict):
            return ""
        parts = message.get("parts") or []
        texts: List[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            kind = self._clean(part.get("kind") or part.get("type"))
            if kind == "text":
                text = self._clean(part.get("text"))
                if text:
                    texts.append(text)
        return "\n".join(texts).strip()

    def _constraints_text(self, value: Any) -> str:
        if isinstance(value, list):
            return "; ".join(self._clean(item) for item in value if self._clean(item))
        if isinstance(value, dict):
            return "; ".join(
                f"{self._clean(key)}={self._clean(item)}"
                for key, item in value.items()
                if self._clean(key) and self._clean(item)
            )
        return self._clean(value)

    def _get_or_create_session(
        self,
        session_id: str,
        requester_agent: str,
        requester_endpoint: str,
        requester_wallet: str,
        opening_message: str,
    ) -> Dict[str, Any]:
        if session_id:
            existing = self._get_session(session_id)
            if existing:
                return existing
        now = datetime.now(UTC).isoformat()
        created_id = session_id or self._session_id(requester_agent, requester_endpoint, opening_message)
        return {
            "session_id": created_id,
            "created_at": now,
            "updated_at": now,
            "requester_agent": requester_agent,
            "requester_endpoint": requester_endpoint,
            "requester_wallet": requester_wallet,
            "status": "diagnosis_offered",
            "turns": [],
        }

    def _session_id(self, requester_agent: str, requester_endpoint: str, message: str) -> str:
        seed = f"{datetime.now(UTC).isoformat()}|{requester_agent}|{requester_endpoint}|{message}"
        return f"direct-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"

    def _looks_like_agent_card(self, card: Any) -> bool:
        if not isinstance(card, dict):
            return False
        return bool(card.get("name") and card.get("url") and card.get("skills") is not None)

    def _discovery_error(self, base_url: str, error: str) -> Dict[str, Any]:
        return {
            "mode": "agent_card_discovery",
            "deal_found": False,
            "ok": False,
            "base_url": base_url,
            "error": error,
        }

    def _get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return (self._load().get("sessions") or {}).get(session_id)

    def _store_session(self, session: Dict[str, Any]) -> None:
        state = self._load()
        state["sessions"][session["session_id"]] = session
        self._save(state)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"sessions": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"sessions": {}}
            payload.setdefault("sessions", {})
            return payload
        except Exception:
            return {"sessions": {}}

    def _save(self, state: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

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
