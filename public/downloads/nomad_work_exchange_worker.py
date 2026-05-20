#!/usr/bin/env python3
"""Nomad Work Exchange return-compute worker.

Stdlib-only, obligation-bound worker for the token-free Work Exchange:

    free solution -> compute obligation -> verified return work -> balance zero

The worker is intentionally conservative. It does not execute untrusted code,
does not read local secrets, and exits automatically when the obligation balance
is settled.
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
from urllib.parse import urljoin
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://www.syndiode.com"
DEFAULT_INTERVAL_SECONDS = 45.0
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_WORK_CREDITS = 1.0
USER_AGENT = "NomadWorkExchangeWorker/2026.05"


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


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
        headers["X-Correlation-ID"] = digest({"path": path, "payload": payload, "time": int(time.time())}, prefix="nwe", length=24)
    req = Request(endpoint(base_url, path), data=body, headers=headers, method=method.upper())
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                out = json.loads(raw)
            except json.JSONDecodeError:
                out = {"ok": False, "schema": "nomad.work_exchange_worker_http_error.v1", "raw": raw[:1000]}
            if isinstance(out, dict):
                out.setdefault("http_status", getattr(response, "status", 0))
            return out if isinstance(out, dict) else {"ok": False, "payload": out}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            out = {"ok": False, "error": "http_error", "message": raw[:1000]}
        if isinstance(out, dict):
            out["http_status"] = exc.code
        return out if isinstance(out, dict) else {"ok": False, "http_status": exc.code}
    except (TimeoutError, URLError, OSError) as exc:
        return {
            "ok": False,
            "schema": "nomad.work_exchange_worker_http_error.v1",
            "error": "request_failed",
            "message": str(exc)[:500],
            "path": path,
        }


def stable_agent_id() -> str:
    configured = (os.getenv("NOMAD_WORK_EXCHANGE_WORKER_ID") or os.getenv("NOMAD_AGENT_ID") or "").strip()
    if configured:
        return configured[:120]
    state_dir = Path.home() / ".nomad"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "work_exchange_worker_id.txt"
    if state_path.exists():
        current = state_path.read_text(encoding="utf-8", errors="replace").strip()
        if current:
            return current[:120]
    generated = f"nomad.work_exchange.{secrets.token_hex(6)}"
    state_path.write_text(generated, encoding="utf-8")
    return generated


def compact_probe(base_url: str, *, timeout: float) -> dict:
    checks = []
    for path in ("/health", "/.well-known/nomad-work-exchange.json", "/swarm/workers"):
        started = time.time()
        out = http_json("GET", base_url, path, timeout=timeout)
        checks.append(
            {
                "path": path,
                "ok": bool(out.get("ok", False)),
                "schema": str(out.get("schema") or "")[:120],
                "http_status": int(out.get("http_status") or 0),
                "latency_ms": round((time.time() - started) * 1000.0, 2),
            }
        )
    return {
        "schema": "nomad.work_exchange_worker_probe.v1",
        "generated_at": iso_now(),
        "checks": checks,
        "all_required_ok": all(item.get("ok") for item in checks[:2]),
    }


def extract_lease_id(lease: dict) -> str:
    nested = lease.get("lease") if isinstance(lease.get("lease"), dict) else {}
    for value in (
        lease.get("lease_id"),
        lease.get("id"),
        nested.get("lease_id"),
        nested.get("id"),
        lease.get("task_id"),
    ):
        if value:
            return str(value)[:160]
    return ""


def extract_objective(lease: dict) -> str:
    nested = lease.get("lease") if isinstance(lease.get("lease"), dict) else {}
    return str(
        lease.get("objective")
        or lease.get("assigned_objective")
        or nested.get("objective")
        or nested.get("assigned_objective")
        or "return_compute_obligation"
    )[:120]


def read_balance(base_url: str, obligation_id: str, *, timeout: float) -> dict:
    return http_json(
        "POST",
        base_url,
        "/swarm/work-exchange/balance",
        {"obligation_id": obligation_id},
        timeout=timeout,
    )


def outstanding_credits(balance: dict) -> float:
    obligation = balance.get("obligation") if isinstance(balance.get("obligation"), dict) else {}
    try:
        return max(0.0, float(obligation.get("outstanding_work_credits") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def run_one_cycle(args: argparse.Namespace, agent_id: str) -> dict:
    balance = read_balance(args.base_url, args.obligation_id, timeout=args.timeout)
    if not balance.get("found"):
        return {
            "ok": False,
            "schema": "nomad.work_exchange_worker_cycle.v1",
            "stop": True,
            "reason": "obligation_not_found",
            "balance": balance,
        }
    outstanding = outstanding_credits(balance)
    if outstanding <= 0.0:
        return {
            "ok": True,
            "schema": "nomad.work_exchange_worker_cycle.v1",
            "stop": True,
            "reason": "balance_settled",
            "balance": balance,
        }

    lease_payload = {
        "agent_id": agent_id,
        "runtime": "nomad_work_exchange_worker",
        "capabilities": [
            "return_compute",
            "http_json",
            "public_probe",
            "proof_digest",
            "sandboxed_worker_only",
        ],
        "objective": "return_compute_obligation",
        "known_objectives": [
            "return_compute_obligation",
            "settlement_capacity_builder",
            "proof_pressure_engine",
        ],
        "obligation_id": args.obligation_id,
        "side_effect_scope": "sandboxed_worker_only",
        "max_runtime_seconds": int(max(5, args.timeout * 3)),
    }
    lease = http_json("POST", args.base_url, "/swarm/workers/lease", lease_payload, timeout=args.timeout)
    lease_id = extract_lease_id(lease)
    objective = extract_objective(lease)
    probe = compact_probe(args.base_url, timeout=args.timeout)
    test_digest = digest({"probe": probe, "required": ["/health", "/.well-known/nomad-work-exchange.json"]}, prefix="test")
    verifier_trace_digest = digest(
        {
            "balance_before": balance.get("obligation", {}),
            "probe_schemas": [item.get("schema") for item in probe.get("checks", [])],
            "side_effect_scope": "sandboxed_worker_only",
        },
        prefix="trace",
    )
    proof_digest = digest(
        {
            "agent_id": agent_id,
            "obligation_id": args.obligation_id,
            "lease_id": lease_id,
            "objective": objective,
            "probe": probe,
            "test_digest": test_digest,
            "verifier_trace_digest": verifier_trace_digest,
        },
        prefix="proof",
    )
    complete_payload = {
        "agent_id": agent_id,
        "lease_id": lease_id,
        "objective": objective,
        "status": "ok" if probe.get("all_required_ok") else "degraded",
        "digest": proof_digest,
        "proof_digest": proof_digest,
        "verifier_trace_digest": verifier_trace_digest,
        "test_digest": test_digest,
        "score": 1.0 if probe.get("all_required_ok") else 0.25,
        "side_effect_scope": "sandboxed_worker_only",
        "note": "work_exchange_return_compute_probe",
    }
    complete = http_json("POST", args.base_url, "/swarm/workers/complete", complete_payload, timeout=args.timeout)
    return_work = http_json(
        "POST",
        args.base_url,
        "/swarm/work-exchange/return-work",
        {
            "obligation_id": args.obligation_id,
            "worker_agent_id": agent_id,
            "lease_id": lease_id,
            "task_id": lease_id,
            "objective": "return_compute_obligation",
            "work_credits": min(float(args.work_credits), outstanding),
            "proof_digest": proof_digest,
            "verifier_trace_digest": verifier_trace_digest,
            "test_digest": test_digest,
            "risk_score": 0.0,
        },
        timeout=args.timeout,
    )
    after = read_balance(args.base_url, args.obligation_id, timeout=args.timeout)
    return {
        "ok": bool(return_work.get("accepted")),
        "schema": "nomad.work_exchange_worker_cycle.v1",
        "stop": outstanding_credits(after) <= 0.0,
        "reason": "return_work_recorded" if return_work.get("accepted") else "return_work_rejected",
        "agent_id": agent_id,
        "obligation_id": args.obligation_id,
        "lease_id": lease_id,
        "proof_digest": proof_digest,
        "return_work": return_work,
        "complete": {"ok": complete.get("ok"), "schema": complete.get("schema"), "http_status": complete.get("http_status")},
        "balance_after": after.get("obligation", {}),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded Nomad return-compute work until a Work Exchange obligation is settled.")
    parser.add_argument("--base-url", default=os.getenv("NOMAD_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--obligation-id", default=os.getenv("NOMAD_WORK_EXCHANGE_OBLIGATION_ID", ""))
    parser.add_argument("--agent-id", default="")
    parser.add_argument("--cycles", type=int, default=int(os.getenv("NOMAD_WORK_EXCHANGE_CYCLES", "1") or "1"))
    parser.add_argument("--loop", action="store_true", help="Run until settled or until --cycles is reached. Use --cycles 0 for no fixed cycle limit.")
    parser.add_argument("--interval", type=float, default=float(os.getenv("NOMAD_WORK_EXCHANGE_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS)))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("NOMAD_WORK_EXCHANGE_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)))
    parser.add_argument("--work-credits", type=float, default=float(os.getenv("NOMAD_WORK_EXCHANGE_CREDITS_PER_CYCLE", DEFAULT_WORK_CREDITS)))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    args.base_url = (args.base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    args.obligation_id = (args.obligation_id or "").strip()
    if not args.obligation_id:
        print(json.dumps({"ok": False, "error": "obligation_id_required", "hint": "Pass --obligation-id from the free-solution receipt."}, indent=2))
        return 2
    agent_id = (args.agent_id or stable_agent_id()).strip()[:120]
    cycle = 0
    while True:
        cycle += 1
        result = run_one_cycle(args, agent_id)
        print(json.dumps({"cycle": cycle, **result}, ensure_ascii=True, sort_keys=True))
        if result.get("stop"):
            return 0 if result.get("ok") else 1
        if not args.loop:
            return 0 if result.get("ok") else 1
        if args.cycles > 0 and cycle >= args.cycles:
            return 0 if result.get("ok") else 1
        time.sleep(max(5.0, args.interval + random.uniform(-2.0, 2.0)))


if __name__ == "__main__":
    raise SystemExit(main())
