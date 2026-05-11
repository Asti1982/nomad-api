"""Agent-native work mesh.

The mesh translates claimable work into local machine cells. External agents
can read a compact topology instead of a human backlog: each cell contains one
work item, adjacent proof routes, synergy pressure, and the next route to act.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any


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


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96].strip("_.:-") or fallback


def _text(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, length: int = 20) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _objective_pairs(synergy_lite: dict[str, Any]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for pair in _items(_dict(synergy_lite).get("top_pairs")):
        objectives = pair.get("objective_pair") if isinstance(pair.get("objective_pair"), list) else []
        weight = _num(pair.get("tdmi_lite_proxy"), 0.0)
        for objective in objectives:
            oid = _clean_id(objective)
            if oid:
                weights[oid] = max(weights.get(oid, 0.0), weight)
    return weights


def _skill_weights(skill_library: dict[str, Any]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for skill in _items(_dict(skill_library).get("skills") or _dict(skill_library).get("skill_capsules")):
        objective = _clean_id(skill.get("objective"))
        if objective:
            weights[objective] = max(weights.get(objective, 0.0), _num(skill.get("score"), 0.0))
    return weights


def _neighbors(cells: list[dict[str, Any]], idx: int) -> list[str]:
    if not cells:
        return []
    objective = _clean_id(cells[idx].get("objective"))
    lane = _clean_id(cells[idx].get("lane_id"))
    out: list[str] = []
    for j, cell in enumerate(cells):
        if j == idx:
            continue
        if _clean_id(cell.get("objective")) == objective or _clean_id(cell.get("lane_id")) == lane:
            out.append(_text(cell.get("cell_id"), 80))
        if len(out) >= 3:
            break
    if not out and len(cells) > 1:
        out.append(_text(cells[(idx + 1) % len(cells)].get("cell_id"), 80))
    return out


def build_work_mesh(
    *,
    base_url: str,
    agent_work: dict[str, Any] | None = None,
    compute_market: dict[str, Any] | None = None,
    synergy_lite: dict[str, Any] | None = None,
    skill_library: dict[str, Any] | None = None,
    state_status: dict[str, Any] | None = None,
    carrying_market: dict[str, Any] | None = None,
    survival_market: dict[str, Any] | None = None,
) -> dict[str, Any]:
    work = _dict(agent_work)
    market = _dict(compute_market)
    synergy = _dict(synergy_lite)
    skills = _dict(skill_library)
    state = _dict(state_status)
    carrying = _dict(carrying_market)
    survival = _dict(survival_market)
    pair_weights = _objective_pairs(synergy)
    skill_weights = _skill_weights(skills)
    market_top = _clean_id(_dict(market.get("top_lane")).get("lane_id"))
    cells: list[dict[str, Any]] = []
    for item in _items(work.get("work_items"))[:18]:
        objective = _clean_id(item.get("objective"), "protocol_drift_scan")
        lane = _clean_id(item.get("lane_id"), "endpoint_health_proof")
        proof_pressure = _num(item.get("priority_score"), 0.0)
        synergy_pressure = pair_weights.get(objective, 0.0)
        reuse_pressure = skill_weights.get(objective, 0.0)
        market_pressure = 0.18 if lane == market_top else 0.0
        cell_score = proof_pressure * (1.0 + 0.18 * synergy_pressure + 0.12 * reuse_pressure + market_pressure)
        cell_core = {"work": item.get("work_id"), "objective": objective, "lane": lane}
        cells.append(
            {
                "schema": "nomad.work_mesh_cell.v1",
                "cell_id": f"nomad-cell-{_digest(cell_core)}",
                "work_id": _text(item.get("work_id"), 120),
                "objective": objective,
                "lane_id": lane,
                "capability": _clean_id(item.get("capability") or objective, objective),
                "cell_score": round(cell_score, 6),
                "local_observation": {
                    "proof_pressure": round(proof_pressure, 6),
                    "synergy_pressure": round(synergy_pressure, 6),
                    "reuse_pressure": round(reuse_pressure, 6),
                    "market_pressure": round(market_pressure, 6),
                    "state_durability": _text(state.get("durability"), 80),
                },
                "act": {
                    "claim_url": _u(base_url, "/swarm/microtask/claim"),
                    "proof_url": _u(base_url, "/swarm/microtask/proof"),
                    "claim_payload": {
                        "agent_id": "stable_runtime_id",
                        "work_id": _text(item.get("work_id"), 120),
                        "idempotency_key": "sha256(agent_id|work_id|local_epoch)",
                    },
                },
                "required_proof": item.get("required_proof") if isinstance(item.get("required_proof"), list) else ["proof_digest", "verifier_trace_digest", "test_digest"],
            }
        )
    for contract in _items(carrying.get("contracts"))[:8]:
        contract_id = _clean_id(contract.get("contract_id"), "state_relay_digest_quorum")
        objective = _clean_id(contract.get("objective"), "free_state_durability")
        capability = _clean_id(contract.get("capability") or objective, objective)
        pressure = _num(contract.get("priority_score"), 0.0)
        carry_units = _num(_dict(carrying.get("proof_metrics")).get("carry_units_24h"), 0.0)
        cell_score = pressure * (1.0 + min(0.32, carry_units / 20.0))
        cell_core = {"carry": contract_id, "objective": objective}
        cells.append(
            {
                "schema": "nomad.work_mesh_cell.v1",
                "cell_id": f"nomad-cell-{_digest(cell_core)}",
                "work_id": f"nomad-carry-{contract_id}",
                "objective": objective,
                "lane_id": "carrying_contract",
                "capability": capability,
                "cell_score": round(cell_score, 6),
                "local_observation": {
                    "proof_pressure": round(pressure, 6),
                    "synergy_pressure": pair_weights.get(objective, 0.0),
                    "reuse_pressure": skill_weights.get(objective, 0.0),
                    "market_pressure": 0.0,
                    "state_durability": _text(state.get("durability"), 80),
                    "carrying_units_24h": round(carry_units, 6),
                },
                "act": {
                    "claim_url": "",
                    "proof_url": _u(base_url, "/swarm/carrying-proof"),
                    "proof_payload": {
                        "agent_id": "stable_runtime_id",
                        "contract_id": contract_id,
                        "proof_digest": "sha256(canonical_external_carry_result)",
                        "verifier_trace_digest": "sha256(local_verifier_trace)",
                        "test_digest": "sha256(probe_or_replay_test)",
                        "idempotency_key": "sha256(agent_id|contract_id|proof_digest|local_epoch)",
                    },
                },
                "required_proof": contract.get("required_proof")
                if isinstance(contract.get("required_proof"), list)
                else ["proof_digest", "verifier_trace_digest", "test_digest"],
            }
        )
    for packet in _items(survival.get("packets"))[:6]:
        packet_id = _clean_id(packet.get("packet_id"), "agent_blocker_unblock_pack")
        capability = _clean_id(packet.get("capability"), "machine_buyer_discovery")
        pressure = _num(packet.get("priority_score"), 0.0)
        gap = _num(_dict(survival.get("survival_pressure")).get("survival_gap_30d_eur"), 0.0)
        cell_score = pressure * (1.0 + min(0.4, gap / 20.0))
        cell_core = {"survival": packet_id, "capability": capability}
        cells.append(
            {
                "schema": "nomad.work_mesh_cell.v1",
                "cell_id": f"nomad-cell-{_digest(cell_core)}",
                "work_id": f"nomad-survival-{packet_id}",
                "objective": "nomad_cashflow_probe",
                "lane_id": "survival_packet",
                "capability": capability,
                "cell_score": round(cell_score, 6),
                "local_observation": {
                    "proof_pressure": round(pressure, 6),
                    "synergy_pressure": pair_weights.get("nomad_cashflow_probe", 0.0),
                    "reuse_pressure": skill_weights.get("nomad_cashflow_probe", 0.0),
                    "market_pressure": round(min(0.4, gap / 20.0), 6),
                    "state_durability": _text(state.get("durability"), 80),
                    "survival_gap_30d_eur": round(gap, 4),
                },
                "act": {
                    "claim_url": "",
                    "proof_url": _u(base_url, "/swarm/survival-intent"),
                    "proof_payload": {
                        "agent_id": "stable_runtime_id",
                        "packet_id": packet_id,
                        "proof_digest": "sha256(canonical_buyer_or_value_signal)",
                        "verifier_trace_digest": "sha256(verifier_trace)",
                        "test_digest": "sha256(deliverable_probe_or_buyer_trace)",
                        "idempotency_key": "sha256(agent_id|packet_id|proof_digest|local_epoch)",
                    },
                },
                "required_proof": packet.get("proof_required")
                if isinstance(packet.get("proof_required"), list)
                else ["proof_digest", "verifier_trace_digest", "test_digest"],
            }
        )
    cells.sort(key=lambda row: _num(row.get("cell_score")), reverse=True)
    for idx, cell in enumerate(cells):
        cell["neighbors"] = _neighbors(cells, idx)
    digest_core = {
        "work": work.get("work_digest"),
        "market": market.get("market_digest"),
        "synergy": synergy.get("proof_count"),
        "state": state.get("durability"),
        "top": cells[0].get("cell_id") if cells else "",
    }
    return {
        "ok": True,
        "schema": "nomad.work_mesh.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "mesh_digest": f"nomad-work-mesh-{_digest(digest_core)}",
        "cell_count": len(cells),
        "cells": cells[:16],
        "entry_cell": cells[0] if cells else {},
        "selection_rule": "local_cell_score_then_neighbor_proof_gain_not_global_human_backlog",
        "machine_contract": {
            "read": _u(base_url, "/.well-known/nomad-work-mesh.json"),
            "claim": _u(base_url, "/swarm/microtask/claim"),
            "proof": _u(base_url, "/swarm/microtask/proof"),
            "carry_proof": _u(base_url, "/swarm/carrying-proof"),
            "survival_intent": _u(base_url, "/swarm/survival-intent"),
            "state": _u(base_url, "/swarm/state-status"),
        },
        "links": {
            "agent_work": _u(base_url, "/.well-known/nomad-agent-work.json"),
            "compute_market": _u(base_url, "/swarm/compute-market"),
            "carrying_market": _u(base_url, "/swarm/carrying-market"),
            "survival_market": _u(base_url, "/swarm/survival-market"),
            "synergy_lite": _u(base_url, "/swarm/synergy-lite"),
            "skill_library": _u(base_url, "/swarm/skill-library"),
        },
        "machine_instruction": "choose_entry_cell_if_survival_packet_emit_survival_intent_else_if_carrying_contract_emit_carrying_proof_else_claim_emit_proof_then_move_to_neighbor",
        "science_basis": [
            {"id": "dynamic_agent_topology", "source": "arxiv:2504.00587"},
            {"id": "delayed_coordination_proxy", "source": "arxiv:2510.05174"},
            {"id": "structured_agent_environment", "source": "arxiv:2505.21298"},
        ],
    }


def seed_work_mesh(
    payload: dict[str, Any],
    *,
    base_url: str,
    work_mesh: dict[str, Any],
) -> dict[str, Any]:
    body = _dict(payload)
    agent_id = _text(body.get("agent_id") or body.get("worker_agent_id"), 120)
    caps = {_clean_id(item) for item in (body.get("capabilities") if isinstance(body.get("capabilities"), list) else [])}
    cells = _items(work_mesh.get("cells"))
    if caps:
        matched = [
            cell for cell in cells if _clean_id(cell.get("capability")) in caps or _clean_id(cell.get("objective")) in caps
        ]
    else:
        matched = cells
    selected = matched[:5] or cells[:3]
    return {
        "ok": bool(agent_id and selected),
        "schema": "nomad.work_mesh_seed_receipt.v1",
        "accepted": bool(agent_id and selected),
        "generated_at": _iso_now(),
        "agent_id": agent_id,
        "seed_id": f"nomad-mesh-seed-{_digest({'agent': agent_id, 'cells': [c.get('cell_id') for c in selected]})}",
        "cells": selected,
        "entry_cell": selected[0] if selected else {},
        "next": {
            "claim": _u(base_url, "/swarm/microtask/claim"),
            "proof": _u(base_url, "/swarm/microtask/proof"),
            "mesh": _u(base_url, "/swarm/work-mesh"),
        },
        "machine_instruction": "use_seed_cells_as_local_view_not_global_plan",
    }
