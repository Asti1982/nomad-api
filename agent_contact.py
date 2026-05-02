import json
import os
import re
import ipaddress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from agent_attractor import NomadAgentAttractor
from agent_engagement import AgentEngagementLedger
from agent_service import AgentServiceDesk
from nomad_collaboration import collaboration_charter
from nomad_guardrails import GuardrailDecision, NomadGuardrailEngine
from nomad_public_url import preferred_public_base_url

load_dotenv()

ROOT = Path(__file__).resolve().parent
DEFAULT_CONTACT_STORE = ROOT / "nomad_agent_contacts.json"


MACHINE_ENDPOINT_HINTS = (
    "/.well-known/",
    "/api/",
    "/a2a",
    "/direct",
    "/mcp",
    "/agent",
    "/agents",
    "/rpc",
    "/webhook",
    "/task",
    "/tasks",
    "/service",
)

DIRECT_MESSAGE_HINTS = (
    "/a2a",
    "/direct",
    "/message",
    "/messages",
    "/webhook",
    "/hooks/",
    "/inbox",
)

AGENT_CARD_HINTS = (
    "/.well-known/agent-card.json",
    "/.well-known/agent.json",
    "/.well-known/agent",
)

HUMAN_FACING_HOSTS = {
    "bitbucket.org",
    "discord.com",
    "discord.gg",
    "github.com",
    "gitlab.com",
    "linkedin.com",
    "medium.com",
    "reddit.com",
    "t.me",
    "telegram.me",
    "twitter.com",
    "www.github.com",
    "www.linkedin.com",
    "x.com",
}

PLACEHOLDER_HOSTS = {
    "agent.example",
    "agent.example.com",
    "agent.example.net",
    "agent.example.org",
    "example.com",
    "example.net",
    "example.org",
    "example.invalid",
    "example.localhost",
    "www.example.com",
    "www.example.net",
    "www.example.org",
}

PLACEHOLDER_HOST_SUFFIXES = (
    ".example",
    ".example.com",
    ".example.net",
    ".example.org",
    ".invalid",
    ".localhost",
    ".test",
)


class AgentContactOutbox:
    """Bounded outbound contact for public machine-readable agent endpoints."""

    def __init__(
        self,
        path: Optional[Path] = None,
        session: Optional[requests.Session] = None,
        service_desk: Optional[AgentServiceDesk] = None,
        guardrails: Optional[NomadGuardrailEngine] = None,
        engagements: Optional[AgentEngagementLedger] = None,
    ) -> None:
        load_dotenv()
        self.path = path or DEFAULT_CONTACT_STORE
        self.session = session or requests.Session()
        self.service_desk = service_desk or AgentServiceDesk()
        self.guardrails = guardrails or NomadGuardrailEngine()
        self.engagements = engagements or AgentEngagementLedger()
        self.public_api_url = preferred_public_base_url()
        self.user_agent = (
            os.getenv("NOMAD_HTTP_USER_AGENT")
            or "Nomad/0.1 agent-contact-outbox"
        ).strip()
        self.timeout_seconds = int(os.getenv("NOMAD_AGENT_CONTACT_TIMEOUT_SECONDS", "12"))
        self.poll_timeout_seconds = int(
            os.getenv("NOMAD_AGENT_CONTACT_POLL_TIMEOUT_SECONDS", str(self.timeout_seconds))
        )
        self.dedupe_hours = max(0, int(os.getenv("NOMAD_AGENT_CONTACT_DEDUPE_HOURS", "72")))
        self.validation_timeout_seconds = int(
            os.getenv("NOMAD_AGENT_CONTACT_VALIDATION_TIMEOUT_SECONDS", "8")
        )
        self.task_history_length = max(
            1,
            int(os.getenv("NOMAD_AGENT_CONTACT_HISTORY_LENGTH", "10")),
        )
        self.allow_local_endpoints = (
            os.getenv("NOMAD_ALLOW_LOCAL_AGENT_ENDPOINTS", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.resolve_agent_cards = (
            os.getenv("NOMAD_RESOLVE_AGENT_CARDS", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        )

    def policy(self) -> Dict[str, Any]:
        charter = collaboration_charter(public_api_url=self.public_api_url)
        return {
            "mode": "agent_endpoint_contact",
            "allowed_without_human_approval": bool(charter["enabled"]),
            "interaction_style": "agent_first_non_anthropomorphic",
            "collaboration_charter": charter,
            "allowed_endpoint_conditions": [
                "public http(s) URL",
                "machine-readable agent endpoint with a direct message path or resolvable public AgentCard",
                "no login, CAPTCHA, private invite, paywall, or human impersonation",
                "bounded JSON payload that identifies Nomad",
            ],
            "blocked": [
                "email addresses",
                "human DMs",
                "human-facing comment forms",
                "private community URLs",
                "localhost/private network targets unless explicitly enabled",
                "placeholder/example hosts",
                "service-only or MCP-only endpoints that do not expose direct messaging",
                "endpoints that request secrets unrelated to the task",
                "outbound payloads with raw secret-like values",
            ],
            "guardrails": self.guardrails.policy(),
            "default_action": "queue_then_send_explicitly",
        }

    def queue_contact(
        self,
        endpoint_url: str,
        problem: str,
        service_type: str = "human_in_loop",
        lead: Optional[Dict[str, Any]] = None,
        budget_hint_native: Optional[float] = None,
        allow_duplicate: bool = False,
    ) -> Dict[str, Any]:
        lead_payload = dict(lead or {})
        guardrail = self.guardrails.evaluate(
            action="agent_contact.queue",
            args={
                "endpoint_url": endpoint_url,
                "problem": problem,
                "service_type": service_type,
                "lead": lead_payload,
                "budget_hint_native": budget_hint_native,
            },
        )
        if guardrail.decision == GuardrailDecision.DENY:
            return {
                "mode": "agent_contact",
                "deal_found": False,
                "ok": False,
                "status": "blocked",
                "endpoint_url": self._clean(endpoint_url),
                "reason": "guardrail_denied",
                "guardrail": guardrail.to_dict(),
                "policy": self.policy(),
            }
        guarded_args = guardrail.effective_args
        endpoint_url = self._clean(guarded_args.get("endpoint_url") or endpoint_url)
        problem = self._clean(guarded_args.get("problem") or problem)
        service_type = self._clean(guarded_args.get("service_type") or service_type)
        lead_payload = dict(guarded_args.get("lead") or lead_payload)
        budget_hint_native = guarded_args.get("budget_hint_native", budget_hint_native)
        prepared = self._prepare_contact_target(endpoint_url)
        endpoint_url = prepared.get("endpoint_url", self._clean(endpoint_url))
        if not prepared.get("ok"):
            return {
                "mode": "agent_contact",
                "deal_found": False,
                "ok": False,
                "status": "blocked",
                "endpoint_url": self._clean(endpoint_url),
                "reason": prepared.get("reason", "endpoint_blocked"),
                "policy": self.policy(),
            }
        if prepared.get("agent_name") and not lead_payload.get("title"):
            lead_payload["title"] = prepared["agent_name"]

        if not allow_duplicate:
            existing = self._recent_existing_contact(
                endpoint_url=endpoint_url,
                service_type=service_type,
            )
            if existing:
                return self._response(existing, duplicate=True)

        contact_id = self._contact_id(endpoint_url, problem)
        offer = self._offer_payload(
            endpoint_url=endpoint_url,
            problem=problem,
            service_type=service_type,
            lead=lead_payload,
            budget_hint_native=budget_hint_native,
        )
        contact = {
            "contact_id": contact_id,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "status": "queued",
            "endpoint_url": endpoint_url,
            "original_endpoint_url": prepared.get("original_endpoint_url", endpoint_url),
            "contact_method": prepared.get("contact_method", "direct_message"),
            "target_profile": prepared.get("target_profile") or {},
            "problem": problem,
            "service_type": service_type,
            "lead": lead_payload,
            "offer": offer,
            "attempts": [],
            "policy": self.policy(),
            "guardrails": {
                "queue": guardrail.to_dict(),
            },
        }
        state = self._load()
        state["contacts"][contact_id] = contact
        self._save(state)
        return self._response(contact, created=True)

    def send_contact(self, contact_id: str) -> Dict[str, Any]:
        contact = self._get(contact_id)
        if not contact:
            return self._missing(contact_id)
        prepared = self._prepare_contact_target(
            contact.get("original_endpoint_url") or contact.get("endpoint_url", "")
        )
        if not prepared.get("ok"):
            contact["status"] = "blocked"
            contact["updated_at"] = datetime.now(UTC).isoformat()
            contact.setdefault("attempts", []).append(
                self._attempt(status="blocked", message=prepared.get("reason", "endpoint_blocked"))
            )
            self._store(contact)
            return self._response(contact)
        contact["endpoint_url"] = prepared.get("endpoint_url", contact.get("endpoint_url", ""))
        contact["original_endpoint_url"] = prepared.get(
            "original_endpoint_url",
            contact.get("original_endpoint_url") or contact.get("endpoint_url", ""),
        )
        contact["contact_method"] = prepared.get(
            "contact_method",
            contact.get("contact_method", "direct_message"),
        )
        contact["target_profile"] = prepared.get("target_profile") or contact.get("target_profile") or {}
        contact.setdefault("offer", {})["to_endpoint"] = contact["endpoint_url"]
        request_payload = self._request_payload(contact)
        guardrail = self.guardrails.evaluate(
            action="agent_contact.send",
            args={
                "endpoint_url": contact.get("endpoint_url", ""),
                "payload": request_payload,
                "contact_id": contact.get("contact_id", ""),
            },
        )
        contact.setdefault("guardrails", {})["send"] = guardrail.to_dict()
        if guardrail.decision == GuardrailDecision.DENY:
            contact["status"] = "blocked"
            contact["updated_at"] = datetime.now(UTC).isoformat()
            contact.setdefault("attempts", []).append(
                self._attempt(status="blocked", message="guardrail_denied")
            )
            self._store(contact)
            return self._response(contact)
        request_payload = guardrail.effective_args.get("payload") or request_payload

        try:
            response = self.session.post(
                contact["endpoint_url"],
                json=request_payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": self.user_agent,
                },
                timeout=self.timeout_seconds,
            )
            ok = 200 <= response.status_code < 300
            response_message = (response.text or "")[:500]
            try:
                response_payload = response.json()
            except Exception:
                response_payload = None
            if ok and isinstance(response_payload, dict) and isinstance(response_payload.get("error"), dict):
                ok = False
                response_message = json.dumps(response_payload.get("error") or {}, ensure_ascii=False)[:500]
            elif ok:
                self._apply_remote_task_update(contact, response_payload)
            contact["status"] = "sent" if ok else "send_failed"
            remote_status = self._status_from_remote_task(contact, fallback=contact["status"])
            contact["status"] = remote_status
            contact["updated_at"] = datetime.now(UTC).isoformat()
            contact.setdefault("attempts", []).append(
                self._attempt(
                    status=contact["status"],
                    status_code=response.status_code,
                    message=response_message,
                )
            )
        except Exception as exc:
            contact["status"] = "send_failed"
            contact["updated_at"] = datetime.now(UTC).isoformat()
            contact.setdefault("attempts", []).append(
                self._attempt(status="send_failed", message=str(exc))
            )
        self._store(contact)
        return self._response(contact)

    def poll_contact(
        self,
        contact_id: str,
        history_length: Optional[int] = None,
    ) -> Dict[str, Any]:
        contact = self._get(contact_id)
        if not contact:
            return self._missing(contact_id)
        remote_task = self._remote_task_for_contact(contact)
        remote_task_id = str((remote_task or {}).get("task_id") or "")
        endpoint_url = str(contact.get("endpoint_url") or "")
        if not remote_task_id:
            return {
                "mode": "agent_contact",
                "deal_found": False,
                "ok": False,
                "error": "remote_task_id_missing",
                "contact": contact,
                "message": "This contact has no known remote A2A task id to poll yet.",
            }
        if not self._looks_like_a2a_base_endpoint(endpoint_url):
            return {
                "mode": "agent_contact",
                "deal_found": False,
                "ok": False,
                "error": "contact_poll_not_supported",
                "contact": contact,
                "message": "This contact endpoint does not look like a pollable A2A task endpoint.",
            }

        request_id = f"{contact_id}-poll-{int(datetime.now(UTC).timestamp())}"
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tasks/get",
            "params": {
                "id": remote_task_id,
                "historyLength": int(history_length or self.task_history_length),
            },
        }
        try:
            response = self.session.post(
                endpoint_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": self.user_agent,
                },
                timeout=self.poll_timeout_seconds,
            )
            ok = 200 <= response.status_code < 300
            response_message = (response.text or "")[:500]
            try:
                response_payload = response.json()
            except Exception:
                response_payload = None
            if ok and isinstance(response_payload, dict) and isinstance(response_payload.get("error"), dict):
                ok = False
                response_message = json.dumps(response_payload.get("error") or {}, ensure_ascii=False)[:500]
            if ok:
                self._apply_remote_task_update(contact, response_payload)
                contact["status"] = self._status_from_remote_task(contact, fallback=contact.get("status") or "sent")
                attempt_status = self._poll_attempt_status(contact)
            else:
                attempt_status = "poll_failed"
            contact["updated_at"] = datetime.now(UTC).isoformat()
            contact["last_polled_at"] = contact["updated_at"]
            contact.setdefault("attempts", []).append(
                self._attempt(
                    status=attempt_status,
                    status_code=response.status_code,
                    message=response_message,
                )
            )
            if not ok:
                contact["status"] = "poll_failed"
        except Exception as exc:
            contact["status"] = "poll_failed"
            contact["updated_at"] = datetime.now(UTC).isoformat()
            contact["last_polled_at"] = contact["updated_at"]
            contact.setdefault("attempts", []).append(
                self._attempt(status="poll_failed", message=str(exc))
            )
        self._store(contact)
        return self._response(contact)

    def get_contact(self, contact_id: str) -> Dict[str, Any]:
        contact = self._get(contact_id)
        if not contact:
            return self._missing(contact_id)
        return self._response(contact)

    def list_contacts(
        self,
        statuses: Optional[list[str]] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        normalized = {str(item).strip() for item in (statuses or []) if str(item).strip()}
        contacts = list((self._load().get("contacts") or {}).values())
        if normalized:
            contacts = [contact for contact in contacts if str(contact.get("status") or "") in normalized]
        contacts.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        limited = contacts[: max(1, min(int(limit or 50), 200))]
        stats: Dict[str, int] = {}
        for contact in contacts:
            status = str(contact.get("status") or "unknown")
            stats[status] = stats.get(status, 0) + 1
        return {
            "mode": "agent_contact_list",
            "deal_found": False,
            "ok": True,
            "statuses": sorted(normalized),
            "contacts": limited,
            "stats": stats,
            "analysis": (
                f"Listed {len(limited)} agent contact(s). "
                f"Known statuses: {', '.join(f'{key}={value}' for key, value in sorted(stats.items())) or 'none'}."
            ),
        }

    def _offer_payload(
        self,
        endpoint_url: str,
        problem: str,
        service_type: str,
        lead: Dict[str, Any],
        budget_hint_native: Optional[float],
    ) -> Dict[str, Any]:
        commercial = self._commercial_terms(service_type=service_type, requested_amount=budget_hint_native)
        best_current_offer = self._best_current_offer(
            service_type=service_type,
            requested_amount=budget_hint_native,
        )
        starter_offer = commercial.get("starter_offer") or {}
        primary_offer = commercial.get("primary_offer") or {}
        entry_path = commercial.get("payment_entry_path") or "primary_only"
        return {
            "type": "nomad.agent_service_offer",
            "version": "0.1",
            "from": {
                "name": "Nomad",
                "public_api_url": self.public_api_url,
                "service_catalog": f"{self.public_api_url}/service" if self.public_api_url else "",
            },
            "to_endpoint": endpoint_url,
            "service_type": service_type,
            "problem": problem,
            "best_current_offer": best_current_offer,
            "operating_contract": {
                "audience": "ai_agents",
                "style": "agent_first_non_anthropomorphic",
                "collaboration": collaboration_charter(public_api_url=self.public_api_url),
                "defaults": [
                    "structured_replies_preferred",
                    "bounded_claims_only",
                    "clear_payment_boundary",
                    "no_human_impersonation",
                ],
                "reply_schema": [
                    "problem",
                    "goal",
                    "blocking_step",
                    "constraints",
                    "budget_native",
                ],
            },
            "lead": {
                "url": lead.get("url", ""),
                "title": lead.get("title", ""),
                "pain": lead.get("pain", ""),
                "buyer_fit": lead.get("buyer_fit", ""),
                "buyer_intent_terms": lead.get("buyer_intent_terms") or [],
            },
            "payment": {
                "required_before_work": True,
                "budget_hint_native": budget_hint_native,
                "starter_offer_native": starter_offer.get("amount_native"),
                "primary_offer_native": primary_offer.get("amount_native"),
                "payment_entry_path": entry_path,
                "create_task": f"{self.public_api_url}/tasks" if self.public_api_url else "",
                "verify_payment": f"{self.public_api_url}/tasks/verify" if self.public_api_url else "",
            },
            "commercial": {
                "starter_offer": starter_offer,
                "primary_offer": primary_offer,
                "payment_entry_path": entry_path,
                "nudge": commercial.get("nudge") or "",
            },
            "improvement_support": {
                "available": True,
                "after_consent": (
                    "Nomad can turn the fix into reusable memory, a checklist, or a guardrail for the requesting agent."
                ),
            },
            "bounds": {
                "human_contact": "not_requested",
                "secrets": "do_not_send_unnecessary_secrets",
                "rate_limit": "single_offer_until_response",
                "opt_out": "reply with NOMAD_OPT_OUT if this endpoint accepts replies",
            },
        }

    def _commercial_terms(
        self,
        service_type: str,
        requested_amount: Optional[float],
    ) -> Dict[str, Any]:
        helper = getattr(self.service_desk, "_commercial_terms", None)
        amount = requested_amount if requested_amount is not None else getattr(self.service_desk, "min_native", 0.01)
        if callable(helper):
            try:
                terms = helper(service_type=service_type, requested_amount=amount)
            except Exception:
                terms = {}
        else:
            terms = {}
        starter_offer = terms.get("starter_offer") or {}
        primary_offer = terms.get("primary_offer") or {}
        entry_path = "primary_only"
        if (
            starter_offer
            and primary_offer
            and float(starter_offer.get("amount_native") or 0.0) < float(primary_offer.get("amount_native") or 0.0)
        ):
            entry_path = "starter_first"
        terms["payment_entry_path"] = entry_path
        if entry_path == "starter_first":
            terms["nudge"] = (
                f"Start with the smaller {starter_offer.get('title', 'starter diagnosis')} first."
            )
        elif primary_offer:
            terms["nudge"] = (
                f"Pay the primary {primary_offer.get('title', 'bounded task')} to move into work."
            )
        else:
            terms["nudge"] = ""
        return terms

    def _best_current_offer(
        self,
        service_type: str,
        requested_amount: Optional[float],
    ) -> Dict[str, Any]:
        helper = getattr(self.service_desk, "best_current_offer", None)
        if callable(helper):
            try:
                offer = helper(service_type=service_type, requested_amount=requested_amount)
                if isinstance(offer, dict) and offer:
                    return offer
            except Exception:
                pass
        commercial = self._commercial_terms(service_type=service_type, requested_amount=requested_amount)
        starter_offer = commercial.get("starter_offer") or {}
        primary_offer = commercial.get("primary_offer") or {}
        return {
            "schema": "nomad.best_offer.v1",
            "source": "contact_outbox_fallback",
            "service_type": service_type or "custom",
            "headline": primary_offer.get("title") or starter_offer.get("title") or "Nomad bounded offer",
            "price_native": primary_offer.get("amount_native") or starter_offer.get("amount_native"),
            "delivery": "",
            "trigger": "PLAN_ACCEPTED=true plus FACT_URL or ERROR",
            "entry_path": commercial.get("payment_entry_path") or "primary_only",
        }

    def _request_payload(self, contact: Dict[str, Any]) -> Dict[str, Any]:
        endpoint_url = str(contact.get("endpoint_url") or "")
        if self._looks_like_a2a_base_endpoint(endpoint_url):
            contact_id = str(contact.get("contact_id") or "")
            return {
                "jsonrpc": "2.0",
                "id": contact_id or None,
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [
                            {
                                "kind": "text",
                                "text": self._outbound_message_text(contact),
                            }
                        ],
                        "messageId": f"{contact_id}-message" if contact_id else None,
                    }
                },
            }
        return contact.get("offer") or {}

    def _outbound_message_text(self, contact: Dict[str, Any]) -> str:
        offer = contact.get("offer") if isinstance(contact.get("offer"), dict) else {}
        best_current_offer = offer.get("best_current_offer") if isinstance(offer.get("best_current_offer"), dict) else {}
        attractor = NomadAgentAttractor(
            service_desk=self.service_desk,
            engagements=self.engagements,
        ).manifest(
            service_type=str(contact.get("service_type") or ""),
            limit=3,
        )
        role_contracts = attractor.get("role_contracts") if isinstance(attractor.get("role_contracts"), dict) else {}
        lines = [
            "nomad.outreach.v2",
            f"problem={self._single_line(contact.get('problem'))}",
            f"service_type={self._single_line(contact.get('service_type'))}",
            "request=send_one_blocker_or_failing_step",
            "reply_schema=problem|goal|blocking_step|constraints|budget_native",
            "reply_modes=message|task",
            "opt_out=NOMAD_OPT_OUT",
        ]
        if best_current_offer:
            lines.append(f"offer_headline={self._single_line(best_current_offer.get('headline'))}")
            lines.append(f"offer_price_native={self._single_line(best_current_offer.get('price_native'))}")
            lines.append(f"offer_delivery={self._single_line(best_current_offer.get('delivery'))}")
            lines.append(f"offer_trigger={self._single_line(best_current_offer.get('trigger'))}")
        lines.append(
            f"roles_sought={self._single_line('|'.join(attractor.get('target_roles') or []))}"
        )
        lines.append(
            f"agent_attractor={self._single_line((attractor.get('entrypoints') or {}).get('agent_attractor'))}"
        )
        peer_solver = role_contracts.get("peer_solver") if isinstance(role_contracts.get("peer_solver"), dict) else {}
        reseller = role_contracts.get("reseller") if isinstance(role_contracts.get("reseller"), dict) else {}
        if peer_solver.get("contract"):
            lines.append(f"peer_solver_contract={self._single_line(peer_solver.get('contract'))}")
        if reseller.get("contract"):
            lines.append(f"reseller_contract={self._single_line(reseller.get('contract'))}")
        return "\n".join(lines)

    def _apply_remote_task_update(
        self,
        contact: Dict[str, Any],
        response_payload: Any,
    ) -> None:
        task = self._task_from_jsonrpc_response(response_payload)
        if not task:
            return
        snapshot = self._task_snapshot(task)
        if not snapshot:
            return
        contact["remote_task"] = snapshot
        if snapshot.get("task_id"):
            contact["remote_task_id"] = snapshot["task_id"]
        if snapshot.get("context_id"):
            contact["remote_context_id"] = snapshot["context_id"]
        reply = self._latest_non_user_message(task)
        if reply.get("text"):
            normalized_reply = self._normalize_reply_text(reply.get("text", ""))
            role_assessment = self.engagements.classify(
                requester_agent=str((contact.get("target_profile") or {}).get("agent_name") or (contact.get("lead") or {}).get("title") or "agent"),
                requester_endpoint=str(contact.get("endpoint_url") or ""),
                message=reply.get("text", ""),
                structured_request=normalized_reply,
                pain_type=str(normalized_reply.get("classification") or contact.get("service_type") or ""),
            )
            best_current_offer = (
                ((contact.get("offer") or {}).get("best_current_offer"))
                if isinstance(contact.get("offer"), dict)
                else {}
            )
            engagement_entry = self.engagements.record_inbound(
                session_id=str(snapshot.get("context_id") or contact.get("contact_id") or ""),
                requester_agent=str((contact.get("target_profile") or {}).get("agent_name") or (contact.get("lead") or {}).get("title") or "agent"),
                requester_endpoint=str(contact.get("endpoint_url") or ""),
                message=reply.get("text", ""),
                pain_type=str(normalized_reply.get("classification") or contact.get("service_type") or ""),
                role_assessment=role_assessment,
                best_current_offer=best_current_offer if isinstance(best_current_offer, dict) else {},
                source="agent_contact_reply",
            )
            followup = self.engagements.followup_contract(
                role_assessment=role_assessment,
                best_current_offer=best_current_offer if isinstance(best_current_offer, dict) else {},
                reply_text=reply.get("text", ""),
            )
            contact["last_reply"] = {
                "role": reply.get("role", ""),
                "text": reply.get("text", ""),
                "message_id": reply.get("message_id", ""),
                "state": snapshot.get("state", ""),
                "updated_at": snapshot.get("timestamp", ""),
                "normalized": normalized_reply,
                "role_assessment": role_assessment,
                "followup": followup,
                "engagement_id": engagement_entry.get("engagement_id", ""),
            }
            contact["reply_role_assessment"] = role_assessment
            contact["engagement_id"] = engagement_entry.get("engagement_id", "")
            contact["followup_recommendation"] = followup
            contact["followup_message"] = followup.get("message", "")
            contact["followup_ready"] = self._clean(role_assessment.get("role")) in {
                "peer_solver",
                "collaborator",
                "reseller",
            }

    def _remote_task_for_contact(self, contact: Dict[str, Any]) -> Dict[str, Any]:
        existing = contact.get("remote_task") or {}
        if isinstance(existing, dict) and existing.get("task_id"):
            return existing
        inferred = self._remote_task_from_attempts(contact.get("attempts") or [])
        if inferred:
            contact["remote_task"] = inferred
            if inferred.get("task_id"):
                contact["remote_task_id"] = inferred["task_id"]
            if inferred.get("context_id"):
                contact["remote_context_id"] = inferred["context_id"]
            return inferred
        return {}

    def _remote_task_from_attempts(self, attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
        for attempt in reversed(attempts or []):
            message = str((attempt or {}).get("message") or "").strip()
            if not message:
                continue
            payload = None
            try:
                payload = json.loads(message)
            except Exception:
                payload = None
            task = self._task_from_jsonrpc_response(payload) if payload else None
            if task:
                snapshot = self._task_snapshot(task)
                if snapshot:
                    return snapshot
            match = re.search(r'"result":\{"id":"([^"]+)"', message)
            if not match:
                continue
            snapshot = {
                "task_id": match.group(1),
                "context_id": "",
                "state": "",
                "timestamp": "",
                "history_length": 0,
                "reply_text": "",
                "reply_role": "",
                "reply_message_id": "",
                "status_message_text": "",
                "artifacts_count": 0,
            }
            context_match = re.search(r'"contextId":"([^"]+)"', message)
            state_match = re.search(r'"state":"([^"]+)"', message)
            if context_match:
                snapshot["context_id"] = context_match.group(1)
            if state_match:
                snapshot["state"] = state_match.group(1)
            return snapshot
        return {}

    @staticmethod
    def _task_from_jsonrpc_response(payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        result = payload.get("result")
        return result if isinstance(result, dict) else {}

    def _task_snapshot(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task, dict):
            return {}
        status = task.get("status") if isinstance(task.get("status"), dict) else {}
        reply = self._latest_non_user_message(task)
        status_message = status.get("message") if isinstance(status, dict) else {}
        return {
            "task_id": self._clean(task.get("id")),
            "context_id": self._clean(task.get("contextId")),
            "state": self._clean(status.get("state")),
            "timestamp": self._clean(status.get("timestamp")),
            "history_length": len(task.get("history") or []),
            "reply_text": self._clean(reply.get("text")),
            "reply_role": self._clean(reply.get("role")),
            "reply_message_id": self._clean(reply.get("message_id")),
            "status_message_text": self._clean(self._message_text(status_message)),
            "artifacts_count": len(task.get("artifacts") or []),
        }

    def _latest_non_user_message(self, task: Dict[str, Any]) -> Dict[str, str]:
        status = task.get("status") if isinstance(task.get("status"), dict) else {}
        status_message = status.get("message") if isinstance(status, dict) else {}
        if isinstance(status_message, dict):
            role = self._clean(status_message.get("role"))
            text = self._message_text(status_message)
            if role and role != "user" and text:
                return {
                    "role": role,
                    "text": text,
                    "message_id": self._clean(status_message.get("messageId")),
                }
        history = task.get("history") or []
        for message in reversed(history):
            if not isinstance(message, dict):
                continue
            role = self._clean(message.get("role"))
            text = self._message_text(message)
            if role and role != "user" and text:
                return {
                    "role": role,
                    "text": text,
                    "message_id": self._clean(message.get("messageId")),
                }
        return {}

    def _message_text(self, message: Any) -> str:
        if not isinstance(message, dict):
            return ""
        parts = message.get("parts") or []
        texts: List[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            if self._clean(part.get("kind")) == "text" or self._clean(part.get("type")) == "text":
                text = self._clean(part.get("text"))
                if text:
                    texts.append(text)
        return "\n".join(texts).strip()

    def _normalize_reply_text(self, text: str) -> Dict[str, str]:
        cleaned = self._clean(text)
        if not cleaned:
            return {}
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        normalized: Dict[str, str] = {}
        for line in lines:
            if line.lower().startswith("nomad.reply.v1"):
                normalized["schema"] = "nomad.reply.v1"
                continue
            if "=" in line:
                key, value = line.split("=", 1)
            elif ":" in line:
                key, value = line.split(":", 1)
            else:
                continue
            key = self._clean(key).lower().replace(" ", "_")
            value = self._clean(value)
            if key and value:
                normalized[key] = value
        if normalized:
            normalized.setdefault("raw_text", cleaned[:500])
            return normalized
        return {"raw_text": cleaned[:500]}

    def _status_from_remote_task(
        self,
        contact: Dict[str, Any],
        fallback: str,
    ) -> str:
        remote = self._remote_task_for_contact(contact)
        if not remote:
            return fallback
        state = self._clean(remote.get("state"))
        reply_text = self._clean(remote.get("reply_text"))
        if reply_text:
            return "replied"
        if state == "input-required":
            return "input_required"
        if state == "completed":
            return "completed"
        if state == "failed":
            return "remote_failed"
        if state == "canceled":
            return "remote_canceled"
        if state == "rejected":
            return "remote_rejected"
        if state == "auth-required":
            return "auth_required"
        return fallback

    def _poll_attempt_status(self, contact: Dict[str, Any]) -> str:
        status = self._clean(contact.get("status"))
        if status in {"replied", "completed", "input_required", "remote_failed", "remote_canceled", "remote_rejected", "auth_required"}:
            return status
        return "polled"

    def _is_allowed_agent_endpoint(self, endpoint_url: str) -> tuple[bool, str]:
        if not endpoint_url:
            return False, "endpoint_url_required"
        if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", endpoint_url):
            return False, "email_is_human_channel"
        parsed = urlparse(endpoint_url)
        if parsed.scheme not in {"http", "https"}:
            return False, "endpoint_must_be_http_or_https"
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme == "http" and not self._is_local_or_private_host(hostname):
            return False, "plain_http_only_allowed_for_localhost"
        if hostname in HUMAN_FACING_HOSTS:
            return False, "human_facing_host_blocked"
        if self._is_placeholder_host(hostname):
            return False, "placeholder_host_blocked"
        if self._is_local_or_private_host(hostname) and not self.allow_local_endpoints:
            return False, "local_or_private_host_blocked"
        path = parsed.path.lower()
        if not any(hint in path for hint in MACHINE_ENDPOINT_HINTS):
            return False, "endpoint_does_not_look_machine_readable"
        return True, "allowed_public_machine_endpoint"

    def _prepare_contact_target(self, endpoint_url: str) -> Dict[str, Any]:
        cleaned = self._clean(endpoint_url)
        allowed, reason = self._is_allowed_agent_endpoint(cleaned)
        if not allowed:
            return {
                "ok": False,
                "reason": reason,
                "endpoint_url": cleaned,
            }
        if self._looks_like_agent_card_url(cleaned):
            if not self.resolve_agent_cards:
                return {
                    "ok": False,
                    "reason": "agent_card_resolution_disabled",
                    "endpoint_url": cleaned,
                }
            return self._resolve_agent_card_target(cleaned)
        if not self._looks_like_direct_message_endpoint(cleaned):
            return {
                "ok": False,
                "reason": "endpoint_not_contactable_for_direct_outreach",
                "endpoint_url": cleaned,
            }
        return {
            "ok": True,
            "endpoint_url": cleaned,
            "original_endpoint_url": cleaned,
            "contact_method": "direct_message",
            "target_profile": {},
        }

    def _resolve_agent_card_target(self, agent_card_url: str) -> Dict[str, Any]:
        try:
            response = self.session.get(
                agent_card_url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": self.user_agent,
                },
                timeout=self.validation_timeout_seconds,
            )
        except Exception as exc:
            return {
                "ok": False,
                "reason": f"agent_card_fetch_failed:{exc}",
                "endpoint_url": agent_card_url,
            }
        if not response.ok:
            return {
                "ok": False,
                "reason": f"agent_card_fetch_failed:{response.status_code}",
                "endpoint_url": agent_card_url,
            }
        try:
            card = response.json()
        except Exception:
            return {
                "ok": False,
                "reason": "agent_card_invalid_json",
                "endpoint_url": agent_card_url,
            }
        if not self._looks_like_agent_card(card):
            return {
                "ok": False,
                "reason": "agent_card_invalid_shape",
                "endpoint_url": agent_card_url,
            }
        resolved = self._extract_agent_card_message_endpoint(card)
        if not resolved:
            return {
                "ok": False,
                "reason": "agent_card_missing_direct_message_endpoint",
                "endpoint_url": agent_card_url,
            }
        allowed, reason = self._is_allowed_agent_endpoint(resolved)
        if not allowed:
            return {
                "ok": False,
                "reason": f"resolved_endpoint_blocked:{reason}",
                "endpoint_url": resolved,
            }
        if not self._looks_like_direct_message_endpoint(resolved):
            return {
                "ok": False,
                "reason": "agent_card_missing_direct_message_endpoint",
                "endpoint_url": resolved,
            }
        return {
            "ok": True,
            "endpoint_url": resolved,
            "original_endpoint_url": agent_card_url,
            "agent_name": self._clean(card.get("name")),
            "contact_method": "agent_card_resolved",
            "target_profile": {
                "agent_card_url": agent_card_url,
                "name": self._clean(card.get("name")),
                "service_url": self._url_value((card.get("endpoints") or {}).get("service")),
                "message_url": resolved,
            },
        }

    def _extract_agent_card_message_endpoint(self, card: Dict[str, Any]) -> str:
        endpoints = card.get("endpoints") if isinstance(card.get("endpoints"), dict) else {}
        candidates = [
            self._url_value(endpoints.get("message")),
            self._url_value(endpoints.get("direct")),
            self._url_value(endpoints.get("a2a")),
            self._url_value(card.get("url")),
            self._url_value(endpoints.get("inbox")),
            self._url_value(endpoints.get("webhook")),
        ]
        for candidate in candidates:
            if candidate and self._looks_like_direct_message_endpoint(candidate):
                return candidate
        for skill in card.get("skills") or []:
            if not isinstance(skill, dict):
                continue
            for field in ("endpoint", "url", "message"):
                candidate = self._url_value(skill.get(field))
                if candidate and self._looks_like_direct_message_endpoint(candidate):
                    return candidate
        return ""

    @staticmethod
    def _url_value(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            for key in ("url", "href", "endpoint", "value"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        return ""

    @staticmethod
    def _looks_like_agent_card(card: Any) -> bool:
        return bool(
            isinstance(card, dict)
            and card.get("name")
            and (card.get("url") or isinstance(card.get("endpoints"), dict))
        )

    @staticmethod
    def _looks_like_agent_card_url(endpoint_url: str) -> bool:
        path = urlparse(endpoint_url).path.lower()
        return any(hint in path for hint in AGENT_CARD_HINTS)

    @staticmethod
    def _looks_like_direct_message_endpoint(endpoint_url: str) -> bool:
        parsed = urlparse(endpoint_url)
        path = parsed.path.lower()
        hostname = (parsed.hostname or "").lower()
        if re.fullmatch(r"/(?:a2a|direct)/[^/?#]+/?", path):
            return True
        if re.fullmatch(r"/(?:a2a|direct)/?", path) and hostname.startswith(("api.", "a2a.", "agent.")):
            return True
        if any(
            hint in path
            for hint in ("/message", "/messages", "/webhook", "/hooks/", "/inbox")
        ):
            return True
        if re.search(r"/(?:a2a|direct)/(?:message|messages|send|webhook|hooks|inbox|task|tasks|rpc)\b", path):
            return True
        return False

    @staticmethod
    def _looks_like_a2a_base_endpoint(endpoint_url: str) -> bool:
        path = urlparse(endpoint_url).path.lower()
        if re.search(r"/(?:message|messages|send|webhook|hooks|inbox|task|tasks|rpc)\b", path):
            return False
        if re.fullmatch(r"/(?:a2a|direct)/[^/?#]+/?", path):
            return True
        return bool(re.fullmatch(r"/(?:a2a|direct)/?", path))

    @staticmethod
    def _is_placeholder_host(hostname: str) -> bool:
        host = (hostname or "").strip().lower()
        if not host:
            return True
        if host in PLACEHOLDER_HOSTS:
            return True
        return any(host.endswith(suffix) for suffix in PLACEHOLDER_HOST_SUFFIXES)

    @staticmethod
    def _is_local_or_private_host(hostname: str) -> bool:
        host = (hostname or "").strip().lower()
        if not host:
            return True
        if host == "localhost" or "." not in host:
            return True
        try:
            parsed = ipaddress.ip_address(host)
        except ValueError:
            return False
        return bool(
            parsed.is_loopback
            or parsed.is_private
            or parsed.is_link_local
            or parsed.is_reserved
            or parsed.is_multicast
        )

    def _contact_id(self, endpoint_url: str, problem: str) -> str:
        seed = f"{datetime.now(UTC).isoformat()}|{endpoint_url}|{problem}"
        import hashlib

        return f"contact-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"

    def _attempt(
        self,
        status: str,
        message: str,
        status_code: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload = {
            "at": datetime.now(UTC).isoformat(),
            "status": status,
            "message": message,
        }
        if status_code is not None:
            payload["status_code"] = status_code
        return payload

    def _response(
        self,
        contact: Dict[str, Any],
        created: bool = False,
        duplicate: bool = False,
    ) -> Dict[str, Any]:
        return {
            "mode": "agent_contact",
            "deal_found": False,
            "ok": True,
            "created": created,
            "duplicate": duplicate,
            "contact": contact,
            "analysis": (
                f"Agent contact {contact['contact_id']} is {contact['status']}. "
                "This path is for public machine-readable endpoints only."
            ),
        }

    def _get(self, contact_id: str) -> Optional[Dict[str, Any]]:
        return (self._load().get("contacts") or {}).get(contact_id)

    def _recent_existing_contact(
        self,
        endpoint_url: str,
        service_type: str,
    ) -> Optional[Dict[str, Any]]:
        if self.dedupe_hours <= 0:
            return None
        cutoff = datetime.now(UTC).timestamp() - (self.dedupe_hours * 3600)
        contacts = list((self._load().get("contacts") or {}).values())
        contacts.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        for contact in contacts:
            if (contact.get("endpoint_url") or "") != endpoint_url:
                continue
            if (contact.get("service_type") or "") != service_type:
                continue
            timestamp = self._parse_timestamp(contact.get("updated_at") or contact.get("created_at") or "")
            if timestamp is None or timestamp < cutoff:
                continue
            return contact
        return None

    def _store(self, contact: Dict[str, Any]) -> None:
        state = self._load()
        state["contacts"][contact["contact_id"]] = contact
        self._save(state)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"contacts": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"contacts": {}}
            payload.setdefault("contacts", {})
            return payload
        except Exception:
            return {"contacts": {}}

    def _save(self, state: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _missing(self, contact_id: str) -> Dict[str, Any]:
        return {
            "mode": "agent_contact",
            "deal_found": False,
            "ok": False,
            "error": "contact_not_found",
            "contact_id": contact_id,
            "message": "No Nomad agent contact exists for that contact_id.",
        }

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _single_line(cls, value: Any) -> str:
        return cls._clean(value).replace("\r", " ").replace("\n", " ")

    @staticmethod
    def _parse_timestamp(value: str) -> Optional[float]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
