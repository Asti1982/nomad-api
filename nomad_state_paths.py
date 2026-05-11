"""Shared state-path helpers for JSONL market/proof ledgers."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def configured_state_dir() -> str:
    return str(os.getenv("NOMAD_STATE_DIR") or os.getenv("NOMAD_MARKET_STATE_DIR") or "").strip()


def fallback_state_dir() -> Path:
    explicit = str(os.getenv("NOMAD_STATE_FALLBACK_DIR") or "").strip()
    if explicit:
        return Path(explicit)
    return Path(tempfile.gettempdir()) / "nomad-state"


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".nomad_state_probe"
        probe.write_text(datetime.now(UTC).isoformat(), encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def state_root() -> Path:
    configured = configured_state_dir()
    if configured:
        candidate = Path(configured)
        if _is_writable_dir(candidate):
            return candidate
        fallback = fallback_state_dir()
        if _is_writable_dir(fallback):
            return fallback
        return candidate
    return Path.cwd()


def state_file(default_path: Path | str, *, env_name: str = "") -> Path:
    explicit = str(os.getenv(env_name) or "").strip() if env_name else ""
    if explicit:
        p = Path(explicit)
        if p.is_absolute() or p.parent != Path("."):
            return p
        return state_root() / p.name
    default = Path(default_path)
    configured = configured_state_dir()
    if configured:
        return state_root() / default.name
    return default
