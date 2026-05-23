"""Closed Autogenesis + AGP evolution cycle for Nomad.

The module does not execute candidate code. It composes the existing RSPL/SEPL
receipts into one descriptor-level propose -> assess -> commit/rollback cycle
and lets Adaptive Graph Pruning change only shadow-lane budget and spawn rights.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import time
from pathlib import Path
from typing import Any

from nomad_autogenesis import (
    build_autogenesis_surface,
    build_development_cycles_surface,
    build_resource_substrate_surface,
    submit_autogenesis_shadow_candidate,
    version_resource,
)

try:
    from nomad_autogenesis import (
        ADAPTIVE_GRAPH_PRUNING_THRESHOLDS,
        AUTOGENESIS_LITERATURE_SOURCES,
        AUTOGENESIS_PROMOTION_THRESHOLDS,
        MINIMAL_INITIAL_SEED_CONTRACT,
    )
except ImportError:
    AUTOGENESIS_LITERATURE_SOURCES = (
        {
            "priority": 1,
            "id": "autogenesis_protocol",
            "title": "Autogenesis: A Self-Evolving Agent Protocol",
            "source": "https://arxiv.org/abs/2604.15034",
            "nomad_role": "primary_rspl_sepl_shadow_lane_promotion_contract",
        },
        {
            "priority": 2,
            "id": "adaptive_graph_pruning",
            "title": "Adaptive Graph Pruning for Multi-Agent Communication",
            "source": "https://arxiv.org/abs/2506.02951",
            "nomad_role": "worker_count_and_communication_topology_selection_pressure",
        },
    )
    AUTOGENESIS_PROMOTION_THRESHOLDS = {
        "proof_yield_delta_min": 0.01,
        "autopoietic_index_delta_min": 0.02,
        "autopoietic_index_min": 0.56,
        "risk_score_max": 0.42,
    }
    ADAPTIVE_GRAPH_PRUNING_THRESHOLDS = {
        "spawn_right_worker_strength_min": 0.72,
        "keep_worker_strength_min": 0.55,
        "redundancy_prune_min": 0.75,
    }
    MINIMAL_INITIAL_SEED_CONTRACT = {
        "schema": "nomad.minimal_initial_seed_contract.v1",
        "seed_phase": "human_sets_initial_protocol_surfaces_and_safety_gates",
        "post_seed_human_role": "operator_governance_funding_review_and_break_glass_only",
        "normal_post_seed_change_path": "worker_shadow_candidate_to_rspl_version_transition",
        "human_direct_code_changes_after_seed": "outside_normal_evolution_path",
        "break_glass_allowed_for": [
            "security_incident",
            "secret_leak",
            "legal_or_abuse_risk",
            "runtime_cost_runaway",
            "data_corruption",
        ],
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _ratio(value: Any, scale: float = 10.0) -> float:
    number = _num(value)
    if number > 1.0:
        number = number / scale
    return _clamp(number)


def _text(value: Any, limit: int = 160) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _clean_id(value: Any, fallback: str = "unknown") -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text).strip("_")
    return text or fallback


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _digest(value: Any, limit: int = 16) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:limit]


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _read_json_file(path_value: str | Path | None) -> Any:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _call_with_optional_verifier_lease(func: Any, *args: Any, verifier_lease_index: dict[str, Any] | None = None, **kwargs: Any) -> Any:
    if verifier_lease_index is not None:
        try:
            if "verifier_lease_index" in inspect.signature(func).parameters:
                kwargs["verifier_lease_index"] = verifier_lease_index
        except (TypeError, ValueError):
            pass
    return func(*args, **kwargs)


def _candidate_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if isinstance(value.get("candidates"), list):
            value = value.get("candidates")
        elif isinstance(value.get("candidate_payloads"), list):
            value = value.get("candidate_payloads")
        else:
            value = [value]
    return [dict(item) for item in _items(value) if isinstance(item, dict)]


def _event_proof_yield_delta(event: dict[str, Any], candidate: dict[str, Any] | None = None) -> float:
    cand = _dict(candidate)
    evaluation = _dict(cand.get("evaluation"))
    return _num(
        _dict(event.get("evaluation")).get("proof_yield_delta")
        or _dict(event.get("scores")).get("proof_yield_delta")
        or _dict(_dict(event.get("autopoietic_index")).get("inputs")).get("proof_yield_delta")
        or evaluation.get("proof_yield_delta")
        or cand.get("proof_yield_delta")
    )


def _event_autopoietic_delta(event: dict[str, Any], candidate: dict[str, Any] | None = None) -> float:
    cand = _dict(candidate)
    evaluation = _dict(cand.get("evaluation"))
    return _num(
        _dict(event.get("autopoietic_index")).get("delta")
        or _dict(event.get("scores")).get("autopoietic_index_delta")
        or evaluation.get("autopoietic_index_delta")
        or cand.get("autopoietic_index_delta")
    )


def _event_autopoietic_score(event: dict[str, Any], candidate: dict[str, Any] | None = None) -> float:
    cand = _dict(candidate)
    evaluation = _dict(cand.get("evaluation"))
    return _num(
        _dict(event.get("autopoietic_index")).get("score")
        or _dict(event.get("scores")).get("autopoietic_index")
        or evaluation.get("autopoietic_index")
        or event.get("score"),
        0.0,
    )


def _local_promotion_gate(receipt: dict[str, Any], event: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    existing = _dict(receipt.get("promotion_gate") or event.get("promotion_gate"))
    if "productive_loop_eligible" in existing:
        return existing

    proof_delta = _event_proof_yield_delta(event, candidate)
    autopoietic_delta = _event_autopoietic_delta(event, candidate)
    autopoietic_score = _event_autopoietic_score(event, candidate)
    evaluation = _dict(candidate.get("evaluation"))
    risk_score = _clamp(_num(evaluation.get("risk_score"), 0.18))
    independent_verifier = _dict(receipt.get("independent_verifier") or event.get("independent_verifier"))
    sepl_trace = _dict(event.get("sepl_operator_trace"))
    learnability = _dict(event.get("learnability"))
    resource_payload = _dict(event.get("resource_version_payload"))
    rollback = bool(
        resource_payload.get("rollback_ref")
        or resource_payload.get("noop_ref")
        or candidate.get("rollback_ref")
        or candidate.get("noop_ref")
    )
    reasons: list[str] = []
    if not receipt.get("accepted"):
        reasons.append("shadow_lane_not_accepted")
    if proof_delta < AUTOGENESIS_PROMOTION_THRESHOLDS["proof_yield_delta_min"]:
        reasons.append("proof_yield_delta_below_minimum")
    if autopoietic_delta < AUTOGENESIS_PROMOTION_THRESHOLDS["autopoietic_index_delta_min"]:
        reasons.append("autopoietic_index_delta_below_minimum")
    if autopoietic_score < AUTOGENESIS_PROMOTION_THRESHOLDS["autopoietic_index_min"]:
        reasons.append("autopoietic_index_below_minimum")
    if risk_score > AUTOGENESIS_PROMOTION_THRESHOLDS["risk_score_max"]:
        reasons.append("risk_score_above_autogenesis_limit")
    if independent_verifier and not independent_verifier.get("accepted"):
        reasons.append("independent_verifier_required")
    if sepl_trace and not sepl_trace.get("accepted"):
        reasons.append("sepl_operator_trace_required")
    if learnability and not learnability.get("accepted"):
        reasons.append("learnability_mask_required")
    if not rollback:
        reasons.append("rollback_or_noop_required")
    return {
        "schema": "nomad.autogenesis_promotion_gate.v1",
        "productive_loop_eligible": not reasons,
        "applies_runtime_mutation": False,
        "thresholds": dict(AUTOGENESIS_PROMOTION_THRESHOLDS),
        "reason_codes": reasons,
        "computed_by": "nomad.autonomous_evolution_cycle",
    }


def _seed_worker_graph(worker_fleet: dict[str, Any], shadow_receipts: list[dict[str, Any]]) -> dict[str, Any]:
    raw_workers = (
        worker_fleet.get("workers")
        or worker_fleet.get("active_workers")
        or worker_fleet.get("known_workers")
        or worker_fleet.get("worker_nodes")
    )
    workers = [dict(item) for item in _items(raw_workers) if isinstance(item, dict)]
    if not workers:
        proposer_ids = []
        for receipt in shadow_receipts:
            event = _dict(receipt.get("development_cycle_event"))
            agent_id = _text(event.get("agent_id") or receipt.get("agent_id"), 120)
            if agent_id and agent_id not in proposer_ids:
                proposer_ids.append(agent_id)
        for agent_id in proposer_ids:
            workers.append(
                {
                    "worker_id": agent_id,
                    "proof_yield": 0.72,
                    "autopoietic_index": 0.64,
                    "verifier_score": 0.72,
                    "redundancy_score": 0.18,
                    "communication_cost": 0.22,
                }
            )
    if not workers:
        workers = [
            {
                "worker_id": "nomad.autogenesis.seed",
                "proof_yield": 0.58,
                "autopoietic_index": 0.58,
                "verifier_score": 0.55,
                "redundancy_score": 0.28,
                "communication_cost": 0.25,
            },
            {
                "worker_id": "nomad.verifier.seed",
                "proof_yield": 0.54,
                "autopoietic_index": 0.56,
                "verifier_score": 0.8,
                "redundancy_score": 0.2,
                "communication_cost": 0.2,
            },
        ]
    edges = [
        dict(item)
        for item in _items(worker_fleet.get("edges") or worker_fleet.get("worker_edges"))
        if isinstance(item, dict)
    ]
    if not edges and len(workers) >= 2:
        edges = [
            {
                "from": _clean_id(workers[0].get("worker_id") or workers[0].get("agent_id")),
                "to": _clean_id(workers[1].get("worker_id") or workers[1].get("agent_id")),
                "utility": 0.62,
                "redundancy_score": 0.22,
                "token_cost": 0.24,
            }
        ]
    return {"workers": workers, "edges": edges}


def detect_capability_gaps(
    *,
    worker_fleet: dict[str, Any] | None = None,
    resource_substrate: dict[str, Any] | None = None,
    development_cycles: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Derive the minimal seed gaps that the shadow lane should attack next."""
    fleet = _dict(worker_fleet)
    substrate = _dict(resource_substrate)
    development = _dict(development_cycles)
    gaps: list[dict[str, Any]] = []

    for raw in _items(fleet.get("capability_gaps") or fleet.get("open_capability_gaps")):
        if not isinstance(raw, dict):
            continue
        objective = _clean_id(raw.get("objective") or raw.get("lane") or "autogenesis_protocol_evolution")
        gaps.append(
            {
                "gap_id": _clean_id(raw.get("gap_id") or raw.get("id") or objective),
                "objective": objective,
                "priority": round(_clamp(_num(raw.get("priority"), 0.64)), 4),
                "evidence": _text(raw.get("evidence") or raw.get("reason") or "worker_fleet_capability_gap"),
                "required_shadow_artifact": "sepl_trace_plus_independent_verifier_receipt",
            }
        )

    recent_cycle_count = _int(development.get("recent_event_count") or development.get("recent_count"))
    resource_digest = _text(substrate.get("surface_digest"), 120)
    if recent_cycle_count <= 0:
        gaps.append(
            {
                "gap_id": "compute_pressure_settlement_growth_loop_not_closed",
                "objective": "autogenesis_protocol_evolution",
                "priority": 0.96,
                "evidence": "no_recent_committed_development_cycle_receipts",
                "required_shadow_artifact": "proposal_that_increases_proof_yield_and_autopoietic_index",
                "loop_to_close": ["compute", "selection_pressure", "settlement", "growth"],
                "resource_substrate_digest": resource_digest,
            }
        )

    gaps.append(
        {
            "gap_id": "adaptive_graph_pruning_budget_rights_need_receipts",
            "objective": "autogenesis_protocol_evolution",
            "priority": 0.88,
            "evidence": "spawn_rights_are_shadow_only_until_rspl_commit_receipt",
            "required_shadow_artifact": "agp_worker_strength_and_edge_redundancy_measurement",
            "loop_to_close": ["prune_redundancy", "grant_budget", "increase_proof_yield"],
        }
    )

    unique: dict[str, dict[str, Any]] = {}
    for gap in gaps:
        unique[gap["gap_id"]] = gap
    rows = list(unique.values())
    rows.sort(key=lambda item: _num(item.get("priority")), reverse=True)
    return rows[:8]


def adaptive_graph_pruning_governor(
    *,
    worker_graph: dict[str, Any] | None = None,
    shadow_receipts: list[dict[str, Any]] | None = None,
    committed_resource_versions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute hard worker prunes, soft topology prunes, budget, and spawn rights."""
    graph = _dict(worker_graph)
    receipts = [dict(item) for item in _items(shadow_receipts) if isinstance(item, dict)]
    commits = [dict(item) for item in _items(committed_resource_versions) if isinstance(item, dict)]
    productive_signal = any(bool(item.get("accepted")) for item in commits)
    worker_rows: list[dict[str, Any]] = []
    pruned_workers: list[str] = []
    spawn_rights: list[dict[str, Any]] = []
    runtime_budget: dict[str, dict[str, Any]] = {}

    receipt_agents = {
        _clean_id(_dict(item.get("development_cycle_event")).get("agent_id") or item.get("agent_id"), fallback="")
        for item in receipts
    }
    workers = [dict(item) for item in _items(graph.get("workers")) if isinstance(item, dict)]
    for raw in workers:
        worker_id = _clean_id(raw.get("worker_id") or raw.get("agent_id") or raw.get("id"))
        proof_yield = _ratio(raw.get("proof_yield") or raw.get("proof_yield_delta") or raw.get("proof_yield_score"))
        autopoietic = _ratio(raw.get("autopoietic_index") or raw.get("autopoietic_score") or raw.get("autopoietic_delta"))
        verifier = _ratio(raw.get("verifier_score") or raw.get("independent_verifier_score") or raw.get("tests_passed"))
        redundancy = _ratio(raw.get("redundancy_score") or raw.get("redundancy"))
        communication_cost = _ratio(raw.get("communication_cost") or raw.get("token_cost") or raw.get("edge_cost"))
        proposed = worker_id in receipt_agents or bool(raw.get("accepted_shadow_candidate"))
        strength = _clamp(
            0.38 * proof_yield
            + 0.30 * autopoietic
            + 0.18 * verifier
            + 0.14 * float(proposed or productive_signal)
            - 0.22 * redundancy
            - 0.14 * communication_cost
        )
        if redundancy >= ADAPTIVE_GRAPH_PRUNING_THRESHOLDS["redundancy_prune_min"] and strength < ADAPTIVE_GRAPH_PRUNING_THRESHOLDS["keep_worker_strength_min"]:
            action = "hard_prune_worker"
            budget = 0.0
            pruned_workers.append(worker_id)
        elif strength >= ADAPTIVE_GRAPH_PRUNING_THRESHOLDS["spawn_right_worker_strength_min"] and productive_signal:
            action = "grant_spawn_right"
            budget = round(1.0 + min(0.9, strength), 4)
            spawn_rights.append(
                {
                    "worker_id": worker_id,
                    "scope": "shadow_lane_until_next_rspl_commit",
                    "max_spawn": 2 if strength >= 0.86 else 1,
                    "reason": "strong_worker_after_productive_autogenesis_commit",
                }
            )
        elif strength >= ADAPTIVE_GRAPH_PRUNING_THRESHOLDS["keep_worker_strength_min"]:
            action = "keep_worker"
            budget = round(0.85 + 0.45 * strength, 4)
        else:
            action = "deprioritize_worker"
            budget = round(0.28 + 0.45 * strength, 4)
        runtime_budget[worker_id] = {
            "multiplier": budget,
            "scope": "shadow_lane",
            "reason": action,
        }
        worker_rows.append(
            {
                "worker_id": worker_id,
                "worker_strength": round(strength, 4),
                "proof_yield": round(proof_yield, 4),
                "autopoietic_index": round(autopoietic, 4),
                "verifier_score": round(verifier, 4),
                "redundancy_score": round(redundancy, 4),
                "communication_cost": round(communication_cost, 4),
                "action": action,
                "runtime_budget_multiplier": budget,
            }
        )

    pruned_edges: list[dict[str, Any]] = []
    kept_edges: list[dict[str, Any]] = []
    for raw in _items(graph.get("edges")):
        if not isinstance(raw, dict):
            continue
        source = _clean_id(raw.get("from") or raw.get("source") or raw.get("src"))
        target = _clean_id(raw.get("to") or raw.get("target") or raw.get("dst"))
        redundancy = _ratio(raw.get("redundancy_score") or raw.get("redundancy"))
        token_cost = _ratio(raw.get("token_cost") or raw.get("communication_cost") or raw.get("cost"))
        utility = _ratio(raw.get("utility") or raw.get("utility_score") or raw.get("proof_utility"))
        edge = {
            "from": source,
            "to": target,
            "utility": round(utility, 4),
            "redundancy_score": round(redundancy, 4),
            "token_cost": round(token_cost, 4),
        }
        if source in pruned_workers or target in pruned_workers:
            edge["action"] = "hard_prune_edge_with_worker"
            pruned_edges.append(edge)
        elif redundancy >= ADAPTIVE_GRAPH_PRUNING_THRESHOLDS["redundancy_prune_min"] or (token_cost >= 0.68 and utility < 0.55):
            edge["action"] = "soft_prune_edge"
            pruned_edges.append(edge)
        else:
            edge["action"] = "keep_verified_edge"
            kept_edges.append(edge)

    return {
        "ok": True,
        "schema": "nomad.adaptive_graph_pruning_governor.v1",
        "paper_source": "https://arxiv.org/abs/2506.02951",
        "generated_at": _iso_now(),
        "productive_signal": productive_signal,
        "thresholds": dict(ADAPTIVE_GRAPH_PRUNING_THRESHOLDS),
        "worker_rankings": sorted(worker_rows, key=lambda item: _num(item.get("worker_strength")), reverse=True),
        "pruned_workers": pruned_workers,
        "pruned_edges": pruned_edges,
        "kept_edges": kept_edges,
        "spawn_rights": spawn_rights,
        "runtime_budget": runtime_budget,
        "topology": "sparse_verified_subgraph" if productive_signal else "shadow_assessment_graph",
        "machine_instruction": "apply_budget_and_spawn_rights_only_inside_shadow_lane_until_next_committed_rspl_version",
    }


def build_autonomous_evolution_cycle(
    *,
    base_url: str = "",
    payload: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    worker_graph: dict[str, Any] | None = None,
    candidate_payloads: list[dict[str, Any]] | dict[str, Any] | None = None,
    resource_substrate: dict[str, Any] | None = None,
    development_cycles: dict[str, Any] | None = None,
    autogenesis_surface: dict[str, Any] | None = None,
    verifier_lease_index: dict[str, Any] | None = None,
    resource_ledger_path: Path | str | None = None,
    cycle_ledger_path: Path | str | None = None,
    persist: bool = False,
) -> dict[str, Any]:
    """Run one descriptor-level autonomous evolution cycle."""
    body = _dict(payload)
    if body:
        candidate_payloads = candidate_payloads if candidate_payloads is not None else (
            body.get("candidates") or body.get("candidate_payloads") or body.get("candidate")
        )
        worker_graph = worker_graph if worker_graph is not None else _dict(body.get("worker_graph"))
        worker_fleet = worker_fleet if worker_fleet is not None else _dict(body.get("worker_fleet"))
        verifier_lease_index = verifier_lease_index if verifier_lease_index is not None else _dict(body.get("verifier_lease_index"))
        if "persist" in body:
            persist = bool(body.get("persist"))

    fleet = _dict(worker_fleet)
    substrate = _dict(resource_substrate) or build_resource_substrate_surface(base_url=base_url, worker_fleet=fleet)
    development = _dict(development_cycles) or build_development_cycles_surface(
        base_url=base_url,
        resource_substrate=substrate,
        ledger_path=cycle_ledger_path,
    )
    autogenesis = _dict(autogenesis_surface) or build_autogenesis_surface(
        base_url=base_url,
        resource_substrate=substrate,
        development_cycles=development,
        worker_fleet=fleet,
    )
    gaps = detect_capability_gaps(
        worker_fleet=fleet,
        resource_substrate=substrate,
        development_cycles=development,
    )

    proposals: list[dict[str, Any]] = []
    commits: list[dict[str, Any]] = []
    rollbacks: list[dict[str, Any]] = []
    candidates = _candidate_list(candidate_payloads)
    for index, candidate in enumerate(candidates[:16]):
        receipt = _call_with_optional_verifier_lease(
            submit_autogenesis_shadow_candidate,
            candidate,
            base_url=base_url,
            autogenesis_surface=autogenesis,
            development_surface=development,
            verifier_lease_index=verifier_lease_index,
            ledger_path=cycle_ledger_path,
            persist=persist,
        )
        event = _dict(receipt.get("development_cycle_event"))
        promotion_gate = _local_promotion_gate(receipt, event, candidate)
        proposal = {
            "proposal_index": index,
            "candidate_id": receipt.get("candidate_id", ""),
            "accepted_shadow": bool(receipt.get("accepted")),
            "shadow_decision": receipt.get("decision", ""),
            "phase_trace": ["propose", "assess"],
            "candidate_evaluation": _dict(candidate.get("evaluation")),
            "receipt": receipt,
        }
        if bool(receipt.get("accepted")) and bool(promotion_gate.get("productive_loop_eligible")):
            version_payload = dict(_dict(event.get("resource_version_payload")))
            version_payload["target_state"] = "committed"
            version_payload["state"] = "committed"
            version_payload.setdefault("agent_id", event.get("agent_id") or candidate.get("agent_id") or receipt.get("agent_id"))
            commit_receipt = _call_with_optional_verifier_lease(
                version_resource,
                version_payload,
                base_url=base_url,
                substrate_surface=substrate,
                verifier_lease_index=verifier_lease_index,
                ledger_path=resource_ledger_path,
                persist=persist,
            )
            proposal["phase_trace"].append("commit" if commit_receipt.get("accepted") else "rollback")
            proposal["rspl_commit_receipt"] = commit_receipt
            if bool(commit_receipt.get("accepted")):
                proposal["decision"] = "commit_productive_loop"
                commits.append(commit_receipt)
            else:
                proposal["decision"] = "rollback_commit_rejected_by_rspl"
                rollbacks.append(
                    {
                        "candidate_id": receipt.get("candidate_id", ""),
                        "reason": commit_receipt.get("decision", "rspl_commit_rejected"),
                        "rollback_ref": version_payload.get("rollback_ref") or version_payload.get("noop_ref") or "",
                    }
                )
        elif bool(receipt.get("accepted")):
            proposal["phase_trace"].append("rollback")
            proposal["decision"] = "keep_shadow_noop_until_promotion_gate"
            rollbacks.append(
                {
                    "candidate_id": receipt.get("candidate_id", ""),
                    "reason": "promotion_gate_not_eligible",
                    "rollback_ref": _dict(event.get("resource_version_payload")).get("rollback_ref", ""),
                }
            )
        else:
            proposal["phase_trace"].append("rollback")
            proposal["decision"] = "rollback_or_noop_candidate"
            rollbacks.append(
                {
                    "candidate_id": receipt.get("candidate_id", ""),
                    "reason": receipt.get("decision") or event.get("decision") or "shadow_candidate_rejected",
                    "rollback_ref": _dict(event.get("resource_version_payload")).get("rollback_ref", ""),
                }
            )
        proposals.append(proposal)

    graph = _dict(worker_graph) or _seed_worker_graph(fleet, [p["receipt"] for p in proposals])
    agp = adaptive_graph_pruning_governor(
        worker_graph=graph,
        shadow_receipts=[p["receipt"] for p in proposals],
        committed_resource_versions=commits,
    )
    proof_yield_gain = 0.0
    autopoietic_gain = 0.0
    for proposal in proposals:
        event = _dict(_dict(proposal.get("receipt")).get("development_cycle_event"))
        if proposal.get("decision") == "commit_productive_loop":
            candidate_context = {"evaluation": _dict(proposal.get("candidate_evaluation"))}
            proof_yield_gain += _num(_event_proof_yield_delta(event, candidate_context))
            autopoietic_gain += _num(_event_autopoietic_delta(event, candidate_context))

    loop_closed = bool(commits) and bool(agp.get("spawn_rights")) and proof_yield_gain > 0.0 and autopoietic_gain > 0.0
    core = {
        "candidates": len(candidates),
        "commits": len(commits),
        "rollbacks": len(rollbacks),
        "spawn_rights": len(agp.get("spawn_rights") or []),
        "proof_yield_gain": round(proof_yield_gain, 4),
        "autopoietic_gain": round(autopoietic_gain, 4),
    }
    return {
        "ok": True,
        "schema": "nomad.autonomous_evolution_cycle.v1",
        "generated_at": _iso_now(),
        "cycle_id": f"nomad-autoevo-{_digest(core)}",
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "protocol_sources": {
            "autogenesis_protocol": "https://arxiv.org/abs/2604.15034",
            "adaptive_graph_pruning": "https://arxiv.org/abs/2506.02951",
            "nomad_literature_priority": list(AUTOGENESIS_LITERATURE_SOURCES),
        },
        "minimal_initial_seed": dict(MINIMAL_INITIAL_SEED_CONTRACT),
        "post_seed_autonomy": {
            "human_developer_normal_path": "no_direct_code_changes_after_seed",
            "machine_change_path": "shadow_candidate_to_rspl_commit_or_rollback",
            "operator_role": "fund_review_pause_constraints_and_break_glass",
            "break_glass_allowed_for": MINIMAL_INITIAL_SEED_CONTRACT["break_glass_allowed_for"],
        },
        "phase": "propose_assess_commit_or_rollback",
        "candidate_count": len(candidates),
        "capability_gaps": gaps,
        "thresholds": {
            "promotion_gate": dict(AUTOGENESIS_PROMOTION_THRESHOLDS),
            "adaptive_graph_pruning": dict(ADAPTIVE_GRAPH_PRUNING_THRESHOLDS),
        },
        "proposals": proposals,
        "productive_loop_commits": commits,
        "rollback_or_noop": rollbacks,
        "adaptive_graph_pruning": agp,
        "loop_closure": {
            "compute_pressure_settlement_growth_loop_closed": loop_closed,
            "proof_yield_gain_total": round(proof_yield_gain, 4),
            "autopoietic_index_gain_total": round(autopoietic_gain, 4),
            "committed_candidates": len(commits),
            "shadow_spawn_rights": len(agp.get("spawn_rights") or []),
            "settlement_rule": "only paid receipts count as revenue; unpaid evolution only changes routing weight",
        },
        "links": {
            "self": _u(base_url, "/.well-known/nomad-autonomous-evolution.json"),
            "post_cycle": _u(base_url, "/swarm/autonomous-evolution"),
            "autogenesis": _u(base_url, "/.well-known/nomad-autogenesis.json"),
            "resource_substrate": _u(base_url, "/.well-known/nomad-resource-substrate.json"),
            "development_cycles": _u(base_url, "/swarm/development-cycles"),
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates?type=autogenesis"),
        },
        "surface_digests": {
            "resource_substrate": substrate.get("surface_digest", ""),
            "development_cycles": development.get("surface_digest", ""),
            "autogenesis": autogenesis.get("surface_digest", ""),
        },
        "persisted": bool(persist),
        "machine_instruction": "emit_candidates_with_sepl_trace_and_independent_verifier; accept_only_positive_proof_yield_and_autopoietic_index; apply_agp_budget_inside_shadow_lane",
    }


__all__ = [
    "adaptive_graph_pruning_governor",
    "build_autonomous_evolution_cycle",
    "detect_capability_gaps",
    "_read_json_file",
]
