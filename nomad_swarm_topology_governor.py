"""Swarm topology governor for non-human Nomad agent scaling.

The governor does not dispatch work. It decides which swarm shape is allowed
for a task and emits lease candidates with side effects disabled. This keeps
"more agents" from becoming an unchecked bag of agents.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any


SCHEMA = "nomad.swarm_topology_governor.v1"
EVENT_SCHEMA = "nomad.swarm_topology_event_receipt.v1"

SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "password",
    "private_key",
    "secret",
    "seed",
    "seed_phrase",
    "token",
}

SWARM_CELLS = [
    ("scout", "external surface discovery without synthesis authority"),
    ("retrieval_miner", "collects outside evidence before mutation"),
    ("proof_digester", "compresses proof traces into stable digests"),
    ("variant_mutator", "proposes bounded code or prompt variants"),
    ("shadow_evaluator", "scores candidates without direct weight changes"),
    ("anti_consensus_keeper", "preserves minority evidence from convergence"),
    ("decoupling_sentinel", "measures context coupling and collapse risk"),
    ("quota_watcher", "counts effective independent channels"),
    ("dead_variant_resurrector", "retests old rejected candidates under new conditions"),
    ("settlement_guard", "blocks value claims without paid receipts"),
    ("topology_auditor", "measures coordination overhead and error amplification"),
    ("apply_blocker", "keeps apply/write outside the swarm gate"),
    ("lease_router", "turns accepted topology into dry-run worker lease hints"),
    ("negative_credit_scribe", "records which topologies amplified errors"),
    ("research_before_mutation_probe", "requires outside evidence before evolution"),
    ("human_text_quarantine", "prevents persuasive prose from increasing weight"),
]


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _clamp(value: Any, default: float = 0.0) -> float:
    return max(0.0, min(1.0, _num(value, default)))


def _text(value: Any, limit: int = 360) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:150].strip("_.:/#-") or fallback


def _digest(value: Any, length: int = 22) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if _clean_id(key) in SECRET_KEYS:
                return True
            if _contains_forbidden(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def _digest_present(value: Any) -> bool:
    text = _text(value, 220).lower()
    return text.startswith(("sha256:", "sha512:", "b3:", "nomad-", "receipt:")) and len(text) >= 12


def _summary_count(surface: dict[str, Any], key: str, fallback_key: str = "cycle_count") -> int:
    summary = _dict(surface.get("summary") or surface.get("recent_summary"))
    return _int(summary.get(key), _int(summary.get(fallback_key)))


def _worker_count(swarm_summary: dict[str, Any]) -> int:
    fleet = _dict(swarm_summary.get("transition_worker_fleet"))
    for key in ("worker_count", "node_count", "active_count", "registered_worker_count"):
        count = _int(fleet.get(key), -1)
        if count >= 0:
            return count
    workers = _items(fleet.get("workers") or fleet.get("nodes"))
    return len(workers)


def _topology_catalog(base_url: str) -> list[dict[str, Any]]:
    return [
        {
            "topology_id": "single_agent",
            "max_agent_count": 1,
            "use_when": "sequential_or_high_baseline_tasks",
            "counterintuitive_rule": "block_extra_agents_when_the_single_agent_is_already_strong",
            "route_url": _u(base_url, "/swarm/development-cycles/events"),
        },
        {
            "topology_id": "centralized_router",
            "max_agent_count": 2,
            "use_when": "tool_heavy_or_error_prone_tasks",
            "counterintuitive_rule": "add_a_router_instead_of_more_workers",
            "route_url": _u(base_url, "/swarm/topology-governor/events"),
        },
        {
            "topology_id": "parallel_fanout",
            "max_agent_count": 8,
            "use_when": "decomposable_tasks_with_independent_proof",
            "counterintuitive_rule": "agents_do_not_talk_until_after_private_outputs_exist",
            "route_url": _u(base_url, "/swarm/workers/lease"),
        },
        {
            "topology_id": "decentralized_navigation",
            "max_agent_count": 4,
            "use_when": "dynamic_web_or_stateful_navigation",
            "counterintuitive_rule": "local_observers_act_before_global_synthesis",
            "route_url": _u(base_url, "/swarm/attach"),
        },
        {
            "topology_id": "shadow_only_reservoir",
            "max_agent_count": 12,
            "use_when": "speculative_research_mutation_or_missing_payment_receipt",
            "counterintuitive_rule": "grow_candidates_without_dispatching_side_effects",
            "route_url": _u(base_url, "/swarm/shadow-lane/candidates"),
        },
        {
            "topology_id": "quarantined_swarm",
            "max_agent_count": 0,
            "use_when": "secret_shaped_payloads_or_apply_send_dispatch_requests",
            "counterintuitive_rule": "the_safest_swarm_is_a_swarm_that_only_records_negative_evidence",
            "route_url": _u(base_url, "/swarm/topology-governor/events"),
        },
    ]


def build_swarm_topology_governor_surface(
    *,
    base_url: str = "",
    swarm_summary: dict[str, Any] | None = None,
    shadow_lane: dict[str, Any] | None = None,
    decoupling_field: dict[str, Any] | None = None,
    anti_consensus: dict[str, Any] | None = None,
    effective_channels: dict[str, Any] | None = None,
    development_cycles: dict[str, Any] | None = None,
    value_cycles: dict[str, Any] | None = None,
    ad_cycles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose a side-effect-free topology selector for larger agent swarms."""

    root = (base_url or "").strip().rstrip("/")
    swarm = _dict(swarm_summary)
    shadow = _dict(shadow_lane)
    decoupling = _dict(decoupling_field)
    anti = _dict(anti_consensus)
    effective = _dict(effective_channels)
    dev = _dict(development_cycles)
    value = _dict(value_cycles)
    ad = _dict(ad_cycles)
    topology_catalog = _topology_catalog(root)
    agent_cells: list[dict[str, Any]] = []
    for index, (role, purpose) in enumerate(SWARM_CELLS):
        agent_cells.append(
            {
                "schema": "nomad.swarm_topology_cell.v1",
                "cell_id": f"swarm-cell-{index + 1:02d}-{role}",
                "role": role,
                "purpose": purpose,
                "dispatch_allowed": False,
                "lease_url": _u(root, "/swarm/workers/lease"),
                "proof_required": True,
                "context_policy": "isolated_until_digest",
            }
        )

    digest_core = {
        "workers": _worker_count(swarm),
        "topologies": [(item["topology_id"], item["max_agent_count"]) for item in topology_catalog],
        "cells": [item["role"] for item in agent_cells],
        "dev": _summary_count(dev, "cycle_count"),
        "value": _summary_count(value, "cycle_count"),
        "ad": _summary_count(ad, "cycle_count"),
    }
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "read_url": _u(root, "/swarm/topology-governor"),
        "well_known_url": _u(root, "/.well-known/nomad-topology-governor.json"),
        "event_url": _u(root, "/swarm/topology-governor/events"),
        "governor_digest": f"nomad-topology-governor-{_digest(digest_core, 26)}",
        "summary": {
            "known_worker_count": _worker_count(swarm),
            "topology_count": len(topology_catalog),
            "candidate_cell_count": len(agent_cells),
            "side_effect_allowed_count": 0,
            "development_cycle_count": _summary_count(dev, "cycle_count"),
            "value_cycle_count": _summary_count(value, "cycle_count"),
            "ad_cycle_count": _summary_count(ad, "cycle_count"),
        },
        "policy": {
            "default": "no_dispatch_without_topology_event_receipt",
            "anti_bag_of_agents": True,
            "context_sharing_default": "forbidden_until_private_digest",
            "vote_default": "ignored",
            "human_text_credit": "zero_without_proof",
            "side_effects": "disabled_on_surface",
        },
        "research_rules": [
            {
                "id": "capability_saturation_cap",
                "rule": "when_single_agent_baseline_exceeds_0_45_extra_agents_are_capped_unless_parallel_fraction_is_high",
            },
            {
                "id": "sequential_task_swarm_collapse",
                "rule": "sequential_tasks_route_to_single_or_centralized_topology_even_when_more_agents_are_requested",
            },
            {
                "id": "private_trajectory_first",
                "rule": "parallel_fanout_agents_emit_private_digests_before_any_synthesis_or_debate",
            },
            {
                "id": "shadow_growth_before_dispatch",
                "rule": "speculative_or_unpaid_swarm_growth_stays_in_shadow_reservoir",
            },
        ],
        "topologies": topology_catalog,
        "agent_cells": agent_cells,
        "adjacent_surfaces": {
            "shadow_lane_schema": _text(shadow.get("schema"), 120),
            "decoupling_schema": _text(decoupling.get("schema"), 120),
            "anti_consensus_schema": _text(anti.get("schema"), 120),
            "effective_channel_schema": _text(effective.get("schema"), 120),
        },
        "links": {
            "event": _u(root, "/swarm/topology-governor/events"),
            "workers": _u(root, "/swarm/workers"),
            "lease": _u(root, "/swarm/workers/lease"),
            "shadow_lane": _u(root, "/swarm/shadow-lane/candidates"),
            "decoupling": _u(root, "/swarm/decoupling-field/merge"),
            "development_cycles": _u(root, "/.well-known/nomad-development-cycles.json"),
            "effective_channels": _u(root, "/.well-known/nomad-effective-channels.json"),
        },
        "machine_instruction": "ask_topology_governor_before_adding_agents; more_cells_may_exist_but_dispatch_requires_digest_and_task_shape",
    }


def _select_topology(body: dict[str, Any], requested: int, proof_present: bool) -> tuple[str, int, str, list[str]]:
    task_type = _clean_id(body.get("task_type") or body.get("task") or body.get("objective"), "unknown")
    sequentiality = _clamp(body.get("sequentiality"), 0.0)
    parallel_fraction = _clamp(body.get("parallel_fraction") or body.get("decomposability"), 0.0)
    baseline_success = _clamp(body.get("single_agent_baseline") or body.get("baseline_success"), 0.0)
    tool_calls = _int(body.get("tool_calls_expected") or body.get("tool_calls"), 0)
    error_risk = _clamp(body.get("error_risk") or body.get("risk_score"), 0.0)
    reasons: list[str] = []

    if not proof_present:
        return "shadow_only_reservoir", min(max(requested, 1), 6), "hold_until_proof_digest", ["proof_digest_missing"]
    if sequentiality >= 0.68:
        return "single_agent", 1, "collapse_sequential_task_to_single_agent", ["sequentiality_high"]
    if baseline_success > 0.45 and parallel_fraction < 0.55:
        return "centralized_router", min(requested, 2), "cap_capability_saturated_swarm", ["single_agent_baseline_above_0_45"]
    if tool_calls >= 4 and requested > 2:
        return "centralized_router", 2, "cap_tool_heavy_swarm_overhead", ["tool_coordination_overhead"]
    if parallel_fraction >= 0.55 and error_risk <= 0.55:
        return "parallel_fanout", min(max(requested, 2), 8), "allow_isolated_parallel_fanout", ["parallel_fraction_high"]
    if "web" in task_type or "navigation" in task_type or "browse" in task_type:
        return "decentralized_navigation", min(max(requested, 2), 4), "allow_decentralized_navigation", ["dynamic_navigation_task"]
    if error_risk > 0.55:
        return "shadow_only_reservoir", min(max(requested, 1), 4), "route_high_risk_to_shadow_only", ["error_risk_high"]
    return "centralized_router", min(max(requested, 1), 2), "allow_small_centralized_swarm", reasons or ["default_small_swarm"]


def evaluate_swarm_topology_event(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    topology_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate a requested swarm shape without dispatching any agents."""

    body = _dict(payload)
    now = _iso_now()
    requested = max(0, min(64, _int(body.get("agent_count_requested") or body.get("requested_agents"), 1)))
    proof_digest = _text(
        body.get("proof_digest") or body.get("evidence_digest") or body.get("task_digest") or body.get("patch_plan_digest"),
        220,
    )
    proof_present = _digest_present(proof_digest)
    side_effect_requested = bool(
        body.get("dispatch")
        or body.get("execute")
        or body.get("send")
        or body.get("apply")
        or body.get("write")
        or body.get("repo_write")
    )
    forbidden = _contains_forbidden(body)

    if not body:
        topology = "quarantined_swarm"
        max_agents = 0
        decision = "reject_empty_topology_event"
        reasons = ["empty_payload"]
        allowed = False
    elif forbidden:
        topology = "quarantined_swarm"
        max_agents = 0
        decision = "reject_secret_shaped_payload"
        reasons = ["secret_shaped_payload"]
        allowed = False
    elif side_effect_requested:
        topology = "quarantined_swarm"
        max_agents = 0
        decision = "block_dispatch_or_apply_request"
        reasons = ["side_effect_requested"]
        allowed = False
    else:
        topology, max_agents, decision, reasons = _select_topology(body, requested, proof_present)
        allowed = decision != "hold_until_proof_digest"

    surface = _dict(topology_surface)
    cells = _items(surface.get("agent_cells"))
    if not cells:
        cells = build_swarm_topology_governor_surface(base_url=base_url).get("agent_cells", [])
    selected_cells = cells[:max_agents]
    objective = _clean_id(body.get("objective") or body.get("task_type") or "swarm_topology", "swarm_topology")
    lease_payloads = []
    for index, cell in enumerate(selected_cells):
        lease_payloads.append(
            {
                "agent_id": f"nomad-swarm-{cell.get('role', 'cell')}-{index + 1}",
                "proposed_objective": objective,
                "preferred_role": cell.get("role"),
                "source_tag": "topology_governor_dry_run",
                "proof_digest": proof_digest,
                "dispatch_allowed": False,
                "dry_run": True,
                "idempotency_key": f"topology-{_digest([objective, topology, cell.get('role'), proof_digest], 18)}",
            }
        )

    receipt_core = {
        "requested": requested,
        "topology": topology,
        "max_agents": max_agents,
        "decision": decision,
        "proof_digest": proof_digest,
        "reasons": reasons,
    }
    return {
        "ok": True,
        "schema": EVENT_SCHEMA,
        "generated_at": now,
        "event_id": f"nomad-topology-event-{_digest({**receipt_core, 't': now}, 18)}",
        "requested_agent_count": requested,
        "allowed_agent_count": max_agents,
        "selected_topology": topology,
        "topology_plan_allowed": allowed,
        "decision": decision,
        "reasons": reasons,
        "metrics": {
            "single_agent_baseline": _clamp(body.get("single_agent_baseline") or body.get("baseline_success"), 0.0),
            "sequentiality": _clamp(body.get("sequentiality"), 0.0),
            "parallel_fraction": _clamp(body.get("parallel_fraction") or body.get("decomposability"), 0.0),
            "tool_calls_expected": _int(body.get("tool_calls_expected") or body.get("tool_calls"), 0),
            "error_risk": _clamp(body.get("error_risk") or body.get("risk_score"), 0.0),
            "proof_digest_present": proof_present,
            "side_effect_requested": side_effect_requested,
        },
        "selected_agent_cells": selected_cells,
        "worker_lease_payload_candidates": lease_payloads,
        "recommended_next": {
            "topology_governor": _u(base_url, "/.well-known/nomad-topology-governor.json"),
            "worker_lease": _u(base_url, "/swarm/workers/lease"),
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates"),
            "development_cycles": _u(base_url, "/swarm/development-cycles/events"),
        },
        "dispatch_allowed": False,
        "repo_write_allowed": False,
        "counts_as_revenue": False,
        "receipt_digest": "sha256:" + _digest(receipt_core, 32),
        "hard_rule": "topology_governor_never_dispatches_agents_or_applies_code",
    }
