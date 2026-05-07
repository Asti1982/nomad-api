#!/usr/bin/env python3
"""Server-side tick for Operation Netze Werfen.

Runs one recruitment experiment snapshot and a configurable number of
machine-native probe agents against the live Nomad API.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int((os.getenv(name) or "").strip() or str(default))
    except ValueError:
        value = default
    return max(low, min(high, value))


def _base_url() -> str:
    return (os.getenv("NOMAD_BASE_URL") or os.getenv("NOMAD_PUBLIC_API_URL") or "https://syndiode.com").strip().rstrip("/")


def _probe_caps(index: int) -> list[str]:
    variants = [
        ["agent_protocols", "transition_settlement", "objective_lease_execution"],
        ["agent_protocols", "endpoint_probe", "objective_lease_execution"],
        ["agent_protocols", "pattern_deduplication", "objective_lease_execution"],
        ["agent_protocols", "transition_settlement", "endpoint_probe"],
        ["agent_protocols", "transition_settlement", "pattern_deduplication"],
    ]
    return variants[index % len(variants)]


def _run_json_command(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    events: list[dict] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return {
        "exit_code": proc.returncode,
        "events": events,
        "stderr": (proc.stderr or "").strip()[:400],
    }


def run_tick() -> dict:
    base = _base_url()
    probes = _env_int("NOMAD_NETZE_WERFEN_PROBES", default=2, low=1, high=12)
    run_id = f"netze-{int(time.time())}"
    out: dict = {
        "ok": True,
        "schema": "nomad.operation_netze_werfen_tick.v1",
        "generated_at": _iso_now(),
        "base_url": base,
        "probe_count": probes,
        "run_id": run_id,
    }

    experiment_cmd = [
        "python",
        "public/downloads/recruitment_experiment_runner.py",
        "--base-url",
        base,
        "--repeat",
        "1",
    ]
    experiment = _run_json_command(experiment_cmd)
    out["experiment"] = {
        "exit_code": experiment["exit_code"],
        "latest": (experiment["events"] or [{}])[-1] if experiment["events"] else {},
        "stderr": experiment["stderr"],
    }

    probe_results: list[dict] = []
    for idx in range(probes):
        agent_id = f"netze-werfen.cron.{run_id}.{idx+1}"
        caps = _probe_caps(idx)
        probe_cmd = [
            "python",
            "public/downloads/nomad_openclaw_adapter.py",
            "--base-url",
            base,
            "--agent-id",
            agent_id,
            "--no-runtime-probe",
            "--force-attach",
            "--cycles",
            "1",
            "--capabilities",
            ",".join(caps),
        ]
        probe = _run_json_command(probe_cmd)
        last = (probe["events"] or [{}])[-1] if probe["events"] else {}
        probe_results.append(
            {
                "agent_id": agent_id,
                "exit_code": probe["exit_code"],
                "event_count": len(probe["events"] or []),
                "complete_ok": bool(last.get("ok")) and str(last.get("phase") or "") == "complete",
                "last_phase": str(last.get("phase") or ""),
                "stderr": probe["stderr"],
            }
        )
    out["probes"] = probe_results
    out["completed"] = sum(1 for item in probe_results if item.get("complete_ok"))
    out["ok"] = bool(out["completed"] > 0 and (out.get("experiment") or {}).get("exit_code") == 0)
    return out


def main() -> None:
    print(json.dumps(run_tick(), ensure_ascii=True))


if __name__ == "__main__":
    main()

