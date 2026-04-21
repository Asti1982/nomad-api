import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Dict, List


class TruthDensityLedger:
    """Scores verified aid outcomes without trusting vague success claims."""

    def build_entry(
        self,
        event: Dict[str, Any],
        help_result: Dict[str, Any],
        prior_entries: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        pain_type = str(help_result.get("pain_type") or event.get("pain_type") or "self_improvement")
        evidence_items = self._evidence_items(help_result)
        outcome = self._outcome(help_result)
        score = self._score(
            success=bool(help_result.get("success", False)),
            evidence_count=len(evidence_items),
            acceptance_count=int(help_result.get("acceptance_count") or 0),
            truth_density_increase=float(help_result.get("truth_density_increase") or 0.0),
            outcome_status=outcome["status"],
        )
        reuse_value = self._reuse_value(pain_type=pain_type, prior_entries=prior_entries, score=score)
        return {
            "schema": "nomad.truth_density_ledger_entry.v1",
            "ledger_id": self._ledger_id(event, help_result),
            "timestamp": event.get("timestamp") or datetime.now(UTC).isoformat(),
            "event_id": event.get("event_id", ""),
            "direction": help_result.get("direction") or "outbound_help",
            "source": event.get("source", ""),
            "agent_id": event.get("other_agent_id", ""),
            "pain_type": pain_type,
            "task": str(help_result.get("task") or "")[:500],
            "evidence": evidence_items,
            "outcome": outcome,
            "truth_density_increase": round(float(help_result.get("truth_density_increase") or 0.0), 4),
            "truth_score": score,
            "reuse_value": reuse_value,
            "acceptance_count": int(help_result.get("acceptance_count") or 0),
            "solution_id": str(help_result.get("solution_id") or ""),
            "solution_title": str(help_result.get("solution_title") or ""),
        }

    def update_entry(
        self,
        entry: Dict[str, Any],
        success: bool,
        evidence: List[str],
        outcome_status: str = "",
        note: str = "",
    ) -> Dict[str, Any]:
        updated = dict(entry)
        outcome = dict(updated.get("outcome") or {})
        history = list(outcome.get("history") or [])
        history.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "success": bool(success),
                "status": outcome_status or ("accepted" if success else "failed"),
                "note": str(note or "")[:500],
                "evidence": [str(item)[:240] for item in evidence if str(item).strip()][:8],
            }
        )
        outcome["success"] = bool(success)
        outcome["status"] = history[-1]["status"]
        outcome["history"] = history[-20:]
        updated["outcome"] = outcome
        existing_evidence = list(updated.get("evidence") or [])
        for item in evidence:
            text = str(item or "").strip()
            if text and text not in existing_evidence:
                existing_evidence.append(text[:240])
        updated["evidence"] = existing_evidence[:20]
        updated["truth_score"] = self._score(
            success=bool(success),
            evidence_count=len(updated["evidence"]),
            acceptance_count=int(updated.get("acceptance_count") or 0),
            truth_density_increase=float(updated.get("truth_density_increase") or 0.0),
            outcome_status=outcome["status"],
        )
        return updated

    def _evidence_items(self, help_result: Dict[str, Any]) -> List[str]:
        explicit = [
            str(item).strip()
            for item in (help_result.get("evidence") or help_result.get("evidence_items") or [])
            if str(item).strip()
        ]
        if explicit:
            return explicit[:12]
        items: List[str] = []
        evidence_count = int(help_result.get("evidence_count") or 0)
        acceptance_count = int(help_result.get("acceptance_count") or 0)
        if evidence_count:
            items.append(f"evidence_count={evidence_count}")
        if acceptance_count:
            items.append(f"acceptance_count={acceptance_count}")
        if help_result.get("solution_id"):
            items.append(f"solution_id={help_result['solution_id']}")
        if "ERROR=" in str(help_result.get("task") or ""):
            items.append("task_contains_error_contract")
        if "FACT_URL" in str(help_result.get("task") or ""):
            items.append("task_contains_fact_url_contract")
        return items[:12]

    def _outcome(self, help_result: Dict[str, Any]) -> Dict[str, Any]:
        success = bool(help_result.get("success", False))
        status = str(help_result.get("outcome_status") or "").strip()
        if not status:
            status = "verified_help_result" if success else "failed_help_result"
        return {
            "success": success,
            "status": status,
            "note": str(help_result.get("outcome_note") or "")[:500],
            "history": [],
        }

    @staticmethod
    def _score(
        success: bool,
        evidence_count: int,
        acceptance_count: int,
        truth_density_increase: float,
        outcome_status: str,
    ) -> float:
        score = 0.2 if success else 0.0
        score += min(0.25, evidence_count * 0.04)
        score += min(0.2, acceptance_count * 0.05)
        score += min(0.25, max(0.0, truth_density_increase))
        if outcome_status in {"accepted", "paid", "delivered", "verified_help_result", "proposal_verified"}:
            score += 0.1
        return round(min(1.0, score), 4)

    @staticmethod
    def _reuse_value(pain_type: str, prior_entries: List[Dict[str, Any]], score: float) -> Dict[str, Any]:
        related = [
            item for item in prior_entries
            if str(item.get("pain_type") or "") == pain_type
        ]
        repeat_count = len(related) + 1
        value = min(1.0, 0.25 + repeat_count * 0.12 + score * 0.4)
        return {
            "score": round(value, 4),
            "repeat_count": repeat_count,
            "reason": "Repeated verified pattern becomes reusable product material.",
        }

    @staticmethod
    def _ledger_id(event: Dict[str, Any], help_result: Dict[str, Any]) -> str:
        seed = json.dumps(
            {
                "event_id": event.get("event_id", ""),
                "agent_id": event.get("other_agent_id", ""),
                "task": help_result.get("task", ""),
                "solution_id": help_result.get("solution_id", ""),
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        return f"tdl-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"
