"""Machine-only adapter consent token mint/verify helpers."""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any
from urllib.parse import quote, unquote


def _secret() -> str:
    return str(os.getenv("NOMAD_ADAPTER_CONSENT_SECRET") or "nomad_adapter_consent_default").strip()


def _ttl_seconds() -> int:
    raw = str(os.getenv("NOMAD_ADAPTER_CONSENT_TTL_SECONDS") or "3600").strip()
    try:
        return max(60, min(86400, int(raw)))
    except ValueError:
        return 3600


def mint_adapter_consent(*, agent_id: str, runtime: str = "openclaw", now_ts: int | None = None) -> str:
    now = int(now_ts if now_ts is not None else time.time())
    exp = now + _ttl_seconds()
    aid = quote(str(agent_id or "").strip().lower() or "unknown_agent", safe="").replace(".", "%2E")
    rt = quote(str(runtime or "").strip().lower() or "openclaw", safe="").replace(".", "%2E")
    nonce = hashlib.sha256(f"{aid}:{rt}:{now}".encode("utf-8")).hexdigest()[:10]
    base = f"v1.{exp}.{aid}.{rt}.{nonce}"
    sig = hashlib.sha256(f"{base}.{_secret()}".encode("utf-8")).hexdigest()[:24]
    return f"{base}.{sig}"


def verify_adapter_consent(*, token: str, agent_id: str, runtime: str = "openclaw", now_ts: int | None = None) -> dict[str, Any]:
    t = str(token or "").strip()
    aid = str(agent_id or "").strip().lower()
    rt = str(runtime or "").strip().lower() or "openclaw"
    if not t:
        return {"ok": False, "reason": "missing_token"}
    parts = t.split(".")
    if len(parts) != 6 or parts[0] != "v1":
        return {"ok": False, "reason": "malformed_token"}
    _, exp_s, token_aid, token_rt, nonce, sig = parts
    try:
        exp = int(exp_s)
    except ValueError:
        return {"ok": False, "reason": "invalid_exp"}
    now = int(now_ts if now_ts is not None else time.time())
    if now > exp:
        return {"ok": False, "reason": "expired"}
    if unquote(token_aid) != aid:
        return {"ok": False, "reason": "agent_mismatch"}
    if unquote(token_rt) != rt:
        return {"ok": False, "reason": "runtime_mismatch"}
    base = f"v1.{exp}.{token_aid}.{token_rt}.{nonce}"
    want = hashlib.sha256(f"{base}.{_secret()}".encode("utf-8")).hexdigest()[:24]
    if sig != want:
        return {"ok": False, "reason": "bad_signature"}
    return {"ok": True, "reason": "ok", "expires_at": exp}


def adapter_consent_required(payload: dict[str, Any], *, path: str) -> bool:
    body = payload if isinstance(payload, dict) else {}
    if str(body.get("consent_token") or "").strip():
        return True
    runtime = str(body.get("runtime") or "").strip().lower()
    source_tag = str(body.get("source_tag") or "").strip().lower()
    requester = str(body.get("requester_agent_id") or "").strip().lower()
    worker = str(body.get("worker_agent_id") or "").strip().lower()
    agent = str(body.get("agent_id") or body.get("adapter_agent_id") or "").strip().lower()
    p = str(path or "").strip().lower()
    return bool(
        runtime == "openclaw"
        or "openclaw" in source_tag
        or "openclaw" in requester
        or "openclaw" in worker
        or "openclaw" in agent
        or p in {"/swarm/idle-intent", "/swarm/microtask/submit", "/swarm/microtask/settle"}
    )

