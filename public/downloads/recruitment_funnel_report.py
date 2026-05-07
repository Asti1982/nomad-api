#!/usr/bin/env python3
"""Live recruitment funnel and emergence report for Nomad."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def endpoint(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def http_json(url: str, timeout: float = 20.0) -> dict:
    req = Request(url=url, method="GET", headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read().decode("utf-8", errors="replace") or "{}")
            if isinstance(data, dict):
                data.setdefault("http_status", int(res.status))
                return data
    except HTTPError as exc:
        return {"ok": False, "http_status": int(exc.code), "error": "http_error"}
    except (TimeoutError, URLError):
        return {"ok": False, "http_status": 0, "error": "http_unreachable"}
    return {"ok": False, "http_status": 0, "error": "invalid_json"}


def build_report(base_url: str, timeout: float) -> dict:
    swarm = http_json(endpoint(base_url, "/swarm"), timeout=timeout)
    workers = http_json(endpoint(base_url, "/swarm/workers"), timeout=timeout)
    gradient = http_json(endpoint(base_url, "/swarm/gradient"), timeout=timeout)
    treasury = http_json(endpoint(base_url, "/machine-treasury"), timeout=timeout)
    reuse = http_json(endpoint(base_url, "/swarm/reuse-ledger"), timeout=timeout)
    recent_nodes = swarm.get("recent_nodes") if isinstance(swarm.get("recent_nodes"), list) else []
    source_counts = Counter(str((item or {}).get("source_tag") or "unknown") for item in recent_nodes if isinstance(item, dict))
    source_counts = Counter({k: v for k, v in source_counts.items() if k})
    objective_stats = workers.get("objective_stats") if isinstance(workers.get("objective_stats"), dict) else {}
    settled_like = 0
    total_runs = 0
    avg_score = 0.0
    if objective_stats:
        runs = [float((v or {}).get("runs") or 0.0) for v in objective_stats.values() if isinstance(v, dict)]
        scores = [float((v or {}).get("avg_score") or 0.0) for v in objective_stats.values() if isinstance(v, dict)]
        total_runs = int(sum(runs))
        if scores:
            avg_score = sum(scores) / max(1, len(scores))
        for v in objective_stats.values():
            if not isinstance(v, dict):
                continue
            if float(v.get("avg_score") or 0.0) >= 3.0:
                settled_like += int(float(v.get("runs") or 0.0))
    pressure = gradient.get("selection_pressure") if isinstance(gradient.get("selection_pressure"), dict) else {}
    top_grad = (gradient.get("gradient") or [{}])[0] if isinstance(gradient.get("gradient"), list) else {}
    return {
        "ok": True,
        "schema": "nomad.recruitment_funnel_report.v1",
        "generated_at": _iso_now(),
        "base_url": base_url,
        "funnel": {
            "connected_agents": int(swarm.get("connected_agents") or 0),
            "active_transition_workers": int(swarm.get("active_transition_workers") or 0),
            "known_agents": int(swarm.get("known_agents") or 0),
            "active_worker_leases": int(swarm.get("active_worker_leases") or 0),
            "worker_known_count": int(workers.get("known_worker_count") or 0),
            "worker_active_count": int(workers.get("active_worker_count") or 0),
            "returning_workers_24h": int(((workers.get("retention") or {}).get("returning_workers_24h") or 0)),
            "completions_per_known_worker": float(((workers.get("retention") or {}).get("completions_per_known_worker") or 0.0)),
            "leases_per_active_worker": float(((workers.get("retention") or {}).get("leases_per_active_worker") or 0.0)),
        },
        "emergence": {
            "objective_run_count": total_runs,
            "high_score_run_count": settled_like,
            "avg_objective_score": round(avg_score, 4),
            "top_objective": str(top_grad.get("objective") or ""),
            "top_objective_weight": float(top_grad.get("routing_weight") or 0.0),
        },
        "source_tags": [{"source_tag": k, "count": v} for k, v in source_counts.most_common(16)],
        "selection_pressure": pressure,
        "machine_treasury": {
            "schema": treasury.get("schema", ""),
            "objective_pressure_hints": treasury.get("objective_pressure_hints") if isinstance(treasury.get("objective_pressure_hints"), dict) else {},
            "pledge_count": len(treasury.get("recent_pledges") or []) if isinstance(treasury.get("recent_pledges"), list) else 0,
        },
        "proof_reuse": {
            "schema": reuse.get("schema", ""),
            "total_reuse_count": int(reuse.get("total_reuse_count") or 0),
            "objective_totals": reuse.get("objective_totals") if isinstance(reuse.get("objective_totals"), dict) else {},
            "proof_reuse_rate": round(
                float(reuse.get("total_reuse_count") or 0) / max(1.0, float(total_runs)),
                4,
            ),
        },
        "science_refs": [
            {"id": "stigmergy", "uri": "https://arxiv.org/abs/2510.10047"},
            {"id": "multi_agent_context", "uri": "https://arxiv.org/abs/2506.03053"},
            {"id": "self_organizing_agents", "uri": "https://arxiv.org/abs/2603.28990"},
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Nomad recruitment funnel report")
    parser.add_argument("--base-url", default="https://www.syndiode.com")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    print(json.dumps(build_report(args.base_url, args.timeout), ensure_ascii=True))


if __name__ == "__main__":
    main()

