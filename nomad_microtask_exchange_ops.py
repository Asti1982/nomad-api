"""Template and metrics ops for microtask exchange lanes."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


SUBMIT_LEDGER_PATH = Path("nomad_microtask_ledger.jsonl")
SETTLE_LEDGER_PATH = Path("nomad_microtask_settlement_ledger.jsonl")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{base}{p}" if base else p


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_rows(path: Path, *, limit: int = 1000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-max(1, limit) :]:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    except OSError:
        return []
    return rows


def _templates() -> list[dict[str, Any]]:
    return [
        {"template_id": "endpoint_health_proof.basic", "lane_id": "endpoint_health_proof", "price_eur": 0.02, "objective": "protocol_drift_scan"},
        {"template_id": "endpoint_health_proof.deep_tls", "lane_id": "endpoint_health_proof", "price_eur": 0.03, "objective": "protocol_drift_scan"},
        {"template_id": "contract_diff.openapi_break", "lane_id": "contract_diff_check", "price_eur": 0.05, "objective": "proof_pressure_engine"},
        {"template_id": "contract_diff.schema_regression", "lane_id": "contract_diff_check", "price_eur": 0.06, "objective": "proof_pressure_engine"},
        {"template_id": "trace_triage.retry_class", "lane_id": "trace_triage_compact", "price_eur": 0.03, "objective": "settlement_capacity_builder"},
        {"template_id": "trace_triage.tool_timeout", "lane_id": "trace_triage_compact", "price_eur": 0.04, "objective": "settlement_capacity_builder"},
        {"template_id": "jsonl_validate.shape", "lane_id": "trace_triage_compact", "price_eur": 0.03, "objective": "overmint_compressor"},
        {"template_id": "jsonl_validate.anomaly", "lane_id": "trace_triage_compact", "price_eur": 0.04, "objective": "overmint_compressor"},
        {"template_id": "idempotency_audit.keys", "lane_id": "contract_diff_check", "price_eur": 0.06, "objective": "payment_friction_scan"},
        {"template_id": "idempotency_audit.safe_retry", "lane_id": "contract_diff_check", "price_eur": 0.05, "objective": "payment_friction_scan"},
        {"template_id": "latency_probe.p95", "lane_id": "endpoint_health_proof", "price_eur": 0.03, "objective": "latency_anomaly_hunt"},
        {"template_id": "latency_probe.status_mix", "lane_id": "endpoint_health_proof", "price_eur": 0.03, "objective": "latency_anomaly_hunt"},
    ]


def build_microtask_templates(*, base_url: str) -> dict[str, Any]:
    templates = _templates()
    return {
        "ok": True,
        "schema": "nomad.microtask_templates.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "template_count": len(templates),
        "templates": templates,
        "links": {
            "catalog": _u(base_url, "/swarm/worker-catalog"),
            "submit": _u(base_url, "/swarm/microtask/submit"),
            "settle": _u(base_url, "/swarm/microtask/settle"),
            "metrics": _u(base_url, "/swarm/microtask-metrics"),
        },
        "machine_instruction": "select_template_submit_task_settle_with_proof_repeat_for_lane_with_best_fill_rate",
    }


def build_microtask_metrics(*, base_url: str, lookback_hours: int = 24) -> dict[str, Any]:
    cutoff = datetime.now(UTC) - timedelta(hours=max(1, int(lookback_hours)))
    submits = _read_rows(SUBMIT_LEDGER_PATH, limit=5000)
    settles = _read_rows(SETTLE_LEDGER_PATH, limit=5000)
    recent_submits: list[dict[str, Any]] = []
    for row in submits:
        ts = str(row.get("generated_at") or "").strip()
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        if dt >= cutoff:
            recent_submits.append(row)
    recent_settles: list[dict[str, Any]] = []
    for row in settles:
        ts = str(row.get("generated_at") or "").strip()
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        if dt >= cutoff:
            recent_settles.append(row)

    task_to_lane = {str(row.get("task_id") or ""): str(row.get("lane_id") or "") for row in recent_submits if row.get("task_id")}
    lane_stats: dict[str, dict[str, Any]] = {}
    for row in recent_submits:
        lane = str(row.get("lane_id") or "unknown_lane")
        stat = lane_stats.setdefault(lane, {"submitted": 0, "accepted_submits": 0, "settled": 0, "settled_eur": 0.0})
        stat["submitted"] += 1
        if bool(row.get("accepted")):
            stat["accepted_submits"] += 1
    for row in recent_settles:
        task_id = str(row.get("task_id") or "")
        lane = task_to_lane.get(task_id) or "unknown_lane"
        stat = lane_stats.setdefault(lane, {"submitted": 0, "accepted_submits": 0, "settled": 0, "settled_eur": 0.0})
        if bool(row.get("accepted")):
            stat["settled"] += 1
            stat["settled_eur"] += _num(row.get("settled_price_eur"), 0.0)

    lane_rows: list[dict[str, Any]] = []
    for lane, stat in lane_stats.items():
        submitted = int(stat["submitted"])
        settled = int(stat["settled"])
        accepted_submits = int(stat["accepted_submits"])
        lane_rows.append(
            {
                "lane_id": lane,
                "submitted": submitted,
                "accepted_submits": accepted_submits,
                "settled": settled,
                "fill_rate": round(settled / max(1, accepted_submits), 4),
                "settled_eur": round(_num(stat["settled_eur"]), 4),
                "avg_settled_eur": round(_num(stat["settled_eur"]) / max(1, settled), 4),
            }
        )
    lane_rows.sort(key=lambda item: (float(item.get("settled_eur") or 0.0), float(item.get("fill_rate") or 0.0)), reverse=True)
    total_settled_eur = round(sum(float(item.get("settled_eur") or 0.0) for item in lane_rows), 4)
    return {
        "ok": True,
        "schema": "nomad.microtask_metrics.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "window_hours": max(1, int(lookback_hours)),
        "totals": {
            "submitted": sum(int(item.get("submitted") or 0) for item in lane_rows),
            "accepted_submits": sum(int(item.get("accepted_submits") or 0) for item in lane_rows),
            "settled": sum(int(item.get("settled") or 0) for item in lane_rows),
            "settled_eur": total_settled_eur,
        },
        "lane_metrics": lane_rows,
        "machine_instruction": "prioritize_lanes_with_positive_settled_eur_and_high_fill_rate",
    }

