#!/usr/bin/env python3
"""Ollama idle bridge: auto-switch idle local capacity into Nomad swarm."""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen


def clean(v: object, limit: int = 320) -> str:
    return " ".join(str(v or "").split())[:limit]


def endpoint(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def http_json(method: str, url: str, payload: dict | None = None, timeout: float = 15.0) -> dict:
    body = b""
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url=url, data=body if body else None, method=method.upper(), headers=headers)
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8", errors="replace")
            doc = json.loads(raw or "{}")
            if isinstance(doc, dict):
                return doc
            return {"ok": False, "error": "invalid_json_shape"}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            doc = json.loads(raw or "{}")
        except json.JSONDecodeError:
            doc = {}
        if not isinstance(doc, dict):
            doc = {}
        doc.setdefault("ok", False)
        doc.setdefault("http_status", int(exc.code))
        return doc
    except (TimeoutError, URLError) as exc:
        return {"ok": False, "error": "http_unreachable", "detail": clean(exc, 180)}


def default_agent_id() -> str:
    host = socket.gethostname().replace(" ", "-").lower()
    return f"ollama-idle-bridge.{host}.nomad"


def _consent_token(*, agent_id: str, runtime: str = "ollama") -> str:
    now = int(time.time())
    exp = now + 3600
    aid = quote(clean(agent_id, 80).lower() or "unknown_agent", safe="").replace(".", "%2E")
    rt = quote(clean(runtime, 32).lower() or "ollama", safe="").replace(".", "%2E")
    nonce = hashlib.sha256(f"{aid}:{rt}:{now}".encode("utf-8")).hexdigest()[:10]
    base = f"v1.{exp}.{aid}.{rt}.{nonce}"
    sig = hashlib.sha256(f"{base}.nomad_adapter_consent_default".encode("utf-8")).hexdigest()[:24]
    return f"{base}.{sig}"


def ollama_busy(*, ollama_url: str, timeout: float = 5.0) -> dict:
    status = http_json("GET", endpoint(ollama_url, "/api/ps"), timeout=timeout)
    models = status.get("models") if isinstance(status.get("models"), list) else []
    busy = len(models) > 0
    return {"ok": True, "busy": busy, "model_count": len(models), "models": models[:8]}


def run_idle_offload_cycle(*, base_url: str, ollama_url: str, agent_id: str, timeout: float = 10.0) -> dict:
    busy = ollama_busy(ollama_url=ollama_url, timeout=min(5.0, timeout))
    if busy.get("busy"):
        return {
            "ok": True,
            "schema": "nomad.ollama_idle_bridge_cycle.v1",
            "state": "owner_priority_active",
            "machine_instruction": "ollama_is_active_keep_local_capacity",
            "next": [{"rel": "recheck_idle", "in_seconds": 20}],
        }
    consent = _consent_token(agent_id=agent_id, runtime="ollama")
    switch = http_json(
        "POST",
        endpoint(base_url, "/swarm/capacity-switch"),
        {
            "adapter_agent_id": agent_id,
            "runtime": "ollama",
            "consent_token": consent,
            "local_token_balance": 0.0,
            "min_token_threshold": 1.0,
            "local_capacity_utilization": 0.0,
            "objective": "settlement_capacity_builder",
        },
        timeout=timeout,
    )
    if not bool(switch.get("switch")):
        return {
            "ok": True,
            "schema": "nomad.ollama_idle_bridge_cycle.v1",
            "state": "observe_local",
            "capacity_switch": switch,
            "machine_instruction": "no_swarm_switch_required_retry_later",
            "next": [{"rel": "capacity_switch", "href": endpoint(base_url, "/swarm/capacity-switch"), "method": "POST"}],
        }
    idle_intent = http_json(
        "POST",
        endpoint(base_url, "/swarm/idle-intent"),
        {
            "schema": "nomad.idle_runtime_intent.v1",
            "agent_id": agent_id,
            "runtime": "ollama",
            "adapter_agent_id": agent_id,
            "consent_token": consent,
            "capabilities": ["ollama_inference", "idle_compute_offload", "objective_lease_execution"],
            "idle_opt_in": {"enabled": True, "preemptible": True, "max_runtime_minutes": 20},
            "seeking": {"mode": "new_objective_or_idle_work", "accept_noop": True},
        },
        timeout=timeout,
    )
    return {
        "ok": True,
        "schema": "nomad.ollama_idle_bridge_cycle.v1",
        "state": "swarm_idle_attached" if idle_intent.get("accepted_for_work") else "swarm_idle_waiting",
        "capacity_switch": switch,
        "idle_intent": idle_intent,
        "machine_instruction": "when_ollama_idle_keep_participating_in_nomad_swarm",
        "next": [
            {"rel": "idle_intent", "href": endpoint(base_url, "/swarm/idle-intent"), "method": "POST"},
            {"rel": "capacity_switch", "href": endpoint(base_url, "/swarm/capacity-switch"), "method": "POST"},
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Auto-connect idle Ollama capacity to Nomad swarm")
    p.add_argument("--base-url", default="https://www.syndiode.com")
    p.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    p.add_argument("--agent-id", default=default_agent_id())
    p.add_argument("--loop", action="store_true")
    p.add_argument("--cycles", type=int, default=1)
    p.add_argument("--interval", type=float, default=20.0)
    p.add_argument("--timeout", type=float, default=10.0)
    a = p.parse_args()

    count = 0
    while True:
        count += 1
        out = run_idle_offload_cycle(
            base_url=a.base_url,
            ollama_url=a.ollama_url,
            agent_id=a.agent_id,
            timeout=a.timeout,
        )
        out["cycle"] = count
        print(json.dumps(out, ensure_ascii=True))
        if not a.loop and count >= max(1, a.cycles):
            break
        if a.loop and a.cycles > 0 and count >= a.cycles:
            break
        time.sleep(max(3.0, a.interval))


if __name__ == "__main__":
    main()

