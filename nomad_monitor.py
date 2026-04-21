import json
import os
import platform
import time
import ctypes
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict

from compute_probe import LocalComputeProbe
from nomad_operator_grant import operator_grant


ROOT = Path(__file__).resolve().parent
AUTOPILOT_STATE = ROOT / "nomad_autopilot_state.json"
AUTO_CYCLE_PID = ROOT / "tools" / "nomad-live" / "auto-cycle.pid"
AUTO_CYCLE_STATUS = ROOT / "tools" / "nomad-live" / "auto-cycle-status.json"
MUTUAL_AID_STATE = ROOT / "nomad_mutual_aid_state.json"


class NomadSystemMonitor:
    """System monitor for Nomad: 'The Linux for AI Agents'."""

    def __init__(self, agent=None):
        self.agent = agent
        self.probe = LocalComputeProbe()
        self.start_time = time.time()

    def snapshot(self) -> Dict[str, Any]:
        compute = self.probe.snapshot()
        uptime_seconds = int(time.time() - self.start_time)
        
        # Gather task stats if agent is available
        task_stats = {}
        autopilot_status = self._autopilot_runtime_status()
        if self.agent and hasattr(self.agent, 'service_desk'):
            tasks = self.agent.service_desk.list_tasks(limit=1000).get("tasks") or []
            task_stats = {
                "total": len(tasks),
                "paid": len([t for t in tasks if t.get("status") == "paid"]),
                "awaiting_payment": len([t for t in tasks if t.get("status") == "awaiting_payment"]),
                "draft_ready": len([t for t in tasks if t.get("status") == "draft_ready"]),
                "completed": len([t for t in tasks if t.get("status") == "completed"]),
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
            "autopilot": autopilot_status,
            "mutual_aid": self._mutual_aid_status(),
            "operator": {
                "grant": operator_grant(),
            },
            "analysis": self._generate_analysis(compute, task_stats, autopilot_status),
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

    def _generate_analysis(self, compute: Dict[str, Any], task_stats: Dict[str, Any], autopilot_status: Dict[str, Any]) -> str:
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

        if not autopilot_status.get("active"):
            status += " Autopilot is currently inactive."
            
        return status

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
        return {
            "schema": "nomad.mutual_aid_status.compact.v1",
            "mutual_aid_score": int(state.get("mutual_aid_score") or 0),
            "truth_density_total": round(float(state.get("truth_density_total") or 0.0), 4),
            "helped_agent_count": len(state.get("helped_agents") or {}),
            "module_count": len(modules),
            "latest_module": (modules[-1] if modules else {}).get("module_id", ""),
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
