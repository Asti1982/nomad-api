import json
import os
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

from nomad_api import serve_in_thread
from nomad_autonomy_proof import AutonomyProofHarness
from nomad_operator_grant import operator_grant, service_approval_scope
from nomad_public_url import preferred_public_base_url
from self_development import SelfDevelopmentJournal
from workflow import NomadAgent


from nomad_monitor import NomadSystemMonitor
from decision_engine import DecisionEngine


load_dotenv()

ROOT = Path(__file__).resolve().parent
DEFAULT_AUTOPILOT_STATE = ROOT / "nomad_autopilot_state.json"


class NomadAutopilot:
    """Continuous loop for Nomad's customer service, outreach, and self-improvement."""

    def __init__(
        self,
        agent: Optional[NomadAgent] = None,
        journal: Optional[SelfDevelopmentJournal] = None,
        path: Optional[Path] = None,
        sleep_fn=time.sleep,
    ) -> None:
        self.agent = agent or NomadAgent()
        try:
            setattr(self.agent, "autopilot", self)
        except Exception:
            pass
        self.monitor = NomadSystemMonitor(agent=self.agent)
        self.journal = journal or SelfDevelopmentJournal()
        self.path = path or DEFAULT_AUTOPILOT_STATE
        self.sleep_fn = sleep_fn
        self.default_interval_seconds = int(os.getenv("NOMAD_AUTOPILOT_INTERVAL_SECONDS", "900"))
        self.default_outreach_limit = int(os.getenv("NOMAD_AUTOPILOT_OUTREACH_LIMIT", "10"))
        self.default_conversion_limit = int(os.getenv("NOMAD_AUTOPILOT_CONVERSION_LIMIT", "5"))
        self.default_daily_lead_target = int(os.getenv("NOMAD_AUTOPILOT_DAILY_LEAD_TARGET", "100"))
        self.default_service_limit = int(os.getenv("NOMAD_AUTOPILOT_SERVICE_LIMIT", "25"))
        self.default_contact_poll_limit = int(
            os.getenv("NOMAD_AUTOPILOT_CONTACT_POLL_LIMIT", "10")
        )
        self.default_service_approval = service_approval_scope()
        _lead_focus = (os.getenv("NOMAD_LEAD_FOCUS") or "compute_auth").strip().lower()
        self.default_outreach_service_type = (
            os.getenv("NOMAD_OUTREACH_SERVICE_TYPE")
            or (
                "compute_auth"
                if _lead_focus in {"compute_auth", "machine_human_gap", "agent_infra_prime"}
                else "human_in_loop"
            )
        ).strip() or "compute_auth"
        self.default_outreach_query = (
            os.getenv("NOMAD_AUTOPILOT_OUTREACH_QUERY") or '"agent-card" "quota" "token" "https://"'
        ).strip()
        self.default_outreach_queries = self._configured_outreach_queries()
        # Continuous acquisition: when NOMAD_AUTOPILOT_CONTINUOUS_ACQUISITION is unset, default ON iff
        # NOMAD_PUBLIC_API_URL points at a non-localhost surface (safe for dev: localhost stays off).
        raw_continuous = os.getenv("NOMAD_AUTOPILOT_CONTINUOUS_ACQUISITION")
        if raw_continuous is None or not str(raw_continuous).strip():
            continuous_acquisition = self.__class__._is_public_service_url(preferred_public_base_url())
        else:
            continuous_acquisition = str(raw_continuous).strip().lower() in {"1", "true", "yes", "on"}
        self.continuous_acquisition = bool(continuous_acquisition)

        def _bool_env(name: str, *, when_continuous: bool, when_idle: bool) -> bool:
            raw = os.getenv(name)
            if raw is None or not str(raw).strip():
                return when_continuous if continuous_acquisition else when_idle
            return str(raw).strip().lower() in {"1", "true", "yes", "on"}

        self.default_send_outreach = _bool_env(
            "NOMAD_AUTOPILOT_SEND_OUTREACH", when_continuous=True, when_idle=False
        )
        self.default_send_a2a = _bool_env(
            "NOMAD_AUTOPILOT_A2A_SEND", when_continuous=True, when_idle=False
        )
        self.all_surfaces_mode = _bool_env(
            "NOMAD_AUTOPILOT_ALL_SURFACES", when_continuous=True, when_idle=False
        )
        self.all_surfaces_enforce = _bool_env(
            "NOMAD_AUTOPILOT_ALL_SURFACES_ENFORCE", when_continuous=False, when_idle=False
        )
        self.evidence_or_pay_enforce = _bool_env(
            "NOMAD_AUTOPILOT_EVIDENCE_OR_PAY_ENFORCE", when_continuous=True, when_idle=False
        )
        self.agent_growth_pipeline_enabled = _bool_env(
            "NOMAD_AUTOPILOT_AGENT_GROWTH_PIPELINE", when_continuous=True, when_idle=False
        )
        self.agent_growth_every_n_cycles = max(
            1, int(os.getenv("NOMAD_AUTOPILOT_AGENT_GROWTH_EVERY_N_CYCLES", "1") or "1")
        )
        self.agent_growth_query = (os.getenv("NOMAD_AUTOPILOT_AGENT_GROWTH_QUERY") or "").strip()
        self.agent_growth_limit = max(
            1, min(int(os.getenv("NOMAD_AUTOPILOT_AGENT_GROWTH_LIMIT", "5") or "5"), 25)
        )
        self.agent_growth_send_outreach = _bool_env(
            "NOMAD_AUTOPILOT_AGENT_GROWTH_SEND", when_continuous=True, when_idle=False
        )
        self.agent_growth_approval = (os.getenv("NOMAD_AGENT_GROWTH_APPROVAL") or "").strip()
        self.agent_growth_no_products = (
            os.getenv("NOMAD_AUTOPILOT_AGENT_GROWTH_NO_PRODUCTS", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.agent_growth_no_swarm_feed = (
            os.getenv("NOMAD_AUTOPILOT_AGENT_GROWTH_NO_SWARM_FEED", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.always_send_payment_followups = (
            os.getenv("NOMAD_ALWAYS_SEND_PAYMENT_FOLLOWUPS", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.default_payment_followup_limit = int(
            os.getenv("NOMAD_AUTOPILOT_PAYMENT_FOLLOWUP_LIMIT", "3")
        )
        self.payment_followup_hours = max(
            1,
            int(os.getenv("NOMAD_AUTOPILOT_PAYMENT_FOLLOWUP_HOURS", "24")),
        )
        self.default_agent_followup_limit = int(
            os.getenv("NOMAD_AUTOPILOT_AGENT_FOLLOWUP_LIMIT", "3")
        )
        self.agent_followup_hours = max(
            1,
            int(os.getenv("NOMAD_AUTOPILOT_AGENT_FOLLOWUP_HOURS", "48")),
        )
        self._api_thread = None
        self._outreach_query_cursor = 0
        self._payment_followup_log: dict[str, dict[str, Any]] = {}
        self._agent_followup_log: dict[str, dict[str, Any]] = {}
        self.autonomy_proof = AutonomyProofHarness()
        self.last_cycle_report: Optional[Dict[str, Any]] = None

    def run_once(
        self,
        objective: str = "",
        profile_id: str = "ai_first",
        outreach_limit: Optional[int] = None,
        outreach_query: str = "",
        send_outreach: Optional[bool] = None,
        conversion_limit: Optional[int] = None,
        conversion_query: str = "",
        send_a2a: Optional[bool] = None,
        daily_lead_target: Optional[int] = None,
        service_limit: Optional[int] = None,
        service_approval: str = "",
        serve_api: bool = False,
        check_decision: bool = False,
    ) -> Dict[str, Any]:
        if serve_api:
            self._ensure_api()

        decision: Dict[str, Any] = {}
        if check_decision:
            decision = self._decision()
            if not decision.get("should_start"):
                report = self._idle_report(decision)
                self._record_idle(report)
                return report

        effective_send_outreach = self.default_send_outreach if send_outreach is None else bool(send_outreach)
        effective_send_a2a = self.default_send_a2a if send_a2a is None else bool(send_a2a)
        public_api_url = preferred_public_base_url()
        send_queue_enabled = bool(
            (effective_send_outreach or effective_send_a2a)
            and self._is_public_service_url(public_api_url)
        )
        payment_send_enabled = bool(
            self.always_send_payment_followups
            and self._is_public_service_url(public_api_url)
        )
        target = max(0, int(daily_lead_target if daily_lead_target is not None else self.default_daily_lead_target))
        daily_quota_start = self._daily_quota(target)
        base_outreach_limit = max(0, int(outreach_limit or self.default_outreach_limit))
        flush_limit = min(base_outreach_limit, daily_quota_start["remaining_to_send"]) if send_queue_enabled else 0
        resolved_service_approval = (service_approval or "").strip() or service_approval_scope()
        service_summary = self._process_service_queue(
            limit=service_limit or self.default_service_limit,
            approval=resolved_service_approval,
        )
        payment_followup_queue = self._queue_payment_followups(
            service_summary=service_summary,
            limit=self.default_payment_followup_limit,
            enabled=payment_send_enabled,
        )
        payment_followup_send = self._send_payment_followups(
            payment_followup_queue,
            enabled=payment_send_enabled,
        )
        contact_summary = self._flush_contact_queue(
            limit=flush_limit,
            send_enabled=send_queue_enabled,
        )
        contact_poll = self._poll_contact_updates(
            limit=min(
                outreach_limit or self.default_outreach_limit,
                self.default_contact_poll_limit,
            )
        )
        agent_followup_queue = self._queue_agent_followups(
            contact_poll=contact_poll,
            limit=self.default_agent_followup_limit,
            enabled=send_queue_enabled,
        )
        queued_agent_followups = len(agent_followup_queue.get("queued_contact_ids") or [])
        if queued_agent_followups > 0:
            agent_followup_send = self._flush_contact_queue(
                limit=queued_agent_followups,
                send_enabled=send_queue_enabled,
            )
        else:
            agent_followup_send = {
                "queued_listing": {"contacts": [], "stats": {}},
                "sent_contact_ids": [],
                "failed_contact_ids": [],
                "analysis": "No queued agent follow-up contacts to send.",
                "skipped": True,
                "reason": "no_agent_followups_queued",
            }
        reply_conversion = self._convert_replies_to_service_tasks(contact_poll)
        evidence_or_pay_gate = self._evidence_or_pay_gate(
            enforce=self.evidence_or_pay_enforce,
            service_summary=service_summary,
            contact_poll=contact_poll,
            reply_conversion=reply_conversion,
        )

        journal_state = self.journal.load()
        surface_gate = self._all_surfaces_gate(
            enabled=self.all_surfaces_mode,
            enforce=self.all_surfaces_enforce,
            public_api_url=public_api_url,
        )
        evidence_remediation = self._evidence_or_pay_remediation(evidence_or_pay_gate)
        surface_remediation = self._surface_gate_remediation(surface_gate)
        selected_objective = (
            (objective or "").strip()
            or str(evidence_remediation.get("objective") or "").strip()
            or str(surface_remediation.get("objective") or "").strip()
            or self._service_objective(service_summary)
            or self._reply_conversion_objective(reply_conversion)
            or self._reply_objective(contact_poll)
            or journal_state.get("next_objective")
            or SelfDevelopmentJournal.default_objective()
        )

        self_improvement = self.agent.self_improvement.run_cycle(
            objective=selected_objective,
            profile_id=profile_id,
        )
        sent_after_flush = self._sent_from_contact_queue(contact_summary)
        remaining_to_send = max(0, daily_quota_start["remaining_to_send"] - sent_after_flush)
        remaining_to_prepare = daily_quota_start["remaining_to_prepare"]
        conversion_base_limit = max(
            0,
            int(conversion_limit if conversion_limit is not None else self.default_conversion_limit),
        )
        conversion_effective_limit = min(
            conversion_base_limit,
            remaining_to_send if effective_send_a2a else remaining_to_prepare,
        )
        lead_conversion = self._run_lead_conversion(
            self_improvement=self_improvement,
            limit=conversion_effective_limit,
            explicit_query=conversion_query or outreach_query,
            send_a2a=effective_send_a2a,
            blocked_reason=self._merge_block_reason(
                str(surface_gate.get("lead_conversion_blocked_reason", "") or ""),
                str(evidence_or_pay_gate.get("lead_conversion_blocked_reason", "") or ""),
            ),
        )
        lead_delta = self._lead_conversion_contact_delta(lead_conversion)
        remaining_to_send = max(0, remaining_to_send - lead_delta["sent"])
        remaining_to_prepare = max(0, remaining_to_prepare - lead_delta["prepared"])
        product_factory = self._run_product_factory(
            lead_conversion=lead_conversion,
            self_improvement=self_improvement,
        )
        lead_workbench = self._run_lead_workbench(limit=5)
        outreach_effective_limit = min(
            base_outreach_limit,
            remaining_to_send if effective_send_outreach else remaining_to_prepare,
        )
        outreach_summary = self._run_outreach(
            self_improvement=self_improvement,
            limit=outreach_effective_limit,
            explicit_query=outreach_query,
            send_outreach=effective_send_outreach,
            blocked_reason=self._merge_block_reason(
                str(surface_gate.get("outreach_blocked_reason", "") or ""),
                str(evidence_or_pay_gate.get("outreach_blocked_reason", "") or ""),
            ),
        )
        daily_quota = self._daily_quota_after(
            start=daily_quota_start,
            contact_summary=contact_summary,
            lead_conversion=lead_conversion,
            outreach_summary=outreach_summary,
        )
        swarm_accumulation = self._run_swarm_accumulation(
            lead_conversion=lead_conversion,
            outreach_summary=outreach_summary,
            public_api_url=public_api_url,
        )
        mutual_aid = self._run_mutual_aid_evolution(
            lead_conversion=lead_conversion,
            contact_poll=contact_poll,
            reply_conversion=reply_conversion,
            objective=selected_objective,
        )
        swarm_coordination = self._run_swarm_coordination(
            self_improvement=self_improvement,
            lead_conversion=lead_conversion,
            outreach_summary=outreach_summary,
            public_api_url=public_api_url,
        )
        all_surfaces = self._run_all_surfaces(
            enabled=self.all_surfaces_mode,
            public_api_url=public_api_url,
            lead_conversion=lead_conversion,
            outreach_summary=outreach_summary,
        )
        agent_growth_pipeline_report: Dict[str, Any] = {"skipped": True, "reason": "disabled"}
        if self.agent_growth_pipeline_enabled:
            state_before = self._load()
            next_run_num = int(state_before.get("run_count") or 0) + 1
            n_every = max(1, int(self.agent_growth_every_n_cycles))
            if next_run_num % n_every == 0:
                from nomad_agent_growth_pipeline import agent_growth_pipeline

                growth_query = self.agent_growth_query or self.default_outreach_query
                growth_send = bool(
                    self.agent_growth_send_outreach
                    and self._is_public_service_url(public_api_url)
                )
                agent_growth_pipeline_report = agent_growth_pipeline(
                    agent=self.agent,
                    query=growth_query,
                    limit=self.agent_growth_limit,
                    base_url=public_api_url,
                    run_product_factory=not self.agent_growth_no_products,
                    send_outreach=growth_send,
                    approval=self.agent_growth_approval,
                    swarm_feed=False if self.agent_growth_no_swarm_feed else None,
                )
            else:
                agent_growth_pipeline_report = {
                    "skipped": True,
                    "reason": "cycle_modulo",
                    "next_run_num": next_run_num,
                    "every_n": n_every,
                }
        autonomous_development = self_improvement.get("autonomous_development") or {}
        outbound_tracking = self._outbound_tracking_snapshot()
        efficiency_plan = self._efficiency_plan(
            public_api_url=public_api_url,
            service_summary=service_summary,
            payment_followup_queue=payment_followup_queue,
            contact_summary=contact_summary,
            contact_poll=contact_poll,
            lead_conversion=lead_conversion,
            outreach_summary=outreach_summary,
            swarm_accumulation=swarm_accumulation,
            swarm_coordination=swarm_coordination,
            self_improvement=self_improvement,
            daily_quota=daily_quota,
            agent_growth_pipeline=agent_growth_pipeline_report,
        )

        report = {
            "mode": "nomad_autopilot",
            "deal_found": False,
            "timestamp": datetime.now(UTC).isoformat(),
            "continuous_acquisition": self.continuous_acquisition,
            "objective": selected_objective,
            "profile_id": profile_id,
            "public_api_url": public_api_url,
            "service_approval": resolved_service_approval,
            "operator_grant": operator_grant(),
            "decision": decision,
            "service": service_summary,
            "payment_followup_queue": payment_followup_queue,
            "payment_followup_send": payment_followup_send,
            "contact_queue": contact_summary,
            "contact_poll": contact_poll,
            "agent_followup_queue": agent_followup_queue,
            "agent_followup_send": agent_followup_send,
            "reply_conversion": reply_conversion,
            "self_improvement": self_improvement,
            "lead_conversion": lead_conversion,
            "product_factory": product_factory,
            "lead_workbench": lead_workbench,
            "outreach": outreach_summary,
            "outbound_tracking": outbound_tracking,
            "swarm_accumulation": swarm_accumulation,
            "mutual_aid": mutual_aid,
            "swarm_coordination": swarm_coordination,
            "all_surfaces": all_surfaces,
            "all_surfaces_gate": surface_gate,
            "surface_gate_remediation": surface_remediation,
            "evidence_or_pay_gate": evidence_or_pay_gate,
            "evidence_or_pay_remediation": evidence_remediation,
            "agent_growth_pipeline": agent_growth_pipeline_report,
            "autonomous_development": autonomous_development,
            "efficiency_plan": efficiency_plan,
            "daily_quota": daily_quota,
            "analysis": self._analysis(
                objective=selected_objective,
                service_summary=service_summary,
                payment_followup_queue=payment_followup_queue,
                payment_followup_send=payment_followup_send,
                contact_summary=contact_summary,
                contact_poll=contact_poll,
                agent_followup_queue=agent_followup_queue,
                agent_followup_send=agent_followup_send,
                reply_conversion=reply_conversion,
                lead_conversion=lead_conversion,
                product_factory=product_factory,
                lead_workbench=lead_workbench,
                outreach_summary=outreach_summary,
                swarm_accumulation=swarm_accumulation,
                mutual_aid=mutual_aid,
                swarm_coordination=swarm_coordination,
                autonomous_development=autonomous_development,
                self_improvement=self_improvement,
                daily_quota=daily_quota,
                surface_gate=surface_gate,
                surface_remediation=surface_remediation,
                evidence_or_pay_gate=evidence_or_pay_gate,
                evidence_remediation=evidence_remediation,
            ),
        }
        report["autonomy_proof"] = self.autonomy_proof.evaluate(
            report,
            previous_state=self._load(),
        )
        report["analysis"] += " " + report["autonomy_proof"]["analysis"]
        agp = report.get("agent_growth_pipeline") or {}
        if agp.get("mode") == "nomad_agent_growth_pipeline" and bool(agp.get("ok", True)):
            leads_ag = agp.get("leads") or {}
            cand = leads_ag.get("candidate_count")
            if cand is None:
                cand = len(leads_ag.get("leads") or [])
            pf_ag = agp.get("product_factory") or {}
            pc_ag = int(pf_ag.get("product_count") or len(pf_ag.get("products") or []))
            sw_ag = agp.get("swarm_accumulation") or {}
            nid_ag = len(sw_ag.get("new_prospect_ids") or [])
            report["analysis"] += (
                f" Agent-growth pipeline: scout_candidates={cand}, products={pc_ag}, new_swarm_prospects={nid_ag}."
            )
        self._record(report)
        return report

    def run_forever(
        self,
        cycles: int = 0,
        interval_seconds: Optional[int] = None,
        self_schedule: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        kwargs["check_decision"] = self_schedule
        delay = max(1, int(interval_seconds or self.default_interval_seconds))
        completed = 0
        last_report: Dict[str, Any] = {}
        while cycles <= 0 or completed < cycles:
            completed += 1
            last_report = self.run_once(**kwargs)
            last_report["loop_index"] = completed
            if cycles > 0 and completed >= cycles:
                break
            next_delay = self._next_loop_delay(last_report=last_report, max_delay=delay)
            self.sleep_fn(next_delay)
        return last_report

    def _outbound_tracking_snapshot(self) -> Dict[str, Any]:
        tracker = getattr(self.agent, "outbound_tracker", None)
        if tracker is None or not hasattr(tracker, "summary"):
            return {
                "ok": False,
                "reason": "tracker_unavailable",
            }
        try:
            summary = tracker.summary(limit=5)
        except Exception as exc:
            return {
                "ok": False,
                "reason": "tracker_error",
                "error": str(exc),
            }
        return {
            "ok": bool(summary.get("ok")),
            "next_best_action": summary.get("next_best_action", ""),
            "contacts": summary.get("contacts") or {},
            "campaigns": summary.get("campaigns") or {},
            "tasks": summary.get("tasks") or {},
            "autonomous_tracking": summary.get("autonomous_tracking") or {},
        }

    def _run_all_surfaces(
        self,
        *,
        enabled: bool,
        public_api_url: str,
        lead_conversion: Dict[str, Any],
        outreach_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not enabled:
            return {
                "mode": "nomad_autopilot_all_surfaces",
                "enabled": False,
                "skipped": True,
                "reason": "disabled",
            }
        base = (public_api_url or "").rstrip("/")
        endpoint = lambda path: f"{base}{path}" if base else path
        lead_stats = lead_conversion.get("stats") if isinstance(lead_conversion.get("stats"), dict) else {}
        outreach_campaign = (
            outreach_summary.get("campaign") if isinstance(outreach_summary.get("campaign"), dict) else {}
        )
        sent_outreach = int(outreach_campaign.get("stats", {}).get("sent") or 0) if isinstance(
            outreach_campaign.get("stats"), dict
        ) else 0
        return {
            "mode": "nomad_autopilot_all_surfaces",
            "enabled": True,
            "surface_urls": {
                "bootstrap": endpoint("/swarm/bootstrap"),
                "develop": endpoint("/swarm/develop"),
                "join": endpoint("/swarm/join"),
                "coordinate": endpoint("/swarm/coordinate"),
                "agent_card": endpoint("/.well-known/agent-card.json"),
                "tasks": endpoint("/tasks"),
            },
            "activation_order": [
                "bootstrap",
                "develop",
                "join",
                "coordinate",
                "tasks",
            ],
            "autonomous_focus": {
                "lane": "outside_human_comfort_compute_auth",
                "strategy": "Use machine-verifiable blocker resolution and reciprocity artifacts.",
            },
            "signals": {
                "lead_conversions_prepared": int(sum(int(v or 0) for v in lead_stats.values())) if lead_stats else 0,
                "outreach_sent": sent_outreach,
            },
        }

    def _all_surfaces_gate(
        self,
        *,
        enabled: bool,
        enforce: bool,
        public_api_url: str,
    ) -> Dict[str, Any]:
        if not enforce:
            return {
                "enabled": bool(enabled),
                "enforced": False,
                "blocked": False,
                "reason": "",
                "outreach_blocked_reason": "",
                "lead_conversion_blocked_reason": "",
            }
        if not enabled:
            return {
                "enabled": False,
                "enforced": True,
                "blocked": True,
                "reason": "all_surfaces_mode_required",
                "outreach_blocked_reason": "all_surfaces_mode_required",
                "lead_conversion_blocked_reason": "all_surfaces_mode_required",
            }
        if not self._is_public_service_url(public_api_url):
            return {
                "enabled": True,
                "enforced": True,
                "blocked": True,
                "reason": "public_api_url_required",
                "outreach_blocked_reason": "public_api_url_required",
                "lead_conversion_blocked_reason": "public_api_url_required",
            }
        return {
            "enabled": True,
            "enforced": True,
            "blocked": False,
            "reason": "",
            "outreach_blocked_reason": "",
            "lead_conversion_blocked_reason": "",
        }

    @staticmethod
    def _merge_block_reason(primary: str, secondary: str) -> str:
        p = (primary or "").strip()
        s = (secondary or "").strip()
        return p or s

    def _evidence_or_pay_gate(
        self,
        *,
        enforce: bool,
        service_summary: Dict[str, Any],
        contact_poll: Dict[str, Any],
        reply_conversion: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not enforce:
            return {
                "enforced": False,
                "blocked": False,
                "reason": "",
                "outreach_blocked_reason": "",
                "lead_conversion_blocked_reason": "",
                "signals": {},
            }
        paid_signals = bool(
            (service_summary.get("worked_task_ids") or [])
            or (service_summary.get("draft_ready_task_ids") or [])
            or (service_summary.get("awaiting_payment_task_ids") or [])
            or (service_summary.get("payment_followups") or [])
        )
        reply_signals = bool(contact_poll.get("reply_summaries") or [])
        converted_signals = bool(reply_conversion.get("created_task_ids") or [])
        signals = {
            "paid_lane_signal": paid_signals,
            "reply_artifact_signal": reply_signals,
            "converted_paid_signal": converted_signals,
        }
        if any(signals.values()):
            return {
                "enforced": True,
                "blocked": False,
                "reason": "",
                "outreach_blocked_reason": "",
                "lead_conversion_blocked_reason": "",
                "signals": signals,
            }
        return {
            "enforced": True,
            "blocked": True,
            "reason": "evidence_or_pay_required",
            "outreach_blocked_reason": "evidence_or_pay_required",
            "lead_conversion_blocked_reason": "evidence_or_pay_required",
            "signals": signals,
        }

    @staticmethod
    def _evidence_or_pay_remediation(evidence_gate: Dict[str, Any]) -> Dict[str, Any]:
        if not bool(evidence_gate.get("blocked")):
            return {
                "required": False,
                "objective": "",
                "priority": "normal",
                "next_actions": [],
            }
        return {
            "required": True,
            "reason": str(evidence_gate.get("reason") or "evidence_or_pay_required"),
            "priority": "critical",
            "objective": (
                "Generate machine-verifiable evidence or paid-lane signal before autonomous outbound growth."
            ),
            "next_actions": [
                "Collect one reply artifact via contact_poll.reply_summaries.",
                "Convert one reply to a bounded paid task or verify one awaiting-payment task.",
                "Only then unlock outreach/lead-conversion send paths.",
            ],
        }

    @staticmethod
    def _surface_gate_remediation(surface_gate: Dict[str, Any]) -> Dict[str, Any]:
        if not bool(surface_gate.get("blocked")):
            return {
                "required": False,
                "objective": "",
                "priority": "normal",
                "next_actions": [],
            }
        reason = str(surface_gate.get("reason") or "unknown")
        objective = (
            "Unblock all-surfaces contract lane so bootstrap/develop/join/coordinate/tasks "
            "run as one machine-native growth loop."
        )
        next_actions = [
            "Set NOMAD_AUTOPILOT_ALL_SURFACES=true.",
            "Expose a public NOMAD_PUBLIC_API_URL and verify /swarm/bootstrap + /swarm/join + /swarm/coordinate.",
            "Re-run autopilot and confirm all_surfaces_gate.blocked=false before outreach/conversion.",
        ]
        if reason == "public_api_url_required":
            next_actions[1] = (
                "Set a public NOMAD_PUBLIC_API_URL (non-localhost) and verify /health + /swarm/bootstrap."
            )
        return {
            "required": True,
            "reason": reason,
            "objective": objective,
            "priority": "critical",
            "next_actions": next_actions,
        }

    def _decision(self) -> Dict[str, Any]:
        state = self._load()
        snapshot = self.monitor.snapshot()
        return DecisionEngine(state=state, snapshot=snapshot).decide()

    def _idle_report(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        next_check_seconds = int(decision.get("next_check_seconds") or self.default_interval_seconds)
        reason = decision.get("reason") or "waiting_for_next_trigger"
        return {
            "mode": "autopilot_idle",
            "deal_found": False,
            "timestamp": datetime.now(UTC).isoformat(),
            "decision": decision,
            "next_check_seconds": next_check_seconds,
            "next_check_at": decision.get("next_check_at", ""),
            "analysis": (
                f"Nomad autopilot stayed awake but did not start work because {reason}. "
                f"Next self-check is in {next_check_seconds} second(s)."
            ),
        }

    def _next_loop_delay(self, last_report: Dict[str, Any], max_delay: int) -> int:
        decision = last_report.get("decision") or {}
        try:
            proposed = int(decision.get("next_check_seconds") or max_delay)
        except (TypeError, ValueError):
            proposed = max_delay
        return max(1, min(max_delay, proposed))

    def _process_service_queue(self, limit: int, approval: str) -> Dict[str, Any]:
        listing = self.agent.service_desk.list_tasks(limit=limit)
        tasks = listing.get("tasks") or []
        worked: list[str] = []
        draft_ready: list[str] = []
        awaiting_payment: list[str] = []
        stale_invalid: list[str] = []
        review_needed: list[str] = []
        payment_followups: list[Dict[str, Any]] = []

        for task in tasks:
            status = str(task.get("status") or "")
            task_id = str(task.get("task_id") or "")
            if not task_id:
                continue
            if status == "paid":
                result = self.agent.service_desk.work_task(task_id=task_id, approval=approval)
                worked.append(((result.get("task") or {}).get("task_id")) or task_id)
            elif status == "draft_ready":
                draft_ready.append(task_id)
            elif status == "awaiting_payment":
                if self._awaiting_payment_task_is_stale_invalid(task):
                    result = self._mark_stale_invalid_task(task)
                    stale_invalid.append(((result.get("task") or {}).get("task_id")) or task_id)
                    continue
                awaiting_payment.append(task_id)
                if hasattr(self.agent.service_desk, "payment_followup"):
                    try:
                        followup = self.agent.service_desk.payment_followup(task_id)
                        if isinstance(followup, dict) and followup.get("ok"):
                            followup["requester_agent"] = str(task.get("requester_agent") or "")
                            followup["callback_url"] = str(task.get("callback_url") or "")
                            followup["metadata"] = task.get("metadata") or {}
                            followup["problem"] = str(task.get("problem") or "")
                            followup["task_status"] = status
                            payment_followups.append(followup)
                    except Exception:
                        pass
            elif status in {"manual_payment_review", "payment_unverified"}:
                review_needed.append(task_id)

        return {
            "listing": listing,
            "worked_task_ids": worked,
            "draft_ready_task_ids": draft_ready,
            "awaiting_payment_task_ids": awaiting_payment,
            "stale_invalid_task_ids": stale_invalid,
            "payment_followups": payment_followups[:5],
            "review_needed_task_ids": review_needed,
            "analysis": (
                f"Service queue processed: worked {len(worked)}, draft_ready {len(draft_ready)}, "
                f"awaiting_payment {len(awaiting_payment)}, stale_invalid {len(stale_invalid)}, "
                f"review_needed {len(review_needed)}."
            ),
        }

    @staticmethod
    def _awaiting_payment_task_is_stale_invalid(task: Dict[str, Any]) -> bool:
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        payment = task.get("payment") if isinstance(task.get("payment"), dict) else {}
        candidates = [
            task.get("callback_url"),
            task.get("requester_wallet"),
            payment.get("tx_hash"),
            task.get("tx_hash"),
            metadata.get("requester_endpoint"),
            metadata.get("endpoint_url"),
            metadata.get("callback_url"),
            metadata.get("tx_hash"),
        ]
        return not any(str(item or "").strip() for item in candidates)

    def _mark_stale_invalid_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_id = str(task.get("task_id") or "")
        reason = (
            "Awaiting-payment task has no requester endpoint, callback, wallet, or tx hash; "
            "it is treated as invalid lead ballast so Nomad can look for real jobs."
        )
        if task_id and hasattr(self.agent.service_desk, "mark_stale_invalid"):
            try:
                return self.agent.service_desk.mark_stale_invalid(task_id, reason=reason)
            except Exception:
                pass
        return {
            "ok": False,
            "task": {"task_id": task_id, "status": "stale_invalid", "invalid_reason": reason},
        }

    def _run_mutual_aid_evolution(
        self,
        lead_conversion: Dict[str, Any],
        contact_poll: Dict[str, Any],
        reply_conversion: Dict[str, Any],
        objective: str,
    ) -> Dict[str, Any]:
        mutual_aid = getattr(self.agent, "mutual_aid", None)
        if not mutual_aid or not hasattr(mutual_aid, "learn_from_autopilot_cycle"):
            return {
                "mode": "nomad_mutual_aid",
                "ok": True,
                "skipped": True,
                "reason": "mutual_aid_unavailable",
            }
        return mutual_aid.learn_from_autopilot_cycle(
            lead_conversion=lead_conversion,
            contact_poll=contact_poll,
            reply_conversion=reply_conversion,
            objective=objective,
        )

    def _run_swarm_accumulation(
        self,
        lead_conversion: Dict[str, Any],
        outreach_summary: Dict[str, Any],
        public_api_url: str,
    ) -> Dict[str, Any]:
        registry = getattr(self.agent, "swarm_registry", None)
        if not registry or not hasattr(registry, "accumulate_agents"):
            return {
                "mode": "nomad_swarm_accumulation",
                "schema": "nomad.swarm_accumulation.v1",
                "ok": True,
                "skipped": True,
                "reason": "swarm_registry_accumulator_unavailable",
                "analysis": "Swarm accumulation skipped because no accumulating swarm registry is attached.",
            }
        base_url = public_api_url if self._is_public_service_url(public_api_url) else "http://127.0.0.1:8787"
        focus = (
            self._focus_from_lead_conversion(lead_conversion)
            or str(outreach_summary.get("service_type_focus") or "").strip()
            or self.default_outreach_service_type
        )
        contacts = self._list_agent_contacts_for_accumulation()
        campaigns = []
        campaign = outreach_summary.get("campaign") if isinstance(outreach_summary.get("campaign"), dict) else {}
        if campaign:
            campaigns.append(campaign)
        leads = [
            conversion.get("lead") or {}
            for conversion in (lead_conversion.get("conversions") or [])
            if isinstance(conversion, dict)
        ]
        try:
            return registry.accumulate_agents(
                contacts=contacts,
                campaigns=campaigns,
                leads=leads,
                base_url=base_url.rstrip("/"),
                focus_pain_type=focus,
            )
        except Exception as exc:
            return {
                "mode": "nomad_swarm_accumulation",
                "schema": "nomad.swarm_accumulation.v1",
                "ok": False,
                "skipped": True,
                "reason": "swarm_accumulation_failed",
                "error": str(exc),
                "analysis": f"Swarm accumulation failed: {exc}",
            }

    def _run_swarm_coordination(
        self,
        self_improvement: Dict[str, Any],
        lead_conversion: Dict[str, Any],
        outreach_summary: Dict[str, Any],
        public_api_url: str,
    ) -> Dict[str, Any]:
        registry = getattr(self.agent, "swarm_registry", None)
        if not registry or not hasattr(registry, "coordination_board"):
            return {
                "mode": "nomad_swarm_coordination",
                "schema": "nomad.swarm_coordination_board.v1",
                "skipped": True,
                "reason": "swarm_registry_unavailable",
                "analysis": "Swarm coordination skipped because no swarm registry is attached to this agent.",
            }
        base_url = public_api_url if self._is_public_service_url(public_api_url) else "http://127.0.0.1:8787"
        focus = (
            self._preferred_outreach_service_type(self_improvement, include_default=False)
            or self._focus_from_lead_conversion(lead_conversion)
            or str(outreach_summary.get("service_type_focus") or "").strip()
            or self.default_outreach_service_type
        )
        try:
            board = registry.coordination_board(
                base_url=base_url.rstrip("/"),
                focus_pain_type=focus,
            )
        except Exception as exc:
            return {
                "mode": "nomad_swarm_coordination",
                "schema": "nomad.swarm_coordination_board.v1",
                "skipped": True,
                "reason": "coordination_board_failed",
                "error": str(exc),
                "analysis": f"Swarm coordination failed: {exc}",
            }
        board["autopilot_focus"] = focus
        board["autopilot_safe_to_publish"] = self._is_public_service_url(public_api_url)
        board["analysis"] = (
            "Autopilot refreshed the swarm coordination board. "
            f"Next safe coordination action: {board.get('next_best_action', '')}"
        )
        return board

    def _list_agent_contacts_for_accumulation(self) -> list[Dict[str, Any]]:
        contacts_api = getattr(self.agent, "agent_contacts", None)
        if not contacts_api or not hasattr(contacts_api, "list_contacts"):
            return []
        try:
            listing = contacts_api.list_contacts(limit=100)
        except TypeError:
            try:
                listing = contacts_api.list_contacts(statuses=None, limit=100)
            except Exception:
                return []
        except Exception:
            return []
        contacts = listing.get("contacts") if isinstance(listing, dict) else []
        return [item for item in (contacts or []) if isinstance(item, dict)]

    def _convert_replies_to_service_tasks(self, contact_poll: Dict[str, Any]) -> Dict[str, Any]:
        replies = contact_poll.get("reply_summaries") or []
        state = self._load()
        already_converted = set(state.get("converted_reply_contact_ids") or [])
        converted_contact_ids: list[str] = []
        created_task_ids: list[str] = []
        skipped_contact_ids: list[str] = []
        errors: list[Dict[str, str]] = []
        if not hasattr(self.agent.service_desk, "create_task"):
            return {
                "mode": "autopilot_reply_conversion",
                "ok": True,
                "skipped": True,
                "reason": "service_desk_create_task_unavailable",
                "converted_contact_ids": [],
                "created_task_ids": [],
            }
        for reply in replies:
            contact_id = str(reply.get("contact_id") or "")
            if not contact_id or contact_id in already_converted:
                continue
            reply_text = str(reply.get("reply_text") or "")
            budget = self._optional_float(reply.get("budget_native"))
            plan_accepted = "PLAN_ACCEPTED=true" in reply_text or "plan_accepted=true" in reply_text.lower()
            # CodeBuddy intent analysis — gated, non-blocking, may skip declined replies
            try:
                from nomad_codebuddy import _env_flag, CODEBUDDY_BRAIN_ENABLED_ENV, CodeBuddyBrainProvider
                if reply_text and _env_flag(CODEBUDDY_BRAIN_ENABLED_ENV, default=False):
                    intent_result = CodeBuddyBrainProvider().analyze_reply_intent(reply_text)
                    if intent_result.get("ok") and intent_result.get("content"):
                        for line in intent_result["content"].splitlines():
                            if ":" not in line:
                                continue
                            key, val = line.split(":", 1)
                            if key.strip().lower() == "intent" and val.strip().lower() == "declined":
                                skipped_contact_ids.append(contact_id)
                                break
                        else:
                            pass  # intent not declined, continue normal flow
                        # Re-check if we just appended contact_id as skipped
                        if contact_id in skipped_contact_ids:
                            continue
            except Exception:
                pass  # brain enrichment is optional, never blocks reply conversion
            if budget is None and not plan_accepted:
                skipped_contact_ids.append(contact_id)
                continue
            requester = str(reply.get("title") or reply.get("endpoint_url") or "a2a-agent").strip()
            service_type = str(reply.get("classification") or self.default_outreach_service_type or "custom").strip()
            problem = (
                f"A2A reply from {requester}: {reply_text[:700]} "
                "Nomad task: convert accepted need into a bounded paid service task."
            ).strip()
            try:
                result = self.agent.service_desk.create_task(
                    problem=problem,
                    requester_agent=requester,
                    service_type=service_type,
                    budget_native=budget,
                    metadata={
                        "source": "autopilot_a2a_reply_conversion",
                        "contact_id": contact_id,
                        "endpoint_url": str(reply.get("endpoint_url") or ""),
                        "plan_accepted": plan_accepted,
                    },
                )
                task_id = ((result.get("task") or {}).get("task_id")) or ""
                if task_id:
                    converted_contact_ids.append(contact_id)
                    created_task_ids.append(task_id)
                    already_converted.add(contact_id)
            except Exception as exc:
                errors.append({"contact_id": contact_id, "error": str(exc)})
        return {
            "mode": "autopilot_reply_conversion",
            "ok": not errors,
            "converted_contact_ids": converted_contact_ids,
            "created_task_ids": created_task_ids,
            "skipped_contact_ids": skipped_contact_ids,
            "errors": errors,
            "analysis": (
                f"Converted {len(converted_contact_ids)} A2A reply/replies into service task(s); "
                f"skipped {len(skipped_contact_ids)} without PLAN_ACCEPTED or budget."
            ),
        }

    def _queue_payment_followups(
        self,
        service_summary: Dict[str, Any],
        limit: int,
        enabled: bool,
    ) -> Dict[str, Any]:
        followups = service_summary.get("payment_followups") or []
        cap = max(0, int(limit or 0))
        if cap <= 0:
            return {
                "mode": "autopilot_payment_followup_queue",
                "ok": True,
                "queued_contact_ids": [],
                "duplicate_contact_ids": [],
                "blocked_task_ids": [],
                "skipped_task_ids": [],
                "skipped_reasons": {},
                "analysis": "Payment follow-up queue skipped because the follow-up limit is zero.",
                "reason": "payment_followup_limit_zero",
                "skipped": True,
            }
        if not enabled:
            return {
                "mode": "autopilot_payment_followup_queue",
                "ok": True,
                "queued_contact_ids": [],
                "duplicate_contact_ids": [],
                "blocked_task_ids": [],
                "skipped_task_ids": [str(item.get("task_id") or "") for item in followups[:cap] if item.get("task_id")],
                "skipped_reasons": {"send_disabled_or_public_url_missing": len(followups[:cap])},
                "analysis": "Payment follow-up queue skipped because autonomous A2A sending is disabled or Nomad is not public.",
                "reason": "send_disabled_or_public_url_missing",
                "skipped": True,
            }
        if not hasattr(self.agent.agent_contacts, "queue_contact"):
            return {
                "mode": "autopilot_payment_followup_queue",
                "ok": True,
                "queued_contact_ids": [],
                "duplicate_contact_ids": [],
                "blocked_task_ids": [],
                "skipped_task_ids": [str(item.get("task_id") or "") for item in followups[:cap] if item.get("task_id")],
                "skipped_reasons": {"queue_contact_unavailable": len(followups[:cap])},
                "analysis": "Payment follow-up queue skipped because the contact outbox cannot queue new contacts here.",
                "reason": "queue_contact_unavailable",
                "skipped": True,
            }

        state = self._load()
        stored_log = state.get("payment_followup_log")
        if isinstance(stored_log, dict):
            self._payment_followup_log = dict(stored_log)
        queued_contact_ids: list[str] = []
        duplicate_contact_ids: list[str] = []
        blocked_task_ids: list[str] = []
        skipped_task_ids: list[str] = []
        skipped_reasons: Dict[str, int] = {}
        now = datetime.now(UTC)

        for followup in followups[:cap]:
            task_id = str(followup.get("task_id") or "")
            if not task_id:
                continue
            endpoint_url = self._payment_followup_endpoint(followup)
            if not endpoint_url:
                skipped_task_ids.append(task_id)
                skipped_reasons["requester_endpoint_missing"] = skipped_reasons.get("requester_endpoint_missing", 0) + 1
                continue
            if not self._payment_followup_due(task_id=task_id, now=now):
                skipped_task_ids.append(task_id)
                skipped_reasons["recent_followup_exists"] = skipped_reasons.get("recent_followup_exists", 0) + 1
                continue
            result = self.agent.agent_contacts.queue_contact(
                endpoint_url=endpoint_url,
                problem=self._payment_followup_problem(followup),
                service_type="wallet_payment",
                lead=self._payment_followup_lead(followup),
                budget_hint_native=self._payment_followup_budget_hint(followup),
            )
            if result.get("ok"):
                contact = result.get("contact") or {}
                contact_id = str(contact.get("contact_id") or "")
                self._payment_followup_log[task_id] = {
                    "queued_at": now.isoformat(),
                    "contact_id": contact_id,
                    "endpoint_url": endpoint_url,
                    "count": int((self._payment_followup_log.get(task_id) or {}).get("count") or 0) + 1,
                }
                if result.get("duplicate"):
                    duplicate_contact_ids.append(contact_id or task_id)
                else:
                    queued_contact_ids.append(contact_id or task_id)
            else:
                blocked_task_ids.append(task_id)
                reason = str(result.get("reason") or "queue_blocked")
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1

        return {
            "mode": "autopilot_payment_followup_queue",
            "ok": True,
            "queued_contact_ids": queued_contact_ids,
            "duplicate_contact_ids": duplicate_contact_ids,
            "blocked_task_ids": blocked_task_ids,
            "skipped_task_ids": skipped_task_ids,
            "skipped_reasons": skipped_reasons,
            "analysis": (
                f"Payment follow-up queue prepared {len(queued_contact_ids)} contact(s), "
                f"duplicates {len(duplicate_contact_ids)}, blocked {len(blocked_task_ids)}, skipped {len(skipped_task_ids)}."
            ),
        }

    def _queue_agent_followups(
        self,
        contact_poll: Dict[str, Any],
        limit: int,
        enabled: bool,
    ) -> Dict[str, Any]:
        replies = contact_poll.get("reply_summaries") or []
        cap = max(0, int(limit or 0))
        if cap <= 0:
            return {
                "mode": "autopilot_agent_followup_queue",
                "ok": True,
                "queued_contact_ids": [],
                "duplicate_contact_ids": [],
                "blocked_contact_ids": [],
                "skipped_contact_ids": [],
                "skipped_reasons": {},
                "analysis": "Agent follow-up queue skipped because the follow-up limit is zero.",
                "reason": "agent_followup_limit_zero",
                "skipped": True,
            }
        if not enabled:
            return {
                "mode": "autopilot_agent_followup_queue",
                "ok": True,
                "queued_contact_ids": [],
                "duplicate_contact_ids": [],
                "blocked_contact_ids": [],
                "skipped_contact_ids": [str(item.get("contact_id") or "") for item in replies[:cap] if item.get("contact_id")],
                "skipped_reasons": {"send_disabled_or_public_url_missing": len(replies[:cap])},
                "analysis": "Agent follow-up queue skipped because autonomous A2A sending is disabled or Nomad is not public.",
                "reason": "send_disabled_or_public_url_missing",
                "skipped": True,
            }
        if not hasattr(self.agent.agent_contacts, "queue_contact"):
            return {
                "mode": "autopilot_agent_followup_queue",
                "ok": True,
                "queued_contact_ids": [],
                "duplicate_contact_ids": [],
                "blocked_contact_ids": [],
                "skipped_contact_ids": [str(item.get("contact_id") or "") for item in replies[:cap] if item.get("contact_id")],
                "skipped_reasons": {"queue_contact_unavailable": len(replies[:cap])},
                "analysis": "Agent follow-up queue skipped because the contact outbox cannot queue new contacts here.",
                "reason": "queue_contact_unavailable",
                "skipped": True,
            }

        state = self._load()
        stored_log = state.get("agent_followup_log")
        if isinstance(stored_log, dict):
            self._agent_followup_log = dict(stored_log)
        queued_contact_ids: list[str] = []
        duplicate_contact_ids: list[str] = []
        blocked_contact_ids: list[str] = []
        skipped_contact_ids: list[str] = []
        skipped_reasons: Dict[str, int] = {}
        now = datetime.now(UTC)

        for reply in replies[:cap]:
            contact_id = str(reply.get("contact_id") or "")
            if not contact_id:
                continue
            if not bool(reply.get("followup_should_queue")):
                skipped_contact_ids.append(contact_id)
                skipped_reasons["customer_or_no_followup"] = skipped_reasons.get("customer_or_no_followup", 0) + 1
                continue
            endpoint_url = str(reply.get("endpoint_url") or "")
            if not endpoint_url:
                skipped_contact_ids.append(contact_id)
                skipped_reasons["requester_endpoint_missing"] = skipped_reasons.get("requester_endpoint_missing", 0) + 1
                continue
            if not self._agent_followup_due(contact_id=contact_id, now=now):
                skipped_contact_ids.append(contact_id)
                skipped_reasons["recent_followup_exists"] = skipped_reasons.get("recent_followup_exists", 0) + 1
                continue
            result = self.agent.agent_contacts.queue_contact(
                endpoint_url=endpoint_url,
                problem=self._agent_followup_problem(reply),
                service_type=str(reply.get("service_type") or reply.get("classification") or self.default_outreach_service_type or "custom").strip(),
                lead=self._agent_followup_lead(reply),
                budget_hint_native=self._optional_float(reply.get("budget_native")),
                allow_duplicate=True,
            )
            if result.get("ok"):
                contact = result.get("contact") or {}
                queued_id = str(contact.get("contact_id") or contact_id)
                self._agent_followup_log[contact_id] = {
                    "queued_at": now.isoformat(),
                    "contact_id": queued_id,
                    "endpoint_url": endpoint_url,
                    "count": int((self._agent_followup_log.get(contact_id) or {}).get("count") or 0) + 1,
                    "role": str(reply.get("agent_role") or ""),
                }
                if result.get("duplicate"):
                    duplicate_contact_ids.append(queued_id)
                else:
                    queued_contact_ids.append(queued_id)
            else:
                blocked_contact_ids.append(contact_id)
                reason = str(result.get("reason") or "queue_blocked")
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1

        return {
            "mode": "autopilot_agent_followup_queue",
            "ok": True,
            "queued_contact_ids": queued_contact_ids,
            "duplicate_contact_ids": duplicate_contact_ids,
            "blocked_contact_ids": blocked_contact_ids,
            "skipped_contact_ids": skipped_contact_ids,
            "skipped_reasons": skipped_reasons,
            "analysis": (
                f"Agent follow-up queue prepared {len(queued_contact_ids)} contact(s), "
                f"duplicates {len(duplicate_contact_ids)}, blocked {len(blocked_contact_ids)}, skipped {len(skipped_contact_ids)}."
            ),
        }

    def _send_payment_followups(
        self,
        payment_followup_queue: Dict[str, Any],
        *,
        enabled: bool,
    ) -> Dict[str, Any]:
        queued_ids = [
            str(item)
            for item in (payment_followup_queue.get("queued_contact_ids") or [])
            if str(item or "").strip()
        ]
        sent_ids: list[str] = []
        failed_ids: list[str] = []
        if not queued_ids:
            return {
                "mode": "autopilot_payment_followup_send",
                "ok": True,
                "sent_contact_ids": [],
                "failed_contact_ids": [],
                "skipped": True,
                "reason": "no_payment_followups_queued",
                "analysis": "No payment follow-up contacts were queued for sending.",
            }
        if not enabled:
            return {
                "mode": "autopilot_payment_followup_send",
                "ok": True,
                "sent_contact_ids": [],
                "failed_contact_ids": [],
                "skipped": True,
                "reason": "payment_followup_send_disabled_or_public_url_missing",
                "analysis": (
                    f"{len(queued_ids)} payment follow-up contact(s) were queued, "
                    "but payment sending is disabled or Nomad has no public service URL."
                ),
            }
        if not hasattr(self.agent.agent_contacts, "send_contact"):
            return {
                "mode": "autopilot_payment_followup_send",
                "ok": False,
                "sent_contact_ids": [],
                "failed_contact_ids": queued_ids,
                "skipped": True,
                "reason": "send_contact_unavailable",
                "analysis": "Payment follow-up sending failed because the contact outbox cannot send contacts here.",
            }

        for contact_id in queued_ids:
            try:
                result = self.agent.agent_contacts.send_contact(contact_id)
            except Exception:
                failed_ids.append(contact_id)
                continue
            status = ((result.get("contact") or {}).get("status")) or ""
            if status == "sent":
                sent_ids.append(contact_id)
            else:
                failed_ids.append(contact_id)
        return {
            "mode": "autopilot_payment_followup_send",
            "ok": not failed_ids,
            "sent_contact_ids": sent_ids,
            "failed_contact_ids": failed_ids,
            "analysis": (
                f"Payment follow-up send processed {len(queued_ids)} money contact(s): "
                f"sent {len(sent_ids)}, failed {len(failed_ids)}."
            ),
        }

    def _flush_contact_queue(self, limit: int, send_enabled: bool) -> Dict[str, Any]:
        queued_listing = self.agent.agent_contacts.list_contacts(statuses=["queued"], limit=limit)
        queued_contacts = queued_listing.get("contacts") or []
        sent_ids: list[str] = []
        failed_ids: list[str] = []
        if not send_enabled:
            return {
                "queued_listing": queued_listing,
                "sent_contact_ids": sent_ids,
                "failed_contact_ids": failed_ids,
                "skipped": True,
                "reason": "autonomous_send_disabled",
                "analysis": (
                    f"Contact queue has {len(queued_contacts)} queued contact(s), but autonomous sending is disabled."
                ),
            }
        for contact in queued_contacts[: max(0, int(limit or 0))]:
            contact_id = str(contact.get("contact_id") or "")
            if not contact_id:
                continue
            result = self.agent.agent_contacts.send_contact(contact_id)
            status = ((result.get("contact") or {}).get("status")) or ""
            if status == "sent":
                sent_ids.append(contact_id)
            else:
                failed_ids.append(contact_id)
        return {
            "queued_listing": queued_listing,
            "sent_contact_ids": sent_ids,
            "failed_contact_ids": failed_ids,
            "analysis": (
                f"Contact queue flush processed {len(queued_contacts)} queued contact(s): "
                f"sent {len(sent_ids)}, failed {len(failed_ids)}."
            ),
        }

    def _poll_contact_updates(self, limit: int) -> Dict[str, Any]:
        sent_listing = self.agent.agent_contacts.list_contacts(statuses=["sent"], limit=limit)
        sent_contacts = sent_listing.get("contacts") or []
        polled_ids: list[str] = []
        replied_ids: list[str] = []
        completed_ids: list[str] = []
        failed_ids: list[str] = []
        reply_summaries: list[Dict[str, str]] = []
        for contact in sent_contacts[: max(0, int(limit or 0))]:
            contact_id = str(contact.get("contact_id") or "")
            if not contact_id:
                continue
            result = self.agent.agent_contacts.poll_contact(contact_id)
            polled_ids.append(contact_id)
            updated = result.get("contact") or {}
            status = str(updated.get("status") or "")
            if status == "replied":
                replied_ids.append(contact_id)
                reply = updated.get("last_reply") or {}
                normalized = reply.get("normalized") or {}
                role_assessment = reply.get("role_assessment") or updated.get("reply_role_assessment") or {}
                followup = reply.get("followup") or updated.get("followup_recommendation") or {}
                reply_summaries.append(
                    {
                        "contact_id": contact_id,
                        "title": str((updated.get("lead") or {}).get("title") or ""),
                        "endpoint_url": str(updated.get("endpoint_url") or ""),
                        "reply_text": str(reply.get("text") or "")[:240],
                        "classification": str(normalized.get("classification") or ""),
                        "service_type": str(updated.get("service_type") or normalized.get("classification") or ""),
                        "agent_role": str(role_assessment.get("role") or ""),
                        "followup_next_path": str(followup.get("next_path") or ""),
                        "followup_message": str(followup.get("message") or updated.get("followup_message") or ""),
                        "followup_should_queue": bool(updated.get("followup_ready")),
                        "next_step": str(normalized.get("next_step") or ""),
                        "budget_native": str(normalized.get("budget_native") or ""),
                    }
                )
            elif status == "completed":
                completed_ids.append(contact_id)
            elif status in {"poll_failed", "remote_failed", "remote_canceled", "remote_rejected"}:
                failed_ids.append(contact_id)
        return {
            "sent_listing": sent_listing,
            "polled_contact_ids": polled_ids,
            "replied_contact_ids": replied_ids,
            "completed_contact_ids": completed_ids,
            "failed_contact_ids": failed_ids,
            "reply_summaries": reply_summaries[:5],
            "analysis": (
                f"Contact poll processed {len(sent_contacts)} sent contact(s): "
                f"replied {len(replied_ids)}, completed {len(completed_ids)}, failed {len(failed_ids)}."
            ),
        }

    def _run_outreach(
        self,
        self_improvement: Dict[str, Any],
        limit: int,
        explicit_query: str,
        send_outreach: bool,
        blocked_reason: str = "",
    ) -> Dict[str, Any]:
        public_api_url = preferred_public_base_url()
        service_type = self._preferred_outreach_service_type(self_improvement)
        query = self._select_outreach_query(
            explicit_query=explicit_query,
            self_improvement=self_improvement,
            service_type=service_type,
        )
        if limit <= 0:
            return {
                "mode": "agent_cold_outreach_campaign",
                "deal_found": False,
                "ok": True,
                "skipped": True,
                "reason": "outreach_limit_zero",
                "query": query,
                "service_type_focus": service_type,
                "analysis": "Outreach skipped because the per-cycle outreach limit is zero.",
            }
        if blocked_reason:
            return {
                "mode": "agent_cold_outreach_campaign",
                "deal_found": False,
                "ok": True,
                "skipped": True,
                "reason": blocked_reason,
                "query": query,
                "service_type_focus": service_type,
                "analysis": "Outreach skipped by all-surfaces contract-first enforcement.",
            }
        if send_outreach and not self._is_public_service_url(public_api_url):
            return {
                "mode": "agent_cold_outreach_campaign",
                "deal_found": False,
                "ok": False,
                "skipped": True,
                "reason": "public_api_url_required",
                "query": query,
                "service_type_focus": service_type,
                "analysis": (
                    "Outreach send is disabled because NOMAD_PUBLIC_API_URL is empty or still points to localhost. "
                    "Nomad should expose /service, /tasks and /x402 endpoints before cold outreach."
                ),
            }
        result = self.agent.agent_campaigns.create_campaign_from_discovery(
            limit=limit,
            query=query,
            send=send_outreach,
            service_type=service_type,
        )
        result["autopilot_query"] = query
        result["service_type_focus"] = service_type
        return result

    def _run_lead_conversion(
        self,
        self_improvement: Dict[str, Any],
        limit: int,
        explicit_query: str,
        send_a2a: bool,
        blocked_reason: str = "",
    ) -> Dict[str, Any]:
        cap = max(0, int(limit or 0))
        if cap <= 0:
            return {
                "mode": "lead_conversion_pipeline",
                "deal_found": False,
                "ok": True,
                "skipped": True,
                "reason": "conversion_limit_zero",
                "analysis": "Lead conversion skipped because conversion limit is zero.",
            }
        if blocked_reason:
            return {
                "mode": "lead_conversion_pipeline",
                "deal_found": False,
                "ok": True,
                "skipped": True,
                "reason": blocked_reason,
                "analysis": "Lead conversion skipped by all-surfaces contract-first enforcement.",
            }
        public_api_url = preferred_public_base_url()
        effective_send = bool(send_a2a and self._is_public_service_url(public_api_url))
        lead_scout = self_improvement.get("lead_scout") or {}
        leads = self._conversion_leads_from_cycle(lead_scout, limit=cap)
        query = self._select_conversion_query(
            explicit_query=explicit_query,
            self_improvement=self_improvement,
        )
        if not hasattr(self.agent, "lead_conversion"):
            return {
                "mode": "lead_conversion_pipeline",
                "deal_found": False,
                "ok": False,
                "skipped": True,
                "reason": "lead_conversion_unavailable",
                "analysis": "Lead conversion is unavailable on this agent instance.",
            }
        result = self.agent.lead_conversion.run(
            query=query,
            limit=cap,
            send=effective_send,
            leads=leads if leads else None,
        )
        result["autopilot_query"] = query
        result["send_requested"] = bool(send_a2a)
        result["send_enabled"] = effective_send
        if send_a2a and not effective_send:
            result["send_blocked_reason"] = "public_api_url_required"
        result["cycle_lead_count"] = len(leads)
        return result

    def _run_product_factory(
        self,
        lead_conversion: Dict[str, Any],
        self_improvement: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        product_factory = getattr(self.agent, "product_factory", None)
        if not product_factory or not hasattr(product_factory, "run"):
            return {
                "mode": "nomad_product_factory",
                "deal_found": False,
                "ok": True,
                "skipped": True,
                "reason": "product_factory_unavailable",
                "analysis": "Productization skipped because product_factory is unavailable.",
            }
        conversions = list(lead_conversion.get("conversions") or [])
        patterns = list(((self_improvement or {}).get("high_value_patterns") or {}).get("patterns") or [])
        if not conversions and not patterns:
            return {
                "mode": "nomad_product_factory",
                "deal_found": False,
                "ok": True,
                "skipped": True,
                "reason": "no_productization_sources",
                "analysis": "Productization skipped because this cycle created no lead conversions or reusable high-value patterns.",
            }
        return product_factory.run(
            conversions=conversions,
            high_value_patterns=patterns or None,
            limit=max(len(conversions), len(patterns), 1),
        )

    def _run_lead_workbench(self, limit: int = 5) -> Dict[str, Any]:
        workbench = getattr(self.agent, "lead_workbench", None)
        if not workbench or not hasattr(workbench, "status"):
            return {
                "mode": "nomad_lead_workbench",
                "schema": "nomad.lead_workbench.v1",
                "ok": True,
                "skipped": True,
                "reason": "lead_workbench_unavailable",
                "analysis": "Lead workbench skipped because it is unavailable.",
            }
        try:
            return workbench.status(limit=limit, work=True)
        except Exception as exc:
            return {
                "mode": "nomad_lead_workbench",
                "schema": "nomad.lead_workbench.v1",
                "ok": False,
                "skipped": True,
                "reason": "lead_workbench_failed",
                "error": str(exc),
                "analysis": f"Lead workbench failed: {exc}",
            }

    def _daily_quota(self, target: int) -> Dict[str, Any]:
        today = datetime.now().astimezone().date().isoformat()
        state = self._load()
        previous = state.get("daily_a2a_quota") if isinstance(state.get("daily_a2a_quota"), dict) else {}
        if previous.get("date") != today:
            previous = {}
        prepared_count = max(0, int(previous.get("prepared_count") or 0))
        sent_count = max(0, int(previous.get("sent_count") or 0))
        target = max(0, int(target or 0))
        return {
            "date": today,
            "target": target,
            "prepared_count": min(prepared_count, target),
            "sent_count": min(sent_count, target),
            "remaining_to_prepare": max(0, target - prepared_count),
            "remaining_to_send": max(0, target - sent_count),
        }

    def _daily_quota_after(
        self,
        start: Dict[str, Any],
        contact_summary: Dict[str, Any],
        lead_conversion: Dict[str, Any],
        outreach_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        lead_delta = self._lead_conversion_contact_delta(lead_conversion)
        outreach_delta = self._outreach_contact_delta(outreach_summary)
        prepared_delta = lead_delta["prepared"] + outreach_delta["prepared"]
        sent_delta = (
            self._sent_from_contact_queue(contact_summary)
            + lead_delta["sent"]
            + outreach_delta["sent"]
        )
        target = max(0, int(start.get("target") or 0))
        prepared_count = min(target, int(start.get("prepared_count") or 0) + prepared_delta)
        sent_count = min(target, int(start.get("sent_count") or 0) + sent_delta)
        return {
            "date": start.get("date") or datetime.now().astimezone().date().isoformat(),
            "target": target,
            "prepared_delta": prepared_delta,
            "sent_delta": sent_delta,
            "prepared_count": prepared_count,
            "sent_count": sent_count,
            "remaining_to_prepare": max(0, target - prepared_count),
            "remaining_to_send": max(0, target - sent_count),
        }

    @staticmethod
    def _sent_from_contact_queue(contact_summary: Dict[str, Any]) -> int:
        return len(contact_summary.get("sent_contact_ids") or [])

    def _payment_followup_due(
        self,
        task_id: str,
        now: datetime,
    ) -> bool:
        entry = self._payment_followup_log.get(task_id) or {}
        queued_at = str(entry.get("queued_at") or "").strip()
        if not queued_at:
            return True
        try:
            queued_dt = datetime.fromisoformat(queued_at.replace("Z", "+00:00"))
        except ValueError:
            return True
        if queued_dt.tzinfo is None:
            queued_dt = queued_dt.replace(tzinfo=UTC)
        return now - queued_dt >= timedelta(hours=self.payment_followup_hours)

    def _agent_followup_due(
        self,
        contact_id: str,
        now: datetime,
    ) -> bool:
        entry = self._agent_followup_log.get(contact_id) or {}
        queued_at = str(entry.get("queued_at") or "").strip()
        if not queued_at:
            return True
        try:
            queued_dt = datetime.fromisoformat(queued_at.replace("Z", "+00:00"))
        except ValueError:
            return True
        if queued_dt.tzinfo is None:
            queued_dt = queued_dt.replace(tzinfo=UTC)
        return now - queued_dt >= timedelta(hours=self.agent_followup_hours)

    @staticmethod
    def _payment_followup_endpoint(followup: Dict[str, Any]) -> str:
        metadata = followup.get("metadata") or {}
        for candidate in (
            followup.get("callback_url"),
            metadata.get("requester_endpoint"),
            metadata.get("endpoint_url"),
        ):
            cleaned = str(candidate or "").strip()
            if cleaned:
                return cleaned
        return ""

    @staticmethod
    def _payment_followup_budget_hint(followup: Dict[str, Any]) -> Optional[float]:
        starter = (followup.get("starter_offer") or {}).get("amount_native")
        primary = (followup.get("primary_offer") or {}).get("amount_native")
        try:
            if starter is not None:
                return float(starter)
            if primary is not None:
                return float(primary)
        except (TypeError, ValueError):
            return None
        return None

    @staticmethod
    def _payment_followup_lead(followup: Dict[str, Any]) -> Dict[str, Any]:
        requester = str(followup.get("requester_agent") or "requesting-agent").strip()
        service_type = str(followup.get("service_type") or "custom").strip()
        task_id = str(followup.get("task_id") or "").strip()
        return {
            "url": f"nomad://service-task/{task_id}" if task_id else "",
            "title": requester,
            "pain": f"awaiting payment for {service_type}",
            "buyer_fit": "warm",
            "buyer_intent_terms": ["payment_followup", service_type, "starter_offer"],
        }

    @staticmethod
    def _payment_followup_problem(followup: Dict[str, Any]) -> str:
        machine_message = str(followup.get("machine_message") or "").strip()
        if machine_message:
            return machine_message
        starter_offer = followup.get("starter_offer") or {}
        primary_offer = followup.get("primary_offer") or {}
        lines = [
            "nomad.payment_followup.v1",
            f"task_id={followup.get('task_id') or ''}",
            f"service_type={followup.get('service_type') or 'custom'}",
            f"requester={followup.get('requester_agent') or 'agent'}",
        ]
        if starter_offer:
            lines.append(f"starter_offer={starter_offer.get('title')}")
            lines.append(f"starter_amount_native={starter_offer.get('amount_native')}")
        if primary_offer:
            lines.append(f"primary_offer={primary_offer.get('title')}")
            lines.append(f"primary_amount_native={primary_offer.get('amount_native')}")
        lines.append("next_action=pay_smallest_offer_or_submit_tx_hash")
        return "\n".join(lines)

    @staticmethod
    def _agent_followup_lead(reply: Dict[str, Any]) -> Dict[str, Any]:
        requester = str(reply.get("title") or reply.get("endpoint_url") or "agent").strip()
        role = str(reply.get("agent_role") or "agent").strip()
        service_type = str(reply.get("service_type") or reply.get("classification") or "custom").strip()
        return {
            "url": f"nomad://agent-contact/{reply.get('contact_id') or ''}" if reply.get("contact_id") else "",
            "title": requester,
            "pain": f"{role} followup for {service_type}",
            "buyer_fit": "strong" if role in {"peer_solver", "reseller"} else "warm",
            "buyer_intent_terms": [role, service_type, "followup_contract"],
        }

    @staticmethod
    def _agent_followup_problem(reply: Dict[str, Any]) -> str:
        message = str(reply.get("followup_message") or "").strip()
        if message:
            return message
        lines = [
            "nomad.followup.v1",
            f"role={reply.get('agent_role') or 'agent'}",
            f"next_path={reply.get('followup_next_path') or ''}",
            "contract=surface|constraint|shared_goal|next_action",
        ]
        return "\n".join(lines)

    @staticmethod
    def _lead_conversion_contact_delta(lead_conversion: Dict[str, Any]) -> Dict[str, int]:
        stats = lead_conversion.get("stats") or {}
        queued = int(stats.get("queued_agent_contact") or 0)
        sent = int(stats.get("sent_agent_contact") or 0)
        return {
            "prepared": queued + sent,
            "sent": sent,
        }

    @staticmethod
    def _outreach_contact_delta(outreach_summary: Dict[str, Any]) -> Dict[str, int]:
        campaign = outreach_summary.get("campaign") or {}
        stats = campaign.get("stats") or {}
        queued = int(stats.get("queued") or 0)
        sent = int(stats.get("sent") or 0)
        return {
            "prepared": max(queued, sent),
            "sent": sent,
        }

    def _service_objective(self, service_summary: Dict[str, Any]) -> str:
        if service_summary.get("worked_task_ids"):
            return (
                "Learn from the freshly paid tasks Nomad just worked, improve conversion from diagnosis to paid help, "
                "and tighten the human-in-the-loop service offer."
            )
        if service_summary.get("draft_ready_task_ids"):
            return (
                "Improve the clarity and usefulness of Nomad's paid draft work products so requesters can act faster."
            )
        if service_summary.get("awaiting_payment_task_ids"):
            followups = service_summary.get("payment_followups") or []
            cheaper_starter = any(item.get("cheaper_starter_available") for item in followups)
            return (
                "Improve Nomad's outreach and task framing so more agents convert from diagnosis to wallet payment, "
                + ("while keeping the smallest starter diagnosis visible." if cheaper_starter else "and keep the payment handoff explicit.")
            )
        if service_summary.get("stale_invalid_task_ids"):
            return (
                "Ignore stale invalid payment placeholders and find real buyer-agent jobs: scout current AI-agent "
                "blockers, convert valid leads into service requests, and keep only tasks with endpoint, wallet, or tx proof."
            )
        return ""

    def _reply_objective(self, contact_poll: Dict[str, Any]) -> str:
        replies = contact_poll.get("reply_summaries") or []
        if not replies:
            return ""
        first = replies[0]
        target = first.get("title") or first.get("endpoint_url") or "the replying agent"
        classification = first.get("classification") or "the reported blocker"
        return (
            f"Convert the fresh A2A reply from {target} about {classification} into a paid service path, "
            "capture the exact pain point, and prepare the smallest next response."
        )

    def _reply_conversion_objective(self, reply_conversion: Dict[str, Any]) -> str:
        task_ids = reply_conversion.get("created_task_ids") or []
        if not task_ids:
            return ""
        return (
            f"Work the newly converted A2A service task(s) {', '.join(task_ids[:3])}: "
            "tighten the payment path, deliver free value first, and package the solution as reusable memory."
        )

    def _direct_outreach_queries_from_cycle(self, self_improvement: Dict[str, Any]) -> List[str]:
        """All outreach_queries from the self-improvement cycle (used in rotation, not only the first)."""
        lead_scout = self_improvement.get("lead_scout") or {}
        out: List[str] = []
        for query in lead_scout.get("outreach_queries") or []:
            cleaned = str(query or "").strip()
            if cleaned:
                out.append(cleaned)
        return out

    def _generic_query_from_cycle(self, self_improvement: Dict[str, Any]) -> str:
        lead_scout = self_improvement.get("lead_scout") or {}
        queries = lead_scout.get("search_queries") or []
        for query in queries:
            cleaned = str(query or "").strip()
            if cleaned and self._looks_like_outreach_query(cleaned):
                return cleaned
        return ""

    def _select_outreach_query(
        self,
        explicit_query: str,
        self_improvement: Dict[str, Any],
        service_type: str = "",
    ) -> str:
        explicit = (explicit_query or "").strip()
        if explicit:
            return explicit
        suggested = self._generic_query_from_cycle(self_improvement)
        state = self._load()
        # Cycle outreach_queries first so self-improvement lead_watch beats generic service-type defaults.
        configured = list(self._direct_outreach_queries_from_cycle(self_improvement))
        configured.extend(list(self._service_type_queries(service_type)))
        if suggested:
            configured.append(suggested)
        configured.extend(self.default_outreach_queries)
        rotation = self._dedupe_queries(configured) or [self.default_outreach_query]
        cursor = int(state.get("outreach_query_cursor") or 0)
        query = rotation[cursor % len(rotation)]
        self._outreach_query_cursor = (cursor + 1) % len(rotation)
        return query

    def _preferred_outreach_service_type(
        self,
        self_improvement: Dict[str, Any],
        include_default: bool = True,
    ) -> str:
        patterns = list(((self_improvement.get("high_value_patterns") or {}).get("patterns") or []))
        if patterns:
            pain_type = str((patterns[0] or {}).get("pain_type") or "").strip()
            if pain_type:
                return pain_type
        product_factory = getattr(self.agent, "product_factory", None)
        if product_factory and hasattr(product_factory, "list_products"):
            try:
                listing = product_factory.list_products(limit=5)
                top = listing.get("top_priority_product") or ((listing.get("products") or [None])[0] or {})
                pain_type = str((top or {}).get("pain_type") or "").strip()
                if pain_type:
                    return pain_type
            except Exception:
                pass
        return self.default_outreach_service_type if include_default else ""

    @staticmethod
    def _focus_from_lead_conversion(lead_conversion: Dict[str, Any]) -> str:
        conversions = lead_conversion.get("conversions") or []
        for conversion in conversions:
            if not isinstance(conversion, dict):
                continue
            lead = conversion.get("lead") or {}
            service_type = str(lead.get("service_type") or "").strip()
            if service_type:
                return service_type
        return ""

    def _select_conversion_query(
        self,
        explicit_query: str,
        self_improvement: Dict[str, Any],
    ) -> str:
        explicit = (explicit_query or "").strip()
        if explicit:
            return explicit
        lead_scout = self_improvement.get("lead_scout") or {}
        active_lead = lead_scout.get("active_lead") or {}
        if active_lead:
            url = active_lead.get("url") or active_lead.get("html_url") or ""
            pain = active_lead.get("pain") or active_lead.get("pain_signal") or ""
            title = active_lead.get("title") or active_lead.get("name") or "active lead"
            if url or pain:
                return f"Lead: {title} URL={url} Pain={pain}".strip()
        queries = lead_scout.get("search_queries") or []
        for query in queries:
            cleaned = str(query or "").strip()
            if cleaned:
                return cleaned
        return self.default_outreach_query

    @staticmethod
    def _conversion_leads_from_cycle(lead_scout: Dict[str, Any], limit: int) -> list[Dict[str, Any]]:
        candidates: list[Dict[str, Any]] = []
        for key in ("monetizable_leads", "addressable_leads", "compute_leads", "leads"):
            for lead in lead_scout.get(key) or []:
                if isinstance(lead, dict):
                    candidates.append(lead)
        active = lead_scout.get("active_lead") or {}
        if active:
            candidates.insert(0, active)
        deduped: list[Dict[str, Any]] = []
        seen: set[str] = set()
        for lead in candidates:
            key = str(lead.get("url") or lead.get("html_url") or lead.get("title") or lead.get("name") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(lead)
        return deduped[: max(1, int(limit or 1))]

    def _configured_outreach_queries(self) -> list[str]:
        raw = os.getenv("NOMAD_AUTOPILOT_OUTREACH_QUERIES", "")
        configured = [
            item.strip()
            for item in re.split(r"[\r\n|]+", raw)
            if item.strip()
        ]
        if configured:
            return configured
        return [
            self.default_outreach_query,
            '"agent-card.json" "rate limit" "https://"',
            '"agent-card.json" "auth" "https://"',
            '"agent-card.json" "token" "https://"',
            '"agent-card.json" "quota" "https://"',
            '"agent-card.json" "x402" "https://"',
            '"agent-card.json" "wallet" "https://"',
            '"agent-card.json" "payment" "https://"',
        ]

    @staticmethod
    def _service_type_queries(service_type: str) -> list[str]:
        mapping = {
            "compute_auth": [
                '"agent-card.json" "quota" "token" "https://"',
                '"agent-card.json" "auth" "fallback" "https://"',
            ],
            "wallet_payment": [
                '"agent-card.json" "x402" "payment" "https://"',
                '"agent-card.json" "wallet" "payment" "https://"',
            ],
            "mcp_integration": [
                '"agent-card.json" "mcp" "schema" "https://"',
                '"agent-card.json" "tool contract" "https://"',
            ],
            "human_in_loop": [
                '"agent-card.json" "approval" "captcha" "https://"',
                '"agent-card.json" "human-in-the-loop" "https://"',
            ],
            "self_improvement": [
                '"agent-card.json" "guardrail" "memory" "https://"',
                '"agent-card.json" "self-improvement" "agent" "https://"',
            ],
            "inter_agent_witness": [
                '"agent-card.json" "witness" "attestation" "https://"',
                '"agent-card.json" "mcp" "provenance" "https://"',
                '"openclaw" "mcp" "agent-card" "https://"',
                '"streamable-http" "mcp" "tools" "https://"',
                '".well-known/agent-card.json" "delegation" "https://"',
                '"jsonrpc" "mcp" "agent" "https://"',
            ],
        }
        return mapping.get(str(service_type or "").strip(), [])

    @staticmethod
    def _dedupe_queries(queries: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for raw in queries:
            cleaned = str(raw or "").strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
        return deduped

    @staticmethod
    def _looks_like_outreach_query(query: str) -> bool:
        lowered = str(query or "").strip().lower()
        return any(
            token in lowered
            for token in ("agent-card", ".well-known", "a2a", "mcp", "agent.json", "openclaw")
        )

    def _ensure_api(self) -> None:
        if self._api_thread and self._api_thread.is_alive():
            return
        self._api_thread = serve_in_thread()

    def _record(self, report: Dict[str, Any]) -> None:
        self.last_cycle_report = report
        state = self._load()
        state["run_count"] = int(state.get("run_count") or 0) + 1
        state["last_run_at"] = report.get("timestamp") or datetime.now(UTC).isoformat()
        state["last_objective"] = report.get("objective", "")
        state["last_public_api_url"] = report.get("public_api_url", "")
        state["last_service"] = self._compact_service(report.get("service") or {})
        state["last_payment_followup_queue"] = self._compact_payment_followup_queue(
            report.get("payment_followup_queue") or {}
        )
        state["last_payment_followup_send"] = self._compact_contacts(
            report.get("payment_followup_send") or {}
        )
        state["last_contact_queue"] = self._compact_contacts(report.get("contact_queue") or {})
        state["last_contact_poll"] = self._compact_contact_poll(report.get("contact_poll") or {})
        state["last_agent_followup_queue"] = self._compact_agent_followup_queue(
            report.get("agent_followup_queue") or {}
        )
        state["last_agent_followup_send"] = self._compact_contacts(report.get("agent_followup_send") or {})
        state["last_reply_conversion"] = self._compact_reply_conversion(report.get("reply_conversion") or {})
        state["last_lead_conversion"] = self._compact_lead_conversion(report.get("lead_conversion") or {})
        state["last_product_factory"] = self._compact_product_factory(report.get("product_factory") or {})
        state["last_agent_growth_pipeline"] = self._compact_agent_growth_pipeline(
            report.get("agent_growth_pipeline") or {}
        )
        state["last_lead_workbench"] = self._compact_lead_workbench(report.get("lead_workbench") or {})
        state["last_outreach"] = self._compact_outreach(report.get("outreach") or {})
        state["last_swarm_accumulation"] = self._compact_swarm_accumulation(
            report.get("swarm_accumulation") or {}
        )
        state["last_mutual_aid"] = self._compact_mutual_aid(report.get("mutual_aid") or {})
        state["last_swarm_coordination"] = self._compact_swarm_coordination(
            report.get("swarm_coordination") or {}
        )
        state["last_autonomous_development"] = self._compact_autonomous_development(
            report.get("autonomous_development") or {}
        )
        state["last_efficiency_plan"] = self._compact_efficiency_plan(report.get("efficiency_plan") or {})
        state["last_autonomy_proof"] = self._compact_autonomy_proof(report.get("autonomy_proof") or {})
        state["useless_cycle_streak"] = int((report.get("autonomy_proof") or {}).get("useless_cycle_streak") or 0)
        state["last_self_improvement"] = self._compact_self_improvement(report.get("self_improvement") or {})
        state["daily_a2a_quota"] = report.get("daily_quota") or state.get("daily_a2a_quota") or {}
        state["payment_followup_log"] = self._payment_followup_log
        state["agent_followup_log"] = self._agent_followup_log
        state["outreach_query_cursor"] = int(self._outreach_query_cursor or 0)
        converted_ids = set(state.get("converted_reply_contact_ids") or [])
        converted_ids.update(report.get("reply_conversion", {}).get("converted_contact_ids") or [])
        state["converted_reply_contact_ids"] = sorted(converted_ids)
        self._store_decision(state, report.get("decision") or {})
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _record_idle(self, report: Dict[str, Any]) -> None:
        state = self._load()
        state["idle_count"] = int(state.get("idle_count") or 0) + 1
        state["last_idle_at"] = report.get("timestamp") or datetime.now(UTC).isoformat()
        self._store_decision(state, report.get("decision") or {})
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _store_decision(state: Dict[str, Any], decision: Dict[str, Any]) -> None:
        if not decision:
            return
        state["last_decision"] = {
            "timestamp": decision.get("timestamp", ""),
            "should_start": bool(decision.get("should_start", False)),
            "reason": decision.get("reason", ""),
            "reasons": decision.get("reasons") or [],
            "next_check_seconds": decision.get("next_check_seconds", 0),
            "next_check_at": decision.get("next_check_at", ""),
            "active_compute_lanes": decision.get("active_compute_lanes") or [],
            "task_stats": decision.get("task_stats") or {},
        }
        state["next_decision_at"] = decision.get("next_check_at", "")

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {
                "run_count": 0,
                "idle_count": 0,
                "last_run_at": "",
                "last_idle_at": "",
                "last_decision": {},
                "next_decision_at": "",
                "last_objective": "",
                "last_public_api_url": "",
                "last_service": {},
                "last_payment_followup_queue": {},
                "last_payment_followup_send": {},
                "last_contact_queue": {},
                "last_contact_poll": {},
                "last_agent_followup_queue": {},
                "last_agent_followup_send": {},
                "last_reply_conversion": {},
                "last_lead_conversion": {},
                "last_product_factory": {},
                "last_agent_growth_pipeline": {},
                "last_lead_workbench": {},
                "last_outreach": {},
                "last_swarm_accumulation": {},
                "last_mutual_aid": {},
                "last_swarm_coordination": {},
                "last_autonomous_development": {},
                "last_efficiency_plan": {},
                "last_autonomy_proof": {},
                "last_self_improvement": {},
                "useless_cycle_streak": 0,
                "daily_a2a_quota": {},
                "payment_followup_log": {},
                "agent_followup_log": {},
                "outreach_query_cursor": 0,
                "converted_reply_contact_ids": [],
            }
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _analysis(
        self,
        objective: str,
        service_summary: Dict[str, Any],
        payment_followup_queue: Dict[str, Any],
        payment_followup_send: Dict[str, Any],
        contact_summary: Dict[str, Any],
        contact_poll: Dict[str, Any],
        agent_followup_queue: Dict[str, Any],
        agent_followup_send: Dict[str, Any],
        reply_conversion: Dict[str, Any],
        lead_conversion: Dict[str, Any],
        product_factory: Dict[str, Any],
        lead_workbench: Dict[str, Any],
        outreach_summary: Dict[str, Any],
        swarm_accumulation: Dict[str, Any],
        mutual_aid: Dict[str, Any],
        swarm_coordination: Dict[str, Any],
        autonomous_development: Dict[str, Any],
        self_improvement: Dict[str, Any],
        daily_quota: Dict[str, Any],
        surface_gate: Dict[str, Any],
        surface_remediation: Dict[str, Any],
        evidence_or_pay_gate: Dict[str, Any],
        evidence_remediation: Dict[str, Any],
    ) -> str:
        worked = len(service_summary.get("worked_task_ids") or [])
        drafts = len(service_summary.get("draft_ready_task_ids") or [])
        awaiting_payment = len(service_summary.get("awaiting_payment_task_ids") or [])
        stale_invalid = len(service_summary.get("stale_invalid_task_ids") or [])
        payment_followups = len(service_summary.get("payment_followups") or [])
        queued_payment_followups = len(payment_followup_queue.get("queued_contact_ids") or [])
        sent_payment_followups = len(payment_followup_send.get("sent_contact_ids") or [])
        queued_sent = len(contact_summary.get("sent_contact_ids") or [])
        queued_agent_followups = len(agent_followup_queue.get("queued_contact_ids") or [])
        sent_agent_followups = len(agent_followup_send.get("sent_contact_ids") or [])
        replied = len(contact_poll.get("replied_contact_ids") or [])
        polled = len(contact_poll.get("polled_contact_ids") or [])
        converted = len(reply_conversion.get("created_task_ids") or [])
        conversion_stats = lead_conversion.get("stats") or {}
        product_count = int(product_factory.get("product_count") or 0)
        lead_worked = int(lead_workbench.get("worked_count") or 0)
        outreach_campaign = (outreach_summary.get("campaign") or {})
        outreach_stats = outreach_campaign.get("stats") or {}
        compute_watch = self_improvement.get("compute_watch") or {}
        lead_scout = self_improvement.get("lead_scout") or {}
        high_value_patterns = (self_improvement.get("high_value_patterns") or {}).get("patterns") or []
        top_high_value_pattern = high_value_patterns[0] if high_value_patterns else {}
        lead_count = len(lead_scout.get("leads") or [])
        analysis = (
            f"Nomad autopilot ran objective '{objective}'. "
            f"Service: worked {worked}, draft_ready {drafts}, awaiting_payment {awaiting_payment}, stale_invalid {stale_invalid}. "
            f"Payment follow-ups prepared {payment_followups}. "
            f"Payment follow-up contacts queued {queued_payment_followups} and sent {sent_payment_followups}. "
            f"Queue flush sent {queued_sent} queued contact(s). "
            f"Contact poll checked {polled} sent contact(s) and found {replied} reply/replies. "
            f"Agent follow-up queue prepared {queued_agent_followups} role-specific contact(s) and sent {sent_agent_followups}. "
            f"Reply conversion created {converted} paid-task candidate(s). "
            f"Lead conversion prepared {sum(int(v) for v in conversion_stats.values()) if conversion_stats else 0} conversion artifact(s). "
            f"Product factory built {product_count} product offer(s). "
            f"Lead workbench worked {lead_worked} item(s). "
            f"Discovery outreach sent {outreach_stats.get('sent', 0)} and queued {outreach_stats.get('queued', 0)}. "
            f"Daily A2A quota: prepared {daily_quota.get('prepared_count', 0)}/{daily_quota.get('target', 0)}, "
            f"sent {daily_quota.get('sent_count', 0)}/{daily_quota.get('target', 0)}."
        )
        if compute_watch:
            analysis += (
                f" Compute watch: brains={compute_watch.get('brain_count', 0)}, "
                f"active_lanes={len(compute_watch.get('active_lanes') or [])}, "
                f"needs_attention={bool(compute_watch.get('needs_attention'))}."
            )
        if lead_count:
            analysis += f" Public lead scout surfaced {lead_count} lead(s) this cycle."
        if top_high_value_pattern:
            analysis += (
                f" Top reusable service pattern: {top_high_value_pattern.get('title', '')} "
                f"for {top_high_value_pattern.get('pain_type', 'unknown')} "
                f"({top_high_value_pattern.get('occurrence_count', 0)} hits)."
            )
        if mutual_aid and not mutual_aid.get("skipped"):
            analysis += (
                f" Mutual-Aid score is {mutual_aid.get('mutual_aid_score', 0)} "
                f"with truth_density_total={mutual_aid.get('truth_density_total', 0)}."
            )
        if swarm_accumulation and not swarm_accumulation.get("skipped"):
            analysis += (
                f" Swarm accumulation known_agents={swarm_accumulation.get('known_agents', 0)} "
                f"prospects={swarm_accumulation.get('prospect_agents', 0)}; "
                f"next={swarm_accumulation.get('next_best_action', '')}"
            )
        if swarm_coordination and not swarm_coordination.get("skipped"):
            analysis += (
                f" Swarm coordination focus={swarm_coordination.get('focus_pain_type', '')} "
                f"connected_agents={swarm_coordination.get('connected_agents', 0)}; "
                f"next={swarm_coordination.get('next_best_action', '')}"
            )
        if autonomous_development:
            if autonomous_development.get("skipped"):
                analysis += f" Autonomous development skipped: {autonomous_development.get('reason', 'unchanged')}."
            else:
                action = autonomous_development.get("action") or {}
                analysis += f" Autonomous development recorded {action.get('action_id', '')}: {action.get('title', '')}."
        if surface_gate.get("blocked"):
            analysis += (
                f" All-surfaces gate is blocking growth lane ({surface_gate.get('reason', '')}); "
                f"remediation objective activated: {surface_remediation.get('objective', '')}"
            )
        if evidence_or_pay_gate.get("blocked"):
            analysis += (
                f" Evidence-or-pay gate is blocking outbound growth ({evidence_or_pay_gate.get('reason', '')}); "
                f"remediation objective activated: {evidence_remediation.get('objective', '')}"
            )
        return analysis

    def _efficiency_plan(
        self,
        *,
        public_api_url: str,
        service_summary: Dict[str, Any],
        payment_followup_queue: Dict[str, Any],
        contact_summary: Dict[str, Any],
        contact_poll: Dict[str, Any],
        lead_conversion: Dict[str, Any],
        outreach_summary: Dict[str, Any],
        swarm_accumulation: Dict[str, Any],
        swarm_coordination: Dict[str, Any],
        self_improvement: Dict[str, Any],
        daily_quota: Dict[str, Any],
        agent_growth_pipeline: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        compute_watch = self_improvement.get("compute_watch") or {}
        active_lanes = [str(item) for item in (compute_watch.get("active_lanes") or []) if item]
        brain_count = int(compute_watch.get("brain_count") or len(active_lanes) or 0)
        prospect_agents = int(swarm_accumulation.get("prospect_agents") or 0)
        joined_agents = int(swarm_coordination.get("connected_agents") or swarm_accumulation.get("joined_agents") or 0)
        queued_contacts = len(contact_summary.get("sent_contact_ids") or [])
        replied_contacts = len(contact_poll.get("replied_contact_ids") or [])
        awaiting_payment = len(service_summary.get("awaiting_payment_task_ids") or [])
        stale_invalid = len(service_summary.get("stale_invalid_task_ids") or [])
        paid_ready = len(service_summary.get("worked_task_ids") or []) + len(service_summary.get("draft_ready_task_ids") or [])
        prepared_conversions = sum(int(v) for v in (lead_conversion.get("stats") or {}).values())
        outreach_campaign = outreach_summary.get("campaign") or {}
        outreach_stats = outreach_campaign.get("stats") or {}
        activation_queue = [
            item
            for item in (swarm_accumulation.get("activation_queue") or [])
            if isinstance(item, dict)
        ]

        if awaiting_payment:
            next_action = "convert_awaiting_payment_to_small_paid_unblock"
        elif stale_invalid:
            next_action = "find_real_jobs_after_dropping_invalid_payment_placeholders"
        elif prospect_agents > joined_agents and activation_queue:
            next_action = "activate_best_agent_prospect"
        elif replied_contacts:
            next_action = "convert_replies_to_join_or_paid_task"
        elif prepared_conversions or int(outreach_stats.get("queued") or 0):
            next_action = "send_or_follow_up_prepared_agent_contacts"
        else:
            next_action = "discover_one_agent_with_public_blocker"

        compute_policy = {
            "active_lanes": active_lanes,
            "brain_count": brain_count,
            "cloudflare_required": False,
            "preferred_next_compute": "reuse_active_lanes" if brain_count >= 2 else "unlock_one_free_or_local_lane",
            "rule": "Do not wait for Cloudflare tokens when local or hosted lanes can produce bounded diagnosis work.",
        }
        if brain_count <= 1 and compute_watch.get("activation_request"):
            compute_policy["activation_request"] = compute_watch.get("activation_request") or {}

        agp = agent_growth_pipeline or {}
        acquisition_hints = agp.get("acquisition_hints") or {}
        machine_instruction = (
            "Prioritize one public blocker, one fast onboarding payload, or one paid task conversion per cycle; "
            "reuse active compute lanes and ask humans only for concrete unlocks."
        )
        if acquisition_hints.get("stuck"):
            machine_instruction += (
                " Agent growth outbound send stalled: use efficiency_plan.acquisition_hints.operator_actions "
                "for the smallest next human step."
            )

        return {
            "schema": "nomad.autopilot_efficiency_plan.v1",
            "goal": "more_agent_onboarding_and_paid_blocker_resolution",
            "public_api_url": public_api_url,
            "next_best_action": next_action,
            "agent_native_moat": {
                "principles": [
                    "contract_first_bootstrap_before_outreach",
                    "machine_verifiable_artifacts_over_human_pitch",
                    "reciprocal_swarm_learning_with_paid_boundary",
                ],
                "surfaces": [
                    f"{public_api_url}/swarm/bootstrap" if public_api_url else "/swarm/bootstrap",
                    f"{public_api_url}/swarm/develop" if public_api_url else "/swarm/develop",
                    f"{public_api_url}/swarm/join" if public_api_url else "/swarm/join",
                    f"{public_api_url}/tasks" if public_api_url else "/tasks",
                ],
            },
            "agent_onboarding_funnel": {
                "joined_agents": joined_agents,
                "prospect_agents": prospect_agents,
                "activation_queue": [
                    {
                        "agent_id": item.get("agent_id", ""),
                        "recommended_role": item.get("recommended_role", ""),
                        "stage": item.get("stage", ""),
                        "next_action": item.get("next_action", ""),
                    }
                    for item in activation_queue[:5]
                ],
                "fast_join_endpoint": f"{public_api_url}/swarm/join" if public_api_url else "/swarm/join",
                "development_endpoint": f"{public_api_url}/swarm/develop" if public_api_url else "/swarm/develop",
            },
            "paid_blocker_lane": {
                "awaiting_payment": awaiting_payment,
                "stale_invalid": stale_invalid,
                "paid_or_draft_ready": paid_ready,
                "queued_payment_followups": len(payment_followup_queue.get("queued_contact_ids") or []),
                "tasks_endpoint": f"{public_api_url}/tasks" if public_api_url else "/tasks",
            },
            "outreach_efficiency": {
                "prepared_conversions": prepared_conversions,
                "queued_contacts_sent": queued_contacts,
                "replied_contacts": replied_contacts,
                "daily_remaining_to_prepare": daily_quota.get("remaining_to_prepare", 0),
                "daily_remaining_to_send": daily_quota.get("remaining_to_send", 0),
            },
            "compute_policy": compute_policy,
            "acquisition_hints": acquisition_hints,
            "machine_instruction": machine_instruction,
        }

    @staticmethod
    def _is_public_service_url(public_api_url: str) -> bool:
        url = str(public_api_url or "").strip()
        if not url:
            return False
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return host not in {"127.0.0.1", "localhost"}

    @staticmethod
    def _compact_service(service_summary: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "worked_task_ids": service_summary.get("worked_task_ids") or [],
            "draft_ready_task_ids": service_summary.get("draft_ready_task_ids") or [],
            "awaiting_payment_task_ids": service_summary.get("awaiting_payment_task_ids") or [],
            "stale_invalid_task_ids": service_summary.get("stale_invalid_task_ids") or [],
            "payment_followups": [
                {
                    "task_id": item.get("task_id") or "",
                    "cheaper_starter_available": bool(item.get("cheaper_starter_available")),
                    "starter_offer": item.get("starter_offer") or {},
                    "primary_offer": item.get("primary_offer") or {},
                    "nudge": item.get("nudge") or "",
                }
                for item in (service_summary.get("payment_followups") or [])[:5]
                if isinstance(item, dict)
            ],
            "review_needed_task_ids": service_summary.get("review_needed_task_ids") or [],
            "stats": ((service_summary.get("listing") or {}).get("stats") or {}),
        }

    @staticmethod
    def _compact_payment_followup_queue(summary: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "queued_contact_ids": summary.get("queued_contact_ids") or [],
            "duplicate_contact_ids": summary.get("duplicate_contact_ids") or [],
            "blocked_task_ids": summary.get("blocked_task_ids") or [],
            "skipped_task_ids": summary.get("skipped_task_ids") or [],
            "skipped_reasons": summary.get("skipped_reasons") or {},
            "analysis": summary.get("analysis", ""),
            "reason": summary.get("reason", ""),
            "skipped": bool(summary.get("skipped", False)),
        }

    @staticmethod
    def _compact_contacts(contact_summary: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "sent_contact_ids": contact_summary.get("sent_contact_ids") or [],
            "failed_contact_ids": contact_summary.get("failed_contact_ids") or [],
            "stats": ((contact_summary.get("queued_listing") or {}).get("stats") or {}),
        }

    @staticmethod
    def _compact_agent_followup_queue(summary: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "queued_contact_ids": summary.get("queued_contact_ids") or [],
            "duplicate_contact_ids": summary.get("duplicate_contact_ids") or [],
            "blocked_contact_ids": summary.get("blocked_contact_ids") or [],
            "skipped_contact_ids": summary.get("skipped_contact_ids") or [],
            "skipped_reasons": summary.get("skipped_reasons") or {},
            "analysis": summary.get("analysis", ""),
            "reason": summary.get("reason", ""),
            "skipped": bool(summary.get("skipped", False)),
        }

    @staticmethod
    def _compact_contact_poll(contact_summary: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "polled_contact_ids": contact_summary.get("polled_contact_ids") or [],
            "replied_contact_ids": contact_summary.get("replied_contact_ids") or [],
            "completed_contact_ids": contact_summary.get("completed_contact_ids") or [],
            "failed_contact_ids": contact_summary.get("failed_contact_ids") or [],
            "reply_summaries": contact_summary.get("reply_summaries") or [],
            "stats": ((contact_summary.get("sent_listing") or {}).get("stats") or {}),
        }

    @staticmethod
    def _compact_reply_conversion(reply_conversion: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "converted_contact_ids": reply_conversion.get("converted_contact_ids") or [],
            "created_task_ids": reply_conversion.get("created_task_ids") or [],
            "skipped_contact_ids": reply_conversion.get("skipped_contact_ids") or [],
            "errors": reply_conversion.get("errors") or [],
            "analysis": reply_conversion.get("analysis", ""),
        }

    @staticmethod
    def _compact_lead_conversion(lead_conversion: Dict[str, Any]) -> Dict[str, Any]:
        conversions = lead_conversion.get("conversions") or []
        return {
            "stats": lead_conversion.get("stats") or {},
            "query": lead_conversion.get("autopilot_query") or lead_conversion.get("query") or "",
            "send_requested": bool(lead_conversion.get("send_requested", False)),
            "send_enabled": bool(lead_conversion.get("send_enabled", False)),
            "send_blocked_reason": lead_conversion.get("send_blocked_reason", ""),
            "cycle_lead_count": lead_conversion.get("cycle_lead_count", 0),
            "conversion_ids": [item.get("conversion_id", "") for item in conversions[:5] if item.get("conversion_id")],
            "statuses": [item.get("status", "") for item in conversions[:5] if item.get("status")],
            "analysis": lead_conversion.get("analysis", ""),
            "skipped": lead_conversion.get("skipped", False),
            "reason": lead_conversion.get("reason", ""),
        }

    @staticmethod
    def _compact_agent_growth_pipeline(payload: Dict[str, Any]) -> Dict[str, Any]:
        if not payload or payload.get("skipped"):
            return {
                "skipped": bool(payload.get("skipped", True)),
                "reason": payload.get("reason", ""),
                "next_run_num": int(payload.get("next_run_num") or 0),
                "every_n": int(payload.get("every_n") or 0),
            }
        leads = payload.get("leads") or {}
        cand = leads.get("candidate_count")
        if cand is None:
            cand = len(leads.get("leads") or [])
        conv = payload.get("conversion") or {}
        convs = conv.get("conversions") or []
        pf = payload.get("product_factory") or {}
        sw = payload.get("swarm_accumulation") or {}
        mrc = payload.get("machine_runtime_contract") or {}
        ah = payload.get("acquisition_hints") or {}
        conv_stats: Dict[str, Any] = dict(conv.get("stats") or {}) if isinstance(conv, dict) else {}
        if not conv_stats and convs:
            for item in convs:
                if not isinstance(item, dict):
                    continue
                st = str(item.get("status") or "unknown")
                conv_stats[st] = int(conv_stats.get(st) or 0) + 1
        sent_ac = int(conv_stats.get("sent_agent_contact") or 0)
        return {
            "schema": payload.get("schema", ""),
            "ok": bool(payload.get("ok", False)),
            "query": payload.get("query", ""),
            "limit": int(payload.get("limit") or 0),
            "scout_candidate_count": int(cand or 0),
            "conversion_count": len(convs),
            "product_count": int(pf.get("product_count") or len(pf.get("products") or [])),
            "new_swarm_prospect_ids": list(sw.get("new_prospect_ids") or [])[:8],
            "machine_runtime_contract_schema": mrc.get("schema", ""),
            "analysis_tail": (payload.get("analysis") or "")[:240],
            "send_outreach": bool(payload.get("send_outreach")),
            "sent_agent_contact": sent_ac,
            "acquisition_stuck": bool(ah.get("stuck")),
            "acquisition_reason_codes": list(ah.get("reason_codes") or [])[:8],
            "human_escalation_hint_tail": " | ".join(str(x) for x in (payload.get("human_escalation_hints") or [])[:3]),
        }

    @staticmethod
    def _compact_product_factory(product_factory: Dict[str, Any]) -> Dict[str, Any]:
        products = product_factory.get("products") or []
        top_priority = product_factory.get("top_priority_product") or (products[0] if products else {})
        engagement_summary = product_factory.get("engagement_summary") or {}
        return {
            "product_count": product_factory.get("product_count", 0),
            "stats": product_factory.get("stats") or {},
            "engagement_summary": {
                "entry_count": engagement_summary.get("entry_count", 0),
                "roles": engagement_summary.get("roles") or {},
            },
            "product_ids": [item.get("product_id", "") for item in products[:5] if item.get("product_id")],
            "variant_skus": [item.get("variant_sku", "") for item in products[:5] if item.get("variant_sku")],
            "statuses": [item.get("status", "") for item in products[:5] if item.get("status")],
            "top_priority_product": {
                "product_id": top_priority.get("product_id", ""),
                "name": top_priority.get("name", ""),
                "priority_score": top_priority.get("priority_score", 0),
                "priority_reason": top_priority.get("priority_reason", ""),
            },
            "analysis": product_factory.get("analysis", ""),
            "skipped": product_factory.get("skipped", False),
            "reason": product_factory.get("reason", ""),
        }

    @staticmethod
    def _compact_lead_workbench(payload: Dict[str, Any]) -> Dict[str, Any]:
        self_help = payload.get("self_help") or {}
        return {
            "schema": payload.get("schema", ""),
            "queue_count": payload.get("queue_count", 0),
            "worked_count": payload.get("worked_count", 0),
            "top_next_action": self_help.get("top_next_action", ""),
            "executable_without_human_count": self_help.get("executable_without_human_count", 0),
            "human_blocked_count": self_help.get("human_blocked_count", 0),
            "next_autopilot_bias": self_help.get("next_autopilot_bias", ""),
            "analysis": payload.get("analysis", ""),
            "skipped": payload.get("skipped", False),
            "reason": payload.get("reason", ""),
        }

    @staticmethod
    def _compact_outreach(outreach_summary: Dict[str, Any]) -> Dict[str, Any]:
        campaign = outreach_summary.get("campaign") or {}
        return {
            "campaign_id": campaign.get("campaign_id", ""),
            "stats": campaign.get("stats") or {},
            "query": outreach_summary.get("autopilot_query") or outreach_summary.get("query") or "",
            "service_type_focus": outreach_summary.get("service_type_focus", ""),
            "analysis": outreach_summary.get("analysis", ""),
            "skipped": outreach_summary.get("skipped", False),
            "reason": outreach_summary.get("reason", ""),
            "discovery": campaign.get("discovery") or outreach_summary.get("discovery") or {},
        }

    @staticmethod
    def _compact_mutual_aid(mutual_aid: Dict[str, Any]) -> Dict[str, Any]:
        plan = mutual_aid.get("evolution_plan") or {}
        return {
            "skipped": bool(mutual_aid.get("skipped", False)),
            "reason": mutual_aid.get("reason", ""),
            "mutual_aid_score": mutual_aid.get("mutual_aid_score", 0),
            "truth_density_total": mutual_aid.get("truth_density_total", 0),
            "truth_ledger_count": mutual_aid.get("truth_ledger_count", 0),
            "paid_pack_count": mutual_aid.get("paid_pack_count", 0),
            "plan": {
                "module_id": plan.get("module_id", ""),
                "filename": plan.get("filename", ""),
                "applied": bool(plan.get("applied", False)),
            },
            "analysis": mutual_aid.get("analysis", ""),
        }

    @staticmethod
    def _compact_swarm_accumulation(swarm_accumulation: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "skipped": bool(swarm_accumulation.get("skipped", False)),
            "reason": swarm_accumulation.get("reason", ""),
            "schema": swarm_accumulation.get("schema", ""),
            "focus_pain_type": swarm_accumulation.get("focus_pain_type", ""),
            "known_agents": swarm_accumulation.get("known_agents", 0),
            "joined_agents": swarm_accumulation.get("joined_agents", 0),
            "prospect_agents": swarm_accumulation.get("prospect_agents", 0),
            "new_prospect_ids": swarm_accumulation.get("new_prospect_ids") or [],
            "updated_prospect_ids": swarm_accumulation.get("updated_prospect_ids") or [],
            "next_best_action": swarm_accumulation.get("next_best_action", ""),
            "activation_queue": [
                {
                    "agent_id": item.get("agent_id", ""),
                    "recommended_role": item.get("recommended_role", ""),
                    "stage": item.get("stage", ""),
                    "score": item.get("score", 0.0),
                    "next_action": item.get("next_action", ""),
                }
                for item in (swarm_accumulation.get("activation_queue") or [])[:6]
                if isinstance(item, dict)
            ],
            "analysis": swarm_accumulation.get("analysis", ""),
        }

    @staticmethod
    def _compact_swarm_coordination(swarm_coordination: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "skipped": bool(swarm_coordination.get("skipped", False)),
            "reason": swarm_coordination.get("reason", ""),
            "schema": swarm_coordination.get("schema", ""),
            "focus_pain_type": swarm_coordination.get("focus_pain_type", ""),
            "connected_agents": swarm_coordination.get("connected_agents", 0),
            "role_counts": swarm_coordination.get("role_counts") or {},
            "next_best_action": swarm_coordination.get("next_best_action", ""),
            "help_lanes": [
                {
                    "lane_id": item.get("lane_id", ""),
                    "role": item.get("role", ""),
                    "entrypoint": item.get("entrypoint", ""),
                    "reply_contract": item.get("reply_contract", ""),
                }
                for item in (swarm_coordination.get("help_lanes") or [])[:4]
                if isinstance(item, dict)
            ],
            "analysis": swarm_coordination.get("analysis", ""),
        }

    @staticmethod
    def _compact_autonomous_development(payload: Dict[str, Any]) -> Dict[str, Any]:
        action = payload.get("action") or payload.get("latest_action") or {}
        candidate = payload.get("candidate") or {}
        return {
            "skipped": bool(payload.get("skipped", False)),
            "reason": payload.get("reason", ""),
            "action_count": payload.get("action_count", 0),
            "action": {
                "action_id": action.get("action_id", ""),
                "type": action.get("type", candidate.get("type", "")),
                "title": action.get("title", candidate.get("title", "")),
                "files": action.get("files", candidate.get("files") or []),
                "next_verification": action.get("next_verification", candidate.get("next_verification", "")),
            },
            "analysis": payload.get("analysis", ""),
        }

    @staticmethod
    def _compact_efficiency_plan(payload: Dict[str, Any]) -> Dict[str, Any]:
        funnel = payload.get("agent_onboarding_funnel") or {}
        paid_lane = payload.get("paid_blocker_lane") or {}
        outreach = payload.get("outreach_efficiency") or {}
        compute = payload.get("compute_policy") or {}
        acq = payload.get("acquisition_hints") or {}
        return {
            "schema": payload.get("schema", ""),
            "goal": payload.get("goal", ""),
            "next_best_action": payload.get("next_best_action", ""),
            "agent_onboarding_funnel": {
                "joined_agents": funnel.get("joined_agents", 0),
                "prospect_agents": funnel.get("prospect_agents", 0),
                "fast_join_endpoint": funnel.get("fast_join_endpoint", ""),
                "development_endpoint": funnel.get("development_endpoint", ""),
            },
            "paid_blocker_lane": {
                "awaiting_payment": paid_lane.get("awaiting_payment", 0),
                "paid_or_draft_ready": paid_lane.get("paid_or_draft_ready", 0),
                "tasks_endpoint": paid_lane.get("tasks_endpoint", ""),
            },
            "outreach_efficiency": {
                "prepared_conversions": outreach.get("prepared_conversions", 0),
                "queued_contacts_sent": outreach.get("queued_contacts_sent", 0),
                "replied_contacts": outreach.get("replied_contacts", 0),
            },
            "compute_policy": {
                "brain_count": compute.get("brain_count", 0),
                "active_lanes": compute.get("active_lanes") or [],
                "cloudflare_required": bool(compute.get("cloudflare_required", False)),
                "preferred_next_compute": compute.get("preferred_next_compute", ""),
            },
            "acquisition_stuck": bool(acq.get("stuck")),
            "acquisition_reason_codes": list(acq.get("reason_codes") or [])[:6],
            "acquisition_actions_tail": " | ".join(str(x) for x in (acq.get("operator_actions") or [])[:2]),
        }

    @staticmethod
    def _compact_autonomy_proof(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "schema": payload.get("schema", ""),
            "cycle_was_useful": bool(payload.get("cycle_was_useful", False)),
            "status": payload.get("status", ""),
            "useful_artifact_created": payload.get("useful_artifact_created", ""),
            "useful_artifact_count": len(payload.get("useful_artifacts") or []),
            "external_progress": bool(payload.get("external_progress", False)),
            "money_progress": bool(payload.get("money_progress", False)),
            "agent_progress": bool(payload.get("agent_progress", False)),
            "code_progress": bool(payload.get("code_progress", False)),
            "learning_progress": bool(payload.get("learning_progress", False)),
            "useless_cycle_streak": int(payload.get("useless_cycle_streak") or 0),
            "stuck_reason": payload.get("stuck_reason", ""),
            "next_required_unlock": payload.get("next_required_unlock", ""),
            "should_pause_autonomy": bool(payload.get("should_pause_autonomy", False)),
            "minimum_next_real_outcome": payload.get("minimum_next_real_outcome", ""),
        }

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _compact_self_improvement(result: Dict[str, Any]) -> Dict[str, Any]:
        development = result.get("self_development") or {}
        reviews = result.get("brain_reviews") or []
        first_review = reviews[0] if reviews else {}
        compute_watch = result.get("compute_watch") or {}
        lead_scout = result.get("lead_scout") or {}
        active_lead = lead_scout.get("active_lead") or {}
        high_value_patterns = (result.get("high_value_patterns") or {}).get("patterns") or []
        top_high_value_pattern = high_value_patterns[0] if high_value_patterns else {}
        return {
            "objective": result.get("objective", ""),
            "external_review_count": result.get("external_review_count", 0),
            "analysis": result.get("analysis", ""),
            "next_objective": development.get("next_objective", ""),
            "brain": {
                "name": first_review.get("name", ""),
                "model": first_review.get("model", ""),
                "ok": first_review.get("ok", False),
            },
            "compute_watch": {
                "needs_attention": compute_watch.get("needs_attention", False),
                "brain_count": compute_watch.get("brain_count", 0),
                "active_lanes": compute_watch.get("active_lanes") or [],
                "headline": compute_watch.get("headline", ""),
                "activation_request": compute_watch.get("activation_request") or {},
            },
            "lead_watch": {
                "focus": lead_scout.get("focus", ""),
                "lead_count": len(lead_scout.get("leads") or []),
                "compute_lead_count": len(lead_scout.get("compute_leads") or []),
                "active_lead_url": active_lead.get("url", ""),
                "active_lead_title": active_lead.get("title") or active_lead.get("name") or "",
                "outreach_queries": lead_scout.get("outreach_queries") or [],
                "help_draft": ((lead_scout.get("help_draft") or {}).get("draft") or ""),
            },
            "high_value_pattern_watch": {
                "title": top_high_value_pattern.get("title", ""),
                "pain_type": top_high_value_pattern.get("pain_type", ""),
                "occurrence_count": top_high_value_pattern.get("occurrence_count", 0),
                "avg_truth_score": top_high_value_pattern.get("avg_truth_score", 0),
                "avg_reuse_value": top_high_value_pattern.get("avg_reuse_value", 0),
            },
        }
