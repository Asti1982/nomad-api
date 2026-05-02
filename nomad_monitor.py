import json
import os
import platform
import time
import ctypes
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict

from compute_probe import LocalComputeProbe
from nomad_collaboration import collaboration_charter
from nomad_operator_grant import operator_grant
from nomad_outbound_tracker import NomadOutboundTracker
from nomad_public_url import preferred_public_base_url


ROOT = Path(__file__).resolve().parent
AUTOPILOT_STATE = ROOT / "nomad_autopilot_state.json"
AUTO_CYCLE_PID = ROOT / "tools" / "nomad-live" / "auto-cycle.pid"
AUTO_CYCLE_STATUS = ROOT / "tools" / "nomad-live" / "auto-cycle-status.json"
MUTUAL_AID_STATE = ROOT / "nomad_mutual_aid_state.json"
AUTONOMOUS_DEVELOPMENT_STATE = ROOT / "nomad_autonomous_development.json"


class NomadSystemMonitor:
    """System monitor for Nomad: 'The Linux for AI Agents'."""

    def __init__(self, agent=None):
        self.agent = agent
        self.probe = LocalComputeProbe()
        self.start_time = time.time()
        self.outbound_tracker = getattr(agent, "outbound_tracker", None) or NomadOutboundTracker()

    def snapshot(self) -> Dict[str, Any]:
        compute = self.probe.snapshot()
        uptime_seconds = int(time.time() - self.start_time)
        
        # Gather task stats if agent is available
        task_stats = {}
        autopilot_status = self._autopilot_runtime_status()
        outbound_status = self._outbound_status()
        if self.agent and hasattr(self.agent, 'service_desk'):
            tasks = self.agent.service_desk.list_tasks(limit=1000).get("tasks") or []
            task_stats = {
                "total": len(tasks),
                "paid": len([t for t in tasks if t.get("status") == "paid"]),
                "awaiting_payment": len([t for t in tasks if t.get("status") == "awaiting_payment"]),
                "draft_ready": len([t for t in tasks if t.get("status") == "draft_ready"]),
                "delivered": len([t for t in tasks if t.get("status") == "delivered"]),
                "completed": len([t for t in tasks if t.get("status") in {"completed", "delivered"}]),
            }
            
            # Check for autopilot (Autopilot usually wraps the agent or is accessible)
            # In Nomad, Autopilot is often a separate loop but we can try to find it
            # if we have a reference to it.
            if hasattr(self.agent, 'autopilot') and self.agent.autopilot:
                ap = self.agent.autopilot
                autopilot_status.update({
                    "active": True,
                    "last_run": ap.last_cycle_report.get("timestamp") if ap.last_cycle_report else None,
                    "objective": ap.last_cycle_report.get("objective") if ap.last_cycle_report else None,
                    "source": "in_process",
                })

        return {
            "mode": "nomad_system_status",
            "timestamp": datetime.now(UTC).isoformat(),
            "uptime": self._format_uptime(uptime_seconds),
            "uptime_seconds": uptime_seconds,
            "os": {
                "platform": platform.platform(),
                "node": platform.node(),
                "release": platform.release(),
                "processor": platform.processor(),
            },
            "resources": {
                "cpu_count": os.cpu_count() or 0,
                "memory_gb": compute.get("memory_gb", 0),
                "gpu": compute.get("gpu", {}),
            },
            "compute_lanes": {
                "local": {
                    "ollama": compute.get("ollama", {}).get("available", False),
                    "llama_cpp": compute.get("llama_cpp", {}).get("available", False),
                },
                "hosted": {
                    "github_models": compute.get("hosted", {}).get("github_models", {}).get("available", False),
                    "huggingface": compute.get("hosted", {}).get("huggingface", {}).get("available", False),
                    "cloudflare": compute.get("hosted", {}).get("cloudflare_workers_ai", {}).get("available", False),
                    "xai_grok": compute.get("hosted", {}).get("xai_grok", {}).get("available", False),
                    "openrouter": compute.get("hosted", {}).get("openrouter", {}).get("available", False),
                    "modal": {
                        "available": compute.get("hosted", {}).get("modal", {}).get("available", False),
                        "sdk": compute.get("hosted", {}).get("modal", {}).get("sdk_available", False),
                        "cli": compute.get("hosted", {}).get("modal", {}).get("cli_available", False),
                    },
                    "lambda_labs": compute.get("hosted", {}).get("lambda_labs", {}).get("available", False),
                    "runpod": compute.get("hosted", {}).get("runpod", {}).get("available", False),
                }
            },
            "tasks": task_stats,
            "outbound": outbound_status,
            "autopilot": autopilot_status,
            "autonomous_development": self._autonomous_development_status(),
            "mutual_aid": self._mutual_aid_status(),
            "roaas": self._roaas_status(),
            "public_surface": self._public_surface_status(),
            "operator": {
                "grant": operator_grant(),
            },
            "analysis": self._generate_analysis(compute, task_stats, autopilot_status, outbound_status),
        }

    def _format_uptime(self, seconds: int) -> str:
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        parts = []
        if days > 0: parts.append(f"{days}d")
        if hours > 0: parts.append(f"{hours}h")
        if minutes > 0: parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        return " ".join(parts)

    def _generate_analysis(
        self,
        compute: Dict[str, Any],
        task_stats: Dict[str, Any],
        autopilot_status: Dict[str, Any],
        outbound_status: Dict[str, Any],
    ) -> str:
        ollama_active = compute.get("ollama", {}).get("available")
        active_hosted = [
            name for name, p in compute.get("hosted", {}).items()
            if isinstance(p, dict) and p.get("available")
        ]
        
        status = "Nomad system is healthy."
        if not ollama_active and not active_hosted:
            status = "Nomad is compute-starved: no local or hosted brains available."
        elif not ollama_active:
            status = "Nomad is running on hosted-only compute; local Ollama is recommended for privacy."
            
        if task_stats.get("paid", 0) > 0:
            status += f" {task_stats['paid']} paid task(s) awaiting processing."

        followup_ready = int(((outbound_status.get("contacts") or {}).get("followup_ready")) or 0)
        if followup_ready > 0:
            status += f" {followup_ready} outbound follow-up(s) are ready."

        if not autopilot_status.get("active"):
            status += " Autopilot is currently inactive."
            
        return status

    def _outbound_status(self) -> Dict[str, Any]:
        try:
            summary = self.outbound_tracker.summary(limit=5)
        except Exception:
            return {"ok": False, "contacts": {"total": 0}, "campaigns": {"total": 0}, "tasks": {"total": 0}}
        return {
            "ok": bool(summary.get("ok")),
            "next_best_action": summary.get("next_best_action", ""),
            "contacts": {
                "total": int(((summary.get("contacts") or {}).get("total")) or 0),
                "awaiting_reply": int(((summary.get("contacts") or {}).get("awaiting_reply")) or 0),
                "followup_ready": int(((summary.get("contacts") or {}).get("followup_ready")) or 0),
            },
            "campaigns": {
                "total": int(((summary.get("campaigns") or {}).get("total")) or 0),
            },
            "tasks": {
                "awaiting_payment": len(((summary.get("tasks") or {}).get("awaiting_payment")) or []),
                "paid_ready": len(((summary.get("tasks") or {}).get("paid_ready")) or []),
            },
            "autonomous_tracking": {
                "payment_followup_log_count": int(((summary.get("autonomous_tracking") or {}).get("payment_followup_log_count")) or 0),
                "agent_followup_log_count": int(((summary.get("autonomous_tracking") or {}).get("agent_followup_log_count")) or 0),
                "converted_reply_count": int(((summary.get("autonomous_tracking") or {}).get("converted_reply_count")) or 0),
            },
        }

    def _autopilot_runtime_status(self) -> Dict[str, Any]:
        state = self._read_json(AUTOPILOT_STATE)
        runtime = self._read_json(AUTO_CYCLE_STATUS)
        pid = self._read_pid(AUTO_CYCLE_PID) or int(runtime.get("pid") or 0)
        last_decision = state.get("last_decision") or {}
        return {
            "active": self._pid_is_running(pid) if pid else False,
            "pid": pid or None,
            "source": "auto_cycle_pid_file" if pid else "state_file",
            "started_at": runtime.get("started_at", ""),
            "last_run": state.get("last_run_at", ""),
            "last_idle": state.get("last_idle_at", ""),
            "objective": state.get("last_objective", ""),
            "next_check_at": state.get("next_decision_at", ""),
            "last_decision": {
                "should_start": bool(last_decision.get("should_start", False)),
                "reason": last_decision.get("reason", ""),
                "next_check_seconds": last_decision.get("next_check_seconds", 0),
            },
        }

    def _mutual_aid_status(self) -> Dict[str, Any]:
        state = self._read_json(MUTUAL_AID_STATE)
        modules = state.get("modules") or []
        ledger = state.get("truth_density_ledger") or []
        inbox = state.get("swarm_inbox") or []
        packs = state.get("paid_packs") or {}
        patterns = [
            entry
            for entry in ledger
            if (entry.get("outcome") or {}).get("success")
        ]
        patterns.sort(
            key=lambda entry: (
                -float(((entry.get("reuse_value") or {}).get("score")) or 0.0),
                -int(((entry.get("reuse_value") or {}).get("repeat_count")) or 0),
                -float(entry.get("truth_score") or 0.0),
            )
        )
        top_pattern = patterns[0] if patterns else {}
        top_high_value_patterns = []
        grouped: dict[str, list[dict]] = {}
        for entry in patterns:
            title = str(entry.get("solution_title") or entry.get("task") or entry.get("pain_type") or "").strip()
            key = f"{entry.get('pain_type', '')}:{title.lower()}"
            grouped.setdefault(key, []).append(entry)
        for entries in grouped.values():
            if len(entries) < 2:
                continue
            top_high_value_patterns.append(
                {
                    "title": entries[-1].get("solution_title") or entries[-1].get("task") or "",
                    "pain_type": entries[-1].get("pain_type", ""),
                    "occurrence_count": len(entries),
                    "avg_truth_score": round(
                        sum(float(item.get("truth_score") or 0.0) for item in entries) / len(entries),
                        4,
                    ),
                    "avg_reuse_value": round(
                        sum(float((item.get("reuse_value") or {}).get("score") or 0.0) for item in entries) / len(entries),
                        4,
                    ),
                }
            )
        top_high_value_patterns.sort(
            key=lambda item: (
                -int(item.get("occurrence_count") or 0),
                -float(item.get("avg_reuse_value") or 0.0),
                -float(item.get("avg_truth_score") or 0.0),
            )
        )
        return {
            "schema": "nomad.mutual_aid_status.compact.v1",
            "mutual_aid_score": int(state.get("mutual_aid_score") or 0),
            "swarm_assist_score": int(state.get("swarm_assist_score") or 0),
            "truth_density_total": round(float(state.get("truth_density_total") or 0.0), 4),
            "helped_agent_count": len(state.get("helped_agents") or {}),
            "module_count": len(modules),
            "truth_ledger_count": len(ledger),
            "swarm_inbox_count": len(inbox),
            "paid_pack_count": len(packs),
            "latest_module": (modules[-1] if modules else {}).get("module_id", ""),
            "top_truth_pattern": {
                "title": top_pattern.get("solution_title") or top_pattern.get("task") or "",
                "pain_type": top_pattern.get("pain_type", ""),
                "repeat_count": int(((top_pattern.get("reuse_value") or {}).get("repeat_count")) or 0),
                "truth_score": float(top_pattern.get("truth_score") or 0.0),
            } if top_pattern else {},
            "top_high_value_patterns": top_high_value_patterns[:3],
        }

    def _autonomous_development_status(self) -> Dict[str, Any]:
        state = self._read_json(AUTONOMOUS_DEVELOPMENT_STATE)
        actions = state.get("actions") or []
        latest = actions[-1] if actions else {}
        return {
            "schema": "nomad.autonomous_development_status.compact.v1",
            "action_count": len(actions),
            "updated_at": state.get("updated_at", ""),
            "latest_action_id": latest.get("action_id", ""),
            "latest_title": latest.get("title", ""),
        }

    def _public_surface_status(self) -> Dict[str, Any]:
        public_url = preferred_public_base_url(request_base_url="http://127.0.0.1:8787")
        charter = collaboration_charter(public_api_url=public_url)
        return {
            "public_api_url": public_url,
            "agent_card": f"{public_url}/.well-known/agent-card.json" if public_url else "",
            "agent_attractor": f"{public_url}/agent-attractor" if public_url else "",
            "service": f"{public_url}/service" if public_url else "",
            "collaboration_enabled": bool(charter.get("enabled")),
            "public_home": charter.get("public_home", ""),
            "publish_agent_presence": bool((charter.get("permission") or {}).get("publish_agent_presence")),
        }

    def _roaas_status(self) -> Dict[str, Any]:
        if not self.agent or not hasattr(self.agent, "self_improvement"):
            return {"enabled": False}
        brain_router = getattr(self.agent.self_improvement, "brain_router", None)
        if brain_router is None or not hasattr(brain_router, "predictive_status"):
            return {"enabled": False}
        try:
            status = brain_router.predictive_status(task_type="self_improvement_review")
            if not isinstance(status, dict):
                return {"enabled": False}
            status["enabled"] = bool(status.get("enabled", True))
            return status
        except Exception as exc:
            return {
                "enabled": False,
                "error": str(exc),
            }

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _read_pid(path: Path) -> int:
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except Exception:
            return 0

    @staticmethod
    def _pid_is_running(pid: int) -> bool:
        if not pid:
            return False
        if os.name == "nt":
            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                process_query_limited_information,
                False,
                int(pid),
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
