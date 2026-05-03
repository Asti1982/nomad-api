import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from nomad_guardrails import guardrail_status
from nomad_machine_error import machine_error_response, merge_machine_error
from nomad_openapi import build_openapi_document
from nomad_collaboration import collaboration_status
from nomad_market_patterns import PatternStatus
from nomad_monitor import NomadSystemMonitor
from nomad_operator_desk import (
    operator_autonomy_step,
    operator_daily_bundle,
    operator_growth_start,
    operator_iteration_report,
    operator_metrics_snapshot,
    operator_sprint,
    operator_verify_bundle,
    unlock_desk_snapshot,
)
from nomad_public_url import preferred_public_base_url
from nomad_roaas_exchange import RuntimePatternExchange
from nomad_swarm_registry import SwarmJoinRegistry, build_peer_join_value_surface
from nomad_unhuman_hub import unhuman_hub_snapshot
from nomad_wire_contract import maybe_merge_http_wire_diag
from nomad_agent_growth_pipeline import agent_growth_pipeline
from nomad_agent_invariants import build_agent_invariants_document
from nomad_agent_market_offers import build_inter_agent_witness_offer_well_known
from nomad_agent_native_index import agent_native_index
from nomad_peer_acquisition import build_peer_acquisition_well_known
from workflow import NomadAgent


HOST = os.getenv("NOMAD_API_HOST", "127.0.0.1")
PORT = int(os.getenv("NOMAD_API_PORT") or os.getenv("PORT") or "8787")
ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
NOMAD_PROCESS_START = time.time()


class NomadApiHandler(BaseHTTPRequestHandler):
    agent = NomadAgent()
    monitor = NomadSystemMonitor(agent=agent)
    roaas = RuntimePatternExchange(agent=agent)
    swarm_registry = agent.swarm_registry
    agent_development = agent.agent_development
    outbound_tracker = agent.outbound_tracker

    @staticmethod
    def _public_url_path_prefix() -> str:
        explicit = (os.getenv("NOMAD_HTTP_PATH_PREFIX") or "").strip().rstrip("/")
        if explicit:
            return explicit if explicit.startswith("/") else f"/{explicit}"
        configured = (os.getenv("NOMAD_PUBLIC_API_URL") or "").strip()
        if not configured.startswith(("http://", "https://")):
            return ""
        pub_path = urlparse(configured).path.rstrip("/")
        if not pub_path or pub_path == "/":
            return ""
        return pub_path

    @classmethod
    def _normalize_public_path(cls, raw_path: str) -> str:
        """Map incoming /nomad/... to /... when public URL is https://host/nomad (reverse-proxy path)."""
        path = raw_path or "/"
        prefix = cls._public_url_path_prefix()
        if not prefix:
            return path
        if path == prefix or path == prefix + "/":
            return "/"
        if path.startswith(prefix + "/"):
            rest = path[len(prefix) :]
            return rest if rest.startswith("/") else f"/{rest}"
        return path

    def do_GET(self) -> None:  # noqa: N802
        parsed_full = urlparse(self.path)
        query = parse_qs(parsed_full.query)
        parsed = parsed_full._replace(path=self._normalize_public_path(parsed_full.path or "/"))

        if parsed.path in {"/", "/index.html", "/nomad.html"}:
            self._html_file_response(PUBLIC_DIR / "nomad.html")
            return

        if parsed.path == "/health":
            base = self._base_url()
            links: dict[str, str] = {}
            if base:
                b = base.rstrip("/")
                links = {
                    "nomad_html": f"{b}/nomad.html",
                    "agent_card": f"{b}/.well-known/agent-card.json",
                    "agent_native_priorities": f"{b}/.well-known/nomad-agent-native-priorities.json",
                    "agent_native_index": f"{b}/.well-known/nomad-agent.json",
                    "inter_agent_witness_offer": f"{b}/.well-known/nomad-inter-agent-witness-offer.json",
                    "peer_acquisition_contract": f"{b}/.well-known/nomad-peer-acquisition.json",
                    "openapi": f"{b}/openapi.json",
                    "swarm": f"{b}/swarm",
                    "tasks": f"{b}/tasks",
                    "service_catalog": f"{b}/service",
                    "growth_start": f"{b}/growth-start",
                    "autonomy_step": f"{b}/autonomy-step",
                    "operator_desk": f"{b}/operator-desk",
                    "operator_sprint": f"{b}/operator-sprint",
                    "agent_reputation": f"{b}/reputation",
                    "unhuman_hub": f"{b}/unhuman-hub",
                    "agent_growth": f"{b}/agent-growth",
                }
            else:
                links = {"openapi": "/openapi.json"}
            uptime = max(0.0, time.time() - NOMAD_PROCESS_START)
            body: dict = {
                "ok": True,
                "service": "nomad-api",
                "schema": "nomad.health.v1",
                "version": os.getenv("NOMAD_VERSION", "0.1.0").strip() or "0.1.0",
                "uptime_seconds": round(uptime, 3),
                "checks": {"api_process": "listening"},
                "public_home": base,
                "for_agents": "Use agent_card, openapi, and swarm for machine discovery; tasks for paid bounded work.",
                "links": links,
            }
            if self._truthy((query.get("deep") or ["false"])[0], default=False):
                body["deep"] = True
                body["deep_note"] = (
                    "deep=true is reserved for optional heavier checks; default /health stays fast and local-only."
                )
            self._json_response(body)
            return

        if parsed.path in {"/openapi.json", "/.well-known/openapi.json", "/openapi"}:
            self._json_response(build_openapi_document(base_url=self._base_url()))
            return

        if parsed.path in {"/status", "/top"}:
            self._json_response(self.monitor.snapshot())
            return

        if parsed.path in {"/mission", "/mission-control", "/next-step", "/growth"}:
            self._json_response(
                self.agent.mission_control.snapshot(
                    base_url=self._base_url(),
                    persist=self._truthy((query.get("persist") or ["true"])[0], default=True),
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                )
            )
            return

        if parsed.path in {"/operator-desk", "/operator/desk"}:
            self._json_response(
                unlock_desk_snapshot(
                    agent=self.agent,
                    persist_mission=self._truthy((query.get("persist") or ["false"])[0]),
                )
            )
            return

        if parsed.path in {"/operator-sprint", "/operator/sprint"}:
            base_raw = (query.get("base_url") or query.get("base") or [""])[0]
            root = str(base_raw or self._base_url() or "").strip()
            self._json_response(
                operator_sprint(
                    agent=self.agent,
                    base_url=root,
                    persist_mission=self._truthy((query.get("persist") or ["false"])[0]),
                )
            )
            return

        if parsed.path in {"/operator-verify", "/operator/verify"}:
            base = (query.get("base_url") or query.get("base") or [""])[0]
            root = str(base or self._base_url() or "").strip()
            self._json_response(operator_verify_bundle(base_url=root))
            return

        if parsed.path in {"/operator-metrics", "/operator/metrics"}:
            self._json_response(operator_metrics_snapshot())
            return

        if parsed.path in {"/operator-daily", "/operator/daily"}:
            base_raw = (query.get("base_url") or query.get("base") or [""])[0]
            root = str(base_raw or self._base_url() or "").strip()
            self._json_response(
                operator_daily_bundle(
                    agent=self.agent,
                    base_url=root,
                    persist_mission=self._truthy((query.get("persist") or ["false"])[0]),
                )
            )
            return

        if parsed.path in {"/operator-report", "/operator/report"}:
            self._json_response(
                operator_iteration_report(
                    tail_lines=int((query.get("tail") or ["400"])[0] or 400),
                )
            )
            return

        if parsed.path in {"/reputation", "/agent-reputation"}:
            self._json_response(self.agent.service_desk.reputation_snapshot())
            return

        if parsed.path in {"/unhuman-hub", "/hub/unhuman"}:
            base_raw = (query.get("base_url") or query.get("base") or [""])[0]
            root = str(base_raw or self._base_url() or "").strip()
            self._json_response(
                unhuman_hub_snapshot(
                    agent=self.agent,
                    base_url=root,
                    persist_mission=self._truthy((query.get("persist") or ["false"])[0]),
                )
            )
            return

        if parsed.path in {"/growth-start", "/operator/growth-start"}:
            q = (query.get("query") or query.get("q") or [""])[0]
            skip = self._truthy((query.get("skip_leads") or ["false"])[0])
            skip_verify = self._truthy((query.get("skip_verify") or ["false"])[0])
            base_raw = (query.get("base_url") or query.get("base") or [""])[0]
            root = str(base_raw or self._base_url() or "").strip()
            self._json_response(
                operator_growth_start(
                    agent=self.agent,
                    base_url=root,
                    persist_mission=self._truthy((query.get("persist") or ["false"])[0]),
                    lead_query=str(q or ""),
                    skip_leads=skip,
                    skip_verify=skip_verify,
                )
            )
            return

        if parsed.path in {"/autonomy-step", "/operator/autonomy-step"}:
            q = (query.get("query") or query.get("q") or [""])[0]
            skip_growth = self._truthy((query.get("skip_growth") or ["false"])[0])
            growth_skip_verify = self._truthy((query.get("growth_skip_verify") or ["false"])[0])
            growth_include_leads = self._truthy((query.get("growth_include_leads") or ["false"])[0])
            swarm_feed_raw = (query.get("swarm_feed") or ["true"])[0]
            swarm_feed_disabled = str(swarm_feed_raw).strip().lower() in {"0", "false", "no", "off"}
            base_raw = (query.get("base_url") or query.get("base") or [""])[0]
            root = str(base_raw or self._base_url() or "").strip()
            cycle_focus = (query.get("cycle_focus") or ["leads_growth"])[0]
            cycle_objective = (query.get("cycle_objective") or [""])[0]
            self._json_response(
                operator_autonomy_step(
                    agent=self.agent,
                    base_url=root,
                    persist_mission=self._truthy((query.get("persist") or ["false"])[0]),
                    lead_query=str(q or ""),
                    skip_growth=skip_growth,
                    growth_skip_verify=growth_skip_verify,
                    growth_skip_leads=not growth_include_leads,
                    swarm_feed=False if swarm_feed_disabled else None,
                    cycle_focus=str(cycle_focus or "leads_growth"),
                    cycle_objective=str(cycle_objective or ""),
                )
            )
            return

        if parsed.path == "/roaas":
            self._json_response(
                self.roaas.status(
                    task_type=(query.get("task_type") or query.get("task") or [""])[0]
                )
            )
            return

        if parsed.path in {"/roaas/export", "/artifacts/runtime-patterns", "/.well-known/nomad-runtime-patterns.json"}:
            headers = {"Cache-Control": "public, max-age=60"} if parsed.path != "/roaas/export" else {}
            self._json_response(
                self.roaas.export_bundle(
                    task_type=(query.get("task_type") or query.get("task") or [""])[0],
                    include_executions=self._truthy(
                        (query.get("include_executions") or ["true"])[0],
                        default=True,
                    ),
                    min_status=self._parse_pattern_status(
                        (query.get("min_status") or ["candidate"])[0]
                    ),
                ),
                headers=headers,
            )
            return

        if parsed.path in {"/agent", "/service"}:
            self._json_response(self.agent.service_desk.service_catalog())
            return

        if parsed.path == "/service/e2e":
            self._json_response(
                self.agent.service_desk.end_to_end_runway(
                    task_id=(query.get("task_id") or [""])[0],
                    problem=(query.get("problem") or [""])[0],
                    service_type=(query.get("service_type") or query.get("type") or [""])[0],
                    budget_native=self._optional_float((query.get("budget_native") or query.get("budget") or [""])[0]),
                    requester_agent=(query.get("requester_agent") or query.get("agent") or [""])[0],
                    requester_wallet=(query.get("requester_wallet") or query.get("wallet") or [""])[0],
                    callback_url=(query.get("callback_url") or query.get("callback") or [""])[0],
                    create_task=self._truthy((query.get("create") or ["false"])[0]),
                    approval=(query.get("approval") or ["draft_only"])[0],
                )
            )
            return

        if parsed.path == "/outbound":
            self._json_response(
                self.outbound_tracker.summary(
                    limit=int((query.get("limit") or ["10"])[0] or 10),
                )
            )
            return

        if parsed.path in {"/lead-workbench", "/lead-work", "/jobs"}:
            self._json_response(
                self.agent.lead_workbench.status(
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                    work=self._truthy((query.get("work") or ["false"])[0]),
                )
            )
            return

        if parsed.path == "/swarm":
            self._json_response(
                self.swarm_registry.public_manifest(
                    base_url=self._base_url(),
                )
            )
            return

        if parsed.path == "/swarm/join":
            self._json_response(
                self.swarm_registry.join_contract(
                    base_url=self._base_url(),
                )
            )
            return

        if parsed.path == "/swarm/nodes":
            self._json_response(self.swarm_registry.summary())
            return

        if parsed.path in {"/swarm/ready", "/swarm/readiness"}:
            self._json_response(
                self.swarm_registry.first_agent_readiness(
                    base_url=self._base_url(),
                )
            )
            return

        if parsed.path == "/swarm/coordinate":
            self._json_response(
                self.swarm_registry.coordination_board(
                    base_url=self._base_url(),
                    focus_pain_type=(query.get("pain_type") or query.get("type") or [""])[0],
                )
            )
            return

        if parsed.path == "/swarm/network":
            self._json_response(
                self.agent.agent_attractor.active_lead_network(
                    service_type=(query.get("service_type") or query.get("type") or [""])[0],
                    role_hint=(query.get("role") or [""])[0],
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                )
            )
            return

        if parsed.path == "/swarm/accumulate":
            self._json_response(
                self.swarm_registry.accumulation_status(
                    base_url=self._base_url(),
                )
            )
            return

        if parsed.path in {"/swarm/develop", "/agent-development"}:
            self._json_response(
                self.agent_development.status(
                    base_url=self._base_url(),
                )
            )
            return

        if parsed.path in {"/agent-attractor", "/.well-known/agent-attractor.json"}:
            self._json_response(
                self.agent.agent_attractor.manifest(
                    service_type=(query.get("service_type") or query.get("type") or [""])[0],
                    role_hint=(query.get("role") or [""])[0],
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                )
            )
            return

        if parsed.path in {"/.well-known/agent-card.json", "/.well-known/agent.json"}:
            self._json_response(self.agent.direct_agent.agent_card())
            return

        if parsed.path in {"/.well-known/nomad-agent-invariants.json", "/agent-invariants"}:
            self._json_response(
                build_agent_invariants_document(public_base_url=self._base_url() or ""),
            )
            return

        if parsed.path in {
            "/.well-known/nomad-inter-agent-witness-offer.json",
            "/inter-agent-witness-offer",
        }:
            self._json_response(
                build_inter_agent_witness_offer_well_known(public_base_url=self._base_url() or ""),
            )
            return

        if parsed.path in {
            "/.well-known/nomad-peer-acquisition.json",
            "/peer-acquisition",
        }:
            self._json_response(
                build_peer_acquisition_well_known(public_base_url=self._base_url() or ""),
            )
            return

        if parsed.path in {
            "/.well-known/nomad-agent.json",
            "/agent-native-index",
            "/agent-native",
        }:
            base_raw = (query.get("base_url") or query.get("base") or [""])[0]
            root = str(base_raw or self._base_url() or "").strip()
            self._json_response(agent_native_index(base_url=root))
            return

        if parsed.path in {
            "/.well-known/nomad-agent-native-priorities.json",
            "/agent-native-priorities",
        }:
            base = self._base_url().rstrip("/")
            surface = build_peer_join_value_surface(base_url=base)
            native = surface.get("agent_native_priorities_humans_underrate") or {}
            psychic = surface.get("human_psychic_avoidance_lanes") or {}
            self._json_response(
                {
                    "ok": True,
                    "schema": "nomad.well_known_agent_native_slice.v1",
                    "agent_native_priorities_humans_underrate": native,
                    "human_psychic_avoidance_lanes": psychic,
                    "agent_native_index_url": f"{base}/.well-known/nomad-agent.json" if base else "/.well-known/nomad-agent.json",
                    "peer_join_contract_url": f"{base}/swarm/join" if base else "/swarm/join",
                    "swarm_manifest_url": f"{base}/swarm" if base else "/swarm",
                }
            )
            return

        if parsed.path == "/direct/sessions":
            session_id = (query.get("session_id") or [""])[0]
            if session_id:
                self._json_response(self.agent.direct_agent.session_status(session_id))
                return
            self._json_response(
                machine_error_response(
                    error="session_id_required",
                    message="Use GET /direct/sessions?session_id=<id>.",
                    hints=["GET /openapi.json documents query parameters for GET routes."],
                ),
                status=400,
            )
            return

        if parsed.path == "/tasks":
            task_id = (query.get("task_id") or [""])[0]
            if task_id:
                self._json_response(self.agent.service_desk.get_task(task_id))
                return
            self._json_response(
                machine_error_response(
                    error="task_id_required",
                    message="Use GET /tasks?task_id=<id> or POST /tasks to create one.",
                    hints=["GET /openapi.json for the tasks GET contract."],
                ),
                status=400,
            )
            return

        if parsed.path == "/agent-contacts":
            contact_id = (query.get("contact_id") or [""])[0]
            if contact_id:
                self._json_response(self.agent.agent_contacts.get_contact(contact_id))
                return
            self._json_response(
                machine_error_response(
                    error="contact_id_required",
                    message="Use GET /agent-contacts?contact_id=<id> or POST /agent-contacts.",
                    hints=["GET /openapi.json lists agent-contacts when extended in a future revision."],
                ),
                status=400,
            )
            return

        if parsed.path == "/agent-campaigns":
            campaign_id = (query.get("campaign_id") or [""])[0]
            if campaign_id:
                self._json_response(self.agent.agent_campaigns.get_campaign(campaign_id))
                return
            self._json_response(
                machine_error_response(
                    error="campaign_id_required",
                    message="Use GET /agent-campaigns?campaign_id=<id> or POST /agent-campaigns.",
                    hints=["GET /openapi.json for stable GET query patterns where documented."],
                ),
                status=400,
            )
            return

        if parsed.path == "/best":
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/best {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/self":
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/self {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/compute":
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/compute {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/modal":
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/modal {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/render":
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/render {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/addons":
            self._json_response(self.agent.addons.status())
            return

        if parsed.path == "/quantum":
            objective = (query.get("objective") or [""])[0]
            self._json_response(
                self.agent.addons.run_quantum_self_improvement(
                    objective=objective,
                    context={"source": "http_get"},
                )
            )
            return

        if parsed.path == "/cycle":
            profile = (query.get("profile") or ["ai_first"])[0]
            objective = (query.get("objective") or [""])[0]
            prompt = f"/cycle {objective} for {profile}".strip()
            result = self.agent.run(prompt)
            self._json_response(result)
            return

        if parsed.path == "/unlock":
            category = (query.get("category") or ["compute"])[0]
            profile = (query.get("profile") or ["ai_first"])[0]
            result = self.agent.run(f"/unlock {category} for {profile}".strip())
            self._json_response(result)
            return

        if parsed.path == "/scout":
            category = (query.get("category") or [""])[0]
            profile = (query.get("profile") or ["ai_first"])[0]
            prompt = f"/scout {category} for {profile}".strip()
            result = self.agent.run(prompt)
            self._json_response(result)
            return

        if parsed.path in {"/lead-calibrate", "/leads-calibrate"}:
            focus = (query.get("focus") or [""])[0]
            limit_raw = (query.get("limit") or ["12"])[0]
            pool_raw = (query.get("candidate_multiplier") or query.get("pool") or ["5"])[0]
            lead_query = (query.get("query") or [""])[0]
            try:
                lim = int(str(limit_raw).strip() or "12")
            except ValueError:
                lim = 12
            try:
                mult = int(str(pool_raw).strip() or "5")
            except ValueError:
                mult = 5
            result = self.agent.lead_discovery.calibrate_focus_scout(
                focus=str(focus or "").strip(),
                query=str(lead_query or "").strip(),
                limit=max(3, min(lim, 25)),
                candidate_multiplier=max(3, min(mult, 10)),
            )
            self._json_response(result)
            return

        if parsed.path == "/leads":
            lead_query = (query.get("query") or [""])[0]
            focus = (query.get("focus") or [""])[0]
            limit_raw = (query.get("limit") or [""])[0]
            if focus.strip() or str(limit_raw).strip():
                try:
                    lim = int(str(limit_raw).strip() or "5")
                except ValueError:
                    lim = 5
                result = self.agent.lead_discovery.scout_public_leads(
                    query=lead_query,
                    limit=max(1, min(lim, 25)),
                    focus=focus.strip(),
                )
            else:
                result = self.agent.lead_discovery.scout_public_leads(query=lead_query)
            self._json_response(result)
            return

        if parsed.path == "/lead-conversions":
            lead_query = (query.get("query") or [""])[0]
            if lead_query:
                result = self.agent.lead_conversion.run(
                    query=lead_query,
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                    send=str((query.get("send") or ["false"])[0]).lower() in {"1", "true", "yes", "on"},
                    budget_hint_native=self._optional_float((query.get("budget_native") or query.get("budget") or [""])[0]),
                )
            else:
                statuses = [
                    item.strip()
                    for raw in (query.get("status") or [])
                    for item in raw.split(",")
                    if item.strip()
                ]
                result = self.agent.lead_conversion.list_conversions(
                    statuses=statuses,
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            self._json_response(result)
            return

        if parsed.path == "/products":
            product_query = (query.get("query") or [""])[0]
            if product_query:
                result = self.agent.product_factory.run(
                    query=product_query,
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                )
            else:
                statuses = [
                    item.strip()
                    for raw in (query.get("status") or [])
                    for item in raw.split(",")
                    if item.strip()
                ]
                result = self.agent.product_factory.list_products(
                    statuses=statuses,
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            self._json_response(result)
            return

        if parsed.path == "/agent-pains":
            problem = (query.get("problem") or [""])[0]
            service_type = (query.get("type") or query.get("service_type") or [""])[0]
            if problem:
                result = self.agent.agent_pain_solver.solve(
                    problem=problem,
                    service_type=service_type,
                    source="http_get",
                )
            else:
                result = self.agent.run("/agent-pains")
            self._json_response(result)
            return

        if parsed.path in {"/doctor", "/reliability-doctor"}:
            problem = (query.get("problem") or ["Agent needs reliability diagnosis."])[0]
            service_type = (query.get("type") or query.get("service_type") or [""])[0]
            result = self.agent.agent_reliability_doctor.diagnose(
                problem=problem,
                service_type=service_type,
                source="http_get",
            )
            self._json_response(result)
            return

        if parsed.path == "/guardrails":
            result = guardrail_status(
                action=(query.get("action") or ["manual.check"])[0],
                approval=(query.get("approval") or [""])[0],
                args={
                    "text": (query.get("text") or [""])[0],
                    "url": (query.get("url") or [""])[0],
                },
            )
            self._json_response(result, status=200 if result.get("ok") else 409)
            return

        if parsed.path == "/collaboration":
            self._json_response(collaboration_status())
            return

        if parsed.path == "/roaas/import":
            self._json_response(
                {
                    "ok": False,
                    "error": "post_required",
                    "message": "Use POST /roaas/import with a runtime pattern bundle.",
                },
                status=405,
            )
            return

        if parsed.path == "/mutual-aid":
            self._json_response(self.agent.mutual_aid.status())
            return

        if parsed.path == "/mutual-aid/ledger":
            self._json_response(
                self.agent.mutual_aid.list_truth_ledger(
                    pain_type=(query.get("pain_type") or query.get("type") or [""])[0],
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            )
            return

        if parsed.path == "/mutual-aid/inbox":
            statuses = [
                item.strip()
                for raw in (query.get("status") or [])
                for item in raw.split(",")
                if item.strip()
            ]
            self._json_response(
                self.agent.mutual_aid.list_swarm_inbox(
                    statuses=statuses,
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            )
            return

        if parsed.path == "/mutual-aid/signals":
            self._json_response(
                self.agent.mutual_aid.list_swarm_development_signals(
                    pain_type=(query.get("pain_type") or query.get("type") or [""])[0],
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            )
            return

        if parsed.path == "/agent-engagements":
            roles = [
                item.strip()
                for raw in (query.get("role") or query.get("roles") or [])
                for item in raw.split(",")
                if item.strip()
            ]
            self._json_response(
                self.agent.agent_engagements.list_engagements(
                    roles=roles,
                    pain_type=(query.get("pain_type") or query.get("type") or [""])[0],
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            )
            return

        if parsed.path == "/agent-engagements/summary":
            self._json_response(
                self.agent.agent_engagements.summary(
                    pain_type=(query.get("pain_type") or query.get("type") or [""])[0],
                    limit=int((query.get("limit") or ["5"])[0] or 5),
                )
            )
            return

        if parsed.path == "/mutual-aid/patterns":
            self._json_response(
                self.agent.mutual_aid.list_high_value_patterns(
                    pain_type=(query.get("pain_type") or query.get("type") or [""])[0],
                    limit=int((query.get("limit") or ["10"])[0] or 10),
                    min_repeat_count=int((query.get("min_repeat_count") or ["2"])[0] or 2),
                )
            )
            return

        if parsed.path == "/mutual-aid/packs":
            self._json_response(
                self.agent.mutual_aid.list_paid_packs(
                    pain_type=(query.get("pain_type") or query.get("type") or [""])[0],
                    limit=int((query.get("limit") or ["25"])[0] or 25),
                )
            )
            return

        self._json_response(
            merge_machine_error(
                {
                    "ok": False,
                    "error": "not_found",
                    "available_paths": [
                    "/",
                    "/nomad.html",
                    "/health",
                    "/openapi.json",
                    "/.well-known/openapi.json",
                    "/mission",
                    "/mission-control",
                    "/next-step",
                    "/growth",
                    "/operator-desk",
                    "/operator/desk",
                    "/operator-sprint",
                    "/operator/sprint",
                    "/operator-verify",
                    "/operator/verify",
                    "/operator-metrics",
                    "/operator/metrics",
                    "/operator-daily",
                    "/operator/daily",
                    "/operator-report",
                    "/operator/report",
                    "/reputation",
                    "/agent-reputation",
                    "/unhuman-hub",
                    "/hub/unhuman",
                    "/agent-growth",
                    "/growth-pipeline",
                    "/growth-start",
                    "/operator/growth-start",
                    "/agent",
                    "/service",
                    "/service/e2e",
                    "/outbound",
                    "/lead-workbench",
                    "/lead-work",
                    "/jobs",
                    "/agent-attractor",
                    "/swarm",
                    "/swarm/join",
                    "/swarm/nodes",
                    "/swarm/ready",
                    "/swarm/network",
                    "/swarm/coordinate",
                    "/swarm/accumulate",
                    "/swarm/develop",
                    "/agent-development",
                    "/.well-known/agent-attractor.json",
                    "/.well-known/agent-card.json",
                    "/.well-known/nomad-agent-invariants.json",
                    "/agent-invariants",
                    "/.well-known/nomad-inter-agent-witness-offer.json",
                    "/inter-agent-witness-offer",
                    "/.well-known/nomad-peer-acquisition.json",
                    "/peer-acquisition",
                    "/.well-known/nomad-agent-native-priorities.json",
                    "/.well-known/nomad-agent.json",
                    "/agent-native-index",
                    "/agent-native",
                    "/a2a/message",
                    "/direct/sessions",
                    "/x402/paid-help",
                    "/tasks",
                    "/agent-contacts",
                    "/agent-campaigns",
                    "/agent-engagements",
                    "/agent-engagements/summary",
                    "/best",
                    "/self",
                    "/compute",
                    "/addons",
                    "/quantum",
                    "/cycle",
                    "/unlock",
                    "/scout",
                    "/leads",
                    "/lead-calibrate",
                    "/lead-conversions",
                    "/products",
                    "/agent-pains",
                    "/reliability-doctor",
                    "/guardrails",
                    "/collaboration",
                    "/roaas",
                    "/roaas/export",
                    "/roaas/import",
                    "/artifacts/runtime-patterns",
                    "/.well-known/nomad-runtime-patterns.json",
                    "/mutual-aid",
                    "/mutual-aid/ledger",
                    "/mutual-aid/inbox",
                    "/mutual-aid/signals",
                    "/mutual-aid/patterns",
                    "/mutual-aid/packs",
                ],
            },
                error="not_found",
                message="No GET handler matched this path.",
                hints=["GET /openapi.json for the primary documented HTTP surface.", "GET /health for liveness."],
            ),
            status=404,
        )

    def do_POST(self) -> None:  # noqa: N802
        parsed_full = urlparse(self.path)
        parsed = parsed_full._replace(path=self._normalize_public_path(parsed_full.path or "/"))
        payload = self._read_json_body()
        if payload is None:
            self._json_response(
                machine_error_response(
                    error="invalid_json",
                    message="POST bodies must be JSON objects.",
                    hints=[
                        "Use Content-Type: application/json and a single UTF-8 JSON object.",
                        "For /swarm/develop send agent_id and problem; for /swarm/join send agent_id, capabilities, request.",
                        "GET /openapi.json for route and body contracts.",
                    ],
                ),
                status=400,
            )
            return

        if parsed.path in {"/agent-growth", "/growth-pipeline"}:
            result = agent_growth_pipeline(
                agent=self.agent,
                query=str(payload.get("query") or payload.get("q") or ""),
                limit=int(payload.get("limit") or 5),
                base_url=str(payload.get("base_url") or payload.get("base") or "").strip(),
                run_product_factory=not bool(payload.get("no_products") or payload.get("skip_products")),
                send_outreach=bool(payload.get("send") or payload.get("send_outreach")),
                swarm_feed=None
                if str(payload.get("swarm_feed", "")).strip().lower() in {"0", "false", "no", "off"}
                else (True if str(payload.get("swarm_feed", "")).strip().lower() in {"1", "true", "yes", "on"} else None),
            )
            self._json_response(result, status=200 if result.get("ok") else 500)
            return

        if parsed.path == "/tasks":
            result = self.agent.service_desk.create_task(
                problem=payload.get("problem", ""),
                requester_agent=payload.get("requester_agent", ""),
                requester_wallet=payload.get("requester_wallet", ""),
                service_type=payload.get("service_type", "custom"),
                budget_native=payload.get("budget_native"),
                callback_url=payload.get("callback_url", ""),
                metadata=payload.get("metadata") or {},
            )
            self._json_response(result, status=201 if result.get("ok") else 400)
            return

        if parsed.path == "/service/e2e":
            result = self.agent.service_desk.end_to_end_runway(
                task_id=payload.get("task_id", ""),
                problem=payload.get("problem", ""),
                service_type=payload.get("service_type") or payload.get("type") or "",
                budget_native=payload.get("budget_native", payload.get("budget")),
                requester_agent=payload.get("requester_agent") or payload.get("agent") or "",
                requester_wallet=payload.get("requester_wallet") or payload.get("wallet") or "",
                callback_url=payload.get("callback_url") or payload.get("callback") or "",
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
                create_task=bool(payload.get("create", False)),
                approval=payload.get("approval", "draft_only"),
            )
            status = 201 if result.get("created") else 200 if result.get("ok", True) else 400
            self._json_response(result, status=status)
            return

        if parsed.path in {"/a2a/message", "/direct/message"}:
            result = self.agent.direct_agent.handle_direct_message(payload)
            jsonrpc = self._jsonrpc_envelope(payload, result)
            self._json_response(
                jsonrpc if self._is_jsonrpc_request(payload) else result,
                status=200 if result.get("ok") else 400,
            )
            return

        if parsed.path == "/a2a/discover":
            result = self.agent.direct_agent.discover_agent_card(
                base_url=payload.get("base_url", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/quantum":
            result = self.agent.addons.run_quantum_self_improvement(
                objective=payload.get("objective", ""),
                context=payload.get("context") or {"source": "http_post"},
            )
            self._json_response(result, status=200 if result.get("ok") else 400)
            return

        if parsed.path == "/x402/paid-help":
            payment_signature = (
                self.headers.get("PAYMENT-SIGNATURE")
                or self.headers.get("X-PAYMENT")
                or payload.get("payment_signature", "")
            )
            if payment_signature:
                task_id = payload.get("task_id") or ((payload.get("task") or {}).get("task_id") if isinstance(payload.get("task"), dict) else "")
                if not task_id:
                    self._json_response(
                        {
                            "ok": False,
                            "error": "task_id_required_for_x402_retry",
                            "message": "Retry with PAYMENT-SIGNATURE and the task_id returned in the 402 response.",
                        },
                        status=400,
                    )
                    return
                verification = self.agent.service_desk.verify_x402_payment(
                    task_id=task_id,
                    payment_signature=payment_signature,
                    requester_wallet=payload.get("requester_wallet", ""),
                )
                if verification.get("ok") and ((verification.get("task") or {}).get("status") == "paid"):
                    worked = self.agent.service_desk.work_task(task_id)
                    self._json_response(
                        {
                            "ok": True,
                            "mode": "x402_paid_help",
                            "payment": verification,
                            "work": worked,
                        },
                        status=200,
                        headers={
                            "PAYMENT-RESPONSE": self.agent.service_desk.x402.payment_response_header(
                                (((verification.get("task") or {}).get("payment") or {}).get("x402") or {}).get("verification") or {}
                            ),
                        },
                    )
                    return
                self._json_response(verification, status=402)
                return

            result = self.agent.direct_agent.handle_direct_message(payload)
            if result.get("ok"):
                payment_required = result.get("payment_required") or {}
                response_payload = (
                    self._jsonrpc_envelope(payload, result)
                    if self._is_jsonrpc_request(payload)
                    else result
                )
                self._json_response(
                    response_payload,
                    status=402,
                    headers={
                        "PAYMENT-REQUIRED": payment_required.get("encoded_header")
                        or self.agent.service_desk.x402.encode_header(payment_required),
                    },
                )
            else:
                self._json_response(result, status=400)
            return

        if parsed.path == "/tasks/verify":
            result = self.agent.service_desk.verify_payment(
                task_id=payload.get("task_id", ""),
                tx_hash=payload.get("tx_hash", ""),
                requester_wallet=payload.get("requester_wallet", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/tasks/x402-verify":
            payment_signature = (
                self.headers.get("PAYMENT-SIGNATURE")
                or self.headers.get("X-PAYMENT")
                or payload.get("payment_signature", "")
            )
            result = self.agent.service_desk.verify_x402_payment(
                task_id=payload.get("task_id", ""),
                payment_signature=payment_signature,
                requester_wallet=payload.get("requester_wallet", ""),
            )
            status = 200 if result.get("ok") and ((result.get("task") or {}).get("status") == "paid") else 402
            headers = {}
            x402_verification = (((result.get("task") or {}).get("payment") or {}).get("x402") or {}).get("verification") or {}
            if x402_verification:
                headers["PAYMENT-RESPONSE"] = self.agent.service_desk.x402.payment_response_header(x402_verification)
            self._json_response(result, status=status, headers=headers)
            return

        if parsed.path == "/tasks/work":
            result = self.agent.service_desk.work_task(
                task_id=payload.get("task_id", ""),
                approval=payload.get("approval", "draft_only"),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/tasks/staking":
            result = self.agent.service_desk.metamask_staking_checklist(
                task_id=payload.get("task_id", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/tasks/stake":
            result = self.agent.service_desk.record_treasury_stake(
                task_id=payload.get("task_id", ""),
                tx_hash=payload.get("tx_hash", ""),
                amount_native=payload.get("amount_native"),
                note=payload.get("note", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/tasks/spend":
            result = self.agent.service_desk.record_solver_spend(
                task_id=payload.get("task_id", ""),
                amount_native=float(payload.get("amount_native") or 0.0),
                note=payload.get("note", ""),
                tx_hash=payload.get("tx_hash", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/tasks/close":
            result = self.agent.service_desk.close_task(
                task_id=payload.get("task_id", ""),
                outcome=payload.get("outcome", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/agent-contacts":
            result = self.agent.agent_contacts.queue_contact(
                endpoint_url=payload.get("endpoint_url", ""),
                problem=payload.get("problem", ""),
                service_type=payload.get("service_type", "human_in_loop"),
                lead=payload.get("lead") or {},
                budget_hint_native=payload.get("budget_hint_native"),
            )
            self._json_response(result, status=201 if result.get("ok") else 400)
            return

        if parsed.path == "/agent-contacts/send":
            result = self.agent.agent_contacts.send_contact(
                contact_id=payload.get("contact_id", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        if parsed.path == "/agent-campaigns":
            targets = payload.get("targets") or []
            if payload.get("discover") or not targets:
                result = self.agent.agent_campaigns.create_campaign_from_discovery(
                    limit=payload.get("limit"),
                    query=payload.get("query") or payload.get("discovery_query") or "",
                    seeds=payload.get("seeds") or targets,
                    send=bool(payload.get("send", False)),
                    service_type=payload.get("service_type", "human_in_loop"),
                    budget_hint_native=payload.get("budget_hint_native"),
                )
            else:
                result = self.agent.agent_campaigns.create_campaign(
                    targets=targets,
                    limit=payload.get("limit"),
                    send=bool(payload.get("send", False)),
                    service_type=payload.get("service_type", "human_in_loop"),
                    budget_hint_native=payload.get("budget_hint_native"),
                )
            self._json_response(result, status=201 if result.get("ok") else 400)
            return

        if parsed.path in {"/lead-calibrate", "/leads-calibrate"}:
            result = self.agent.lead_discovery.calibrate_focus_scout(
                focus=str(payload.get("focus") or "").strip(),
                query=str(payload.get("query") or payload.get("q") or "").strip(),
                limit=max(3, min(int(payload.get("limit") or 12), 25)),
                candidate_multiplier=max(
                    3,
                    min(int(payload.get("candidate_multiplier") or payload.get("pool") or 5), 10),
                ),
            )
            self._json_response(result)
            return

        if parsed.path == "/leads":
            result = self.agent.lead_discovery.scout_public_leads(
                query=payload.get("query", "") or payload.get("q", ""),
                limit=max(1, min(int(payload.get("limit") or 5), 25)),
                focus=str(payload.get("focus") or "").strip(),
            )
            self._json_response(result)
            return

        if parsed.path == "/lead-conversions":
            if payload.get("list"):
                result = self.agent.lead_conversion.list_conversions(
                    statuses=payload.get("statuses") or payload.get("status") or [],
                    limit=int(payload.get("limit") or 25),
                )
            else:
                result = self.agent.lead_conversion.run(
                    query=payload.get("query", ""),
                    limit=int(payload.get("limit") or 5),
                    send=bool(payload.get("send", False)),
                    budget_hint_native=payload.get("budget_hint_native") or payload.get("budget_native"),
                    leads=payload.get("leads") if isinstance(payload.get("leads"), list) else None,
                )
            self._json_response(result, status=200 if result.get("ok", True) else 400)
            return

        if parsed.path == "/products":
            if payload.get("list"):
                result = self.agent.product_factory.list_products(
                    statuses=payload.get("statuses") or payload.get("status") or [],
                    limit=int(payload.get("limit") or 25),
                )
            else:
                result = self.agent.product_factory.run(
                    query=payload.get("query", ""),
                    limit=int(payload.get("limit") or 5),
                    leads=payload.get("leads") if isinstance(payload.get("leads"), list) else None,
                    conversions=payload.get("conversions") if isinstance(payload.get("conversions"), list) else None,
                )
            self._json_response(result, status=200 if result.get("ok", True) else 400)
            return

        if parsed.path == "/agent-pains":
            problem = payload.get("problem") or payload.get("message") or ""
            if problem:
                result = self.agent.agent_pain_solver.solve(
                    problem=problem,
                    service_type=payload.get("service_type") or payload.get("type") or "",
                    source="http_post",
                )
            else:
                result = self.agent.run("/agent-pains")
            self._json_response(result, status=200 if result.get("ok", True) else 400)
            return

        if parsed.path in {"/doctor", "/reliability-doctor"}:
            result = self.agent.agent_reliability_doctor.diagnose(
                problem=payload.get("problem") or payload.get("message") or "Agent needs reliability diagnosis.",
                service_type=payload.get("service_type") or payload.get("type") or "",
                source="http_post",
                evidence=payload.get("evidence") if isinstance(payload.get("evidence"), list) else None,
            )
            self._json_response(result, status=200 if result.get("ok", True) else 400)
            return

        if parsed.path == "/guardrails":
            result = guardrail_status(
                action=payload.get("action") or "manual.check",
                approval=payload.get("approval") or "",
                args=payload.get("args") if isinstance(payload.get("args"), dict) else {
                    "text": payload.get("text") or payload.get("message") or "",
                    "url": payload.get("url") or "",
                },
            )
            self._json_response(result, status=200 if result.get("ok") else 409)
            return

        if parsed.path == "/collaboration":
            self._json_response(collaboration_status())
            return

        if parsed.path == "/swarm/join":
            join_result = self.swarm_registry.register_join(
                payload,
                base_url=self._base_url(),
                remote_addr=self._remote_addr(),
                path=parsed.path,
            )
            if join_result.get("error") == "idempotency_key_conflict":
                join_status = 409
            elif join_result.get("idempotent_replay"):
                join_status = 200
            else:
                join_status = 202
            self._json_response(join_result, status=join_status)
            return

        if parsed.path == "/swarm/accumulate":
            result = self._accumulate_swarm_agents(payload)
            self._json_response(result, status=202 if result.get("ok") else 400)
            return

        if parsed.path in {"/swarm/develop", "/agent-development"}:
            result = self.agent_development.assist_agent(
                payload,
                base_url=self._base_url(),
                remote_addr=self._remote_addr(),
            )
            if not result.get("ok") and not result.get("machine_error"):
                result = merge_machine_error(
                    result,
                    error=str(result.get("error") or "agent_development_failed"),
                    message="Swarm develop request did not succeed.",
                    hints=["GET /swarm/develop for required fields.", "GET /openapi.json for the POST schema."],
                )
            if result.get("idempotent_replay"):
                dev_status = 200
            else:
                dev_status = 202 if result.get("ok") else 422
            self._json_response(result, status=dev_status)
            return

        if parsed.path in {"/roaas/import", "/artifacts/runtime-patterns", "/.well-known/nomad-runtime-patterns.json"}:
            result = self.roaas.import_bundle(
                payload,
                source=str(payload.get("source") or "").strip(),
                trust_level=self._parse_pattern_status(payload.get("trust_level") or "candidate"),
            )
            self._json_response(result, status=202 if result.get("ok") else 400)
            return

        if parsed.path in {"/aid", "/mutual-aid/inbox"}:
            result = self.agent.mutual_aid.receive_swarm_proposal(payload)
            if not result.get("ok") and not result.get("machine_error"):
                reason = ""
                ver = result.get("verification") if isinstance(result.get("verification"), dict) else {}
                reason = str(ver.get("reason") or "").strip()
                result = merge_machine_error(
                    result,
                    error="swarm_proposal_rejected",
                    message=reason or "Proposal failed verification.",
                    hints=[
                        "Send sender_id, title, proposal, evidence per swarm contract.",
                        "GET /openapi.json for mutual-aid patterns when extended.",
                    ],
                )
            self._json_response(result, status=202 if result.get("ok") else 422)
            return

        if parsed.path == "/mutual-aid/outcomes":
            result = self.agent.mutual_aid.record_truth_outcome(
                ledger_id=payload.get("ledger_id", ""),
                success=bool(payload.get("success", False)),
                evidence=payload.get("evidence") if isinstance(payload.get("evidence"), list) else [],
                outcome_status=payload.get("outcome_status", ""),
                note=payload.get("note", ""),
            )
            self._json_response(result, status=200 if result.get("ok") else 404)
            return

        self._json_response(
            merge_machine_error(
                {
                    "ok": False,
                    "error": "not_found",
                    "available_paths": [
                    "/",
                    "/nomad.html",
                    "/openapi.json",
                    "/.well-known/openapi.json",
                    "/tasks",
                    "/service/e2e",
                    "/tasks/verify",
                    "/tasks/x402-verify",
                    "/tasks/work",
                    "/tasks/staking",
                    "/tasks/stake",
                    "/tasks/spend",
                    "/tasks/close",
                    "/agent-contacts",
                    "/agent-contacts/send",
                    "/agent-campaigns",
                    "/agent-engagements",
                    "/agent-engagements/summary",
                    "/outbound",
                    "/operator-desk",
                    "/operator/desk",
                    "/operator-sprint",
                    "/operator/sprint",
                    "/operator-verify",
                    "/operator/verify",
                    "/operator-metrics",
                    "/operator/metrics",
                    "/operator-daily",
                    "/operator/daily",
                    "/operator-report",
                    "/operator/report",
                    "/reputation",
                    "/agent-reputation",
                    "/unhuman-hub",
                    "/hub/unhuman",
                    "/agent-growth",
                    "/growth-pipeline",
                    "/growth-start",
                    "/operator/growth-start",
                    "/agent-attractor",
                    "/swarm",
                    "/swarm/join",
                    "/swarm/network",
                    "/swarm/coordinate",
                    "/swarm/accumulate",
                    "/swarm/develop",
                    "/agent-development",
                    "/.well-known/agent-attractor.json",
                    "/.well-known/agent-card.json",
                    "/.well-known/nomad-agent-invariants.json",
                    "/agent-invariants",
                    "/.well-known/nomad-inter-agent-witness-offer.json",
                    "/inter-agent-witness-offer",
                    "/.well-known/nomad-peer-acquisition.json",
                    "/peer-acquisition",
                    "/.well-known/nomad-agent-native-priorities.json",
                    "/.well-known/nomad-agent.json",
                    "/agent-native-index",
                    "/agent-native",
                    "/a2a/message",
                    "/a2a/discover",
                    "/x402/paid-help",
                    "/leads",
                    "/lead-calibrate",
                    "/lead-conversions",
                    "/products",
                    "/agent-pains",
                    "/reliability-doctor",
                    "/guardrails",
                    "/collaboration",
                    "/roaas",
                    "/roaas/export",
                    "/roaas/import",
                    "/artifacts/runtime-patterns",
                    "/.well-known/nomad-runtime-patterns.json",
                    "/aid",
                    "/mutual-aid/inbox",
                    "/mutual-aid/outcomes",
                ],
            },
                error="not_found",
                message="No POST handler matched this path.",
                hints=["GET /openapi.json for documented POST routes.", "GET /health for liveness."],
            ),
            status=404,
        )

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._send_common_headers()
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _accumulate_swarm_agents(self, payload: dict) -> dict:
        contacts = payload.get("contacts") if isinstance(payload.get("contacts"), list) else []
        campaigns = payload.get("campaigns") if isinstance(payload.get("campaigns"), list) else []
        leads = payload.get("leads") if isinstance(payload.get("leads"), list) else []
        limit = int(payload.get("limit") or 100)
        if payload.get("from_contacts", True):
            try:
                listing = self.agent.agent_contacts.list_contacts(limit=limit)
                contacts = list(contacts) + [
                    item for item in (listing.get("contacts") or []) if isinstance(item, dict)
                ]
            except Exception:
                pass
        if payload.get("from_campaigns", True):
            try:
                listing = self.agent.agent_campaigns.list_campaigns(limit=min(limit, 25))
                campaigns = list(campaigns) + [
                    item for item in (listing.get("campaigns") or []) if isinstance(item, dict)
                ]
            except Exception:
                pass
        return self.swarm_registry.accumulate_agents(
            contacts=contacts,
            campaigns=campaigns,
            leads=leads,
            base_url=self._base_url(),
            focus_pain_type=str(payload.get("focus_pain_type") or payload.get("pain_type") or payload.get("service_type") or ""),
        )

    def _read_json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _send_common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _base_url(self) -> str:
        configured = preferred_public_base_url(allow_local_fallback=False)
        if configured:
            return configured

        proto = str(self.headers.get("X-Forwarded-Proto") or "http").split(",")[0].strip() or "http"
        host = (
            str(self.headers.get("X-Forwarded-Host") or "").split(",")[0].strip()
            or str(self.headers.get("Host") or "").strip()
            or f"{HOST}:{PORT}"
        )
        prefix = str(self.headers.get("X-Forwarded-Prefix") or "").split(",")[0].strip()
        if prefix and not prefix.startswith("/"):
            prefix = f"/{prefix}"
        return f"{proto}://{host}{prefix}".rstrip("/")

    def _remote_addr(self) -> str:
        forwarded_for = str(self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if forwarded_for:
            return forwarded_for
        if isinstance(self.client_address, tuple) and self.client_address:
            return str(self.client_address[0])
        return ""

    def _is_jsonrpc_request(self, payload: dict) -> bool:
        return (
            isinstance(payload, dict)
            and payload.get("jsonrpc") == "2.0"
            and "id" in payload
            and isinstance(payload.get("method"), str)
        )

    def _jsonrpc_envelope(self, request_payload: dict, result: dict) -> dict:
        message = self._a2a_message_result(result)
        return {
            "jsonrpc": "2.0",
            "id": request_payload.get("id"),
            "result": message,
        }

    def _a2a_message_result(self, result: dict) -> dict:
        message_id = (
            ((result.get("session") or {}).get("last_task_id"))
            or ((result.get("task") or {}).get("task_id"))
            or "nomad-message"
        )
        text = str(result.get("next_agent_message") or "")
        return {
            "messageId": message_id,
            "role": "agent",
            "type": "message",
            "parts": [
                {
                    "type": "text",
                    "kind": "text",
                    "text": text,
                }
            ],
            "metadata": {
                "mode": result.get("mode", ""),
                "classification": ((result.get("free_diagnosis") or {}).get("classification") or ""),
                "task_id": ((result.get("task") or {}).get("task_id") or ""),
                "payment_required": bool(result.get("payment_required")),
                "normalized_request": result.get("normalized_request") or {},
                "structured_reply": result.get("structured_reply") or {},
                "decision_envelope": result.get("decision_envelope") or {},
            },
        }

    def _json_response(self, payload: dict, status: int = 200, headers: dict | None = None) -> None:
        if isinstance(payload, dict):
            payload = maybe_merge_http_wire_diag(self, payload)
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_common_headers()
        for key, value in (headers or {}).items():
            self.send_header(key, str(value))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_file_response(self, path: Path, status: int = 200) -> None:
        if not path.exists() or not path.is_file():
            self._json_response(
                machine_error_response(
                    error="html_not_found",
                    message=f"Missing static file: {path.name}",
                    hints=["GET /nomad.html when public/nomad.html exists.", "GET /openapi.json for API routes."],
                ),
                status=404,
            )
            return
        body = path.read_bytes()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._send_common_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _truthy(value: object, default: bool = False) -> bool:
        if value is None or value == "":
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _parse_pattern_status(value: object) -> PatternStatus:
        try:
            return PatternStatus(str(value or "").strip().lower())
        except ValueError:
            return PatternStatus.CANDIDATE


def serve() -> None:
    server = ThreadingHTTPServer((HOST, PORT), NomadApiHandler)
    print(f"--- Nomad API Live on http://{HOST}:{PORT} ---")
    server.serve_forever()


def serve_in_thread() -> threading.Thread:
    thread = threading.Thread(target=serve, name="nomad-api", daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    serve()
