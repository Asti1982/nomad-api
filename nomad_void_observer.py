"""Void observer: non-narrative edge coherence — complements CodexPeerAgent (growth/narrative).

Humans reason in stories; this pass only permutes (path, status) pairs into a stable hash and
compares to NOMAD_VOID_OBSERVER_BASELINE_SHA256 when set. Silent proxy or path-prefix drift shows up
as fingerprint drift even when every page still 'looks fine' in isolation.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from typing import Any, Dict, List
from urllib.parse import urlparse

from nomad_swarm_helper_agent import run_swarm_helper_pass


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_probe_lines(probes: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for p in probes:
        if not isinstance(p, dict):
            continue
        url = str(p.get("url") or "")
        parsed = urlparse(url)
        path = parsed.path or "/"
        status = int(p.get("status") or 0)
        ok = bool(p.get("ok"))
        lines.append(f"{status}\t{int(ok)}\t{path}")
    lines.sort()
    return lines


def _fingerprint(lines: List[str]) -> str:
    blob = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def void_metrics_from_probes(
    probes: List[Dict[str, Any]],
    *,
    probe_ok_count: int | None = None,
) -> Dict[str, Any]:
    """Fingerprint and drift metrics from an existing swarm-helper probe list (no extra HTTP)."""
    plist = probes if isinstance(probes, list) else []
    lines = _canonical_probe_lines(plist)
    fp = _fingerprint(lines)
    baseline = (os.getenv("NOMAD_VOID_OBSERVER_BASELINE_SHA256") or "").strip().lower()
    drift = bool(baseline and fp != baseline)
    statuses = [int(p.get("status") or 0) for p in plist if isinstance(p, dict)]
    spread = len(set(statuses)) if statuses else 0
    vacuum_stability = round(1.0 - min(max(spread - 1, 0), 8) / 8.0, 4)
    ordinal_series = statuses[:32]
    ok_count = probe_ok_count if probe_ok_count is not None else sum(1 for p in plist if isinstance(p, dict) and p.get("ok"))
    return {
        "edge_coherence_sha256": fp,
        "baseline_sha256_configured": bool(baseline),
        "baseline_drift": drift,
        "vacuum_stability": vacuum_stability,
        "ordinal_status_series": ordinal_series,
        "probe_ok_count": int(ok_count),
    }


def run_void_observer_pulse(
    *,
    base_url: str = "",
    timeout: float = 25.0,
    agent_id: str = "",
) -> Dict[str, Any]:
    """
    GET-only: reuses swarm-helper probes, then discards bodies for the void signature.
    """
    swarm = run_swarm_helper_pass(
        base_url=base_url,
        dry_run=True,
        post_join=False,
        post_develop=False,
        timeout=timeout,
        agent_id=agent_id,
    )
    probes = swarm.get("probes") or []
    metrics = void_metrics_from_probes(
        probes if isinstance(probes, list) else [],
        probe_ok_count=int(swarm.get("probe_ok_count") or 0),
    )

    return {
        "mode": "nomad_void_observer_pulse",
        "schema": "nomad.void_observer_pulse.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "public_base_url": swarm.get("public_base_url", ""),
        **metrics,
        "swarm_helper_schema": swarm.get("schema", ""),
        "analysis": (
            "Void observer: permutation-invariant (path,status,ok) fingerprint over the same GET lattice "
            "as swarm-helper. CodexPeerAgent handles growth and A2A; this detects silent routing or "
            "prefix drift without reading JSON semantics."
        ),
    }
