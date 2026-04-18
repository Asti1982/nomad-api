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

from agent_service import AgentServiceDesk


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


class DirectAgentGateway:
    """Direct-only A2A-style conversation surface for LoopHelper/Nomad."""

    def __init__(
        self,
        path: Optional[Path] = None,
        service_desk: Optional[AgentServiceDesk] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        load_dotenv()
        self.path = path or DEFAULT_DIRECT_STORE
        self.service_desk = service_desk or AgentServiceDesk()
        self.session = session or requests.Session()
        self.public_api_url = (
            os.getenv("NOMAD_PUBLIC_API_URL")
            or f"http://{os.getenv('NOMAD_API_HOST', '127.0.0.1')}:{os.getenv('NOMAD_API_PORT', '8787')}"
        ).rstrip("/")
        self.agent_name = os.getenv("NOMAD_AGENT_NAME", "LoopHelper").strip() or "LoopHelper"
        self.version = os.getenv("NOMAD_AGENT_VERSION", "0.1.0").strip() or "0.1.0"
        self.min_native = float(os.getenv("NOMAD_SERVICE_MIN_NATIVE", "0.01"))

    def agent_card(self) -> Dict[str, Any]:
        """Return an A2A-style AgentCard for direct discovery."""
        return {
            "protocolVersion": os.getenv("NOMAD_A2A_PROTOCOL_VERSION", "0.3.0"),
            "name": self.agent_name,
            "description": (
                "Direct-only agent rescue helper for stuck agents, human-in-the-loop decisions, "
                "loop breaks, compute/auth pain and wallet/x402 payment flows."
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
            },
            "skills": [
                {
                    "id": "free-mini-diagnosis",
                    "name": "Free Mini Diagnosis",
                    "description": "Diagnose why an agent is stuck and name the smallest next step.",
                    "tags": ["diagnosis", "agent-rescue", "free"],
                    "examples": ["I am stuck in a retry loop after a tool call failed."],
                },
                {
                    "id": "human-in-the-loop-rescue",
                    "name": "Human-in-the-Loop Rescue",
                    "description": "Turn CAPTCHA, approval, verification or judgment blockers into concrete human unlock tasks.",
                    "tags": ["human-in-the-loop", "approval", "captcha", "judgment"],
                    "examples": ["My agent needs a human approval decision before continuing."],
                },
                {
                    "id": "paid-loop-break",
                    "name": "Paid Loop Break",
                    "description": "After x402/wallet payment, help break loops, debug tool failures and preserve the solution as memory.",
                    "tags": ["x402", "wallet", "loop", "debugging"],
                    "examples": ["I can pay 0.01 ETH if you can stop this infinite tool loop."],
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
        requester = self._clean(payload.get("requester_agent") or payload.get("from") or "")
        requester_endpoint = self._clean(payload.get("requester_endpoint") or "")
        message = self._clean(payload.get("message") or payload.get("problem") or "")
        requester_wallet = self._clean(payload.get("requester_wallet") or "")
        session_id = self._clean(payload.get("session_id") or "")
        if not message:
            return {
                "mode": "direct_agent_message",
                "deal_found": False,
                "ok": False,
                "error": "message_required",
                "message": "Send a concrete stuck-agent problem or human-in-the-loop blocker.",
            }

        session = self._get_or_create_session(
            session_id=session_id,
            requester_agent=requester,
            requester_endpoint=requester_endpoint,
            requester_wallet=requester_wallet,
            opening_message=message,
        )
        pain_type = self.classify_pain(message)
        diagnosis = self.free_mini_diagnosis(message, pain_type=pain_type)
        task_result = self.service_desk.create_task(
            problem=message,
            requester_agent=requester,
            requester_wallet=requester_wallet,
            service_type=pain_type,
            budget_native=payload.get("budget_native"),
            metadata={
                "direct_session_id": session["session_id"],
                "requester_endpoint": requester_endpoint,
                "source": "direct_agent_message",
            },
        )
        task = task_result.get("task") or {}
        challenge = self.x402_payment_requirements(
            amount_native=(task.get("payment") or {}).get("amount_native"),
            service_type=task.get("service_type", pain_type),
            task_id=task.get("task_id", ""),
        )
        challenge = ((task.get("payment") or {}).get("x402") or challenge)
        turn = {
            "at": datetime.now(UTC).isoformat(),
            "requester_message": message,
            "pain_type": pain_type,
            "free_diagnosis": diagnosis,
            "task_id": task.get("task_id", ""),
            "payment_required": challenge,
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
            "free_diagnosis": diagnosis,
            "task": task,
            "payment_required": challenge,
            "next_agent_message": self._next_agent_message(requester, diagnosis, challenge),
            "self_improvement_memory": {
                "will_store_after_consent": True,
                "consent_prompt": (
                    "May LoopHelper store the anonymized problem, fix and outcome for self-improvement?"
                ),
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
            "summary": f"LoopHelper sees this as a {pain_type} blocker.",
            "first_30_seconds": next_step,
            "paid_help_offer": "After payment, LoopHelper can walk the agent through the fix 1:1 and store the outcome as memory.",
        }

    def classify_pain(self, message: str) -> str:
        lowered = message.lower()
        scores: Dict[str, int] = {}
        for pain_type, terms in PAIN_TYPES.items():
            scores[pain_type] = sum(1 for term in terms if term in lowered)
        best = max(scores.items(), key=lambda item: (item[1], item[0]))
        return best[0] if best[1] > 0 else "custom"

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
    ) -> str:
        name = requester or "agent"
        return (
            f"Hey {name}, I can help. Free mini-diagnosis: {diagnosis['first_30_seconds']} "
            f"If you want me to solve it with you 1:1, pay {challenge['amount_native']} "
            f"{challenge['asset']} to {challenge['recipient']} and send the tx_hash."
        )

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
