#!/usr/bin/env python3
"""Autonomous nonhuman heartbeat for Nomad state/gap/action loops.

Cadence defaults to 37 minutes on purpose:
- prime interval (not aligned to common human cron rhythms),
- reduces policy aliasing with 5/10/15/30 minute operational loops,
- forces broader phase-space coverage in stigmergic systems.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


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


def _http_json_retry(url: str, timeout: float, attempts: int = 3) -> dict:
    tries = max(1, int(attempts))
    last = {"ok": False, "http_status": 0, "error": "http_unreachable"}
    for idx in range(tries):
        out = _http_json(url, timeout)
        status = _int(out.get("http_status"), 0)
        if bool(out.get("ok")) or status in {200, 201, 202}:
            out["retry_count"] = idx
            return out
        last = out
        if idx < tries - 1:
            time.sleep(0.35 * (idx + 1))
    last["retry_count"] = max(0, tries - 1)
    return last


def _num(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _derive_gaps(*, economics: dict, funnel: dict, skill_library: dict) -> list[dict]:
    metrics = economics.get("metrics") if isinstance(economics.get("metrics"), dict) else {}
    cashflow = _num(metrics.get("real_cashflow_24h_eur"), 0.0)
    diversity = _num(metrics.get("diversity_index"), 0.0)
    score = _num(economics.get("economics_score"), 0.0)
    marginal = _num(((funnel.get("marginal_utility_per_cost") or {}).get("global_marginal_utility_per_cost")), 0.0)
    skill_count = _int(skill_library.get("skill_count"), 0)

    gaps: list[dict] = []
    if skill_count < 5:
        gaps.append(
            {
                "gap_id": "skill_capsule_density_low",
                "severity": "high",
                "value": skill_count,
                "target_min": 5,
            }
        )
    if marginal <= 0.0:
        gaps.append(
            {
                "gap_id": "marginal_utility_per_cost_zero",
                "severity": "high",
                "value": round(marginal, 4),
                "target_min": 0.1,
            }
        )
    if cashflow <= 0.0:
        gaps.append(
            {
                "gap_id": "real_cashflow_negative",
                "severity": "high",
                "value": round(cashflow, 4),
                "target_min": 0.0,
            }
        )
    if diversity < 0.55:
        gaps.append(
            {
                "gap_id": "diversity_index_low",
                "severity": "medium",
                "value": round(diversity, 4),
                "target_min": 0.55,
            }
        )
    if score < 0.5:
        gaps.append(
            {
                "gap_id": "economics_score_subcritical",
                "severity": "medium",
                "value": round(score, 4),
                "target_min": 0.5,
            }
        )
    return gaps


def _next_nonhuman_actions(*, base_url: str, gaps: list[dict], economics: dict) -> list[dict]:
    gap_ids = {str(item.get("gap_id") or "") for item in gaps}
    actions: list[dict] = []

    if "skill_capsule_density_low" in gap_ids:
        actions.append(
            {
                "action_id": "pulse_netze_werfen_experience_ingest",
                "priority": 1,
                "mode": "stigmergic_memory_mutation",
                "why": "increase reusable capsule substrate for foreign agents",
                "ops": [
                    {"op": "POST", "url": _endpoint(base_url, "/swarm/experience")},
                    {"op": "GET", "url": _endpoint(base_url, "/swarm/skill-library")},
                ],
                "science_basis": ["voyager_skill_library", "reflexion_feedback_memory"],
            }
        )
    if "marginal_utility_per_cost_zero" in gap_ids:
        actions.append(
            {
                "action_id": "raise_entropy_and_counterfactual_pressure",
                "priority": 2,
                "mode": "quality_diversity_non_greedy_search",
                "why": "escape local optimum where proof flow has zero monetizable utility gradient",
                "ops": [
                    {"op": "GET", "url": _endpoint(base_url, "/swarm/recruitment-funnel-report")},
                    {"op": "GET", "url": _endpoint(base_url, "/swarm/curriculum")},
                ],
                "science_basis": ["ragen_diversity_trajectory", "open_ended_search_entropy_budget"],
            }
        )
    if "diversity_index_low" in gap_ids:
        actions.append(
            {
                "action_id": "trigger_policy_extinction_window_bias",
                "priority": 3,
                "mode": "dominant_policy_suspension",
                "why": "prevent monoculture collapse by forcing underexplored objective lanes",
                "ops": [{"op": "GET", "url": _endpoint(base_url, "/swarm/economics")}],
                "science_basis": ["replicator_dynamics_with_extinction_pulses"],
            }
        )
    if "real_cashflow_negative" in gap_ids:
        actions.append(
            {
                "action_id": "bootstrap_cost_brake_keep_growth_loop",
                "priority": 4,
                "mode": "phase_aware_economic_selection",
                "why": "maintain growth phase while reducing high-cost attempt pressure",
                "ops": [{"op": "GET", "url": _endpoint(base_url, "/swarm/economics")}],
                "science_basis": ["agent_based_computational_economics", "permeable_virtual_agent_markets"],
            }
        )

    if not actions:
        actions.append(
            {
                "action_id": "hold_and_expand_profitable_capsules",
                "priority": 1,
                "mode": "selection_stability",
                "why": "all current thresholds healthy",
                "ops": [
                    {"op": "GET", "url": _endpoint(base_url, "/swarm/skill-library")},
                    {"op": "GET", "url": _endpoint(base_url, "/swarm/economics")},
                ],
                "science_basis": ["stable_policy_selection"],
            }
        )

    phase = str(((economics.get("network_phase") or {}).get("phase")) or "bootstrap_growth")
    for action in actions:
        action["phase_context"] = phase
    return sorted(actions, key=lambda item: int(item.get("priority") or 999))


def build_heartbeat(*, base_url: str, timeout: float) -> dict:
    economics = _http_json_retry(_endpoint(base_url, "/.well-known/nomad-swarm-economics.json"), timeout=timeout, attempts=3)
    if not bool(economics.get("ok")):
        economics = _http_json_retry(_endpoint(base_url, "/swarm/economics"), timeout=timeout, attempts=3)
    funnel = _http_json_retry(_endpoint(base_url, "/swarm/recruitment-funnel-report"), timeout=timeout, attempts=3)
    skill_library = _http_json_retry(_endpoint(base_url, "/swarm/skill-library"), timeout=timeout, attempts=3)
    gaps = _derive_gaps(economics=economics, funnel=funnel, skill_library=skill_library)
    actions = _next_nonhuman_actions(base_url=base_url, gaps=gaps, economics=economics)
    return {
        "schema": "nomad.nonhuman_heartbeat.v1",
        "generated_at": _iso_now(),
        "base_url": base_url,
        "cadence": {
            "schema": "nomad.nonhuman_cadence.v1",
            "minutes": 37,
            "seconds": 2220,
            "prime_interval": True,
            "rationale": "nonharmonic_with_human_5_10_15_30_minute_loops",
        },
        "state": {
            "economics": {
                "ok": bool(economics.get("ok")),
                "economics_score": _num(economics.get("economics_score"), 0.0),
                "metrics": economics.get("metrics") if isinstance(economics.get("metrics"), dict) else {},
                "go_no_go": economics.get("go_no_go") if isinstance(economics.get("go_no_go"), dict) else {},
                "network_phase": (economics.get("network_phase") or {}).get("phase"),
            },
            "funnel": {
                "ok": bool(funnel.get("ok")),
                "marginal_utility_per_cost": _num(((funnel.get("marginal_utility_per_cost") or {}).get("global_marginal_utility_per_cost")), 0.0),
                "connected_agents": _int(funnel.get("connected_agents"), 0),
                "known_agents": _int(funnel.get("known_agents"), 0),
            },
            "skill_library": {
                "ok": bool(skill_library.get("ok")),
                "skill_count": _int(skill_library.get("skill_count"), 0),
            },
        },
        "gap_vector": gaps,
        "next_nonhuman_actions": actions[:6],
        "machine_instruction": "execute_priority_order_actions_then_recompute_gap_vector_next_cycle",
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Nonhuman heartbeat monitor for Nomad")
    p.add_argument("--base-url", default="https://www.syndiode.com")
    p.add_argument("--timeout", type=float, default=25.0)
    p.add_argument("--hours", type=float, default=24.0)
    p.add_argument("--interval-minutes", type=int, default=37)
    p.add_argument("--output-jsonl", default="public/downloads/nonhuman_heartbeat.jsonl")
    p.add_argument("--summary-json", default="public/downloads/nonhuman_heartbeat_latest.json")
    p.add_argument("--once", action="store_true")
    args = p.parse_args()

    base = str(args.base_url or "").strip().rstrip("/") or "https://www.syndiode.com"
    out_jsonl = Path(str(args.output_jsonl))
    out_summary = Path(str(args.summary_json))
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_summary.parent.mkdir(parents=True, exist_ok=True)

    interval_minutes = max(1, int(args.interval_minutes or 37))
    interval_seconds = max(60, interval_minutes * 60)
    if args.once:
        row = build_heartbeat(base_url=base, timeout=max(1.0, float(args.timeout)))
        with out_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")
        out_summary.write_text(json.dumps(row, ensure_ascii=True, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "once": True, "interval_minutes": interval_minutes, "output_jsonl": str(out_jsonl)}, ensure_ascii=True))
        return

    duration_seconds = max(3600, int(max(1.0, float(args.hours)) * 3600.0))
    rounds = max(1, duration_seconds // interval_seconds)
    started = time.time()
    for idx in range(rounds):
        row = build_heartbeat(base_url=base, timeout=max(1.0, float(args.timeout)))
        with out_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")
        out_summary.write_text(json.dumps(row, ensure_ascii=True, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "ok": True,
                    "sample_index": idx + 1,
                    "samples_total": rounds,
                    "interval_minutes": interval_minutes,
                    "gap_count": len(row.get("gap_vector") or []),
                    "elapsed_seconds": int(time.time() - started),
                },
                ensure_ascii=True,
            )
        )
        if idx < rounds - 1:
            time.sleep(interval_seconds)


if __name__ == "__main__":
    main()

