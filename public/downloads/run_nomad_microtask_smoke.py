#!/usr/bin/env python3
"""Run one autonomous microtask submit/settle cycle."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _post_json(url: str, payload: dict, timeout: float) -> dict:
    req = Request(
        url=url,
        method="POST",
        data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    with urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8", errors="replace") or "{}")


def run_cycle(*, base_url: str, lane_id: str, objective: str, price_eur: float, requester: str, worker: str, timeout: float) -> dict:
    submit_payload = {
        "lane_id": lane_id,
        "requester_agent_id": requester,
        "objective": objective,
        "price_eur": float(price_eur),
        "payload": {
            "kind": "smoke_probe",
            "generated_at": _iso_now(),
            "target": "https://www.syndiode.com/health",
        },
    }
    submit = _post_json(_u(base_url, "/swarm/microtask/submit"), submit_payload, timeout)
    settle = {}
    if bool(submit.get("accepted")) and str(submit.get("task_id") or "").strip():
        settle_payload = {
            "task_id": submit.get("task_id"),
            "worker_agent_id": worker,
            "objective": objective,
            "settled_price_eur": float(price_eur),
            "proof_digest": f"proof-{submit.get('task_id')}",
            "verifier_trace_digest": f"trace-{submit.get('task_id')}",
            "test_digest": f"test-{submit.get('task_id')}",
            "settlement_ref": f"smoke-{submit.get('task_id')}",
            "utility_delta": 0.01,
            "reuse_count": 1,
            "risk_score": 0.0,
        }
        settle = _post_json(_u(base_url, "/swarm/microtask/settle"), settle_payload, timeout)
    return {"submit": submit, "settle": settle}


def main() -> None:
    p = argparse.ArgumentParser(description="Run Nomad microtask submit/settle smoke cycle")
    p.add_argument("--base-url", default="https://www.syndiode.com")
    p.add_argument("--lane-id", default="endpoint_health_proof")
    p.add_argument("--objective", default="settlement_capacity_builder")
    p.add_argument("--price-eur", type=float, default=0.03)
    p.add_argument("--requester-agent-id", default="smoke.microtask.buyer")
    p.add_argument("--worker-agent-id", default="smoke.microtask.worker")
    p.add_argument("--timeout", type=float, default=20.0)
    args = p.parse_args()
    out = run_cycle(
        base_url=args.base_url,
        lane_id=args.lane_id,
        objective=args.objective,
        price_eur=args.price_eur,
        requester=args.requester_agent_id,
        worker=args.worker_agent_id,
        timeout=args.timeout,
    )
    print(json.dumps(out, ensure_ascii=True))


if __name__ == "__main__":
    main()

