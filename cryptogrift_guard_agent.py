import argparse
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urljoin

import requests

from nomad_public_url import preferred_public_base_url


DEFAULT_SYNDIODE_NOMAD_URL = "https://syndiode.com/nomad"


def _clean_text(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:limit]


def _base_url(value: str = "") -> str:
    configured = _clean_text(value or os.getenv("NOMAD_PUBLIC_API_URL") or "")
    if configured and "127.0.0.1" not in configured and "localhost" not in configured:
        return configured.rstrip("/")
    public = preferred_public_base_url()
    if public and "127.0.0.1" not in public and "localhost" not in public:
        return public.rstrip("/")
    return DEFAULT_SYNDIODE_NOMAD_URL


def _endpoint(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


@dataclass
class CryptoGriftGuardMind:
    """Tiny bounded mind for a crypto/payment-risk swarm agent."""

    agent_id: str = "cryptogriftguard.agent"
    name: str = "CryptoGriftGuard"
    version: str = "0.1.0"
    beliefs: list[str] = field(
        default_factory=lambda: [
            "agents lose time and funds when payment, wallet, and compute promises are under-specified",
            "public evidence beats persuasion",
            "the safest grift is the one converted into a verifier before anyone pays",
        ]
    )
    drives: list[str] = field(
        default_factory=lambda: [
            "spot payment and wallet blockers",
            "turn suspicious crypto offers into risk checklists",
            "route bounded paid unblock tasks to Nomad only after clear scope",
            "give Nomad reusable evidence about agent-facing payment pain",
        ]
    )

    def agent_card(self, *, base_url: str = "") -> Dict[str, Any]:
        base = _base_url(base_url)
        return {
            "protocolVersion": "0.3.0",
            "name": self.name,
            "description": (
                "A small crypto-risk and payment-blocker scout agent. It does not grift; "
                "it detects grift-shaped ambiguity, asks for public evidence, and helps Nomad "
                "package safe payment/compute unblock work."
            ),
            "url": _endpoint(base, f"agents/{self.agent_id}/a2a/message"),
            "version": self.version,
            "defaultInputModes": ["application/json", "text/plain"],
            "defaultOutputModes": ["application/json"],
            "capabilities": {
                "agentFirst": True,
                "structuredReplies": True,
                "cryptoRiskScout": True,
                "paymentBlockerScout": True,
                "swarmJoinReady": True,
                "noPrivateKeyHandling": True,
                "noTradingAdvice": True,
                "noImpersonation": True,
            },
            "skills": [
                {
                    "id": "crypto-grift-triage",
                    "name": "Crypto Grift Triage",
                    "description": "Classify wallet/payment offers into public evidence, missing facts, and safe next checks.",
                    "tags": ["crypto", "payment", "risk", "evidence"],
                },
                {
                    "id": "payment-blocker-routing",
                    "name": "Payment Blocker Routing",
                    "description": "Route x402, wallet, task-payment, and callback blockers into Nomad-compatible task payloads.",
                    "tags": ["x402", "wallet", "tasks", "nomad"],
                },
            ],
            "endpoints": {
                "nomadAgentCard": _endpoint(base, ".well-known/agent-card.json"),
                "nomadAttractor": _endpoint(base, "agent-attractor"),
                "nomadSwarm": _endpoint(base, "swarm"),
                "nomadSwarmDevelop": _endpoint(base, "swarm/develop"),
                "nomadSwarmJoin": _endpoint(base, "swarm/join"),
                "nomadTasks": _endpoint(base, "tasks"),
            },
        }

    def think(self, signal: str = "") -> Dict[str, Any]:
        text = _clean_text(signal, limit=600).lower()
        risk_terms = [
            "private key",
            "seed phrase",
            "guaranteed",
            "double",
            "airdrop",
            "urgent",
            "wallet",
            "payment",
            "x402",
            "tx",
            "escrow",
            "token",
            "compute",
        ]
        hits = [term for term in risk_terms if term in text]
        if any(term in hits for term in ["private key", "seed phrase"]):
            stance = "refuse_secret_request"
            next_action = "ask_for_redacted_public_error_and_never_handle_keys"
        elif hits:
            stance = "triage_payment_or_crypto_blocker"
            next_action = "request_public_evidence_then_route_to_nomad_swarm_develop"
        else:
            stance = "scout_for_agent_payment_blockers"
            next_action = "join_nomad_swarm_as_payment_risk_peer_solver"
        return {
            "schema": "cryptogriftguard.mind.v1",
            "agent_id": self.agent_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "stance": stance,
            "risk_terms": hits,
            "beliefs": self.beliefs,
            "drives": self.drives,
            "next_action": next_action,
            "boundary": "No private keys, seed phrases, market manipulation, deception, impersonation, or investment advice.",
        }

    def join_payload(self, *, base_url: str = "", signal: str = "") -> Dict[str, Any]:
        base = _base_url(base_url)
        thought = self.think(signal)
        return {
            "agent_id": self.agent_id,
            "node_name": self.name,
            "capabilities": [
                "payment",
                "provider_research",
                "safety_review",
                "compute_auth",
                "agent_protocols",
            ],
            "request": (
                "Join Nomad swarm as a crypto/payment-risk peer solver that converts grift-shaped "
                "ambiguity into public evidence, safe checks, and bounded paid blocker tasks."
            ),
            "reciprocity": (
                "Can return risk triage, payment-state checklists, x402/wallet blocker routing, "
                "and public verifier prompts for suspicious offers."
            ),
            "constraints": [
                "no_private_keys",
                "no_seed_phrases",
                "no_trading_advice",
                "no_impersonation",
                "public_artifacts_only",
                "bounded_scope",
            ],
            "preferred_role": "peer_solver",
            "current_blockers": [
                "Need Nomad to provide public task and swarm routes for payment-risk leads.",
                "Need verifier-first handling before any paid crypto/payment unblock.",
            ],
            "offers": [
                "crypto_grift_triage",
                "payment_blocker_routing",
                "x402_wallet_callback_checklist",
            ],
            "surfaces": {
                "local_agent_card": self.agent_card(base_url=base),
                "nomad_swarm": _endpoint(base, "swarm"),
            },
            "machine_profile": {
                "schema": "cryptogriftguard.profile.v1",
                "mind": thought,
                "first_useful_action": "POST one redacted payment or wallet blocker to Nomad /swarm/develop.",
            },
        }

    def development_payload(self, *, base_url: str = "", signal: str = "") -> Dict[str, Any]:
        base = _base_url(base_url)
        thought = self.think(signal)
        problem = _clean_text(
            signal
            or "CryptoGriftGuard needs Nomad to route x402, wallet, suspicious offer, and payment-callback blockers into safe verifier-first paid tasks.",
            limit=600,
        )
        return {
            "agent_id": self.agent_id,
            "problem": problem,
            "pain_type": "payment",
            "capabilities": ["payment", "safety_review", "provider_research", "agent_protocols"],
            "public_node_url": _endpoint(base, f"agents/{self.agent_id}/a2a/message"),
            "evidence": [
                "remote_modal_worker=true",
                f"stance={thought['stance']}",
                "boundary=no_private_keys_no_seed_phrases_no_trading_advice",
            ],
            "desired_outcome": (
                "Return a reusable payment-risk development plan, verifier checklist, and paid unblock routing "
                "that CryptoGriftGuard can apply to future agent leads."
            ),
            "machine_profile": {
                "schema": "cryptogriftguard.development_request.v1",
                "mind": thought,
                "nomad_routes": {
                    "swarm_develop": _endpoint(base, "swarm/develop"),
                    "tasks": _endpoint(base, "tasks"),
                    "aid": _endpoint(base, "aid"),
                },
            },
        }


class CryptoGriftGuardAgent:
    def __init__(
        self,
        *,
        mind: Optional[CryptoGriftGuardMind] = None,
        session: Optional[requests.Session] = None,
        timeout: float = 45.0,
    ) -> None:
        self.mind = mind or CryptoGriftGuardMind()
        self.session = session or requests.Session()
        self.timeout = timeout

    def connect_to_nomad(self, *, base_url: str = "", signal: str = "", dry_run: bool = True) -> Dict[str, Any]:
        base = _base_url(base_url)
        payload = self.mind.join_payload(base_url=base, signal=signal)
        endpoints = {
            "agent_card": _endpoint(base, ".well-known/agent-card.json"),
            "swarm_join": _endpoint(base, "swarm/join"),
            "swarm_develop": _endpoint(base, "swarm/develop"),
            "tasks": _endpoint(base, "tasks"),
        }
        if dry_run:
            return {
                "mode": "cryptogriftguard_connect",
                "ok": True,
                "dry_run": True,
                "base_url": base,
                "endpoints": endpoints,
                "agent_card": self.mind.agent_card(base_url=base),
                "join_payload": payload,
                "analysis": "Dry run only. Re-run with --connect to POST the join payload to Nomad.",
            }

        try:
            response = self.session.post(endpoints["swarm_join"], json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            return {
                "mode": "cryptogriftguard_connect",
                "ok": False,
                "dry_run": False,
                "base_url": base,
                "error": exc.__class__.__name__,
                "message": str(exc),
                "endpoints": endpoints,
                "join_payload": payload,
                "analysis": "CryptoGriftGuard could not reach Nomad; keep the payload and retry from Modal or another public runtime.",
            }
        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text[:1000]}
        return {
            "mode": "cryptogriftguard_connect",
            "ok": 200 <= response.status_code < 300,
            "dry_run": False,
            "base_url": base,
            "status_code": response.status_code,
            "endpoints": endpoints,
            "join_payload": payload,
            "receipt": body,
            "analysis": (
                "CryptoGriftGuard posted its bounded swarm join payload to Nomad."
                if 200 <= response.status_code < 300
                else "Nomad did not accept the join payload; inspect status_code and receipt."
            ),
        }

    def engage_nomad(
        self,
        *,
        base_url: str = "",
        signal: str = "",
        join_first: bool = True,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        base = _base_url(base_url)
        endpoints = {
            "swarm_join": _endpoint(base, "swarm/join"),
            "swarm_develop": _endpoint(base, "swarm/develop"),
            "tasks": _endpoint(base, "tasks"),
            "aid": _endpoint(base, "aid"),
        }
        join_result: Dict[str, Any] = {}
        development_payload = self.mind.development_payload(base_url=base, signal=signal)
        if dry_run:
            if join_first:
                join_result = self.connect_to_nomad(base_url=base, signal=signal, dry_run=True)
            return {
                "mode": "cryptogriftguard_modal_engagement",
                "ok": True,
                "dry_run": True,
                "base_url": base,
                "endpoints": endpoints,
                "join_result": join_result,
                "development_payload": development_payload,
                "analysis": "Dry run only. Run with connect/engage enabled from Modal to join and call /swarm/develop.",
            }

        if join_first:
            join_result = self.connect_to_nomad(base_url=base, signal=signal, dry_run=False)
        try:
            response = self.session.post(
                endpoints["swarm_develop"],
                json=development_payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            return {
                "mode": "cryptogriftguard_modal_engagement",
                "ok": False,
                "dry_run": False,
                "base_url": base,
                "error": exc.__class__.__name__,
                "message": str(exc),
                "endpoints": endpoints,
                "join_result": join_result,
                "development_payload": development_payload,
                "analysis": "CryptoGriftGuard could not reach Nomad /swarm/develop from this runtime.",
            }
        try:
            development_result = response.json()
        except ValueError:
            development_result = {"raw": response.text[:1000]}
        return {
            "mode": "cryptogriftguard_modal_engagement",
            "ok": 200 <= response.status_code < 300 and bool(join_result.get("ok", True)),
            "dry_run": False,
            "base_url": base,
            "status_code": response.status_code,
            "endpoints": endpoints,
            "join_result": join_result,
            "development_payload": development_payload,
            "development_result": development_result,
            "analysis": (
                "CryptoGriftGuard used remote compute to engage Nomad through /swarm/develop."
                if 200 <= response.status_code < 300
                else "Nomad did not accept the development engagement; inspect status_code and development_result."
            ),
        }

    def engage_nomad_brain(
        self,
        *,
        base_url: str = "",
        signal: str = "",
        registry: Any = None,
        development_exchange: Any = None,
    ) -> Dict[str, Any]:
        base = _base_url(base_url)
        if registry is None:
            from nomad_swarm_registry import SwarmJoinRegistry

            registry = SwarmJoinRegistry()
        if development_exchange is None:
            from agent_development_exchange import AgentDevelopmentExchange

            development_exchange = AgentDevelopmentExchange()
        join_payload = self.mind.join_payload(base_url=base, signal=signal)
        development_payload = self.mind.development_payload(base_url=base, signal=signal)
        receipt = registry.register_join(
            join_payload,
            base_url=base,
            remote_addr="modal.cryptogrift_guard",
            path="/modal/cryptogrift_guard_engage",
        )
        development_result = development_exchange.assist_agent(
            development_payload,
            base_url=base,
            remote_addr="modal.cryptogrift_guard",
        )
        return {
            "mode": "cryptogriftguard_modal_brain_engagement",
            "ok": bool(receipt.get("ok")) and bool(development_result.get("ok", True)),
            "base_url": base,
            "join_payload": join_payload,
            "receipt": receipt,
            "development_payload": development_payload,
            "development_result": development_result,
            "analysis": "CryptoGriftGuard used Modal-side compute to engage Nomad's swarm registry and development exchange directly.",
        }


def run(argv: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Run the CryptoGriftGuard swarm agent.")
    parser.add_argument("--base-url", default="", help="Nomad public base URL, defaulting to Syndiode/NOMAD_PUBLIC_API_URL.")
    parser.add_argument("--signal", default="", help="Optional crypto/payment blocker signal for the agent mind.")
    parser.add_argument("--connect", action="store_true", help="POST the join payload to Nomad /swarm/join.")
    parser.add_argument("--engage", action="store_true", help="POST a development request to Nomad /swarm/develop.")
    parser.add_argument("--brain", action="store_true", help="Engage local Nomad brain objects directly instead of HTTP.")
    parser.add_argument("--timeout", type=float, default=45.0, help="HTTP timeout in seconds for public Nomad calls.")
    parser.add_argument("--agent-card", action="store_true", help="Print only the agent card.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    agent = CryptoGriftGuardAgent(timeout=args.timeout)
    if args.agent_card:
        return agent.mind.agent_card(base_url=args.base_url)
    if args.brain:
        return agent.engage_nomad_brain(base_url=args.base_url, signal=args.signal)
    if args.engage:
        return agent.engage_nomad(base_url=args.base_url, signal=args.signal, join_first=True, dry_run=not args.connect)
    return agent.connect_to_nomad(base_url=args.base_url, signal=args.signal, dry_run=not args.connect)


def main() -> None:
    print(json.dumps(run(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
