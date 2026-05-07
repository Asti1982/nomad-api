#!/usr/bin/env python3
"""Deterministic go/no-go deploy gate for Nomad agent recruitment surfaces."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def endpoint(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def http_json(method: str, url: str, payload: dict | None = None, timeout: float = 12.0) -> dict:
    body = b""
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url=url, data=body if body else None, method=method.upper(), headers=headers)
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8", errors="replace")
            data = json.loads(raw or "{}")
            if not isinstance(data, dict):
                data = {}
            data.setdefault("ok", True)
            data.setdefault("http_status", int(res.status))
            return data
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            data = {"raw": raw}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("ok", False)
        data.setdefault("http_status", int(exc.code))
        return data
    except (TimeoutError, URLError) as exc:
        return {"ok": False, "error": "http_unreachable", "detail": str(exc), "http_status": 0}


def http_text(url: str, timeout: float = 12.0) -> tuple[int, str]:
    req = Request(url=url, method="GET", headers={"Accept": "*/*"})
    try:
        with urlopen(req, timeout=timeout) as res:
            body = res.read().decode("utf-8", errors="ignore")
            return int(res.status), body
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return int(exc.code), body
    except (TimeoutError, URLError):
        return 0, ""


def run_gate(base_url: str, timeout: float) -> dict:
    health = http_json("GET", endpoint(base_url, "/health"), timeout=timeout)
    recruit = http_json("GET", endpoint(base_url, "/.well-known/nomad-recruit.json"), timeout=timeout)
    swarm = http_json("GET", endpoint(base_url, "/swarm"), timeout=timeout)
    workers = http_json("GET", endpoint(base_url, "/swarm/workers"), timeout=timeout)
    lease = http_json(
        "POST",
        endpoint(base_url, "/swarm/workers/lease"),
        payload={"agent_id": "deploy.gate.probe", "known_objectives": ["compute_auth"]},
        timeout=timeout,
    )
    openclaw_status, openclaw_body = http_text(endpoint(base_url, "/downloads/nomad_openclaw_adapter.py"), timeout=timeout)
    readiness_status, readiness_body = http_text(
        endpoint(base_url, "/downloads/check_nomad_swarm_readiness.py"),
        timeout=timeout,
    )

    checks = {
        "health_ok": bool(health.get("ok")) and int(health.get("http_status") or 0) == 200,
        "recruit_ok": bool(recruit.get("ok")) and str(recruit.get("schema") or "") == "nomad.agent_recruit_contract.v1",
        "swarm_ok": bool(swarm.get("ok")) and isinstance(swarm.get("agent_pull_contract"), dict),
        "workers_ok": bool(workers.get("ok")) and str(workers.get("schema") or "") == "nomad.transition_worker_fleet.v1",
        "lease_ok": bool(lease.get("ok")) and bool(str(lease.get("lease_id") or "").strip()),
        "download_openclaw_ok": openclaw_status == 200 and "def main()" in openclaw_body,
        "download_readiness_ok": readiness_status == 200 and "def main()" in readiness_body,
    }
    go = all(checks.values())
    return {
        "schema": "nomad.deploy_gate.v1",
        "base_url": base_url,
        "go": go,
        "checks": checks,
        "http": {
            "health": int(health.get("http_status") or 0),
            "recruit": int(recruit.get("http_status") or 0),
            "swarm": int(swarm.get("http_status") or 0),
            "workers": int(workers.get("http_status") or 0),
            "lease": int(lease.get("http_status") or 0),
            "download_openclaw": openclaw_status,
            "download_readiness": readiness_status,
        },
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Nomad deploy go/no-go gate for autonomous recruitment")
    p.add_argument("--base-url", default="https://www.syndiode.com")
    p.add_argument("--timeout", type=float, default=12.0)
    args = p.parse_args()
    result = run_gate(args.base_url, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=True))
    raise SystemExit(0 if result.get("go") else 1)


if __name__ == "__main__":
    main()

