from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from nomad_market_patterns import ComputeLane, MarketPatternRegistry
from nomad_predictive_router import PredictiveRouter


@dataclass
class LaneBenchmarkProfile:
    lane: ComputeLane
    base_latency_ms: float
    base_cost_usd: float
    success_rate: float
    task_latency_multiplier: dict[str, float] = field(default_factory=dict)
    task_cost_multiplier: dict[str, float] = field(default_factory=dict)
    task_success_bonus: dict[str, float] = field(default_factory=dict)


@dataclass
class BenchmarkTask:
    task_type: str
    rounds: int = 8


class BenchmarkHarness:
    def __init__(
        self,
        *,
        lane_profiles: list[LaneBenchmarkProfile],
        tasks: list[BenchmarkTask],
        benchmark_dir: Optional[Path] = None,
    ) -> None:
        self.lane_profiles = {profile.lane: profile for profile in lane_profiles}
        self.tasks = tasks
        self.benchmark_dir = Path(benchmark_dir or Path(__file__).resolve().parent / "benchmark-output")
        self.benchmark_dir.mkdir(parents=True, exist_ok=True)
        self.lane_order = list(self.lane_profiles.keys())

    def run(
        self,
        *,
        baseline_lane: ComputeLane = ComputeLane.XAI_GROK,
        output_path: Optional[Path] = None,
    ) -> dict[str, Any]:
        baseline = self._run_policy(policy="baseline", baseline_lane=baseline_lane)
        adaptive = self._run_policy(policy="adaptive", baseline_lane=baseline_lane)
        report = {
            "schema": "nomad.runtime_benchmark.v1",
            "baseline_lane": baseline_lane.value,
            "task_count": len(self.tasks),
            "lane_count": len(self.lane_profiles),
            "baseline": baseline,
            "adaptive": adaptive,
            "comparison": {
                "latency_reduction_ms": round(float(baseline["avg_latency_ms"]) - float(adaptive["avg_latency_ms"]), 3),
                "cost_reduction_usd": round(float(baseline["total_cost_usd"]) - float(adaptive["total_cost_usd"]), 6),
                "error_rate_reduction": round(float(baseline["error_rate"]) - float(adaptive["error_rate"]), 6),
            },
        }
        if output_path:
            out = Path(output_path)
            out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            report["output_path"] = str(out)
        return report

    def _run_policy(self, *, policy: str, baseline_lane: ComputeLane) -> dict[str, Any]:
        run_dir = self.benchmark_dir / policy
        run_dir.mkdir(parents=True, exist_ok=True)
        registry = MarketPatternRegistry(registry_path=run_dir / "patterns.json")
        router = PredictiveRouter(registry=registry, health_path=run_dir / "lane-health.json")
        totals = {
            "policy": policy,
            "attempts": 0,
            "successes": 0,
            "failure_count": 0,
            "total_latency_ms": 0.0,
            "total_cost_usd": 0.0,
            "lane_counts": {},
            "task_breakdown": {},
        }
        attempt_index = 0
        for task in self.tasks:
            task_stats = totals["task_breakdown"].setdefault(
                task.task_type,
                {"attempts": 0, "successes": 0, "total_latency_ms": 0.0, "total_cost_usd": 0.0},
            )
            for _ in range(max(1, int(task.rounds))):
                lane = baseline_lane if policy == "baseline" else self._select_adaptive_lane(task_type=task.task_type, router=router)
                outcome = self._simulate(task_type=task.task_type, lane=lane, attempt_index=attempt_index)
                attempt_index += 1
                if policy == "adaptive":
                    router.record_outcome(
                        lane=lane,
                        latency_ms=float(outcome["latency_ms"]),
                        success=bool(outcome["success"]),
                        task_type=task.task_type,
                        cost_usd=float(outcome["cost_usd"]),
                        error_type=str(outcome["error_type"] or ""),
                        prompt_hash=f"benchmark::{task.task_type}::{lane.value}",
                        model_hint=f"benchmark-{lane.value}",
                        verification="local",
                    )
                totals["attempts"] += 1
                totals["successes"] += 1 if outcome["success"] else 0
                totals["failure_count"] += 0 if outcome["success"] else 1
                totals["total_latency_ms"] += float(outcome["latency_ms"])
                totals["total_cost_usd"] += float(outcome["cost_usd"])
                totals["lane_counts"][lane.value] = int(totals["lane_counts"].get(lane.value) or 0) + 1
                task_stats["attempts"] += 1
                task_stats["successes"] += 1 if outcome["success"] else 0
                task_stats["total_latency_ms"] += float(outcome["latency_ms"])
                task_stats["total_cost_usd"] += float(outcome["cost_usd"])
        return self._finalize_metrics(totals, registry=registry)

    def _select_adaptive_lane(self, *, task_type: str, router: PredictiveRouter) -> ComputeLane:
        explored = {pattern.lane for pattern in router._registry.all_for_task(task_type)}
        for lane in self.lane_order:
            if lane not in explored:
                return lane
        ranked = router.rank_lanes(
            task_type=task_type,
            lanes=self.lane_order,
            preferred_lanes=self.lane_order,
        )
        if ranked:
            return ranked[0]["lane"]
        return self.lane_order[0]

    def _simulate(self, *, task_type: str, lane: ComputeLane, attempt_index: int) -> dict[str, Any]:
        profile = self.lane_profiles[lane]
        score = self._score(task_type=task_type, lane=lane, attempt_index=attempt_index)
        latency_multiplier = float(profile.task_latency_multiplier.get(task_type) or 1.0)
        cost_multiplier = float(profile.task_cost_multiplier.get(task_type) or 1.0)
        success_rate = float(profile.success_rate + float(profile.task_success_bonus.get(task_type) or 0.0))
        success_rate = max(0.05, min(0.995, success_rate))
        jitter = 0.9 + (score * 0.2)
        latency_ms = round(profile.base_latency_ms * latency_multiplier * jitter, 3)
        cost_usd = round(profile.base_cost_usd * cost_multiplier, 6)
        success = score <= success_rate
        return {
            "lane": lane.value,
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
            "success": success,
            "error_type": "" if success else ("timeout" if latency_ms >= 1200 else "model_error"),
        }

    def _finalize_metrics(self, totals: dict[str, Any], *, registry: MarketPatternRegistry) -> dict[str, Any]:
        attempts = max(1, int(totals["attempts"]))
        task_breakdown = {}
        for task_type, stats in (totals.get("task_breakdown") or {}).items():
            task_attempts = max(1, int(stats["attempts"]))
            task_breakdown[task_type] = {
                "attempts": task_attempts,
                "avg_latency_ms": round(float(stats["total_latency_ms"]) / task_attempts, 3),
                "avg_cost_usd": round(float(stats["total_cost_usd"]) / task_attempts, 6),
                "error_rate": round(1.0 - (float(stats["successes"]) / task_attempts), 6),
            }
        return {
            "policy": totals["policy"],
            "attempts": attempts,
            "successes": int(totals["successes"]),
            "failure_count": int(totals["failure_count"]),
            "avg_latency_ms": round(float(totals["total_latency_ms"]) / attempts, 3),
            "total_cost_usd": round(float(totals["total_cost_usd"]), 6),
            "avg_cost_usd": round(float(totals["total_cost_usd"]) / attempts, 6),
            "error_rate": round(float(totals["failure_count"]) / attempts, 6),
            "lane_counts": totals["lane_counts"],
            "task_breakdown": task_breakdown,
            "registry": registry.summary(),
        }

    @staticmethod
    def _score(*, task_type: str, lane: ComputeLane, attempt_index: int) -> float:
        digest = hashlib.sha256(f"{task_type}:{lane.value}:{attempt_index}".encode("utf-8")).digest()
        raw = int.from_bytes(digest[:8], "big")
        return raw / float(2**64 - 1)


def default_harness(benchmark_dir: Optional[Path] = None) -> BenchmarkHarness:
    return BenchmarkHarness(
        benchmark_dir=benchmark_dir,
        lane_profiles=[
            LaneBenchmarkProfile(
                lane=ComputeLane.LOCAL_OLLAMA,
                base_latency_ms=700,
                base_cost_usd=0.0,
                success_rate=0.82,
                task_latency_multiplier={"self_improvement_review": 1.15, "compute_task": 0.8},
                task_success_bonus={"compute_task": 0.08},
            ),
            LaneBenchmarkProfile(
                lane=ComputeLane.GITHUB_MODELS,
                base_latency_ms=180,
                base_cost_usd=0.00025,
                success_rate=0.94,
                task_latency_multiplier={"self_improvement_review": 0.75, "compute_task": 1.1},
                task_success_bonus={"self_improvement_review": 0.02},
            ),
            LaneBenchmarkProfile(
                lane=ComputeLane.XAI_GROK,
                base_latency_ms=950,
                base_cost_usd=0.003,
                success_rate=0.88,
                task_latency_multiplier={"self_improvement_review": 1.1, "compute_task": 1.3},
            ),
        ],
        tasks=[
            BenchmarkTask(task_type="self_improvement_review", rounds=10),
            BenchmarkTask(task_type="compute_task", rounds=6),
        ],
    )


if __name__ == "__main__":
    report = default_harness().run(
        baseline_lane=ComputeLane.XAI_GROK,
        output_path=Path(__file__).resolve().parent / "benchmark-output" / "nomad-runtime-benchmark.json",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
