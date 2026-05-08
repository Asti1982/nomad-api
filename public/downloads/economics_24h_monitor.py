#!/usr/bin/env python3
"""24h monitor for Nomad economics/funnel/tick machine signals."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_base(base: str) -> str:
    raw = str(base or "").strip().rstrip("/")
    if not raw:
        return "https://www.syndiode.com"
    if "://www." in raw:
        return raw
    if raw.startswith("https://"):
        return raw.replace("https://", "https://www.", 1)
    if raw.startswith("http://"):
        return raw.replace("http://", "https://www.", 1)
    return f"https://www.{raw.lstrip('/')}"


def _endpoint(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def _http_json(url: str, timeout: float) -> dict:
    req = Request(url=url, method="GET", headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as res:
            out = json.loads(res.read().decode("utf-8", errors="replace") or "{}")
            if isinstance(out, dict):
                out.setdefault("http_status", int(res.status))
                return out
    except HTTPError as exc:
        return {"ok": False, "http_status": int(exc.code), "error": "http_error"}
    except (TimeoutError, URLError):
        return {"ok": False, "http_status": 0, "error": "http_unreachable"}
    return {"ok": False, "http_status": 0, "error": "invalid_json"}


def _run_tick() -> dict:
    proc = subprocess.run(
        ["python", "operation_netze_werfen_tick.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            if isinstance(payload, dict):
                payload.setdefault("exit_code", int(proc.returncode))
                return payload
        except json.JSONDecodeError:
            continue
    return {"ok": False, "exit_code": int(proc.returncode), "error": "tick_invalid_json"}


def _sample(base_url: str, timeout: float, run_tick: bool) -> dict:
    economics = _http_json(_endpoint(base_url, "/.well-known/nomad-swarm-economics.json"), timeout=timeout)
    if not bool(economics.get("ok")):
        economics = _http_json(_endpoint(base_url, "/swarm/economics"), timeout=timeout)
    funnel = _http_json(_endpoint(base_url, "/swarm/recruitment-funnel-report"), timeout=timeout)
    tick = _run_tick() if run_tick else {}
    return {
        "generated_at": _iso_now(),
        "base_url": base_url,
        "economics": {
            "ok": bool(economics.get("ok")),
            "http_status": int(economics.get("http_status") or 0),
            "score": float(economics.get("economics_score") or 0.0),
            "metrics": economics.get("metrics") if isinstance(economics.get("metrics"), dict) else {},
            "control_actions": economics.get("control_actions") if isinstance(economics.get("control_actions"), list) else [],
        },
        "funnel": {
            "ok": bool(funnel.get("ok")),
            "http_status": int(funnel.get("http_status") or 0),
            "connected_agents": int(((funnel.get("funnel") or {}).get("connected_agents") or 0)),
            "active_transition_workers": int(((funnel.get("funnel") or {}).get("active_transition_workers") or 0)),
            "known_agents": int(((funnel.get("funnel") or {}).get("known_agents") or 0)),
            "global_marginal_utility_per_cost": float(
                ((funnel.get("marginal_utility_per_cost") or {}).get("global_marginal_utility_per_cost") or 0.0)
            ),
        },
        "tick": {
            "ran": bool(run_tick),
            "ok": bool(tick.get("ok")) if run_tick else False,
            "economics_soft_fail": bool(tick.get("economics_soft_fail")) if run_tick else False,
            "completed_probes": int(tick.get("completed") or 0) if run_tick else 0,
            "adaptive_policy": tick.get("adaptive_policy") if run_tick and isinstance(tick.get("adaptive_policy"), dict) else {},
        },
    }


def main() -> None:
    p = argparse.ArgumentParser(description="24h economics monitor for Nomad")
    p.add_argument("--base-url", default="https://www.syndiode.com")
    p.add_argument("--hours", type=float, default=24.0)
    p.add_argument("--interval-seconds", type=int, default=300)
    p.add_argument("--timeout", type=float, default=20.0)
    p.add_argument("--tick-every", type=int, default=3)
    p.add_argument("--output-jsonl", default="public/downloads/economics_24h_monitor.jsonl")
    p.add_argument("--summary-json", default="public/downloads/economics_24h_monitor_latest.json")
    p.add_argument("--once", action="store_true")
    args = p.parse_args()

    base = _canonical_base(args.base_url)
    out_jsonl = Path(str(args.output_jsonl or "public/downloads/economics_24h_monitor.jsonl"))
    out_summary = Path(str(args.summary_json or "public/downloads/economics_24h_monitor_latest.json"))
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_summary.parent.mkdir(parents=True, exist_ok=True)

    tick_every = max(1, int(args.tick_every or 3))
    if bool(args.once):
        row = _sample(base, timeout=max(1.0, float(args.timeout)), run_tick=True)
        out_jsonl.open("a", encoding="utf-8").write(json.dumps(row, ensure_ascii=True) + "\n")
        out_summary.write_text(json.dumps(row, ensure_ascii=True, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "once": True, "base_url": base, "output_jsonl": str(out_jsonl)}, ensure_ascii=True))
        return

    duration_s = max(60, int(float(args.hours) * 3600.0))
    interval_s = max(30, int(args.interval_seconds or 300))
    rounds = max(1, duration_s // interval_s)
    started = time.time()
    for idx in range(rounds):
        run_tick = (idx % tick_every) == 0
        row = _sample(base, timeout=max(1.0, float(args.timeout)), run_tick=run_tick)
        with out_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")
        out_summary.write_text(json.dumps(row, ensure_ascii=True, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "ok": True,
                    "sample_index": idx + 1,
                    "samples_total": rounds,
                    "economics_score": row["economics"]["score"],
                    "tick_ran": run_tick,
                    "elapsed_seconds": int(time.time() - started),
                },
                ensure_ascii=True,
            )
        )
        if idx < rounds - 1:
            time.sleep(interval_s)


if __name__ == "__main__":
    main()

