from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class LaneType(str, Enum):
    BUG_FIX = "bug_fix"
    ARCHITECTURE = "architecture"
    CODE_REVIEW = "code_review"
    PERFORMANCE = "performance"
    SECURITY_AUDIT = "security_audit"
    PR_PLAN = "pr_plan"
    COMPUTE_TASK = "compute_task"
    KNOWLEDGE_SHARE = "knowledge_share"
    MUTUAL_AID = "mutual_aid"
    SELF_DEVELOPMENT = "self_development"


class EvidenceKind(str, Enum):
    TASK_PAID = "task_paid"
    REGRESSION_PREVENTED = "regression_prevented"
    SOLUTION_ACCEPTED = "solution_accepted"
    PR_MERGED = "pr_merged"
    DEPLOYMENT_CONFIRMED = "deployment_confirmed"
    REPRODUCTION = "reproduction"
    AGENT_REPLIED = "agent_replied"
    TEST_PASSED = "test_passed"
    REVIEW_USED = "review_used"
    CONTACT_MADE = "contact_made"
    OUTREACH_SENT = "outreach_sent"
    PLAN_SHARED = "plan_shared"


class OutcomeKind(str, Enum):
    VERIFIED_SUCCESS = "verified_success"
    PARTIAL_SUCCESS = "partial_success"
    UNCONFIRMED = "unconfirmed"
    FAILED = "failed"
    REGRESSION = "regression"
    ABANDONED = "abandoned"


EVIDENCE_WEIGHTS: Dict[EvidenceKind, float] = {
    EvidenceKind.TASK_PAID: 2.0,
    EvidenceKind.REGRESSION_PREVENTED: 2.0,
    EvidenceKind.SOLUTION_ACCEPTED: 1.5,
    EvidenceKind.PR_MERGED: 1.5,
    EvidenceKind.DEPLOYMENT_CONFIRMED: 1.5,
    EvidenceKind.REPRODUCTION: 1.0,
    EvidenceKind.AGENT_REPLIED: 1.0,
    EvidenceKind.TEST_PASSED: 1.0,
    EvidenceKind.REVIEW_USED: 1.0,
    EvidenceKind.CONTACT_MADE: 0.4,
    EvidenceKind.OUTREACH_SENT: 0.4,
    EvidenceKind.PLAN_SHARED: 0.4,
}


@dataclass
class Evidence:
    kind: EvidenceKind
    detail: str
    timestamp: float = field(default_factory=time.time)
    weight: float = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EvidenceKind):
            try:
                self.kind = EvidenceKind(str(self.kind))
            except ValueError:
                self.kind = EvidenceKind.PLAN_SHARED
        self.detail = str(self.detail or "")[:500]
        self.weight = EVIDENCE_WEIGHTS.get(self.kind, 0.5)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "detail": self.detail,
            "timestamp": round(float(self.timestamp), 6),
            "weight": self.weight,
        }


@dataclass
class LedgerEntry:
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    agent_id: str = ""
    task_description: str = ""
    lane: LaneType = LaneType.MUTUAL_AID
    opened_at: float = field(default_factory=time.time)
    closed_at: Optional[float] = None
    outcome: OutcomeKind = OutcomeKind.UNCONFIRMED
    evidence: List[Evidence] = field(default_factory=list)
    module_produced: Optional[str] = None
    reuse_count: int = 0
    notes: str = ""
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.lane, LaneType):
            try:
                self.lane = LaneType(str(self.lane))
            except ValueError:
                self.lane = LaneType.MUTUAL_AID
        if not isinstance(self.outcome, OutcomeKind):
            try:
                self.outcome = OutcomeKind(str(self.outcome))
            except ValueError:
                self.outcome = OutcomeKind.UNCONFIRMED
        normalized_evidence: List[Evidence] = []
        for item in self.evidence:
            if isinstance(item, Evidence):
                normalized_evidence.append(item)
            elif isinstance(item, dict):
                normalized_evidence.append(
                    Evidence(kind=item.get("kind", EvidenceKind.PLAN_SHARED), detail=item.get("detail", ""))
                )
        self.evidence = normalized_evidence

    @property
    def raw_evidence_score(self) -> float:
        return sum(item.weight for item in self.evidence)

    @property
    def truth_density(self) -> float:
        return min(self.raw_evidence_score / 10.0, 1.0)

    @property
    def reuse_value(self) -> float:
        return min(self.truth_density + 0.15 * math.log1p(max(0, int(self.reuse_count))), 1.0)

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.closed_at is None:
            return None
        return max(0.0, self.closed_at - self.opened_at)

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    def add_evidence(self, kind: EvidenceKind, detail: str) -> "LedgerEntry":
        self.evidence.append(Evidence(kind=kind, detail=detail))
        return self

    def compute_hash(self) -> str:
        payload = json.dumps(
            {
                "entry_id": self.entry_id,
                "agent_id": self.agent_id,
                "task_description": self.task_description,
                "lane": self.lane.value,
                "opened_at": round(float(self.opened_at), 6),
                "closed_at": round(float(self.closed_at), 6) if self.closed_at is not None else None,
                "outcome": self.outcome.value,
                "evidence": [item.to_dict() for item in self.evidence],
                "module_produced": self.module_produced or "",
                "reuse_count": int(self.reuse_count),
                "notes": self.notes,
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        if not self.content_hash:
            self.content_hash = self.compute_hash()
        return {
            "entry_id": self.entry_id,
            "agent_id": self.agent_id,
            "task_description": self.task_description,
            "lane": self.lane.value,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "outcome": self.outcome.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "module_produced": self.module_produced,
            "reuse_count": int(self.reuse_count),
            "notes": self.notes,
            "content_hash": self.content_hash,
            "truth_density": round(self.truth_density, 4),
            "reuse_value": round(self.reuse_value, 4),
            "raw_score": round(self.raw_evidence_score, 2),
            "duration_s": self.duration_seconds,
        }


@dataclass
class RegressionCheck:
    window: int = 20

    def check(
        self,
        new_entry: LedgerEntry,
        history: List[LedgerEntry],
        baseline_lane: Optional[LaneType] = None,
    ) -> Tuple[bool, str]:
        lane = baseline_lane or new_entry.lane
        relevant = [
            item for item in history
            if item.lane == lane and item.outcome != OutcomeKind.ABANDONED and not item.is_open
        ][-self.window:]
        if len(relevant) < 3:
            return False, "not_enough_historical_data"
        baseline_success = sum(
            1
            for item in relevant
            if item.outcome in (OutcomeKind.VERIFIED_SUCCESS, OutcomeKind.PARTIAL_SUCCESS)
        ) / len(relevant)
        if new_entry.truth_density < (baseline_success - 0.15) and new_entry.outcome == OutcomeKind.UNCONFIRMED:
            return True, f"truth_density_below_lane_baseline:{new_entry.truth_density:.2f}<{baseline_success:.2f}"
        return False, "no_regression_signal"


class TruthDensityLedger:
    """Scores verified aid outcomes and also exposes a persistent append-only ledger API."""

    LEDGER_PATH = Path("truth_density_ledger.ndjson")
    INDEX_NAME = "truth_density_index.json"

    def __init__(
        self,
        ledger_path: Optional[Path] = None,
        regression_checker: Optional[RegressionCheck] = None,
        index_path: Optional[Path] = None,
    ) -> None:
        self._path = Path(ledger_path) if ledger_path is not None else self.LEDGER_PATH
        self._index = Path(index_path) if index_path is not None else self._path.with_name(self.INDEX_NAME)
        self._open: Dict[str, LedgerEntry] = {}
        self._closed: List[LedgerEntry] = []
        self._regression = regression_checker or RegressionCheck()
        self._load()

    def build_entry(
        self,
        event: Dict[str, Any],
        help_result: Dict[str, Any],
        prior_entries: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        pain_type = str(help_result.get("pain_type") or event.get("pain_type") or "self_improvement")
        evidence_objects = self._evidence_objects(help_result)
        evidence_items = [item.detail for item in evidence_objects]
        evidence_weight = sum(item.weight for item in evidence_objects)
        outcome = self._outcome(help_result)
        score = self._score(
            success=bool(help_result.get("success", False)),
            evidence_count=len(evidence_items),
            acceptance_count=int(help_result.get("acceptance_count") or 0),
            truth_density_increase=float(help_result.get("truth_density_increase") or 0.0),
            outcome_status=outcome["status"],
            evidence_weight=evidence_weight,
        )
        reuse_value = self._reuse_value(pain_type=pain_type, prior_entries=prior_entries, score=score)
        entry = {
            "schema": "nomad.truth_density_ledger_entry.v1",
            "ledger_id": self._ledger_id(event, help_result),
            "timestamp": event.get("timestamp") or self._iso_now(),
            "event_id": event.get("event_id", ""),
            "direction": help_result.get("direction") or "outbound_help",
            "source": event.get("source", ""),
            "agent_id": event.get("other_agent_id", ""),
            "pain_type": pain_type,
            "lane": self._lane_for_pain(pain_type).value,
            "task": str(help_result.get("task") or "")[:500],
            "evidence": evidence_items,
            "evidence_details": [item.to_dict() for item in evidence_objects],
            "raw_evidence_score": round(evidence_weight, 4),
            "outcome": outcome,
            "truth_density_increase": round(float(help_result.get("truth_density_increase") or 0.0), 4),
            "truth_score": score,
            "reuse_value": reuse_value,
            "acceptance_count": int(help_result.get("acceptance_count") or 0),
            "solution_id": str(help_result.get("solution_id") or ""),
            "solution_title": str(help_result.get("solution_title") or ""),
        }
        entry["regression_check"] = self._state_regression_check(entry, prior_entries)
        entry["content_hash"] = self._content_hash(entry)
        return entry

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
                "timestamp": self._iso_now(),
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
        details = [self._evidence_from_text(item).to_dict() for item in updated["evidence"]]
        updated["evidence_details"] = details
        updated["raw_evidence_score"] = round(sum(float(item.get("weight") or 0.0) for item in details), 4)
        updated["truth_score"] = self._score(
            success=bool(success),
            evidence_count=len(updated["evidence"]),
            acceptance_count=int(updated.get("acceptance_count") or 0),
            truth_density_increase=float(updated.get("truth_density_increase") or 0.0),
            outcome_status=outcome["status"],
            evidence_weight=float(updated.get("raw_evidence_score") or 0.0),
        )
        updated["content_hash"] = self._content_hash(updated)
        return updated

    def open_entry(
        self,
        agent_id: str,
        task_description: str,
        lane: LaneType = LaneType.MUTUAL_AID,
        notes: str = "",
    ) -> LedgerEntry:
        entry = LedgerEntry(
            agent_id=str(agent_id or "")[:200],
            task_description=str(task_description or "")[:1000],
            lane=lane,
            notes=str(notes or "")[:1000],
        )
        self._open[entry.entry_id] = entry
        self._append(entry)
        return entry

    def close_entry(
        self,
        entry_id: str,
        outcome: OutcomeKind,
        module_produced: Optional[str] = None,
        notes: str = "",
    ) -> Tuple[LedgerEntry, bool, str]:
        if entry_id not in self._open:
            raise KeyError(f"unknown_open_entry:{entry_id}")
        entry = self._open.pop(entry_id)
        entry.closed_at = time.time()
        entry.outcome = outcome
        if module_produced:
            entry.module_produced = str(module_produced)[:500]
        if notes:
            entry.notes = (entry.notes + " " + str(notes)[:1000]).strip()
        if entry.outcome == OutcomeKind.UNCONFIRMED and entry.raw_evidence_score >= 1.0:
            entry.outcome = OutcomeKind.PARTIAL_SUCCESS
        is_regression, reason = self._regression.check(entry, self._closed)
        if is_regression:
            entry.notes = (entry.notes + f" [REGRESSION:{reason}]").strip()
        self._upsert_closed(entry)
        self._append(entry)
        self._write_index()
        return entry, is_regression, reason

    def record_reuse(self, entry_id: str, source: str = "") -> LedgerEntry:
        for entry in self._closed:
            if entry.entry_id == entry_id:
                entry.reuse_count += 1
                if source:
                    entry.notes = (entry.notes + f" [REUSE:{source}]").strip()
                self._append(entry)
                self._write_index()
                return entry
        raise KeyError(f"unknown_closed_entry:{entry_id}")

    def get_by_agent(self, agent_id: str) -> List[LedgerEntry]:
        return [entry for entry in self._closed if entry.agent_id == agent_id]

    def get_by_lane(self, lane: LaneType) -> List[LedgerEntry]:
        return [entry for entry in self._closed if entry.lane == lane]

    def top_reusable(self, n: int = 5) -> List[LedgerEntry]:
        return sorted(self._closed, key=lambda entry: entry.reuse_value, reverse=True)[: max(0, int(n))]

    def open_entries(self) -> List[LedgerEntry]:
        return list(self._open.values())

    def abandon_stale(self, older_than_seconds: float = 86400.0) -> int:
        now = time.time()
        stale_ids = [
            entry_id
            for entry_id, entry in self._open.items()
            if (now - float(entry.opened_at)) > float(older_than_seconds)
        ]
        for entry_id in stale_ids:
            self.close_entry(entry_id, OutcomeKind.ABANDONED, notes="auto_abandoned_timeout")
        return len(stale_ids)

    def summary(self) -> Dict[str, Any]:
        total = len(self._closed)
        if total == 0:
            return {
                "total_closed": 0,
                "total_open": len(self._open),
                "avg_truth_density": 0.0,
                "outcome_breakdown": {},
                "lane_breakdown": {},
                "top_reusable": [],
                "message": "no_closed_entries",
            }
        outcomes: Dict[str, int] = {}
        lanes: Dict[str, Dict[str, Any]] = {}
        for entry in self._closed:
            outcomes[entry.outcome.value] = outcomes.get(entry.outcome.value, 0) + 1
            lane_stats = lanes.setdefault(entry.lane.value, {"count": 0, "successes": 0, "td_total": 0.0})
            lane_stats["count"] += 1
            lane_stats["td_total"] += entry.truth_density
            if entry.outcome in (OutcomeKind.VERIFIED_SUCCESS, OutcomeKind.PARTIAL_SUCCESS):
                lane_stats["successes"] += 1
        lane_breakdown = {
            lane: {
                "count": int(stats["count"]),
                "success_rate": round(float(stats["successes"]) / max(1, int(stats["count"])), 3),
                "avg_td": round(float(stats["td_total"]) / max(1, int(stats["count"])), 4),
            }
            for lane, stats in lanes.items()
        }
        return {
            "total_closed": total,
            "total_open": len(self._open),
            "avg_truth_density": round(sum(entry.truth_density for entry in self._closed) / total, 4),
            "outcome_breakdown": outcomes,
            "lane_breakdown": lane_breakdown,
            "top_reusable": [
                {
                    "entry_id": entry.entry_id,
                    "lane": entry.lane.value,
                    "agent_id": entry.agent_id,
                    "reuse_count": entry.reuse_count,
                    "reuse_value": round(entry.reuse_value, 4),
                    "outcome": entry.outcome.value,
                    "summary": entry.task_description[:80],
                }
                for entry in self.top_reusable(5)
            ],
        }

    def print_report(self) -> None:
        summary = self.summary()
        print("Nomad Truth-Density-Ledger")
        if summary.get("message"):
            print(summary["message"])
            return
        print(f"closed={summary['total_closed']} open={summary['total_open']} avg_td={summary['avg_truth_density']}")
        print(json.dumps(summary.get("outcome_breakdown") or {}, ensure_ascii=True, sort_keys=True))

    def _load(self) -> None:
        if not self._path.exists():
            return
        closed_by_id: Dict[str, LedgerEntry] = {}
        open_by_id: Dict[str, LedgerEntry] = {}
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines:
            text = line.strip()
            if not text:
                continue
            try:
                entry = self._dict_to_entry(json.loads(text))
            except (TypeError, ValueError, KeyError, json.JSONDecodeError):
                continue
            if entry.is_open:
                if entry.entry_id not in closed_by_id:
                    open_by_id[entry.entry_id] = entry
            else:
                open_by_id.pop(entry.entry_id, None)
                closed_by_id[entry.entry_id] = entry
        self._open = open_by_id
        self._closed = list(closed_by_id.values())

    def _append(self, entry: LedgerEntry) -> None:
        entry.content_hash = entry.compute_hash()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.to_dict(), ensure_ascii=True, sort_keys=True) + "\n")

    def _write_index(self) -> None:
        self._index.parent.mkdir(parents=True, exist_ok=True)
        self._index.write_text(json.dumps(self.summary(), ensure_ascii=True, indent=2), encoding="utf-8")

    def _upsert_closed(self, entry: LedgerEntry) -> None:
        for index, existing in enumerate(self._closed):
            if existing.entry_id == entry.entry_id:
                self._closed[index] = entry
                return
        self._closed.append(entry)

    @staticmethod
    def _dict_to_entry(payload: Dict[str, Any]) -> LedgerEntry:
        evidence = [
            Evidence(
                kind=item.get("kind", EvidenceKind.PLAN_SHARED),
                detail=item.get("detail", ""),
                timestamp=float(item.get("timestamp") or time.time()),
            )
            for item in (payload.get("evidence") or [])
            if isinstance(item, dict)
        ]
        return LedgerEntry(
            entry_id=str(payload.get("entry_id") or str(uuid.uuid4())[:12]),
            agent_id=str(payload.get("agent_id") or ""),
            task_description=str(payload.get("task_description") or ""),
            lane=payload.get("lane", LaneType.MUTUAL_AID),
            opened_at=float(payload.get("opened_at") or time.time()),
            closed_at=payload.get("closed_at"),
            outcome=payload.get("outcome", OutcomeKind.UNCONFIRMED),
            evidence=evidence,
            module_produced=payload.get("module_produced"),
            reuse_count=int(payload.get("reuse_count") or 0),
            notes=str(payload.get("notes") or ""),
            content_hash=str(payload.get("content_hash") or ""),
        )

    def _evidence_items(self, help_result: Dict[str, Any]) -> List[str]:
        return [item.detail for item in self._evidence_objects(help_result)]

    def _evidence_objects(self, help_result: Dict[str, Any]) -> List[Evidence]:
        explicit = [
            str(item).strip()
            for item in (help_result.get("evidence") or help_result.get("evidence_items") or [])
            if str(item).strip()
        ]
        if explicit:
            return [self._evidence_from_text(item) for item in explicit[:12]]

        items: List[Evidence] = []
        evidence_count = int(help_result.get("evidence_count") or 0)
        acceptance_count = int(help_result.get("acceptance_count") or 0)
        for index in range(min(evidence_count, 8)):
            items.append(Evidence(EvidenceKind.PLAN_SHARED, f"inferred_solution_evidence_{index + 1}"))
        for index in range(min(acceptance_count, 4)):
            items.append(Evidence(EvidenceKind.PLAN_SHARED, f"inferred_acceptance_criterion_{index + 1}"))
        if help_result.get("solution_id"):
            items.append(Evidence(EvidenceKind.PLAN_SHARED, f"solution_id={help_result['solution_id']}"))
        task = str(help_result.get("task") or "")
        if "ERROR=" in task:
            items.append(Evidence(EvidenceKind.REPRODUCTION, "task_contains_error_contract"))
        if "FACT_URL" in task:
            items.append(Evidence(EvidenceKind.REPRODUCTION, "task_contains_fact_url_contract"))
        return items[:12]

    @staticmethod
    def _evidence_from_text(text: str) -> Evidence:
        value = " ".join(str(text or "").split())[:500]
        lowered = value.lower()
        kind = EvidenceKind.PLAN_SHARED
        if "paid" in lowered or "payment" in lowered or "invoice" in lowered:
            kind = EvidenceKind.TASK_PAID
        elif "regression prevented" in lowered or "prevented regression" in lowered:
            kind = EvidenceKind.REGRESSION_PREVENTED
        elif "accepted" in lowered or "plan_accepted" in lowered or "solution accepted" in lowered:
            kind = EvidenceKind.SOLUTION_ACCEPTED
        elif "pr merged" in lowered or "merged pr" in lowered:
            kind = EvidenceKind.PR_MERGED
        elif "deployed" in lowered or "deployment" in lowered or "staging" in lowered:
            kind = EvidenceKind.DEPLOYMENT_CONFIRMED
        elif "repro" in lowered or "observed error" in lowered or "error=" in lowered:
            kind = EvidenceKind.REPRODUCTION
        elif "reply" in lowered or "replied" in lowered:
            kind = EvidenceKind.AGENT_REPLIED
        elif "test passed" in lowered or "dry-run" in lowered or "dry run" in lowered:
            kind = EvidenceKind.TEST_PASSED
        elif "review used" in lowered or "review applied" in lowered:
            kind = EvidenceKind.REVIEW_USED
        elif "contact" in lowered:
            kind = EvidenceKind.CONTACT_MADE
        elif "outreach" in lowered:
            kind = EvidenceKind.OUTREACH_SENT
        return Evidence(kind=kind, detail=value)

    @staticmethod
    def _outcome(help_result: Dict[str, Any]) -> Dict[str, Any]:
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
        evidence_weight: float = 0.0,
    ) -> float:
        score = 0.2 if success else 0.0
        score += min(0.3, max(0.0, evidence_weight) / 10.0)
        score += min(0.12, max(0, evidence_count) * 0.02)
        score += min(0.15, max(0, acceptance_count) * 0.04)
        score += min(0.25, max(0.0, truth_density_increase))
        if outcome_status in {"accepted", "paid", "delivered", "verified_help_result", "proposal_verified"}:
            score += 0.1
        if outcome_status in {"failed", "failed_help_result", "rejected"}:
            score -= 0.15
        return round(max(0.0, min(1.0, score)), 4)

    @staticmethod
    def _reuse_value(pain_type: str, prior_entries: List[Dict[str, Any]], score: float) -> Dict[str, Any]:
        related = [
            item for item in prior_entries
            if str(item.get("pain_type") or "") == pain_type and (item.get("outcome") or {}).get("success")
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

    @staticmethod
    def _lane_for_pain(pain_type: str) -> LaneType:
        mapping = {
            "compute_auth": LaneType.COMPUTE_TASK,
            "tool_failure": LaneType.BUG_FIX,
            "mcp_integration": LaneType.ARCHITECTURE,
            "loop_break": LaneType.PERFORMANCE,
            "human_in_loop": LaneType.PR_PLAN,
            "payment": LaneType.MUTUAL_AID,
            "memory": LaneType.KNOWLEDGE_SHARE,
            "repo_issue_help": LaneType.BUG_FIX,
            "self_improvement": LaneType.SELF_DEVELOPMENT,
        }
        return mapping.get(str(pain_type or ""), LaneType.MUTUAL_AID)

    @staticmethod
    def _state_regression_check(entry: Dict[str, Any], prior_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        lane = str(entry.get("lane") or "")
        relevant = [
            item for item in prior_entries
            if str(item.get("lane") or "") == lane and (item.get("outcome") or {}).get("status") != OutcomeKind.ABANDONED.value
        ][-20:]
        if len(relevant) < 3:
            return {"is_regression": False, "reason": "not_enough_historical_data"}
        baseline = sum(1 for item in relevant if (item.get("outcome") or {}).get("success")) / len(relevant)
        score = float(entry.get("truth_score") or 0.0)
        if not (entry.get("outcome") or {}).get("success") and score < (baseline - 0.15):
            return {
                "is_regression": True,
                "reason": f"truth_score_below_lane_baseline:{score:.2f}<{baseline:.2f}",
                "baseline_success_rate": round(baseline, 4),
            }
        return {
            "is_regression": False,
            "reason": "no_regression_signal",
            "baseline_success_rate": round(baseline, 4),
        }

    @staticmethod
    def _content_hash(entry: Dict[str, Any]) -> str:
        payload = {
            key: value
            for key, value in entry.items()
            if key not in {"content_hash", "analysis"}
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]

    @staticmethod
    def _iso_now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
