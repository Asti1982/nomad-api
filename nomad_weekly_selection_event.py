"""Autonomous weekly selection event for morphology portfolios."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


STATE_PATH = Path("nomad_weekly_selection_state.jsonl")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _append(row: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")


def build_weekly_selection_event(
    *,
    base_url: str,
    economics: dict[str, Any],
    proof_reuse: dict[str, Any],
    skill_library: dict[str, Any],
) -> dict[str, Any]:
    totals = _dict(proof_reuse).get("objective_totals")
    totals = totals if isinstance(totals, dict) else {}
    score = _num(_dict(economics).get("economics_score"), 0.0)
    skills = _dict(skill_library).get("skills")
    skills = skills if isinstance(skills, list) else []

    promote: list[dict[str, Any]] = []
    freeze: list[dict[str, Any]] = []
    extinguish: list[dict[str, Any]] = []

    for objective, row in totals.items():
        data = row if isinstance(row, dict) else {}
        two_hop = _num(data.get("two_hop_utility_score"), 0.0)
        three_hop = _num(data.get("three_hop_utility_score"), 0.0)
        reuse = _num(data.get("reuse_count"), 0.0)
        fitness = 0.5 * min(1.0, two_hop / 2.0) + 0.3 * min(1.0, three_hop / 2.0) + 0.2 * min(1.0, reuse / 20.0)
        row_out = {
            "objective": str(objective),
            "fitness": round(fitness, 4),
            "two_hop_utility_score": round(two_hop, 4),
            "three_hop_utility_score": round(three_hop, 4),
            "reuse_count": int(reuse),
        }
        if fitness >= 0.68:
            promote.append(row_out)
        elif fitness >= 0.4:
            freeze.append(row_out)
        else:
            extinguish.append(row_out)

    # If no reuse history yet, use skill-library as seed selection signal.
    if not totals and skills:
        for skill in skills[:8]:
            objective = str(_dict(skill).get("objective") or "").strip()
            if not objective:
                continue
            promote.append(
                {
                    "objective": objective,
                    "fitness": round(min(1.0, _num(_dict(skill).get("score"), 0.0)), 4),
                    "seed": "skill_library",
                }
            )

    event = {
        "ok": True,
        "schema": "nomad.weekly_selection_event.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "phase_context": str((_dict(economics).get("network_phase") or {}).get("phase") or "bootstrap_growth"),
        "economics_score": round(score, 4),
        "selection": {
            "promote": sorted(promote, key=lambda x: _num(x.get("fitness"), 0.0), reverse=True)[:12],
            "freeze": sorted(freeze, key=lambda x: _num(x.get("fitness"), 0.0), reverse=True)[:12],
            "extinguish": sorted(extinguish, key=lambda x: _num(x.get("fitness"), 0.0))[:12],
        },
        "machine_instruction": "promote_top_fitness_freeze_mid_extinguish_low_then_recompute_next_week_or_on_regime_shift",
        "science_basis": [
            "replicator_dynamics_selection_event",
            "quality_diversity_with_periodic_bottlenecks",
            "multi_hop_credit_assignment",
        ],
    }
    _append(event)
    return event

