import os
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Optional


class DecisionEngine:
    """Nomad's local season controller for autonomous work timing."""

    def __init__(
        self,
        state: Optional[Dict[str, Any]] = None,
        snapshot: Optional[Dict[str, Any]] = None,
        now: Optional[datetime] = None,
    ):
        self.state = state or {}
        self.snapshot = snapshot or {}
        self.now = now or datetime.now(UTC)
        self.min_check_seconds = self._env_int("NOMAD_AUTOPILOT_MIN_CHECK_SECONDS", 300)
        self.max_check_seconds = self._env_int("NOMAD_AUTOPILOT_MAX_CHECK_SECONDS", 3600)
        self.force_after_seconds = self._env_int("NOMAD_AUTOPILOT_FORCE_AFTER_SECONDS", 4 * 3600)
        self.opportunistic_after_seconds = self._env_int(
            "NOMAD_AUTOPILOT_OPPORTUNISTIC_AFTER_SECONDS",
            90 * 60,
        )
        self.payment_poll_seconds = self._env_int(
            "NOMAD_AUTOPILOT_PAYMENT_POLL_SECONDS",
            60 * 60,
        )
        self.contact_poll_seconds = self._env_int(
            "NOMAD_AUTOPILOT_CONTACT_POLL_SECONDS",
            30 * 60,
        )

    def should_start_cycle(self) -> bool:
        return bool(self.decide().get("should_start"))

    def decide(self) -> Dict[str, Any]:
        task_stats = self._task_stats()
        active_lanes = self._active_compute_lanes()
        last_run = self._last_run_at()
        seconds_since_last_run = self._seconds_since(last_run)
        reasons: list[str] = []

        # 1. Immediate priority: Paid or awaiting tasks
        if task_stats.get("paid", 0) > 0:
            reasons.append("paid_service_task")
            return self._decision(True, reasons, task_stats, active_lanes, 60, last_run)

        # 2. Reputation growth: if Mutual-Aid exists but is still shallow, scout again after the normal wait.
        mutual_aid_score = self._mutual_aid_score()
        if (
            mutual_aid_score is not None
            and mutual_aid_score < 10
            and seconds_since_last_run >= self.opportunistic_after_seconds
        ):
            reasons.append("low_reputation_scout_required")
            return self._decision(True, reasons, task_stats, active_lanes, 60, last_run)

        # 3. Prevent stale state
        if last_run is None:
            reasons.append("first_run")
            return self._decision(True, reasons, task_stats, active_lanes, 60, last_run)

        if seconds_since_last_run >= self.force_after_seconds:
            reasons.append("max_idle_elapsed")
            return self._decision(True, reasons, task_stats, active_lanes, 60, last_run)

        if (
            task_stats.get("awaiting_payment", 0) > 0
            and seconds_since_last_run >= self.payment_poll_seconds
        ):
            reasons.append("payment_followup_due")
            return self._decision(True, reasons, task_stats, active_lanes, 60, last_run)

        if self._sent_contact_count() > 0 and seconds_since_last_run >= self.contact_poll_seconds:
            reasons.append("contact_poll_due")
            return self._decision(True, reasons, task_stats, active_lanes, 60, last_run)

        if len(active_lanes) >= 2 and seconds_since_last_run >= self.opportunistic_after_seconds:
            reasons.append("compute_capacity_available")
            return self._decision(True, reasons, task_stats, active_lanes, 60, last_run)

        next_check_seconds = self._next_idle_check_seconds(
            seconds_since_last_run=seconds_since_last_run,
            task_stats=task_stats,
            active_lanes=active_lanes,
        )
        reasons.append("waiting_for_next_trigger")
        return self._decision(
            False,
            reasons,
            task_stats,
            active_lanes,
            next_check_seconds,
            last_run,
        )

    def _decision(
        self,
        should_start: bool,
        reasons: list[str],
        task_stats: Dict[str, int],
        active_lanes: list[str],
        next_check_seconds: int,
        last_run: Optional[datetime],
    ) -> Dict[str, Any]:
        clamped = self._clamp_check_seconds(next_check_seconds)
        next_check_at = self.now + timedelta(seconds=clamped)
        return {
            "mode": "autopilot_decision",
            "timestamp": self.now.isoformat(),
            "should_start": should_start,
            "reason": reasons[0] if reasons else "",
            "reasons": reasons,
            "next_check_seconds": clamped,
            "next_check_at": next_check_at.isoformat(),
            "last_run_at": last_run.isoformat() if last_run else "",
            "active_compute_lanes": active_lanes,
            "task_stats": task_stats,
        }

    def _next_idle_check_seconds(
        self,
        seconds_since_last_run: int,
        task_stats: Dict[str, int],
        active_lanes: list[str],
    ) -> int:
        candidates = [self.max_check_seconds]
        candidates.append(self.force_after_seconds - seconds_since_last_run)
        if task_stats.get("awaiting_payment", 0) > 0:
            candidates.append(self.payment_poll_seconds - seconds_since_last_run)
        if self._sent_contact_count() > 0:
            candidates.append(self.contact_poll_seconds - seconds_since_last_run)
        if len(active_lanes) >= 2:
            candidates.append(self.opportunistic_after_seconds - seconds_since_last_run)
        positive_candidates = [value for value in candidates if value > 0]
        if not positive_candidates:
            return self.min_check_seconds
        return min(positive_candidates)

    def _clamp_check_seconds(self, seconds: int) -> int:
        return max(self.min_check_seconds, min(self.max_check_seconds, int(seconds)))

    def _task_stats(self) -> Dict[str, int]:
        snapshot_tasks = self.snapshot.get("tasks") or {}
        state_service = self.state.get("last_service") or {}
        state_stats = state_service.get("stats") or {}

        def count(name: str, key: str = "") -> int:
            raw = snapshot_tasks.get(name)
            if raw is None:
                raw = state_stats.get(name)
            if raw is None and key:
                raw = len(state_service.get(key) or [])
            try:
                return int(raw or 0)
            except (TypeError, ValueError):
                return 0

        return {
            "paid": count("paid", "paid_task_ids"),
            "awaiting_payment": count("awaiting_payment", "awaiting_payment_task_ids"),
            "draft_ready": count("draft_ready", "draft_ready_task_ids"),
            "completed": count("completed", "completed_task_ids"),
            "total": count("total"),
        }

    def _active_compute_lanes(self) -> list[str]:
        compute = self.snapshot.get("compute_lanes") or {}
        active: list[str] = []
        for scope in ("local", "hosted"):
            lanes = compute.get(scope) or {}
            if not isinstance(lanes, dict):
                continue
            for name, value in lanes.items():
                available = bool(value.get("available")) if isinstance(value, dict) else bool(value)
                if available:
                    active.append(f"{scope}.{name}")
        if active:
            return sorted(active)

        compute_watch = ((self.state.get("last_self_improvement") or {}).get("compute_watch") or {})
        return sorted(str(lane) for lane in (compute_watch.get("active_lanes") or []) if lane)

    def _sent_contact_count(self) -> int:
        stats = ((self.state.get("last_contact_poll") or {}).get("stats") or {})
        try:
            return int(stats.get("sent") or 0)
        except (TypeError, ValueError):
            return 0

    def _mutual_aid_score(self) -> Optional[int]:
        sources = [
            self.snapshot.get("mutual_aid") or {},
            self.state.get("last_mutual_aid") or {},
            self.state.get("mutual_aid") or {},
        ]
        for source in sources:
            raw = source.get("mutual_aid_score")
            if raw is None:
                raw = source.get("score")
            if raw is None:
                continue
            try:
                return int(raw)
            except (TypeError, ValueError):
                continue
        return None

    def _last_run_at(self) -> Optional[datetime]:
        raw = self.state.get("last_run_at") or self.snapshot.get("last_run_at") or ""
        parsed = self._parse_datetime(raw)
        if parsed:
            return parsed
        last_decision = self.state.get("last_decision") or {}
        if last_decision.get("should_start"):
            return self._parse_datetime(last_decision.get("timestamp"))
        return None

    def _seconds_since(self, value: Optional[datetime]) -> int:
        if not value:
            return 10**9
        return max(0, int((self.now - value).total_seconds()))

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except (TypeError, ValueError):
            return default
