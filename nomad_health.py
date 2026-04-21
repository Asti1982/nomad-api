import json
import os
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Any, Dict, Optional


class LaneCooldownManager:
    """Manages persistent infrastructure cooldowns for Nomad's 'Kernel'."""

    def __init__(self, state_path: Optional[Path] = None):
        # Default to the same state file Nomad uses for self-development
        self.state_path = state_path or Path(__file__).resolve().parent / "nomad_self_state.json"

    def is_on_cooldown(self, lane_id: str) -> bool:
        cooldowns = self._load_cooldowns()
        if lane_id not in cooldowns:
            return False
        
        blocked_until_str = cooldowns[lane_id].get("blocked_until")
        if not blocked_until_str:
            return False
            
        try:
            blocked_until = datetime.fromisoformat(blocked_until_str)
            if blocked_until > datetime.now(UTC):
                return True
        except (ValueError, TypeError):
            pass
            
        return False

    def get_cooldown_remaining(self, lane_id: str) -> int:
        cooldowns = self._load_cooldowns()
        if lane_id not in cooldowns:
            return 0
        try:
            blocked_until = datetime.fromisoformat(cooldowns[lane_id]["blocked_until"])
            remaining = int((blocked_until - datetime.now(UTC)).total_seconds())
            return max(0, remaining)
        except Exception:
            return 0

    def record_cooldown(self, lane_id: str, minutes: int = 60, reason: str = "rate_limited"):
        cooldowns = self._load_cooldowns()
        blocked_until = datetime.now(UTC) + timedelta(minutes=minutes)
        cooldowns[lane_id] = {
            "blocked_until": blocked_until.isoformat(),
            "reason": reason,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._save_cooldowns(cooldowns)

    def _load_cooldowns(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            return state.get("lane_cooldowns") or {}
        except Exception:
            return {}

    def _save_cooldowns(self, cooldowns: Dict[str, Any]):
        try:
            state = {}
            if self.state_path.exists():
                state = json.loads(self.state_path.read_text(encoding="utf-8"))
            state["lane_cooldowns"] = cooldowns
            self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            pass
