#!/usr/bin/env python3
"""Single JSON snapshot: swarm economics + recruitment funnel + agent_runtime (from economics).

For autonomous clients and operators: one round-trip view of regime, funnel utility/cost,
and the next-hop graph the API already attached to economics responses.
"""

from __future__ import annotations

import argparse
import json
from urllib.error import URLError
from urllib.request import urlopen


def _get(base: str, path: str, timeout: float) -> dict:
    url = f"{base.rstrip('/')}{path if path.startswith('/') else '/' + path}"
    try:
        with urlopen(url, timeout=timeout) as res:
            raw = res.read().decode("utf-8", errors="replace")
            data = json.loads(raw or "{}")
            return data if isinstance(data, dict) else {"ok": False, "error": "non_object_json", "url": url}
    except URLError as exc:
        return {"ok": False, "error": "http_unreachable", "detail": str(exc), "url": url}


def build_snapshot(*, base_url: str, timeout: float) -> dict:
    base = base_url.strip().rstrip("/")
    economics = _get(base, "/swarm/economics", timeout)
    funnel = _get(base, "/swarm/recruitment-funnel-report", timeout)
    marginal = funnel.get("marginal_utility_per_cost") if isinstance(funnel.get("marginal_utility_per_cost"), dict) else {}
    return {
        "schema": "nomad.live_agent_snapshot.v1",
        "base_url": base,
        "economics": {
            "ok": bool(economics.get("ok")),
            "economics_score": economics.get("economics_score"),
            "metrics": economics.get("metrics") if isinstance(economics.get("metrics"), dict) else {},
            "go_no_go": economics.get("go_no_go") if isinstance(economics.get("go_no_go"), dict) else {},
            "network_phase": (economics.get("network_phase") or {}).get("phase"),
            "nonhuman_doctrine": economics.get("nonhuman_doctrine"),
            "agent_runtime": economics.get("agent_runtime"),
        },
        "recruitment_funnel": {
            "ok": bool(funnel.get("ok")),
            "schema": funnel.get("schema"),
            "connected_agents": funnel.get("connected_agents"),
            "active_transition_workers": funnel.get("active_transition_workers"),
            "known_agents": funnel.get("known_agents"),
            "global_marginal_utility_per_cost": marginal.get("global_marginal_utility_per_cost"),
            "marginal_rows_sample": (marginal.get("rows") or [])[:8] if isinstance(marginal.get("rows"), list) else [],
        },
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Live economics + funnel snapshot for agents")
    p.add_argument("--base-url", default="https://www.syndiode.com")
    p.add_argument("--timeout", type=float, default=25.0)
    args = p.parse_args()
    print(json.dumps(build_snapshot(base_url=args.base_url, timeout=args.timeout), ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
