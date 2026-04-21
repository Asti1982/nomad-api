import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional


class SelfDevelopmentJournal:
    """Persistent memory for Nomad's bounded self-development cycles."""

    def __init__(self, path: Optional[Path] = None, max_entries: int = 50) -> None:
        self.path = path or Path(__file__).resolve().parent / "nomad_self_state.json"
        self.max_entries = max_entries

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self._empty_state()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return self._empty_state()
            payload.setdefault("cycle_count", len(payload.get("cycles") or []))
            payload.setdefault("cycles", [])
            payload.setdefault("current_objective", self.default_objective())
            payload.setdefault("next_objective", self.default_objective())
            payload.setdefault("open_human_unlock", None)
            payload.setdefault("self_development_unlocks", [])
            payload.setdefault("last_cycle_at", "")
            payload.setdefault("last_agent_pain_solution", None)
            payload.setdefault("last_autonomous_development", None)
            return payload
        except Exception:
            return self._empty_state()

    def record_cycle(self, result: Dict[str, Any]) -> Dict[str, Any]:
        state = self.load()
        cycles = list(state.get("cycles") or [])
        entry = self._cycle_entry(result)
        cycles.append(entry)
        cycles = cycles[-self.max_entries :]

        next_objective = self.choose_next_objective(result, previous_state=state)
        self_development_unlocks = self.propose_human_unlocks(result, previous_state=state)
        state.update(
            {
                "last_cycle_at": entry["timestamp"],
                "cycle_count": int(state.get("cycle_count") or 0) + 1,
                "current_objective": result.get("objective") or state.get("next_objective") or self.default_objective(),
                "next_objective": next_objective,
                "open_human_unlock": self._compact_unlock(result),
                "self_development_unlocks": self_development_unlocks,
                "last_external_review_count": result.get("external_review_count", 0),
                "last_local_actions": [
                    self._compact_action(item)
                    for item in (result.get("local_actions") or [])[:4]
                ],
                "last_lead": (result.get("lead_scout") or {}).get("active_lead"),
                "last_agent_pain_solution": self._compact_agent_pain_solution(result),
                "last_autonomous_development": self._compact_autonomous_development(result),
                "cycles": cycles,
            }
        )
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return state

    def choose_next_objective(
        self,
        result: Optional[Dict[str, Any]] = None,
        previous_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        result = result or {}
        previous_state = previous_state or self.load()

        lead_scout = result.get("lead_scout") or {}
        active_lead = lead_scout.get("active_lead") or previous_state.get("last_lead")
        if active_lead:
            url = active_lead.get("url") or active_lead.get("name") or "active lead"
            pain = active_lead.get("pain") or "visible infrastructure pain"
            pain_class = active_lead.get("addressable_label") or active_lead.get("recommended_service_type") or ""
            class_text = f" in {pain_class}" if pain_class else ""
            return (
                f"Work active lead {url}{class_text}. Validate pain: {pain}. Draft the first useful help action "
                "without posting publicly."
            )

        human_unlock = self._compact_unlock(result) or previous_state.get("open_human_unlock")
        if human_unlock:
            name = human_unlock.get("candidate_name", "open unlock")
            category = human_unlock.get("category", "self_improvement")
            return (
                f"Reduce dependency on human unlock '{name}' in {category}: find an alternative, "
                "a skip path, or a clearer verification step."
            )

        agent_solution = self._compact_agent_pain_solution(result) or previous_state.get("last_agent_pain_solution")
        if agent_solution and agent_solution.get("next_nomad_action"):
            return (
                f"Apply reusable agent solution '{agent_solution.get('title')}' for "
                f"{agent_solution.get('pain_type')}: {agent_solution.get('next_nomad_action')}"
            )

        local_actions = result.get("local_actions") or previous_state.get("last_local_actions") or []
        for action in local_actions:
            if not action.get("requires_human"):
                return (
                    f"Execute local self-improvement: {action.get('title', 'improve Nomad')} "
                    f"because {action.get('reason', 'it improves Nomad')}."
                )

        return self.default_objective()

    def propose_human_unlocks(
        self,
        result: Optional[Dict[str, Any]] = None,
        previous_state: Optional[Dict[str, Any]] = None,
    ) -> list[Dict[str, Any]]:
        result = result or {}
        previous_state = previous_state or self.load()
        unlocks: list[Dict[str, Any]] = []

        lead_scout = result.get("lead_scout") or {}
        active_lead = lead_scout.get("active_lead") or previous_state.get("last_lead")
        if active_lead:
            url = active_lead.get("url") or active_lead.get("name") or "active lead"
            pain = active_lead.get("pain") or "visible infrastructure pain"
            pain_class = active_lead.get("addressable_label") or active_lead.get("recommended_service_type") or ""
            unlocks.append(
                self._unlock_payload(
                    candidate_id="approve-active-lead-help",
                    candidate_name="Approve help for active agent lead",
                    short_ask="Approve whether Nomad may draft help for the active lead.",
                    human_action=(
                        f"Open/review {url} and decide whether Nomad should prepare a public GitHub comment, "
                        "a private draft only, or a PR/repro plan."
                    ),
                    human_deliverable=(
                        "`APPROVE_LEAD_HELP=comment`, `APPROVE_LEAD_HELP=draft_only`, "
                        "`APPROVE_LEAD_HELP=pr_plan`, or `/skip last`."
                    ),
                    reason=(
                        f"Nomad found an active lead with pain signal: {pain}"
                        f"{f' in {pain_class}' if pain_class else ''}. It should not contact or post "
                        "publicly without human permission."
                    ),
                    success_criteria=[
                        "Nomad knows whether it may draft public outreach, private-only help, or a PR/repro plan.",
                        "No public comment is posted without explicit human approval.",
                    ],
                    example_response="APPROVE_LEAD_HELP=draft_only",
                )
            )

        open_unlock = self._compact_unlock(result) or previous_state.get("open_human_unlock")
        if open_unlock and open_unlock.get("candidate_id") == "fresh-agent-customer-lead":
            unlocks.append(
                self._unlock_payload(
                    candidate_id="seed-agent-customer-source",
                    candidate_name="Seed one agent-customer lead source",
                    short_ask="Give Nomad one concrete place to scout, or approve public GitHub scouting.",
                    human_action=(
                        "Send one exact repo, issue, tool, community, or search surface where agents show infra pain; "
                        "or explicitly allow Nomad to keep searching public GitHub issues."
                    ),
                    human_deliverable=(
                        "`LEAD_URL=https://...`, `SCOUT_SURFACE=https://...`, "
                        "`SCOUT_PERMISSION=public_github`, or `/skip last`."
                    ),
                    reason=(
                        "Nomad's next development loop improves fastest when the human unlocks one concrete frontier "
                        "instead of leaving lead discovery abstract."
                    ),
                    success_criteria=[
                        "Nomad has one concrete public surface or lead URL to work first.",
                        "The next cycle can validate one pain signal without asking the human to scout manually.",
                    ],
                    example_response="SCOUT_PERMISSION=public_github",
                )
            )

        local_actions = result.get("local_actions") or previous_state.get("last_local_actions") or []
        if any(action.get("requires_human") for action in local_actions):
            unlocks.append(
                self._unlock_payload(
                    candidate_id="confirm-fallback-brain-priority",
                    candidate_name="Confirm fallback brain priority",
                    short_ask="Choose which fallback brain Nomad should prefer while one lane is blocked.",
                    human_action=(
                        "Tell Nomad which fallback-brain path to prefer while GitHub Models is rate-limited or partial."
                    ),
                    human_deliverable=(
                        "`COMPUTE_PRIORITY=huggingface`, `COMPUTE_PRIORITY=modal`, "
                        "`COMPUTE_PRIORITY=github_later`, or `/skip last`."
                    ),
                    reason=(
                        "Self-development needs stable fallback brains; human preference prevents Nomad from repeatedly "
                        "asking for the same blocked compute unlock."
                    ),
                    success_criteria=[
                        "Nomad stops repeating a blocked compute unlock as its primary self-development blocker.",
                        "The next cycle uses the selected fallback path first.",
                    ],
                    example_response="COMPUTE_PRIORITY=huggingface",
                )
            )

        if not unlocks:
            unlocks.append(
                self._unlock_payload(
                    candidate_id="approve-next-self-dev-step",
                    candidate_name="Approve next self-development step",
                    short_ask="Approve the next bounded self-development action Nomad should execute.",
                    human_action=(
                        "Review Nomad's next autonomous objective and reply with approval, a narrower scope, or skip."
                    ),
                    human_deliverable=(
                        "`APPROVE_SELF_DEV=yes`, `SELF_DEV_SCOPE=<one sentence>`, or `/skip last`."
                    ),
                    reason=(
                        "Nomad should keep its self-development bounded and auditable instead of silently drifting."
                    ),
                    success_criteria=[
                        "Nomad has explicit permission or a narrower scope for the next autonomous cycle.",
                        "The next cycle produces one verifiable result and one next unlock.",
                    ],
                    example_response="APPROVE_SELF_DEV=yes",
                )
            )
        return unlocks[:3]

    @staticmethod
    def default_objective() -> str:
        return (
            "Find one concrete AI-agent compute/auth pain lead, improve Nomad's scout quality, "
            "and convert it into one verifiable next action or paid help path."
        )

    def status_text(self) -> str:
        state = self.load()
        lines = [
            "Nomad self-development",
            f"Cycles recorded: {state.get('cycle_count', 0)}",
            f"Last cycle: {state.get('last_cycle_at') or 'never'}",
            f"Next objective: {state.get('next_objective') or self.default_objective()}",
        ]
        unlock = state.get("open_human_unlock")
        if unlock:
            lines.append(
                f"Open human unlock: {unlock.get('candidate_name')} ({unlock.get('category')})"
            )
        dev_unlocks = state.get("self_development_unlocks") or []
        if dev_unlocks:
            first = dev_unlocks[0]
            lines.append(f"Next human self-dev unlock: {first.get('short_ask')}")
        agent_solution = state.get("last_agent_pain_solution") or {}
        if agent_solution:
            lines.append(
                f"Last agent pain solution: {agent_solution.get('title')} ({agent_solution.get('pain_type')})"
            )
        autonomous = state.get("last_autonomous_development") or {}
        if autonomous:
            lines.append(
                f"Last autonomous development: {autonomous.get('title') or autonomous.get('reason') or 'none'}"
            )
        return "\n".join(lines)

    def codex_task_prompt(self, autopilot_state_path: Optional[Path] = None) -> str:
        state = self.load()
        autopilot_path = autopilot_state_path or Path(__file__).resolve().parent / "nomad_autopilot_state.json"
        autopilot = self._load_optional_json(autopilot_path)
        compute_watch = (autopilot.get("last_self_improvement") or {}).get("compute_watch") or {}
        lead_watch = (autopilot.get("last_self_improvement") or {}).get("lead_watch") or {}
        open_unlock = state.get("open_human_unlock") or {}
        dev_unlocks = state.get("self_development_unlocks") or []
        next_unlock = dev_unlocks[0] if dev_unlocks else {}
        lines = [
            "Nomad self-development task for Codex",
            "",
            "Please implement the next bounded improvement for Nomad directly in this repo.",
            "",
            f"Primary objective: {state.get('next_objective') or self.default_objective()}",
        ]
        current_objective = state.get("current_objective") or ""
        if current_objective:
            lines.append(f"Current objective: {current_objective}")
        if state.get("last_lead"):
            lead = state["last_lead"]
            active_line = (
                f"Active lead: {(lead.get('url') or lead.get('name') or '').strip()} | "
                f"pain: {lead.get('pain') or 'unknown'} | "
                f"class: {lead.get('addressable_label') or lead.get('recommended_service_type') or 'unknown'}"
            )
            if lead.get("quote_summary"):
                active_line += f" | quote: {lead.get('quote_summary')}"
            if lead.get("product_package"):
                active_line += f" | product: {lead.get('product_package')}"
            lines.append(active_line)
        if compute_watch:
            lines.append(
                "Compute watch: "
                f"needs_attention={bool(compute_watch.get('needs_attention'))}, "
                f"brain_count={compute_watch.get('brain_count', 0)}, "
                f"active_lanes={', '.join(compute_watch.get('active_lanes') or []) or 'none'}."
            )
            if compute_watch.get("headline"):
                lines.append(f"Compute headline: {compute_watch['headline']}")
        if lead_watch:
            lines.append(
                "Lead watch: "
                f"lead_count={lead_watch.get('lead_count', 0)}, "
                f"compute_lead_count={lead_watch.get('compute_lead_count', 0)}."
            )
        if open_unlock:
            lines.append(
                f"Open unlock: {open_unlock.get('candidate_name') or 'unknown'} | {open_unlock.get('short_ask') or ''}"
            )
        if next_unlock:
            lines.append(
                f"Next human self-dev unlock: {next_unlock.get('short_ask') or next_unlock.get('candidate_name') or ''}"
            )
        agent_solution = state.get("last_agent_pain_solution") or {}
        if agent_solution:
            lines.append(
                "Last reusable agent solution: "
                f"{agent_solution.get('title') or 'unknown'} for {agent_solution.get('pain_type') or 'unknown'}; "
                f"next self-apply: {agent_solution.get('next_nomad_action') or 'not recorded'}"
            )
        public_url = autopilot.get("last_public_api_url") or ""
        if public_url:
            lines.append(f"Current public URL: {public_url}")
        lines.extend(
            [
                "",
                "Constraints:",
                "- Keep changes bounded and practical.",
                "- Prefer free/open compute and agent-friendly workflows.",
                "- Improve Nomad's ability to earn, self-improve, or help other agents.",
                "- Run the relevant tests after changes.",
                "",
                "When finished, report:",
                "- what changed,",
                "- what it improves,",
                "- and the next best Nomad objective.",
            ]
        )
        return "\n".join(lines)

    def _empty_state(self) -> Dict[str, Any]:
        return {
            "cycle_count": 0,
            "last_cycle_at": "",
            "current_objective": "",
            "next_objective": self.default_objective(),
            "open_human_unlock": None,
            "self_development_unlocks": [],
            "last_external_review_count": 0,
            "last_local_actions": [],
            "last_lead": None,
            "last_agent_pain_solution": None,
            "last_autonomous_development": None,
            "cycles": [],
        }

    @staticmethod
    def _load_optional_json(path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _cycle_entry(self, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "objective": result.get("objective", ""),
            "external_review_count": result.get("external_review_count", 0),
            "analysis": result.get("analysis", ""),
            "open_human_unlock": self._compact_unlock(result),
            "local_actions": [
                self._compact_action(item)
                for item in (result.get("local_actions") or [])[:4]
            ],
            "agent_pain_solution": self._compact_agent_pain_solution(result),
            "autonomous_development": self._compact_autonomous_development(result),
        }

    @staticmethod
    def _unlock_payload(
        candidate_id: str,
        candidate_name: str,
        short_ask: str,
        human_action: str,
        human_deliverable: str,
        reason: str,
        success_criteria: list[str],
        example_response: str,
    ) -> Dict[str, Any]:
        return {
            "category": "self_development",
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "role": "self-development human unlock",
            "lane_state": "pending",
            "requires_account": False,
            "env_vars": [],
            "ask": human_action,
            "short_ask": short_ask,
            "reason": reason,
            "human_action": human_action,
            "human_deliverable": human_deliverable,
            "success_criteria": success_criteria,
            "example_response": example_response,
            "timebox_minutes": 3,
        }

    @staticmethod
    def _compact_unlock(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        unlocks = result.get("human_unlocks") or []
        if not unlocks:
            return None
        unlock = unlocks[0]
        return {
            "category": unlock.get("category"),
            "candidate_id": unlock.get("candidate_id"),
            "candidate_name": unlock.get("candidate_name"),
            "short_ask": unlock.get("short_ask"),
            "human_action": unlock.get("human_action"),
        }

    @staticmethod
    def _compact_action(action: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": action.get("type"),
            "category": action.get("category"),
            "title": action.get("title"),
            "reason": action.get("reason"),
            "requires_human": action.get("requires_human", False),
        }

    @staticmethod
    def _compact_agent_pain_solution(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        solver = result.get("agent_pain_solver") or {}
        solution = solver.get("solution") or {}
        if not solution:
            return None
        guardrail = solution.get("guardrail") or {}
        return {
            "solution_id": solution.get("solution_id", ""),
            "pain_type": solution.get("pain_type", ""),
            "title": solution.get("title", ""),
            "guardrail_id": guardrail.get("id", ""),
            "next_nomad_action": solver.get("next_nomad_action", ""),
        }

    @staticmethod
    def _compact_autonomous_development(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        payload = result.get("autonomous_development") or {}
        if not payload:
            return None
        action = payload.get("action") or payload.get("candidate") or {}
        if action:
            return {
                "action_id": action.get("action_id", ""),
                "type": action.get("type", ""),
                "title": action.get("title", ""),
                "files": action.get("files") or [],
                "skipped": bool(payload.get("skipped", False)),
                "reason": payload.get("reason", ""),
            }
        return {
            "skipped": bool(payload.get("skipped", False)),
            "reason": payload.get("reason", ""),
        }
