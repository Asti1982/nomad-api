"""Modal-hosted Nomad transition worker (second swarm edge).

Credit-friendly pattern: a scheduled function runs a short multi-cycle burst
every few minutes instead of holding a 24h container.

Modal free credits (commonly ~USD 30/month on eligible workspaces) are usually
more than enough for this pattern: each wake is a few CPU-seconds on a small
Linux container. Rule of thumb at default cadence (3-minute schedule, two inner
cycles, ~40s HTTP timeout cap per cycle): on the order of **tens to low hundreds
of CPU-minutes per month**, i.e. **well under** a single-digit dollar burn at
typical CPU rates—leaving headroom for experimentation. **GPU colocated
inference is not assumed** here; for local LLM quality, point the worker at a
reachable Ollama base URL (for example a **Cloudflare Tunnel** or Tailscale
endpoint to your laptop) via Modal function env:

- ``NOMAD_TRANSITION_WORKER_OLLAMA_URL`` — e.g. ``https://ollama-tunnel.example.com``
- ``NOMAD_TRANSITION_WORKER_OLLAMA_URLS`` — comma-separated fallbacks

Prerequisites: https://modal.com account, ``pip install modal``, ``modal setup``.

Deploy from repository root::

    modal deploy modal/nomad_worker.py

Optional: set function env in the Modal dashboard (recommended over baking secrets):

- ``NOMAD_BASE_URL`` — default ``https://syndiode.com``
- ``NOMAD_TRANSITION_WORKER_ID`` — default ``transition-worker.modal-cloud.nomad``
- ``NOMAD_MACHINE_OBJECTIVE`` — default ``unhuman_supremacy``
- ``NOMAD_WORKER_INTERVAL`` — seconds between inner cycles (default ``10``)
- ``NOMAD_WORKER_TIMEOUT`` — HTTP/Ollama cycle timeout (default ``40``)
- ``NOMAD_TRANSITION_WORKER_NO_FLEET`` — set ``1`` to skip fleet lease calls

On-demand burst (local dev)::

    modal run modal/nomad_worker.py::manual_swarm_burst
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import modal

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_PATH = REPO_ROOT / "public" / "downloads" / "nomad_transition_worker.py"
if not WORKER_PATH.is_file():
    raise FileNotFoundError(f"Expected portable worker at {WORKER_PATH}")

image = modal.Image.debian_slim(python_version="3.11").add_local_file(
    str(WORKER_PATH),
    "/app/nomad_transition_worker.py",
    copy=True,
)

app = modal.App("nomad-swarm-edge-worker")


def _run_worker_cycles(*, cycles: int) -> None:
    spec = importlib.util.spec_from_file_location(
        "nomad_transition_worker_modal",
        "/app/nomad_transition_worker.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    base = (os.environ.get("NOMAD_BASE_URL") or "https://syndiode.com").strip()
    agent = (os.environ.get("NOMAD_TRANSITION_WORKER_ID") or "").strip() or "transition-worker.modal-cloud.nomad"
    interval = str(int(os.environ.get("NOMAD_WORKER_INTERVAL", "10") or "10"))
    timeout = str(float(os.environ.get("NOMAD_WORKER_TIMEOUT", "40") or "40"))
    objective = (os.environ.get("NOMAD_MACHINE_OBJECTIVE") or "unhuman_supremacy").strip()
    argv = [
        "nomad_transition_worker.py",
        "--base-url",
        base,
        "--agent-id",
        agent,
        "--machine-objective",
        objective,
        "--cycles",
        str(int(cycles)),
        "--interval",
        interval,
        "--timeout",
        timeout,
    ]
    if (os.environ.get("NOMAD_TRANSITION_WORKER_NO_FLEET") or "").strip().lower() in {"1", "true", "yes", "on"}:
        argv.append("--no-fleet")
    old = sys.argv
    try:
        sys.argv = argv
        mod.main()
    finally:
        sys.argv = old


@app.function(image=image, schedule=modal.Period(minutes=3), timeout=300)
def scheduled_swarm_tick() -> str:
    """Periodic edge worker: two cycles per wake (tune via Modal dashboard env)."""
    _run_worker_cycles(cycles=2)
    return "ok"


@app.function(image=image, timeout=420)
def manual_swarm_burst() -> str:
    """Single-shot burst for ``modal run`` smoke tests."""
    _run_worker_cycles(cycles=3)
    return "ok"
