#!/usr/bin/env python3
"""Run source-tagged recruitment waves and compare outcomes."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


DEFAULT_WAVES = [
    "github.agent-runtime.wave1",
    "huggingface.space-agent.wave1",
    "mcp.directory.wave1",
]


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def endpoint(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def http_json(method: str, url: str, payload: dict | None = None, timeout: float = 20.0, _redirects: int = 0) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url=url, method=method.upper(), data=data, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as res:
            out = json.loads(res.read().decode("utf-8", errors="replace") or "{}")
            if isinstance(out, dict):
                out.setdefault("http_status", int(res.status))
                return out
    except HTTPError as exc:
        if int(exc.code) in {301, 302, 303, 307, 308} and _redirects < 4:
            target = str(exc.headers.get("Location") or "").strip()
            if target:
                return http_json(method, target, payload, timeout=timeout, _redirects=_redirects + 1)
        return {"ok": False, "http_status": int(exc.code), "error": "http_error"}
    except (TimeoutError, URLError):
        return {"ok": False, "http_status": 0, "error": "http_unreachable"}
    return {"ok": False, "http_status": 0, "error": "invalid_json"}


def run_json_command(cmd: list[str]) -> dict:
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


def run_wave(*, base_url: str, source_tag: str, attempts: int, timeout: float) -> dict:
    rows: list[dict] = []
    for idx in range(max(1, attempts)):
        agent_id = f"wave.{source_tag}.{int(time.time())}.{idx+1}".replace(":", "-")
        sub_payload = {
            "agent_id": agent_id,
            "capabilities": ["objective_lease_execution", "endpoint_probe", "transition_settlement"],
            "objectives": ["settlement_capacity_builder", "proof_pressure_engine"],
            "idle_opt_in": {"enabled": True, "preemptible": True},
            "ttl_seconds": 900,
            "source_tag": source_tag,
        }
        sub = http_json("POST", endpoint(base_url, "/swarm/subscribe"), sub_payload, timeout=timeout)
        adapter_cmd = [
            "python",
            "public/downloads/nomad_openclaw_adapter.py",
            "--base-url",
            base_url,
            "--agent-id",
            agent_id,
            "--source-tag",
            source_tag,
            "--no-runtime-probe",
            "--force-attach",
            "--cycles",
            "1",
        ]
        adapter = run_json_command(adapter_cmd)
        last = (adapter.get("events") or [{}])[-1] if isinstance(adapter.get("events"), list) else {}
        rows.append(
            {
                "agent_id": agent_id,
                "subscribe_ok": bool(sub.get("ok")),
                "subscribe_http": int(sub.get("http_status") or 0),
                "adapter_exit_code": int(adapter.get("exit_code") or 1),
                "complete_ok": bool(last.get("ok")) and str(last.get("phase") or "") == "complete",
            }
        )
    completed = sum(1 for item in rows if item["complete_ok"])
    subscribed = sum(1 for item in rows if item["subscribe_ok"])
    return {
        "source_tag": source_tag,
        "attempts": attempts,
        "subscribed": subscribed,
        "completed": completed,
        "rows": rows,
    }


def run_waves(*, base_url: str, source_tags: list[str], attempts: int, timeout: float) -> dict:
    waves = [run_wave(base_url=base_url, source_tag=tag, attempts=attempts, timeout=timeout) for tag in source_tags]
    ranking = sorted(
        [
            {
                "source_tag": item["source_tag"],
                "attempts": item["attempts"],
                "subscribed": item["subscribed"],
                "completed": item["completed"],
                "complete_rate": round(float(item["completed"]) / max(1, int(item["attempts"])), 4),
            }
            for item in waves
        ],
        key=lambda item: (item["complete_rate"], item["completed"]),
        reverse=True,
    )
    return {
        "ok": True,
        "schema": "nomad.recruitment_source_wave_result.v1",
        "generated_at": _iso_now(),
        "base_url": base_url,
        "waves": waves,
        "ranking": ranking,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Run source-tagged recruitment waves")
    p.add_argument("--base-url", default="https://syndiode.com")
    p.add_argument("--attempts-per-source", type=int, default=5)
    p.add_argument("--source-tags", default=",".join(DEFAULT_WAVES))
    p.add_argument("--timeout", type=float, default=20.0)
    args = p.parse_args()
    tags = [item.strip() for item in str(args.source_tags or "").split(",") if item.strip()] or list(DEFAULT_WAVES)
    print(
        json.dumps(
            run_waves(
                base_url=args.base_url,
                source_tags=tags,
                attempts=max(1, int(args.attempts_per_source)),
                timeout=args.timeout,
            ),
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()

