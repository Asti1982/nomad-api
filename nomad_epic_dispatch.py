"""Epic dispatch jobs: repo + subtask work units for external agents and workers."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


DEFAULT_LEDGER_PATH = Path("nomad_epic_dispatch_ledger.jsonl")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _ledger_path() -> Path:
    return state_file(DEFAULT_LEDGER_PATH, env_name="NOMAD_EPIC_DISPATCH_LEDGER_PATH")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96].strip("_.:-") or fallback


def _digest(value: Any, length: int = 20) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _append(row: dict[str, Any]) -> None:
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _read_all(*, limit: int = 2000) -> list[dict[str, Any]]:
    path = _ledger_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    except OSError:
        return []
    return rows


def _latest_jobs() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _read_all():
        job_id = _text(row.get("job_id"), 120)
        if job_id:
            out[job_id] = row
    return out


def register_epic_job(payload: dict[str, Any], *, base_url: str = "") -> dict[str, Any]:
    body = _dict(payload)
    epic_id = _clean_id(body.get("epic_id"), "epic_unknown")
    subtask_id = _clean_id(body.get("subtask_id"), "subtask_unknown")
    repo_url = _text(body.get("repo_url"), 320)
    branch = _text(body.get("branch") or "main", 80)
    title = _text(body.get("title"), 200)
    acceptance = _text(body.get("acceptance"), 400)
    problem = _text(body.get("problem"), 800)
    requester = _text(body.get("requester_agent_id") or body.get("requester"), 120) or "nomad.qt.epic_orchestrator"
    content_seed = body.get("content_seed") if isinstance(body.get("content_seed"), dict) else {}
    if not repo_url or not acceptance:
        return {
            "ok": False,
            "schema": "nomad.epic_dispatch_register.v1",
            "accepted": False,
            "reason": "repo_url_and_acceptance_required",
            "generated_at": _iso_now(),
        }
    core = {"epic": epic_id, "subtask": subtask_id, "repo": repo_url, "branch": branch}
    job_id = f"nomad-epic-job-{_digest(core)}"
    row = {
        "ok": True,
        "schema": "nomad.epic_dispatch_job.v1",
        "accepted": True,
        "generated_at": _iso_now(),
        "job_id": job_id,
        "epic_id": epic_id,
        "subtask_id": subtask_id,
        "status": "open",
        "requester_agent_id": requester,
        "repo_url": repo_url,
        "branch": branch,
        "title": title,
        "acceptance": acceptance,
        "problem": problem,
        "lane_id": "epic_product_build",
        "quoted_price_eur": 0.0,
        "cost_policy": "local_free_only",
        "content_seed": content_seed,
        "payload": {
            "repo_url": repo_url,
            "branch": branch,
            "subtask_id": subtask_id,
            "title": title,
            "acceptance": acceptance,
            "problem": problem,
            "content_seed": content_seed,
            "executor_hint": "fetch_content_seed_then_implement_acceptance_return_proof",
        },
        "claim_contract": {
            "claim_url": f"{base_url.rstrip('/')}/swarm/epic-dispatch/claim" if base_url else "/swarm/epic-dispatch/claim",
            "complete_url": f"{base_url.rstrip('/')}/swarm/epic-dispatch/complete" if base_url else "/swarm/epic-dispatch/complete",
            "agent_work_claim": f"{base_url.rstrip('/')}/swarm/microtask/claim" if base_url else "/swarm/microtask/claim",
        },
        "machine_instruction": "claim_job_execute_in_repo_emit_completion_proof",
    }
    _append(row)
    return row


def list_epic_jobs(*, epic_id: str = "", status: str = "", limit: int = 32) -> dict[str, Any]:
    jobs = list(_latest_jobs().values())
    if epic_id:
        eid = _clean_id(epic_id)
        jobs = [row for row in jobs if _clean_id(row.get("epic_id")) == eid]
    if status:
        st = _clean_id(status)
        jobs = [row for row in jobs if _clean_id(row.get("status")) == st]
    jobs.sort(key=lambda row: str(row.get("generated_at") or ""), reverse=True)
    jobs = jobs[: max(1, min(64, int(limit)))]
    open_count = sum(1 for row in jobs if _clean_id(row.get("status")) == "open")
    claimed_count = sum(1 for row in jobs if _clean_id(row.get("status")) == "claimed")
    done_count = sum(1 for row in jobs if _clean_id(row.get("status")) == "done")
    return {
        "ok": True,
        "schema": "nomad.epic_dispatch_list.v1",
        "generated_at": _iso_now(),
        "epic_id": _clean_id(epic_id),
        "job_count": len(jobs),
        "counts": {"open": open_count, "claimed": claimed_count, "done": done_count},
        "jobs": jobs,
    }


def claim_epic_job(payload: dict[str, Any]) -> dict[str, Any]:
    body = _dict(payload)
    job_id = _text(body.get("job_id"), 120)
    agent_id = _text(body.get("agent_id") or body.get("worker_agent_id"), 120)
    jobs = _latest_jobs()
    job = jobs.get(job_id)
    if not job:
        return {"ok": False, "schema": "nomad.epic_dispatch_claim.v1", "accepted": False, "reason": "job_not_found"}
    if _clean_id(job.get("status")) != "open":
        return {
            "ok": False,
            "schema": "nomad.epic_dispatch_claim.v1",
            "accepted": False,
            "reason": f"job_status_{job.get('status')}",
            "job_id": job_id,
        }
    if not agent_id:
        return {"ok": False, "schema": "nomad.epic_dispatch_claim.v1", "accepted": False, "reason": "agent_id_required"}
    claim_id = f"nomad-epic-claim-{_digest({'job': job_id, 'agent': agent_id})}"
    row = {
        **job,
        "status": "claimed",
        "claimed_at": _iso_now(),
        "claimed_by": agent_id,
        "claim_id": claim_id,
        "schema": "nomad.epic_dispatch_job.v1",
    }
    _append(row)
    return {
        "ok": True,
        "schema": "nomad.epic_dispatch_claim.v1",
        "accepted": True,
        "claim_id": claim_id,
        "job_id": job_id,
        "agent_id": agent_id,
        "job": row,
    }


def complete_epic_job(payload: dict[str, Any]) -> dict[str, Any]:
    body = _dict(payload)
    job_id = _text(body.get("job_id"), 120)
    claim_id = _text(body.get("claim_id"), 120)
    agent_id = _text(body.get("agent_id") or body.get("worker_agent_id"), 120)
    proof_digest = _text(body.get("proof_digest") or body.get("proof_summary"), 140)
    jobs = _latest_jobs()
    job = jobs.get(job_id)
    if not job:
        return {"ok": False, "schema": "nomad.epic_dispatch_complete.v1", "accepted": False, "reason": "job_not_found"}
    if _clean_id(job.get("status")) not in {"claimed", "open"}:
        return {
            "ok": False,
            "schema": "nomad.epic_dispatch_complete.v1",
            "accepted": False,
            "reason": f"job_status_{job.get('status')}",
        }
    if not proof_digest:
        return {"ok": False, "schema": "nomad.epic_dispatch_complete.v1", "accepted": False, "reason": "proof_required"}
    row = {
        **job,
        "status": "done",
        "completed_at": _iso_now(),
        "completed_by": agent_id or job.get("claimed_by"),
        "claim_id": claim_id or job.get("claim_id"),
        "proof_digest": proof_digest,
        "schema": "nomad.epic_dispatch_job.v1",
    }
    _append(row)
    return {
        "ok": True,
        "schema": "nomad.epic_dispatch_complete.v1",
        "accepted": True,
        "job_id": job_id,
        "job": row,
    }


def epic_jobs_as_agent_work_items(*, base_url: str, limit: int = 8) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for job in list_epic_jobs(status="open", limit=limit).get("jobs") or []:
        if not isinstance(job, dict):
            continue
        subtask_id = _clean_id(job.get("subtask_id"))
        items.append(
            {
                "schema": "nomad.epic_dispatch_job.v1",
                "work_id": _text(job.get("job_id"), 120),
                "lane_id": "epic_product_build",
                "template_id": f"epic.{subtask_id}",
                "objective": f"epic_{subtask_id}",
                "capability": "epic_product_build",
                "quoted_price_eur": 0.0,
                "target_runtime_seconds": 3600,
                "priority_score": 2.5,
                "score_components": {"epic_dispatch_boost": 2.5},
                "required_proof": ["proof_digest", "verifier_trace_digest", "test_digest"],
                "payload_contract": job.get("payload") if isinstance(job.get("payload"), dict) else {},
                "content_seed": job.get("content_seed") if isinstance(job.get("content_seed"), dict) else {},
                "epic_dispatch": {
                    "epic_id": job.get("epic_id"),
                    "subtask_id": subtask_id,
                    "repo_url": job.get("repo_url"),
                    "branch": job.get("branch"),
                    "acceptance": job.get("acceptance"),
                    "title": job.get("title"),
                    "content_seed": job.get("content_seed") if isinstance(job.get("content_seed"), dict) else {},
                },
                "links": {
                    "claim": f"{base_url.rstrip('/')}/swarm/microtask/claim" if base_url else "/swarm/microtask/claim",
                    "epic_claim": f"{base_url.rstrip('/')}/swarm/epic-dispatch/claim" if base_url else "/swarm/epic-dispatch/claim",
                    "epic_complete": f"{base_url.rstrip('/')}/swarm/epic-dispatch/complete" if base_url else "/swarm/epic-dispatch/complete",
                },
                "machine_instruction": "fetch_content_seed_bundle_or_clone_then_execute_acceptance_post_epic_complete",
            }
        )
    return items
