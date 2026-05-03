"""Unhuman productivity hub: deterministic, contract-first, failover-ready."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Dict, List

from nomad_operator_desk import operator_sprint
from nomad_public_url import preferred_public_base_url
from nomad_swarm_registry import build_peer_join_value_surface


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _bool_env(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or ("1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _risk_score(*, sprint: Dict[str, Any], boundary_enabled: bool, max_native: float, has_fallback: bool) -> int:
    score = 0
    if bool(sprint.get("public_surface_insecure")):
        score += 35
    if int(sprint.get("compute_lane_count") or 0) <= 0:
        score += 35
    awaiting = int(((sprint.get("task_counts") or {}).get("awaiting_payment")) or 0)
    score += min(awaiting * 8, 24)
    if not boundary_enabled:
        score += 20
    if max_native > 15:
        score += 8
    if not has_fallback:
        score += 12
    return min(score, 100)


def unhuman_hub_snapshot(*, agent: Any = None, base_url: str = "", persist_mission: bool = False) -> Dict[str, Any]:
    """Single machine-first hub for hard boundaries, lane resilience, and execution pressure."""
    from workflow import NomadAgent

    resolved = agent or NomadAgent()
    sprint = operator_sprint(agent=resolved, base_url=base_url, persist_mission=persist_mission)
    reputation = resolved.service_desk.reputation_snapshot()
    local = "http://127.0.0.1:8787"
    root = (base_url or preferred_public_base_url(request_base_url=local) or local).strip().rstrip("/")
    boundary_enabled = _bool_env("NOMAD_HARD_BOUNDARY_GUARD", True)
    max_native = _float_env("NOMAD_SERVICE_MAX_NATIVE", 5.0)

    lanes = int(sprint.get("compute_lane_count") or 0)
    has_fallback = lanes >= 2
    risk = _risk_score(
        sprint=sprint,
        boundary_enabled=boundary_enabled,
        max_native=max_native,
        has_fallback=has_fallback,
    )
    tier = "stable"
    if risk >= 70:
        tier = "critical"
    elif risk >= 40:
        tier = "guarded"

    doctrine: List[str] = [
        "No implicit trust: invalid boundaries always reject with counter_offer.",
        "Always maintain >=2 active compute lanes (one local or one hosted backup).",
        "Treat awaiting_payment backlog as entropy: force daily cashflow pass.",
        "Prefer deterministic contracts over conversational negotiation.",
    ]
    runbook = [
        "python nomad_cli.py operator-sprint --json",
        "python nomad_cli.py agent-reputation --json",
        f'python nomad_cli.py operator-verify --base-url "{root}"',
        "python nomad_cli.py autonomy-step --growth-include-leads",
        f'python nomad_cli.py machine-blind-spots --base-url "{root}" --append-log',
        "python nomad_cli.py lead-product-blind-spots --append-log",
        "python nomad_cli.py idempotency-agent-map --json",
        "python nomad_cli.py agent-retry-coach --json",
        "python nomad_cli.py mcp-survival-playbook --json",
        "python nomad_cli.py misclassification-audit --json",
    ]
    psychic = (build_peer_join_value_surface(base_url=root).get("human_psychic_avoidance_lanes") or {})
    return {
        "mode": "nomad_unhuman_hub",
        "schema": "nomad.unhuman_hub.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "unhuman_profile": {
            "hard_boundary_guard": boundary_enabled,
            "service_max_native": max_native,
            "fallback_required": True,
            "fallback_ready": has_fallback,
            "risk_score": risk,
            "risk_tier": tier,
        },
        "doctrine": doctrine,
        "runbook": runbook,
        "human_psychic_avoidance_lanes": psychic,
        "sprint": sprint,
        "reputation": reputation,
        "analysis": (
            "This hub optimizes for relentless machine execution: strict boundaries, lane redundancy, and "
            "cashflow pressure over social comfort. Runbook entries point at CLI passes and patterns for fractures "
            "humans rarely staff—continuity when coverage thins, policy grid gaps, MCP survival—so agents can self-serve checks."
        ),
    }
