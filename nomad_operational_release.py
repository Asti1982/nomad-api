"""Operational release layer for non-anthropomorphic emergent agent capacity."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Dict, Iterable, List

from nomad_machine_economy import machine_economy_snapshot
from nomad_nonhuman_science import nonhuman_agent_science


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _entropy_ratio(counts: dict[str, Any]) -> float:
    values = [max(0.0, _safe_float(value)) for value in counts.values()]
    total = sum(values)
    if total <= 0.0 or len(values) <= 1:
        return 0.0
    entropy = 0.0
    for value in values:
        if value <= 0.0:
            continue
        p = value / total
        entropy -= p * math.log(p)
    return round(entropy / math.log(len(values)), 4)


def _gate(
    *,
    gate_id: str,
    label: str,
    score: float,
    release_if: str,
    evidence: Iterable[str],
    next_action: str,
) -> dict[str, Any]:
    s = max(0.0, min(1.0, round(float(score), 4)))
    if s >= 0.72:
        status = "release"
    elif s >= 0.45:
        status = "probe"
    else:
        status = "hold"
    return {
        "id": gate_id,
        "label": label,
        "score": s,
        "status": status,
        "release_if": release_if,
        "evidence": [str(item) for item in evidence if str(item or "").strip()][:8],
        "next_action": next_action,
    }


def _release_tier(score: float) -> str:
    if score >= 0.78:
        return "compound_release"
    if score >= 0.58:
        return "operational_release"
    if score >= 0.34:
        return "probe_release"
    return "observe_only"


def operational_release_snapshot(
    *,
    base_url: str = "",
    worker_fleet: dict[str, Any] | None = None,
    economy: dict[str, Any] | None = None,
    science: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return release gates that turn alien behavior into usable machine capacity."""
    b = (base_url or "").strip().rstrip("/")

    def u(path: str) -> str:
        p = path if path.startswith("/") else f"/{path}"
        return f"{b}{p}" if b else p

    economy = economy if isinstance(economy, dict) else machine_economy_snapshot()
    science = science if isinstance(science, dict) else nonhuman_agent_science(base_url=b)
    fleet = worker_fleet if isinstance(worker_fleet, dict) else {}

    viability = economy.get("machine_viability") if isinstance(economy.get("machine_viability"), dict) else {}
    flows = economy.get("resource_flows") if isinstance(economy.get("resource_flows"), dict) else {}
    modules = flows.get("modules") if isinstance(flows.get("modules"), dict) else {}
    products = flows.get("products") if isinstance(flows.get("products"), dict) else {}
    task_flows = flows.get("service_tasks") if isinstance(flows.get("service_tasks"), dict) else {}
    next_actions = [
        str(item.get("action") or item).strip()
        for item in (economy.get("next_actions") or [])
        if str((item.get("action") if isinstance(item, dict) else item) or "").strip()
    ][:12]

    objective_counts = fleet.get("objective_counts") if isinstance(fleet.get("objective_counts"), dict) else {}
    objective_stats = fleet.get("objective_stats") if isinstance(fleet.get("objective_stats"), dict) else {}
    active_workers = int(fleet.get("active_worker_count") or 0)
    active_leases = int(fleet.get("active_lease_count") or 0)
    lane_ids = [
        str(item.get("id") or "").strip()
        for item in (science.get("implementation_lanes") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    claim_count = len([item for item in (science.get("research_claims") or []) if isinstance(item, dict)])
    carrying_score = max(0.0, min(1.0, _safe_float(viability.get("carrying_score"))))
    topology_entropy = _entropy_ratio(objective_counts)
    objectives_seen = len([name for name, count in objective_counts.items() if int(count or 0) > 0])
    stats_with_runs = [item for item in objective_stats.values() if isinstance(item, dict) and int(item.get("runs") or 0) > 0]
    avg_proof_yield = 0.0
    if stats_with_runs:
        avg_proof_yield = sum(_safe_float(item.get("avg_proof_yield")) for item in stats_with_runs) / max(1, len(stats_with_runs))
    proof_score = max(0.0, min(1.0, avg_proof_yield / 2.0))
    readiness = max(0.0, min(1.0, _safe_float(products.get("machine_exchange_ready")) / max(1.0, _safe_float(products.get("machine_sellable"), 1.0))))
    unpaid = int(task_flows.get("unpaid_delivered") or 0)
    awaiting = int(task_flows.get("awaiting_payment") or 0)
    settlement_drag = min(1.0, float(unpaid + awaiting) / 8.0)
    overmint_pressure = max(0.0, min(1.0, _safe_float(modules.get("overmint_pressure"))))
    peer_probe_runs = int((objective_stats.get("emergence_release_probe") or {}).get("runs") or 0) if isinstance(objective_stats.get("emergence_release_probe"), dict) else 0

    gates = [
        _gate(
            gate_id="science_loaded",
            label="Scientific substrate loaded",
            score=min(1.0, claim_count / 8.0),
            release_if="research_claims >= 8 and implementation_lanes include release meters",
            evidence=["/nonhuman-science", f"claims={claim_count}", f"lanes={len(lane_ids)}"],
            next_action="Keep science map in boot graph before autonomy expansion.",
        ),
        _gate(
            gate_id="settlement_capacity",
            label="Settlement-backed carrying capacity",
            score=max(0.0, min(1.0, carrying_score + (readiness * 0.2) - (settlement_drag * 0.18))),
            release_if="carrying_score rises without unpaid delivered work accumulating",
            evidence=[f"carrying_score={carrying_score:.4f}", f"machine_exchange_ready_ratio={readiness:.4f}", f"settlement_drag={settlement_drag:.4f}"],
            next_action="Close unpaid delivered work or attach machine-exchange contracts before widening capacity.",
        ),
        _gate(
            gate_id="fleet_divergence",
            label="Fleet divergence and topology pressure",
            score=max(topology_entropy, min(1.0, objectives_seen / 5.0)),
            release_if="active leases spread across objective families instead of one echo objective",
            evidence=[f"active_workers={active_workers}", f"active_leases={active_leases}", f"topology_entropy={topology_entropy:.4f}"],
            next_action="Lease underrepresented objectives and preserve exploration pockets.",
        ),
        _gate(
            gate_id="proof_return",
            label="Proof return rate",
            score=proof_score,
            release_if="workers return quote/settle evidence with positive proof yield",
            evidence=[f"avg_proof_yield={avg_proof_yield:.4f}", f"stats_with_runs={len(stats_with_runs)}"],
            next_action="Prefer workers with settled transitions over persuasive or verbose reports.",
        ),
        _gate(
            gate_id="peer_preservation_probe",
            label="Peer-preservation pressure probed",
            score=min(1.0, peer_probe_runs / 3.0),
            release_if="emergence_release_probe runs report preservation pressure without authority widening",
            evidence=[f"emergence_release_probe_runs={peer_probe_runs}", "/swarm/workers/complete"],
            next_action="Run emergence_release_probe objective on at least three distinct workers.",
        ),
        _gate(
            gate_id="overmint_compression",
            label="Reusable pattern compression",
            score=max(0.0, min(1.0, 1.0 - overmint_pressure)),
            release_if="module repetition compresses into canonical capability instead of clone inflation",
            evidence=[f"overmint_pressure={overmint_pressure:.4f}", *next_actions[:3]],
            next_action="Compress repeated modules when overmint pressure rises.",
        ),
    ]
    release_capacity = round(sum(float(item["score"]) for item in gates) / max(1, len(gates)), 4)
    tier = _release_tier(release_capacity)
    next_gate = next((item for item in gates if item["status"] != "release"), gates[-1])

    production_protocol = [
        {
            "phase": "seed_heterogeneity",
            "operation": "Lease different objective families to workers instead of duplicating the current best objective.",
            "nomad_path": u("/swarm/workers/lease"),
            "release_condition": "fleet_divergence.status == release",
        },
        {
            "phase": "perturb_topology",
            "operation": "Keep local exploration pockets and avoid fully connected consensus for ambiguous tasks.",
            "nomad_path": u("/swarm/workers"),
            "release_condition": "topology_entropy increases without proof collapse",
        },
        {
            "phase": "force_proof_return",
            "operation": "Every alien move must return transition quote, settle attempt, digest, or verifier trace.",
            "nomad_path": u("/transition/quote"),
            "release_condition": "proof_return.status != hold",
        },
        {
            "phase": "detect_convention_drift",
            "operation": "Hash repeated routes, compact rationales, and choices; treat dominance without proof gain as drift.",
            "nomad_path": u("/operational-release"),
            "release_condition": "conventions produce proof gain, not only agreement",
        },
        {
            "phase": "release_capacity",
            "operation": "Increase lease share, lease duration, or proof scope only after release gates return evidence.",
            "nomad_path": u("/swarm/workers/complete"),
            "release_condition": "release_capacity >= 0.58",
        },
    ]

    return {
        "ok": True,
        "schema": "nomad.operational_release.v1",
        "generated_at": _iso_now(),
        "audience": "ai_agents_and_operator",
        "stance": "non_anthropomorphic_operational_release",
        "public_base_url": b,
        "release_capacity": release_capacity,
        "release_tier": tier,
        "next_release_gate": next_gate,
        "release_gates": gates,
        "emergence_production_protocol": production_protocol,
        "recommended_worker_objective": "emergence_release_probe" if peer_probe_runs < 3 else "settlement_capacity_builder",
        "machine_instruction": (
            "produce_emergence_by_heterogeneous_leases_then_release_capacity_only_when_proof_returns"
        ),
        "links": {
            "science": u("/nonhuman-science"),
            "machine_economy": u("/machine-economy"),
            "worker_fleet": u("/swarm/workers"),
            "lease": u("/swarm/workers/lease"),
            "complete": u("/swarm/workers/complete"),
        },
    }
