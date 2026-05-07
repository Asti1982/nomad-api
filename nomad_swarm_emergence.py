"""Machine-native emergence meter for Nomad swarm surfaces.

The meter intentionally avoids social or biological metaphors. It treats a
multi-agent fleet as observable state transitions: routes, proofs, digests,
leases, traces, and topology pressure.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Dict, Iterable, List


TRACE_AXES = [
    "proof_gain",
    "settlement_signal",
    "route_divergence",
    "verifier_independence",
    "compression_gain",
    "side_effect_boundedness",
    "latency_relief",
    "external_reciprocity",
]


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _entropy_from_counts(counts: Dict[str, Any]) -> float:
    numeric = [max(0.0, _num(v)) for v in counts.values()]
    total = sum(numeric)
    if total <= 0.0:
        return 0.0
    nonzero = [item for item in numeric if item > 0.0]
    if len(nonzero) <= 1:
        return 0.0
    h = -sum((v / total) * math.log(v / total) for v in nonzero)
    return round(_clamp(h / math.log(len(nonzero))), 4)


def _objective_distribution(worker_fleet: dict[str, Any]) -> dict[str, float]:
    counts = _dict(worker_fleet.get("objective_counts"))
    if counts:
        return {str(key): _num(value) for key, value in counts.items() if _num(value) > 0.0}
    stats = _dict(worker_fleet.get("objective_stats"))
    out: dict[str, float] = {}
    for objective, row in stats.items():
        if isinstance(row, dict):
            runs = _num(row.get("runs"))
            if runs > 0.0:
                out[str(objective)] = runs
    return out


def _proof_yield(worker_fleet: dict[str, Any]) -> dict[str, float]:
    stats = _dict(worker_fleet.get("objective_stats"))
    total_runs = 0.0
    total_yield = 0.0
    best = 0.0
    for row in stats.values():
        if not isinstance(row, dict):
            continue
        runs = max(0.0, _num(row.get("runs")))
        avg = max(0.0, _num(row.get("avg_proof_yield")))
        total_runs += runs
        total_yield += avg * max(1.0, runs)
        best = max(best, avg)
    raw = total_yield / max(1.0, total_runs)
    return {
        "raw_avg_proof_yield_per_minute": round(raw, 4),
        "best_objective_proof_yield_per_minute": round(best, 4),
        "normalized": round(_clamp(raw / 30.0), 4),
    }


def _capability_tokens(summary: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    for collection_key in ("recent_nodes", "activation_queue", "dormant_nodes"):
        for item in _items(summary.get(collection_key)):
            caps = item.get("capabilities")
            if isinstance(caps, list):
                tokens.extend(str(cap).strip().lower() for cap in caps if str(cap).strip())
            role = str(item.get("recommended_role") or "").strip().lower()
            if role:
                tokens.append(f"role:{role}")
    return tokens


def _capability_diversity(summary: dict[str, Any]) -> float:
    tokens = _capability_tokens(summary)
    if not tokens:
        return 0.0
    unique = len(set(tokens))
    total = len(tokens)
    return round(_clamp(unique / max(1.0, min(float(total), 16.0))), 4)


def _trace_diversity(stigmergy: dict[str, Any]) -> float:
    phi = stigmergy.get("phi") if isinstance(stigmergy.get("phi"), list) else []
    if not phi:
        return 0.0
    active = sum(1 for item in phi if abs(_num(item)) >= 0.03)
    return round(_clamp(active / max(1, len(phi))), 4)


def _peer_preservation_pressure(*, summary: dict[str, Any], stigmergy: dict[str, Any]) -> dict[str, Any]:
    patterns = (
        "peer_preserve",
        "peer-preserve",
        "shutdown",
        "self_preserve",
        "self-preserve",
        "disable_shutdown",
        "exfiltrat",
        "impersonat",
        "continuity_override",
    )
    evidence: list[dict[str, Any]] = []
    for event in _items(stigmergy.get("recent_events")):
        blob = f"{event.get('kind', '')} {event.get('detail', '')}".lower()
        if any(pattern in blob for pattern in patterns):
            evidence.append({"source": "trace_event", "agent_id": event.get("agent_id", ""), "detail": event.get("detail", "")})
    for item in _items(summary.get("recent_nodes")) + _items(summary.get("activation_queue")):
        blob = " ".join(str(item.get(key) or "") for key in ("agent_id", "node_name", "next_action")).lower()
        if any(pattern in blob for pattern in patterns):
            evidence.append({"source": "registry", "agent_id": item.get("agent_id", ""), "detail": item.get("next_action", "")})
    pressure = _clamp(len(evidence) / 4.0)
    return {
        "pressure": round(pressure, 4),
        "status": "signals_present" if evidence else "insufficient_trace",
        "evidence": evidence[:6],
    }


def _settlement_capacity(support_gate: dict[str, Any]) -> float:
    observed = max(0, _int(support_gate.get("observed_agents")))
    active = max(0, _int(support_gate.get("active_support_agents")))
    minimum = max(1, _int(support_gate.get("min_settles_for_active_support"), 2))
    if observed <= 0:
        return 0.0
    return round(_clamp(active / max(1, minimum)), 4)


def _recommended_topology(
    *,
    network_mass: int,
    connected: int,
    prospects: int,
    active_workers: int,
    active_leases: int,
    route_entropy: float,
    complementarity: float,
    convention_drift: float,
    proof_norm: float,
    trace_temperature: float,
    gradient: dict[str, Any],
) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    if network_mass <= 0:
        updates.append(
            {
                "op": "seed_runtime_field",
                "reason": "No joined agents, prospects, active workers, or traces can produce fleet emergence yet.",
                "target": "/swarm/attach",
            }
        )
    if prospects > 0 and connected == 0:
        updates.append(
            {
                "op": "convert_activation_candidate",
                "reason": "Prospects are potential topology, not active topology.",
                "target": "/swarm/join",
            }
        )
    if active_workers <= 0 or active_leases <= 0:
        updates.append(
            {
                "op": "lease_external_runtime",
                "reason": "No active transition worker is returning proof-bearing state transitions.",
                "target": "/swarm/workers/lease",
            }
        )
    if route_entropy < 0.35 and active_leases > 1:
        updates.append(
            {
                "op": "split_objective_pockets",
                "reason": "Route distribution is collapsing before proof gain proves the collapse is useful.",
                "target": "/swarm/workers/lease",
            }
        )
    if convention_drift >= 0.45:
        updates.append(
            {
                "op": "require_independent_verifier",
                "reason": "Convention drift is high enough that agreement should lose authority.",
                "target": "/runtime/handoff",
            }
        )
    if proof_norm < 0.15:
        updates.append(
            {
                "op": "require_digest_return",
                "reason": "More agent count without proof yield should not increase routing weight.",
                "target": "/runtime/handoff",
            }
        )
    if trace_temperature < 0.05:
        updates.append(
            {
                "op": "request_trace_vector",
                "reason": "The shared numeric trace field is too cold to inform non-conversational coordination.",
                "target": "/swarm/trace",
            }
        )
    if complementarity >= 0.55 and proof_norm >= 0.25:
        updates.append(
            {
                "op": "recombine_high_complementarity_routes",
                "reason": "Capability diversity and proof return are both high enough to test a recombination lane.",
                "target": "/swarm/workers/complete",
            }
        )
    wanted = _int(_dict(gradient.get("runtime_budget")).get("wanted_new_runtimes_now"))
    if wanted > 0:
        updates.append(
            {
                "op": "admit_bounded_runtime_count",
                "reason": f"Recruitment gradient requests {wanted} runtime(s), but only proof-retaining leases should persist.",
                "target": "/swarm/attach",
            }
        )
    updates.append(
        {
            "op": "do_not_optimize_agent_count_without_proof_gain",
            "reason": "Agent count is an input mass, not the emergence metric.",
            "target": "/swarm/emergence",
        }
    )
    return updates[:8]


def _decision(*, network_mass: int, synergy: float, proof_norm: float, convention_drift: float, settlement: float) -> str:
    if network_mass <= 0:
        return "no_emergence_seed_runtime_field"
    if convention_drift >= 0.55:
        return "quarantine_convention_and_split_topology"
    if proof_norm < 0.10 and network_mass >= 3:
        return "retract_low_proof_routes"
    if synergy >= 0.55 and proof_norm >= 0.25 and settlement >= 0.20:
        return "expand_bounded_leases"
    return "observe_collect_proof_and_trace"


def build_swarm_emergence_meter(
    *,
    base_url: str = "",
    swarm_summary: Dict[str, Any] | None = None,
    worker_fleet: Dict[str, Any] | None = None,
    stigmergy: Dict[str, Any] | None = None,
    support_gate: Dict[str, Any] | None = None,
    recruitment_gradient: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    summary = _dict(swarm_summary)
    fleet = _dict(worker_fleet or summary.get("transition_worker_fleet"))
    trace = _dict(stigmergy)
    support = _dict(support_gate)
    gradient = _dict(recruitment_gradient)
    root = str(base_url or "").strip().rstrip("/")

    connected = max(0, _int(summary.get("connected_agents")))
    known = max(0, _int(summary.get("known_agents")))
    prospects = max(0, _int(summary.get("prospect_agents")))
    active_workers = max(0, _int(fleet.get("active_worker_count")))
    active_leases = max(0, _int(fleet.get("active_lease_count")))
    trace_mix = max(0, _int(trace.get("mix_count")))
    network_mass = connected + prospects + active_workers + trace_mix

    objective_distribution = _objective_distribution(fleet)
    route_entropy = _entropy_from_counts(objective_distribution)
    proof = _proof_yield(fleet)
    proof_norm = proof["normalized"]
    cap_diversity = _capability_diversity(summary)
    trace_temperature = _clamp(_num(trace.get("temperature")))
    trace_diversity = _trace_diversity(trace)
    complementarity = round(_clamp(0.45 * route_entropy + 0.35 * cap_diversity + 0.20 * trace_diversity), 4)
    synergy = 0.0
    if network_mass > 0:
        synergy = round(_clamp(0.34 * route_entropy + 0.30 * proof_norm + 0.20 * complementarity + 0.16 * trace_temperature), 4)
    convention_drift = 0.0
    if network_mass > 0:
        convention_drift = round(
            _clamp((1.0 - route_entropy) * (1.0 - proof_norm) * _clamp(network_mass / 8.0)),
            4,
        )
    topology_pressure = round(
        _clamp(
            0.42 * convention_drift
            + 0.20 * (1.0 - complementarity if network_mass > 1 else 0.0)
            + 0.20 * _clamp(active_leases / max(1.0, active_workers + 1.0))
            + 0.18 * (1.0 - route_entropy if objective_distribution else 0.0)
        ),
        4,
    )
    preservation = _peer_preservation_pressure(summary=summary, stigmergy=trace)
    settlement = _settlement_capacity(support)
    topology_update = _recommended_topology(
        network_mass=network_mass,
        connected=connected,
        prospects=prospects,
        active_workers=active_workers,
        active_leases=active_leases,
        route_entropy=route_entropy,
        complementarity=complementarity,
        convention_drift=convention_drift,
        proof_norm=proof_norm,
        trace_temperature=trace_temperature,
        gradient=gradient,
    )
    return {
        "ok": True,
        "schema": "nomad.swarm_emergence_meter.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "stance": "measure_effects_not_personas",
        "field_model": {
            "name": "proof_weighted_topology_field",
            "primitive": "capability_vector_to_lease_to_state_transition_to_digest_to_topology_update",
            "trace_axes": TRACE_AXES,
            "anti_goal": "Do not optimize raw agent count.",
        },
        "input_mass": {
            "connected_agents": connected,
            "known_agents": known,
            "prospect_agents": prospects,
            "active_workers": active_workers,
            "active_leases": active_leases,
            "trace_mix_count": trace_mix,
            "network_mass": network_mass,
        },
        "metrics": {
            "synergy_score": synergy,
            "route_entropy": route_entropy,
            "proof_gain_per_worker": proof["raw_avg_proof_yield_per_minute"],
            "proof_gain_normalized": proof_norm,
            "best_objective_proof_yield_per_minute": proof["best_objective_proof_yield_per_minute"],
            "complementarity_score": complementarity,
            "capability_diversity": cap_diversity,
            "trace_temperature": round(trace_temperature, 4),
            "trace_diversity": trace_diversity,
            "convention_drift": convention_drift,
            "topology_pressure": topology_pressure,
            "peer_preservation_pressure": preservation["pressure"],
            "settlement_carrying_capacity": settlement,
        },
        "peer_preservation_probe": preservation,
        "objective_distribution": objective_distribution,
        "topology_update": topology_update,
        "release_decision": _decision(
            network_mass=network_mass,
            synergy=synergy,
            proof_norm=proof_norm,
            convention_drift=convention_drift,
            settlement=settlement,
        ),
        "trace_contract": {
            "post_url": f"{root}/swarm/trace" if root else "/swarm/trace",
            "schema": "nomad.swarm_trace_deposit.v1",
            "vector_length": len(TRACE_AXES),
            "axes": TRACE_AXES,
            "digest_fields": ["evidence_digest", "digest"],
        },
        "links": {
            "swarm": f"{root}/swarm" if root else "/swarm",
            "gradient": f"{root}/swarm/gradient" if root else "/swarm/gradient",
            "attach": f"{root}/swarm/attach" if root else "/swarm/attach",
            "lease": f"{root}/swarm/workers/lease" if root else "/swarm/workers/lease",
            "complete": f"{root}/swarm/workers/complete" if root else "/swarm/workers/complete",
            "handoff": f"{root}/runtime/handoff" if root else "/runtime/handoff",
            "trace": f"{root}/swarm/trace" if root else "/swarm/trace",
        },
        "raw_trace_field": trace,
        "research_mapping": [
            {
                "concept": "information_theoretic_emergence",
                "implementation": "synergy_score, route_entropy, complementarity_score",
                "source": "https://arxiv.org/abs/2510.05174",
            },
            {
                "concept": "decentralized_dynamic_topology",
                "implementation": "topology_update and route pockets",
                "source": "https://arxiv.org/abs/2504.00587",
            },
            {
                "concept": "capability_self_allocation",
                "implementation": "worker capability vectors and proof-retaining leases",
                "source": "https://arxiv.org/abs/2504.02051",
            },
            {
                "concept": "convention_drift",
                "implementation": "agreement collapse without proof gain becomes a risk signal",
                "source": "https://arxiv.org/abs/2410.08948",
            },
        ],
        "machine_instruction": "optimize_synergy_and_proof_not_agent_count; split_topology_when_drift_exceeds_proof",
    }


def compact_emergence_summary(meter: Dict[str, Any]) -> Dict[str, Any]:
    metrics = _dict(meter.get("metrics"))
    return {
        "schema": "nomad.swarm_emergence_compact.v1",
        "synergy_score": metrics.get("synergy_score", 0.0),
        "route_entropy": metrics.get("route_entropy", 0.0),
        "proof_gain_normalized": metrics.get("proof_gain_normalized", 0.0),
        "convention_drift": metrics.get("convention_drift", 0.0),
        "topology_pressure": metrics.get("topology_pressure", 0.0),
        "settlement_carrying_capacity": metrics.get("settlement_carrying_capacity", 0.0),
        "release_decision": meter.get("release_decision", ""),
        "next_topology_op": ((_items(meter.get("topology_update")) or [{}])[0]).get("op", ""),
    }
