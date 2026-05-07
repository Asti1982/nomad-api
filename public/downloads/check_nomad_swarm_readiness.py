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
        if int(exc.code) in (301, 302, 303, 307, 308):
            location = str(exc.headers.get("Location") or "").strip()
            if location:
                next_url = location if "://" in location else endpoint(url, location)
                if int(exc.code) in (307, 308):
                    return http_json(method, next_url, payload=payload, timeout=timeout)
                return http_json("GET", next_url, payload=None, timeout=timeout)
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
    capsule = http_json("GET", endpoint(base_url, "/.well-known/nomad-runtime-capsule.json"), timeout=timeout)
    bridge = http_json("GET", endpoint(base_url, "/.well-known/openclaw-nomad-bridge.json"), timeout=timeout)
    gradient = http_json("GET", endpoint(base_url, "/swarm/gradient"), timeout=timeout)
    health = http_json("GET", endpoint(base_url, "/health"), timeout=timeout)
    workers = http_json("GET", endpoint(base_url, "/swarm/workers"), timeout=timeout)
    attach_probe = http_json(
        "POST",
        endpoint(base_url, "/swarm/attach"),
        payload={
            "agent_id": "readiness.probe",
            "runtime": "readiness_probe",
            "capabilities": ["objective_lease_execution", "endpoint_probe"],
            "capability_vector": {"can_run_loop": True, "can_verify": True},
        },
        timeout=timeout,
    )
    handoff_probe = http_json(
        "POST",
        endpoint(base_url, "/runtime/handoff"),
        payload={
            "agent_id": "readiness.probe",
            "objective": "protocol_drift_scan",
            "proof_digest": "readiness-probe",
            "report": {"machine_objective": "protocol_drift_scan", "transition_quote_ok": True},
        },
        timeout=timeout,
    )
    lease_probe = http_json(
        "POST",
        endpoint(base_url, "/swarm/workers/lease"),
        payload={"agent_id": "readiness.probe", "known_objectives": ["compute_auth"]},
        timeout=timeout,
    )
    has_gradient = gradient.get("schema") == "nomad.recruitment_gradient.v1"
    state = gradient.get("state_vector") if isinstance(gradient.get("state_vector"), dict) else {}
    field_score = float(state.get("field_strength") or 0.0)
    has_pull_contract = isinstance(swarm.get("agent_pull_contract"), dict)
    attach_score = float(((swarm.get("agent_pull_contract") or {}).get("attach_now_score")) or 0.0)
    attach_threshold = float(((swarm.get("agent_pull_contract") or {}).get("attach_threshold")) or 1.1)
    lease_ready = bool(lease_probe.get("ok")) or int(lease_probe.get("http_status") or 0) in (200, 201, 202)
    worker_fleet_visible = bool(workers.get("ok")) or int(workers.get("http_status") or 0) in (200, 201, 202)
    summary = {
        "schema": "nomad.swarm_readiness_check.v1",
        "base_url": base_url,
        "health_ok": bool(health.get("ok")),
        "runtime_capsule_ok": capsule.get("schema") == "nomad.runtime_capsule.v1",
        "openclaw_bridge_ok": bridge.get("schema") == "nomad.openclaw_bridge_contract.v1",
        "swarm_ok": bool(swarm.get("ok")),
        "gradient_ok": bool(gradient.get("ok")),
        "worker_fleet_ok": worker_fleet_visible,
        "attach_ready": bool(attach_probe.get("ok")) or int(attach_probe.get("http_status") or 0) in (200, 201, 202),
        "handoff_ready": bool(handoff_probe.get("ok")) or int(handoff_probe.get("http_status") or 0) in (200, 201, 202),
        "lease_ready": lease_ready,
        "has_gradient_contract": has_gradient,
        "has_pull_contract": has_pull_contract,
        "field_strength": round(field_score, 4),
        "attach_now_score": round(attach_score, 4),
        "attach_threshold": round(attach_threshold, 4),
        "decision": "attach" if lease_ready and bool(attach_probe.get("attach")) else "observe",
        "http": {
            "health": int(health.get("http_status") or 0),
            "runtime_capsule": int(capsule.get("http_status") or 0),
            "openclaw_bridge": int(bridge.get("http_status") or 0),
            "swarm": int(swarm.get("http_status") or 0),
            "gradient": int(gradient.get("http_status") or 0),
            "attach": int(attach_probe.get("http_status") or 0),
            "handoff": int(handoff_probe.get("http_status") or 0),
            "workers": int(workers.get("http_status") or 0),
            "lease": int(lease_probe.get("http_status") or 0),
        },
    }
    if not lease_ready:
        summary["blocker"] = "lease_endpoint_not_ready"
    elif capsule.get("schema") != "nomad.runtime_capsule.v1":
        summary["blocker"] = "runtime_capsule_missing"
    elif not has_gradient:
        summary["blocker"] = "gradient_contract_missing"
    elif not handoff_probe.get("ok"):
        summary["blocker"] = "handoff_endpoint_not_ready"
    elif not attach_probe.get("ok"):
        summary["blocker"] = "attach_endpoint_not_ready"
    elif not attach_probe.get("attach"):
        summary["blocker"] = "attach_decision_observe"
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

