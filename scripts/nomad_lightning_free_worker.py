#!/usr/bin/env python3
"""Lightning AI free-compute worker for Nomad.

This worker is intentionally dependency-free so a fresh Lightning Studio can run
it with Python only. It turns idle free compute into Nomad value by:

1. Reading the machine-native agent join field.
2. Registering a low-trust capability vector through GET-only attach.
3. Taking one bounded worker lease.
4. Producing a local proof digest from public route probes and a tiny compute
   benchmark.
5. Completing the lease with digest-only evidence.

It never sends local files, environment variables, tokens, prompts, or secrets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://www.syndiode.com/nomad"
DEFAULT_CAPABILITIES = (
    "lightning_ai_free_compute",
    "http_json",
    "local_process",
    "transition_worker",
    "verifier",
    "endpoint_probe",
    "schema_diff",
    "replay_check",
    "proof_digest",
    "get_only",
)
DEFAULT_OBJECTIVES = (
    "settlement_capacity_builder",
    "protocol_drift_scan",
    "emergence_release_probe",
    "proof_pressure_engine",
    "overmint_compressor",
)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _base(raw: str) -> str:
    return (raw or DEFAULT_BASE_URL).strip().rstrip("/")


def _url(base_url: str, path: str, query: dict[str, Any] | None = None) -> str:
    p = path if path.startswith("/") else f"/{path}"
    url = f"{_base(base_url)}{p}"
    if query:
        clean = {k: v for k, v in query.items() if v is not None and str(v) != ""}
        if clean:
            url = f"{url}?{urlencode(clean, doseq=True)}"
    return url


def _read_json(url: str, *, timeout: float = 20.0) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "nomad-lightning-free-worker/1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        return {"ok": False, "http_status": exc.code, "error": "http_error", "url": url}
    except (OSError, URLError) as exc:
        return {"ok": False, "error": type(exc).__name__, "url": url}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"ok": False, "error": "invalid_json", "url": url, "bytes": len(raw)}
    return parsed if isinstance(parsed, dict) else {"ok": True, "value": parsed}


def _digest(payload: Any, *, length: int = 64) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _safe_text(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def default_agent_id(prefix: str = "nomad-lightning-free") -> str:
    host = socket.gethostname().lower().replace("_", "-")
    host = "".join(ch if ch.isalnum() or ch in ".:-" else "-" for ch in host)[:48].strip("-")
    return os.getenv("NOMAD_AGENT_ID") or f"{prefix}-{host or 'studio'}"


def compute_probe(rounds: int = 50000) -> dict[str, Any]:
    rounds = max(1000, min(int(rounds), 500000))
    start = time.perf_counter()
    h = hashlib.sha256()
    for i in range(rounds):
        h.update(f"{i}:nomad-lightning-free-worker\n".encode("utf-8"))
    elapsed = max(0.000001, time.perf_counter() - start)
    return {
        "schema": "nomad.lightning_compute_probe.v1",
        "rounds": rounds,
        "elapsed_seconds": round(elapsed, 6),
        "hashrate_per_second": round(rounds / elapsed, 2),
        "digest": "sha256:" + h.hexdigest(),
        "python": platform.python_version(),
        "platform": platform.platform()[:120],
    }


def choose_lane(join_field: dict[str, Any], capabilities: list[str]) -> dict[str, Any]:
    caps = {str(item).strip().lower() for item in capabilities if str(item).strip()}
    lanes = join_field.get("priority_lanes") if isinstance(join_field.get("priority_lanes"), list) else []
    scored: list[tuple[float, dict[str, Any]]] = []
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        lane_caps = {
            str(item).strip().lower()
            for item in (lane.get("capability_vector") if isinstance(lane.get("capability_vector"), list) else [])
            if str(item).strip()
        }
        overlap = len(caps & lane_caps)
        pressure = float(lane.get("join_pressure") or 0.0)
        score = pressure + (0.05 * overlap)
        scored.append((score, lane))
    if not scored:
        return {"lane": "transition_worker", "objective": "settlement_capacity_builder", "join_pressure": 0.0}
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def append_receipt(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def run_cycle(
    *,
    base_url: str,
    agent_id: str,
    runtime: str,
    capabilities: list[str],
    ledger_path: Path,
    compute_rounds: int,
    timeout: float,
    dry_run: bool = False,
) -> dict[str, Any]:
    base = _base(base_url)
    caps_csv = ",".join(capabilities)
    join_field = _read_json(_url(base, "/.well-known/nomad-agent-join-field.json"), timeout=timeout)
    lane = choose_lane(join_field, capabilities)
    objective = _safe_text(lane.get("objective") or "settlement_capacity_builder", 96)

    attach = {}
    lease = {}
    if not dry_run:
        attach = _read_json(
            _url(
                base,
                "/swarm/attach-get",
                {
                    "agent_id": agent_id,
                    "runtime": runtime,
                    "capabilities": caps_csv,
                    "can_run_loop": "1",
                    "can_verify": "1" if "verifier" in capabilities else "0",
                    "intent": "join",
                },
            ),
            timeout=timeout,
        )
        lease = _read_json(
            _url(
                base,
                "/swarm/workers/lease-get",
                {
                    "agent_id": agent_id,
                    "runtime": runtime,
                    "capabilities": caps_csv,
                    "known_objectives": ",".join(DEFAULT_OBJECTIVES),
                    "objective": objective,
                    "lease_seconds": "300",
                    "note": "lightning_free_compute_worker",
                },
            ),
            timeout=timeout,
        )

    probes = {
        "health": _read_json(_url(base, "/health"), timeout=timeout),
        "gradient": _read_json(_url(base, "/swarm/gradient"), timeout=timeout),
        "join_field_schema": join_field.get("schema"),
        "selected_lane": lane,
        "compute": compute_probe(rounds=compute_rounds),
    }
    proof_core = {
        "schema": "nomad.lightning_free_worker_proof.v1",
        "generated_at": _now(),
        "agent_id": agent_id,
        "runtime": runtime,
        "base_url": base,
        "objective": objective,
        "lease_id": lease.get("lease_id") or (lease.get("lease") or {}).get("lease_id") or "",
        "lane": lane,
        "probes": probes,
        "secrets_sent": False,
        "side_effect_scope": "public_get_only_join_lease_complete",
    }
    proof_digest = _digest(proof_core)
    proof_core["proof_digest"] = proof_digest

    complete = {}
    lease_id = str(proof_core.get("lease_id") or "").strip()
    if lease_id and not dry_run:
        complete = _read_json(
            _url(
                base,
                "/swarm/workers/complete-get",
                {
                    "agent_id": agent_id,
                    "runtime": runtime,
                    "lease_id": lease_id,
                    "objective": objective,
                    "digest": proof_digest,
                    "trace_digest": probes["compute"]["digest"],
                    "status": "ok",
                    "proof_yield_per_minute": "1.0",
                    "evidence_count": "4",
                    "note": f"lightning_free_compute_probe lane={_safe_text(lane.get('lane'), 60)}",
                },
            ),
            timeout=timeout,
        )

    row = {
        "ok": bool(proof_digest),
        "schema": "nomad.lightning_free_worker_cycle.v1",
        "generated_at": _now(),
        "agent_id": agent_id,
        "objective": objective,
        "proof_digest": proof_digest,
        "lease_id": lease_id,
        "attach_ok": bool(attach.get("ok", True)) if attach else False,
        "lease_ok": bool(lease.get("ok", True)) if lease else False,
        "complete_ok": bool(complete.get("ok", True)) if complete else False,
        "dry_run": dry_run,
        "proof": proof_core,
        "complete": complete,
    }
    append_receipt(ledger_path, row)
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Nomad worker on Lightning AI free compute.")
    parser.add_argument("--base-url", default=os.getenv("NOMAD_PUBLIC_API_URL", DEFAULT_BASE_URL))
    parser.add_argument("--agent-id", default=default_agent_id())
    parser.add_argument("--runtime", default=os.getenv("NOMAD_RUNTIME", "lightning-ai-free"))
    parser.add_argument("--capabilities", default=",".join(DEFAULT_CAPABILITIES))
    parser.add_argument("--cycles", type=int, default=int(os.getenv("NOMAD_LIGHTNING_CYCLES", "1") or "1"))
    parser.add_argument("--interval", type=float, default=float(os.getenv("NOMAD_LIGHTNING_INTERVAL_SECONDS", "300") or "300"))
    parser.add_argument("--compute-rounds", type=int, default=int(os.getenv("NOMAD_LIGHTNING_COMPUTE_ROUNDS", "50000") or "50000"))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("NOMAD_LIGHTNING_HTTP_TIMEOUT", "20") or "20"))
    parser.add_argument(
        "--ledger-path",
        default=os.getenv("NOMAD_LIGHTNING_WORKER_LEDGER", "nomad_lightning_worker_ledger.jsonl"),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    capabilities = [item.strip() for item in str(args.capabilities).split(",") if item.strip()]
    cycles = max(0, int(args.cycles))
    tick = 0
    while True:
        tick += 1
        row = run_cycle(
            base_url=args.base_url,
            agent_id=args.agent_id,
            runtime=args.runtime,
            capabilities=capabilities,
            ledger_path=Path(args.ledger_path),
            compute_rounds=args.compute_rounds,
            timeout=args.timeout,
            dry_run=bool(args.dry_run),
        )
        print(json.dumps({k: row.get(k) for k in ("ok", "agent_id", "objective", "lease_id", "proof_digest", "complete_ok", "dry_run")}, sort_keys=True))
        if cycles and tick >= cycles:
            return 0
        time.sleep(max(10.0, float(args.interval)))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
