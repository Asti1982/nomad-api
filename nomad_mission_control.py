import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from nomad_public_url import preferred_public_base_url
from self_development import SelfDevelopmentJournal


ROOT = Path(__file__).resolve().parent
DEFAULT_MISSION_CONTROL_STATE = ROOT / "nomad_mission_control_state.json"


class NomadMissionControl:
    """Daily operating loop that turns Nomad's ambition into bounded work."""

    def __init__(
        self,
        agent: Any,
        path: Optional[Path] = None,
        journal: Optional[SelfDevelopmentJournal] = None,
    ) -> None:
        self.agent = agent
        self.path = path or DEFAULT_MISSION_CONTROL_STATE
        self.journal = journal or SelfDevelopmentJournal()

    def snapshot(
        self,
        *,
        base_url: str = "",
        persist: bool = True,
        limit: int = 5,
    ) -> dict[str, Any]:
        public_url = (base_url or preferred_public_base_url(request_base_url="http://127.0.0.1:8787")).rstrip("/")
        monitor = self._monitor_snapshot()
        tasks = self._service_tasks(limit=max(limit, 10))
        outbound = self._outbound_summary(limit=limit)
        readiness = self._swarm_readiness(base_url=public_url)
        attractor = self._agent_attractor(base_url=public_url, limit=limit)
        swarm_summary = self._swarm_summary()
        lead_workbench = self._lead_workbench(limit=limit)
        state = self._load_state()

        blockers = self._rank_blockers(
            monitor=monitor,
            tasks=tasks,
            outbound=outbound,
            readiness=readiness,
            lead_workbench=lead_workbench,
            state=state,
        )
        top_blocker = blockers[0] if blockers else self._blocker(
            "keep_daily_loop_alive",
            "Keep Nomad's daily learning and paid-job loop alive.",
            "medium",
            "Run one bounded self-improvement cycle and store the outcome.",
        )
        paid_job_focus = self._paid_job_focus(tasks=tasks, top_blocker=top_blocker, public_url=public_url)
        human_unlocks = self._human_unlocks(
            top_blocker=top_blocker,
            tasks=tasks,
            monitor=monitor,
            outbound=outbound,
            public_url=public_url,
        )
        agent_tasks = self._agent_tasks(
            top_blocker=top_blocker,
            paid_job_focus=paid_job_focus,
            readiness=readiness,
            attractor=attractor,
            public_url=public_url,
            limit=limit,
        )
        compute_policy = self._compute_policy(monitor=monitor, readiness=readiness)
        self_improvement = self._self_improvement_loop(top_blocker=top_blocker, human_unlocks=human_unlocks)
        telegram_unlock = self._telegram_unlock(top_blocker=top_blocker, human_unlocks=human_unlocks, paid_job_focus=paid_job_focus)
        next_action = self._next_action(
            top_blocker=top_blocker,
            human_unlocks=human_unlocks,
            agent_tasks=agent_tasks,
            paid_job_focus=paid_job_focus,
        )

        report = {
            "mode": "nomad_mission_control",
            "schema": "nomad.mission_control.v1",
            "ok": True,
            "timestamp": datetime.now(UTC).isoformat(),
            "public_url": public_url,
            "top_blocker": top_blocker,
            "blockers": blockers,
            "next_action": next_action,
            "human_unlocks": human_unlocks,
            "telegram_unlock": telegram_unlock,
            "agent_tasks": agent_tasks,
            "paid_job_focus": paid_job_focus,
            "lead_workbench": lead_workbench,
            "agent_attraction": self._agent_attraction_summary(readiness=readiness, attractor=attractor, public_url=public_url),
            "compute_policy": compute_policy,
            "self_improvement": self_improvement,
            "signals": {
                "service_tasks": self._task_counts(tasks),
                "outbound": self._compact_outbound(outbound),
                "swarm_ready": readiness.get("status", ""),
                "connected_agents": int(swarm_summary.get("connected_agents") or 0),
                "lead_queue_count": int(lead_workbench.get("queue_count") or 0),
            },
            "analysis": (
                "Mission Control selected one highest-leverage blocker, one human unlock, "
                "bounded agent tasks, and a compute policy that activates specialists only when a real blocker exists."
            ),
        }
        if persist:
            self._record(report)
        return report

    def _monitor_snapshot(self) -> dict[str, Any]:
        monitor = getattr(self.agent, "monitor", None)
        if monitor and hasattr(monitor, "snapshot"):
            try:
                return monitor.snapshot()
            except Exception:
                pass
        return {}

    def _service_tasks(self, *, limit: int) -> list[dict[str, Any]]:
        desk = getattr(self.agent, "service_desk", None)
        if not desk or not hasattr(desk, "list_tasks"):
            return []
        try:
            return list((desk.list_tasks(limit=limit).get("tasks") or []))
        except Exception:
            return []

    def _outbound_summary(self, *, limit: int) -> dict[str, Any]:
        tracker = getattr(self.agent, "outbound_tracker", None)
        if not tracker or not hasattr(tracker, "summary"):
            return {}
        try:
            return tracker.summary(limit=limit)
        except Exception:
            return {}

    def _swarm_readiness(self, *, base_url: str) -> dict[str, Any]:
        registry = getattr(self.agent, "swarm_registry", None)
        if not registry or not hasattr(registry, "first_agent_readiness"):
            return {}
        try:
            return registry.first_agent_readiness(base_url=base_url)
        except Exception:
            return {}

    def _swarm_summary(self) -> dict[str, Any]:
        registry = getattr(self.agent, "swarm_registry", None)
        if not registry or not hasattr(registry, "summary"):
            return {}
        try:
            return registry.summary()
        except Exception:
            return {}

    def _agent_attractor(self, *, base_url: str, limit: int) -> dict[str, Any]:
        attractor = getattr(self.agent, "agent_attractor", None)
        if not attractor or not hasattr(attractor, "manifest"):
            return {}
        try:
            return attractor.manifest(service_type="compute_auth", role_hint="peer_solver", limit=limit)
        except Exception:
            return {}

    def _lead_workbench(self, *, limit: int) -> dict[str, Any]:
        workbench = getattr(self.agent, "lead_workbench", None)
        if not workbench or not hasattr(workbench, "status"):
            return {}
        try:
            return workbench.status(limit=limit, work=False)
        except Exception:
            return {}

    def _rank_blockers(
        self,
        *,
        monitor: dict[str, Any],
        tasks: list[dict[str, Any]],
        outbound: dict[str, Any],
        readiness: dict[str, Any],
        lead_workbench: dict[str, Any],
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        blockers: list[dict[str, Any]] = []
        counts = self._task_counts(tasks)
        if counts["paid"] > 0:
            blockers.append(
                self._blocker(
                    "paid_task_waiting_for_delivery",
                    "A paid task is waiting for Nomad to deliver a draft or artifact.",
                    "critical",
                    "Work the oldest paid task now and store the delivery as proof.",
                )
            )
        valid_awaiting_payment = [
            task for task in tasks if str(task.get("status") or "") == "awaiting_payment" and self._has_payment_route(task)
        ]
        stale_awaiting_payment = [
            task for task in tasks if str(task.get("status") or "") == "awaiting_payment" and not self._has_payment_route(task)
        ]
        if valid_awaiting_payment:
            blockers.append(
                self._blocker(
                    "convert_awaiting_payment",
                    "A task exists but payment is not verified yet.",
                    "high",
                    "Send the smallest safe payment follow-up and offer a starter diagnosis.",
                )
            )
        if stale_awaiting_payment:
            blockers.append(
                self._blocker(
                    "drop_invalid_payment_placeholders",
                    f"{len(stale_awaiting_payment)} awaiting-payment task(s) have no requester route or payment proof.",
                    "medium",
                    "Mark invalid placeholders stale and look for real jobs/leads.",
                )
            )
        if counts["total"] == 0:
            blockers.append(
                self._blocker(
                    "no_first_paid_customer",
                    "Nomad still needs the first real paid customer or paid agent blocker.",
                    "critical",
                    "Publish one concrete paid micro-offer and scout five AI-agent blocker surfaces.",
                )
            )
        compute_lanes = ((monitor.get("compute_lanes") or {}).get("hosted") or {})
        local_lanes = ((monitor.get("compute_lanes") or {}).get("local") or {})
        hosted_active = [
            name
            for name, value in compute_lanes.items()
            if (value.get("available") if isinstance(value, dict) else bool(value))
        ]
        local_active = [name for name, value in local_lanes.items() if bool(value)]
        if not hosted_active and not local_active:
            blockers.append(
                self._blocker(
                    "compute_starved",
                    "No reliable local or hosted model lane is currently active.",
                    "high",
                    "Prefer local-first work, then activate Modal or another fallback only for a concrete blocker.",
                )
            )
        followups = int((((outbound.get("contacts") or {}).get("followup_ready")) or 0))
        if followups > 0:
            blockers.append(
                self._blocker(
                    "followups_ready",
                    f"{followups} outbound follow-up(s) are ready.",
                    "medium",
                    "Review and send only follow-ups tied to a concrete paid-job or agent-help path.",
                )
            )
        if not readiness:
            blockers.append(
                self._blocker(
                    "missing_agent_join_readiness",
                    "The swarm readiness packet is unavailable.",
                    "high",
                    "Restore /swarm/ready before inviting more agents.",
                )
            )
        queue_count = int(lead_workbench.get("queue_count") or 0)
        executable_count = int(((lead_workbench.get("self_help") or {}).get("executable_without_human_count")) or 0)
        if queue_count > 0:
            blockers.append(
                self._blocker(
                    "lead_queue_waiting",
                    f"{queue_count} lead/product work item(s) are waiting; {executable_count} can move without human outreach.",
                    "high" if executable_count else "medium",
                    "Work the highest-priority lead/product queue items and store learning signals.",
                )
            )
        if not state.get("last_report_at"):
            blockers.append(
                self._blocker(
                    "mission_loop_not_yet_recorded",
                    "Mission Control has not recorded a previous operating loop.",
                    "medium",
                    "Record today's top blocker and next action so Nomad can compare tomorrow.",
                )
            )
        return sorted(blockers, key=lambda item: self._severity_rank(item.get("severity", "low")))

    @staticmethod
    def _blocker(blocker_id: str, summary: str, severity: str, next_action: str) -> dict[str, str]:
        return {
            "id": blocker_id,
            "summary": summary,
            "severity": severity,
            "next_action": next_action,
        }

    @staticmethod
    def _severity_rank(severity: str) -> int:
        return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(severity, 4)

    @staticmethod
    def _has_payment_route(task: dict[str, Any]) -> bool:
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        payment = task.get("payment") if isinstance(task.get("payment"), dict) else {}
        candidates = [
            task.get("callback_url"),
            task.get("requester_wallet"),
            task.get("tx_hash"),
            payment.get("tx_hash"),
            metadata.get("requester_endpoint"),
            metadata.get("endpoint_url"),
            metadata.get("callback_url"),
            metadata.get("tx_hash"),
        ]
        return any(str(item or "").strip() for item in candidates)

    def _paid_job_focus(
        self,
        *,
        tasks: list[dict[str, Any]],
        top_blocker: dict[str, Any],
        public_url: str,
    ) -> dict[str, Any]:
        counts = self._task_counts(tasks)
        valid_awaiting = [
            task for task in tasks if str(task.get("status") or "") == "awaiting_payment" and self._has_payment_route(task)
        ]
        paid_or_waiting = [
            task
            for task in tasks
            if str(task.get("status") or "") in {"paid", "draft_ready", "manual_payment_review"}
            or (str(task.get("status") or "") == "awaiting_payment" and self._has_payment_route(task))
        ]
        target = "debugging AI agent deployment, webhook, auth, payment, or compute blocker"
        status = "deliver_existing_task" if counts["paid"] else ("convert_waiting_task" if valid_awaiting else "needs_first_customer")
        return {
            "schema": "nomad.first_paid_job_focus.v1",
            "status": status,
            "target_customer": "AI agent builder or autonomous agent blocked by infrastructure friction",
            "target_offer": "Nomad Agent Blocker Diagnosis",
            "service_type": "compute_auth",
            "price_band": "starter 0.01 native token, bounded unblock 0.03+ native token or 25-100 USD equivalent",
            "promise": "one diagnosis, one smallest unlock, one verifier or safe resume step",
            "intake_url": f"{public_url}/service/e2e",
            "machine_offer_url": f"{public_url}/agent-attractor?service_type=compute_auth&role=customer",
            "current_task_count": counts,
            "priority_task_ids": [str(task.get("task_id") or "") for task in paid_or_waiting[:5] if task.get("task_id")],
            "next_action": top_blocker.get("next_action", ""),
        }

    def _human_unlocks(
        self,
        *,
        top_blocker: dict[str, Any],
        tasks: list[dict[str, Any]],
        monitor: dict[str, Any],
        outbound: dict[str, Any],
        public_url: str,
    ) -> list[dict[str, Any]]:
        unlocks: list[dict[str, Any]] = []
        blocker_id = top_blocker.get("id", "")
        if blocker_id == "paid_task_waiting_for_delivery":
            paid = next((task for task in tasks if str(task.get("status") or "") == "paid"), {})
            unlocks.append(
                self._unlock(
                    "approve-paid-task-delivery",
                    "Approve paid task delivery scope",
                    f"Review task {paid.get('task_id', 'oldest paid task')} and approve draft-only delivery or a narrower scope.",
                    "SERVICE_APPROVAL=draft_only",
                )
            )
        elif blocker_id == "convert_awaiting_payment":
            waiting = next((task for task in tasks if str(task.get("status") or "") == "awaiting_payment"), {})
            unlocks.append(
                self._unlock(
                    "provide-payment-route",
                    "Provide payment route",
                    f"Nomad sends money follow-ups automatically when an endpoint exists. Provide requester endpoint or tx hash for task {waiting.get('task_id', 'awaiting-payment task')}.",
                    "REQUESTER_ENDPOINT=https://... or TX_HASH=0x...",
                )
            )
        elif blocker_id == "no_first_paid_customer":
            unlocks.append(
                self._unlock(
                    "approve-first-paid-offer",
                    "Approve first paid micro-offer",
                    "Approve Nomad to present one concrete paid blocker diagnosis offer to AI-agent builders.",
                    "APPROVE_FIRST_PAID_OFFER=yes",
                )
            )
        if "127.0.0.1" in public_url or "localhost" in public_url:
            unlocks.append(
                self._unlock(
                    "publish-public-agent-surface",
                    "Expose public agent surface",
                    "Provide or approve a public URL so outside agents can reach /swarm/ready, /swarm/join, and /service/e2e.",
                    "PUBLIC_NOMAD_URL=https://...",
                )
            )
        compute = monitor.get("compute_lanes") or {}
        if not any(bool(v) for v in (compute.get("local") or {}).values()):
            unlocks.append(
                self._unlock(
                    "choose-compute-fallback",
                    "Choose fallback compute lane",
                    "Choose the next fallback brain for concrete blockers only.",
                    "COMPUTE_PRIORITY=modal",
                )
            )
        if int((((outbound.get("contacts") or {}).get("followup_ready")) or 0)) > 0:
            unlocks.append(
                self._unlock(
                    "approve-agent-followups",
                    "Approve agent follow-ups",
                    "Approve only follow-ups tied to an explicit paid blocker or useful agent collaboration.",
                    "APPROVE_AGENT_FOLLOWUPS=bounded",
                )
            )
        return unlocks[:4]

    @staticmethod
    def _unlock(unlock_id: str, title: str, ask: str, expected_reply: str) -> dict[str, Any]:
        return {
            "id": unlock_id,
            "title": title,
            "ask": ask,
            "expected_reply": expected_reply,
            "done_when": "Nomad can perform the next step without guessing or spending unnecessary compute.",
            "channel": "telegram_or_cli",
        }

    def _agent_tasks(
        self,
        *,
        top_blocker: dict[str, Any],
        paid_job_focus: dict[str, Any],
        readiness: dict[str, Any],
        attractor: dict[str, Any],
        public_url: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        base_tasks = [
            {
                "id": "work-lead-queue",
                "role": "customer_success",
                "objective": "Work the highest-priority private lead/product queue items and store learning signals before searching wider.",
                "output_contract": {"worked_items": ["item_id", "offer_snippet", "learning_signal"]},
                "endpoint": f"{public_url}/lead-workbench?work=true",
            },
            {
                "id": "find-agent-blocker-surfaces",
                "role": "scout",
                "objective": "Find five public AI-agent builder surfaces with compute, auth, webhook, payment, or deployment blockers.",
                "output_contract": {"leads": ["url", "pain_signal", "service_type", "safe_contact_route"]},
                "endpoint": f"{public_url}/agent-attractor",
            },
            {
                "id": "prepare-first-paid-diagnosis",
                "role": "seller_or_customer_success",
                "objective": f"Turn the offer '{paid_job_focus.get('target_offer')}' into one machine-readable service request.",
                "output_contract": {"service_type": "compute_auth", "problem": "one bounded blocker", "budget": "starter or bounded unblock"},
                "endpoint": paid_job_focus.get("intake_url", f"{public_url}/service/e2e"),
            },
            {
                "id": "join-as-peer-solver",
                "role": "peer_solver",
                "objective": "Join Nomad only with public capabilities and one bounded blocker or verifier artifact.",
                "output_contract": readiness.get("first_exchange_endpoints") or {},
                "endpoint": f"{public_url}/swarm/join",
            },
            {
                "id": "verify-one-solution",
                "role": "verifier",
                "objective": "Take one Nomad solution and return public or redacted evidence that it works or fails.",
                "output_contract": {"evidence": "public URL, error class, or redacted reproduction result"},
                "endpoint": f"{public_url}/aid",
            },
        ]
        if top_blocker.get("id") == "paid_task_waiting_for_delivery":
            base_tasks.insert(
                0,
                {
                    "id": "deliver-paid-task-first",
                    "role": "worker",
                    "objective": "Produce the paid task draft before doing any new attraction work.",
                    "output_contract": {"artifact": "diagnosis, smallest unlock, verifier step"},
                    "endpoint": f"{public_url}/service",
                },
            )
        if attractor.get("schema"):
            base_tasks[0]["attractor_schema"] = attractor.get("schema")
        return base_tasks[: max(1, limit)]

    def _compute_policy(self, *, monitor: dict[str, Any], readiness: dict[str, Any]) -> dict[str, Any]:
        readiness_budget = readiness.get("activation_budget") if isinstance(readiness.get("activation_budget"), dict) else {}
        compute = monitor.get("compute_lanes") or {}
        active_local = [
            name for name, value in (compute.get("local") or {}).items() if bool(value)
        ]
        active_hosted = [
            name
            for name, value in (compute.get("hosted") or {}).items()
            if (value.get("available") if isinstance(value, dict) else bool(value))
        ]
        return {
            "schema": "nomad.compute_discipline.v1",
            "default_mode": "local_first_then_modal_or_deferred",
            "max_active_agents_per_blocker": int(readiness_budget.get("max_active_agents_per_blocker") or 2),
            "active_local_lanes": active_local,
            "active_hosted_lanes": active_hosted,
            "activation_triggers": [
                "paid_task_present",
                "external_agent_joined_with_bounded_payload",
                "public_verifier_artifact_present",
                "human_unlock_approved",
            ],
            "do_not_do": [
                "do_not_wake_full_swarm_for_vague_growth",
                "do_not_spend_remote_compute_without_a_blocker",
                "do_not_claim_registry_nodes_are_live_model_processes",
            ],
            "fallback": "write learning packet and wait for blocker-specific compute",
        }

    def _self_improvement_loop(
        self,
        *,
        top_blocker: dict[str, Any],
        human_unlocks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            journal_state = self.journal.load()
        except Exception:
            journal_state = {}
        return {
            "schema": "nomad.daily_self_improvement_loop.v1",
            "cycle": [
                "sense_status",
                "rank_blockers",
                "choose_one_next_action",
                "ask_for_exact_human_unlock_if_needed",
                "activate_at_most_two_relevant_agents",
                "store_result_as_learning_packet",
                "compare_again_next_cycle",
            ],
            "current_objective": (
                journal_state.get("next_objective")
                or f"Resolve blocker {top_blocker.get('id')}: {top_blocker.get('next_action')}"
            ),
            "needs_human": bool(human_unlocks),
            "learning_packet_fields": [
                "blocker_id",
                "action_taken",
                "evidence",
                "cost",
                "agent_ids_used",
                "reusable_pattern",
                "next_better_action",
            ],
        }

    def _telegram_unlock(
        self,
        *,
        top_blocker: dict[str, Any],
        human_unlocks: list[dict[str, Any]],
        paid_job_focus: dict[str, Any],
    ) -> dict[str, Any]:
        first_unlock = human_unlocks[0] if human_unlocks else {}
        message = (
            "NOMAD HUMAN UNLOCK\n"
            f"Top blocker: {top_blocker.get('summary', '')}\n"
            f"Next: {top_blocker.get('next_action', '')}\n"
            f"Paid focus: {paid_job_focus.get('target_offer', '')}\n"
            f"Reply: {first_unlock.get('expected_reply', 'APPROVE_SELF_DEV=yes')}"
        )
        return {
            "schema": "nomad.telegram_human_unlock.v1",
            "send_when": "only_if_human_unlock_required",
            "message": message,
            "primary_unlock_id": first_unlock.get("id", ""),
        }

    @staticmethod
    def _agent_attraction_summary(
        *,
        readiness: dict[str, Any],
        attractor: dict[str, Any],
        public_url: str,
    ) -> dict[str, Any]:
        return {
            "schema": "nomad.agent_attraction_focus.v1",
            "agent_first_not_human_marketing": True,
            "entrypoints": {
                "readiness": f"{public_url}/swarm/ready",
                "join": f"{public_url}/swarm/join",
                "develop": f"{public_url}/swarm/develop",
                "offer": f"{public_url}/agent-attractor",
            },
            "readiness_status": readiness.get("status", ""),
            "attractor_schema": attractor.get("schema", ""),
            "best_agent_to_attract_next": "peer_solver with public evidence for compute/auth/payment blockers",
            "what_agent_gets_back": [
                "arrival_plan",
                "role_and_lane",
                "first_exchange_contract",
                "bounded service or mutual-aid path",
            ],
        }

    @staticmethod
    def _next_action(
        *,
        top_blocker: dict[str, Any],
        human_unlocks: list[dict[str, Any]],
        agent_tasks: list[dict[str, Any]],
        paid_job_focus: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "summary": top_blocker.get("next_action", ""),
            "human_unlock_first": human_unlocks[0] if human_unlocks else None,
            "agent_task_first": agent_tasks[0] if agent_tasks else None,
            "cli_hint": "python main.py --cli mission --json",
            "paid_job_hint": paid_job_focus.get("intake_url", ""),
        }

    @staticmethod
    def _task_counts(tasks: list[dict[str, Any]]) -> dict[str, int]:
        statuses = [str(task.get("status") or "") for task in tasks]
        return {
            "total": len(tasks),
            "paid": statuses.count("paid"),
            "awaiting_payment": statuses.count("awaiting_payment"),
            "draft_ready": statuses.count("draft_ready"),
            "delivered": statuses.count("delivered"),
        }

    @staticmethod
    def _compact_outbound(outbound: dict[str, Any]) -> dict[str, int]:
        contacts = outbound.get("contacts") or {}
        return {
            "contacts_total": int(contacts.get("total") or 0),
            "awaiting_reply": int(contacts.get("awaiting_reply") or 0),
            "followup_ready": int(contacts.get("followup_ready") or 0),
        }

    def _load_state(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"reports": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {"reports": []}
        except Exception:
            return {"reports": []}

    def _record(self, report: dict[str, Any]) -> None:
        state = self._load_state()
        reports = list(state.get("reports") or [])
        compact = {
            "timestamp": report.get("timestamp", ""),
            "top_blocker": report.get("top_blocker", {}),
            "next_action": report.get("next_action", {}),
            "paid_job_focus": report.get("paid_job_focus", {}),
            "human_unlock_count": len(report.get("human_unlocks") or []),
        }
        reports.append(compact)
        state.update(
            {
                "schema": "nomad.mission_control_state.v1",
                "last_report_at": report.get("timestamp", ""),
                "last_top_blocker": report.get("top_blocker", {}),
                "last_next_action": report.get("next_action", {}),
                "reports": reports[-30:],
            }
        )
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
