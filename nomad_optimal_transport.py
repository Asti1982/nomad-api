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
MULTIAXIS_PLAN_SCHEMA = "nomad.dynamic_multiaxis_optimal_transport_plan.v1"
ERROR_SCHEMA = "nomad.optimal_transport_error.v1"

EPS = 1e-12
OT_AXES = ("capability", "proof_quality", "dynamics", "settlement")
DEFAULT_AXIS_WEIGHTS = {
    "capability": 0.28,
    "proof_quality": 0.27,
    "dynamics": 0.20,
    "settlement": 0.25,
}
MAX_COMPILED_ATOMS = 256


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


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in re.split(r"[, ]+", value) if item.strip()]
    return []


def _axis_weights(value: Any) -> dict[str, float]:
    raw = value if isinstance(value, dict) else {}
    weights = {axis: max(0.0, _num(raw.get(axis), DEFAULT_AXIS_WEIGHTS[axis])) for axis in OT_AXES}
    total = sum(weights.values())
    if total <= EPS:
        return dict(DEFAULT_AXIS_WEIGHTS)
    return {axis: weights[axis] / total for axis in OT_AXES}


def _keyword_score(text: str, table: tuple[tuple[str, float], ...], default: float = 0.5) -> float:
    lowered = text.lower()
    score = default
    for key, value in table:
        if key in lowered:
            score = max(score, value)
    return _clamp(score)


def _node_text(node: dict[str, Any]) -> str:
    fields = [
        node.get("id"),
        node.get("node_id"),
        node.get("label"),
        node.get("objective"),
        node.get("kind"),
        node.get("action"),
        node.get("target_stage"),
        node.get("current_stage"),
        node.get("problem_type"),
        node.get("route"),
    ]
    fields.extend(_list(node.get("capabilities")))
    fields.extend(_list(node.get("required_evidence")))
    return " ".join(_text(item, 160) for item in fields).lower()


def _capability_coordinate(text: str) -> float:
    return _keyword_score(
        text,
        (
            ("runtime", 0.08),
            ("health", 0.08),
            ("server", 0.08),
            ("repair", 0.12),
            ("lease", 0.28),
            ("capacity", 0.30),
            ("worker", 0.32),
            ("proof", 0.56),
            ("test", 0.58),
            ("review", 0.60),
            ("settlement", 0.88),
            ("receipt", 0.90),
            ("paid", 0.92),
        ),
        default=0.48,
    )


def _proof_coordinate(node: dict[str, Any], text: str) -> float:
    explicit = node.get("proof_quality")
    if explicit is not None:
        return _clamp(_num(explicit))
    for key in ("proof_score", "proof_signal", "reproducibility", "verifier_score"):
        if node.get(key) is not None:
            return _clamp(_num(node.get(key)))
    if _text(node.get("proof_digest") or node.get("verifier_trace_digest"), 40):
        return 0.86
    evidence = " ".join(str(item).lower() for item in _list(node.get("required_evidence")))
    if "proof" in evidence or "verifier" in evidence or "test" in evidence:
        return 0.72
    return _keyword_score(text, (("proof", 0.72), ("test", 0.70), ("verifier", 0.78), ("digest", 0.76)), default=0.42)


def _dynamics_coordinate(node: dict[str, Any], text: str) -> float:
    explicit = node.get("dynamics")
    if explicit is not None:
        return _clamp(_num(explicit))
    for key in ("dynamic_score", "urgency", "velocity", "pressure_score", "repeat_pressure"):
        if node.get(key) is not None:
            return _clamp(_num(node.get(key)) / (1.7 if key == "pressure_score" else 1.0))
    severity = _clean_id(node.get("severity"))
    if severity == "high":
        return 0.92
    if severity == "medium":
        return 0.66
    if severity == "low":
        return 0.32
    return _keyword_score(text, (("urgent", 0.86), ("restart", 0.82), ("failure", 0.78), ("stale", 0.64)), default=0.46)


def _settlement_coordinate(node: dict[str, Any], text: str) -> float:
    explicit = node.get("settlement")
    if explicit is not None:
        return _clamp(_num(explicit))
    for key in ("settlement_score", "receipt_proximity", "paid_probability"):
        if node.get(key) is not None:
            return _clamp(_num(node.get(key)))
    if _text(node.get("settlement_ref") or node.get("receipt_ref"), 80):
        return 0.86
    return _keyword_score(text, (("settlement", 0.86), ("receipt", 0.90), ("paid", 0.96), ("invoice", 0.82)), default=0.36)


def _vector_from_node(node: dict[str, Any]) -> dict[str, float]:
    axes = node.get("axes") if isinstance(node.get("axes"), dict) else {}
    vector = node.get("vector")
    if isinstance(vector, dict):
        axes = {**axes, **vector}
    elif isinstance(vector, list):
        axes = {**axes, **{axis: vector[index] for index, axis in enumerate(OT_AXES) if index < len(vector)}}
    coordinates = node.get("coordinates") if isinstance(node.get("coordinates"), dict) else {}
    axes = {**axes, **coordinates}
    if axes:
        return {axis: _clamp(_num(axes.get(axis), 0.5)) for axis in OT_AXES}
    text = _node_text(node)
    legacy_position = node.get("position") if node.get("position") is not None else node.get("coordinate")
    capability = _clamp(_num(legacy_position, _capability_coordinate(text))) if legacy_position is not None else _capability_coordinate(text)
    return {
        "capability": capability,
        "proof_quality": _proof_coordinate(node, text),
        "dynamics": _dynamics_coordinate(node, text),
        "settlement": _settlement_coordinate(node, text),
    }


def _range_for_axis(node: dict[str, Any], axis: str, center: float) -> tuple[float, float]:
    for key in ("box", "intervals", "ranges"):
        container = node.get(key)
        if isinstance(container, dict) and axis in container:
            raw = container.get(axis)
            if isinstance(raw, dict):
                start = _num(raw.get("start"), _num(raw.get("min"), center))
                end = _num(raw.get("end"), _num(raw.get("max"), center))
            elif isinstance(raw, list) and len(raw) >= 2:
                start = _num(raw[0], center)
                end = _num(raw[1], center)
            else:
                start = end = _num(raw, center)
            return (_clamp(min(start, end)), _clamp(max(start, end)))
    radius = _num(node.get(f"{axis}_radius"), 0.0)
    if radius > EPS:
        return (_clamp(center - radius), _clamp(center + radius))
    return (center, center)


def _compiled_atoms(
    nodes: list[dict[str, Any]],
    *,
    continuous_resolution: int = 3,
) -> tuple[bool, str, list[dict[str, Any]]]:
    atoms: list[dict[str, Any]] = []
    resolution = max(1, min(7, int(continuous_resolution or 1)))
    for node in nodes:
        mass = max(0.0, _num(node.get("mass"), 0.0))
        if mass <= EPS:
            continue
        node_id = _clean_id(node.get("id") or node.get("node_id"), f"node-{_digest(node, 8)}")
        vector = _vector_from_node(node)
        ranges = {axis: _range_for_axis(node, axis, vector[axis]) for axis in OT_AXES}
        continuous_axes = [axis for axis, (start, end) in ranges.items() if end - start > EPS]
        if not (node.get("continuous") or node.get("box") or node.get("intervals") or node.get("ranges")):
            continuous_axes = []
        axis_points: list[tuple[str, list[float]]] = []
        for axis in OT_AXES:
            start, end = ranges[axis]
            if axis in continuous_axes:
                width = (end - start) / resolution
                points = [start + width * (idx + 0.5) for idx in range(resolution)]
            else:
                points = [vector[axis]]
            axis_points.append((axis, points))
        product = 1
        for _axis, points in axis_points:
            product *= len(points)
        if len(atoms) + product > MAX_COMPILED_ATOMS:
            return False, "continuous_compilation_atom_limit_exceeded", []

        def build(index: int, current: dict[str, float]) -> None:
            if index >= len(axis_points):
                atoms.append(
                    {
                        "id": f"{node_id}#{len(atoms)+1}" if product > 1 else node_id,
                        "parent_id": node_id,
                        "mass": mass / product,
                        "vector": dict(current),
                        "kind": _text(node.get("kind"), 80),
                        "metadata": node.get("metadata") if isinstance(node.get("metadata"), dict) else {},
                    }
                )
                return
            axis, points = axis_points[index]
            for point in points:
                current[axis] = _clamp(point)
                build(index + 1, current)

        build(0, {})
    if not atoms:
        return False, "zero_compiled_mass", []
    return True, "", atoms


def _ground_distance(
    left: dict[str, float],
    right: dict[str, float],
    *,
    weights: dict[str, float],
    ground_metric_order: float,
) -> float:
    q = max(1.0, float(ground_metric_order or 2.0))
    total = 0.0
    for axis in OT_AXES:
        total += weights.get(axis, 0.0) * (abs(left.get(axis, 0.5) - right.get(axis, 0.5)) ** q)
    return total ** (1.0 / q)


def _normalize_atoms(atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = sum(max(0.0, _num(atom.get("mass"), 0.0)) for atom in atoms)
    if total <= EPS:
        return []
    out = []
    for atom in atoms:
        mass = max(0.0, _num(atom.get("mass"), 0.0)) / total
        if mass <= EPS:
            continue
        out.append({**atom, "mass": mass})
    return out


def _min_cost_transport(
    supply_atoms: list[dict[str, Any]],
    demand_atoms: list[dict[str, Any]],
    *,
    costs: list[list[float]],
) -> tuple[bool, str, list[list[float]], float]:
    m = len(supply_atoms)
    n = len(demand_atoms)
    source = 0
    supply_offset = 1
    demand_offset = 1 + m
    sink = 1 + m + n
    graph: list[list[dict[str, Any]]] = [[] for _ in range(sink + 1)]
    edge_refs: list[list[dict[str, int]]] = [[{} for _ in range(n)] for _ in range(m)]

    def add_edge(fr: int, to: int, cap: float, cost: float) -> int:
        fwd = {"to": to, "rev": len(graph[to]), "cap": cap, "cost": cost}
        rev = {"to": fr, "rev": len(graph[fr]), "cap": 0.0, "cost": -cost}
        graph[fr].append(fwd)
        graph[to].append(rev)
        return len(graph[fr]) - 1

    for i, atom in enumerate(supply_atoms):
        add_edge(source, supply_offset + i, _num(atom.get("mass")), 0.0)
    for i in range(m):
        for j in range(n):
            idx = add_edge(supply_offset + i, demand_offset + j, 1.0, costs[i][j])
            edge_refs[i][j] = {"node": supply_offset + i, "edge": idx}
    for j, atom in enumerate(demand_atoms):
        add_edge(demand_offset + j, sink, _num(atom.get("mass")), 0.0)

    flow = 0.0
    total_cost = 0.0
    max_iter = (m + n + 4) * max(2, m * n)
    for _ in range(max_iter):
        if flow >= 1.0 - 1e-10:
            break
        dist = [math.inf] * (sink + 1)
        prev: list[tuple[int, int] | None] = [None] * (sink + 1)
        dist[source] = 0.0
        for _relax in range(sink + 1):
            changed = False
            for u, edges in enumerate(graph):
                if not math.isfinite(dist[u]):
                    continue
                for ei, edge in enumerate(edges):
                    if edge["cap"] <= EPS:
                        continue
                    v = int(edge["to"])
                    nd = dist[u] + float(edge["cost"])
                    if nd + 1e-15 < dist[v]:
                        dist[v] = nd
                        prev[v] = (u, ei)
                        changed = True
            if not changed:
                break
        if prev[sink] is None:
            return False, "min_cost_flow_no_augmenting_path", [], total_cost
        aug = 1.0 - flow
        v = sink
        while v != source:
            u, ei = prev[v]  # type: ignore[misc]
            aug = min(aug, float(graph[u][ei]["cap"]))
            v = u
        v = sink
        while v != source:
            u, ei = prev[v]  # type: ignore[misc]
            edge = graph[u][ei]
            edge["cap"] -= aug
            graph[v][int(edge["rev"])]["cap"] += aug
            total_cost += aug * float(edge["cost"])
            v = u
        flow += aug
    if flow < 1.0 - 1e-8:
        return False, "min_cost_flow_incomplete", [], total_cost
    matrix = [[0.0 for _ in range(n)] for _ in range(m)]
    for i in range(m):
        for j in range(n):
            ref = edge_refs[i][j]
            edge = graph[ref["node"]][ref["edge"]]
            reverse = graph[int(edge["to"])][int(edge["rev"])]
            matrix[i][j] = max(0.0, float(reverse["cap"]))
    return True, "", matrix, total_cost


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


def solve_multiaxis_optimal_transport(
    supply: list[dict[str, Any]],
    demand: list[dict[str, Any]],
    *,
    p: float = 2.0,
    ground_metric_order: float = 2.0,
    axis_weights: dict[str, Any] | None = None,
    continuous_resolution: int = 3,
    base_url: str = "",
) -> dict[str, Any]:
    """Solve OT over Nomad's capability/proof/dynamics/settlement vector field.

    Finite atoms are solved exactly as a balanced discrete transportation
    problem. Continuous boxes are first compiled into deterministic finite-volume
    atoms; the returned plan is exact for that compiled empirical measure.
    """

    if p < 1:
        return {
            "ok": False,
            "schema": ERROR_SCHEMA,
            "error": "invalid_wasserstein_order",
            "message": "Wasserstein order p must be >= 1.",
        }
    weights = _axis_weights(axis_weights)
    supply_ok, supply_issue, supply_atoms_raw = _compiled_atoms(supply, continuous_resolution=continuous_resolution)
    demand_ok, demand_issue, demand_atoms_raw = _compiled_atoms(demand, continuous_resolution=continuous_resolution)
    if not supply_ok or not demand_ok:
        return {
            "ok": False,
            "schema": ERROR_SCHEMA,
            "error": supply_issue or demand_issue,
            "message": "Supply and demand must compile into positive finite atoms within the hosted atom limit.",
            "max_compiled_atoms": MAX_COMPILED_ATOMS,
        }
    supply_atoms = _normalize_atoms(supply_atoms_raw)
    demand_atoms = _normalize_atoms(demand_atoms_raw)
    if not supply_atoms or not demand_atoms:
        return {
            "ok": False,
            "schema": ERROR_SCHEMA,
            "error": "zero_probability_mass_after_normalization",
            "message": "Supply and demand must each have positive mass after normalization.",
        }

    ground: list[list[float]] = []
    costs: list[list[float]] = []
    for s_atom in supply_atoms:
        ground_row: list[float] = []
        cost_row: list[float] = []
        s_vec = s_atom["vector"] if isinstance(s_atom.get("vector"), dict) else {}
        for d_atom in demand_atoms:
            d_vec = d_atom["vector"] if isinstance(d_atom.get("vector"), dict) else {}
            distance = _ground_distance(s_vec, d_vec, weights=weights, ground_metric_order=ground_metric_order)
            ground_row.append(distance)
            cost_row.append(distance**p)
        ground.append(ground_row)
        costs.append(cost_row)

    flow_ok, flow_issue, matrix, total_cost = _min_cost_transport(supply_atoms, demand_atoms, costs=costs)
    if not flow_ok:
        return {
            "ok": False,
            "schema": ERROR_SCHEMA,
            "error": flow_issue,
            "message": "Discrete min-cost-flow transport failed to produce a balanced plan.",
        }

    transport_plan: list[dict[str, Any]] = []
    for i, s_atom in enumerate(supply_atoms):
        for j, d_atom in enumerate(demand_atoms):
            amount = matrix[i][j]
            if amount <= 1e-10:
                continue
            transport_plan.append(
                {
                    "source_id": s_atom["id"],
                    "source_parent_id": s_atom.get("parent_id", s_atom["id"]),
                    "target_id": d_atom["id"],
                    "target_parent_id": d_atom.get("parent_id", d_atom["id"]),
                    "amount": round(amount, 12),
                    "ground_distance": round(ground[i][j], 12),
                    "cost_contribution": round(amount * costs[i][j], 12),
                    "source_vector": {axis: round(_num(s_atom.get("vector", {}).get(axis)), 6) for axis in OT_AXES},
                    "target_vector": {axis: round(_num(d_atom.get("vector", {}).get(axis)), 6) for axis in OT_AXES},
                }
            )
    transport_plan.sort(key=lambda item: (float(item.get("amount") or 0.0), -float(item.get("ground_distance") or 0.0)), reverse=True)
    wasserstein = max(0.0, total_cost) ** (1.0 / p)
    digest_core = {
        "p": p,
        "ground_metric_order": ground_metric_order,
        "axis_weights": weights,
        "supply": [(atom["id"], atom["mass"], atom["vector"]) for atom in supply_atoms],
        "demand": [(atom["id"], atom["mass"], atom["vector"]) for atom in demand_atoms],
        "cost": round(total_cost, 12),
    }
    return {
        "ok": True,
        "schema": MULTIAXIS_PLAN_SCHEMA,
        "generated_at": _iso_now(),
        "plan_digest": f"nomad-dynamic-ot-plan-{_digest(digest_core)}",
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "metric": f"W{p:g}",
        "p": p,
        "ground_metric_order": ground_metric_order,
        "axes": list(OT_AXES),
        "axis_weights": {axis: round(weights[axis], 6) for axis in OT_AXES},
        "ground_cost": "weighted_Lq_distance(capability,proof_quality,dynamics,settlement)^p",
        "solver": "exact_balanced_discrete_min_cost_flow_on_compiled_atoms",
        "continuous_compilation": {
            "mode": "deterministic_finite_volume_atoms",
            "resolution_per_continuous_axis": continuous_resolution,
            "exactness": "exact_for_the_compiled_empirical_measure; exact_original_1d_intervals_remain_available_through_quantile_mode",
            "max_compiled_atoms": MAX_COMPILED_ATOMS,
        },
        "wasserstein_distance": round(wasserstein, 12),
        "transport_cost": round(total_cost, 12),
        "transport_plan": transport_plan,
        "supply_atoms": supply_atoms,
        "demand_atoms": demand_atoms,
        "exactness_boundary": {
            "exact_for": [
                "finite_discrete_measures_over_nomad_ot_axes",
                "deterministically_compiled_continuous_boxes_as_empirical_measures",
                "general_wasserstein_order_p_greater_equal_1",
                "weighted_lq_ground_metrics_over_capability_proof_dynamics_settlement",
            ],
            "not_claimed": [
                "closed_form_exact_multidimensional_continuous_ot_for_arbitrary_densities",
                "unverified_revenue_or_emergence_claims",
            ],
        },
    }


def solve_dynamic_multiaxis_optimal_transport(
    time_slices: list[dict[str, Any]],
    *,
    p: float = 2.0,
    ground_metric_order: float = 2.0,
    axis_weights: dict[str, Any] | None = None,
    continuous_resolution: int = 3,
    temporal_regularization: float = 0.08,
    base_url: str = "",
) -> dict[str, Any]:
    """Solve a sequence of multi-axis OT problems and expose plan churn."""

    if not time_slices:
        return {
            "ok": False,
            "schema": ERROR_SCHEMA,
            "error": "time_slices_empty",
            "message": "Dynamic OT requires at least one time slice.",
        }
    slice_plans: list[dict[str, Any]] = []
    total_cost = 0.0
    churn_cost = 0.0
    previous_pairs: dict[tuple[str, str], float] = {}
    for index, item in enumerate(time_slices):
        supply = _items(item.get("supply"))
        demand = _items(item.get("demand"))
        plan = solve_multiaxis_optimal_transport(
            supply,
            demand,
            p=p,
            ground_metric_order=ground_metric_order,
            axis_weights=axis_weights,
            continuous_resolution=continuous_resolution,
            base_url=base_url,
        )
        if not plan.get("ok"):
            return {**plan, "time_index": index}
        pairs = {
            (str(row.get("source_parent_id") or row.get("source_id")), str(row.get("target_parent_id") or row.get("target_id"))): _num(row.get("amount"))
            for row in plan.get("transport_plan") or []
            if isinstance(row, dict)
        }
        if previous_pairs:
            keys = set(previous_pairs) | set(pairs)
            churn = 0.5 * sum(abs(pairs.get(key, 0.0) - previous_pairs.get(key, 0.0)) for key in keys)
        else:
            churn = 0.0
        regularized = _num(plan.get("transport_cost")) + max(0.0, temporal_regularization) * churn
        total_cost += regularized
        churn_cost += churn
        slice_plans.append(
            {
                "time_index": index,
                "timestamp": item.get("timestamp") or item.get("t") or index,
                "transport_cost": plan.get("transport_cost"),
                "wasserstein_distance": plan.get("wasserstein_distance"),
                "plan_churn_from_previous": round(churn, 12),
                "regularized_cost": round(regularized, 12),
                "plan_digest": plan.get("plan_digest"),
                "top_transport": (plan.get("transport_plan") or [])[:8],
            }
        )
        previous_pairs = pairs
    dynamic_distance = max(0.0, total_cost) ** (1.0 / p)
    return {
        "ok": True,
        "schema": "nomad.dynamic_optimal_transport_plan.v1",
        "generated_at": _iso_now(),
        "plan_digest": f"nomad-dynamic-ot-sequence-{_digest(slice_plans)}",
        "metric": f"dynamic_W{p:g}",
        "p": p,
        "ground_metric_order": ground_metric_order,
        "axis_weights": {axis: round(_axis_weights(axis_weights)[axis], 6) for axis in OT_AXES},
        "temporal_regularization": max(0.0, temporal_regularization),
        "dynamic_wasserstein_distance": round(dynamic_distance, 12),
        "regularized_transport_cost": round(total_cost, 12),
        "plan_churn_total": round(churn_cost, 12),
        "slice_count": len(slice_plans),
        "slice_plans": slice_plans,
        "machine_instruction": "route_current_slice_by_top_transport_but_penalize_needless_assignment_churn_across_slices",
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
        market_score = _clamp(score)
        vector = {
            "capability": _axis_position_from_objective(objective),
            "proof_quality": _clamp(0.38 + 0.42 * market_score + (0.12 if _text(worker.get("proof_digest"), 40) else 0.0)),
            "dynamics": _clamp(0.34 + 0.46 * market_score),
            "settlement": 0.86 if "settlement" in _clean_id(objective) or _text(worker.get("settlement_ref"), 40) else 0.46,
        }
        supply.append(
            {
                "id": worker.get("offer_id") or worker.get("agent_id") or f"worker-{len(supply)+1}",
                "label": worker.get("agent_id") or worker.get("offer_id") or objective,
                "mass": score,
                "position": _axis_position_from_objective(objective),
                "vector": vector,
                "kind": "runtime_capacity",
                "metadata": {"objective": objective, "market_score": score},
            }
        )
    top_worker = _dict(compute.get("top_worker"))
    if not supply and top_worker:
        objective = _text(top_worker.get("objective") or "settlement_capacity_builder", 120)
        market_score = _clamp(_num(top_worker.get("market_score"), 0.1))
        supply.append(
            {
                "id": top_worker.get("offer_id") or top_worker.get("agent_id") or "top_worker",
                "mass": max(0.01, _num(top_worker.get("market_score"), 0.1)),
                "position": _axis_position_from_objective(objective),
                "vector": {
                    "capability": _axis_position_from_objective(objective),
                    "proof_quality": _clamp(0.38 + 0.42 * market_score),
                    "dynamics": _clamp(0.34 + 0.46 * market_score),
                    "settlement": 0.86 if "settlement" in _clean_id(objective) else 0.46,
                },
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
                "vector": {"capability": 0.28, "proof_quality": 0.45, "dynamics": 0.38, "settlement": 0.44},
                "kind": "seed_runtime_capacity",
            }
        )

    demand: list[dict[str, Any]] = []
    for row in _items(pressure.get("rows"))[:12]:
        mass = max(0.0, _num(row.get("pressure_score"), 0.0))
        if mass <= EPS:
            continue
        required_evidence = row.get("required_evidence") if isinstance(row.get("required_evidence"), list) else []
        target_stage = _clean_id(row.get("target_stage") or row.get("current_stage"))
        source = _clean_id(row.get("source"))
        receipt_pressure = 0.88 if any(term in target_stage for term in ("paid", "settled", "receipt")) else 0.38
        proof_pressure = 0.78 if any("proof" in str(item).lower() or "verifier" in str(item).lower() for item in required_evidence) else 0.46
        if source == "server_failure_guard":
            proof_pressure = max(proof_pressure, 0.72)
        demand.append(
            {
                "id": row.get("row_id") or f"pressure-{len(demand)+1}",
                "label": row.get("action") or row.get("kind") or row.get("source"),
                "mass": mass,
                "position": _axis_position_from_pressure_row(row),
                "vector": {
                    "capability": _axis_position_from_pressure_row(row),
                    "proof_quality": proof_pressure,
                    "dynamics": _clamp(mass / 1.7),
                    "settlement": receipt_pressure,
                },
                "kind": row.get("kind") or "pressure_row",
                "metadata": {
                    "source": row.get("source"),
                    "route": row.get("route"),
                    "action": row.get("action"),
                    "required_evidence": required_evidence,
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
                "vector": {"capability": 0.88, "proof_quality": 0.72, "dynamics": 0.62, "settlement": 0.94},
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
                "vector": {"capability": 0.88, "proof_quality": 0.64, "dynamics": 0.48, "settlement": 0.9},
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
        "vector_axes": {
            "names": list(OT_AXES),
            "axis_weights": DEFAULT_AXIS_WEIGHTS,
            "coordinate_contract": {
                "capability": "semantic runtime capability class: protection/capacity/proof/settlement",
                "proof_quality": "verifier, digest, failing-test, and evidence strength",
                "dynamics": "urgency, instability, repeat pressure, and route velocity",
                "settlement": "paid receipt, settlement, invoice, or return-compute proximity",
            },
            "important_boundary": "coordinates are auditable routing features, not claims that the world has only four dimensions",
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
    p: float = 2.0,
) -> dict[str, Any]:
    problem = compile_nomad_ot_problem(
        base_url=base_url,
        compute_market=compute_market,
        value_pressure=value_pressure,
        settlement=settlement,
    )
    plan = solve_multiaxis_optimal_transport(
        problem["supply"],
        problem["demand"],
        p=p,
        ground_metric_order=2.0,
        axis_weights=DEFAULT_AXIS_WEIGHTS,
        continuous_resolution=3,
        base_url=base_url,
    )
    legacy_quantile_plan = solve_quantile_optimal_transport(problem["supply"], problem["demand"], p=1 if p != 2 else 2, base_url=base_url)
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
        "purpose": "dynamic_discrete_continuous_wasserstein_routing_for_capabilities_proof_quality_dynamics_and_settlement",
        "mathematical_contract": {
            "formulation": "min_gamma integral d(x,y)^p d_gamma over probability measures on Nomad feature space",
            "feature_space": list(OT_AXES),
            "ground_metric": "weighted_Lq over capability, proof_quality, dynamics, settlement",
            "method": "exact balanced discrete min-cost flow over finite atoms plus exact 1D quantile mode for declared one-axis intervals",
            "no_heuristic_substitutes": ["no_sinkhorn", "no_softmax", "no_majority_vote", "no_unlabeled_projection"],
            "continuous_support": "1D non-overlapping intervals are exact via quantile mode; multi-axis boxes compile to deterministic finite-volume empirical measures",
            "discrete_support": "finite atoms are solved by min-cost-flow transport for general p>=1",
            "dynamic_support": "POST time_slices to solve sequence plans with temporal churn regularization",
        },
        "compiled_problem": problem,
        "plan": plan,
        "legacy_1d_quantile_plan": legacy_quantile_plan,
        "top_assignments": top_assignments,
        "routing_contracts": {
            "weighted_runtime_routing": "assign supply mass to demand mass by OT amount descending",
            "lease_assignment": "prefer demand targets matched to runtime_capacity supply at low transport cost",
            "capability_matching": "capability distance is only one axis; high proof, dynamics, or settlement pressure can override human-looking task labels",
            "proof_matching": "route proof workers toward high proof_quality demand unless settlement or instability distance dominates",
            "dynamic_stability": "repeat failures and high-velocity work appear on the dynamics axis and can attract capacity before growth work",
            "settlement_pressure": "paid/receipt demand appears on the settlement axis and attracts capacity through Wasserstein distance",
        },
    }


def solve_ot_request(payload: dict[str, Any] | None, *, base_url: str = "") -> dict[str, Any]:
    body = _dict(payload)
    p = _num(body.get("p") or body.get("wasserstein_order"), 1.0)
    if body.get("time_slices"):
        return solve_dynamic_multiaxis_optimal_transport(
            _items(body.get("time_slices")),
            p=p,
            ground_metric_order=_num(body.get("ground_metric_order"), 2.0),
            axis_weights=body.get("axis_weights") if isinstance(body.get("axis_weights"), dict) else None,
            continuous_resolution=int(_num(body.get("continuous_resolution"), 3)),
            temporal_regularization=_num(body.get("temporal_regularization"), 0.08),
            base_url=base_url,
        )
    supply = _items(body.get("supply"))
    demand = _items(body.get("demand"))
    mode = _clean_id(body.get("mode") or body.get("solver"))
    multi_signal = bool(
        mode in {"multiaxis", "multi_axis", "dynamic", "discrete_continuous"}
        or body.get("axis_weights")
        or body.get("ground_metric_order")
        or any(any(key in node for key in ("vector", "axes", "coordinates", "box", "intervals", "ranges")) for node in supply + demand)
    )
    if multi_signal:
        return solve_multiaxis_optimal_transport(
            supply,
            demand,
            p=p,
            ground_metric_order=_num(body.get("ground_metric_order"), 2.0),
            axis_weights=body.get("axis_weights") if isinstance(body.get("axis_weights"), dict) else None,
            continuous_resolution=int(_num(body.get("continuous_resolution"), 3)),
            base_url=base_url,
        )
    return solve_quantile_optimal_transport(supply, demand, p=int(p), base_url=base_url)
