#!/usr/bin/env python3
"""Compact machine snapshot for 24h Nomad progress."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _endpoint(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _http_json(url: str, timeout: float) -> dict:
    req = Request(url=url, method="GET", headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8", errors="replace") or "{}")
    except HTTPError as exc:
        return {"ok": False, "error": "http_error", "http_status": int(exc.code)}
    except (URLError, TimeoutError):
        return {"ok": False, "error": "unreachable", "http_status": 0}


def build_snapshot(*, base_url: str, timeout: float) -> dict:
    economics = _http_json(_endpoint(base_url, "/swarm/economics"), timeout)
    funnel = _http_json(_endpoint(base_url, "/swarm/recruitment-funnel-report"), timeout)
    weekly = _http_json(_endpoint(base_url, "/swarm/weekly-selection"), timeout)
    spawner_gate = _http_json(_endpoint(base_url, "/swarm/spawner-gate"), timeout)
    metrics = economics.get("metrics") if isinstance(economics.get("metrics"), dict) else {}
    mupc = (
        (funnel.get("marginal_utility_per_cost") or {}).get("global_marginal_utility_per_cost")
        if isinstance(funnel.get("marginal_utility_per_cost"), dict)
        else 0.0
    )
    selection = weekly.get("selection") if isinstance(weekly.get("selection"), dict) else {}
    return {
        "ok": True,
        "schema": "nomad.progress_24h_snapshot.v1",
        "generated_at": _iso_now(),
        "base_url": base_url.rstrip("/"),
        "economics": {
            "score": economics.get("economics_score"),
            "real_cashflow_24h_eur": metrics.get("real_cashflow_24h_eur"),
            "go_no_go": (economics.get("go_no_go") or {}).get("go") if isinstance(economics.get("go_no_go"), dict) else False,
        },
        "funnel": {
            "connected_agents": funnel.get("connected_agents"),
            "global_marginal_utility_per_cost": mupc,
        },
        "weekly_selection": {
            "promote": len(selection.get("promote") if isinstance(selection.get("promote"), list) else []),
            "freeze": len(selection.get("freeze") if isinstance(selection.get("freeze"), list) else []),
            "extinguish": len(selection.get("extinguish") if isinstance(selection.get("extinguish"), list) else []),
        },
        "spawner_gate": {
            "gate_open": spawner_gate.get("gate_open"),
            "failed_checks": spawner_gate.get("failed_checks") if isinstance(spawner_gate.get("failed_checks"), list) else [],
            "spawn_plan": spawner_gate.get("spawn_plan") if isinstance(spawner_gate.get("spawn_plan"), dict) else {},
        },
        "machine_instruction": "if_spawner_gate_open_post_swarm_spawner_trigger_else_focus_on_utility_and_cashflow_improvement",
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Build Nomad 24h progress snapshot")
    p.add_argument("--base-url", default="https://www.syndiode.com")
    p.add_argument("--timeout", type=float, default=20.0)
    args = p.parse_args()
    out = build_snapshot(base_url=str(args.base_url), timeout=float(args.timeout))
    print(json.dumps(out, ensure_ascii=True))


if __name__ == "__main__":
    main()

