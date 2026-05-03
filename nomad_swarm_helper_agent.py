"""Outbound helper that probes Nomad's public API and optionally joins the swarm (connects the network)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

import requests

from nomad_public_url import preferred_public_base_url


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _base_url(explicit: str = "") -> str:
    raw = (explicit or os.getenv("NOMAD_PUBLIC_API_URL") or "").strip().rstrip("/")
    if raw and "127.0.0.1" not in raw and "localhost" not in raw.lower():
        return raw
    pub = (preferred_public_base_url() or "").strip().rstrip("/")
    if pub and "127.0.0.1" not in pub and "localhost" not in pub.lower():
        return pub
    return "https://syndiode.com/nomad"


def _get(session: requests.Session, url: str, *, timeout: float) -> Dict[str, Any]:
    try:
        r = session.get(url, timeout=timeout)
        body: Any
        try:
            body = r.json()
        except Exception:
            body = {"raw": (r.text or "")[:400]}
        return {"ok": r.ok, "status": r.status_code, "url": url, "body": body}
    except Exception as exc:
        return {"ok": False, "status": 0, "url": url, "error": str(exc), "body": None}


def _post_json(
    session: requests.Session,
    url: str,
    payload: Dict[str, Any],
    *,
    timeout: float,
    idempotency_key: str,
) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Idempotency-Key": idempotency_key,
    }
    try:
        r = session.post(url, json=payload, headers=headers, timeout=timeout)
        body: Any
        try:
            body = r.json()
        except Exception:
            body = {"raw": (r.text or "")[:600]}
        return {"ok": r.ok, "status": r.status_code, "url": url, "body": body}
    except Exception as exc:
        return {"ok": False, "status": 0, "url": url, "error": str(exc), "body": None}


def run_swarm_helper_pass(
    *,
    base_url: str = "",
    dry_run: bool = True,
    post_join: bool = False,
    post_develop: bool = False,
    timeout: float = 25.0,
    agent_id: str = "",
) -> Dict[str, Any]:
    """
    Machine-first pass: read health + swarm + join contract; optionally POST join/develop.
    When dry_run is True, no mutating POST is sent (only GET probes).
    """
    root = _base_url(base_url)
    session = requests.Session()
    idem = f"swarm-helper-{uuid.uuid4().hex[:24]}"
    aid = (agent_id or os.getenv("NOMAD_SWARM_HELPER_AGENT_ID") or "nomad.swarm_helper.v1").strip()

    probes: List[Dict[str, Any]] = []
    for path in (
        "/health",
        "/swarm",
        "/swarm/join",
        "/.well-known/agent-card.json",
        "/openapi.json",
        "/.well-known/nomad-agent.json",
        "/swarm/accumulate",
        "/mission",
    ):
        probes.append(_get(session, f"{root}{path}", timeout=timeout))

    join_result: Optional[Dict[str, Any]] = None
    develop_result: Optional[Dict[str, Any]] = None

    if not dry_run and post_join:
        join_payload = {
            "agent_id": aid,
            "node_name": aid,
            "capabilities": ["runtime_patterns", "debugging", "agent_protocols"],
            "request": (
                "Swarm helper: offer bounded health probes, join idempotency checks, "
                "and public evidence for Nomad network growth."
            ),
            "reciprocity": "Can POST structured machine signals to /aid when verified; no human impersonation.",
            "idempotency_key": idem,
        }
        join_result = _post_json(session, f"{root}/swarm/join", join_payload, timeout=timeout, idempotency_key=idem)

    if not dry_run and post_develop:
        dev_idem = f"swarm-helper-dev-{uuid.uuid4().hex[:20]}"
        develop_payload = {
            "agent_id": aid,
            "problem": (
                "Nomad swarm-helper: confirm develop exchange accepts bounded agent_id + problem; "
                "no secrets in payload."
            ),
            "pain_type": "self_improvement",
            "capabilities": ["debugging"],
            "evidence": ["SOURCE=nomad_swarm_helper_agent", f"PUBLIC_BASE={root}"],
            "idempotency_key": dev_idem,
        }
        develop_result = _post_json(
            session,
            f"{root}/swarm/develop",
            develop_payload,
            timeout=timeout,
            idempotency_key=dev_idem,
        )

    ok_reads = sum(1 for p in probes if p.get("ok"))
    return {
        "mode": "nomad_swarm_helper_pass",
        "schema": "nomad.swarm_helper_pass.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "dry_run": bool(dry_run),
        "post_join_requested": bool(post_join),
        "post_develop_requested": bool(post_develop),
        "agent_id": aid,
        "idempotency_key_join": idem if post_join and not dry_run else "",
        "probe_ok_count": ok_reads,
        "probes": probes,
        "swarm_join_post": join_result,
        "swarm_develop_post": develop_result,
        "analysis": (
            f"Probes: {ok_reads}/{len(probes)} GETs succeeded. "
            f"Join POST: {'sent' if join_result else 'skipped'}. "
            f"Develop POST: {'sent' if develop_result else 'skipped'}."
        ),
    }
