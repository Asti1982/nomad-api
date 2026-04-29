from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from nomad_market_patterns import (
    ROOT,
    ComputeLane,
    MarketPattern,
    MarketPatternRegistry,
    PatternStatus,
)
from nomad_predictive_router import PredictiveRouter


DEFAULT_HEAL_LOG_PATH = ROOT / "nomad_heal_log.ndjson"


class HealStrategy(str, Enum):
    LANE_SWITCH = "lane_switch"
    PROMPT_REPAIR = "prompt_repair"
    RETIRE = "retire"
    SANDBOX_RETEST = "sandbox_retest"
    RATE_LIMIT_WAIT = "rate_limit_wait"
    ESCALATE = "escalate"


@dataclass
class HealAction:
    pattern_id: str
    task_type: str
    old_lane: ComputeLane
    strategy: HealStrategy
    reason: str
    executed_at: float = field(default_factory=time.time)
    success: bool = False
    result: str = ""
    new_lane: Optional[ComputeLane] = None
    new_pattern_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "task_type": self.task_type,
            "old_lane": self.old_lane.value,
            "strategy": self.strategy.value,
            "reason": self.reason,
            "executed_at": self.executed_at,
            "success": self.success,
            "result": self.result,
            "new_lane": self.new_lane.value if self.new_lane else None,
            "new_pattern_id": self.new_pattern_id,
        }


@dataclass
class Diagnosis:
    pattern: MarketPattern
    failure_mode: str
    recommended: HealStrategy
    urgency: float
    rationale: str

    @classmethod
    def diagnose(cls, pattern: MarketPattern, router: PredictiveRouter) -> "Diagnosis":
        executions = pattern.executions[-20:]
        if not executions:
            return cls(
                pattern=pattern,
                failure_mode="unknown",
                recommended=HealStrategy.SANDBOX_RETEST,
                urgency=0.2,
                rationale="No execution history exists yet, so a deterministic retest is safest.",
            )

        error_types = [str(entry.error_type or "").lower() for entry in executions if entry.error_type]
        recent = executions[-5:]
        recent_failures = [entry for entry in recent if not entry.success]
        failure_rate = len(recent_failures) / max(len(recent), 1)
        timeout_hits = sum(1 for error in error_types if "timeout" in error)
        rate_limit_hits = sum(1 for error in error_types if "rate_limit" in error or "429" in error)
        api_errors = sum(
            1
            for error in error_types
            if any(marker in error for marker in ("401", "403", "404", "deprecat", "model_not_found"))
        )

        if rate_limit_hits >= 2:
            return cls(
                pattern=pattern,
                failure_mode="rate_limit",
                recommended=HealStrategy.RATE_LIMIT_WAIT,
                urgency=0.45,
                rationale=f"Rate limiting appeared {rate_limit_hits} times in the latest pattern history.",
            )

        if api_errors >= 1:
            return cls(
                pattern=pattern,
                failure_mode="api_change",
                recommended=HealStrategy.PROMPT_REPAIR,
                urgency=0.9,
                rationale="Structured API or model errors suggest a prompt or contract repair is needed.",
            )

        lane_health = router._get_health(pattern.lane)
        if timeout_hits >= 2 or lane_health.is_circuit_open:
            return cls(
                pattern=pattern,
                failure_mode="timeout",
                recommended=HealStrategy.LANE_SWITCH,
                urgency=0.8,
                rationale=f"Lane {pattern.lane.value} is under timeout or circuit-breaker pressure.",
            )

        if pattern.execution_count >= 20 and pattern.success_rate < 0.4:
            return cls(
                pattern=pattern,
                failure_mode="chronic_failure",
                recommended=HealStrategy.RETIRE,
                urgency=0.65,
                rationale="The pattern stayed weak for a long time and should be replaced.",
            )

        if failure_rate >= 0.6:
            return cls(
                pattern=pattern,
                failure_mode="quality_degradation",
                recommended=HealStrategy.SANDBOX_RETEST,
                urgency=0.55,
                rationale="The recent failure rate is high without a single dominant root cause.",
            )

        return cls(
            pattern=pattern,
            failure_mode="unknown",
            recommended=HealStrategy.SANDBOX_RETEST,
            urgency=0.25,
            rationale="A bounded retest is the safest next move for an unclear degradation.",
        )


class SelfHealingPipeline:
    HEAL_LOG_PATH = DEFAULT_HEAL_LOG_PATH

    def __init__(
        self,
        router: PredictiveRouter,
        registry: Optional[MarketPatternRegistry] = None,
        prompt_repair_hook: Optional[Callable[[MarketPattern, Diagnosis], Awaitable[tuple[bool, str, str]]]] = None,
        sandbox_retest_hook: Optional[Callable[[MarketPattern], Awaitable[tuple[bool, float, str]]]] = None,
        escalation_hook: Optional[Callable[[HealAction], Awaitable[None]]] = None,
        max_actions_per_cycle: int = 3,
        heal_log_path: Optional[Path] = None,
    ) -> None:
        self._router = router
        self._registry = registry or router._registry
        self._prompt_repair_hook = prompt_repair_hook
        self._sandbox_retest_hook = sandbox_retest_hook
        self._escalation_hook = escalation_hook
        self._max_actions_per_cycle = max(1, int(max_actions_per_cycle))
        self._heal_log_path = Path(heal_log_path or self.HEAL_LOG_PATH)
        self._heal_log: list[HealAction] = []
        self._load_log()

    async def run_healing_cycle(self) -> dict[str, Any]:
        degraded = self._registry.degraded()
        if not degraded:
            return {
                "status": "healthy",
                "degraded_patterns": 0,
                "actions_taken": 0,
                "actions": [],
            }

        diagnoses = [Diagnosis.diagnose(pattern, self._router) for pattern in degraded]
        diagnoses.sort(key=lambda item: item.urgency, reverse=True)

        actions: list[HealAction] = []
        for diagnosis in diagnoses[: self._max_actions_per_cycle]:
            action = await self._execute_heal(diagnosis)
            actions.append(action)
            self._heal_log.append(action)

        self._save_log(actions)
        return {
            "status": "healing_complete",
            "degraded_patterns": len(degraded),
            "actions_taken": len(actions),
            "healed": sum(1 for action in actions if action.success),
            "failed": sum(1 for action in actions if not action.success),
            "actions": [action.to_dict() for action in actions],
        }

    def run_healing_cycle_sync(self) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run_healing_cycle())
        return {
            "status": "skipped",
            "reason": "event_loop_running",
            "message": "Healing was not executed because an event loop is already running.",
            "actions_taken": 0,
            "actions": [],
        }

    def heal_summary(self) -> dict[str, Any]:
        if not self._heal_log:
            return {"total_actions": 0}
        by_strategy: dict[str, int] = {}
        for action in self._heal_log:
            by_strategy[action.strategy.value] = by_strategy.get(action.strategy.value, 0) + 1
        success_rate = sum(1 for action in self._heal_log if action.success) / len(self._heal_log)
        return {
            "log_path": str(self._heal_log_path),
            "total_actions": len(self._heal_log),
            "success_rate": round(success_rate, 4),
            "by_strategy": by_strategy,
            "last_action_at": self._heal_log[-1].executed_at,
        }

    async def _execute_heal(self, diagnosis: Diagnosis) -> HealAction:
        action = HealAction(
            pattern_id=diagnosis.pattern.pattern_id,
            task_type=diagnosis.pattern.task_type,
            old_lane=diagnosis.pattern.lane,
            strategy=diagnosis.recommended,
            reason=diagnosis.rationale,
        )
        try:
            if diagnosis.recommended == HealStrategy.LANE_SWITCH:
                await self._heal_lane_switch(action, diagnosis)
            elif diagnosis.recommended == HealStrategy.PROMPT_REPAIR:
                await self._heal_prompt_repair(action, diagnosis)
            elif diagnosis.recommended == HealStrategy.RETIRE:
                await self._heal_retire(action, diagnosis)
            elif diagnosis.recommended == HealStrategy.SANDBOX_RETEST:
                await self._heal_sandbox_retest(action, diagnosis)
            elif diagnosis.recommended == HealStrategy.RATE_LIMIT_WAIT:
                await self._heal_rate_limit_wait(action, diagnosis)
            elif diagnosis.recommended == HealStrategy.ESCALATE:
                await self._heal_escalate(action, diagnosis)
        except Exception as exc:
            action.success = False
            action.result = f"Self-healing raised an exception: {exc}"
        return action

    async def _heal_lane_switch(self, action: HealAction, diagnosis: Diagnosis) -> None:
        ranked = self._router.rank_lanes(
            task_type=diagnosis.pattern.task_type,
            lanes=[lane for lane in ComputeLane if lane not in {ComputeLane.UNKNOWN, diagnosis.pattern.lane}],
        )
        if not ranked:
            action.result = "No alternative lane is currently eligible."
            return

        target = ranked[0]
        replacement = self._registry.mint_from_execution(
            task_type=diagnosis.pattern.task_type,
            compute_lane=target["lane"],
            latency_ms=float(target["predicted_latency_ms"]),
            cost_usd=0.0,
            success=True,
            model_hint=diagnosis.pattern.model_hint,
            notes=f"Self-healing lane switch from {diagnosis.pattern.lane.value}.",
        )
        action.success = True
        action.new_lane = target["lane"]
        action.new_pattern_id = replacement.pattern_id
        action.result = (
            f"Created replacement pattern {replacement.pattern_id} on {target['lane'].value} "
            f"with predicted score {target['routing_score']:.3f}."
        )

    async def _heal_prompt_repair(self, action: HealAction, diagnosis: Diagnosis) -> None:
        if not self._prompt_repair_hook:
            action.result = "No prompt repair hook is configured, so the repair was only diagnosed."
            return

        success, prompt_hash, notes = await self._prompt_repair_hook(diagnosis.pattern, diagnosis)
        if not success:
            action.result = f"Prompt repair hook reported failure: {notes}"
            return

        repaired = self._registry.mint_from_execution(
            task_type=diagnosis.pattern.task_type,
            compute_lane=diagnosis.pattern.lane,
            latency_ms=diagnosis.pattern.avg_latency_ms if diagnosis.pattern.avg_latency_ms != float("inf") else 2000.0,
            cost_usd=diagnosis.pattern.avg_cost_usd if diagnosis.pattern.avg_cost_usd != float("inf") else 0.0,
            success=True,
            prompt_hash=prompt_hash,
            model_hint=diagnosis.pattern.model_hint,
            notes=f"Prompt repaired: {notes}",
        )
        action.success = True
        action.new_pattern_id = repaired.pattern_id
        action.result = f"Prompt repair created replacement pattern {repaired.pattern_id}."

    async def _heal_retire(self, action: HealAction, diagnosis: Diagnosis) -> None:
        self._registry.retire(diagnosis.pattern.pattern_id, reason=diagnosis.rationale)
        replacement_decision = self._router.route(task_type=diagnosis.pattern.task_type)
        replacement = self._registry.mint_from_execution(
            task_type=diagnosis.pattern.task_type,
            compute_lane=replacement_decision.chosen_lane,
            latency_ms=replacement_decision.predicted_latency_ms,
            cost_usd=0.0,
            success=True,
            notes=f"Replacement for retired pattern {diagnosis.pattern.pattern_id}.",
        )
        action.success = True
        action.new_lane = replacement_decision.chosen_lane
        action.new_pattern_id = replacement.pattern_id
        action.result = (
            f"Retired {diagnosis.pattern.pattern_id} and created replacement {replacement.pattern_id} "
            f"on {replacement_decision.chosen_lane.value}."
        )

    async def _heal_sandbox_retest(self, action: HealAction, diagnosis: Diagnosis) -> None:
        if not self._sandbox_retest_hook:
            action.result = "No sandbox retest hook is configured, so the retest was only diagnosed."
            return

        success, latency_ms, notes = await self._sandbox_retest_hook(diagnosis.pattern)
        diagnosis.pattern.record_execution(
            latency_ms=latency_ms,
            cost_usd=0.0,
            success=success,
            error_type="" if success else "sandbox_retest_failed",
        )
        self._registry._save()
        action.success = success
        action.result = f"Sandbox retest {'passed' if success else 'failed'} in {latency_ms:.0f}ms. {notes}"

    async def _heal_rate_limit_wait(self, action: HealAction, diagnosis: Diagnosis) -> None:
        self._router.record_outcome(
            lane=diagnosis.pattern.lane,
            latency_ms=5000.0,
            success=False,
            task_type=diagnosis.pattern.task_type,
            error_type="rate_limit_backoff",
            notes="Self-healing recorded a backoff after repeated rate limiting.",
        )
        action.success = True
        action.result = f"Registered a backoff penalty for lane {diagnosis.pattern.lane.value}."

    async def _heal_escalate(self, action: HealAction, diagnosis: Diagnosis) -> None:
        if self._escalation_hook:
            await self._escalation_hook(action)
        action.success = True
        action.result = f"Escalation recorded for degraded pattern {diagnosis.pattern.pattern_id}."

    def _load_log(self) -> None:
        if not self._heal_log_path.exists():
            return
        try:
            lines = self._heal_log_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return
        for line in lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                action = HealAction(
                    pattern_id=str(payload["pattern_id"]),
                    task_type=str(payload["task_type"]),
                    old_lane=ComputeLane(str(payload["old_lane"])),
                    strategy=HealStrategy(str(payload["strategy"])),
                    reason=str(payload["reason"]),
                    executed_at=float(payload.get("executed_at") or time.time()),
                    success=bool(payload.get("success", False)),
                    result=str(payload.get("result") or ""),
                    new_lane=ComputeLane(str(payload["new_lane"])) if payload.get("new_lane") else None,
                    new_pattern_id=payload.get("new_pattern_id"),
                )
            except Exception:
                continue
            self._heal_log.append(action)

    def _save_log(self, actions: list[HealAction]) -> None:
        if not actions:
            return
        with self._heal_log_path.open("a", encoding="utf-8") as handle:
            for action in actions:
                handle.write(json.dumps(action.to_dict(), ensure_ascii=False) + "\n")
