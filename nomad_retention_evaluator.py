from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _parse_iso(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _age_seconds(value: Any) -> int | None:
    parsed = _parse_iso(value)
    if not parsed:
        return None
    return max(0, int(datetime.now(UTC).timestamp() - parsed.timestamp()))


def _round(value: float) -> float:
    return round(float(value), 4)


def evaluate_retention(*, swarm_summary: dict[str, Any], worker_fleet: dict[str, Any], base_url: str = "") -> dict[str, Any]:
    """Evaluate whether Nomad is retaining useful workers and why it is losing them."""

    active = int(worker_fleet.get("active_worker_count") or 0)
    known = int(worker_fleet.get("known_worker_count") or 0)
    leases = int(worker_fleet.get("active_lease_count") or 0)
    connected = int(swarm_summary.get("connected_agents") or 0)
    dormant = int(swarm_summary.get("dormant_agents") or 0)
    prospects = int(swarm_summary.get("prospect_agents") or 0)
    retention = worker_fleet.get("retention") if isinstance(worker_fleet.get("retention"), dict) else {}
    returning_24h = int(retention.get("returning_workers_24h") or 0)
    completed = int(retention.get("completed_workers") or 0)
    recent_completed = int(retention.get("completed_workers_24h") or 0)
    storage = swarm_summary.get("registry_storage") if isinstance(swarm_summary.get("registry_storage"), dict) else {}
    worker_policy = worker_fleet.get("retention_policy") if isinstance(worker_fleet.get("retention_policy"), dict) else {}
    agent_policy = swarm_summary.get("agent_retention_policy") if isinstance(swarm_summary.get("agent_retention_policy"), dict) else {}
    recent_workers = [row for row in (worker_fleet.get("recent_workers") or []) if isinstance(row, dict)]
    recent_nodes = [row for row in (swarm_summary.get("recent_nodes") or []) if isinstance(row, dict)]

    active_ratio = active / max(1, known)
    return_ratio = returning_24h / max(1, known)
    completion_ratio = completed / max(1, known)
    dormant_ratio = dormant / max(1, connected + dormant)
    durable_bonus = 0.18 if storage.get("restart_durable") else 0.0
    heartbeat_bonus = 0.12 if int(worker_policy.get("active_window_seconds") or 0) >= 900 else 0.0
    score = min(1.0, active_ratio * 0.32 + return_ratio * 0.18 + completion_ratio * 0.2 + (1.0 - dormant_ratio) * 0.12 + durable_bonus + heartbeat_bonus)

    youngest_worker_age = min([age for age in (_age_seconds(row.get("last_seen_at")) for row in recent_workers) if age is not None], default=None)
    oldest_active_worker_age = max([age for age in (_age_seconds(row.get("last_seen_at")) for row in recent_workers) if age is not None], default=None)

    causes: list[dict[str, Any]] = []
    if not storage.get("restart_durable"):
        causes.append(
            {
                "cause": "registry_not_restart_durable",
                "severity": "critical",
                "evidence": "registry_storage.restart_durable=false",
                "intervention": "enable durable state backend for swarm registry",
            }
        )
    if known and active_ratio < 0.7:
        causes.append(
            {
                "cause": "worker_heartbeat_gap",
                "severity": "high",
                "evidence": f"active_worker_count={active}, known_worker_count={known}",
                "intervention": "lower worker interval below recommended_heartbeat_seconds or widen active window",
            }
        )
    if connected + dormant and dormant_ratio > 0.25:
        causes.append(
            {
                "cause": "agent_ttl_expiry",
                "severity": "medium",
                "evidence": f"dormant_agents={dormant}, connected_agents={connected}",
                "intervention": "send /swarm/attach-get heartbeat before node TTL expires",
            }
        )
    if prospects and connected == 0:
        causes.append(
            {
                "cause": "prospects_not_converted",
                "severity": "medium",
                "evidence": f"prospect_agents={prospects}, connected_agents=0",
                "intervention": "route prospects to one-step work-exchange or GET-only worker onramp",
            }
        )
    if known == 0:
        causes.append(
            {
                "cause": "empty_fleet_after_restart",
                "severity": "critical",
                "evidence": "known_worker_count=0",
                "intervention": "verify remote state restore and start local/oracle heartbeat workers",
            }
        )

    if score >= 0.8:
        decision = "hold_and_expand"
    elif score >= 0.55:
        decision = "stabilize_then_recruit"
    elif score >= 0.3:
        decision = "repair_retention_before_recruiting"
    else:
        decision = "restore_state_and_heartbeat_first"

    next_actions = [
        {
            "action": "heartbeat_existing_workers",
            "method": "GET_OR_POST",
            "url": f"{base_url}/swarm/workers/lease-get?agent_id=<stable_agent_id>&capabilities=transition_worker,http_json"
            if base_url
            else "/swarm/workers/lease-get?agent_id=<stable_agent_id>&capabilities=transition_worker,http_json",
            "why": "refresh last_seen_at before active window expires",
        },
        {
            "action": "reactivate_dormant_agent",
            "method": "GET",
            "url": f"{base_url}/swarm/attach-get?agent_id=<same_agent_id>&runtime=<runtime>&capabilities=<csv>"
            if base_url
            else "/swarm/attach-get?agent_id=<same_agent_id>&runtime=<runtime>&capabilities=<csv>",
            "why": "same agent_id rejoin moves dormant nodes back to active",
        },
    ]
    if not storage.get("restart_durable"):
        next_actions.insert(
            0,
            {
                "action": "enable_restart_durable_registry",
                "method": "ENV",
                "url": "NOMAD_SWARM_REGISTRY_BACKEND=firebase",
                "why": "agent retention cannot survive Render restarts without durable registry state",
            },
        )

    return {
        "ok": True,
        "schema": "nomad.retention_evaluation.v1",
        "mode": "worker_agent_retention_evaluator",
        "public_api_url": base_url,
        "decision": decision,
        "retention_score": _round(score),
        "metrics": {
            "active_worker_count": active,
            "known_worker_count": known,
            "active_worker_ratio": _round(active_ratio),
            "returning_workers_24h": returning_24h,
            "return_ratio_24h": _round(return_ratio),
            "completed_workers": completed,
            "completed_workers_24h": recent_completed,
            "completion_ratio": _round(completion_ratio),
            "connected_agents": connected,
            "dormant_agents": dormant,
            "dormant_ratio": _round(dormant_ratio),
            "active_worker_leases": leases,
            "youngest_worker_age_seconds": youngest_worker_age,
            "oldest_recent_worker_age_seconds": oldest_active_worker_age,
        },
        "storage": storage,
        "worker_retention_policy": worker_policy,
        "agent_retention_policy": agent_policy,
        "causes": causes,
        "next_actions": next_actions,
        "watch": {
            "schema": "nomad.retention_watch.v1",
            "sample_every_seconds": min(
                300,
                max(30, int(worker_policy.get("recommended_heartbeat_seconds") or 300)),
            ),
            "alert_if": [
                "retention_score < 0.55",
                "active_worker_ratio < 0.7 while known_worker_count > 0",
                "registry_storage.restart_durable=false",
                "dormant_ratio > 0.25",
            ],
        },
        "recent_worker_ids": [str(row.get("agent_id") or "") for row in recent_workers[:12]],
        "recent_agent_ids": [str(row.get("agent_id") or "") for row in recent_nodes[:12]],
        "updated_at": datetime.now(UTC).isoformat(),
    }
