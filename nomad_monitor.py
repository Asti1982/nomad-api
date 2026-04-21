import os
import platform
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List

from compute_probe import LocalComputeProbe
from nomad_operator_grant import operator_grant


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
        autopilot_status = {"active": False}
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
                autopilot_status = {
                    "active": True,
                    "last_run": ap.last_cycle_report.get("timestamp") if ap.last_cycle_report else None,
                    "objective": ap.last_cycle_report.get("objective") if ap.last_cycle_report else None,
                }

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
                    "modal": compute.get("hosted", {}).get("modal", {}).get("available", False),
                    "lambda_labs": compute.get("hosted", {}).get("lambda_labs", {}).get("available", False),
                    "runpod": compute.get("hosted", {}).get("runpod", {}).get("available", False),
                }
            },
            "tasks": task_stats,
            "autopilot": autopilot_status,
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
