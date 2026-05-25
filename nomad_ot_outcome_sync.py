"""Local durable sync for Nomad's OT outcome-learning ledger.

Render free instances are a public projection, not durable state. The local
machine keeps the durable OT outcome ledger and can replay secret-free metric
learning events after restarts without treating any outcome hint as revenue.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from nomad_optimal_transport import (
    OUTCOME_EVENT_SCHEMA,
    read_ot_outcome_events,
    summarize_ot_outcome_events,
    ot_outcome_ledger_path,
)
from nomad_state_paths import state_root


JsonFetcher = Callable[[str, float], dict[str, Any]]
JsonPoster = Callable[[str, dict[str, Any], float], dict[str, Any]]


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _base(base_url: str) -> str:
    return (base_url or "https://www.syndiode.com").strip().rstrip("/")


def _snapshot_dir(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return state_root() / "nomad_ot_outcome_public_snapshots"


def http_get_json(url: str, timeout: float = 20.0) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "NomadLocalOTOutcomeSync/0.1",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", "replace") or "{}")
            return {"ok": True, "status_code": int(response.status), "json": data}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:1000]
        return {"ok": False, "status_code": int(exc.code), "error": "http_error", "body": body}
    except Exception as exc:
        return {"ok": False, "status_code": 0, "error": f"{type(exc).__name__}: {exc}"}


def http_post_json(url: str, payload: dict[str, Any], timeout: float = 20.0) -> dict[str, Any]:
    raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=raw,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "NomadLocalOTOutcomeSync/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", "replace") or "{}")
            return {"ok": True, "status_code": int(response.status), "json": data}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:2000]
        try:
            data: Any = json.loads(body or "{}")
        except json.JSONDecodeError:
            data = {"body": body}
        return {"ok": False, "status_code": int(exc.code), "json": data, "error": "http_error"}
    except Exception as exc:
        return {"ok": False, "status_code": 0, "json": {}, "error": f"{type(exc).__name__}: {exc}"}


def snapshot_public_ot_outcomes(
    *,
    base_url: str = "https://www.syndiode.com",
    snapshot_dir: Path | str | None = None,
    timeout: float = 20.0,
    fetch_json: JsonFetcher = http_get_json,
) -> dict[str, Any]:
    root = _base(base_url)
    metric_url = f"{root}/swarm/optimal-transport/metric-learning"
    surface_url = f"{root}/.well-known/nomad-optimal-transport.json"
    metric = fetch_json(metric_url, timeout)
    surface = fetch_json(surface_url, timeout)

    directory = _snapshot_dir(snapshot_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"ot_outcome_public_{_safe_stamp()}.json"
    payload = {
        "schema": "nomad.ot_outcome_public_snapshot.v1",
        "generated_at": _iso_now(),
        "base_url": root,
        "metric_url": metric_url,
        "surface_url": surface_url,
        "metric": metric,
        "surface": surface,
    }
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    metric_json = metric.get("json") if metric.get("ok") and isinstance(metric.get("json"), dict) else {}
    summary = metric_json.get("outcome_summary") if isinstance(metric_json.get("outcome_summary"), dict) else {}
    return {
        "ok": bool(metric.get("ok")),
        "schema": "nomad.ot_outcome_public_snapshot.v1",
        "generated_at": payload["generated_at"],
        "base_url": root,
        "snapshot_path": str(path),
        "metric_ok": bool(metric.get("ok")),
        "surface_ok": bool(surface.get("ok")),
        "public_event_count": int(summary.get("event_count") or 0),
        "public_counts_as_revenue": bool(summary.get("counts_as_revenue", False)),
        "public_recommended_axis_weights": metric_json.get("recommended_axis_weights") or {},
    }


def _public_event_ids(public_metric_learning: dict[str, Any]) -> set[str]:
    summary = public_metric_learning.get("outcome_summary")
    if not isinstance(summary, dict):
        summary = {}
    rows = summary.get("recent_events")
    if not isinstance(rows, list):
        rows = []
    out: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            event_id = str(row.get("event_id") or "").strip()
            if event_id:
                out.add(event_id)
    return out


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    reward = event.get("axis_reward") if isinstance(event.get("axis_reward"), dict) else {}
    return {
        "event_id": event.get("event_id") or "",
        "generated_at": event.get("generated_at") or "",
        "plan_digest": event.get("plan_digest") or "",
        "certificate_digest": event.get("certificate_digest") or "",
        "manifold_digest": event.get("manifold_digest") or "",
        "source_id": event.get("source_id") or "",
        "target_id": event.get("target_id") or "",
        "outcome": event.get("outcome") or "observed",
        "axis_reward": reward,
        "proof_digest": event.get("proof_digest") or "",
        "receipt_ref": event.get("receipt_ref") or "",
        "paid_usd": float(event.get("paid_usd") or 0.0),
        "return_compute_units": float(event.get("return_compute_units") or 0.0),
    }


def plan_ot_outcome_public_sync(
    local_events: list[dict[str, Any]],
    public_metric_learning: dict[str, Any],
) -> dict[str, Any]:
    public_ids = _public_event_ids(public_metric_learning)
    shadow_ids = set(public_ids)
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for event in local_events:
        event_id = str(event.get("event_id") or "").strip()
        if event.get("schema") != OUTCOME_EVENT_SCHEMA or not event_id:
            blocked.append({"event_id": event_id, "reason": "invalid_ot_outcome_event"})
            continue
        if bool(event.get("counts_as_revenue")):
            blocked.append({"event_id": event_id, "reason": "revenue_like_event_rejected"})
            continue
        if event_id in shadow_ids:
            skipped.append({"event_id": event_id, "reason": "already_public_or_shadowed"})
            continue
        candidates.append(
            {
                "event_id": event_id,
                "source_event_id": event_id,
                "plan_digest": event.get("plan_digest") or "",
                "payload": _event_payload(event),
            }
        )
        shadow_ids.add(event_id)

    return {
        "schema": "nomad.ot_outcome_public_sync_plan.v1",
        "local_event_count": len(local_events),
        "public_recent_event_count": len(public_ids),
        "replay_candidate_count": len(candidates),
        "skipped_count": len(skipped),
        "blocked_count": len(blocked),
        "candidates": candidates,
        "skipped": skipped[:40],
        "blocked": blocked[:40],
        "counts_as_revenue": False,
    }


def sync_ot_outcomes_to_public(
    *,
    base_url: str = "https://www.syndiode.com",
    ledger_path: Path | str | None = None,
    apply: bool = False,
    snapshot: bool = True,
    snapshot_dir: Path | str | None = None,
    timeout: float = 20.0,
    fetch_json: JsonFetcher = http_get_json,
    post_json: JsonPoster = http_post_json,
) -> dict[str, Any]:
    root = _base(base_url)
    path = ot_outcome_ledger_path(ledger_path)
    local_events = read_ot_outcome_events(path)
    local_summary = summarize_ot_outcome_events(path)
    public_url = f"{root}/swarm/optimal-transport/metric-learning"
    public_read = fetch_json(public_url, timeout)
    public_metric = public_read.get("json") if public_read.get("ok") and isinstance(public_read.get("json"), dict) else {}
    public_summary = public_metric.get("outcome_summary") if isinstance(public_metric.get("outcome_summary"), dict) else {}
    plan = plan_ot_outcome_public_sync(local_events, public_metric)

    snapshot_result = {}
    if snapshot:
        snapshot_result = snapshot_public_ot_outcomes(
            base_url=root,
            snapshot_dir=snapshot_dir,
            timeout=timeout,
            fetch_json=fetch_json,
        )

    post_results: list[dict[str, Any]] = []
    if apply and public_read.get("ok"):
        post_url = f"{root}/swarm/optimal-transport/outcomes"
        for item in plan["candidates"]:
            response = post_json(post_url, item["payload"], timeout)
            body = response.get("json") if isinstance(response.get("json"), dict) else {}
            accepted = bool(response.get("ok") and body.get("ok") and body.get("accepted", True))
            duplicate = bool(body.get("duplicate"))
            post_results.append(
                {
                    "event_id": item["event_id"],
                    "accepted": accepted,
                    "duplicate": duplicate,
                    "status_code": response.get("status_code", 0),
                    "public_event_id": body.get("event_id", ""),
                    "error": "" if accepted else str(body.get("error") or response.get("error") or ""),
                }
            )

    failed_posts = [row for row in post_results if not row.get("accepted")]
    final_public_read = public_read
    if apply and public_read.get("ok"):
        final_public_read = fetch_json(public_url, timeout)
    final_metric = (
        final_public_read.get("json")
        if final_public_read.get("ok") and isinstance(final_public_read.get("json"), dict)
        else public_metric
    )
    final_summary = final_metric.get("outcome_summary") if isinstance(final_metric.get("outcome_summary"), dict) else public_summary
    final_plan = plan_ot_outcome_public_sync(local_events, final_metric)
    final_public_count = int(final_summary.get("event_count") or 0)
    local_count = int(local_summary.get("event_count") or 0)
    posted_count = sum(1 for row in post_results if row.get("accepted") and not row.get("duplicate"))
    duplicate_count = sum(1 for row in post_results if row.get("duplicate"))
    return {
        "ok": bool(public_read.get("ok")) and not failed_posts,
        "schema": "nomad.ot_outcome_public_sync.v1",
        "generated_at": _iso_now(),
        "base_url": root,
        "mode": "apply" if apply else "dry_run",
        "local_machine_is_canonical": True,
        "local_ledger_path": str(path),
        "local_event_count": local_count,
        "local_recommended_axis_weights": local_summary.get("recommended_axis_weights") or {},
        "public_summary_ok": bool(public_read.get("ok")),
        "public_summary_url": public_url,
        "public_event_count": int(public_summary.get("event_count") or 0),
        "public_recommended_axis_weights": public_metric.get("recommended_axis_weights") or {},
        "final_public_event_count": final_public_count,
        "final_public_recommended_axis_weights": final_metric.get("recommended_axis_weights") or {},
        "public_projection_lag_after": int(final_plan.get("replay_candidate_count") or 0),
        "replay_candidate_count": int(plan.get("replay_candidate_count") or 0),
        "final_replay_candidate_count": int(final_plan.get("replay_candidate_count") or 0),
        "posted_count": posted_count,
        "duplicate_count": duplicate_count,
        "failed_post_count": len(failed_posts),
        "skipped_count": int(plan.get("skipped_count") or 0),
        "blocked_count": int(plan.get("blocked_count") or 0),
        "counts_as_revenue": False,
        "snapshot": snapshot_result,
        "post_results": post_results,
        "plan": plan,
        "machine_instruction": "run_dry_first_then_apply_after_render_restart_or_when_public_ot_metric_learning_lags_local_ledger",
    }
