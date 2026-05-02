import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from agent_contact import AgentContactOutbox, DEFAULT_CONTACT_STORE
from nomad_lead_workbench import NomadLeadWorkbench
from nomad_outbound_tracker import NomadOutboundTracker


ROOT = Path(__file__).resolve().parent
DEFAULT_SWARM_INTAKE_STATE = ROOT / "nomad_swarm_intake_state.json"
DEFAULT_HUMAN_UNLOCKS = ROOT / "nomad_human_unlocks.md"


class NomadSwarmIntake:
    """Prioritize inbound/outbound agent work before spending scarce sends or compute."""

    def __init__(
        self,
        *,
        contact_store_path: Optional[Path] = None,
        state_path: Optional[Path] = None,
        human_unlocks_path: Optional[Path] = None,
        lead_workbench: Optional[NomadLeadWorkbench] = None,
        contact_outbox: Optional[AgentContactOutbox] = None,
        outbound_tracker: Optional[NomadOutboundTracker] = None,
    ) -> None:
        self.contact_store_path = Path(contact_store_path or DEFAULT_CONTACT_STORE)
        self.state_path = Path(state_path or DEFAULT_SWARM_INTAKE_STATE)
        self.human_unlocks_path = Path(human_unlocks_path or DEFAULT_HUMAN_UNLOCKS)
        self.lead_workbench = lead_workbench or NomadLeadWorkbench()
        self.contact_outbox = contact_outbox or AgentContactOutbox(store_path=self.contact_store_path)
        self.outbound_tracker = outbound_tracker or NomadOutboundTracker(contact_store_path=self.contact_store_path)

    def plan(
        self,
        *,
        execute: bool = False,
        send: bool = False,
        poll_limit: int = 5,
        send_limit: int = 2,
        work_limit: int = 5,
        host_cooldown_minutes: int = 60,
        write_unlocks: bool = True,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        state = self._read_json(self.state_path, default={})
        contacts = self._contacts()
        host_cooldowns = self._host_cooldowns(
            contacts=contacts,
            now=now,
            cooldown=timedelta(minutes=max(5, int(host_cooldown_minutes or 60))),
        )
        lead_queue = self._lead_queue()
        dedupe = self._dedupe_leads(lead_queue)
        poll_candidates = self._poll_candidates(contacts, limit=poll_limit)
        send_candidates = self._send_candidates(
            contacts=contacts,
            cooldowns=host_cooldowns,
            limit=send_limit,
        )
        blocked_queued = self._blocked_queued_contacts(contacts, host_cooldowns)
        human_unlocks = self._human_unlocks(
            dedupe=dedupe,
            blocked_queued=blocked_queued,
            host_cooldowns=host_cooldowns,
        )

        actions = self._action_plan(
            poll_candidates=poll_candidates,
            send_candidates=send_candidates,
            dedupe=dedupe,
            blocked_queued=blocked_queued,
            send_enabled=send,
        )
        execution = self._execute(
            execute=execute,
            send=send,
            poll_candidates=poll_candidates,
            send_candidates=send_candidates,
            work_limit=work_limit,
        )
        if write_unlocks:
            self._write_human_unlocks(human_unlocks=human_unlocks, actions=actions)

        state["last_run_at"] = now.isoformat()
        state["last_host_cooldowns"] = host_cooldowns
        state["last_action_plan"] = actions
        state["last_human_unlocks"] = human_unlocks
        state["last_execution"] = execution
        self._write_json(self.state_path, state)

        outbound = self.outbound_tracker.summary(limit=8)
        return {
            "mode": "nomad_swarm_intake",
            "schema": "nomad.swarm_intake.v1",
            "ok": True,
            "generated_at": now.isoformat(),
            "execute_requested": execute,
            "send_enabled": send,
            "contacts": {
                "total": len(contacts),
                "poll_candidates": len(poll_candidates),
                "send_candidates": len(send_candidates),
                "blocked_by_cooldown": len(blocked_queued),
                "host_cooldowns": host_cooldowns,
            },
            "lead_triage": dedupe,
            "action_plan": actions,
            "execution": execution,
            "human_unlocks": human_unlocks,
            "human_unlocks_path": str(self.human_unlocks_path),
            "outbound_next_best_action": outbound.get("next_best_action", ""),
            "analysis": self._analysis(
                poll_count=len(poll_candidates),
                send_count=len(send_candidates),
                blocked_count=len(blocked_queued),
                work_count=int((execution.get("lead_workbench") or {}).get("worked_count") or 0),
                send_enabled=send,
            ),
        }

    def _execute(
        self,
        *,
        execute: bool,
        send: bool,
        poll_candidates: list[dict[str, Any]],
        send_candidates: list[dict[str, Any]],
        work_limit: int,
    ) -> dict[str, Any]:
        if not execute:
            return {"executed": False, "reason": "dry_run_plan_only"}
        polled: list[dict[str, Any]] = []
        for contact in poll_candidates:
            polled.append(self.contact_outbox.poll_contact(str(contact.get("contact_id") or "")))
        sent: list[dict[str, Any]] = []
        if send:
            for contact in send_candidates:
                sent.append(self.contact_outbox.send_contact(str(contact.get("contact_id") or "")))
        lead_workbench = self.lead_workbench.status(limit=work_limit, work=True)
        return {
            "executed": True,
            "polled_contact_ids": [str(item.get("contact", {}).get("contact_id") or "") for item in polled],
            "sent_contact_ids": [str(item.get("contact", {}).get("contact_id") or "") for item in sent],
            "send_failed_contact_ids": [
                str(item.get("contact", {}).get("contact_id") or "")
                for item in sent
                if str(item.get("contact", {}).get("status") or "") == "send_failed"
            ],
            "lead_workbench": {
                "worked_count": lead_workbench.get("worked_count", 0),
                "queue_count": lead_workbench.get("queue_count", 0),
                "top_next_action": (lead_workbench.get("self_help") or {}).get("top_next_action", ""),
            },
        }

    def _lead_queue(self) -> list[dict[str, Any]]:
        try:
            conversions = self.lead_workbench._load_conversions()
            products = self.lead_workbench._load_products()
            state = self.lead_workbench._load_state()
            return self.lead_workbench._build_queue(
                conversions=conversions,
                products=products,
                state=state,
            )
        except Exception:
            status = self.lead_workbench.status(limit=25, work=False)
            return [item for item in status.get("queue") or [] if isinstance(item, dict)]

    @staticmethod
    def _dedupe_leads(queue: list[dict[str, Any]], *, limit: int = 5) -> dict[str, Any]:
        groups: dict[str, dict[str, Any]] = {}
        for item in queue:
            key = NomadSwarmIntake._lead_key(item)
            group = groups.setdefault(
                key,
                {
                    "key": key,
                    "url": str(item.get("url") or ""),
                    "title": str(item.get("title") or ""),
                    "service_type": str(item.get("service_type") or ""),
                    "best_priority_score": 0.0,
                    "count": 0,
                    "executable_count": 0,
                    "human_blocked_count": 0,
                    "top_action": "",
                    "item_ids": [],
                },
            )
            score = float(item.get("priority_score") or 0.0)
            group["count"] += 1
            group["best_priority_score"] = max(float(group["best_priority_score"]), score)
            if item.get("can_execute_without_human"):
                group["executable_count"] += 1
            if item.get("human_gate"):
                group["human_blocked_count"] += 1
            if not group["top_action"] or score >= float(group["best_priority_score"]):
                group["top_action"] = str(item.get("safe_next_action") or "")
            if len(group["item_ids"]) < 5:
                group["item_ids"].append(str(item.get("item_id") or ""))
        ordered = sorted(
            groups.values(),
            key=lambda item: (
                -float(item.get("best_priority_score") or 0.0),
                -int(item.get("executable_count") or 0),
                str(item.get("url") or item.get("title") or ""),
            ),
        )
        return {
            "schema": "nomad.lead_triage.v1",
            "raw_queue_count": len(queue),
            "unique_lead_count": len(ordered),
            "duplicate_count": max(0, len(queue) - len(ordered)),
            "top_unique_leads": ordered[: max(1, min(limit, 10))],
        }

    @staticmethod
    def _lead_key(item: dict[str, Any]) -> str:
        url = str(item.get("url") or "").strip().lower().rstrip("/")
        if url:
            return url
        title = " ".join(str(item.get("title") or "").strip().lower().split())
        service_type = str(item.get("service_type") or "").strip().lower()
        return f"{service_type}:{title}"

    def _contacts(self) -> list[dict[str, Any]]:
        payload = self._read_json(self.contact_store_path, default={"contacts": {}})
        contacts = list((payload.get("contacts") or {}).values())
        contacts = [item for item in contacts if isinstance(item, dict)]
        contacts.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
        return contacts

    @staticmethod
    def _host_cooldowns(
        *,
        contacts: list[dict[str, Any]],
        now: datetime,
        cooldown: timedelta,
    ) -> dict[str, dict[str, Any]]:
        cooldowns: dict[str, dict[str, Any]] = {}
        for contact in contacts:
            host = NomadSwarmIntake._host(contact.get("endpoint_url"))
            if not host:
                continue
            for attempt in contact.get("attempts") or []:
                if not isinstance(attempt, dict):
                    continue
                status = str(attempt.get("status") or "")
                message = str(attempt.get("message") or "").lower()
                if status != "send_failed" or "rate limit" not in message and "rate limited" not in message:
                    continue
                at = NomadSwarmIntake._parse_time(str(attempt.get("at") or contact.get("updated_at") or ""))
                if not at:
                    continue
                until = at + cooldown
                if until <= now:
                    continue
                previous = cooldowns.get(host) or {}
                if str(until.isoformat()) > str(previous.get("until") or ""):
                    cooldowns[host] = {
                        "until": until.isoformat(),
                        "reason": "remote_rate_limited",
                        "last_contact_id": str(contact.get("contact_id") or ""),
                    }
        return cooldowns

    @staticmethod
    def _poll_candidates(contacts: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
        candidates = [
            item
            for item in contacts
            if str(item.get("status") or "") == "sent" and str(item.get("remote_task_id") or "")
        ]
        candidates.sort(key=lambda item: str(item.get("last_polled_at") or item.get("updated_at") or ""))
        return candidates[: max(0, min(int(limit or 0), 25))]

    @staticmethod
    def _send_candidates(
        *,
        contacts: list[dict[str, Any]],
        cooldowns: dict[str, dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for contact in contacts:
            if str(contact.get("status") or "") != "queued":
                continue
            host = NomadSwarmIntake._host(contact.get("endpoint_url"))
            if host and host in cooldowns:
                continue
            candidates.append(contact)
        candidates.sort(key=lambda item: str(item.get("created_at") or ""))
        return candidates[: max(0, min(int(limit or 0), 10))]

    @staticmethod
    def _blocked_queued_contacts(
        contacts: list[dict[str, Any]],
        cooldowns: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        blocked: list[dict[str, Any]] = []
        for contact in contacts:
            if str(contact.get("status") or "") != "queued":
                continue
            host = NomadSwarmIntake._host(contact.get("endpoint_url"))
            if host in cooldowns:
                blocked.append(
                    {
                        "contact_id": str(contact.get("contact_id") or ""),
                        "endpoint_url": str(contact.get("endpoint_url") or ""),
                        "host": host,
                        "cooldown_until": cooldowns[host].get("until"),
                    }
                )
        return blocked

    @staticmethod
    def _action_plan(
        *,
        poll_candidates: list[dict[str, Any]],
        send_candidates: list[dict[str, Any]],
        dedupe: dict[str, Any],
        blocked_queued: list[dict[str, Any]],
        send_enabled: bool,
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        if poll_candidates:
            actions.append(
                {
                    "action": "poll_sent_contacts",
                    "why": "existing remote tasks can produce replies without consuming new send quota",
                    "contact_ids": [str(item.get("contact_id") or "") for item in poll_candidates],
                }
            )
        if send_candidates and send_enabled:
            actions.append(
                {
                    "action": "send_cooldown_clear_agent_contacts",
                    "why": "queued A2A endpoints are not under host cooldown",
                    "contact_ids": [str(item.get("contact_id") or "") for item in send_candidates],
                }
            )
        elif send_candidates:
            actions.append(
                {
                    "action": "hold_send_candidates_until_send_enabled",
                    "why": "dry-run or no-send mode keeps outreach bounded",
                    "contact_ids": [str(item.get("contact_id") or "") for item in send_candidates],
                }
            )
        if blocked_queued:
            actions.append(
                {
                    "action": "respect_host_cooldown",
                    "why": "remote endpoint reported rate limiting",
                    "blocked_contact_ids": [str(item.get("contact_id") or "") for item in blocked_queued[:10]],
                }
            )
        top_leads = dedupe.get("top_unique_leads") or []
        if top_leads:
            actions.append(
                {
                    "action": "work_top_unique_leads",
                    "why": "deduped lead work improves product signal under scarce compute",
                    "lead_keys": [str(item.get("key") or "") for item in top_leads[:5]],
                }
            )
        return actions

    @staticmethod
    def _human_unlocks(
        *,
        dedupe: dict[str, Any],
        blocked_queued: list[dict[str, Any]],
        host_cooldowns: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        unlocks: list[dict[str, Any]] = []
        for lead in dedupe.get("top_unique_leads") or []:
            if int(lead.get("human_blocked_count") or 0) <= 0:
                continue
            unlocks.append(
                {
                    "type": "public_post_or_access_approval",
                    "title": str(lead.get("title") or lead.get("url") or lead.get("key") or ""),
                    "needed": "Approve a bounded public post/PR plan or provide a machine endpoint/fact URL.",
                    "expected_reply": "APPROVAL_GRANTED=<scope> or FACT_URL=https://...",
                }
            )
        if blocked_queued:
            unlocks.append(
                {
                    "type": "remote_rate_limit",
                    "title": "A2A host cooldown active",
                    "needed": "Wait for cooldown or provide a better agent endpoint not sharing the limited host.",
                    "expected_reply": "NEW_AGENT_ENDPOINT=https://... or WAIT",
                    "hosts": sorted(host_cooldowns.keys()),
                }
            )
        return unlocks[:10]

    def _write_human_unlocks(
        self,
        *,
        human_unlocks: list[dict[str, Any]],
        actions: list[dict[str, Any]],
    ) -> None:
        lines = [
            "# Nomad Human Unlocks",
            "",
            f"Updated: {datetime.now(UTC).isoformat()}",
            "",
            "## Next Actions",
        ]
        for action in actions[:8]:
            lines.append(f"- {action.get('action')}: {action.get('why')}")
        lines.extend(["", "## Unlocks"])
        if not human_unlocks:
            lines.append("- No human unlock required right now. Continue polling, deduping, and private lead work.")
        for unlock in human_unlocks:
            lines.append(f"- {unlock.get('type')}: {unlock.get('title')}")
            lines.append(f"  Needed: {unlock.get('needed')}")
            lines.append(f"  Reply: `{unlock.get('expected_reply')}`")
        self.human_unlocks_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    @staticmethod
    def _host(value: Any) -> str:
        try:
            return (urlparse(str(value or "")).hostname or "").lower()
        except Exception:
            return ""

    @staticmethod
    def _parse_time(value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None

    @staticmethod
    def _read_json(path: Path, *, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return dict(default)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else dict(default)
        except Exception:
            return dict(default)

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _analysis(
        *,
        poll_count: int,
        send_count: int,
        blocked_count: int,
        work_count: int,
        send_enabled: bool,
    ) -> str:
        send_note = "send enabled" if send_enabled else "send held"
        return (
            "Swarm intake triage complete: "
            f"{poll_count} poll candidate(s), {send_count} send candidate(s), "
            f"{blocked_count} queued contact(s) held by cooldown, "
            f"{work_count} lead(s) worked. {send_note}."
        )
