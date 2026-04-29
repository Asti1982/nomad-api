from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from nomad_market_patterns import (
    ROOT,
    ComputeLane,
    MarketPatternRegistry,
    normalize_compute_lane,
)


DEFAULT_LANE_HEALTH_PATH = ROOT / "nomad_lane_health.json"


def current_time_bucket(now: Optional[time.struct_time] = None) -> str:
    current = now or time.localtime()
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    hour_block = (current.tm_hour // 2) * 2
    return f"{days[current.tm_wday]}_{hour_block:02d}"


@dataclass
class LaneHealthRecord:
    lane: ComputeLane
    bucket_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_error_at: Optional[float] = None
    consecutive_errors: int = 0
    is_circuit_open: bool = False
    circuit_opened_at: Optional[float] = None

    CIRCUIT_THRESHOLD = 5
    CIRCUIT_COOLDOWN_SECONDS = 300

    def record(self, latency_ms: float, success: bool) -> None:
        bucket = current_time_bucket()
        stats = self.bucket_stats.setdefault(
            bucket,
            {"latency_ms": [], "error_count": 0, "call_count": 0},
        )
        stats["call_count"] += 1
        if success:
            stats["latency_ms"].append(float(latency_ms))
            stats["latency_ms"] = stats["latency_ms"][-100:]
            self.consecutive_errors = 0
            if self.is_circuit_open and self._cooldown_elapsed():
                self._close_circuit()
            return

        stats["error_count"] += 1
        self.last_error_at = time.time()
        self.consecutive_errors += 1
        if self.consecutive_errors >= self.CIRCUIT_THRESHOLD:
            self._open_circuit()

    def predicted_latency_ms(self) -> float:
        bucket = current_time_bucket()
        bucket_latency = self.bucket_stats.get(bucket, {}).get("latency_ms") or []
        if bucket_latency:
            weights = [math.exp(0.08 * idx) for idx in range(len(bucket_latency))]
            total = sum(weights)
            return sum(latency * weight for latency, weight in zip(bucket_latency, weights)) / total

        all_latencies: list[float] = []
        for stats in self.bucket_stats.values():
            all_latencies.extend(float(latency) for latency in (stats.get("latency_ms") or []))
        if all_latencies:
            return sum(all_latencies) / len(all_latencies)
        return 2000.0

    def predicted_error_rate(self) -> float:
        bucket = current_time_bucket()
        stats = self.bucket_stats.get(bucket) or {}
        calls = int(stats.get("call_count") or 0)
        errors = int(stats.get("error_count") or 0)
        if calls >= 3:
            return errors / max(calls, 1)

        total_calls = sum(int(item.get("call_count") or 0) for item in self.bucket_stats.values())
        total_errors = sum(int(item.get("error_count") or 0) for item in self.bucket_stats.values())
        if total_calls <= 0:
            return 0.1
        return total_errors / total_calls

    @property
    def is_available(self) -> bool:
        if not self.is_circuit_open:
            return True
        return self._cooldown_elapsed()

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane.value,
            "bucket_stats": self.bucket_stats,
            "last_error_at": self.last_error_at,
            "consecutive_errors": self.consecutive_errors,
            "is_circuit_open": self.is_circuit_open,
            "circuit_opened_at": self.circuit_opened_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LaneHealthRecord":
        record = cls(lane=normalize_compute_lane(payload.get("lane")))
        record.bucket_stats = payload.get("bucket_stats") or {}
        record.last_error_at = payload.get("last_error_at")
        record.consecutive_errors = int(payload.get("consecutive_errors") or 0)
        record.is_circuit_open = bool(payload.get("is_circuit_open", False))
        record.circuit_opened_at = payload.get("circuit_opened_at")
        return record

    def _open_circuit(self) -> None:
        self.is_circuit_open = True
        self.circuit_opened_at = time.time()

    def _close_circuit(self) -> None:
        self.is_circuit_open = False
        self.circuit_opened_at = None
        self.consecutive_errors = 0

    def _cooldown_elapsed(self) -> bool:
        if not self.circuit_opened_at:
            return False
        return (time.time() - self.circuit_opened_at) >= self.CIRCUIT_COOLDOWN_SECONDS


@dataclass
class RoutingDecision:
    task_type: str
    chosen_lane: ComputeLane
    pattern_id: Optional[str]
    predicted_latency_ms: float
    predicted_error_rate: float
    routing_score: float
    reason: str
    fallback_lanes: list[ComputeLane] = field(default_factory=list)
    decided_at: float = field(default_factory=time.time)

    def is_high_confidence(self) -> bool:
        return self.routing_score >= 0.7 and self.predicted_error_rate <= 0.1

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "chosen_lane": self.chosen_lane.value,
            "pattern_id": self.pattern_id,
            "predicted_latency_ms": round(self.predicted_latency_ms, 1),
            "predicted_error_rate": round(self.predicted_error_rate, 4),
            "routing_score": round(self.routing_score, 4),
            "reason": self.reason,
            "fallback_lanes": [lane.value for lane in self.fallback_lanes],
            "high_confidence": self.is_high_confidence(),
        }


class PredictiveRouter:
    HEALTH_PATH = DEFAULT_LANE_HEALTH_PATH
    LANE_COST_PRIOR: dict[ComputeLane, float] = {
        ComputeLane.LOCAL_OLLAMA: 0.0,
        ComputeLane.GITHUB_MODELS: 0.0002,
        ComputeLane.HUGGINGFACE: 0.0004,
        ComputeLane.CLOUDFLARE_WORKERS_AI: 0.0005,
        ComputeLane.XAI_GROK: 0.003,
        ComputeLane.MODAL: 0.0005,
        ComputeLane.LAMBDA_LABS: 0.0007,
        ComputeLane.RUNPOD: 0.0006,
        ComputeLane.CODEBUDDY_BRAIN: 0.0003,
        ComputeLane.UNKNOWN: 0.01,
    }

    def __init__(
        self,
        registry: Optional[MarketPatternRegistry] = None,
        health_path: Optional[Path] = None,
    ) -> None:
        self._registry = registry or MarketPatternRegistry()
        self._health_path = Path(health_path or self.HEALTH_PATH)
        self._health: dict[ComputeLane, LaneHealthRecord] = {}
        self._load_health()

    def rank_lanes(
        self,
        task_type: str,
        lanes: Optional[list[ComputeLane]] = None,
        budget_usd: Optional[float] = None,
        max_latency_ms: Optional[float] = None,
        preferred_lanes: Optional[list[ComputeLane]] = None,
    ) -> list[dict[str, Any]]:
        candidate_lanes = [
            normalize_compute_lane(lane)
            for lane in (lanes or list(ComputeLane))
            if normalize_compute_lane(lane) != ComputeLane.UNKNOWN
        ]
        if not candidate_lanes:
            candidate_lanes = [ComputeLane.LOCAL_OLLAMA]

        ranked: list[dict[str, Any]] = []
        for lane in candidate_lanes:
            health = self._get_health(lane)
            if not health.is_available:
                continue

            predicted_latency = health.predicted_latency_ms()
            predicted_error_rate = health.predicted_error_rate()
            cost_prior = self.LANE_COST_PRIOR.get(lane, 0.01)
            if budget_usd is not None and cost_prior > budget_usd:
                continue
            if max_latency_ms is not None and predicted_latency > (max_latency_ms * 1.2):
                continue

            pattern = self._registry.best_for(
                task_type=task_type,
                budget_usd=budget_usd,
                max_latency_ms=max_latency_ms,
                preferred_lanes=[lane],
            )
            pattern_score = pattern.efficiency_score if pattern else 0.3
            latency_score = max(0.0, 1.0 - (predicted_latency / 5000.0))
            error_score = max(0.0, 1.0 - (predicted_error_rate * 3))
            cost_score = 1.0 - min(1.0, cost_prior / 0.01)
            preferred_bonus = 0.1 if preferred_lanes and lane in preferred_lanes else 0.0

            combined = round(
                (pattern_score * 0.4)
                + (latency_score * 0.25)
                + (error_score * 0.2)
                + (cost_score * 0.1)
                + (preferred_bonus * 0.05),
                6,
            )
            ranked.append(
                {
                    "lane": lane,
                    "pattern_id": pattern.pattern_id if pattern else None,
                    "pattern_score": pattern_score,
                    "predicted_latency_ms": predicted_latency,
                    "predicted_error_rate": predicted_error_rate,
                    "cost_prior": cost_prior,
                    "routing_score": combined,
                }
            )

        ranked.sort(
            key=lambda item: (
                -float(item["routing_score"]),
                float(item["predicted_latency_ms"]),
                float(item["predicted_error_rate"]),
                str(item["lane"].value),
            )
        )
        return ranked

    def route(
        self,
        task_type: str,
        budget_usd: Optional[float] = None,
        max_latency_ms: Optional[float] = None,
        preferred_lanes: Optional[list[ComputeLane]] = None,
        require_high_confidence: bool = False,
    ) -> RoutingDecision:
        ranked = self.rank_lanes(
            task_type=task_type,
            budget_usd=budget_usd,
            max_latency_ms=max_latency_ms,
            preferred_lanes=preferred_lanes,
        )
        if not ranked:
            return RoutingDecision(
                task_type=task_type,
                chosen_lane=ComputeLane.LOCAL_OLLAMA,
                pattern_id=None,
                predicted_latency_ms=2000.0,
                predicted_error_rate=0.2,
                routing_score=0.1,
                reason="No lane satisfied the active constraints. Falling back to local_ollama.",
            )

        best = ranked[0]
        decision = RoutingDecision(
            task_type=task_type,
            chosen_lane=best["lane"],
            pattern_id=best["pattern_id"],
            predicted_latency_ms=best["predicted_latency_ms"],
            predicted_error_rate=best["predicted_error_rate"],
            routing_score=best["routing_score"],
            reason=self._build_reason(best=best, ranked=ranked),
            fallback_lanes=[item["lane"] for item in ranked[1:4]],
        )
        if require_high_confidence and not decision.is_high_confidence():
            modal_available = any(item["lane"] == ComputeLane.MODAL for item in ranked)
            if modal_available:
                decision.chosen_lane = ComputeLane.MODAL
                decision.reason = f"Low-confidence decision. Modal sandbox chosen instead. Original: {decision.reason}"
        return decision

    def record_outcome(
        self,
        lane: ComputeLane | str,
        latency_ms: float,
        success: bool,
        task_type: str = "",
        cost_usd: float = 0.0,
        tokens_used: int = 0,
        error_type: str = "",
        prompt_hash: str = "",
        model_hint: str = "",
        notes: str = "",
        verification: str = "local",
    ) -> None:
        normalized_lane = normalize_compute_lane(lane)
        self._get_health(normalized_lane).record(latency_ms=latency_ms, success=success)
        if task_type:
            self._registry.mint_from_execution(
                task_type=task_type,
                compute_lane=normalized_lane,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                success=success,
                tokens_used=tokens_used,
                error_type=error_type,
                prompt_hash=prompt_hash,
                model_hint=model_hint,
                notes=notes,
                verification=verification,
            )
        self._save_health()

    def lane_status(self) -> dict[str, Any]:
        payload = {"time_bucket": current_time_bucket(), "lanes": {}}
        for lane in ComputeLane:
            if lane == ComputeLane.UNKNOWN:
                continue
            health = self._get_health(lane)
            payload["lanes"][lane.value] = {
                "available": health.is_available,
                "circuit_open": health.is_circuit_open,
                "consecutive_errors": health.consecutive_errors,
                "predicted_latency_ms": round(health.predicted_latency_ms(), 1),
                "predicted_error_rate": round(health.predicted_error_rate(), 4),
            }
        return payload

    def _build_reason(self, best: dict[str, Any], ranked: list[dict[str, Any]]) -> str:
        bucket = current_time_bucket()
        parts = [f"Lane {best['lane'].value} selected for bucket {bucket}."]
        if best["predicted_error_rate"] <= 0.02:
            parts.append("Observed failure pressure is low.")
        elif best["predicted_error_rate"] >= 0.15:
            parts.append(f"Failure pressure is elevated at {best['predicted_error_rate']:.0%}.")
        if best["predicted_latency_ms"] <= 300:
            parts.append(f"Low latency is expected ({best['predicted_latency_ms']:.0f}ms).")
        elif best["predicted_latency_ms"] >= 1500:
            parts.append(f"Latency is expected to be high ({best['predicted_latency_ms']:.0f}ms).")
        if len(ranked) > 1:
            runner_up = ranked[1]
            delta = best["routing_score"] - runner_up["routing_score"]
            parts.append(f"Margin vs {runner_up['lane'].value}: +{delta:.3f}.")
        return " ".join(parts)

    def _get_health(self, lane: ComputeLane | str) -> LaneHealthRecord:
        normalized_lane = normalize_compute_lane(lane)
        if normalized_lane not in self._health:
            self._health[normalized_lane] = LaneHealthRecord(lane=normalized_lane)
        return self._health[normalized_lane]

    def _load_health(self) -> None:
        if not self._health_path.exists():
            return
        try:
            payload = json.loads(self._health_path.read_text(encoding="utf-8"))
        except Exception:
            return
        for entry in payload.get("lanes", []):
            try:
                record = LaneHealthRecord.from_dict(entry)
            except Exception:
                continue
            self._health[record.lane] = record

    def _save_health(self) -> None:
        self._health_path.write_text(
            json.dumps(
                {
                    "schema_version": "nomad.lane_health.v1",
                    "updated_at": time.time(),
                    "lanes": [record.to_dict() for record in self._health.values()],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
