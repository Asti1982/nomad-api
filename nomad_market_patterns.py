from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parent
DEFAULT_PATTERN_REGISTRY_PATH = ROOT / "nomad_runtime_patterns.json"
TRUSTED_THRESHOLD = 5


class ComputeLane(str, Enum):
    LOCAL_OLLAMA = "local_ollama"
    GITHUB_MODELS = "github_models"
    HUGGINGFACE = "huggingface"
    CLOUDFLARE_WORKERS_AI = "cloudflare_workers_ai"
    XAI_GROK = "xai_grok"
    MODAL = "modal"
    LAMBDA_LABS = "lambda_labs"
    RUNPOD = "runpod"
    CODEBUDDY_BRAIN = "codebuddy_brain"
    UNKNOWN = "unknown"


class PatternStatus(str, Enum):
    CANDIDATE = "candidate"
    TRUSTED = "trusted"
    DEGRADED = "degraded"
    RETIRED = "retired"
    PREMIUM = "premium"


def normalize_compute_lane(value: ComputeLane | str | None) -> ComputeLane:
    if isinstance(value, ComputeLane):
        return value
    cleaned = str(value or "").strip().lower()
    aliases = {
        "ollama": ComputeLane.LOCAL_OLLAMA,
        "local": ComputeLane.LOCAL_OLLAMA,
        "local_ollama": ComputeLane.LOCAL_OLLAMA,
        "github_models": ComputeLane.GITHUB_MODELS,
        "github-models": ComputeLane.GITHUB_MODELS,
        "huggingface": ComputeLane.HUGGINGFACE,
        "cloudflare": ComputeLane.CLOUDFLARE_WORKERS_AI,
        "cloudflare_workers_ai": ComputeLane.CLOUDFLARE_WORKERS_AI,
        "cloudflare-workers-ai": ComputeLane.CLOUDFLARE_WORKERS_AI,
        "xai": ComputeLane.XAI_GROK,
        "xai_grok": ComputeLane.XAI_GROK,
        "xai-grok": ComputeLane.XAI_GROK,
        "modal": ComputeLane.MODAL,
        "lambda": ComputeLane.LAMBDA_LABS,
        "lambda_labs": ComputeLane.LAMBDA_LABS,
        "lambda-labs": ComputeLane.LAMBDA_LABS,
        "runpod": ComputeLane.RUNPOD,
        "codebuddy": ComputeLane.CODEBUDDY_BRAIN,
        "codebuddy_brain": ComputeLane.CODEBUDDY_BRAIN,
        "codebuddy-brain": ComputeLane.CODEBUDDY_BRAIN,
    }
    return aliases.get(cleaned, ComputeLane.UNKNOWN)


@dataclass
class ExecutionRecord:
    timestamp: float = field(default_factory=time.time)
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    success: bool = True
    tokens_used: int = 0
    error_type: str = ""

    def efficiency_contribution(
        self,
        baseline_latency_ms: float = 2000.0,
        baseline_cost_usd: float = 0.01,
    ) -> float:
        if not self.success:
            return 0.0
        latency_score = max(0.0, 1.0 - (self.latency_ms / baseline_latency_ms))
        cost_score = max(0.0, 1.0 - (self.cost_usd / baseline_cost_usd))
        return round((latency_score * 0.55) + (cost_score * 0.45), 6)


@dataclass
class MarketPattern:
    pattern_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    task_type: str = ""
    lane: ComputeLane = ComputeLane.UNKNOWN
    prompt_hash: str = ""
    model_hint: str = ""
    notes: str = ""
    status: PatternStatus = PatternStatus.CANDIDATE
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    executions: list[ExecutionRecord] = field(default_factory=list)
    trust: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.trust, dict):
            self.trust = {}
        self.trust = self._normalize_trust(self.trust)

    @property
    def execution_count(self) -> int:
        return len(self.executions)

    @property
    def success_rate(self) -> float:
        if not self.executions:
            return 0.0
        successes = sum(1 for entry in self.executions if entry.success)
        return successes / len(self.executions)

    @property
    def avg_latency_ms(self) -> float:
        successful = [entry.latency_ms for entry in self.executions if entry.success]
        if not successful:
            return float("inf")
        return sum(successful) / len(successful)

    @property
    def avg_cost_usd(self) -> float:
        successful = [entry.cost_usd for entry in self.executions if entry.success]
        if not successful:
            return float("inf")
        return sum(successful) / len(successful)

    @property
    def p95_latency_ms(self) -> float:
        successful = sorted(entry.latency_ms for entry in self.executions if entry.success)
        if not successful:
            return float("inf")
        index = max(0, int(len(successful) * 0.95) - 1)
        return successful[index]

    @property
    def local_verifications(self) -> int:
        return int(self.trust.get("local_verifications") or 0)

    @property
    def efficiency_score(self) -> float:
        if not self.executions:
            return 0.0
        recent = self.executions[-20:]
        contributions = [entry.efficiency_contribution() for entry in recent]
        avg_efficiency = sum(contributions) / len(contributions)
        reuse_bonus = 0.1 * math.log1p(self.execution_count / 5)
        status_factor = {
            PatternStatus.CANDIDATE: 0.85,
            PatternStatus.TRUSTED: 1.0,
            PatternStatus.PREMIUM: 1.05,
            PatternStatus.DEGRADED: 0.6,
            PatternStatus.RETIRED: 0.0,
        }[self.status]
        return round(min((avg_efficiency + reuse_bonus) * status_factor, 1.0), 4)

    @property
    def price_usd(self) -> float:
        if self.status == PatternStatus.RETIRED:
            return 0.0
        base = self.efficiency_score * 0.5
        if self.status == PatternStatus.PREMIUM:
            base *= 2.0
        if self.execution_count < 3:
            base *= 0.3
        return round(max(base, 0.01), 4)

    @property
    def trust_score(self) -> float:
        base = self.efficiency_score * 0.65
        local_bonus = min(0.2, self.local_verifications * 0.05)
        signed_bonus = 0.1 if self.trust.get("signature_valid") else 0.0
        remote_bonus = min(0.05, int(self.trust.get("remote_observations") or 0) * 0.01)
        degraded_penalty = 0.15 if self.status == PatternStatus.DEGRADED else 0.0
        return round(max(0.0, min(1.0, base + local_bonus + signed_bonus + remote_bonus - degraded_penalty)), 4)

    def record_execution(
        self,
        latency_ms: float,
        cost_usd: float,
        success: bool,
        tokens_used: int = 0,
        error_type: str = "",
        verification: str = "local",
    ) -> "MarketPattern":
        self.executions.append(
            ExecutionRecord(
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                success=success,
                tokens_used=tokens_used,
                error_type=error_type,
            )
        )
        self.updated_at = time.time()
        self._apply_verification(verification=verification, success=success)
        self._update_status()
        return self

    def _update_status(self) -> None:
        if self.status == PatternStatus.RETIRED:
            return

        if self.execution_count >= 5:
            recent = self.executions[-5:]
            recent_failures = sum(1 for entry in recent if not entry.success)
            if recent_failures >= 3:
                self.status = PatternStatus.DEGRADED
                return
            if (
                self.status == PatternStatus.DEGRADED
                and recent_failures <= 1
                and self.success_rate >= 0.7
                and (self.local_verifications >= 2 or self.execution_count >= TRUSTED_THRESHOLD)
            ):
                self.status = PatternStatus.TRUSTED if self.execution_count >= TRUSTED_THRESHOLD else PatternStatus.CANDIDATE

        if self.status == PatternStatus.CANDIDATE:
            imported_candidate = bool(self.trust.get("imported"))
            signed_candidate_ready = bool(self.trust.get("signature_valid")) and self.local_verifications >= 2 and self.success_rate >= 0.75
            broadly_trusted_ready = (
                not imported_candidate
                and self.execution_count >= TRUSTED_THRESHOLD
                and self.success_rate >= 0.8
            )
            locally_reverified_import = imported_candidate and self.local_verifications >= 3 and self.success_rate >= 0.8
            if signed_candidate_ready or broadly_trusted_ready or locally_reverified_import:
                self.status = PatternStatus.TRUSTED

        if (
            self.status == PatternStatus.TRUSTED
            and self.local_verifications >= 8
            and self.execution_count >= 10
            and self.success_rate >= 0.92
            and self.p95_latency_ms <= 1000
            and self.avg_cost_usd <= 0.003
        ):
            self.status = PatternStatus.PREMIUM

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["lane"] = self.lane.value
        payload["status"] = self.status.value
        payload["trust_score"] = self.trust_score
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MarketPattern":
        executions = [
            ExecutionRecord(**entry)
            for entry in (payload.get("executions") or [])
            if isinstance(entry, dict)
        ]
        return cls(
            pattern_id=str(payload.get("pattern_id") or str(uuid.uuid4())[:12]),
            task_type=str(payload.get("task_type") or ""),
            lane=normalize_compute_lane(payload.get("lane")),
            prompt_hash=str(payload.get("prompt_hash") or ""),
            model_hint=str(payload.get("model_hint") or ""),
            notes=str(payload.get("notes") or ""),
            status=PatternStatus(str(payload.get("status") or PatternStatus.CANDIDATE.value)),
            created_at=float(payload.get("created_at") or time.time()),
            updated_at=float(payload.get("updated_at") or time.time()),
            executions=executions,
            trust=payload.get("trust") if isinstance(payload.get("trust"), dict) else {},
        )

    def _apply_verification(self, verification: str, success: bool) -> None:
        normalized = str(verification or "local").strip().lower()
        if normalized == "local":
            self.trust["last_local_verification_at"] = time.time()
            if success:
                self.trust["local_verifications"] = self.local_verifications + 1
            self.trust["verification_state"] = "locally_verified" if self.local_verifications > 0 or success else "candidate"
            return
        if normalized == "remote":
            self.trust["remote_observations"] = int(self.trust.get("remote_observations") or 0) + 1

    @staticmethod
    def _normalize_trust(trust: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(trust)
        normalized["local_verifications"] = int(normalized.get("local_verifications") or 0)
        normalized["remote_observations"] = int(normalized.get("remote_observations") or 0)
        normalized["signature_valid"] = bool(normalized.get("signature_valid", False))
        normalized["imported"] = bool(normalized.get("imported", False))
        normalized["verification_state"] = str(normalized.get("verification_state") or "candidate")
        return normalized


class MarketPatternRegistry:
    REGISTRY_PATH = DEFAULT_PATTERN_REGISTRY_PATH

    def __init__(self, registry_path: Optional[Path] = None):
        self._path = Path(registry_path or self.REGISTRY_PATH)
        self._patterns: dict[str, MarketPattern] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        for entry in payload.get("patterns", []):
            try:
                pattern = MarketPattern.from_dict(entry)
            except Exception:
                continue
            self._patterns[pattern.pattern_id] = pattern

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(
                {
                    "schema_version": "nomad.market_patterns.v1",
                    "updated_at": time.time(),
                    "total_patterns": len(self._patterns),
                    "patterns": [pattern.to_dict() for pattern in self._patterns.values()],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def mint_from_execution(
        self,
        task_type: str,
        compute_lane: ComputeLane | str,
        latency_ms: float,
        cost_usd: float,
        success: bool,
        prompt_hash: str = "",
        model_hint: str = "",
        tokens_used: int = 0,
        error_type: str = "",
        notes: str = "",
        verification: str = "local",
    ) -> MarketPattern:
        lane = normalize_compute_lane(compute_lane)
        existing = self._find_matching(task_type=task_type, lane=lane, prompt_hash=prompt_hash)
        if existing:
            existing.record_execution(
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                success=success,
                tokens_used=tokens_used,
                error_type=error_type,
                verification=verification,
            )
            if notes:
                existing.notes = notes
            if model_hint:
                existing.model_hint = model_hint
            self._save()
            return existing

        pattern = MarketPattern(
            task_type=task_type,
            lane=lane,
            prompt_hash=prompt_hash or self._hash_strategy(task_type, lane, model_hint),
            model_hint=model_hint,
            notes=notes,
        )
        pattern.record_execution(
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            success=success,
            tokens_used=tokens_used,
            error_type=error_type,
            verification=verification,
        )
        self._patterns[pattern.pattern_id] = pattern
        self._save()
        return pattern

    def best_for(
        self,
        task_type: str,
        budget_usd: Optional[float] = None,
        max_latency_ms: Optional[float] = None,
        preferred_lanes: Optional[list[ComputeLane]] = None,
        exclude_degraded: bool = True,
    ) -> Optional[MarketPattern]:
        candidates = [
            pattern
            for pattern in self._patterns.values()
            if pattern.task_type == task_type
            and pattern.status != PatternStatus.RETIRED
            and (not exclude_degraded or pattern.status != PatternStatus.DEGRADED)
        ]
        if budget_usd is not None:
            candidates = [pattern for pattern in candidates if pattern.avg_cost_usd <= budget_usd]
        if max_latency_ms is not None:
            candidates = [pattern for pattern in candidates if pattern.avg_latency_ms <= max_latency_ms]
        if preferred_lanes:
            preferred = [pattern for pattern in candidates if pattern.lane in preferred_lanes]
            if preferred:
                candidates = preferred
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.efficiency_score)

    def all_for_task(self, task_type: str) -> list[MarketPattern]:
        patterns = [pattern for pattern in self._patterns.values() if pattern.task_type == task_type]
        return sorted(patterns, key=lambda item: item.efficiency_score, reverse=True)

    def degraded(self) -> list[MarketPattern]:
        return [pattern for pattern in self._patterns.values() if pattern.status == PatternStatus.DEGRADED]

    def promote_to_premium(self, pattern_id: str, reason: str = "") -> MarketPattern:
        pattern = self._get(pattern_id)
        if pattern.status != PatternStatus.TRUSTED:
            raise ValueError(
                f"Pattern {pattern_id} must be TRUSTED before promotion (current: {pattern.status.value})"
            )
        pattern.status = PatternStatus.PREMIUM
        if reason:
            pattern.notes = f"{pattern.notes} [PREMIUM: {reason}]".strip()
        self._save()
        return pattern

    def retire(self, pattern_id: str, reason: str = "") -> MarketPattern:
        pattern = self._get(pattern_id)
        pattern.status = PatternStatus.RETIRED
        if reason:
            pattern.notes = f"{pattern.notes} [RETIRED: {reason}]".strip()
        self._save()
        return pattern

    def premium_catalog(self) -> list[dict[str, Any]]:
        catalog: list[dict[str, Any]] = []
        for pattern in self._patterns.values():
            if pattern.status != PatternStatus.PREMIUM:
                continue
            catalog.append(
                {
                    "pattern_id": pattern.pattern_id,
                    "task_type": pattern.task_type,
                    "lane": pattern.lane.value,
                    "model_hint": pattern.model_hint,
                    "efficiency": pattern.efficiency_score,
                    "avg_latency_ms": round(pattern.avg_latency_ms, 1),
                    "avg_cost_usd": round(pattern.avg_cost_usd, 6),
                    "price_usd": pattern.price_usd,
                    "executions": pattern.execution_count,
                    "trust_score": pattern.trust_score,
                    "notes": pattern.notes,
                }
            )
        return catalog

    def export_bundle(
        self,
        output_path: str | Path,
        min_status: PatternStatus = PatternStatus.TRUSTED,
        include_executions: bool = False,
    ) -> Path:
        exportable = [
            pattern
            for pattern in self._patterns.values()
            if pattern.status in {PatternStatus.TRUSTED, PatternStatus.PREMIUM, min_status}
        ]
        payload = {
            "schema_version": "nomad.market_patterns.bundle.v1",
            "exported_at": time.time(),
            "source": "nomad",
            "total_patterns": len(exportable),
            "patterns": [
                {
                    **pattern.to_dict(),
                    "executions": pattern.to_dict()["executions"] if include_executions else [],
                }
                for pattern in exportable
            ],
        }
        out = Path(output_path)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return out

    def bundle_payload(
        self,
        task_type: str = "",
        min_status: PatternStatus = PatternStatus.CANDIDATE,
        include_executions: bool = True,
        max_patterns: int = 50,
        max_executions_per_pattern: int = 20,
    ) -> dict[str, Any]:
        patterns = list(self._patterns.values())
        if task_type:
            patterns = [pattern for pattern in patterns if pattern.task_type == task_type]

        allowed_statuses = self._exportable_statuses(min_status=min_status)
        patterns = [
            pattern
            for pattern in patterns
            if pattern.status in allowed_statuses and pattern.status != PatternStatus.RETIRED
        ]
        patterns.sort(
            key=lambda item: (
                -item.efficiency_score,
                -item.execution_count,
                str(item.task_type).lower(),
                str(item.lane.value).lower(),
            )
        )
        patterns = patterns[:max_patterns]

        payload_patterns: list[dict[str, Any]] = []
        for pattern in patterns:
            data = pattern.to_dict()
            if include_executions:
                data["executions"] = data.get("executions", [])[-max_executions_per_pattern:]
            else:
                data["executions"] = []
            payload_patterns.append(data)

        return {
            "schema_version": "nomad.market_patterns.bundle.v1",
            "exported_at": time.time(),
            "registry_path": str(self._path),
            "task_type": task_type,
            "min_status": min_status.value,
            "total_patterns": len(payload_patterns),
            "patterns": payload_patterns,
        }

    def import_bundle(
        self,
        bundle_path: str | Path,
        trust_level: PatternStatus = PatternStatus.CANDIDATE,
    ) -> int:
        payload = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
        imported = 0
        for entry in payload.get("patterns", []):
            if entry.get("pattern_id") in self._patterns:
                continue
            pattern = MarketPattern.from_dict(entry)
            if pattern.status in {PatternStatus.TRUSTED, PatternStatus.PREMIUM}:
                pattern.status = trust_level
            self._patterns[pattern.pattern_id] = pattern
            imported += 1
        if imported:
            self._save()
        return imported

    def import_bundle_payload(
        self,
        payload: dict[str, Any],
        trust_level: PatternStatus = PatternStatus.CANDIDATE,
        source: str = "",
        source_node: Optional[dict[str, Any]] = None,
        verification: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        imported = 0
        skipped_existing = 0
        imported_ids: list[str] = []
        verification = verification or {}
        for entry in payload.get("patterns", []):
            if not isinstance(entry, dict):
                continue
            pattern_id = str(entry.get("pattern_id") or "").strip()
            if pattern_id and pattern_id in self._patterns:
                skipped_existing += 1
                continue
            pattern = MarketPattern.from_dict(entry)
            remote_status = pattern.status.value
            if pattern.status in {PatternStatus.TRUSTED, PatternStatus.PREMIUM}:
                pattern.status = trust_level
            pattern.trust.update(
                {
                    "imported": True,
                    "source": source,
                    "source_node": source_node or {},
                    "remote_status": remote_status,
                    "remote_verification_count": int(pattern.trust.get("local_verifications") or 0),
                    "signature_valid": bool(verification.get("signature_valid")),
                    "verification_reason": str(verification.get("reason") or ""),
                    "verification_state": "signed_candidate" if verification.get("signature_valid") else "unsigned_candidate",
                    "imported_at": time.time(),
                    "local_verifications": 0,
                }
            )
            if source:
                pattern.notes = f"{pattern.notes} [IMPORTED_FROM: {source}]".strip()
            self._patterns[pattern.pattern_id] = pattern
            imported += 1
            imported_ids.append(pattern.pattern_id)
        if imported:
            self._save()
        return {
            "ok": True,
            "imported": imported,
            "skipped_existing": skipped_existing,
            "trust_level": trust_level.value,
            "imported_pattern_ids": imported_ids,
        }

    def evaluate_promotions(self) -> dict[str, Any]:
        changes: list[dict[str, Any]] = []
        for pattern in self._patterns.values():
            before = pattern.status
            pattern._update_status()
            if pattern.status != before:
                changes.append(
                    {
                        "pattern_id": pattern.pattern_id,
                        "task_type": pattern.task_type,
                        "from_status": before.value,
                        "to_status": pattern.status.value,
                        "trust_score": pattern.trust_score,
                    }
                )
        if changes:
            self._save()
        return {
            "ok": True,
            "changed": len(changes),
            "changes": changes,
        }

    def summary(self, task_type: str = "") -> dict[str, Any]:
        patterns = list(self._patterns.values())
        if task_type:
            patterns = [pattern for pattern in patterns if pattern.task_type == task_type]
        top = sorted(patterns, key=lambda item: item.efficiency_score, reverse=True)[:5]
        by_status: dict[str, int] = {}
        for pattern in patterns:
            by_status[pattern.status.value] = by_status.get(pattern.status.value, 0) + 1
        return {
            "registry_path": str(self._path),
            "pattern_count": len(patterns),
            "by_status": by_status,
            "degraded_count": sum(1 for pattern in patterns if pattern.status == PatternStatus.DEGRADED),
            "signed_pattern_count": sum(1 for pattern in patterns if pattern.trust.get("signature_valid")),
            "reverified_pattern_count": sum(1 for pattern in patterns if pattern.local_verifications > 0),
            "promotion_rules": self.promotion_rules(),
            "top_patterns": [
                {
                    "pattern_id": pattern.pattern_id,
                    "task_type": pattern.task_type,
                    "lane": pattern.lane.value,
                    "status": pattern.status.value,
                    "efficiency_score": pattern.efficiency_score,
                    "execution_count": pattern.execution_count,
                    "trust_score": pattern.trust_score,
                }
                for pattern in top
            ],
        }

    def _find_matching(self, task_type: str, lane: ComputeLane, prompt_hash: str) -> Optional[MarketPattern]:
        for pattern in self._patterns.values():
            if pattern.task_type != task_type or pattern.lane != lane:
                continue
            if not prompt_hash or pattern.prompt_hash == prompt_hash:
                return pattern
        return None

    def _get(self, pattern_id: str) -> MarketPattern:
        if pattern_id not in self._patterns:
            raise KeyError(f"Pattern '{pattern_id}' was not found.")
        return self._patterns[pattern_id]

    @staticmethod
    def _hash_strategy(task_type: str, lane: ComputeLane, model_hint: str) -> str:
        return hashlib.sha256(f"{task_type}:{lane.value}:{model_hint}".encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _exportable_statuses(min_status: PatternStatus) -> set[PatternStatus]:
        if min_status == PatternStatus.PREMIUM:
            return {PatternStatus.PREMIUM}
        if min_status == PatternStatus.TRUSTED:
            return {PatternStatus.TRUSTED, PatternStatus.PREMIUM}
        return {PatternStatus.CANDIDATE, PatternStatus.TRUSTED, PatternStatus.PREMIUM}

    @staticmethod
    def promotion_rules() -> dict[str, Any]:
        return {
            "candidate_to_trusted": {
                "execution_count_min": TRUSTED_THRESHOLD,
                "success_rate_min": 0.8,
                "or_signed_local_reverify": {
                    "signature_valid": True,
                    "local_verifications_min": 2,
                    "success_rate_min": 0.75,
                },
            },
            "trusted_to_premium": {
                "local_verifications_min": 8,
                "execution_count_min": 10,
                "success_rate_min": 0.92,
                "p95_latency_ms_max": 1000,
                "avg_cost_usd_max": 0.003,
            },
            "degrade": {
                "recent_window": 5,
                "recent_failures_min": 3,
            },
            "recover_from_degraded": {
                "recent_failures_max": 1,
                "success_rate_min": 0.7,
                "local_verifications_min": 2,
            },
        }
