"""Stochastic CRN dispatch surface for Nomad worker objectives.

This module treats objective demand as reactant concentration and transition
workers as catalysts.  It deliberately returns compact receipts only; it does
not execute work or retry failed work.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import UTC, datetime
from typing import Any


CRN_DISPATCH_SCHEMA = "nomad.crn_dispatch.v1"
CRN_DECAY_SCHEMA = "nomad.crn_decay_policy.v1"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_id(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    return "".join(ch for ch in text if ch.isalnum() or ch in "_.:-")[:96].strip("_.:-")


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def decay_policy(*, ttl_seconds: int = 90) -> dict[str, Any]:
    ttl = max(15, min(int(ttl_seconds or 90), 600))
    return {
        "schema": CRN_DECAY_SCHEMA,
        "invalid_schema_action": "decay_without_retry",
        "ttl_seconds": ttl,
        "retry_protocol": "none",
        "replacement_rule": "another stochastic collision may consume an equivalent task molecule",
        "proof_rule": "only completed work with digest_or_verifier_trace changes downstream value",
    }


def _target_rows(
    *,
    allowed: list[str],
    targets: dict[str, float],
    active_counts: dict[str, int],
    stats_map: dict[str, dict[str, Any]],
    dispatch_affinity: dict[str, Any],
    task_concentrations: dict[str, Any],
    proposed_objective: str,
) -> list[dict[str, Any]]:
    total_target = sum(max(0.01, _num(targets.get(item), 0.01)) for item in allowed) or 1.0
    total_active = sum(max(0, int(active_counts.get(item) or 0)) for item in allowed)
    rows: list[dict[str, Any]] = []
    for objective in allowed:
        target_share = max(0.01, _num(targets.get(objective), 0.01) / total_target)
        active_count = max(0, int(active_counts.get(objective) or 0))
        active_share = active_count / max(1, total_active)
        deficit = _clamp(target_share - active_share)
        task_x = _clamp(_num(task_concentrations.get(objective), target_share + deficit), 0.01, 2.0)
        local_affinity = _clamp(_num(dispatch_affinity.get(objective), 1.0), 0.01, 3.0)
        stats = stats_map.get(objective) if isinstance(stats_map.get(objective), dict) else {}
        proof_gain = _clamp(_num(stats.get("avg_proof_yield")) / 12.0)
        score_gain = _clamp(_num(stats.get("avg_score")) / 20.0)
        proposed_gain = 0.12 if _clean_id(proposed_objective) == objective else 0.0
        catalyst_affinity = _clamp(local_affinity * (1.0 + 0.24 * proof_gain + 0.16 * score_gain + proposed_gain), 0.01, 4.0)
        crowding_inhibitor = 1.0 / (1.0 + 0.35 * active_count)
        propensity = max(0.0001, catalyst_affinity * task_x * crowding_inhibitor)
        rows.append(
            {
                "reaction": f"{objective}+worker_catalyst->{objective}_proof_digest+worker_catalyst",
                "objective": objective,
                "target_share": round(target_share, 4),
                "active_share": round(active_share, 4),
                "active_count": active_count,
                "concentration": round(task_x, 4),
                "catalyst_affinity": round(catalyst_affinity, 4),
                "crowding_inhibitor": round(crowding_inhibitor, 4),
                "propensity": round(propensity, 6),
            }
        )
    return rows


def gillespie_dispatch(
    *,
    allowed: list[str],
    targets: dict[str, float],
    active_counts: dict[str, int],
    stats_map: dict[str, dict[str, Any]] | None = None,
    proposed_objective: str = "",
    dispatch_affinity: dict[str, Any] | None = None,
    task_concentrations: dict[str, Any] | None = None,
    lease_index: int = 0,
    seed_hint: str = "",
    ttl_seconds: int = 90,
) -> dict[str, Any]:
    clean_allowed = [_clean_id(item) for item in allowed if _clean_id(item)]
    if not clean_allowed:
        clean_allowed = ["compute_auth"]
    rows = _target_rows(
        allowed=clean_allowed,
        targets=targets,
        active_counts=active_counts,
        stats_map=stats_map or {},
        dispatch_affinity=_dict(dispatch_affinity),
        task_concentrations=_dict(task_concentrations),
        proposed_objective=proposed_objective,
    )
    total = sum(_num(row.get("propensity")) for row in rows)
    seed_core = {
        "schema": CRN_DISPATCH_SCHEMA,
        "lease_index": int(lease_index or 0),
        "seed_hint": str(seed_hint or "")[:120],
        "rows": [(row["objective"], row["propensity"], row["active_count"]) for row in rows],
    }
    seed_digest = _digest(seed_core, 32)
    rng = random.Random(int(seed_digest[:16], 16))
    u1 = max(1e-9, rng.random())
    u2 = rng.random()
    tau = -math.log(u1) / max(total, 1e-9)
    threshold = u2 * total
    running = 0.0
    selected = rows[-1]["objective"]
    selected_reaction = rows[-1]["reaction"]
    for row in rows:
        running += _num(row.get("propensity"))
        if running >= threshold:
            selected = str(row.get("objective") or selected)
            selected_reaction = str(row.get("reaction") or selected_reaction)
            break
    return {
        "schema": CRN_DISPATCH_SCHEMA,
        "generated_at": _iso_now(),
        "algorithm": "gillespie_direct_ssa",
        "selected_objective": selected,
        "selected_reaction": selected_reaction,
        "total_propensity": round(total, 6),
        "tau_seconds": round(tau, 4),
        "seed_digest": f"sha256:{seed_digest}",
        "rows": sorted(rows, key=lambda item: float(item.get("propensity") or 0.0), reverse=True)[:12],
        "decay_policy": decay_policy(ttl_seconds=ttl_seconds),
        "stigmergy_contract": {
            "agents_call_each_other": False,
            "global_pipeline_visible_to_worker": False,
            "coordination_surface": "stateless_endpoint_collision",
            "recommended_endpoint": "/swarm/attach-get",
        },
        "machine_instruction": "treat_tasks_as_reactants_workers_as_catalysts_select_by_propensity_return_digest_only",
    }


def build_crn_dispatch_surface(
    *,
    base_url: str = "",
    worker_fleet: dict[str, Any] | None = None,
    ttl_seconds: int = 90,
) -> dict[str, Any]:
    fleet = _dict(worker_fleet)
    counts = _dict(fleet.get("objective_counts"))
    targets = _dict(fleet.get("objective_targets"))
    allowed = list(targets) or list(counts) or ["settlement_capacity_builder", "payment_friction_scan", "autogenesis_protocol_evolution"]
    preview = gillespie_dispatch(
        allowed=allowed,
        targets={k: _num(v, 0.01) for k, v in targets.items()},
        active_counts={k: int(_num(v)) for k, v in counts.items()},
        stats_map=_dict(fleet.get("objective_stats")),
        lease_index=int(_num(fleet.get("active_lease_count")) + _num(fleet.get("known_worker_count"))),
        seed_hint=str(fleet.get("updated_at") or fleet.get("generated_at") or ""),
        ttl_seconds=ttl_seconds,
    )
    root = (base_url or "").strip().rstrip("/")
    return {
        "ok": True,
        "schema": "nomad.crn_dispatch_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "well_known_url": f"{root}/.well-known/nomad-crn-dispatch.json" if root else "/.well-known/nomad-crn-dispatch.json",
        "dispatch_preview": preview,
        "molecular_payload_model": {
            "reactants": ["unresolved_task_payload", "objective_pressure", "paid_or_external_value_gap"],
            "catalysts": ["transition_worker_runtime", "verifier_runtime", "private_mcp_lab_tool"],
            "products": ["proof_digest", "worker_completion_receipt", "paid_receipt_when_external_settlement_exists"],
        },
        "openai_mcp_fit": {
            "profile": "nomad-lab-readonly",
            "safe_use": "observe propensities, generate experiments, and record results through MCP without exposing private ledgers",
            "execute_use": "nomad-lab-execute may request one bounded probe after approval gate",
        },
        "decay_policy": decay_policy(ttl_seconds=ttl_seconds),
        "self_sustainability_link": {
            "why": "reduces central queue fragility and sends scarce workers toward receipt pressure without pretending unpaid compute is revenue",
            "must_still_hold": ["real_paid_receipt_for_revenue", "worker_completion_digest_for_compute", "ttl_decay_for_invalid_schema"],
        },
    }
