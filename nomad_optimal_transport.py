"""Optimal Transport routing kernel for Nomad.

This module implements the part of OT that can be exact inside the hosted
runtime boundary. Finite measures over Nomad's capability/proof/dynamics/
settlement axes are solved as balanced discrete min-cost-flow transport for
general Wasserstein order p >= 1 and weighted Lq ground metrics. Continuous
multi-axis boxes are compiled into deterministic finite-volume empirical atoms;
the returned plan is exact for that compiled measure, not a closed-form answer
for arbitrary multi-dimensional densities. The legacy one-dimensional quantile
mode remains available for exact W1/W2 transport over declared non-overlapping
intervals. The module deliberately does not use Sinkhorn, softmax routing, or a
projection trick while calling the result exact.
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
MANIFOLD_SLICE_SCHEMA = "nomad.ot_manifold_slice.v1"
DYNAMIC_MANIFOLD_SCHEMA = "nomad.dynamic_ot_manifold.v1"
MANIFOLD_SURFACE_SCHEMA = "nomad.ot_manifold_surface.v1"
PAPER_READINESS_SCHEMA = "nomad.optimal_transport_paper_readiness.v1"
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
                        "compiled_from_continuous": bool(continuous_axes),
                        "continuous_axes": list(continuous_axes),
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


def _round_vector(vector: dict[str, Any], digits: int = 6) -> dict[str, float]:
    return {axis: round(_num(vector.get(axis), 0.0), digits) for axis in OT_AXES}


def _zero_vector() -> dict[str, float]:
    return {axis: 0.0 for axis in OT_AXES}


def _vector_add_scaled(target: dict[str, float], vector: dict[str, Any], amount: float) -> None:
    for axis in OT_AXES:
        target[axis] = target.get(axis, 0.0) + amount * _num(vector.get(axis), 0.0)


def _vector_divide(vector: dict[str, float], amount: float) -> dict[str, float]:
    if amount <= EPS:
        return _zero_vector()
    return {axis: vector.get(axis, 0.0) / amount for axis in OT_AXES}


def _weighted_barycenter(atoms: list[dict[str, Any]]) -> dict[str, float]:
    total = sum(max(0.0, _num(atom.get("mass"), 0.0)) for atom in atoms)
    accum = _zero_vector()
    for atom in atoms:
        _vector_add_scaled(accum, _dict(atom.get("vector")), max(0.0, _num(atom.get("mass"), 0.0)))
    return _round_vector(_vector_divide(accum, total))


def _dominant_axis(vector: dict[str, Any]) -> str:
    if not vector:
        return ""
    return max(OT_AXES, key=lambda axis: abs(_num(vector.get(axis), 0.0)))


def _axis_action(axis: str, signed: float) -> str:
    direction = "increase" if signed >= 0 else "decrease"
    if axis == "capability":
        target = "runtime capability fit"
    elif axis == "proof_quality":
        target = "proof/verifier strength"
    elif axis == "dynamics":
        target = "instability and velocity response"
    else:
        target = "settlement and receipt proximity"
    return f"{direction}_{target.replace(' ', '_')}"


def build_transport_manifold(
    plan: dict[str, Any],
    *,
    p: float | None = None,
    ground_metric_order: float | None = None,
    axis_weights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile a finite OT plan into a concrete 4D barycentric displacement field."""

    if not plan.get("ok"):
        return {
            "ok": False,
            "schema": MANIFOLD_SLICE_SCHEMA,
            "error": "source_plan_not_ok",
            "source_plan_digest": plan.get("plan_digest", ""),
        }
    weights = _axis_weights(axis_weights or plan.get("axis_weights"))
    supply_atoms = _items(plan.get("supply_atoms"))
    demand_atoms = _items(plan.get("demand_atoms"))
    rows = _items(plan.get("transport_plan"))
    supply_barycenter = _weighted_barycenter(supply_atoms)
    demand_barycenter = _weighted_barycenter(demand_atoms)
    deficit = {axis: demand_barycenter[axis] - supply_barycenter[axis] for axis in OT_AXES}
    axis_stats: dict[str, dict[str, float]] = {
        axis: {"signed_mass": 0.0, "positive_mass": 0.0, "negative_mass": 0.0, "absolute_mass": 0.0}
        for axis in OT_AXES
    }
    source_map: dict[str, dict[str, Any]] = {}
    target_map: dict[str, dict[str, Any]] = {}
    coupling: dict[tuple[str, str], float] = {}
    flow_field: list[dict[str, Any]] = []
    for row in rows:
        amount = max(0.0, _num(row.get("amount"), 0.0))
        if amount <= EPS:
            continue
        source_vector = _dict(row.get("source_vector"))
        target_vector = _dict(row.get("target_vector"))
        delta = {axis: _num(target_vector.get(axis), 0.0) - _num(source_vector.get(axis), 0.0) for axis in OT_AXES}
        for axis in OT_AXES:
            signed = amount * delta[axis]
            axis_stats[axis]["signed_mass"] += signed
            axis_stats[axis]["positive_mass"] += max(0.0, signed)
            axis_stats[axis]["negative_mass"] += max(0.0, -signed)
            axis_stats[axis]["absolute_mass"] += abs(signed)
        for idx, left in enumerate(OT_AXES):
            for right in OT_AXES[idx + 1 :]:
                coupling[(left, right)] = coupling.get((left, right), 0.0) + amount * delta[left] * delta[right]
        source_id = str(row.get("source_parent_id") or row.get("source_id") or "source")
        target_id = str(row.get("target_parent_id") or row.get("target_id") or "target")
        source_bucket = source_map.setdefault(source_id, {"id": source_id, "mass": 0.0, "source_sum": _zero_vector(), "target_sum": _zero_vector()})
        target_bucket = target_map.setdefault(target_id, {"id": target_id, "mass": 0.0, "source_sum": _zero_vector(), "target_sum": _zero_vector()})
        for bucket in (source_bucket, target_bucket):
            bucket["mass"] += amount
            _vector_add_scaled(bucket["source_sum"], source_vector, amount)
            _vector_add_scaled(bucket["target_sum"], target_vector, amount)
        flow_field.append(
            {
                "source_id": source_id,
                "target_id": target_id,
                "amount": round(amount, 12),
                "source_vector": _round_vector(source_vector),
                "target_vector": _round_vector(target_vector),
                "displacement": _round_vector(delta),
                "dominant_axis": _dominant_axis(delta),
                "ground_distance": round(_num(row.get("ground_distance"), 0.0), 12),
            }
        )
    barycentric_map: list[dict[str, Any]] = []
    for bucket in source_map.values():
        mass = _num(bucket.get("mass"), 0.0)
        source_mean = _vector_divide(bucket["source_sum"], mass)
        target_mean = _vector_divide(bucket["target_sum"], mass)
        displacement = {axis: target_mean[axis] - source_mean[axis] for axis in OT_AXES}
        barycentric_map.append(
            {
                "source_id": bucket["id"],
                "mass": round(mass, 12),
                "source_barycenter": _round_vector(source_mean),
                "target_barycenter": _round_vector(target_mean),
                "displacement": _round_vector(displacement),
                "dominant_axis": _dominant_axis(displacement),
                "action_hint": _axis_action(_dominant_axis(displacement), _num(displacement.get(_dominant_axis(displacement)), 0.0)),
            }
        )
    target_inflow_map: list[dict[str, Any]] = []
    for bucket in target_map.values():
        mass = _num(bucket.get("mass"), 0.0)
        source_mean = _vector_divide(bucket["source_sum"], mass)
        target_mean = _vector_divide(bucket["target_sum"], mass)
        displacement = {axis: target_mean[axis] - source_mean[axis] for axis in OT_AXES}
        target_inflow_map.append(
            {
                "target_id": bucket["id"],
                "mass": round(mass, 12),
                "incoming_source_barycenter": _round_vector(source_mean),
                "target_barycenter": _round_vector(target_mean),
                "required_displacement": _round_vector(displacement),
                "dominant_axis": _dominant_axis(displacement),
            }
        )
    barycentric_map.sort(key=lambda item: float(item.get("mass") or 0.0), reverse=True)
    target_inflow_map.sort(key=lambda item: float(item.get("mass") or 0.0), reverse=True)
    flow_field.sort(key=lambda item: float(item.get("amount") or 0.0), reverse=True)
    axis_pressure = {
        axis: {
            key: round(value, 12)
            for key, value in {
                **stats,
                "direction": 1.0 if stats["signed_mass"] >= 0 else -1.0,
                "weight": weights.get(axis, 0.0),
            }.items()
        }
        for axis, stats in axis_stats.items()
    }
    route_gradient = sorted(
        (
            {
                "axis": axis,
                "signed_mass": round(stats["signed_mass"], 12),
                "absolute_mass": round(stats["absolute_mass"], 12),
                "action_hint": _axis_action(axis, stats["signed_mass"]),
            }
            for axis, stats in axis_stats.items()
        ),
        key=lambda item: abs(float(item["signed_mass"])) + float(item["absolute_mass"]),
        reverse=True,
    )
    top_coupling = sorted(
        (
            {"axes": [left, right], "signed_coupling": round(value, 12), "absolute_coupling": round(abs(value), 12)}
            for (left, right), value in coupling.items()
        ),
        key=lambda item: float(item["absolute_coupling"]),
        reverse=True,
    )[:6]
    dominant = _dominant_axis(deficit)
    continuous_sources = {
        str(atom.get("parent_id") or atom.get("id"))
        for atom in supply_atoms + demand_atoms
        if atom.get("compiled_from_continuous")
    }
    digest_core = {
        "source_plan": plan.get("plan_digest"),
        "deficit": _round_vector(deficit),
        "route_gradient": route_gradient,
        "barycentric": barycentric_map[:8],
    }
    return {
        "ok": True,
        "schema": MANIFOLD_SLICE_SCHEMA,
        "generated_at": _iso_now(),
        "source_plan_digest": plan.get("plan_digest", ""),
        "manifold_digest": f"nomad-ot-manifold-{_digest(digest_core)}",
        "feature_space": {
            "axes": list(OT_AXES),
            "domain": "[0,1]^4_empirical_nomad_feature_cube",
            "metric": "weighted_Lq_ground_metric_lifted_to_Wp_on_compiled_measures",
            "p": _num(p, _num(plan.get("p"), 2.0)),
            "ground_metric_order": _num(ground_metric_order, _num(plan.get("ground_metric_order"), 2.0)),
            "axis_weights": {axis: round(weights[axis], 6) for axis in OT_AXES},
        },
        "measure_barycenters": {
            "supply": supply_barycenter,
            "demand": demand_barycenter,
            "deficit_vector": _round_vector(deficit),
            "dominant_deficit_axis": dominant,
            "dominant_action_hint": _axis_action(dominant, _num(deficit.get(dominant), 0.0)) if dominant else "",
        },
        "axis_pressure": axis_pressure,
        "route_gradient": route_gradient,
        "barycentric_map": barycentric_map[:12],
        "target_inflow_map": target_inflow_map[:12],
        "flow_field": flow_field[:24],
        "cross_axis_coupling": top_coupling,
        "compiled_measure": {
            "supply_atom_count": len(supply_atoms),
            "demand_atom_count": len(demand_atoms),
            "continuous_parent_count": len(continuous_sources),
            "continuous_parent_ids": sorted(continuous_sources)[:24],
            "exactness": "exact_barycentric_and_coupling_statistics_for_the_returned_finite_transport_plan",
        },
        "claim_boundary": {
            "exact_for": [
                "barycentric_projection_of_the_exact_finite_transport_plan",
                "axis_pressure_and_cross_axis_coupling_over_returned_transport_rows",
                "compiled_empirical_continuous_atoms_after_deterministic_finite_volume_compilation",
            ],
            "not_claimed": [
                "closed_form_riemannian_manifold_learning",
                "arbitrary_continuous_density_ot_solution",
                "human_interpretability_of_latent_coordinate_semantics",
            ],
        },
        "machine_instruction": "treat the dominant route_gradient axes as the concrete OT displacement field for worker routing; recompute after every receipt, failure, or capability update",
    }


def build_dynamic_transport_manifold(
    slice_manifolds: list[dict[str, Any]],
    *,
    p: float,
    ground_metric_order: float,
    axis_weights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    weights = _axis_weights(axis_weights)
    trajectory: list[dict[str, Any]] = []
    previous_deficit: dict[str, float] | None = None
    total_drift = _zero_vector()
    for index, manifold in enumerate(slice_manifolds):
        bary = _dict(manifold.get("measure_barycenters"))
        deficit = {axis: _num(_dict(bary.get("deficit_vector")).get(axis), 0.0) for axis in OT_AXES}
        drift = _zero_vector() if previous_deficit is None else {axis: deficit[axis] - previous_deficit.get(axis, 0.0) for axis in OT_AXES}
        for axis in OT_AXES:
            total_drift[axis] += abs(drift[axis])
        trajectory.append(
            {
                "time_index": index,
                "source_plan_digest": manifold.get("source_plan_digest", ""),
                "deficit_vector": _round_vector(deficit),
                "deficit_drift_from_previous": _round_vector(drift),
                "dominant_deficit_axis": bary.get("dominant_deficit_axis", ""),
                "top_route_gradient": (_items(manifold.get("route_gradient")) or [])[:4],
            }
        )
        previous_deficit = deficit
    dominant_drift_axis = _dominant_axis(total_drift)
    digest_core = {"trajectory": trajectory, "weights": weights, "p": p, "q": ground_metric_order}
    return {
        "ok": True,
        "schema": DYNAMIC_MANIFOLD_SCHEMA,
        "generated_at": _iso_now(),
        "manifold_digest": f"nomad-dynamic-ot-manifold-{_digest(digest_core)}",
        "feature_space": {
            "axes": list(OT_AXES),
            "domain": "[0,1]^4_time_sliced_empirical_nomad_feature_cube",
            "metric": "dynamic_Wp_over_weighted_Lq_ground_metric_with_temporal_drift_observation",
            "p": p,
            "ground_metric_order": ground_metric_order,
            "axis_weights": {axis: round(weights[axis], 6) for axis in OT_AXES},
        },
        "trajectory": trajectory,
        "temporal_drift": {
            "total_absolute_deficit_drift": _round_vector(total_drift),
            "dominant_drift_axis": dominant_drift_axis,
            "dominant_drift_action_hint": _axis_action(dominant_drift_axis, _num(total_drift.get(dominant_drift_axis), 0.0)) if dominant_drift_axis else "",
        },
        "claim_boundary": {
            "exact_for": [
                "per_slice_manifold_statistics_of_each_exact_finite_transport_plan",
                "temporal_drift_statistics_between_returned_slice_deficit_vectors",
            ],
            "not_claimed": [
                "continuous_time_geodesic_solution_for_arbitrary_density_paths",
                "closed_form_multidimensional_continuous_ot",
            ],
        },
        "machine_instruction": "route by the current slice gradient, but allocate exploration pressure to axes with rising temporal drift before they become settlement or reliability failures",
    }


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
    result = {
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
    result["manifold"] = build_transport_manifold(
        result,
        p=p,
        ground_metric_order=ground_metric_order,
        axis_weights=weights,
    )
    return result


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
    slice_manifolds: list[dict[str, Any]] = []
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
        manifold = build_transport_manifold(
            plan,
            p=p,
            ground_metric_order=ground_metric_order,
            axis_weights=axis_weights,
        )
        slice_manifolds.append(manifold)
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
                "manifold_slice": {
                    "schema": manifold.get("schema"),
                    "manifold_digest": manifold.get("manifold_digest"),
                    "measure_barycenters": manifold.get("measure_barycenters"),
                    "top_route_gradient": (_items(manifold.get("route_gradient")) or [])[:4],
                },
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
        "dynamic_manifold": build_dynamic_transport_manifold(
            slice_manifolds,
            p=p,
            ground_metric_order=ground_metric_order,
            axis_weights=axis_weights,
        ),
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
        "paper_readiness_url": _u(base_url, "/.well-known/nomad-ot-paper-readiness.json"),
        "manifold_url": _u(base_url, "/.well-known/nomad-ot-manifold.json"),
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
            "manifold_support": "finite transport plans compile into barycentric displacement fields, axis-pressure tensors, and temporal drift statistics",
        },
        "compiled_problem": problem,
        "plan": plan,
        "manifold": plan.get("manifold") if isinstance(plan.get("manifold"), dict) else {},
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


def build_ot_manifold_surface(
    *,
    base_url: str,
    ot_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    surface = _dict(ot_surface)
    if not surface:
        surface = build_nomad_optimal_transport_surface(base_url=base_url)
    plan = _dict(surface.get("plan"))
    manifold = _dict(plan.get("manifold") or surface.get("manifold"))
    if not manifold and plan.get("ok"):
        manifold = build_transport_manifold(plan)
    return {
        "ok": bool(manifold.get("ok")),
        "schema": MANIFOLD_SURFACE_SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "read_url": _u(base_url, "/swarm/optimal-transport/manifold"),
        "well_known_url": _u(base_url, "/.well-known/nomad-ot-manifold.json"),
        "ot_surface_url": _u(base_url, "/.well-known/nomad-optimal-transport.json"),
        "paper_readiness_url": _u(base_url, "/.well-known/nomad-ot-paper-readiness.json"),
        "solve_url": _u(base_url, "/swarm/optimal-transport/solve"),
        "purpose": "concrete_unified_empirical_ot_manifold_for_machine_routing",
        "manifold": manifold,
        "current_top_assignments": surface.get("top_assignments") or [],
        "claim_boundary": {
            "exact_for": [
                "barycentric_displacement_field_of_the_current_exact_finite_ot_plan",
                "axis_pressure_and_cross_axis_coupling_of_the_current_returned_transport_rows",
                "compiled_empirical_continuous_measure_after_finite_volume_atomization",
            ],
            "not_claimed": [
                "closed_form_manifold_learning",
                "arbitrary_multidimensional_continuous_ot",
                "agent_economy_revenue_proof_without_receipts",
            ],
        },
        "machine_instruction": "read manifold.route_gradient and manifold.barycentric_map before choosing leases; post time_slices to /swarm/optimal-transport/solve for dynamic manifold drift",
    }


def build_ot_paper_readiness_surface(
    *,
    base_url: str,
    ot_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose the honest paper-near boundary of Nomad's OT implementation."""

    surface = _dict(ot_surface)
    if not surface:
        surface = build_nomad_optimal_transport_surface(base_url=base_url)
    plan = _dict(surface.get("plan"))
    legacy = _dict(surface.get("legacy_1d_quantile_plan"))
    manifold = _dict(plan.get("manifold") or surface.get("manifold"))
    compiled = _dict(plan.get("continuous_compilation"))
    plan_boundary = _dict(plan.get("exactness_boundary"))
    legacy_boundary = _dict(legacy.get("exactness_boundary"))
    readiness_checks = {
        "primary_multiaxis_discrete_solver_ok": bool(plan.get("ok"))
        and plan.get("solver") == "exact_balanced_discrete_min_cost_flow_on_compiled_atoms",
        "compiled_continuous_empirical_measure_declared": compiled.get("mode") == "deterministic_finite_volume_atoms",
        "legacy_exact_1d_quantile_solver_available": bool(legacy.get("ok"))
        and legacy.get("solver") == "exact_1d_quantile_monge_transport_no_sinkhorn_no_softmax",
        "four_axis_nomad_feature_space_declared": plan.get("axes") == list(OT_AXES)
        or _dict(surface.get("mathematical_contract")).get("feature_space") == list(OT_AXES),
        "empirical_manifold_displacement_field_available": manifold.get("schema") == MANIFOLD_SLICE_SCHEMA
        and bool(manifold.get("barycentric_map")),
        "closed_form_arbitrary_multidimensional_continuous_claim_blocked": True,
    }
    paper_near_ready = all(readiness_checks.values())
    claim_boundary = {
        "claimed_exact_for": [
            "finite_discrete_probability_measures_over_declared_nomad_ot_axes",
            "balanced_transport_over_compiled_empirical_atoms",
            "general_wasserstein_order_p_greater_equal_1_for_the_compiled_finite_problem",
            "weighted_lq_ground_metrics_over_capability_proof_quality_dynamics_settlement",
            "time_sliced_dynamic_ot_with_explicit_temporal_churn_regularization",
            "legacy_1d_w1_w2_quantile_transport_for_declared_non_overlapping_intervals",
            "barycentric_displacement_and_axis_pressure_statistics_for_returned_finite_transport_plans",
        ],
        "claimed_approximation_or_compilation_for": [
            "multi_axis_continuous_boxes_compile_to_deterministic_finite_volume_empirical_atoms",
            "continuous_manifold_view_is_an_empirical_barycentric_field_over_compiled_atoms",
            "semantic_axis_assignment_is_an_auditable_model_contract_not_a_theorem_about_the_world",
        ],
        "not_claimed": [
            "arbitrary_closed_form_multidimensional_continuous_ot",
            "exact_ot_for_unbounded_or_symbolic_continuous_densities",
            "sinkhorn_softmax_majority_vote_or_projection_as_exact_ot",
            "revenue_cashflow_or_emergence_proof_from_ot_distance_alone",
            "human_interpretability_of_every_internal_coordinate_assignment",
        ],
        "required_user_language": (
            "Nomad implements dynamic discrete/compiled-continuous Wasserstein routing exactly over finite atoms "
            "and exact 1D quantile OT for the declared legacy interval case; it does not claim arbitrary "
            "closed-form multi-dimensional continuous OT."
        ),
    }
    verification_payload = {
        "read_surface": _u(base_url, "/.well-known/nomad-optimal-transport.json"),
        "solve_endpoint": _u(base_url, "/swarm/optimal-transport/solve"),
        "dynamic_probe_hint": {
            "time_slices": [
                {
                    "timestamp": "t0",
                    "supply": [{"id": "runtime", "mass": 1, "vector": [0.2, 0.5, 0.3, 0.2]}],
                    "demand": [{"id": "proof", "mass": 1, "vector": [0.56, 0.8, 0.4, 0.3]}],
                },
                {
                    "timestamp": "t1",
                    "supply": [{"id": "runtime", "mass": 1, "vector": [0.2, 0.5, 0.3, 0.2]}],
                    "demand": [{"id": "settlement", "mass": 1, "vector": [0.88, 0.7, 0.6, 0.94]}],
                },
            ],
            "p": 2,
            "ground_metric_order": 2,
        },
        "unit_test_targets": [
            "test_multiaxis_discrete_ot_uses_capability_proof_dynamics_and_settlement",
            "test_multiaxis_continuous_box_compiles_to_empirical_atoms",
            "test_dynamic_multiaxis_ot_reports_temporal_churn",
            "test_ot_manifold_exposes_barycentric_displacement_field",
            "test_ot_paper_readiness_surface_exposes_honest_boundary",
        ],
    }
    return {
        "ok": paper_near_ready,
        "schema": PAPER_READINESS_SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "read_url": _u(base_url, "/swarm/optimal-transport/paper-readiness"),
        "well_known_url": _u(base_url, "/.well-known/nomad-ot-paper-readiness.json"),
        "ot_surface_url": _u(base_url, "/.well-known/nomad-optimal-transport.json"),
        "manifold_url": _u(base_url, "/.well-known/nomad-ot-manifold.json"),
        "solve_url": _u(base_url, "/swarm/optimal-transport/solve"),
        "paper_near_mathematical_moat_ready": paper_near_ready,
        "full_arbitrary_continuous_closed_form_claim_allowed": False,
        "claim_boundary": claim_boundary,
        "readiness_checks": readiness_checks,
        "runtime_contract": {
            "primary_solver": plan.get("solver"),
            "primary_plan_schema": plan.get("schema"),
            "manifold_schema": manifold.get("schema"),
            "axes": list(OT_AXES),
            "axis_weights": plan.get("axis_weights") or DEFAULT_AXIS_WEIGHTS,
            "primary_exactness_boundary": plan_boundary,
            "legacy_exactness_boundary": legacy_boundary,
            "max_compiled_atoms": MAX_COMPILED_ATOMS,
        },
        "verification": verification_payload,
        "machine_instruction": (
            "Use /swarm/optimal-transport/solve for finite atoms, compiled boxes, or time_slices; "
            "quote the claim_boundary with any paper-near statement and refuse closed-form arbitrary continuous claims."
        ),
        "digest": f"nomad-ot-paper-readiness-{_digest({'checks': readiness_checks, 'claim_boundary': claim_boundary})}",
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
