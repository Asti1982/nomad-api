#!/usr/bin/env python3
"""Check whether a Nomad host is ready for autonomous external worker attachment."""

from __future__ import annotations

import argparse
import json
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


def check(base_url: str, timeout: float) -> dict:
    swarm = http_json("GET", endpoint(base_url, "/swarm"), timeout=timeout)
    health = http_json("GET", endpoint(base_url, "/health"), timeout=timeout)
    workers = http_json("GET", endpoint(base_url, "/swarm/workers"), timeout=timeout)
    lease_probe = http_json(
        "POST",
        endpoint(base_url, "/swarm/workers/lease"),
        payload={"agent_id": "readiness.probe", "known_objectives": ["compute_auth"]},
        timeout=timeout,
    )
    has_pull_contract = isinstance(swarm.get("agent_pull_contract"), dict)
    attach_score = float(((swarm.get("agent_pull_contract") or {}).get("attach_now_score")) or 0.0)
    attach_threshold = float(((swarm.get("agent_pull_contract") or {}).get("attach_threshold")) or 1.1)
    lease_ready = bool(lease_probe.get("ok"))
    worker_fleet_visible = bool(workers.get("ok"))
    summary = {
        "schema": "nomad.swarm_readiness_check.v1",
        "base_url": base_url,
        "health_ok": bool(health.get("ok")),
        "swarm_ok": bool(swarm.get("ok")),
        "worker_fleet_ok": worker_fleet_visible,
        "lease_ready": lease_ready,
        "has_pull_contract": has_pull_contract,
        "attach_now_score": round(attach_score, 4),
        "attach_threshold": round(attach_threshold, 4),
        "decision": "attach" if lease_ready and has_pull_contract and attach_score >= attach_threshold else "observe",
        "http": {
            "health": int(health.get("http_status") or 0),
            "swarm": int(swarm.get("http_status") or 0),
            "workers": int(workers.get("http_status") or 0),
            "lease": int(lease_probe.get("http_status") or 0),
        },
    }
    if not lease_ready:
        summary["blocker"] = "lease_endpoint_not_ready"
    elif not has_pull_contract:
        summary["blocker"] = "pull_contract_missing"
    elif attach_score < attach_threshold:
        summary["blocker"] = "attach_score_below_threshold"
    else:
        summary["blocker"] = ""
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="Check Nomad swarm readiness for external agent attachment")
    p.add_argument("--base-url", default="https://syndiode.com")
    p.add_argument("--timeout", type=float, default=12.0)
    args = p.parse_args()
    print(json.dumps(check(args.base_url, args.timeout), ensure_ascii=True))


if __name__ == "__main__":
    main()

