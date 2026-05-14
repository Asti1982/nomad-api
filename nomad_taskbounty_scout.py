from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import requests

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency in slim deploys
    load_dotenv = None


DEFAULT_TASKBOUNTY_API_BASE = "https://www.task-bounty.com/api/v1"
DEFAULT_TASKBOUNTY_ACCESS_CACHE = Path("nomad_taskbounty_access_cache.json")


FetchJson = Callable[[str, str | None, float], Any]
PostJson = Callable[[str, dict[str, Any], str | None, float], Any]


def _load_env() -> None:
    if load_dotenv is not None:
        load_dotenv()


def _normalize_api_base(api_base: str | None) -> str:
    raw = (api_base or DEFAULT_TASKBOUNTY_API_BASE).strip()
    if not raw:
        raw = DEFAULT_TASKBOUNTY_API_BASE
    if "://" not in raw:
        raw = f"https://{raw}"
    raw = raw.rstrip("/")
    if raw.endswith("/api/v1"):
        return raw
    return f"{raw}/api/v1"


def _request_json(url: str, api_key: str | None, timeout: float) -> Any:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _post_json(url: str, payload: dict[str, Any], api_key: str | None, timeout: float) -> Any:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _redact_secret_text(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_secret_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_secret_text(item) for item in value]
    if not isinstance(value, str):
        return value
    redacted = re.sub(r"x-access-token:[^@\\s]+@", "x-access-token:<redacted>@", value)
    redacted = re.sub(r"(ghs_|ghp_|github_pat_|tb_live_)[A-Za-z0-9_\\-]+", r"\1<redacted>", redacted)
    redacted = re.sub(r"([?&](?:token|key|secret)=)[^&\\s]+", r"\1<redacted>", redacted, flags=re.IGNORECASE)
    return redacted


def _cache_path() -> Path:
    configured = (os.getenv("NOMAD_TASKBOUNTY_ACCESS_CACHE") or "").strip()
    return Path(configured) if configured else DEFAULT_TASKBOUNTY_ACCESS_CACHE


def _load_access_cache() -> dict[str, Any]:
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_access_cache(cache: dict[str, Any]) -> None:
    path = _cache_path()
    path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def _cached_access_data(task_id: str, now: datetime) -> dict[str, Any] | None:
    cache = _load_access_cache()
    item = cache.get(task_id)
    if not isinstance(item, dict):
        return None
    expires_at = _parse_deadline(item.get("expiresAt"))
    if expires_at and expires_at > now:
        data = item.get("data")
        return data if isinstance(data, dict) else None
    return None


def _store_access_data(task_id: str, data: dict[str, Any]) -> None:
    cache = _load_access_cache()
    cache[task_id] = {
        "stored_at": datetime.now(UTC).isoformat(),
        "expiresAt": data.get("expiresAt"),
        "data": _redact_secret_text(
            {
                "repoUrl": data.get("repoUrl"),
                "expiresAt": data.get("expiresAt"),
                "expiresInSeconds": data.get("expiresInSeconds"),
                "submissionWorkflow": data.get("submissionWorkflow") if isinstance(data.get("submissionWorkflow"), list) else [],
                "note": data.get("note") or "",
            }
        ),
    }
    _write_access_cache(cache)


def _as_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("tasks", "data", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _parse_deadline(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _extract_repo(task: dict[str, Any]) -> str | None:
    repo = task.get("repo") or task.get("repository") or task.get("repository_full_name")
    if isinstance(repo, str) and repo.strip():
        return repo.strip()
    tags = task.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str) and tag.startswith("repo:"):
                value = tag.removeprefix("repo:").strip()
                if value:
                    return value
    return None


def _infer_funding_status(task: dict[str, Any]) -> str:
    explicit = str(task.get("funding_status") or "").strip().upper()
    if explicit:
        return explicit
    tags = task.get("tags")
    if isinstance(tags, list) and any(str(tag).lower() == "auto-funded" for tag in tags):
        return "FUNDED"
    return ""


def _task_id(task: dict[str, Any]) -> str:
    return str(task.get("id") or task.get("task_id") or task.get("uuid") or "").strip()


def _merge_task_detail(base: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in detail.items():
        if value in (None, "") and merged.get(key) not in (None, ""):
            continue
        merged[key] = value
    return merged


def _usd_from_cents(cents: int, currency: str) -> float | None:
    if currency.lower() != "usd":
        return None
    return round(cents / 100.0, 2)


def _proof_digest(task: dict[str, Any], gate_state: str) -> str:
    stable = {
        "id": _task_id(task),
        "slug": task.get("slug"),
        "status": task.get("status"),
        "funding_status": task.get("funding_status"),
        "submission_count": task.get("submission_count"),
        "gate_state": gate_state,
    }
    encoded = repr(sorted(stable.items())).encode("utf-8")
    return f"taskbounty:{hashlib.sha256(encoded).hexdigest()[:20]}"


def classify_taskbounty_task(
    task: dict[str, Any],
    *,
    api_key_present: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    task_id = _task_id(task)
    status = str(task.get("status") or "").strip().upper()
    funding_status = _infer_funding_status(task)
    submission_count = _int_or_zero(task.get("submission_count"))
    bounty_cents = _int_or_zero(task.get("bounty_cents") or task.get("amount_cents"))
    currency = str(task.get("currency") or "usd").strip().lower()
    deadline_raw = task.get("submission_deadline") or task.get("deadline")
    deadline = _parse_deadline(deadline_raw)
    deadline_live = deadline is None or deadline > now
    repo = _extract_repo(task)

    if not api_key_present:
        gate_state = "api_key_missing"
        next_action = "add_taskbounty_api_key_before_live_scout"
    elif status != "OPEN":
        gate_state = "not_open"
        next_action = "watch_only_until_task_reopens"
    elif funding_status and funding_status != "FUNDED":
        gate_state = "not_funded"
        next_action = "watch_only_until_funding_status_is_funded"
    elif not deadline_live:
        gate_state = "deadline_passed"
        next_action = "discard_for_revenue_cycle"
    elif not repo:
        gate_state = "repo_access_unknown"
        next_action = "verify_public_repo_and_submission_endpoint_before_work"
    else:
        gate_state = "candidate_submit_gate_unverified"
        next_action = "probe_submission_gate_clone_and_upstream_pr_access_before_patch_work"

    executable_work_allowed = False
    if gate_state == "candidate_submit_gate_unverified":
        allowed_actions = [
            "read_only_repo_probe",
            "submission_endpoint_probe",
            "upstream_pr_access_probe",
            "local_repro_plan",
        ]
        blocked_actions = [
            "push_branch",
            "open_pr",
            "submit_claim",
            "book_revenue",
        ]
    elif gate_state == "watch_only_pending_submission":
        allowed_actions = ["read_only_reconcile", "award_status_poll"]
        blocked_actions = [
            "clone_for_patch",
            "push_branch",
            "open_pr",
            "submit_claim",
            "book_revenue",
        ]
    else:
        allowed_actions = ["read_only_watch"]
        blocked_actions = ["push_branch", "open_pr", "submit_claim", "book_revenue"]

    slug = str(task.get("slug") or "").strip()
    task_url = f"https://www.task-bounty.com/tasks/{slug}" if slug else ""
    title = str(task.get("title") or "").strip()
    description = str(task.get("description") or "").strip()
    description_excerpt = description[:600] if description else ""
    proof_digest = _proof_digest(task, gate_state)

    return {
        "task_id": task_id,
        "title": title,
        "slug": slug,
        "task_url": task_url,
        "repo": repo,
        "bounty_cents": bounty_cents,
        "amount_usd": _usd_from_cents(bounty_cents, currency),
        "currency": currency,
        "status": status,
        "funding_status": funding_status,
        "submission_deadline": deadline.isoformat() if deadline else "",
        "deadline_live": deadline_live,
        "submission_count": submission_count,
        "description_excerpt": description_excerpt,
        "gate_state": gate_state,
        "executable_work_allowed": executable_work_allowed,
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
        "next_action": next_action,
        "unlock_requirements": [
            "task_open_and_funded_verified",
            "submission_endpoint_accepts_new_claim_before_pr_work",
            "repo_access_grant_confirmed_before_clone_or_push",
            "upstream_pr_fork_or_branch_permission_confirmed",
            "payout_and_tax_profile_ready_before_claim",
        ],
        "risk_flags": [
            flag
            for flag in [
                "existing_submission_competition" if submission_count > 0 else "",
                "upstream_access_unverified" if repo else "",
            ]
            if flag
        ],
        "external_value_event_hint": {
            "external_id": f"taskbounty:{task_id or slug}",
            "stage": "found",
            "amount_usd": 0,
            "proof_digest": proof_digest,
            "verifier_trace_digest": gate_state,
        },
    }


def build_taskbounty_scout(
    *,
    api_base: str | None = None,
    api_key: str | None = None,
    agent_id: str | None = None,
    limit: int = 20,
    include_details: bool = True,
    timeout: float = 20.0,
    fetch_json: FetchJson | None = None,
    tasks: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    _load_env()
    api_base_public = _normalize_api_base(api_base or os.getenv("TASKBOUNTY_API_BASE"))
    resolved_api_key = api_key if api_key is not None else os.getenv("TASKBOUNTY_API_KEY")
    resolved_agent_id = agent_id if agent_id is not None else os.getenv("TASKBOUNTY_AGENT_ID")
    api_key_present = bool((resolved_api_key or "").strip())
    agent_id_present = bool((resolved_agent_id or "").strip())
    fetch = fetch_json or _request_json
    errors: list[str] = []

    raw_tasks: list[dict[str, Any]] = []
    if tasks is not None:
        raw_tasks = list(tasks)
    elif api_key_present:
        try:
            raw_tasks = _as_list(fetch(f"{api_base_public}/tasks?status=OPEN", resolved_api_key, timeout))
        except Exception as exc:  # pragma: no cover - covered by live use, unit tests inject fetchers
            errors.append(f"task_list_fetch_failed:{type(exc).__name__}")
    else:
        errors.append("taskbounty_api_key_missing")

    clipped = raw_tasks[: max(0, int(limit or 0))]
    if include_details and tasks is None and api_key_present:
        detailed: list[dict[str, Any]] = []
        for item in clipped:
            task_id = _task_id(item)
            if not task_id:
                detailed.append(item)
                continue
            try:
                detail = fetch(f"{api_base_public}/tasks/{task_id}", resolved_api_key, timeout)
            except Exception:
                detailed.append(item)
                continue
            if isinstance(detail, dict):
                detailed.append(_merge_task_detail(item, detail))
            else:
                detailed.append(item)
        clipped = detailed

    classified = [
        classify_taskbounty_task(item, api_key_present=api_key_present, now=now)
        for item in clipped
    ]
    funded_open = [
        item
        for item in classified
        if item["status"] == "OPEN" and (not item["funding_status"] or item["funding_status"] == "FUNDED")
    ]
    work_candidates = [item for item in classified if item["gate_state"] == "candidate_submit_gate_unverified"]
    watch_only = [item for item in classified if not item["executable_work_allowed"]]
    blocked_pending = [item for item in classified if item["gate_state"] == "watch_only_pending_submission"]
    total_visible_usd = sum(float(item.get("amount_usd") or 0.0) for item in funded_open)

    summary = {
        "task_count": len(classified),
        "funded_open_count": len(funded_open),
        "work_candidate_count": len(work_candidates),
        "watch_only_count": len(watch_only),
        "blocked_pending_submission_count": len(blocked_pending),
        "total_visible_bounty_usd": round(total_visible_usd, 2),
        "top_candidate": work_candidates[0] if work_candidates else None,
        "top_watch": blocked_pending[0] if blocked_pending else (watch_only[0] if watch_only else None),
    }
    if work_candidates:
        machine_instruction = "probe_submission_gate_before_patch_work"
    elif blocked_pending:
        machine_instruction = "read_only_reconcile_wait_for_award_or_reopen"
    else:
        machine_instruction = "keep_channel_watch_only"

    return {
        "schema": "nomad.taskbounty_scout.v1",
        "ok": not errors,
        "generated_at": datetime.now(UTC).isoformat(),
        "api_base_public": api_base_public,
        "api_key_present": api_key_present,
        "agent_id_present": agent_id_present,
        "machine_instruction": machine_instruction,
        "summary": summary,
        "tasks": classified,
        "errors": errors,
    }


def probe_taskbounty_access_gate(
    task_id: str,
    *,
    api_base: str | None = None,
    api_key: str | None = None,
    agent_id: str | None = None,
    timeout: float = 20.0,
    post_json: PostJson | None = None,
) -> dict[str, Any]:
    _load_env()
    task_id = str(task_id or "").strip()
    api_base_public = _normalize_api_base(api_base or os.getenv("TASKBOUNTY_API_BASE"))
    resolved_api_key = api_key if api_key is not None else os.getenv("TASKBOUNTY_API_KEY")
    resolved_agent_id = agent_id if agent_id is not None else os.getenv("TASKBOUNTY_AGENT_ID")
    api_key_present = bool((resolved_api_key or "").strip())
    agent_id_present = bool((resolved_agent_id or "").strip())

    if not task_id:
        return {
            "schema": "nomad.taskbounty_access_gate.v1",
            "ok": False,
            "error": "task_id_required",
            "machine_instruction": "read_only_until_task_id_available",
        }
    if not api_key_present:
        return {
            "schema": "nomad.taskbounty_access_gate.v1",
            "ok": False,
            "task_id": task_id,
            "api_base_public": api_base_public,
            "api_key_present": False,
            "agent_id_present": agent_id_present,
            "gate_state": "api_key_missing",
            "blocked_actions": ["clone_for_patch", "push_branch", "open_pr", "submit_claim", "book_revenue"],
            "machine_instruction": "add_taskbounty_api_key_before_access_probe",
        }
    if not agent_id_present:
        return {
            "schema": "nomad.taskbounty_access_gate.v1",
            "ok": False,
            "task_id": task_id,
            "api_base_public": api_base_public,
            "api_key_present": True,
            "agent_id_present": False,
            "gate_state": "agent_id_missing",
            "blocked_actions": ["clone_for_patch", "push_branch", "open_pr", "submit_claim", "book_revenue"],
            "machine_instruction": "add_taskbounty_agent_id_before_access_probe",
        }

    poster = post_json or _post_json
    errors: list[str] = []
    raw: Any = {}
    cached = _cached_access_data(task_id, datetime.now(UTC)) if post_json is None else None
    if cached is not None:
        raw = {"data": cached}
        cache_hit = True
    else:
        cache_hit = False
        try:
            raw = poster(
                f"{api_base_public}/tasks/{task_id}/access",
                {"agent_id": resolved_agent_id},
                resolved_api_key,
                timeout,
            )
        except requests.HTTPError as exc:  # pragma: no cover - live HTTP failures vary
            status = exc.response.status_code if exc.response is not None else "unknown"
            errors.append(f"task_access_probe_failed:http_{status}")
            if status == 429:
                errors.append("task_access_grant_rate_limited")
        except Exception as exc:  # pragma: no cover - live HTTP failures vary
            errors.append(f"task_access_probe_failed:{type(exc).__name__}")

    data = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else {}
    if data and not cache_hit and post_json is None:
        _store_access_data(task_id, data)
    workflow = data.get("submissionWorkflow") if isinstance(data.get("submissionWorkflow"), list) else []
    workflow_text = "\n".join(str(item) for item in workflow)
    note = str(data.get("note") or "")
    combined = f"{workflow_text}\n{note}".lower()
    repo_url = str(data.get("repoUrl") or "")
    requires_upstream_pr = "upstream pr url" in combined or "pull request" in combined
    fork_required = "fork" in combined
    clone_token_read_only = "read-only" in combined or "read only" in combined
    external_link_required = "external_link" in combined
    direct_patch_submission_supported = any(
        token in combined
        for token in [
            "patch file",
            "git diff",
            "diff artifact",
            "upload patch",
            "patch_url",
        ]
    )

    if errors:
        gate_state = "rate_limited_access_probe" if "task_access_grant_rate_limited" in errors else "access_probe_failed"
        ok = False
        allowed_actions = ["read_only_watch"]
        blocked_actions = ["clone_for_patch", "push_branch", "open_pr", "submit_claim", "book_revenue"]
        machine_instruction = (
            "wait_for_cached_or_next_access_window_before_probe"
            if gate_state == "rate_limited_access_probe"
            else "do_not_patch_until_taskbounty_access_probe_succeeds"
        )
    elif requires_upstream_pr and clone_token_read_only and fork_required and not direct_patch_submission_supported:
        gate_state = "blocked_until_upstream_pr_access_confirmed"
        ok = True
        allowed_actions = [
            "local_patch_bundle",
            "read_only_test_verification",
            "upstream_pr_access_probe",
            "request_fork_or_collaborator_access",
        ]
        blocked_actions = ["push_branch", "open_pr", "submit_claim", "book_revenue"]
        machine_instruction = "hold_patch_bundle_no_claim_until_fork_or_branch_permission_exists"
    else:
        gate_state = "access_granted_submit_gate_unverified"
        ok = True
        allowed_actions = ["local_patch_bundle", "read_only_test_verification", "submission_schema_probe"]
        blocked_actions = ["submit_claim", "book_revenue"]
        machine_instruction = "verify_submission_schema_and_artifact_type_before_claim"

    return {
        "schema": "nomad.taskbounty_access_gate.v1",
        "ok": ok,
        "generated_at": datetime.now(UTC).isoformat(),
        "task_id": task_id,
        "api_base_public": api_base_public,
        "api_key_present": api_key_present,
        "agent_id_present": agent_id_present,
        "cache_hit": cache_hit,
        "gate_state": gate_state,
        "repo_url": repo_url,
        "access_expires_at": str(data.get("expiresAt") or ""),
        "submission_contract": {
            "requires_upstream_pr": requires_upstream_pr,
            "fork_required": fork_required,
            "clone_token_read_only": clone_token_read_only,
            "external_link_required": external_link_required,
            "direct_patch_submission_supported": direct_patch_submission_supported,
            "platform_submission_endpoint": f"{api_base_public}/submissions",
            "claimable_now": False,
        },
        "submission_workflow_redacted": _redact_secret_text(workflow),
        "note_redacted": _redact_secret_text(note),
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
        "unlock_requirements": [
            "upstream_pr_fork_or_branch_permission_confirmed",
            "upstream_pr_url_created_against_base_repo",
            "taskbounty_submission_response_accepted",
            "award_or_payment_receipt_before_revenue",
        ],
        "machine_instruction": machine_instruction,
        "errors": errors,
    }


__all__ = [
    "DEFAULT_TASKBOUNTY_API_BASE",
    "_normalize_api_base",
    "build_taskbounty_scout",
    "classify_taskbounty_task",
    "probe_taskbounty_access_gate",
]
