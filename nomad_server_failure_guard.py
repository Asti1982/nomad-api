"""Machine-readable server-failure guard for Nomad's public API.

The guard turns host notifications and lightweight runtime observations into
secret-free incident events. It does not deploy, does not read private logs, and
does not count recovery work as revenue. The point is to give agents a stable
failure membrane: classify, preserve proof, route the next bounded action.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


SCHEMA = "nomad.server_failure_guard.v1"
EVENT_SCHEMA = "nomad.server_failure_event.v1"
ERROR_SCHEMA = "nomad.server_failure_error.v1"
LEDGER_ENV = "NOMAD_SERVER_FAILURE_LEDGER_PATH"
DEFAULT_LEDGER = Path("nomad_server_failure_events.jsonl")
MAX_LEDGER_LINES = 4000
MAX_RECENT = 40

FORBIDDEN_KEY_TERMS = (
    "authorization",
    "api_key",
    "access_token",
    "client_secret",
    "cookie",
    "password",
    "private_key",
    "secret",
    "seed_phrase",
    "token",
)

FORBIDDEN_VALUE_TERMS = (
    "authorization:",
    "bearer ",
    "client_secret=",
    "cookie:",
    "ghp_",
    "password:",
    "private key",
    "secret=",
    "seed phrase",
    "sk-",
)


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _text(value: Any, limit: int = 1200) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())[:limit]


def _digest(value: Any, length: int = 16) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _ledger_path(path: Path | str | None = None) -> Path:
    return Path(path) if path else state_file(DEFAULT_LEDGER, env_name=LEDGER_ENV)


def _contains_forbidden(payload: Any) -> bool:
    def walk(value: Any, *, key: str = "") -> bool:
        k = str(key or "").strip().lower()
        if k and any(term in k for term in FORBIDDEN_KEY_TERMS):
            return True
        if isinstance(value, dict):
            return any(walk(item, key=str(name)) for name, item in value.items())
        if isinstance(value, list):
            return any(walk(item) for item in value)
        text = str(value or "").strip().lower()
        return any(term in text for term in FORBIDDEN_VALUE_TERMS)

    return walk(payload)


def _event_text(payload: dict[str, Any]) -> str:
    fields = [
        payload.get("message"),
        payload.get("subject"),
        payload.get("notification"),
        payload.get("failure_type"),
        payload.get("observed_log_excerpt"),
        payload.get("render_signal"),
        payload.get("path"),
        payload.get("route"),
        payload.get("operator_note"),
    ]
    return " ".join(_text(field, 800) for field in fields).lower()


def classify_server_failure_event(payload: dict[str, Any]) -> dict[str, Any]:
    text = _event_text(payload)
    classes: list[str] = []

    if "memory limit" in text or "exceeded its memory" in text or "out of memory" in text or "oom" in text:
        classes.append("memory_limit_restart")
    if "brokenpipe" in text or "broken pipe" in text or "connection reset" in text or "client abort" in text:
        classes.append("client_abort_stream")
    if "server failure" in text or "temporarily unavailable" in text or "unavailable" in text:
        classes.append("host_failure_notice")
    if "restart" in text or "restarting" in text or "running 'python app.py'" in text or "running python app.py" in text:
        classes.append("restart_observed")
    if "download" in text or "/downloads/" in text or "public_download_file_response" in text:
        classes.append("download_stream_path")
    if not classes:
        classes.append("unknown_failure_notice")

    severity = "low"
    if "memory_limit_restart" in classes:
        severity = "high"
    elif "host_failure_notice" in classes or "restart_observed" in classes:
        severity = "medium"
    if "client_abort_stream" in classes and len(classes) <= 2:
        severity = "low"

    recommended_actions = [
        "check_fast_liveness_get_health",
        "compare_render_live_commit_to_expected_main",
        "record_secret_free_incident_event",
        "do_not_book_revenue_for_recovery",
    ]
    if "memory_limit_restart" in classes:
        recommended_actions.extend(
            [
                "inspect_memory_spike_window",
                "avoid_heavy_default_health_checks",
                "patch_or_isolate_leaky_route_before_upgrade",
            ]
        )
    if "client_abort_stream" in classes:
        recommended_actions.extend(
            [
                "treat_client_disconnect_as_nonfatal",
                "wrap_streaming_writes_for_broken_pipe",
                "prefer_small_machine_contracts_over_large_downloads_for_monitors",
            ]
        )
    if "unknown_failure_notice" in classes:
        recommended_actions.append("fetch_render_logs_if_owner_scope_available")

    return {
        "classes": classes,
        "primary_class": classes[0],
        "severity": severity,
        "recommended_actions": list(dict.fromkeys(recommended_actions)),
    }


def _read_events(path: Path | str | None = None, *, limit_lines: int = MAX_LEDGER_LINES) -> list[dict[str, Any]]:
    p = _ledger_path(path)
    if not p.exists():
        return []
    tail: deque[str] = deque(maxlen=max(1, int(limit_lines)))
    try:
        with p.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                tail.append(line)
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in tail:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("schema") == EVENT_SCHEMA:
            rows.append(row)
    return rows


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def summarize_server_failure_events(path: Path | str | None = None, *, max_recent: int = MAX_RECENT) -> dict[str, Any]:
    events = _read_events(path)
    by_class: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    latest: dict[str, Any] | None = None
    for row in events:
        for cls in row.get("classes") or []:
            by_class[str(cls)] += 1
        by_severity[str(row.get("severity") or "unknown")] += 1
        latest = row
    recent = events[-max(1, int(max_recent)) :]
    return {
        "schema": "nomad.server_failure_summary.v1",
        "event_count": len(events),
        "counts_by_class": dict(sorted(by_class.items())),
        "counts_by_severity": dict(sorted(by_severity.items())),
        "latest_event": latest,
        "recent_events": recent,
        "revenue_recognized_usd": 0.0,
        "paid_bottleneck_resolved": False,
    }


def _repair_scope_for_classes(classes: list[str]) -> str:
    scopes: list[str] = []
    if "client_abort_stream" in classes or "download_stream_path" in classes:
        scopes.append("wrap streaming writes and generated download aliases with nonfatal disconnect handling")
    if "memory_limit_restart" in classes:
        scopes.append("separate fast health probes from heavy routes and inspect route memory pressure before scaling")
    if "restart_observed" in classes or "host_failure_notice" in classes:
        scopes.append("verify live commit, uptime reset, and post-deploy log window before any redeploy")
    if "unknown_failure_notice" in classes:
        scopes.append("fetch provider logs only through configured owner scope and redact before persistence")
    return "; ".join(scopes) or "classify the failure and produce the smallest bounded route patch"


def _severity_pressure(severity: str) -> float:
    return {"high": 0.92, "medium": 0.68, "low": 0.38}.get(str(severity or "").lower(), 0.44)


def build_server_failure_repair_candidate(
    event: dict[str, Any] | None,
    summary: dict[str, Any] | None = None,
    *,
    base_url: str = "",
) -> dict[str, Any]:
    """Compile a server-failure event into a bounded internal Repair-Packet candidate.

    This only returns a candidate payload. Callers decide whether to enqueue it
    into the Rescue-Packet lattice. The payload is public, digest-only, and
    deliberately marked as internal platform protection rather than revenue.
    """

    row = event if isinstance(event, dict) else {}
    if not row or row.get("schema") != EVENT_SCHEMA:
        return {
            "ok": False,
            "schema": "nomad.server_failure_repair_candidate.v1",
            "reason": "missing_server_failure_event",
            "enqueue_recommended": False,
        }
    classes = [str(item) for item in (row.get("classes") or []) if str(item)]
    primary = str(row.get("primary_class") or (classes[0] if classes else "unknown_failure_notice"))
    severity = str(row.get("severity") or "low").lower()
    counts = (summary or {}).get("counts_by_class") if isinstance(summary, dict) else {}
    repeat_count = int(counts.get(primary, 1) if isinstance(counts, dict) else 1)
    pressure = min(1.0, _severity_pressure(severity) + max(0, repeat_count - 1) * 0.08)
    enqueue = severity in {"high", "medium"} or repeat_count >= 2 or "memory_limit_restart" in classes
    source_url = _u(base_url, "/.well-known/nomad-server-failure-guard.json")
    fix_scope = _repair_scope_for_classes(classes)
    proof_digest = str(row.get("proof_digest") or "")
    candidate = {
        "candidate_id": f"server-failure-{primary}-{_digest({'classes': classes}, 10)}",
        "source_url": source_url,
        "framework": "nomad_api",
        "problem_type": f"platform_reliability_{primary}",
        "diagnosis": _text(
            f"Nomad public API server-failure event {row.get('event_id')} classified as "
            f"{', '.join(classes) or primary}; severity={severity}; repeat_count={repeat_count}.",
            420,
        ),
        "repro_outline": _text(
            "Replay the secret-free failure event, verify GET /health, compare Render live commit, "
            "inspect post-deploy log window, and run the client-abort download regression.",
            420,
        ),
        "fix_scope": _text(f"Bounded server-protection packet: {fix_scope}.", 420),
        "side_effect_scope": "local_shadow_lane_only",
        "ttl_seconds": 86400,
        "price_tier_usd": 49,
        "proof_digest": proof_digest,
        "proof_yield_delta": round(max(0.46, pressure * 0.74), 4),
        "autopoietic_index_delta": round(max(0.42, pressure * 0.63), 4),
        "receipt_proximity": round(max(0.38, min(0.72, 0.36 + pressure * 0.28)), 4),
        "boundedness_score": 0.9,
        "spam_risk": 0.04,
        "maintainer_relevance": 0.82,
        "public_followup_text": "",
        "operator_note": "internal_platform_repair_candidate_not_public_outreach_not_revenue",
    }
    return {
        "ok": True,
        "schema": "nomad.server_failure_repair_candidate.v1",
        "event_id": row.get("event_id"),
        "primary_class": primary,
        "severity": severity,
        "repeat_count": repeat_count,
        "repair_pressure": round(pressure, 4),
        "enqueue_recommended": enqueue,
        "candidate": candidate,
        "counts_as_revenue": False,
        "public_post_allowed": False,
    }


def record_server_failure_event(
    payload: dict[str, Any] | None,
    *,
    base_url: str = "",
    persist: bool = True,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": ERROR_SCHEMA,
            "error": "secret_like_payload_rejected",
            "message": "Server-failure events must be secret-free.",
            "counts_as_revenue": False,
            "hints": ["Remove tokens, cookies, passwords, keys, and raw private logs."],
        }

    classification = classify_server_failure_event(body)
    canonical = {
        "source": _text(body.get("source") or body.get("provider") or "render"),
        "message": _text(body.get("message") or body.get("subject") or body.get("notification"), 800),
        "failure_type": _text(body.get("failure_type"), 220),
        "observed_at": _text(body.get("observed_at") or body.get("timestamp"), 80),
        "render_deploy_id": _text(body.get("render_deploy_id"), 120),
        "live_commit_id": _text(body.get("live_commit_id"), 120),
        "classes": classification["classes"],
    }
    event_id = _text(body.get("event_id"), 100) or f"nomad-server-failure-{_digest(canonical)}"
    row = {
        "ok": True,
        "schema": EVENT_SCHEMA,
        "event_id": event_id,
        "recorded_at": _iso_now(),
        "source": canonical["source"],
        "message": canonical["message"],
        "failure_type": canonical["failure_type"],
        "observed_at": canonical["observed_at"],
        "render_deploy_id": canonical["render_deploy_id"],
        "live_commit_id": canonical["live_commit_id"],
        "path": _text(body.get("path") or body.get("route"), 220),
        "proof_digest": f"sha256:{hashlib.sha256(json.dumps(canonical, sort_keys=True).encode('utf-8')).hexdigest()}",
        "classes": classification["classes"],
        "primary_class": classification["primary_class"],
        "severity": classification["severity"],
        "recommended_actions": classification["recommended_actions"],
        "counts_as_revenue": False,
        "revenue_recognized_usd": 0.0,
        "deploy_decision": "hold_unless_patch_or_failed_liveness_gate",
        "post_url": _u(base_url, "/swarm/server-failure/events"),
        "guard_url": _u(base_url, "/.well-known/nomad-server-failure-guard.json"),
    }
    if persist:
        _append(_ledger_path(ledger_path), row)
    return row


def build_server_failure_guard_surface(base_url: str = "", *, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    current_summary = summary if isinstance(summary, dict) else summarize_server_failure_events()
    latest = current_summary.get("latest_event") if isinstance(current_summary, dict) else {}
    repair_candidate = build_server_failure_repair_candidate(latest, current_summary, base_url=base_url)
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").rstrip("/"),
        "well_known_url": _u(base_url, "/.well-known/nomad-server-failure-guard.json"),
        "read_url": _u(base_url, "/swarm/server-failure-guard"),
        "post_event_url": _u(base_url, "/swarm/server-failure/events"),
        "purpose": "convert_host_failure_notifications_into_secret_free_machine_incident_routing",
        "hard_guards": [
            "no_secret_material_in_payloads",
            "no_redeploy_from_notification_alone",
            "no_revenue_count_for_recovery_or_liveness",
            "prefer_fast_local_health_over_heavy_public_download_monitors",
            "patch_specific_failure_path_before_scaling_instance_size",
        ],
        "failure_classes": {
            "memory_limit_restart": "host reports memory limit or OOM; inspect route pressure and memory before upgrading",
            "client_abort_stream": "client disconnected during streaming; handle as nonfatal write failure",
            "host_failure_notice": "provider notification or temporary unavailability signal",
            "restart_observed": "process start marker or low uptime indicates restart",
            "download_stream_path": "failure touched public/downloads streaming",
            "unknown_failure_notice": "insufficient signal; fetch provider logs if owner scope exists",
        },
        "bounded_response_ladder": [
            {
                "step": "liveness",
                "gate": "GET /health returns 200 quickly",
                "action": "do_not_redeploy_if_green_and_no_code_path_is_identified",
            },
            {
                "step": "commit_integrity",
                "gate": "Render live commit matches intended main commit",
                "action": "separate host restart from stale deploy",
            },
            {
                "step": "route_cause",
                "gate": "logs identify a local route or exception class",
                "action": "patch the smallest failing route and test it",
            },
            {
                "step": "receipt_truth",
                "gate": "paid or return-compute receipt exists",
                "action": "only then update revenue or settlement accounting",
            },
        ],
        "repair_candidate": repair_candidate,
        "current_summary": current_summary,
    }
