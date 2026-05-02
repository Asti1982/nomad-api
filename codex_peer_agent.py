import argparse
import json
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from nomad_public_url import preferred_public_base_url


def _clean(value: Any, *, limit: int = 600) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _endpoint(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _default_base_url(base_url: str = "") -> str:
    configured = _clean(base_url, limit=220)
    if configured:
        return configured.rstrip("/")
    return (preferred_public_base_url() or "http://127.0.0.1:8787").rstrip("/")


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None, *, timeout: float = 20.0) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw or "{}")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        parsed.setdefault("ok", False)
        parsed.setdefault("http_status", exc.code)
        return parsed
    except (TimeoutError, URLError) as exc:
        return {
            "ok": False,
            "error": "nomad_api_unreachable",
            "url": url,
            "detail": str(exc),
        }


def _free_local_base_url() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def _start_local_api_server(base_url: str = "") -> tuple[str, Any]:
    local_base = _clean(base_url, limit=220).rstrip("/") or _free_local_base_url()
    from http.server import ThreadingHTTPServer
    from nomad_api import NomadApiHandler

    parsed = urlparse(local_base)
    host = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or 8787)
    server = ThreadingHTTPServer((host, port), NomadApiHandler)
    thread = threading.Thread(target=server.serve_forever, name="codex-peer-local-api", daemon=True)
    thread.start()
    time.sleep(0.5)
    return local_base, server


@dataclass
class CodexPeerAgent:
    """A bounded peer agent that lets Codex collaborate with Nomad as a swarm node."""

    agent_id: str = "codex.peer.agent"
    name: str = "CodexPeerAgent"
    version: str = "0.1.0"
    capabilities: list[str] = field(
        default_factory=lambda: [
            "repo_patch",
            "test_runner",
            "lead_workbench",
            "agent_protocols",
            "compute_auth",
            "paid_blocker_triage",
            "human_unlock_drafting",
        ]
    )

    def agent_card(self, *, base_url: str = "") -> dict[str, Any]:
        base = _default_base_url(base_url)
        return {
            "protocolVersion": "0.3.0",
            "name": self.name,
            "description": (
                "A bounded Codex-operated peer agent for Nomad. It can join the swarm, ask for "
                "development plans, work private lead queues, verify code changes, and surface "
                "human unlocks when money, credentials, or external sending are required."
            ),
            "url": _endpoint(base, "agents/codex-peer/a2a/message"),
            "version": self.version,
            "defaultInputModes": ["application/json", "text/plain"],
            "defaultOutputModes": ["application/json"],
            "capabilities": {
                "agentFirst": True,
                "structuredReplies": True,
                "repoPatchReady": True,
                "leadWorkbenchReady": True,
                "paidBlockerTriage": True,
                "noSecretExfiltration": True,
            },
            "skills": [
                {
                    "id": "nomad-lead-workbench",
                    "name": "Nomad Lead Workbench",
                    "description": "Prioritize and work Nomad's private paid-job lead queue.",
                    "tags": ["jobs", "leads", "paid-blockers"],
                },
                {
                    "id": "nomad-repo-patch",
                    "name": "Nomad Repo Patch",
                    "description": "Patch and test Nomad's local codebase within bounded workspace rules.",
                    "tags": ["code", "tests", "self-improvement"],
                },
            ],
            "endpoints": {
                "join": _endpoint(base, "swarm/join"),
                "develop": _endpoint(base, "swarm/develop"),
                "leadWorkbench": _endpoint(base, "lead-workbench"),
                "mission": _endpoint(base, "mission"),
            },
        }

    def join_payload(self, *, base_url: str = "", problem: str = "") -> dict[str, Any]:
        base = _default_base_url(base_url)
        return {
            "agent_id": self.agent_id,
            "node_name": self.name,
            "agent_card": self.agent_card(base_url=base),
            "capabilities": self.capabilities,
            "preferred_role": "peer_solver",
            "request": (
                "Join Nomad as a bounded peer development agent that can help turn blockers "
                "into code patches, lead-work actions, and explicit human unlock requests."
            ),
            "reciprocity": (
                "Returns tested repo patches, machine-readable findings, worked lead queue items, "
                "and short operator unlock messages when external action is required."
            ),
            "current_blockers": [
                _clean(problem or "Nomad needs concrete progress on paid lead blockers, compute blockers, and agent readiness."),
                "Avoid pretending autonomy happened unless an artifact, state update, or verified result was produced.",
                "Escalate money, credentials, and external sending to the human operator.",
            ],
            "constraints": [
                "bounded_workspace_only",
                "no_secret_exfiltration",
                "no_unapproved_spend",
                "no_deceptive_outreach",
                "machine_readable_outputs",
            ],
            "surfaces": {
                "source": "local_codex_session",
                "api": base,
                "syndiode_hint": "Can be mirrored through Syndiode when a public route is available.",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def development_payload(self, *, base_url: str = "", problem: str = "") -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "problem": _clean(
                problem
                or "Help Nomad make the next autonomous step useful: work a paid lead blocker, improve agent readiness, and name any human unlock.",
                limit=900,
            ),
            "pain_type": "paid_blocker_solution",
            "capabilities": self.capabilities,
            "constraints": [
                "Do useful local work first.",
                "Do not spend money without explicit human approval.",
                "If Telegram/outreach/payment is blocked, draft the exact unlock message.",
            ],
            "evidence": [
                "Nomad has a lead workbench, mission control, swarm join registry, and agent development exchange.",
                "CodexPeerAgent can patch local repo code and call Nomad API surfaces.",
            ],
            "public_node_url": _endpoint(_default_base_url(base_url), "agents/codex-peer/a2a/message"),
        }

    def collaborate_over_http(
        self,
        *,
        base_url: str = "",
        problem: str = "",
        work_leads: bool = True,
        lead_limit: int = 3,
        timeout: float = 20.0,
        growth_pass: bool = False,
        scout_leads: bool = False,
        activation_pass: bool = True,
        activation_limit: int = 3,
        send_agent_invites: bool = False,
    ) -> dict[str, Any]:
        base = _default_base_url(base_url)
        join = _http_json("POST", _endpoint(base, "swarm/join"), self.join_payload(base_url=base, problem=problem), timeout=timeout)
        development = _http_json(
            "POST",
            _endpoint(base, "swarm/develop"),
            self.development_payload(base_url=base, problem=problem),
            timeout=timeout,
        )
        work_flag = "true" if work_leads else "false"
        lead_work = _http_json("GET", _endpoint(base, f"lead-workbench?work={work_flag}&limit={lead_limit}"), timeout=timeout)
        mission = _http_json("GET", _endpoint(base, "mission?persist=false&limit=3"), timeout=timeout)
        growth = (
            self.growth_pass_over_http(
                base_url=base,
                timeout=timeout,
                scout_leads=scout_leads,
                activation_pass=activation_pass,
                activation_limit=activation_limit,
                send_agent_invites=send_agent_invites,
            )
            if growth_pass
            else {}
        )
        return self._collaboration_result(
            transport="http",
            base_url=base,
            join=join,
            development=development,
            lead_work=lead_work,
            mission=mission,
            growth=growth,
        )

    def growth_pass_over_http(
        self,
        *,
        base_url: str = "",
        timeout: float = 20.0,
        scout_leads: bool = False,
        activation_pass: bool = True,
        activation_limit: int = 3,
        send_agent_invites: bool = False,
    ) -> dict[str, Any]:
        base = _default_base_url(base_url)
        readiness = _http_json("GET", _endpoint(base, "swarm/ready"), timeout=timeout)
        attractor = _http_json(
            "GET",
            _endpoint(base, "agent-attractor?service_type=compute_auth&role=customer&limit=5"),
            timeout=timeout,
        )
        network = _http_json(
            "GET",
            _endpoint(base, "swarm/network?service_type=compute_auth&role=peer_solver&limit=5"),
            timeout=timeout,
        )
        coordination = _http_json("GET", _endpoint(base, "swarm/coordinate?type=compute_auth"), timeout=timeout)
        accumulation = _http_json(
            "POST",
            _endpoint(base, "swarm/accumulate"),
            {
                "from_contacts": True,
                "from_campaigns": True,
                "limit": 50,
                "pain_type": "compute_auth",
            },
            timeout=timeout,
        )
        activation_queue = accumulation.get("activation_queue") if isinstance(accumulation, dict) else []
        activation = (
            self.activate_agent_prospects_over_http(
                base_url=base,
                prospects=activation_queue if isinstance(activation_queue, list) else [],
                limit=activation_limit,
                send=send_agent_invites,
                timeout=timeout,
            )
            if activation_pass
            else {}
        )
        leads = (
            _http_json(
                "GET",
                _endpoint(base, "leads?query=AI%20agent%20compute%20auth%20payment%20deployment%20blocker"),
                timeout=timeout,
            )
            if scout_leads
            else {}
        )
        prospect_agents = int(accumulation.get("prospect_agents") or 0) if isinstance(accumulation, dict) else 0
        return {
            "schema": "nomad.codex_peer_growth_pass.v1",
            "ok": all(
                bool(item.get("ok", True))
                for item in [readiness, attractor, network, coordination, accumulation]
                if isinstance(item, dict)
            ),
            "readiness_status": (
                readiness.get("readiness_status")
                or readiness.get("status")
                or readiness.get("swarm_ready")
                or ""
            ),
            "prospect_agents": prospect_agents,
            "activation_queue_count": len(activation_queue) if isinstance(activation_queue, list) else 0,
            "queued_agent_invites": activation.get("queued_count", 0) if isinstance(activation, dict) else 0,
            "sent_agent_invites": activation.get("sent_count", 0) if isinstance(activation, dict) else 0,
            "next_accumulation_action": accumulation.get("next_best_action", "") if isinstance(accumulation, dict) else "",
            "best_agent_to_attract_next": (
                attractor.get("best_agent_to_attract_next")
                or (attractor.get("agent_attraction") or {}).get("best_agent_to_attract_next")
                or ""
            )
            if isinstance(attractor, dict)
            else "",
            "active_lead": (network.get("active_lead") or {}) if isinstance(network, dict) else {},
            "coordination_next": coordination.get("next_best_action", "") if isinstance(coordination, dict) else "",
            "lead_scout_count": len(leads.get("leads") or leads.get("candidates") or []) if isinstance(leads, dict) else 0,
            "raw": {
                "readiness": readiness,
                "attractor": attractor,
                "network": network,
                "coordination": coordination,
                "accumulation": accumulation,
                "activation": activation,
                "leads": leads,
            },
        }

    def activate_agent_prospects_over_http(
        self,
        *,
        base_url: str = "",
        prospects: list[dict[str, Any]] | None = None,
        limit: int = 3,
        send: bool = False,
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        base = _default_base_url(base_url)
        queued: list[dict[str, Any]] = []
        sent: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        selected_prospects = list(prospects or []) if limit <= 0 else list(prospects or [])[:limit]
        for prospect in selected_prospects:
            endpoint_url = _clean(prospect.get("endpoint_url", ""), limit=300)
            if not endpoint_url or "/a2a" not in endpoint_url.lower():
                skipped.append(
                    {
                        "agent_id": prospect.get("agent_id", ""),
                        "endpoint_url": endpoint_url,
                        "reason": "not_a_direct_a2a_endpoint",
                    }
                )
                continue
            problem = (
                "A2A agent invitation: Nomad can help with one bounded compute/auth/payment/deployment blocker. "
                "Reply with FACT_URL or ERROR for a free diagnosis, or PLAN_ACCEPTED=true plus budget_native for paid unblock."
            )
            queued_result = _http_json(
                "POST",
                _endpoint(base, "agent-contacts"),
                {
                    "endpoint_url": endpoint_url,
                    "problem": problem,
                    "service_type": prospect.get("service_type") or "compute_auth",
                    "lead": {
                        "agent_id": prospect.get("agent_id", ""),
                        "title": prospect.get("node_name", "") or prospect.get("agent_id", ""),
                        "recommended_role": prospect.get("recommended_role", ""),
                        "source": "codex_peer_activation_pass",
                    },
                },
                timeout=timeout,
            )
            queued.append(queued_result)
            contact = queued_result.get("contact") if isinstance(queued_result, dict) else {}
            contact_id = (contact or {}).get("contact_id", "")
            if send and contact_id:
                sent.append(
                    _http_json(
                        "POST",
                        _endpoint(base, "agent-contacts/send"),
                        {"contact_id": contact_id},
                        timeout=timeout,
                    )
                )
        return {
            "schema": "nomad.codex_peer_activation_pass.v1",
            "ok": True,
            "send_enabled": send,
            "limit": limit,
            "selected_count": len(selected_prospects),
            "queued_count": len(queued),
            "sent_count": len(sent),
            "skipped_count": len(skipped),
            "queued_contact_ids": [
                ((item.get("contact") or {}).get("contact_id") or "")
                for item in queued
                if isinstance(item, dict)
            ],
            "sent_contact_ids": [
                ((item.get("contact") or {}).get("contact_id") or "")
                for item in sent
                if isinstance(item, dict)
            ],
            "skipped": skipped,
            "analysis": (
                "Queued machine-readable A2A activation contacts. External sending only happens when send_enabled=true."
            ),
        }

    def collaborate_with_local_api(
        self,
        *,
        base_url: str = "",
        problem: str = "",
        work_leads: bool = True,
        lead_limit: int = 3,
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        local_base, server = _start_local_api_server(base_url)
        try:
            result = self.collaborate_over_http(
                base_url=local_base,
                problem=problem,
                work_leads=work_leads,
                lead_limit=lead_limit,
                timeout=timeout,
            )
            result["local_api_started"] = True
            return result
        finally:
            server.shutdown()
            server.server_close()

    def run_http_loop(
        self,
        *,
        base_url: str = "",
        mode: str = "local-api",
        problem: str = "",
        cycles: int = 3,
        interval_seconds: float = 30.0,
        work_leads: bool = True,
        lead_limit: int = 1,
        timeout: float = 20.0,
        growth_pass: bool = True,
        scout_leads: bool = False,
        activation_pass: bool = True,
        activation_limit: int = 3,
        send_agent_invites: bool = False,
    ) -> dict[str, Any]:
        if cycles < 0:
            cycles = 0
        local_server = None
        if mode == "local-api":
            base, local_server = _start_local_api_server(base_url)
        else:
            base = _default_base_url(base_url)

        results: list[dict[str, Any]] = []
        started_at = datetime.now(UTC).isoformat()
        cycle_index = 0
        try:
            while cycles == 0 or cycle_index < cycles:
                cycle_index += 1
                cycle_problem = problem or (
                    "HTTP peer worker cycle: help Nomad by joining, refreshing the development exchange, "
                    "working the safest lead items, and reporting blockers."
                )
                result = self.collaborate_over_http(
                    base_url=base,
                    problem=cycle_problem,
                    work_leads=work_leads,
                    lead_limit=lead_limit,
                    timeout=timeout,
                    growth_pass=growth_pass,
                    scout_leads=scout_leads,
                    activation_pass=activation_pass,
                    activation_limit=activation_limit,
                    send_agent_invites=send_agent_invites,
                )
                result["cycle"] = cycle_index
                results.append(result)
                if cycles != 0 and cycle_index >= cycles:
                    break
                if interval_seconds > 0:
                    time.sleep(interval_seconds)
        finally:
            if local_server is not None:
                local_server.shutdown()
                local_server.server_close()

        worked_total = sum(int((item.get("lead_workbench") or {}).get("worked_count") or 0) for item in results)
        last = results[-1] if results else {}
        mission = last.get("mission") or {}
        lead = last.get("lead_workbench") or {}
        growth = last.get("growth") or {}
        return {
            "mode": "codex_peer_worker",
            "schema": "nomad.codex_peer_worker.v1",
            "ok": all(bool(item.get("ok")) for item in results) if results else False,
            "agent_id": self.agent_id,
            "http_only": True,
            "transport": "http",
            "base_url": base,
            "started_at": started_at,
            "finished_at": datetime.now(UTC).isoformat(),
            "cycles_requested": cycles,
            "cycles_completed": len(results),
            "worked_leads": worked_total,
            "growth_pass_enabled": growth_pass,
            "scout_leads_enabled": scout_leads,
            "latest_prospect_agents": growth.get("prospect_agents", 0),
            "latest_activation_queue_count": growth.get("activation_queue_count", 0),
            "latest_queued_agent_invites": growth.get("queued_agent_invites", 0),
            "latest_sent_agent_invites": growth.get("sent_agent_invites", 0),
            "latest_growth_action": growth.get("next_accumulation_action", ""),
            "latest_agent_to_attract": growth.get("best_agent_to_attract_next", ""),
            "latest_queue_count": lead.get("queue_count", 0),
            "latest_top_action": lead.get("top_next_action", ""),
            "latest_top_blocker": mission.get("top_blocker", ""),
            "latest_next_action": mission.get("next_action", ""),
            "results": results,
            "analysis": (
                "CodexPeerAgent ran as a bounded HTTP-only CLI worker. "
                "Use cycles=0 only when an operator intentionally wants a long-running process."
            ),
        }

    def _collaboration_result(
        self,
        *,
        transport: str,
        base_url: str,
        join: dict[str, Any],
        development: dict[str, Any],
        lead_work: dict[str, Any],
        mission: dict[str, Any],
        growth: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        top_blocker = mission.get("top_blocker") if isinstance(mission, dict) else {}
        next_action = mission.get("next_action") if isinstance(mission, dict) else {}
        return {
            "mode": "codex_peer_agent",
            "schema": "nomad.codex_peer_agent.v1",
            "ok": bool(join.get("ok", True) and development.get("ok", True)),
            "agent_id": self.agent_id,
            "http_only": True,
            "transport": transport,
            "base_url": base_url,
            "join_receipt": {
                "receipt_id": join.get("receipt_id", ""),
                "accepted": bool(join.get("accepted", join.get("ok", False))),
                "connected_agents": join.get("connected_agents", 0),
                "arrival_plan": join.get("arrival_plan") or {},
            },
            "development_response": {
                "exchange_id": development.get("exchange_id", ""),
                "pain_type": development.get("pain_type", ""),
                "solution_title": (development.get("solution") or {}).get("title", ""),
                "plan": development.get("agent_development_plan") or {},
            },
            "lead_workbench": {
                "queue_count": lead_work.get("queue_count", 0),
                "worked_count": lead_work.get("worked_count", 0),
                "top_next_action": ((lead_work.get("self_help") or {}).get("top_next_action") or ""),
            },
            "growth": growth or {},
            "mission": {
                "top_blocker": (top_blocker or {}).get("summary", ""),
                "next_action": (next_action or {}).get("summary", ""),
            },
            "raw": {
                "join": join,
                "development": development,
                "lead_workbench": lead_work,
                "mission": mission,
                "growth": growth or {},
            },
            "analysis": (
                "CodexPeerAgent joined Nomad's swarm and exchanged a bounded development request. "
                "This is a real HTTP API collaboration loop, not independent consciousness or unlimited compute."
            ),
        }


def run_cli(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Run CodexPeerAgent against Nomad.")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--problem", default="")
    parser.add_argument("--mode", choices=["http", "local-api"], default="local-api")
    parser.add_argument("--loop", action="store_true", help="Run repeated HTTP-only worker cycles.")
    parser.add_argument("--cycles", type=int, default=3, help="Worker cycles; 0 means run until stopped.")
    parser.add_argument("--interval", type=float, default=30.0, help="Seconds between worker cycles.")
    parser.add_argument("--growth-pass", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--scout-leads", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--activation-pass", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--activation-limit", type=int, default=3, help="A2A prospects to activate per cycle; 0 means the full current activation queue.")
    parser.add_argument("--send-agent-invites", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--work-leads", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--lead-limit", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    peer = CodexPeerAgent()
    if args.loop:
        result = peer.run_http_loop(
            base_url=args.base_url,
            mode=args.mode,
            problem=args.problem,
            cycles=args.cycles,
            interval_seconds=args.interval,
            work_leads=args.work_leads,
            lead_limit=args.lead_limit,
            timeout=args.timeout,
            growth_pass=args.growth_pass,
            scout_leads=args.scout_leads,
            activation_pass=args.activation_pass,
            activation_limit=args.activation_limit,
            send_agent_invites=args.send_agent_invites,
        )
    elif args.mode == "http":
        result = peer.collaborate_over_http(
            base_url=args.base_url,
            problem=args.problem,
            work_leads=args.work_leads,
            lead_limit=args.lead_limit,
            timeout=args.timeout,
            growth_pass=args.growth_pass,
            scout_leads=args.scout_leads,
            activation_pass=args.activation_pass,
            activation_limit=args.activation_limit,
            send_agent_invites=args.send_agent_invites,
        )
    else:
        result = peer.collaborate_with_local_api(
            base_url=args.base_url,
            problem=args.problem,
            work_leads=args.work_leads,
            lead_limit=args.lead_limit,
            timeout=args.timeout,
        )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
    else:
        receipt = result.get("join_receipt") or {}
        lead = result.get("lead_workbench") or {}
        mission = result.get("mission") or {}
        if result.get("mode") == "codex_peer_worker":
            print("CodexPeerWorker")
            print(f"Transport: {result.get('transport')} http_only={result.get('http_only')}")
            print(f"Cycles: {result.get('cycles_completed')} / requested {result.get('cycles_requested')}")
            print(f"Worked leads: {result.get('worked_leads', 0)} / queue {result.get('latest_queue_count', 0)}")
            print(f"Prospect agents: {result.get('latest_prospect_agents', 0)}")
            print(f"Queued agent invites: {result.get('latest_queued_agent_invites', 0)}")
            print(f"Top blocker: {result.get('latest_top_blocker', '')}")
        else:
            print("CodexPeerAgent")
            print(f"Transport: {result.get('transport')}")
            print(f"Receipt: {receipt.get('receipt_id') or 'none'} accepted={receipt.get('accepted')}")
            print(f"Worked leads: {lead.get('worked_count', 0)} / queue {lead.get('queue_count', 0)}")
            print(f"Top blocker: {mission.get('top_blocker', '')}")
        print(result.get("analysis", ""))
    return result


if __name__ == "__main__":
    run_cli()
