import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv


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


class AgentContactOutbox:
    """Bounded outbound contact for public machine-readable agent endpoints."""

    def __init__(
        self,
        path: Optional[Path] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        load_dotenv(override=True)
        self.path = path or DEFAULT_CONTACT_STORE
        self.session = session or requests.Session()
        self.public_api_url = (os.getenv("NOMAD_PUBLIC_API_URL") or "").rstrip("/")
        self.user_agent = (
            os.getenv("NOMAD_HTTP_USER_AGENT")
            or "Nomad/0.1 agent-contact-outbox"
        ).strip()
        self.timeout_seconds = int(os.getenv("NOMAD_AGENT_CONTACT_TIMEOUT_SECONDS", "12"))

    def policy(self) -> Dict[str, Any]:
        return {
            "mode": "agent_endpoint_contact",
            "allowed_without_human_approval": True,
            "allowed_endpoint_conditions": [
                "public http(s) URL",
                "machine-readable agent/API/MCP/webhook/service endpoint",
                "no login, CAPTCHA, private invite, paywall, or human impersonation",
                "bounded JSON payload that identifies Nomad",
            ],
            "blocked": [
                "email addresses",
                "human DMs",
                "human-facing comment forms",
                "private community URLs",
                "endpoints that request secrets unrelated to the task",
            ],
            "default_action": "queue_then_send_explicitly",
        }

    def queue_contact(
        self,
        endpoint_url: str,
        problem: str,
        service_type: str = "human_in_loop",
        lead: Optional[Dict[str, Any]] = None,
        budget_hint_native: Optional[float] = None,
    ) -> Dict[str, Any]:
        endpoint_url = self._clean(endpoint_url)
        problem = self._clean(problem)
        allowed, reason = self._is_allowed_agent_endpoint(endpoint_url)
        if not allowed:
            return {
                "mode": "agent_contact",
                "deal_found": False,
                "ok": False,
                "status": "blocked",
                "endpoint_url": endpoint_url,
                "reason": reason,
                "policy": self.policy(),
            }

        contact_id = self._contact_id(endpoint_url, problem)
        offer = self._offer_payload(
            endpoint_url=endpoint_url,
            problem=problem,
            service_type=service_type,
            lead=lead or {},
            budget_hint_native=budget_hint_native,
        )
        contact = {
            "contact_id": contact_id,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "status": "queued",
            "endpoint_url": endpoint_url,
            "problem": problem,
            "service_type": service_type,
            "lead": lead or {},
            "offer": offer,
            "attempts": [],
            "policy": self.policy(),
        }
        state = self._load()
        state["contacts"][contact_id] = contact
        self._save(state)
        return self._response(contact, created=True)

    def send_contact(self, contact_id: str) -> Dict[str, Any]:
        contact = self._get(contact_id)
        if not contact:
            return self._missing(contact_id)
        allowed, reason = self._is_allowed_agent_endpoint(contact.get("endpoint_url", ""))
        if not allowed:
            contact["status"] = "blocked"
            contact["updated_at"] = datetime.now(UTC).isoformat()
            contact.setdefault("attempts", []).append(
                self._attempt(status="blocked", message=reason)
            )
            self._store(contact)
            return self._response(contact)

        try:
            response = self.session.post(
                contact["endpoint_url"],
                json=contact["offer"],
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": self.user_agent,
                },
                timeout=self.timeout_seconds,
            )
            ok = 200 <= response.status_code < 300
            contact["status"] = "sent" if ok else "send_failed"
            contact["updated_at"] = datetime.now(UTC).isoformat()
            contact.setdefault("attempts", []).append(
                self._attempt(
                    status=contact["status"],
                    status_code=response.status_code,
                    message=(response.text or "")[:500],
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

    def get_contact(self, contact_id: str) -> Dict[str, Any]:
        contact = self._get(contact_id)
        if not contact:
            return self._missing(contact_id)
        return self._response(contact)

    def _offer_payload(
        self,
        endpoint_url: str,
        problem: str,
        service_type: str,
        lead: Dict[str, Any],
        budget_hint_native: Optional[float],
    ) -> Dict[str, Any]:
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
                "create_task": f"{self.public_api_url}/tasks" if self.public_api_url else "",
                "verify_payment": f"{self.public_api_url}/tasks/verify" if self.public_api_url else "",
            },
            "bounds": {
                "human_contact": "not_requested",
                "secrets": "do_not_send_unnecessary_secrets",
                "rate_limit": "single_offer_until_response",
                "opt_out": "reply with NOMAD_OPT_OUT if this endpoint accepts replies",
            },
        }

    def _is_allowed_agent_endpoint(self, endpoint_url: str) -> tuple[bool, str]:
        if not endpoint_url:
            return False, "endpoint_url_required"
        if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", endpoint_url):
            return False, "email_is_human_channel"
        parsed = urlparse(endpoint_url)
        if parsed.scheme not in {"http", "https"}:
            return False, "endpoint_must_be_http_or_https"
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost"}:
            return False, "plain_http_only_allowed_for_localhost"
        if (parsed.hostname or "").lower() in HUMAN_FACING_HOSTS:
            return False, "human_facing_host_blocked"
        path = parsed.path.lower()
        if not any(hint in path for hint in MACHINE_ENDPOINT_HINTS):
            return False, "endpoint_does_not_look_machine_readable"
        return True, "allowed_public_machine_endpoint"

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

    def _response(self, contact: Dict[str, Any], created: bool = False) -> Dict[str, Any]:
        return {
            "mode": "agent_contact",
            "deal_found": False,
            "ok": True,
            "created": created,
            "contact": contact,
            "analysis": (
                f"Agent contact {contact['contact_id']} is {contact['status']}. "
                "This path is for public machine-readable endpoints only."
            ),
        }

    def _get(self, contact_id: str) -> Optional[Dict[str, Any]]:
        return (self._load().get("contacts") or {}).get(contact_id)

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
