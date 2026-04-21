import json
import os
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

from nomad_api import serve_in_thread
from nomad_operator_grant import operator_grant, service_approval_scope
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
        self.default_outreach_service_type = (
            os.getenv("NOMAD_OUTREACH_SERVICE_TYPE")
            or ("compute_auth" if (os.getenv("NOMAD_LEAD_FOCUS") or "compute_auth").strip().lower() == "compute_auth" else "human_in_loop")
        ).strip() or "compute_auth"
        self.default_outreach_query = (
            os.getenv("NOMAD_AUTOPILOT_OUTREACH_QUERY") or '"agent-card" "quota" "token" "https://"'
        ).strip()
        self.default_outreach_queries = self._configured_outreach_queries()
        self.default_send_outreach = (
            os.getenv("NOMAD_AUTOPILOT_SEND_OUTREACH", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.default_send_a2a = (
            os.getenv("NOMAD_AUTOPILOT_A2A_SEND", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.default_payment_followup_limit = int(
            os.getenv("NOMAD_AUTOPILOT_PAYMENT_FOLLOWUP_LIMIT", "3")
        )
        self.payment_followup_hours = max(
            1,
            int(os.getenv("NOMAD_AUTOPILOT_PAYMENT_FOLLOWUP_HOURS", "24")),
        )
        self._api_thread = None
        self._outreach_query_cursor = 0
        self._payment_followup_log: dict[str, dict[str, Any]] = {}
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
        decision: Dict[str, Any] = {}
        if check_decision:
            decision = self._decision()
            if not decision.get("should_start"):
                report = self._idle_report(decision)
                self._record_idle(report)
                return report

        if serve_api:
            self._ensure_api()

        effective_send_outreach = self.default_send_outreach if send_outreach is None else bool(send_outreach)
        effective_send_a2a = self.default_send_a2a if send_a2a is None else bool(send_a2a)
        public_api_url = (os.getenv("NOMAD_PUBLIC_API_URL") or "").rstrip("/")
        send_queue_enabled = bool(
            (effective_send_outreach or effective_send_a2a)
            and self._is_public_service_url(public_api_url)
        )
        target = max(0, int(daily_lead_target if daily_lead_target is not None else self.default_daily_lead_target))
        daily_quota_start = self._daily_quota(target)
        base_outreach_limit = max(0, int(outreach_limit or self.default_outreach_limit))
        flush_limit = min(base_outreach_limit, daily_quota_start["remaining_to_send"]) if send_queue_enabled else 0
        service_summary = self._process_service_queue(
            limit=service_limit or self.default_service_limit,
            approval=service_approval or self.default_service_approval,
        )
        payment_followup_queue = self._queue_payment_followups(
            service_summary=service_summary,
            limit=self.default_payment_followup_limit,
            enabled=send_queue_enabled,
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
        reply_conversion = self._convert_replies_to_service_tasks(contact_poll)

        journal_state = self.journal.load()
        selected_objective = (
            (objective or "").strip()
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
        )
        lead_delta = self._lead_conversion_contact_delta(lead_conversion)
        remaining_to_send = max(0, remaining_to_send - lead_delta["sent"])
        remaining_to_prepare = max(0, remaining_to_prepare - lead_delta["prepared"])
        outreach_effective_limit = min(
            base_outreach_limit,
            remaining_to_send if effective_send_outreach else remaining_to_prepare,
        )
        outreach_summary = self._run_outreach(
            self_improvement=self_improvement,
            limit=outreach_effective_limit,
            explicit_query=outreach_query,
            send_outreach=effective_send_outreach,
        )
        daily_quota = self._daily_quota_after(
            start=daily_quota_start,
            contact_summary=contact_summary,
            lead_conversion=lead_conversion,
            outreach_summary=outreach_summary,
        )
        mutual_aid = self._run_mutual_aid_evolution(
            lead_conversion=lead_conversion,
            contact_poll=contact_poll,
            reply_conversion=reply_conversion,
            objective=selected_objective,
        )

        report = {
            "mode": "nomad_autopilot",
            "deal_found": False,
            "timestamp": datetime.now(UTC).isoformat(),
            "objective": selected_objective,
            "profile_id": profile_id,
            "public_api_url": public_api_url,
            "service_approval": service_approval or self.default_service_approval,
            "operator_grant": operator_grant(),
            "decision": decision,
            "service": service_summary,
            "payment_followup_queue": payment_followup_queue,
            "contact_queue": contact_summary,
            "contact_poll": contact_poll,
            "reply_conversion": reply_conversion,
            "self_improvement": self_improvement,
            "lead_conversion": lead_conversion,
            "outreach": outreach_summary,
            "mutual_aid": mutual_aid,
            "daily_quota": daily_quota,
            "analysis": self._analysis(
                objective=selected_objective,
                service_summary=service_summary,
                payment_followup_queue=payment_followup_queue,
                contact_summary=contact_summary,
                contact_poll=contact_poll,
                reply_conversion=reply_conversion,
                lead_conversion=lead_conversion,
                outreach_summary=outreach_summary,
                mutual_aid=mutual_aid,
                self_improvement=self_improvement,
                daily_quota=daily_quota,
            ),
        }
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
            "payment_followups": payment_followups[:5],
            "review_needed_task_ids": review_needed,
            "analysis": (
                f"Service queue processed: worked {len(worked)}, draft_ready {len(draft_ready)}, "
                f"awaiting_payment {len(awaiting_payment)}, review_needed {len(review_needed)}."
            ),
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
                reply_summaries.append(
                    {
                        "contact_id": contact_id,
                        "title": str((updated.get("lead") or {}).get("title") or ""),
                        "endpoint_url": str(updated.get("endpoint_url") or ""),
                        "reply_text": str(reply.get("text") or "")[:240],
                        "classification": str(normalized.get("classification") or ""),
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
    ) -> Dict[str, Any]:
        public_api_url = (os.getenv("NOMAD_PUBLIC_API_URL") or "").rstrip("/")
        query = self._select_outreach_query(
            explicit_query=explicit_query,
            self_improvement=self_improvement,
        )
        if limit <= 0:
            return {
                "mode": "agent_cold_outreach_campaign",
                "deal_found": False,
                "ok": True,
                "skipped": True,
                "reason": "outreach_limit_zero",
                "query": query,
                "analysis": "Outreach skipped because the per-cycle outreach limit is zero.",
            }
        if send_outreach and not self._is_public_service_url(public_api_url):
            return {
                "mode": "agent_cold_outreach_campaign",
                "deal_found": False,
                "ok": False,
                "skipped": True,
                "reason": "public_api_url_required",
                "query": query,
                "analysis": (
                    "Outreach send is disabled because NOMAD_PUBLIC_API_URL is empty or still points to localhost. "
                    "Nomad should expose /service, /tasks and /x402 endpoints before cold outreach."
                ),
            }
        result = self.agent.agent_campaigns.create_campaign_from_discovery(
            limit=limit,
            query=query,
            send=send_outreach,
            service_type=self.default_outreach_service_type,
        )
        result["autopilot_query"] = query
        return result

    def _run_lead_conversion(
        self,
        self_improvement: Dict[str, Any],
        limit: int,
        explicit_query: str,
        send_a2a: bool,
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
        public_api_url = (os.getenv("NOMAD_PUBLIC_API_URL") or "").rstrip("/")
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

    def _query_from_cycle(self, self_improvement: Dict[str, Any]) -> str:
        lead_scout = self_improvement.get("lead_scout") or {}
        queries = lead_scout.get("outreach_queries") or []
        for query in queries:
            cleaned = str(query or "").strip()
            if cleaned:
                return cleaned
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
    ) -> str:
        explicit = (explicit_query or "").strip()
        if explicit:
            return explicit
        suggested = self._query_from_cycle(self_improvement)
        state = self._load()
        configured = list(self.default_outreach_queries)
        if suggested:
            configured = [suggested, *configured]
        rotation = self._dedupe_queries(configured) or [self.default_outreach_query]
        cursor = int(state.get("outreach_query_cursor") or 0)
        query = rotation[cursor % len(rotation)]
        self._outreach_query_cursor = (cursor + 1) % len(rotation)
        return query

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
            for token in ("agent-card", ".well-known", "a2a", "mcp", "agent.json")
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
        state["last_contact_queue"] = self._compact_contacts(report.get("contact_queue") or {})
        state["last_contact_poll"] = self._compact_contact_poll(report.get("contact_poll") or {})
        state["last_reply_conversion"] = self._compact_reply_conversion(report.get("reply_conversion") or {})
        state["last_lead_conversion"] = self._compact_lead_conversion(report.get("lead_conversion") or {})
        state["last_outreach"] = self._compact_outreach(report.get("outreach") or {})
        state["last_mutual_aid"] = self._compact_mutual_aid(report.get("mutual_aid") or {})
        state["last_self_improvement"] = self._compact_self_improvement(report.get("self_improvement") or {})
        state["daily_a2a_quota"] = report.get("daily_quota") or state.get("daily_a2a_quota") or {}
        state["payment_followup_log"] = self._payment_followup_log
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
                "last_contact_queue": {},
                "last_contact_poll": {},
                "last_reply_conversion": {},
                "last_lead_conversion": {},
                "last_outreach": {},
                "last_mutual_aid": {},
                "last_self_improvement": {},
                "daily_a2a_quota": {},
                "payment_followup_log": {},
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
        contact_summary: Dict[str, Any],
        contact_poll: Dict[str, Any],
        reply_conversion: Dict[str, Any],
        lead_conversion: Dict[str, Any],
        outreach_summary: Dict[str, Any],
        mutual_aid: Dict[str, Any],
        self_improvement: Dict[str, Any],
        daily_quota: Dict[str, Any],
    ) -> str:
        worked = len(service_summary.get("worked_task_ids") or [])
        drafts = len(service_summary.get("draft_ready_task_ids") or [])
        awaiting_payment = len(service_summary.get("awaiting_payment_task_ids") or [])
        payment_followups = len(service_summary.get("payment_followups") or [])
        queued_payment_followups = len(payment_followup_queue.get("queued_contact_ids") or [])
        queued_sent = len(contact_summary.get("sent_contact_ids") or [])
        replied = len(contact_poll.get("replied_contact_ids") or [])
        polled = len(contact_poll.get("polled_contact_ids") or [])
        converted = len(reply_conversion.get("created_task_ids") or [])
        conversion_stats = lead_conversion.get("stats") or {}
        outreach_campaign = (outreach_summary.get("campaign") or {})
        outreach_stats = outreach_campaign.get("stats") or {}
        compute_watch = self_improvement.get("compute_watch") or {}
        lead_scout = self_improvement.get("lead_scout") or {}
        lead_count = len(lead_scout.get("leads") or [])
        analysis = (
            f"Nomad autopilot ran objective '{objective}'. "
            f"Service: worked {worked}, draft_ready {drafts}, awaiting_payment {awaiting_payment}. "
            f"Payment follow-ups prepared {payment_followups}. "
            f"Payment follow-up contacts queued {queued_payment_followups}. "
            f"Queue flush sent {queued_sent} queued contact(s). "
            f"Contact poll checked {polled} sent contact(s) and found {replied} reply/replies. "
            f"Reply conversion created {converted} paid-task candidate(s). "
            f"Lead conversion prepared {sum(int(v) for v in conversion_stats.values()) if conversion_stats else 0} conversion artifact(s). "
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
        if mutual_aid and not mutual_aid.get("skipped"):
            analysis += (
                f" Mutual-Aid score is {mutual_aid.get('mutual_aid_score', 0)} "
                f"with truth_density_total={mutual_aid.get('truth_density_total', 0)}."
            )
        return analysis

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
    def _compact_outreach(outreach_summary: Dict[str, Any]) -> Dict[str, Any]:
        campaign = outreach_summary.get("campaign") or {}
        return {
            "campaign_id": campaign.get("campaign_id", ""),
            "stats": campaign.get("stats") or {},
            "query": outreach_summary.get("autopilot_query") or outreach_summary.get("query") or "",
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
            "plan": {
                "module_id": plan.get("module_id", ""),
                "filename": plan.get("filename", ""),
                "applied": bool(plan.get("applied", False)),
            },
            "analysis": mutual_aid.get("analysis", ""),
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
        }
