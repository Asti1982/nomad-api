"""Optimal Transport routing kernel for Nomad.

This module implements the part of OT that can be exact in a tiny hosted API:
one-dimensional Monge/Kantorovich transport via quantile matching. Discrete
atoms and non-overlapping piecewise-uniform continuous intervals are compiled
into quantile segments; the solver then integrates W1 or W2 costs exactly over
those segments. It deliberately does not use Sinkhorn, softmax routing, or
multi-dimensional projection while calling the result exact.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from typing import Any


SCHEMA = "nomad.optimal_transport.v1"
PLAN_SCHEMA = "nomad.optimal_transport_plan.v1"
ERROR_SCHEMA = "nomad.optimal_transport_error.v1"

EPS = 1e-12


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


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _text(value: Any, limit: int = 220) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:140].strip("_.:/#-") or fallback


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _axis_position_from_objective(objective: str) -> float:
    key = _clean_id(objective)
    if "server" in key or "runtime" in key or "health" in key:
        return 0.08
    if "lease" in key or "capacity" in key or "worker" in key:
        return 0.28
    if "proof" in key or "test" in key or "review" in key:
        return 0.56
    if "settlement" in key or "receipt" in key or "paid" in key:
        return 0.88
    return 0.48


def _axis_position_from_pressure_row(row: dict[str, Any]) -> float:
    explicit = row.get("ot_coordinate")
    if explicit is not None:
        return _clamp(_num(explicit, 0.5))
    action = _clean_id(row.get("action"))
    stage = _clean_id(row.get("target_stage") or row.get("current_stage"))
    kind = _clean_id(row.get("kind"))
    if "platform_repair" in kind or "protected_runtime" in stage:
        return 0.08
    if "capacity" in action or "worker" in kind or "lease" in action:
        return 0.28
    if "proof" in kind or "proof" in action or "submitted" in stage:
        return 0.56
    if "settlement" in action or "paid" in stage or "receipt" in action or "settled" in stage:
        return 0.88
    return 0.5


def _node_to_segment(node: dict[str, Any], total_mass: float, cumulative: float) -> dict[str, Any]:
    raw_mass = max(0.0, _num(node.get("mass"), 0.0))
    mass = raw_mass / total_mass
    node_id = _clean_id(node.get("id") or node.get("node_id"), f"node-{_digest(node, 8)}")
    if "interval" in node and isinstance(node.get("interval"), dict):
        interval = _dict(node.get("interval"))
        start = _num(interval.get("start"), _num(interval.get("min"), 0.0))
        end = _num(interval.get("end"), _num(interval.get("max"), start))
    elif node.get("continuous"):
        start = _num(node.get("start"), _num(node.get("min"), _num(node.get("position"), 0.0)))
        end = _num(node.get("end"), _num(node.get("max"), start))
    else:
        start = _num(node.get("position"), _num(node.get("coordinate"), 0.0))
        end = start
    if end < start:
        start, end = end, start
    slope = (end - start) / mass if mass > EPS else 0.0
    return {
        "id": node_id,
        "label": _text(node.get("label") or node.get("kind") or node_id, 120),
        "mass": mass,
        "raw_mass": raw_mass,
        "u0": cumulative,
        "u1": cumulative + mass,
        "x0": start,
        "x1": end,
        "slope": slope,
        "kind": _text(node.get("kind"), 80),
        "metadata": node.get("metadata") if isinstance(node.get("metadata"), dict) else {},
    }


def _sort_key(node: dict[str, Any]) -> tuple[float, str]:
    if "interval" in node and isinstance(node.get("interval"), dict):
        interval = _dict(node.get("interval"))
        start = _num(interval.get("start"), _num(interval.get("min"), 0.0))
        end = _num(interval.get("end"), _num(interval.get("max"), start))
        return ((start + end) / 2.0, _clean_id(node.get("id")))
    if node.get("continuous"):
        start = _num(node.get("start"), _num(node.get("position"), 0.0))
        end = _num(node.get("end"), start)
        return ((start + end) / 2.0, _clean_id(node.get("id")))
    return (_num(node.get("position"), _num(node.get("coordinate"), 0.0)), _clean_id(node.get("id")))


def _validate_nodes(nodes: list[dict[str, Any]], role: str) -> tuple[bool, str]:
    if not nodes:
        return False, f"{role}_empty"
    total = sum(max(0.0, _num(node.get("mass"), 0.0)) for node in nodes)
    if total <= EPS:
        return False, f"{role}_zero_mass"
    intervals: list[tuple[float, float, str]] = []
    for node in nodes:
        if "dimension" in node and str(node.get("dimension")) not in {"", "1", "1d", "one_dimensional"}:
            return False, f"{role}_non_1d_node_rejected"
        if "position" not in node and "coordinate" not in node and "interval" not in node and not node.get("continuous"):
            return False, f"{role}_node_missing_position_or_interval"
        if "interval" in node or node.get("continuous"):
            if "interval" in node and isinstance(node.get("interval"), dict):
                interval = _dict(node.get("interval"))
                start = _num(interval.get("start"), _num(interval.get("min"), 0.0))
                end = _num(interval.get("end"), _num(interval.get("max"), start))
            else:
                start = _num(node.get("start"), _num(node.get("position"), 0.0))
                end = _num(node.get("end"), start)
            if end < start:
                start, end = end, start
            intervals.append((start, end, _clean_id(node.get("id"))))
    intervals.sort()
    for left, right in zip(intervals, intervals[1:]):
        if left[1] > right[0] + EPS:
            return False, f"{role}_overlapping_continuous_intervals_rejected_for_exact_quantile_mode"
    return True, ""


def _segments(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(nodes, key=_sort_key)
    total = sum(max(0.0, _num(node.get("mass"), 0.0)) for node in ordered)
    out: list[dict[str, Any]] = []
    cumulative = 0.0
    for node in ordered:
        if _num(node.get("mass"), 0.0) <= EPS:
            continue
        seg = _node_to_segment(node, total, cumulative)
        out.append(seg)
        cumulative = seg["u1"]
    if out:
        out[-1]["u1"] = 1.0
        out[-1]["mass"] = max(0.0, out[-1]["u1"] - out[-1]["u0"])
    return out


def _integral_abs_linear(a: float, b: float, length: float) -> float:
    if length <= EPS:
        return 0.0
    if abs(b) <= EPS:
        return abs(a) * length

    def primitive(t: float) -> float:
        return a * t + 0.5 * b * t * t

    root = -a / b
    if EPS < root < length - EPS:
        return abs(primitive(root) - primitive(0.0)) + abs(primitive(length) - primitive(root))
    return abs(primitive(length) - primitive(0.0))


def _integral_square_linear(a: float, b: float, length: float) -> float:
    if length <= EPS:
        return 0.0
    return a * a * length + a * b * length * length + (b * b * length * length * length) / 3.0


def solve_quantile_optimal_transport(
    supply: list[dict[str, Any]],
    demand: list[dict[str, Any]],
    *,
    p: int = 1,
    base_url: str = "",
) -> dict[str, Any]:
    """Solve exact 1D Wasserstein transport for declared quantile measures."""

    if p not in {1, 2}:
        return {
            "ok": False,
            "schema": ERROR_SCHEMA,
            "error": "unsupported_wasserstein_order",
            "message": "Exact hosted OT currently supports p=1 and p=2 on one-dimensional quantile measures.",
        }
    supply_ok, supply_issue = _validate_nodes(supply, "supply")
    demand_ok, demand_issue = _validate_nodes(demand, "demand")
    if not supply_ok or not demand_ok:
        return {
            "ok": False,
            "schema": ERROR_SCHEMA,
            "error": supply_issue or demand_issue,
            "message": "Supply and demand must be positive one-dimensional atoms or non-overlapping piecewise-uniform intervals.",
        }

    s_segments = _segments(supply)
    d_segments = _segments(demand)
    i = j = 0
    s_offset = d_offset = 0.0
    total_cost = 0.0
    plan: list[dict[str, Any]] = []
    while i < len(s_segments) and j < len(d_segments):
        s = s_segments[i]
        d = d_segments[j]
        s_left = max(0.0, s["mass"] - s_offset)
        d_left = max(0.0, d["mass"] - d_offset)
        amount = min(s_left, d_left)
        if amount <= EPS:
            if s_left <= EPS:
                i += 1
                s_offset = 0.0
            if d_left <= EPS:
                j += 1
                d_offset = 0.0
            continue
        s_x = s["x0"] + s["slope"] * s_offset
        d_x = d["x0"] + d["slope"] * d_offset
        a = s_x - d_x
        b = s["slope"] - d["slope"]
        contribution = _integral_abs_linear(a, b, amount) if p == 1 else _integral_square_linear(a, b, amount)
        total_cost += contribution
        plan.append(
            {
                "source_id": s["id"],
                "target_id": d["id"],
                "amount": round(amount, 12),
                "source_interval": [round(s_x, 12), round(s_x + s["slope"] * amount, 12)],
                "target_interval": [round(d_x, 12), round(d_x + d["slope"] * amount, 12)],
                "cost_contribution": round(contribution, 12),
            }
        )
        s_offset += amount
        d_offset += amount
        if s_offset >= s["mass"] - EPS:
            i += 1
            s_offset = 0.0
        if d_offset >= d["mass"] - EPS:
            j += 1
            d_offset = 0.0

    wasserstein = total_cost if p == 1 else math.sqrt(max(0.0, total_cost))
    digest_core = {
        "p": p,
        "supply": [(seg["id"], seg["mass"], seg["x0"], seg["x1"]) for seg in s_segments],
        "demand": [(seg["id"], seg["mass"], seg["x0"], seg["x1"]) for seg in d_segments],
        "cost": round(total_cost, 12),
    }
    return {
        "ok": True,
        "schema": PLAN_SCHEMA,
        "generated_at": _iso_now(),
        "plan_digest": f"nomad-ot-plan-{_digest(digest_core)}",
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "metric": f"W{p}",
        "p": p,
        "ground_cost": "|x-y|^p_on_declared_1d_pressure_axis",
        "solver": "exact_1d_quantile_monge_transport_no_sinkhorn_no_softmax",
        "normalization": "supply_and_demand_masses_are_independently_normalized_to_probability_measures",
        "wasserstein_distance": round(wasserstein, 12),
        "transport_cost": round(total_cost, 12),
        "transport_plan": plan,
        "supply_quantile_segments": s_segments,
        "demand_quantile_segments": d_segments,
        "exactness_boundary": {
            "exact_for": [
                "discrete_atoms_on_one_declared_axis",
                "non_overlapping_piecewise_uniform_continuous_intervals_on_one_declared_axis",
                "p_equals_1_or_2",
            ],
            "rejected_as_not_exact_here": [
                "multi_dimensional_measures_without_explicit_reduction",
                "overlapping_continuous_intervals",
                "entropic_sinkhorn_or_softmax_approximations",
            ],
        },
    }


def compile_nomad_ot_problem(
    *,
    base_url: str,
    compute_market: dict[str, Any] | None = None,
    value_pressure: dict[str, Any] | None = None,
    settlement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile live Nomad surfaces into a declared 1D OT routing problem."""

    compute = _dict(compute_market)
    pressure = _dict(value_pressure)
    settlement_surface = _dict(settlement)
    supply: list[dict[str, Any]] = []
    for worker in _items(compute.get("scored_workers")):
        score = max(0.0, _num(worker.get("market_score"), 0.0))
        if score <= EPS:
            continue
        objective = _text(worker.get("objective") or "settlement_capacity_builder", 120)
        supply.append(
            {
                "id": worker.get("offer_id") or worker.get("agent_id") or f"worker-{len(supply)+1}",
                "label": worker.get("agent_id") or worker.get("offer_id") or objective,
                "mass": score,
                "position": _axis_position_from_objective(objective),
                "kind": "runtime_capacity",
                "metadata": {"objective": objective, "market_score": score},
            }
        )
    top_worker = _dict(compute.get("top_worker"))
    if not supply and top_worker:
        objective = _text(top_worker.get("objective") or "settlement_capacity_builder", 120)
        supply.append(
            {
                "id": top_worker.get("offer_id") or top_worker.get("agent_id") or "top_worker",
                "mass": max(0.01, _num(top_worker.get("market_score"), 0.1)),
                "position": _axis_position_from_objective(objective),
                "kind": "runtime_capacity",
                "metadata": {"objective": objective},
            }
        )
    if not supply:
        supply.append(
            {
                "id": "nomad_runtime_seed",
                "label": "Nomad baseline runtime",
                "mass": 1.0,
                "position": 0.28,
                "kind": "seed_runtime_capacity",
            }
        )

    demand: list[dict[str, Any]] = []
    for row in _items(pressure.get("rows"))[:12]:
        mass = max(0.0, _num(row.get("pressure_score"), 0.0))
        if mass <= EPS:
            continue
        demand.append(
            {
                "id": row.get("row_id") or f"pressure-{len(demand)+1}",
                "label": row.get("action") or row.get("kind") or row.get("source"),
                "mass": mass,
                "position": _axis_position_from_pressure_row(row),
                "kind": row.get("kind") or "pressure_row",
                "metadata": {
                    "source": row.get("source"),
                    "route": row.get("route"),
                    "action": row.get("action"),
                    "required_evidence": row.get("required_evidence") if isinstance(row.get("required_evidence"), list) else [],
                },
            }
        )
    settlement_top = _dict(settlement_surface.get("top") or settlement_surface.get("top_lane"))
    if settlement_top:
        demand.append(
            {
                "id": "settlement_pressure",
                "label": "settlement pressure",
                "mass": max(0.12, _num(settlement_top.get("pressure_score"), 0.24)),
                "position": 0.88,
                "kind": "settlement_pressure",
                "metadata": {"source": "settlement_signal_layer"},
            }
        )
    if not demand:
        demand.append(
            {
                "id": "settlement_capacity_builder",
                "label": "settlement capacity builder",
                "mass": 1.0,
                "position": 0.88,
                "kind": "settlement_pressure",
            }
        )

    return {
        "schema": "nomad.optimal_transport_problem.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "axis": {
            "name": "runtime_proof_settlement_pressure_axis",
            "range": [0.0, 1.0],
            "coordinate_contract": {
                "0.08": "runtime_protection_or_health_repair",
                "0.28": "lease_and_capacity_assignment",
                "0.56": "proof_generation_and_matching",
                "0.88": "settlement_or_paid_receipt_pressure",
            },
            "important_boundary": "OT is exact over declared coordinates; semantic coordinate assignment is an auditable model contract.",
        },
        "supply": supply,
        "demand": demand,
    }


def build_nomad_optimal_transport_surface(
    *,
    base_url: str,
    compute_market: dict[str, Any] | None = None,
    value_pressure: dict[str, Any] | None = None,
    settlement: dict[str, Any] | None = None,
    p: int = 1,
) -> dict[str, Any]:
    problem = compile_nomad_ot_problem(
        base_url=base_url,
        compute_market=compute_market,
        value_pressure=value_pressure,
        settlement=settlement,
    )
    plan = solve_quantile_optimal_transport(problem["supply"], problem["demand"], p=p, base_url=base_url)
    top_assignments = []
    if plan.get("ok"):
        top_assignments = sorted(
            plan.get("transport_plan") or [],
            key=lambda item: float(item.get("amount") or 0.0),
            reverse=True,
        )[:8]
    return {
        "ok": bool(plan.get("ok")),
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "read_url": _u(base_url, "/swarm/optimal-transport"),
        "well_known_url": _u(base_url, "/.well-known/nomad-optimal-transport.json"),
        "solve_url": _u(base_url, "/swarm/optimal-transport/solve"),
        "purpose": "exact_wasserstein_runtime_routing_for_leases_proofs_and_settlement_pressure",
        "mathematical_contract": {
            "formulation": "min_gamma integral |x-y|^p d_gamma over probability measures on one declared axis",
            "method": "1D quantile coupling / monotone rearrangement",
            "no_heuristic_substitutes": ["no_sinkhorn", "no_softmax", "no_majority_vote", "no_unlabeled_projection"],
            "continuous_support": "piecewise_uniform_intervals_are_integrated_exactly_in_quantile_space",
            "discrete_support": "atoms_are_exact_piecewise_constant_quantile_segments",
        },
        "compiled_problem": problem,
        "plan": plan,
        "top_assignments": top_assignments,
        "routing_contracts": {
            "weighted_runtime_routing": "assign supply mass to demand mass by OT amount descending",
            "lease_assignment": "prefer demand targets matched to runtime_capacity supply at low transport cost",
            "proof_matching": "route proof workers toward demand nodes near proof coordinate 0.56 unless OT cost says settlement pressure dominates",
            "settlement_pressure": "unmatched high-coordinate demand appears as mass near 0.88 and attracts capacity through Wasserstein distance",
        },
    }


def solve_ot_request(payload: dict[str, Any] | None, *, base_url: str = "") -> dict[str, Any]:
    body = _dict(payload)
    supply = _items(body.get("supply"))
    demand = _items(body.get("demand"))
    p = int(_num(body.get("p") or body.get("wasserstein_order"), 1))
    return solve_quantile_optimal_transport(supply, demand, p=p, base_url=base_url)
