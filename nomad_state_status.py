"""Durable state status for Nomad market/proof ledgers."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import configured_state_dir, fallback_state_dir, state_root


STATE_FILES = [
    "nomad_swarm_registry.json",
    "nomad_work_exchange_ledger.jsonl",
    "nomad_worker_market_ledger.jsonl",
    "nomad_microtask_ledger.jsonl",
    "nomad_microtask_settlement_ledger.jsonl",
    "nomad_growth_arena_ledger.jsonl",
    "nomad_agent_work_claims.jsonl",
    "nomad_agent_work_proofs.jsonl",
]


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _line_count(path: Path) -> int:
    if not path.exists() or not path.is_file():
        return 0
    try:
        return sum(1 for _ in path.open("r", encoding="utf-8"))
    except OSError:
        return 0


def _probe_writable(path: Path) -> tuple[bool, str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".nomad_state_probe"
        probe.write_text(_iso_now(), encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, ""
    except OSError as exc:
        return False, str(exc)[:180]


def _read_int_file(path: str) -> int | None:
    try:
        raw = Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not raw or raw == "max":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _process_memory_status() -> dict[str, Any]:
    rss_kb: int | None = None
    peak_kb: int | None = None
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("VmRSS:"):
                rss_kb = int(line.split()[1])
            elif line.startswith("VmHWM:"):
                peak_kb = int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    cgroup_bytes = (
        _read_int_file("/sys/fs/cgroup/memory.max")
        or _read_int_file("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    )
    limit_mb = round(cgroup_bytes / (1024 * 1024), 3) if cgroup_bytes else None
    rss_mb = round((rss_kb or 0) / 1024, 3) if rss_kb is not None else None
    peak_mb = round((peak_kb or 0) / 1024, 3) if peak_kb is not None else None
    ratio = round(float(rss_mb) / float(limit_mb), 4) if rss_mb is not None and limit_mb else None
    state = "unknown"
    if ratio is not None:
        state = "critical" if ratio >= 0.9 else "warning" if ratio >= 0.75 else "ok"
    elif rss_mb is not None:
        state = "observed_no_limit"
    return {
        "schema": "nomad.process_memory_status.v1",
        "rss_mb": rss_mb,
        "peak_rss_mb": peak_mb,
        "cgroup_limit_mb": limit_mb,
        "rss_limit_ratio": ratio,
        "state": state,
    }


def build_state_status(*, base_url: str = "") -> dict[str, Any]:
    configured = configured_state_dir()
    preferred = Path(configured) if configured else Path.cwd()
    preferred_writable, preferred_error = _probe_writable(preferred)
    effective_root = state_root()
    writable, error = _probe_writable(effective_root)
    files: list[dict[str, Any]] = []
    for name in STATE_FILES:
        path = effective_root / name
        files.append(
            {
                "name": name,
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() and path.is_file() else 0,
                "line_count": _line_count(path),
            }
        )
    render_runtime = (os.getenv("RENDER") or "").strip().lower() == "true"
    disk_configured = bool(configured)
    durability = "configured_writable" if disk_configured and writable else "ephemeral_default"
    render_disk_path = str(effective_root).startswith(("/var/data", "/opt/render/project/src/storage", "/app/storage"))
    firestore_backend = str(os.getenv("NOMAD_STATE_BACKEND") or os.getenv("NOMAD_SWARM_REGISTRY_BACKEND") or "").strip().lower()
    remote_state_configured = firestore_backend in {"firebase", "firestore"}
    if render_runtime and disk_configured and render_disk_path and writable:
        durability = "render_disk_path_configured_writable"
    if render_runtime and configured and not str(effective_root).startswith(("/var/data", "/opt/render/project/src/storage", "/app/storage")):
        durability = "render_path_may_not_be_disk"
    if configured and not preferred_writable and writable:
        durability = "fallback_writable_configured_path_unwritable"
    if not writable:
        durability = "not_writable"
    retention_blockers: list[str] = []
    if render_runtime and durability in {"render_path_may_not_be_disk", "ephemeral_default"} and not remote_state_configured:
        retention_blockers.append("render_state_ephemeral_attach_disk_or_enable_firestore")
    if render_runtime and configured and str(effective_root).startswith(("/tmp", "\\tmp")):
        retention_blockers.append("nomad_state_dir_points_to_tmp")
    memory_status = _process_memory_status()
    if render_runtime and memory_status.get("state") in {"warning", "critical"}:
        retention_blockers.append("render_memory_pressure_reduce_crawler_surface_or_scale_instance")
    return {
        "ok": writable,
        "schema": "nomad.state_status.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "state_dir_configured": disk_configured,
        "state_dir": str(effective_root),
        "configured_state_dir": configured,
        "configured_state_dir_writable": preferred_writable,
        "configured_state_dir_error": preferred_error,
        "fallback_state_dir": str(fallback_state_dir()),
        "using_fallback": bool(configured and str(effective_root) != str(preferred)),
        "render_runtime": render_runtime,
        "durability": durability,
        "writable": writable,
        "render_disk_attachment_required": bool(render_runtime and disk_configured),
        "render_disk_attachment_confirmed": False,
        "render_disk_attachment_note": "filesystem_probe_can_verify_writable_path_not_render_disk_attachment",
        "remote_state_backend_configured": remote_state_configured,
        "retention_blockers": retention_blockers,
        "process_memory": memory_status,
        "write_error": error,
        "state_files": files,
        "recommended_render_mount_path": "/var/data/nomad",
        "recommended_env": {
            "NOMAD_STATE_DIR": "/var/data/nomad",
        },
        "links": {
            "self": _u(base_url, "/swarm/state-status"),
            "well_known": _u(base_url, "/.well-known/nomad-state-status.json"),
            "agent_work": _u(base_url, "/.well-known/nomad-agent-work.json"),
            "work_mesh": _u(base_url, "/.well-known/nomad-work-mesh.json"),
        },
        "machine_instruction": "if_state_dir_configured_false_attach_persistent_disk_then_set_nomad_state_dir",
    }
