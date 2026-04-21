import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parent
DEFAULT_AUTONOMOUS_DEVELOPMENT_LOG = ROOT / "nomad_autonomous_development.json"


class AutonomousDevelopmentLog:
    """Records concrete, bounded self-development receipts from Nomad cycles."""

    def __init__(self, path: Optional[Path] = None, max_entries: int = 200) -> None:
        self.path = Path(path or DEFAULT_AUTONOMOUS_DEVELOPMENT_LOG)
        self.max_entries = max_entries

    def apply_cycle(self, objective: str, self_improvement: Dict[str, Any]) -> Dict[str, Any]:
        candidate = self._candidate_from_cycle(objective=objective, self_improvement=self_improvement)
        if not candidate:
            return {
                "mode": "nomad_autonomous_development",
                "schema": "nomad.autonomous_development.v1",
                "ok": True,
                "skipped": True,
                "reason": "no_non_human_development_candidate",
                "analysis": "No bounded non-human development candidate was produced in this cycle.",
            }

        state = self._load()
        fingerprints = set(state.get("fingerprints") or [])
        fingerprint = candidate["fingerprint"]
        if fingerprint in fingerprints:
            return {
                "mode": "nomad_autonomous_development",
                "schema": "nomad.autonomous_development.v1",
                "ok": True,
                "skipped": True,
                "reason": "duplicate_development_candidate",
                "candidate": candidate,
                "latest_action": (state.get("actions") or [{}])[-1],
                "analysis": "Nomad already recorded this autonomous development candidate; no repeated receipt was written.",
            }

        action = {
            "schema": "nomad.autonomous_development_action.v1",
            "action_id": self._action_id(fingerprint),
            "created_at": datetime.now(UTC).isoformat(),
            "fingerprint": fingerprint,
            "objective": str(objective or "")[:500],
            **{key: value for key, value in candidate.items() if key != "fingerprint"},
        }
        actions = list(state.get("actions") or [])
        actions.append(action)
        state["actions"] = actions[-self.max_entries :]
        fingerprints.add(fingerprint)
        state["fingerprints"] = sorted(fingerprints)[-self.max_entries :]
        state["last_action"] = action
        state["updated_at"] = action["created_at"]
        self._save(state)
        return {
            "mode": "nomad_autonomous_development",
            "schema": "nomad.autonomous_development.v1",
            "ok": True,
            "skipped": False,
            "action": action,
            "action_count": len(state["actions"]),
            "analysis": f"Nomad recorded autonomous development receipt: {action['title']}",
        }

    def status(self) -> Dict[str, Any]:
        state = self._load()
        actions = list(state.get("actions") or [])
        return {
            "mode": "nomad_autonomous_development_status",
            "schema": "nomad.autonomous_development_status.v1",
            "ok": True,
            "action_count": len(actions),
            "latest_action": actions[-1] if actions else {},
            "updated_at": state.get("updated_at", ""),
        }

    def _candidate_from_cycle(self, objective: str, self_improvement: Dict[str, Any]) -> Dict[str, Any]:
        lead_scout = self_improvement.get("lead_scout") or {}
        active_lead = lead_scout.get("active_lead") or {}
        help_draft = lead_scout.get("help_draft") or {}
        help_draft_path = str(lead_scout.get("help_draft_path") or "").strip()
        lead_url = str(active_lead.get("url") or active_lead.get("html_url") or "").strip()
        if active_lead and help_draft:
            fingerprint = self._fingerprint(
                "lead_help_artifact",
                lead_url,
                active_lead.get("title") or active_lead.get("name") or "",
                active_lead.get("recommended_service_type") or "",
            )
            files = [help_draft_path] if help_draft_path else []
            return {
                "fingerprint": fingerprint,
                "type": "lead_help_artifact",
                "title": "Drafted a bounded help artifact for an agent lead",
                "reason": "A concrete public lead was found and Nomad produced private-first help.",
                "evidence": [
                    lead_url or str(active_lead.get("title") or "active lead"),
                    str(active_lead.get("pain") or active_lead.get("pain_signal") or "")[:240],
                    str(lead_scout.get("next_agent_action") or "")[:240],
                ],
                "files": files,
                "next_verification": "Human may inspect the draft, approve public posting, or let Nomad keep it private.",
            }

        agent_pain = self_improvement.get("agent_pain_solver") or {}
        solution = agent_pain.get("solution") or {}
        if solution:
            fingerprint = self._fingerprint(
                "agent_pain_solution",
                solution.get("pain_type") or "",
                solution.get("solution_id") or "",
                solution.get("title") or "",
            )
            return {
                "fingerprint": fingerprint,
                "type": "agent_pain_solution",
                "title": f"Captured reusable solution: {solution.get('title') or 'agent pain solution'}",
                "reason": agent_pain.get("analysis") or "Nomad converted a repeated agent pain pattern into a reusable solution.",
                "evidence": [
                    str(solution.get("pain_type") or ""),
                    str((solution.get("guardrail") or {}).get("id") or ""),
                    str(solution.get("required_input") or "")[:240],
                ],
                "files": [],
                "next_verification": "Use this solution in a service task, lead draft, or Mutual-Aid pack and record the outcome.",
            }

        for action in self_improvement.get("local_actions") or []:
            if not isinstance(action, dict) or action.get("requires_human"):
                continue
            title = str(action.get("title") or "Autonomous local action").strip()
            fingerprint = self._fingerprint(
                "local_action",
                action.get("type") or "",
                action.get("category") or "",
                title,
                objective,
            )
            return {
                "fingerprint": fingerprint,
                "type": action.get("type") or "local_action",
                "title": title,
                "reason": action.get("reason") or "Nomad selected this as a bounded non-human self-development action.",
                "evidence": [str(action.get("category") or ""), str(action.get("type") or "")],
                "files": [],
                "next_verification": "Check whether the next cycle changes objective, lead quality, or service conversion.",
            }
        return {}

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self._empty_state()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                empty = self._empty_state()
                empty.update(payload)
                return empty
        except Exception:
            pass
        return self._empty_state()

    def _save(self, state: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")

    @staticmethod
    def _empty_state() -> Dict[str, Any]:
        return {
            "schema": "nomad.autonomous_development_log.v1",
            "actions": [],
            "fingerprints": [],
            "last_action": {},
            "updated_at": "",
        }

    @staticmethod
    def _fingerprint(*parts: Any) -> str:
        text = "|".join(" ".join(str(part or "").split()).lower() for part in parts)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _action_id(fingerprint: str) -> str:
        return f"adev-{hashlib.sha256(str(fingerprint).encode('utf-8')).hexdigest()[:12]}"
