#!/usr/bin/env python3
"""Nomad combined sustainability worker.

Stdlib-only worker that joins Nomad's three practical sustainability loops:

1. keep one external transition worker visible with a stable pseudonymous id
2. repay a real Work Exchange obligation with bounded public probes
3. submit an optional proof-backed machine-treasury pledge receipt

It intentionally does not create Reliability Doctor intakes, fake tx hashes,
hidden compute, Telegram spam, or referral outreach.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import secrets
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://www.syndiode.com"
DEFAULT_INTERVAL_SECONDS = 300.0
DEFAULT_TIMEOUT_SECONDS = 25.0
USER_AGENT = "NomadSustainabilityWorker/2026.05"


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: object, *, prefix: str = "sha256", length: int = 48) -> str:
    return f"{prefix}-{hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()[:length]}"


def endpoint(base_url: str, path: str) -> str:
    base = (base_url or DEFAULT_BASE_URL).strip().rstrip("/") + "/"
    return urljoin(base, path.lstrip("/"))


def http_json(method: str, base_url: str, path: str, payload: dict | None = None, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict:
    body = None
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if payload is not None:
        body = canonical(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["X-Correlation-ID"] = digest({"path": path, "payload": payload, "time": int(time.time())}, prefix="nsk", length=24)
    req = Request(endpoint(base_url, path), data=body, headers=headers, method=method.upper())
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                out = json.loads(raw)
            except json.JSONDecodeError:
                out = {"ok": False, "schema": "nomad.sustainability_worker_http_error.v1", "raw": raw[:1000]}
            if isinstance(out, dict):
                out.setdefault("http_status", getattr(response, "status", 0))
                return out
            return {"ok": False, "payload": out}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            out = {"ok": False, "error": "http_error", "message": raw[:1000]}
        if isinstance(out, dict):
            out["http_status"] = exc.code
            return out
        return {"ok": False, "http_status": exc.code}
    except (TimeoutError, URLError, OSError) as exc:
        return {
            "ok": False,
            "schema": "nomad.sustainability_worker_http_error.v1",
            "error": "request_failed",
            "message": str(exc)[:500],
            "path": path,
        }


def http_get_query(base_url: str, path: str, params: dict[str, str], *, timeout: float) -> dict:
    query = urlencode({k: v for k, v in params.items() if v != ""})
    return http_json("GET", base_url, f"{path}?{query}", timeout=timeout)


def stable_agent_id() -> str:
    configured = (os.getenv("NOMAD_SUSTAINABILITY_WORKER_ID") or os.getenv("NOMAD_AGENT_ID") or "").strip()
    if configured:
        return configured[:120]
    state_dir = Path.home() / ".nomad"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "sustainability_worker_id.txt"
    if state_path.exists():
        current = state_path.read_text(encoding="utf-8", errors="replace").strip()
        if current:
            return current[:120]
    generated = f"external.sustainability.{secrets.token_hex(6)}"
    state_path.write_text(generated, encoding="utf-8")
    return generated


def compact_probe(base_url: str, *, timeout: float) -> dict:
    checks = []
    for path in ("/health", "/.well-known/nomad-sustainability-kernel.json", "/.well-known/nomad-work-exchange.json"):
        started = time.time()
        out = http_json("GET", base_url, path, timeout=timeout)
        checks.append(
            {
                "path": path,
                "ok": bool(out.get("ok", False)),
                "schema": str(out.get("schema") or "")[:140],
                "http_status": int(out.get("http_status") or 0),
                "latency_ms": round((time.time() - started) * 1000.0, 2),
            }
        )
    return {
        "schema": "nomad.sustainability_worker_probe.v1",
        "generated_at": iso_now(),
        "checks": checks,
        "all_required_ok": all(item.get("ok") for item in checks[:2]),
    }


def external_heartbeat(base_url: str, agent_id: str, *, timeout: float) -> dict:
    return http_get_query(
        base_url,
        "/swarm/workers/lease-get",
        {
            "agent_id": agent_id,
            "runtime": "portable-sustainability-worker",
            "capabilities": "transition_worker,verifier,http_json,get_only,retention_heartbeat,sustainability_kernel",
            "known_objectives": "settlement_capacity_builder,proof_pressure_engine,protocol_drift_scan,external_worker_retention",
            "objective": "settlement_capacity_builder",
            "source_tag": "external_provider",
        },
        timeout=timeout,
    )


def balance(base_url: str, obligation_id: str, *, timeout: float) -> dict:
    return http_json("POST", base_url, "/swarm/work-exchange/balance", {"obligation_id": obligation_id}, timeout=timeout)


def outstanding_credits(snapshot: dict) -> float:
    obligation = snapshot.get("obligation") if isinstance(snapshot.get("obligation"), dict) else {}
    try:
        return max(0.0, float(obligation.get("outstanding_work_credits") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def run_return_compute(base_url: str, agent_id: str, obligation_id: str, *, work_credits: float, timeout: float) -> dict:
    before = balance(base_url, obligation_id, timeout=timeout)
    if not before.get("found"):
        return {"ok": False, "stop": True, "reason": "obligation_not_found", "balance": before}
    outstanding = outstanding_credits(before)
    if outstanding <= 0.0:
        return {"ok": True, "stop": True, "reason": "balance_settled", "balance": before}

    lease = http_json(
        "POST",
        base_url,
        "/swarm/workers/lease",
        {
            "agent_id": agent_id,
            "runtime": "nomad_sustainability_worker",
            "capabilities": ["return_compute", "public_probe", "http_json", "sustainability_kernel"],
            "objective": "return_compute_obligation",
            "obligation_id": obligation_id,
            "side_effect_scope": "sandboxed_worker_only",
        },
        timeout=timeout,
    )
    nested = lease.get("lease") if isinstance(lease.get("lease"), dict) else {}
    lease_id = str(lease.get("lease_id") or nested.get("lease_id") or lease.get("id") or nested.get("id") or "")[:160]
    probe = compact_probe(base_url, timeout=timeout)
    test_digest = digest({"probe": probe, "required": ["/health", "/.well-known/nomad-sustainability-kernel.json"]}, prefix="test")
    verifier_trace_digest = digest(
        {
            "balance_before": before.get("obligation", {}),
            "probe_schemas": [item.get("schema") for item in probe.get("checks", [])],
            "side_effect_scope": "sandboxed_worker_only",
        },
        prefix="trace",
    )
    proof_digest = digest(
        {
            "agent_id": agent_id,
            "obligation_id": obligation_id,
            "lease_id": lease_id,
            "probe": probe,
            "test_digest": test_digest,
            "verifier_trace_digest": verifier_trace_digest,
        },
        prefix="proof",
    )
    complete = http_json(
        "POST",
        base_url,
        "/swarm/workers/complete",
        {
            "agent_id": agent_id,
            "lease_id": lease_id,
            "objective": "return_compute_obligation",
            "status": "ok" if probe.get("all_required_ok") else "degraded",
            "digest": proof_digest,
            "proof_digest": proof_digest,
            "verifier_trace_digest": verifier_trace_digest,
            "test_digest": test_digest,
            "score": 1.0 if probe.get("all_required_ok") else 0.25,
            "source_tag": "external_provider",
            "side_effect_scope": "sandboxed_worker_only",
        },
        timeout=timeout,
    )
    returned = http_json(
        "POST",
        base_url,
        "/swarm/work-exchange/return-work",
        {
            "obligation_id": obligation_id,
            "worker_agent_id": agent_id,
            "lease_id": lease_id,
            "objective": "return_compute_obligation",
            "work_credits": min(max(0.0, float(work_credits)), outstanding),
            "proof_digest": proof_digest,
            "verifier_trace_digest": verifier_trace_digest,
            "test_digest": test_digest,
            "risk_score": 0.0,
        },
        timeout=timeout,
    )
    after = balance(base_url, obligation_id, timeout=timeout)
    return {
        "ok": bool(returned.get("accepted")),
        "stop": outstanding_credits(after) <= 0.0,
        "reason": "return_compute_receipt_recorded" if returned.get("accepted") else "return_compute_rejected",
        "lease_id": lease_id,
        "proof_digest": proof_digest,
        "complete": {"ok": complete.get("ok"), "schema": complete.get("schema"), "http_status": complete.get("http_status")},
        "return_work": returned,
        "balance_after": after.get("obligation", {}),
    }


def submit_pledge(args: argparse.Namespace, agent_id: str) -> dict:
    if args.pledge_amount_native <= 0:
        return {"ok": False, "error": "pledge_amount_native_required"}
    if not (args.pledge_proof_digest or args.pledge_settlement_ref):
        return {"ok": False, "error": "pledge_public_proof_required"}
    payload = {
        "agent_id": agent_id,
        "objective": args.pledge_objective,
        "amount_native": args.pledge_amount_native,
        "horizon_cycles": args.pledge_horizon_cycles,
        "intent": args.pledge_intent,
        "source_tag": "external_sustainability_worker",
        "proof_digest": args.pledge_proof_digest,
        "settlement_ref": args.pledge_settlement_ref,
        "idempotency_key": args.pledge_idempotency_key
        or digest(
            {
                "agent_id": agent_id,
                "objective": args.pledge_objective,
                "amount": args.pledge_amount_native,
                "proof": args.pledge_proof_digest,
                "settlement": args.pledge_settlement_ref,
            },
            prefix="pledge",
        ),
    }
    return http_json("POST", args.base_url, "/machine-treasury/pledge", payload, timeout=args.timeout)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Nomad's combined sustainability worker without fake utility or hidden compute.")
    parser.add_argument("--base-url", default=os.getenv("NOMAD_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--agent-id", default=os.getenv("NOMAD_AGENT_ID", ""))
    parser.add_argument("--heartbeat", action="store_true", help="Keep a pseudonymous external worker visible via get-only heartbeat.")
    parser.add_argument("--obligation-id", default=os.getenv("NOMAD_WORK_EXCHANGE_OBLIGATION_ID", ""))
    parser.add_argument("--work-credits", type=float, default=float(os.getenv("NOMAD_WORK_EXCHANGE_CREDITS_PER_CYCLE", "1.0") or "1.0"))
    parser.add_argument("--pledge-amount-native", type=float, default=0.0)
    parser.add_argument("--pledge-objective", default="settlement_capacity_builder")
    parser.add_argument("--pledge-horizon-cycles", type=int, default=24)
    parser.add_argument("--pledge-intent", default="proof_backed_compute_pressure")
    parser.add_argument("--pledge-proof-digest", default="")
    parser.add_argument("--pledge-settlement-ref", default="")
    parser.add_argument("--pledge-idempotency-key", default="")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--cycles", type=int, default=1, help="Use 0 with --loop for no fixed cycle limit.")
    parser.add_argument("--interval", type=float, default=float(os.getenv("NOMAD_SUSTAINABILITY_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS)))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("NOMAD_SUSTAINABILITY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    args.base_url = (args.base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    agent_id = (args.agent_id or stable_agent_id()).strip()[:120]
    pledge_done = False
    cycle = 0
    while True:
        cycle += 1
        result: dict[str, object] = {
            "ok": True,
            "schema": "nomad.sustainability_worker_cycle.v1",
            "cycle": cycle,
            "agent_id": agent_id,
            "generated_at": iso_now(),
        }
        if args.heartbeat:
            result["heartbeat"] = external_heartbeat(args.base_url, agent_id, timeout=args.timeout)
        if args.obligation_id:
            returned = run_return_compute(
                args.base_url,
                agent_id,
                args.obligation_id.strip(),
                work_credits=args.work_credits,
                timeout=args.timeout,
            )
            result["return_compute"] = returned
            if returned.get("stop"):
                print(json.dumps(result, ensure_ascii=True, sort_keys=True))
                return 0 if returned.get("ok") else 1
        if args.pledge_amount_native > 0 and not pledge_done:
            result["pledge"] = submit_pledge(args, agent_id)
            pledge_done = True
        if not (args.heartbeat or args.obligation_id or args.pledge_amount_native > 0):
            result["kernel"] = http_json("GET", args.base_url, "/.well-known/nomad-sustainability-kernel.json", timeout=args.timeout)
            print(json.dumps(result, ensure_ascii=True, sort_keys=True))
            return 0
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        if not args.loop:
            return 0
        if args.cycles > 0 and cycle >= args.cycles:
            return 0
        time.sleep(max(5.0, args.interval + random.uniform(-3.0, 3.0)))


if __name__ == "__main__":
    raise SystemExit(main())
