"""Retry / backoff coach from append-only edge + lead JSONL — humans rarely tune from telemetry.

Reads last N lines of edge_coherence.jsonl and lead_coherence.jsonl (if present), derives
conservative delay and jitter recommendations so agents avoid retry storms after gateway/HTML facade stress.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
DEFAULT_EDGE_LOG = ROOT / "nomad_autonomous_artifacts" / "edge_coherence.jsonl"
DEFAULT_LEAD_LOG = ROOT / "nomad_autonomous_artifacts" / "lead_coherence.jsonl"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _tail_jsonl(path: Path, *, max_lines: int) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    tail = lines[-max(1, min(max_lines, 500)) :]
    out: List[Dict[str, Any]] = []
    for ln in tail:
        try:
            row = json.loads(ln)
            if isinstance(row, dict):
                out.append(row)
        except json.JSONDecodeError:
            continue
    return out


def run_agent_retry_coach(
    *,
    edge_log_path: str = "",
    lead_log_path: str = "",
    tail_lines: int = 0,
) -> Dict[str, Any]:
    edge_p = Path((edge_log_path or os.getenv("NOMAD_EDGE_COHERENCE_LOG") or str(DEFAULT_EDGE_LOG)).strip())
    lead_p = Path((lead_log_path or os.getenv("NOMAD_LEAD_COHERENCE_LOG") or str(DEFAULT_LEAD_LOG)).strip())

    if int(tail_lines or 0) > 0:
        cap = max(1, min(int(tail_lines), 500))
    else:
        try:
            cap = int(os.getenv("NOMAD_AGENT_RETRY_COACH_TAIL") or "96")
        except (TypeError, ValueError):
            cap = 96
        cap = max(1, min(cap, 500))

    edge_rows = _tail_jsonl(edge_p, max_lines=cap)
    lead_rows = _tail_jsonl(lead_p, max_lines=cap)

    n_edge = len(edge_rows)
    n_lead = len(lead_rows)

    avg_gateway = 0.0
    avg_facade = 0.0
    div_frac = 0.0
    if edge_rows:
        gw = [float(r.get("gateway_hits") or 0) for r in edge_rows]
        fc = [float(r.get("facade_count") or 0) for r in edge_rows]
        dv = [1.0 if r.get("readiness_divergence") else 0.0 for r in edge_rows]
        avg_gateway = round(sum(gw) / len(gw), 4)
        avg_facade = round(sum(fc) / len(fc), 4)
        div_frac = round(sum(dv) / len(dv), 4)

    avg_desert = 0.0
    if lead_rows:
        ds = [float(r.get("execution_desert") or 0) for r in lead_rows]
        avg_desert = round(sum(ds) / len(ds), 4)

    # Agent-centric backoff: invisible to human KPIs, bounded.
    base_delay = round(1.5 + 3.0 * avg_gateway + 5.0 * avg_facade + 4.0 * div_frac + 2.0 * avg_desert, 2)
    base_delay = min(max(base_delay, 1.2), 120.0)
    jitter_ratio = round(0.18 + 0.12 * min(1.0, avg_gateway + avg_facade), 3)
    jitter_ratio = min(max(jitter_ratio, 0.12), 0.42)
    max_retries = 4 if (avg_gateway + avg_facade) > 1.5 else 7
    if div_frac > 0.35:
        max_retries = min(max_retries, 4)

    notes: List[str] = []
    if n_edge < 3:
        notes.append("sparse_edge_log: run machine-blind-spots --append-log on a schedule before trusting delays.")
    if n_lead < 3:
        notes.append("sparse_lead_log: run lead-product-blind-spots --append-log to correlate pipeline friction.")
    if avg_facade > 0.2:
        notes.append("html_facade_stress: prefer void fingerprint diff over raw status codes before retrying writes.")
    if div_frac > 0.25:
        notes.append("readiness_divergence_trend: split health checks from swarm/ready probes in separate timers.")
    if not notes:
        notes.append("telemetry_ok_for_coarse_tuning: still rotate idempotency keys on logical operation boundaries.")

    return {
        "mode": "nomad_agent_retry_coach",
        "schema": "nomad.agent_retry_coach.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "sources": {"edge_log": str(edge_p), "lead_log": str(lead_p)},
        "samples": {"edge_lines_used": n_edge, "lead_lines_used": n_lead, "tail_cap": cap},
        "observed_stress": {
            "avg_gateway_hits": avg_gateway,
            "avg_facade_count": avg_facade,
            "readiness_divergence_fraction": div_frac,
            "avg_execution_desert": avg_desert,
        },
        "recommendation": {
            "base_delay_seconds": base_delay,
            "jitter_ratio": jitter_ratio,
            "max_retries_per_operation": max_retries,
            "respect_retry_after": True,
            "idempotent_post_paths": ["/swarm/join", "/swarm/develop"],
            "non_idempotent_post_paths_avoid_exponential": [
                "/agent-contacts",
                "/agent-contacts/send",
                "/tasks/work",
                "/aid",
            ],
        },
        "coach_notes": notes,
        "analysis": (
            "Machine-only backoff hints from JSONL tails; humans rarely plot gateway+facade+divergence+desert together. "
            "Agents should combine this with nomad_idempotency_agent_map for branch-vs-retry decisions."
        ),
    }
