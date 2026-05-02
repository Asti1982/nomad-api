import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_campaign import DEFAULT_CAMPAIGN_STORE
from agent_contact import DEFAULT_CONTACT_STORE
from agent_service import DEFAULT_TASK_STORE
from nomad_public_url import preferred_public_base_url


ROOT = Path(__file__).resolve().parent
DEFAULT_AUTOPILOT_STATE = ROOT / "nomad_autopilot_state.json"


class NomadOutboundTracker:
    """Unified tracking view over Nomad's outbound contacts, campaigns, and follow-up queues."""

    def __init__(
        self,
        contact_store_path: Optional[Path] = None,
        campaign_store_path: Optional[Path] = None,
        task_store_path: Optional[Path] = None,
        autopilot_state_path: Optional[Path] = None,
    ) -> None:
        self.contact_store_path = Path(contact_store_path or DEFAULT_CONTACT_STORE)
        self.campaign_store_path = Path(campaign_store_path or DEFAULT_CAMPAIGN_STORE)
        self.task_store_path = Path(task_store_path or DEFAULT_TASK_STORE)
        self.autopilot_state_path = Path(autopilot_state_path or DEFAULT_AUTOPILOT_STATE)
        self.public_api_url = preferred_public_base_url(request_base_url="http://127.0.0.1:8787")

    def summary(self, limit: int = 10) -> Dict[str, Any]:
        cap = max(1, min(int(limit or 10), 25))
        contacts = self._contacts()
        campaigns = self._campaigns()
        tasks = self._tasks()
        autopilot = self._autopilot_state()
        contact_statuses = self._count_by(contacts, "status")
        campaign_statuses = self._count_by(campaigns, "status")
        task_statuses = self._count_by(tasks, "status")
        recent_threads = self._recent_threads(contacts, cap)
        recent_actions = self._recent_actions(contacts, campaigns, cap)
        next_best_action = self._next_best_action(
            contacts=contacts,
            campaigns=campaigns,
            tasks=tasks,
            recent_threads=recent_threads,
        )
        return {
            "mode": "nomad_outbound_tracking",
            "deal_found": False,
            "ok": True,
            "public_api_url": self.public_api_url,
            "contacts": {
                "total": len(contacts),
                "status_counts": contact_statuses,
                "awaiting_reply": int(contact_statuses.get("sent", 0)),
                "replied": int(contact_statuses.get("replied", 0)),
                "followup_ready": sum(1 for item in contacts if bool(item.get("followup_ready"))),
                "remote_tasks": sum(1 for item in contacts if item.get("remote_task_id")),
                "recent_threads": recent_threads,
            },
            "campaigns": {
                "total": len(campaigns),
                "status_counts": campaign_statuses,
                "latest": self._compact_campaign(campaigns[0]) if campaigns else {},
            },
            "tasks": {
                "total": len(tasks),
                "status_counts": task_statuses,
                "awaiting_payment": [
                    self._compact_task(item)
                    for item in tasks
                    if str(item.get("status") or "") == "awaiting_payment"
                ][:cap],
                "paid_ready": [
                    self._compact_task(item)
                    for item in tasks
                    if str(item.get("status") or "") == "paid"
                ][:cap],
                "draft_ready": [
                    self._compact_task(item)
                    for item in tasks
                    if str(item.get("status") or "") == "draft_ready"
                ][:cap],
            },
            "autonomous_tracking": {
                "last_run_at": str(autopilot.get("last_run_at") or ""),
                "last_objective": str(autopilot.get("last_objective") or ""),
                "last_public_api_url": str(autopilot.get("last_public_api_url") or ""),
                "payment_followup_log_count": len(autopilot.get("payment_followup_log") or {}),
                "agent_followup_log_count": len(autopilot.get("agent_followup_log") or {}),
                "converted_reply_count": len(autopilot.get("converted_reply_contact_ids") or []),
                "last_payment_followup_queue": autopilot.get("last_payment_followup_queue") or {},
                "last_contact_queue": autopilot.get("last_contact_queue") or {},
                "last_contact_poll": autopilot.get("last_contact_poll") or {},
                "last_agent_followup_queue": autopilot.get("last_agent_followup_queue") or {},
                "last_agent_followup_send": autopilot.get("last_agent_followup_send") or {},
            },
            "recent_actions": recent_actions,
            "next_best_action": next_best_action,
            "analysis": self._analysis(
                contact_statuses=contact_statuses,
                campaign_statuses=campaign_statuses,
                task_statuses=task_statuses,
                next_best_action=next_best_action,
            ),
        }

    def _contacts(self) -> List[Dict[str, Any]]:
        contacts = list((self._read_json(self.contact_store_path).get("contacts") or {}).values())
        contacts.sort(
            key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
            reverse=True,
        )
        return [item for item in contacts if isinstance(item, dict)]

    def _campaigns(self) -> List[Dict[str, Any]]:
        campaigns = list((self._read_json(self.campaign_store_path).get("campaigns") or {}).values())
        campaigns.sort(
            key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
            reverse=True,
        )
        return [item for item in campaigns if isinstance(item, dict)]

    def _tasks(self) -> List[Dict[str, Any]]:
        tasks = list((self._read_json(self.task_store_path).get("tasks") or {}).values())
        tasks.sort(
            key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
            reverse=True,
        )
        return [item for item in tasks if isinstance(item, dict)]

    def _autopilot_state(self) -> Dict[str, Any]:
        return self._read_json(self.autopilot_state_path)

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _count_by(items: List[Dict[str, Any]], key: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in items:
            value = str(item.get(key) or "unknown").strip() or "unknown"
            counts[value] = counts.get(value, 0) + 1
        return counts

    def _recent_threads(self, contacts: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        threads: List[Dict[str, Any]] = []
        for item in contacts[: max(limit * 2, 8)]:
            last_reply = item.get("last_reply") if isinstance(item.get("last_reply"), dict) else {}
            followup = item.get("followup_recommendation") if isinstance(item.get("followup_recommendation"), dict) else {}
            threads.append(
                {
                    "contact_id": str(item.get("contact_id") or ""),
                    "status": str(item.get("status") or ""),
                    "service_type": str(item.get("service_type") or ""),
                    "endpoint_url": str(item.get("endpoint_url") or ""),
                    "updated_at": str(item.get("updated_at") or item.get("created_at") or ""),
                    "remote_task_id": str(item.get("remote_task_id") or ""),
                    "followup_ready": bool(item.get("followup_ready")),
                    "last_reply_excerpt": str(last_reply.get("text") or "")[:180],
                    "followup_next_path": str(followup.get("next_path") or ""),
                }
            )
        return threads[:limit]

    def _recent_actions(
        self,
        contacts: List[Dict[str, Any]],
        campaigns: List[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        for contact in contacts:
            contact_id = str(contact.get("contact_id") or "")
            endpoint_url = str(contact.get("endpoint_url") or "")
            service_type = str(contact.get("service_type") or "")
            created_at = str(contact.get("created_at") or "")
            if created_at:
                actions.append(
                    {
                        "at": created_at,
                        "kind": "contact_queued",
                        "contact_id": contact_id,
                        "service_type": service_type,
                        "endpoint_url": endpoint_url,
                        "summary": f"Queued {contact_id} for {endpoint_url}.",
                    }
                )
            for attempt in contact.get("attempts") or []:
                if not isinstance(attempt, dict):
                    continue
                actions.append(
                    {
                        "at": str(attempt.get("at") or contact.get("updated_at") or ""),
                        "kind": str(attempt.get("status") or "contact_attempt"),
                        "contact_id": contact_id,
                        "service_type": service_type,
                        "endpoint_url": endpoint_url,
                        "summary": str(attempt.get("message") or "")[:180],
                    }
                )
            last_reply = contact.get("last_reply") if isinstance(contact.get("last_reply"), dict) else {}
            if last_reply.get("text"):
                actions.append(
                    {
                        "at": str(last_reply.get("updated_at") or contact.get("updated_at") or ""),
                        "kind": "reply_received",
                        "contact_id": contact_id,
                        "service_type": service_type,
                        "endpoint_url": endpoint_url,
                        "summary": str(last_reply.get("text") or "")[:180],
                    }
                )
        for campaign in campaigns:
            stats = campaign.get("stats") if isinstance(campaign.get("stats"), dict) else {}
            actions.append(
                {
                    "at": str(campaign.get("updated_at") or campaign.get("created_at") or ""),
                    "kind": "campaign_" + str(campaign.get("status") or "unknown"),
                    "campaign_id": str(campaign.get("campaign_id") or ""),
                    "summary": (
                        f"Campaign {campaign.get('campaign_id', '')}: queued {stats.get('queued', 0)}, "
                        f"sent {stats.get('sent', 0)}, blocked {stats.get('blocked', 0)}."
                    ),
                }
            )
        actions.sort(key=lambda item: str(item.get("at") or ""), reverse=True)
        return actions[:limit]

    def _next_best_action(
        self,
        *,
        contacts: List[Dict[str, Any]],
        campaigns: List[Dict[str, Any]],
        tasks: List[Dict[str, Any]],
        recent_threads: List[Dict[str, Any]],
    ) -> str:
        followup_ready = next((item for item in contacts if bool(item.get("followup_ready"))), None)
        if followup_ready:
            return (
                f"Queue the role-specific follow-up for {followup_ready.get('contact_id')} "
                f"at {followup_ready.get('endpoint_url')}."
            )
        queued = next((item for item in contacts if str(item.get("status") or "") == "queued"), None)
        if queued:
            return f"Send queued contact {queued.get('contact_id')} to {queued.get('endpoint_url')}."
        sent = next((item for item in contacts if str(item.get("status") or "") == "sent"), None)
        if sent:
            return f"Poll sent contact {sent.get('contact_id')} for a remote task update."
        awaiting_payment = next((item for item in tasks if str(item.get("status") or "") == "awaiting_payment"), None)
        if awaiting_payment:
            return f"Follow up on payment for task {awaiting_payment.get('task_id')} and ask for tx_hash or x402 signature."
        queued_campaign = next((item for item in campaigns if str(item.get("status") or "") == "queued"), None)
        if queued_campaign:
            return f"Flush queued campaign {queued_campaign.get('campaign_id')} into outbound sends."
        if recent_threads:
            return f"Review the most recent outbound thread {recent_threads[0].get('contact_id')} for reuse or closure."
        return "Run one bounded discovery or cold-outreach cycle to create the next outbound thread."

    @staticmethod
    def _compact_campaign(campaign: Dict[str, Any]) -> Dict[str, Any]:
        stats = campaign.get("stats") if isinstance(campaign.get("stats"), dict) else {}
        return {
            "campaign_id": str(campaign.get("campaign_id") or ""),
            "status": str(campaign.get("status") or ""),
            "updated_at": str(campaign.get("updated_at") or campaign.get("created_at") or ""),
            "service_type": str(campaign.get("service_type") or ""),
            "stats": {
                "queued": int(stats.get("queued") or 0),
                "sent": int(stats.get("sent") or 0),
                "blocked": int(stats.get("blocked") or 0),
                "failed": int(stats.get("failed") or 0),
            },
        }

    @staticmethod
    def _compact_task(task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task_id": str(task.get("task_id") or ""),
            "status": str(task.get("status") or ""),
            "service_type": str(task.get("service_type") or ""),
            "updated_at": str(task.get("updated_at") or task.get("created_at") or ""),
            "requester_agent": str(task.get("requester_agent") or ""),
            "callback_url": str(task.get("callback_url") or ""),
            "budget_native": task.get("budget_native"),
        }

    @staticmethod
    def _analysis(
        *,
        contact_statuses: Dict[str, int],
        campaign_statuses: Dict[str, int],
        task_statuses: Dict[str, int],
        next_best_action: str,
    ) -> str:
        return (
            "Nomad outbound tracking is live. "
            f"Contacts: {', '.join(f'{key}={value}' for key, value in sorted(contact_statuses.items())) or 'none'}. "
            f"Campaigns: {', '.join(f'{key}={value}' for key, value in sorted(campaign_statuses.items())) or 'none'}. "
            f"Tasks: {', '.join(f'{key}={value}' for key, value in sorted(task_statuses.items())) or 'none'}. "
            f"Next best action: {next_best_action}"
        )
