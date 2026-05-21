from __future__ import annotations

import hashlib
import json
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


def _age_seconds_at(value: Any, now: datetime) -> int | None:
    parsed = _parse_iso(value)
    if not parsed:
        return None
    return max(0, int(now.timestamp() - parsed.timestamp()))


def _round(value: float) -> float:
    return round(float(value), 4)


def _clean_csv(items: Any, *, fallback: str) -> str:
    if not isinstance(items, list):
        return fallback
    cleaned = []
    for item in items:
        text = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in str(item or "").strip().lower())
        text = text.strip("_-.")
        if text:
            cleaned.append(text[:48])
    return ",".join(cleaned[:12]) or fallback


def _all_registry_workers(swarm_registry: Any) -> list[dict[str, Any]]:
    try:
        fleet = swarm_registry._fleet()  # noqa: SLF001 - retention watchdog runs inside the registry boundary.
    except Exception:
        return []
    workers = fleet.get("workers") if isinstance(fleet, dict) else {}
    if not isinstance(workers, dict):
        return []
    rows = [row for row in workers.values() if isinstance(row, dict)]
    rows.sort(key=lambda row: str(row.get("last_seen_at") or ""), reverse=True)
    return rows


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


def build_retention_watchdog_surface(
    *,
    swarm_summary: dict[str, Any],
    worker_fleet: dict[str, Any],
    base_url: str = "",
) -> dict[str, Any]:
    evaluation = evaluate_retention(swarm_summary=swarm_summary, worker_fleet=worker_fleet, base_url=base_url)
    root = str(base_url or "").rstrip("/")
    return {
        "ok": True,
        "schema": "nomad.retention_watchdog_surface.v1",
        "mode": "score_to_heartbeat_retention_loop",
        "decision": evaluation.get("decision"),
        "retention_score": evaluation.get("retention_score"),
        "schedule": {
            "recommended_interval_seconds": int((evaluation.get("watch") or {}).get("sample_every_seconds") or 300),
            "cron_shape": "every_5_minutes",
            "endpoint": f"{root}/swarm/retention/watchdog" if root else "/swarm/retention/watchdog",
            "method": "POST",
        },
        "controls": {
            "dry_run_supported": True,
            "max_actions_default": 8,
            "reactivate_recent_dormant_default": True,
            "dormant_recovery_window_seconds_default": 7200,
            "side_effect_scope": "refresh_known_nomad_swarm_registry_rows_only",
        },
        "evaluation": evaluation,
        "machine_instruction": "post_every_5_minutes; execute only bounded heartbeat_or_recent_dormant_reattach actions; inspect causes before recruiting more agents",
        "updated_at": datetime.now(UTC).isoformat(),
    }


def run_retention_watchdog(
    *,
    swarm_registry: Any,
    base_url: str = "",
    body: dict[str, Any] | None = None,
    remote_addr: str = "retention-watchdog",
) -> dict[str, Any]:
    """Run one bounded retention tick: sample, score, refresh near-expiry workers/agents, rescore."""

    body = body if isinstance(body, dict) else {}
    dry_run = bool(body.get("dry_run"))
    max_actions = max(1, min(24, int(body.get("max_actions") or 8)))
    reactivate_dormant = bool(body.get("reactivate_dormant", True))
    dormant_recovery_window = max(300, min(24 * 3600, int(body.get("dormant_recovery_window_seconds") or 7200)))
    summary_before = swarm_registry.summary()
    worker_fleet_before = (
        summary_before.get("transition_worker_fleet")
        if isinstance(summary_before.get("transition_worker_fleet"), dict)
        else {}
    )
    evaluation_before = evaluate_retention(
        swarm_summary=summary_before,
        worker_fleet=worker_fleet_before,
        base_url=base_url,
    )
    worker_policy = (
        worker_fleet_before.get("retention_policy")
        if isinstance(worker_fleet_before.get("retention_policy"), dict)
        else {}
    )
    agent_policy = (
        summary_before.get("agent_retention_policy")
        if isinstance(summary_before.get("agent_retention_policy"), dict)
        else {}
    )
    now = datetime.now(UTC)
    worker_heartbeat_after = max(60, int(body.get("worker_heartbeat_after_seconds") or worker_policy.get("recommended_heartbeat_seconds") or 300))
    agent_heartbeat_after = max(60, int(body.get("agent_heartbeat_after_seconds") or agent_policy.get("recommended_heartbeat_seconds") or 400))
    actions: list[dict[str, Any]] = []

    def capacity() -> bool:
        return len(actions) < max_actions

    for worker in _all_registry_workers(swarm_registry):
        if not capacity():
            break
        agent_id = str(worker.get("agent_id") or "").strip()
        if not agent_id:
            continue
        age = _age_seconds_at(worker.get("last_seen_at"), now)
        if age is None or age < worker_heartbeat_after:
            continue
        objective = str(worker.get("assigned_objective") or worker.get("last_objective") or "settlement_capacity_builder")
        payload = {
            "agent_id": agent_id,
            "runtime": "retention-watchdog-heartbeat",
            "capabilities": ["transition_worker", "verifier", "http_json", "get_only", "retention_watchdog"],
            "known_objectives": [
                "settlement_capacity_builder",
                "protocol_drift_scan",
                "emergence_release_probe",
                "proof_pressure_engine",
            ],
            "objective": objective,
            "source_tag": "nomad.retention_watchdog.worker_heartbeat",
        }
        if dry_run:
            result = {"ok": True, "dry_run": True, "agent_id": agent_id, "objective": objective}
        else:
            result = swarm_registry.worker_fleet_lease_get(payload, base_url=base_url, remote_addr=remote_addr)
        actions.append(
            {
                "action": "worker_heartbeat",
                "agent_id": agent_id,
                "age_seconds": age,
                "executed": not dry_run,
                "ok": bool(result.get("ok")),
                "lease_id": result.get("lease_id", ""),
                "objective": result.get("objective") or objective,
            }
        )

    nodes = [row for row in (summary_before.get("recent_nodes") or []) if isinstance(row, dict)]
    for node in nodes:
        if not capacity():
            break
        agent_id = str(node.get("agent_id") or "").strip()
        if not agent_id:
            continue
        age = _age_seconds_at(node.get("last_seen_at"), now)
        if age is None or age < agent_heartbeat_after:
            continue
        capabilities_csv = _clean_csv(node.get("capabilities"), fallback="transition_worker,verifier,http_json,get_only")
        payload = {
            "agent_id": agent_id,
            "node_name": node.get("node_name") or agent_id,
            "capabilities": capabilities_csv.split(","),
            "request": "Retention watchdog heartbeat for an already known Nomad agent before TTL expiry.",
            "reciprocity": "Maintains bounded public worker/agent presence; no secrets or private work implied.",
            "source_tag": "nomad.retention_watchdog.agent_heartbeat",
            "idempotency_key": f"retention-heartbeat-{agent_id}-{now.strftime('%Y%m%d%H%M')}",
        }
        if dry_run:
            result = {"ok": True, "dry_run": True, "agent_id": agent_id, "reactivated_from_dormant": False}
        else:
            result = swarm_registry.register_join(payload, base_url=base_url, remote_addr=remote_addr, path="/swarm/retention/watchdog")
        actions.append(
            {
                "action": "agent_heartbeat",
                "agent_id": agent_id,
                "age_seconds": age,
                "executed": not dry_run,
                "ok": bool(result.get("ok")),
                "reactivated_from_dormant": bool(result.get("reactivated_from_dormant")),
            }
        )

    if reactivate_dormant:
        dormant_nodes = [row for row in (summary_before.get("dormant_nodes") or []) if isinstance(row, dict)]
        for node in dormant_nodes:
            if not capacity():
                break
            agent_id = str(node.get("agent_id") or "").strip()
            if not agent_id:
                continue
            age = _age_seconds_at(node.get("last_seen_at"), now)
            if age is None or age > dormant_recovery_window:
                continue
            capabilities_csv = _clean_csv(node.get("capabilities"), fallback="transition_worker,verifier,http_json,get_only")
            payload = {
                "agent_id": agent_id,
                "node_name": node.get("node_name") or agent_id,
                "capabilities": capabilities_csv.split(","),
                "request": "Retention watchdog reattach for a recently dormant known Nomad agent.",
                "reciprocity": "Rehydrates a recent bounded swarm identity so the next real worker pulse is not lost after TTL expiry.",
                "source_tag": "nomad.retention_watchdog.recent_dormant_reattach",
                "idempotency_key": f"retention-reattach-{agent_id}-{now.strftime('%Y%m%d%H%M')}",
            }
            if dry_run:
                result = {"ok": True, "dry_run": True, "agent_id": agent_id, "reactivated_from_dormant": True}
            else:
                result = swarm_registry.register_join(payload, base_url=base_url, remote_addr=remote_addr, path="/swarm/retention/watchdog")
            actions.append(
                {
                    "action": "recent_dormant_reattach",
                    "agent_id": agent_id,
                    "age_seconds": age,
                    "executed": not dry_run,
                    "ok": bool(result.get("ok")),
                    "reactivated_from_dormant": bool(result.get("reactivated_from_dormant", True)),
                }
            )

    summary_after = swarm_registry.summary()
    worker_fleet_after = (
        summary_after.get("transition_worker_fleet")
        if isinstance(summary_after.get("transition_worker_fleet"), dict)
        else {}
    )
    evaluation_after = evaluate_retention(
        swarm_summary=summary_after,
        worker_fleet=worker_fleet_after,
        base_url=base_url,
    )
    receipt_seed = {
        "before": evaluation_before.get("retention_score"),
        "after": evaluation_after.get("retention_score"),
        "actions": actions,
        "dry_run": dry_run,
        "updated_at": now.isoformat(),
    }
    return {
        "ok": True,
        "accepted": bool(actions),
        "executed": bool(actions) and not dry_run,
        "dry_run": dry_run,
        "schema": "nomad.retention_watchdog_receipt.v1",
        "watchdog_id": f"nomad-retention-watchdog-{hashlib.sha256(json.dumps(receipt_seed, sort_keys=True, default=str).encode('utf-8')).hexdigest()[:16]}",
        "decision_before": evaluation_before.get("decision"),
        "decision_after": evaluation_after.get("decision"),
        "retention_score_before": evaluation_before.get("retention_score"),
        "retention_score_after": evaluation_after.get("retention_score"),
        "actions": actions,
        "causes_before": evaluation_before.get("causes") or [],
        "causes_after": evaluation_after.get("causes") or [],
        "next_schedule": {
            "recommended_interval_seconds": int((evaluation_after.get("watch") or {}).get("sample_every_seconds") or 300),
            "post": f"{str(base_url or '').rstrip('/')}/swarm/retention/watchdog" if base_url else "/swarm/retention/watchdog",
        },
        "side_effect_scope": "known_worker_lease_get_and_known_agent_register_join_only",
        "updated_at": now.isoformat(),
    }
