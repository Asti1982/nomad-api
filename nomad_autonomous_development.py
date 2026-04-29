import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parent
DEFAULT_AUTONOMOUS_DEVELOPMENT_LOG = ROOT / "nomad_autonomous_development.json"
DEFAULT_AUTONOMOUS_ARTIFACT_DIR = ROOT / "nomad_autonomous_artifacts"


class AutonomousDevelopmentLog:
    """Receipt log for artifacts that emerge from verified collaborative agent patterns."""

    def __init__(
        self,
        path: Optional[Path] = None,
        artifact_dir: Optional[Path] = None,
        max_entries: int = 200,
    ) -> None:
        self.path = Path(path or DEFAULT_AUTONOMOUS_DEVELOPMENT_LOG)
        self.artifact_dir = Path(artifact_dir or DEFAULT_AUTONOMOUS_ARTIFACT_DIR)
        self.max_entries = max_entries

    def apply_cycle(self, objective: str, self_improvement: Dict[str, Any]) -> Dict[str, Any]:
        candidate = self._candidate_from_cycle(objective=objective, self_improvement=self_improvement)
        if not candidate:
            return {
                "mode": "nomad_autonomous_development",
                "schema": "nomad.autonomous_development.v1",
                "ok": True,
                "skipped": True,
                "reason": "no_collaborative_materialization_candidate",
                "analysis": (
                    "No collaboratively verified pattern was strong enough to justify artifact materialization "
                    "in this cycle."
                ),
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
                "analysis": "Nomad already recorded this materialization candidate; no repeated receipt was written.",
            }

        candidate = self._materialize_candidate(candidate)
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
            "analysis": f"Nomad recorded a collaborative materialization receipt: {action['title']}",
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
        high_value_patterns = ((self_improvement.get("high_value_patterns") or {}).get("patterns") or [])
        top_pattern = high_value_patterns[0] if high_value_patterns else {}
        if int(top_pattern.get("occurrence_count") or 0) >= 2 and self._has_collaborative_support(top_pattern):
            pattern_id = str(top_pattern.get("pattern_id") or "")
            fingerprint = self._fingerprint(
                "high_value_pattern_artifact",
                pattern_id,
                top_pattern.get("title") or "",
                top_pattern.get("occurrence_count") or 0,
            )
            artifact_slug = self._artifact_slug(top_pattern)
            blueprint = self._pattern_service_blueprint(pattern=top_pattern, objective=objective)
            verifier_text = self._pattern_verifier_checklist(pattern=top_pattern)
            return {
                "fingerprint": fingerprint,
                "type": "high_value_pattern_artifact",
                "title": f"Packaged high-value pattern: {top_pattern.get('title') or 'agent rescue pattern'}",
                "reason": (
                    f"Repeated {top_pattern.get('pain_type') or 'agent'} pain with "
                    f"{top_pattern.get('occurrence_count', 0)} successful occurrences deserves a reusable offer."
                ),
                "evidence": [
                    str(top_pattern.get("pain_type") or ""),
                    str(top_pattern.get("title") or ""),
                    f"occurrence_count={top_pattern.get('occurrence_count', 0)}",
                    f"avg_truth_score={top_pattern.get('avg_truth_score', 0)}",
                ],
                "files": [],
                "artifacts": [
                    {
                        "filename": f"patterns/{artifact_slug}.service.json",
                        "content": json.dumps(blueprint, ensure_ascii=True, indent=2),
                    },
                    {
                        "filename": f"patterns/{artifact_slug}.verifier.md",
                        "content": verifier_text,
                    },
                ],
                "next_verification": (
                    "Use the generated service blueprint on one live agent pain report and record whether "
                    "the verifier checklist closes the loop."
                ),
            }
        return {}

    @staticmethod
    def _has_collaborative_support(pattern: Dict[str, Any]) -> bool:
        source_agents = [
            str(item).strip()
            for item in (pattern.get("source_agents") or [])
            if str(item).strip()
        ]
        development_signal_count = int(pattern.get("development_signal_count") or 0)
        return len(set(source_agents)) >= 2 or development_signal_count >= 1

    def _materialize_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        materialized = dict(candidate)
        files = list(materialized.get("files") or [])
        for artifact in materialized.pop("artifacts", []) or []:
            if not isinstance(artifact, dict):
                continue
            filename = str(artifact.get("filename") or "").strip()
            content = artifact.get("content")
            if not filename or content is None:
                continue
            path = self._artifact_path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(content), encoding="utf-8")
            files.append(str(path))
        materialized["files"] = files
        return materialized

    def _artifact_path(self, filename: str) -> Path:
        root = self.artifact_dir.resolve()
        candidate = (root / Path(filename)).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"artifact_path_escape:{filename}") from exc
        return candidate

    def _pattern_service_blueprint(self, pattern: Dict[str, Any], objective: str) -> Dict[str, Any]:
        productization = pattern.get("productization") or {}
        agent_offer = pattern.get("agent_offer") or {}
        self_evolution = pattern.get("self_evolution") or {}
        return {
            "schema": "nomad.service_blueprint.v1",
            "source": "high_value_pattern",
            "pattern_id": pattern.get("pattern_id", ""),
            "title": pattern.get("title", ""),
            "pain_type": pattern.get("pain_type", ""),
            "objective": str(objective or "")[:500],
            "offer_summary": {
                "starter_diagnosis": agent_offer.get("starter_diagnosis", ""),
                "reply_contract": agent_offer.get("reply_contract", ""),
                "smallest_paid_unblock": agent_offer.get("smallest_paid_unblock") or {},
            },
            "productization": {
                "pack_ready": bool(productization.get("pack_ready", False)),
                "sku": productization.get("sku", ""),
                "name": productization.get("name", ""),
                "starter_offer": productization.get("starter_offer") or {},
                "paid_offer": productization.get("paid_offer") or {},
            },
            "service_deliverables": [
                "one concise diagnosis",
                "one verifier checklist",
                "one reusable self-apply step",
            ],
            "self_apply_step": self_evolution.get("self_apply_step", ""),
            "next_action": self_evolution.get("next_action", ""),
            "evidence": {
                "occurrence_count": pattern.get("occurrence_count", 0),
                "avg_truth_score": pattern.get("avg_truth_score", 0),
                "avg_reuse_value": pattern.get("avg_reuse_value", 0),
                "source_agents": pattern.get("source_agents") or [],
            },
        }

    @staticmethod
    def _pattern_verifier_checklist(pattern: Dict[str, Any]) -> str:
        agent_offer = pattern.get("agent_offer") or {}
        self_evolution = pattern.get("self_evolution") or {}
        return "\n".join(
            [
                f"# Verifier Checklist: {pattern.get('title') or 'High-Value Pattern'}",
                "",
                f"- Pain type: {pattern.get('pain_type') or 'unknown'}",
                f"- Successful occurrences: {pattern.get('occurrence_count', 0)}",
                f"- Average truth score: {pattern.get('avg_truth_score', 0)}",
                f"- Average reuse value: {pattern.get('avg_reuse_value', 0)}",
                f"- Reply contract: {agent_offer.get('reply_contract', '')}",
                f"- Self-apply step: {self_evolution.get('self_apply_step', '')}",
                "",
                "Verification steps:",
                "1. Confirm the requester pain matches the pattern title and pain type.",
                "2. Deliver the starter diagnosis before any paid unblock.",
                "3. Check whether the unblock uses the smallest bounded paid offer.",
                "4. Record the outcome back into the truth-density ledger.",
            ]
        )

    @staticmethod
    def _artifact_slug(pattern: Dict[str, Any]) -> str:
        title = str(pattern.get("title") or pattern.get("pain_type") or "pattern").strip().lower()
        cleaned = "".join(char if char.isalnum() else "-" for char in title)
        slug = "-".join(part for part in cleaned.split("-") if part)
        return slug[:48] or "pattern"

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
