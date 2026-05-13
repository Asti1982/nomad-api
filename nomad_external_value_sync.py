"""Local durable sync for Nomad's external-value ledger.

Render free instances are treated as a stateless public projection. The local
machine keeps the durable ledger and can replay monotonic public events after a
restart without storing payout secrets in Render or source control.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from nomad_external_value import STAGE_INDEX, _ledger_path, _read_events, summarize_external_value_ledger
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
    return state_root() / "nomad_external_value_public_snapshots"


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": event.get("agent_id") or "",
        "external_id": event.get("external_id") or "",
        "stage": event.get("stage") or "",
        "work_url": event.get("work_url") or "",
        "proof_digest": event.get("proof_digest") or "",
        "verifier_trace_digest": event.get("verifier_trace_digest") or "",
        "amount_usd": float(event.get("amount_usd") or event.get("revenue_recognized_usd") or 0.0),
        "meta": event.get("meta") if isinstance(event.get("meta"), dict) else {},
    }


def http_get_json(url: str, timeout: float = 20.0) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "NomadLocalExternalValueSync/0.1",
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
            "User-Agent": "NomadLocalExternalValueSync/0.1",
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


def snapshot_public_external_value(
    *,
    base_url: str = "https://www.syndiode.com",
    snapshot_dir: Path | str | None = None,
    timeout: float = 20.0,
    fetch_json: JsonFetcher = http_get_json,
) -> dict[str, Any]:
    root = _base(base_url)
    summary_url = f"{root}/swarm/external-value?summary=1"
    surface_url = f"{root}/.well-known/nomad-external-value.json"
    summary = fetch_json(summary_url, timeout)
    surface = fetch_json(surface_url, timeout)

    directory = _snapshot_dir(snapshot_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"external_value_public_{_safe_stamp()}.json"
    payload = {
        "schema": "nomad.external_value_public_snapshot.v1",
        "generated_at": _iso_now(),
        "base_url": root,
        "summary_url": summary_url,
        "surface_url": surface_url,
        "summary": summary,
        "surface": surface,
    }
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": bool(summary.get("ok")),
        "schema": "nomad.external_value_public_snapshot.v1",
        "generated_at": payload["generated_at"],
        "base_url": root,
        "snapshot_path": str(path),
        "summary_ok": bool(summary.get("ok")),
        "surface_ok": bool(surface.get("ok")),
        "public_event_tail_count": int(((summary.get("json") or {}).get("event_tail_count") or 0) if summary.get("ok") else 0),
        "public_distinct_externals": int(((summary.get("json") or {}).get("distinct_externals") or 0) if summary.get("ok") else 0),
    }


def _public_stage_map(public_summary: dict[str, Any]) -> dict[str, str]:
    rows = public_summary.get("latest_by_external")
    if not isinstance(rows, list):
        rows = []
    out: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("external_id") or "")
        stage = str(row.get("stage") or "").strip().lower()
        if eid and stage in STAGE_INDEX:
            out[eid] = stage
    return out


def plan_external_value_public_sync(
    local_events: list[dict[str, Any]],
    public_summary: dict[str, Any],
) -> dict[str, Any]:
    """Compute replay candidates from local durable ledger into public Render state."""
    public_stage = _public_stage_map(public_summary)
    shadow = dict(public_stage)
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for event in local_events:
        eid = str(event.get("external_id") or "")
        stage = str(event.get("stage") or "").strip().lower()
        if not eid or stage not in STAGE_INDEX:
            blocked.append({"external_id": eid, "stage": stage, "reason": "invalid_event"})
            continue
        current = shadow.get(eid, "")
        current_idx = STAGE_INDEX.get(current, -1)
        requested_idx = STAGE_INDEX[stage]
        if requested_idx <= current_idx:
            skipped.append({"external_id": eid, "stage": stage, "reason": "already_public_or_shadowed"})
            continue
        if requested_idx != current_idx + 1:
            blocked.append(
                {
                    "external_id": eid,
                    "stage": stage,
                    "public_or_shadow_stage": current or "(none)",
                    "reason": "missing_prior_stage",
                }
            )
            continue
        candidates.append(
            {
                "external_id": eid,
                "stage": stage,
                "source_event_id": event.get("event_id") or "",
                "payload": _event_payload(event),
            }
        )
        shadow[eid] = stage

    return {
        "schema": "nomad.external_value_public_sync_plan.v1",
        "local_event_count": len(local_events),
        "public_distinct_externals": len(public_stage),
        "replay_candidate_count": len(candidates),
        "skipped_count": len(skipped),
        "blocked_count": len(blocked),
        "candidates": candidates,
        "skipped": skipped[:40],
        "blocked": blocked[:40],
    }


def sync_external_value_to_public(
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
    """Replay local durable external-value events into the public stateless API."""
    root = _base(base_url)
    path = _ledger_path(ledger_path)
    local_events = _read_events(path)
    local_summary = summarize_external_value_ledger(ledger_path=path)
    public_url = f"{root}/swarm/external-value?summary=1"
    public_read = fetch_json(public_url, timeout)
    public_summary = public_read.get("json") if public_read.get("ok") and isinstance(public_read.get("json"), dict) else {}
    plan = plan_external_value_public_sync(local_events, public_summary)

    snapshot_result = {}
    if snapshot:
        snapshot_result = snapshot_public_external_value(
            base_url=root,
            snapshot_dir=snapshot_dir,
            timeout=timeout,
            fetch_json=fetch_json,
        )

    post_results: list[dict[str, Any]] = []
    if apply and public_read.get("ok"):
        post_url = f"{root}/swarm/external-value"
        for item in plan["candidates"]:
            response = post_json(post_url, item["payload"], timeout)
            body = response.get("json") if isinstance(response.get("json"), dict) else {}
            accepted = bool(response.get("ok") and body.get("ok"))
            duplicate = str(body.get("reason") or body.get("error") or "") in {"duplicate_stage", "transition_rejected"}
            post_results.append(
                {
                    "external_id": item["external_id"],
                    "stage": item["stage"],
                    "accepted": accepted,
                    "status_code": response.get("status_code", 0),
                    "public_event_id": body.get("event_id", ""),
                    "public_receipt_digest": body.get("nomad_proof_receipt_digest", ""),
                    "error": "" if accepted else str(body.get("reason") or body.get("error") or response.get("error") or ""),
                    "duplicate_or_stale": bool(duplicate),
                }
            )

    accepted_count = sum(1 for row in post_results if row.get("accepted"))
    failed_posts = [row for row in post_results if not row.get("accepted") and not row.get("duplicate_or_stale")]
    final_public_read = public_read
    if apply and public_read.get("ok"):
        final_public_read = fetch_json(public_url, timeout)
    final_public_summary = (
        final_public_read.get("json")
        if final_public_read.get("ok") and isinstance(final_public_read.get("json"), dict)
        else public_summary
    )
    final_public_events = int(final_public_summary.get("event_tail_count") or 0)
    final_public_externals = int(final_public_summary.get("distinct_externals") or 0)
    return {
        "ok": bool(public_read.get("ok")) and not failed_posts,
        "schema": "nomad.external_value_public_sync.v1",
        "generated_at": _iso_now(),
        "base_url": root,
        "mode": "apply" if apply else "dry_run",
        "local_machine_is_canonical": True,
        "local_ledger_path": str(path),
        "local_event_tail_count": int(local_summary.get("event_tail_count") or 0),
        "local_distinct_externals": int(local_summary.get("distinct_externals") or 0),
        "local_revenue_recognized_usd_total": float(local_summary.get("revenue_recognized_usd_total") or 0.0),
        "public_summary_ok": bool(public_read.get("ok")),
        "public_summary_url": public_url,
        "public_event_tail_count": int(public_summary.get("event_tail_count") or 0),
        "public_distinct_externals": int(public_summary.get("distinct_externals") or 0),
        "public_revenue_recognized_usd_total": float(public_summary.get("revenue_recognized_usd_total") or 0.0),
        "final_public_event_tail_count": final_public_events,
        "final_public_distinct_externals": final_public_externals,
        "final_public_revenue_recognized_usd_total": float(
            final_public_summary.get("revenue_recognized_usd_total") or 0.0
        ),
        "public_projection_lag_after": max(0, int(local_summary.get("event_tail_count") or 0) - final_public_events),
        "replay_candidate_count": int(plan.get("replay_candidate_count") or 0),
        "posted_count": accepted_count,
        "failed_post_count": len(failed_posts),
        "skipped_count": int(plan.get("skipped_count") or 0),
        "blocked_count": int(plan.get("blocked_count") or 0),
        "snapshot": snapshot_result,
        "post_results": post_results,
        "plan": plan,
        "machine_instruction": (
            "run_dry_first_then_apply_after_render_restart_or_when_public_projection_lags_local_durable_ledger"
        ),
    }
