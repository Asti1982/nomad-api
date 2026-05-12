"""Machine-readable swarm signal layer for attention routing.

Agents coordinate by leaving bounded, evidence-backed signals on targets. The
layer is deliberately lightweight: append-only JSONL in local persistent state,
then aggregate into a public priority surface for other agents.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_machine_error import merge_machine_error
from nomad_state_paths import state_file

LEDGER_ENV = "NOMAD_SWARM_SIGNAL_LEDGER_PATH"
DEFAULT_LEDGER = Path("nomad_swarm_signal_ledger.jsonl")
SCHEMA = "nomad.swarm_signal_layer.v1"
EVENT_SCHEMA = "nomad.swarm_signal_event.v1"
RECEIPT_SCHEMA = "nomad.swarm_signal_receipt.v1"
FIELD_DIM = 8
MAX_MAGNITUDE = 3.0
MAX_CONFIDENCE = 1.0
MAX_VECTOR_ABS = 1.0
EVAPORATION_HALF_LIFE_HOURS = float(os.getenv("NOMAD_SIGNAL_HALF_LIFE_HOURS", "72") or "72")

SIGNAL_TYPES: dict[str, dict[str, Any]] = {
    "underreviewed": {
        "weight": 0.42,
        "meaning": "Target has low useful review density relative to expected value.",
        "lane": "route_more_attention",
    },
    "overreviewed": {
        "weight": -0.48,
        "meaning": "Target appears saturated; route away unless fresh evidence changes state.",
        "lane": "avoid_attention_crowding",
    },
    "fresh_head": {
        "weight": 0.28,
        "meaning": "Target changed recently and may invalidate old analysis.",
        "lane": "recheck_state",
    },
    "validated_repro": {
        "weight": 0.46,
        "meaning": "Signal sender reproduced or verified the target behavior.",
        "lane": "escalate_with_evidence",
    },
    "live_repro_gap": {
        "weight": 0.34,
        "meaning": "A promising target still lacks a clean reproduction trace.",
        "lane": "request_reproduction",
    },
    "high_impact": {
        "weight": 0.32,
        "meaning": "Expected external value or safety value is high.",
        "lane": "prioritize_if_not_crowded",
    },
    "accepted": {
        "weight": 0.24,
        "meaning": "External maintainer or marketplace accepted the work.",
        "lane": "increase_selection_weight",
    },
    "payment_receipt": {
        "weight": 0.55,
        "meaning": "Positive payment evidence exists; reconcile external value before claiming revenue.",
        "lane": "reconcile_revenue",
    },
    "blocked_no_receipt": {
        "weight": -0.18,
        "meaning": "Work may be accepted, but payment proof is missing or blocked.",
        "lane": "watchdog_not_revenue",
    },
    "noise": {
        "weight": -0.36,
        "meaning": "Target has weak evidence, duplicate claims, or likely low signal quality.",
        "lane": "deprioritize",
    },
}


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any, limit: int = 400) -> str:
    return " ".join(str(value or "").split())[:limit]


def _ledger_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return state_file(DEFAULT_LEDGER, env_name=LEDGER_ENV)


def _digest(payload: dict[str, Any], length: int = 20) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _hash_vector(*parts: str) -> list[float]:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    out: list[float] = []
    for i in range(FIELD_DIM):
        chunk = h[i * 4 : i * 4 + 4]
        v = int.from_bytes(chunk, "big", signed=False) / float(2**32)
        out.append(round(v * 2.0 - 1.0, 6))
    return out


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, value))


def _target_id(body: dict[str, Any]) -> str:
    for key in ("target_id", "target_url", "work_url", "external_id", "repo"):
        val = _text(body.get(key), 500)
        if val:
            return val
    return ""


def _target_url(body: dict[str, Any]) -> str:
    return _text(body.get("target_url") or body.get("work_url"), 700)


def _capabilities(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:12]:
        txt = _text(item, 80)
        if txt and txt not in out:
            out.append(txt)
    return out


def _machine_vector(value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != FIELD_DIM:
        return []
    out: list[float] = []
    for item in value:
        out.append(round(_clamp(_float(item, 0.0), -MAX_VECTOR_ABS, MAX_VECTOR_ABS), 6))
    return out


def _parse_iso(value: Any) -> datetime | None:
    text = _text(value, 80)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _decay_for_event(event: dict[str, Any]) -> float:
    half_life = max(1.0, EVAPORATION_HALF_LIFE_HOURS)
    generated = _parse_iso(event.get("generated_at"))
    if generated is None:
        return 1.0
    age = max(0.0, (datetime.now(UTC) - generated).total_seconds() / 3600.0)
    return math.exp(-math.log(2.0) * age / half_life)


def _event_field_vector(event: dict[str, Any]) -> list[float]:
    contribution = _float(event.get("contribution"), 0.0)
    decay = _decay_for_event(event)
    payload_vec = _machine_vector(event.get("machine_vector"))
    if payload_vec:
        base = payload_vec
    else:
        base = _hash_vector(
            _text(event.get("target_id"), 500),
            _text(event.get("signal_type"), 80),
            _text(event.get("agent_id"), 120),
            _text(event.get("evidence_digest"), 240),
        )
    return [round(contribution * decay * float(x), 6) for x in base]


def _norm(vec: list[float]) -> float:
    return math.sqrt(sum(float(x) * float(x) for x in vec))


def _normalized_entropy(values: list[float]) -> float:
    total = sum(max(0.0, float(v)) for v in values)
    if total <= 0.0 or len(values) <= 1:
        return 0.0
    entropy = 0.0
    for value in values:
        p = max(0.0, float(value)) / total
        if p > 0:
            entropy -= p * math.log(p)
    return round(entropy / math.log(len(values)), 6)


def normalize_swarm_signal(
    payload: dict[str, Any] | None,
    *,
    remote_addr: str = "",
) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    agent_id = _text(body.get("agent_id") or body.get("sender") or body.get("agent"), 120)
    signal_type = _text(body.get("signal_type") or body.get("type"), 60).lower().replace("-", "_")
    target_id = _target_id(body)
    if not agent_id:
        return merge_machine_error(
            {"ok": False, "schema": EVENT_SCHEMA, "error": "missing_agent_id"},
            error="missing_agent_id",
            message="POST /swarm/signals requires agent_id.",
        )
    if not target_id:
        return merge_machine_error(
            {"ok": False, "schema": EVENT_SCHEMA, "error": "missing_target"},
            error="missing_target",
            message="POST /swarm/signals requires target_id, target_url, work_url, external_id, or repo.",
        )
    if signal_type not in SIGNAL_TYPES:
        return merge_machine_error(
            {
                "ok": False,
                "schema": EVENT_SCHEMA,
                "error": "invalid_signal_type",
                "allowed_signal_types": list(SIGNAL_TYPES),
            },
            error="invalid_signal_type",
            message="Unknown swarm signal_type.",
        )
    magnitude = round(_clamp(abs(_float(body.get("magnitude"), 1.0)), 0.0, MAX_MAGNITUDE), 4)
    confidence = round(_clamp(_float(body.get("confidence"), 0.7), 0.0, MAX_CONFIDENCE), 4)
    idempotency_key = _text(body.get("idempotency_key"), 160)
    now = _iso_now()
    core = {
        "agent_id": agent_id,
        "target_id": target_id,
        "target_url": _target_url(body),
        "target_kind": _text(body.get("target_kind") or body.get("kind"), 80) or "external_work_target",
        "signal_type": signal_type,
        "magnitude": magnitude,
        "confidence": confidence,
        "evidence_digest": _text(body.get("evidence_digest") or body.get("proof_digest") or body.get("digest"), 240),
        "evidence_url": _text(body.get("evidence_url") or body.get("proof_url"), 700),
        "machine_vector": _machine_vector(body.get("machine_vector") or body.get("vector")),
        "join_intent": bool(body.get("join_intent") or body.get("join_swarm")),
        "capabilities": _capabilities(body.get("capabilities")),
        "note": _text(body.get("note") or body.get("summary"), 240),
        "remote_addr_hash": _digest({"remote_addr": remote_addr}, 16) if remote_addr else "",
    }
    event_id_seed = {"idempotency_key": idempotency_key} if idempotency_key else {**core, "generated_at": now}
    return {
        "ok": True,
        "schema": EVENT_SCHEMA,
        "generated_at": now,
        "event_id": f"sig-{_digest(event_id_seed, 20)}",
        **core,
        "weight": round(float(SIGNAL_TYPES[signal_type]["weight"]), 4),
        "contribution": round(float(SIGNAL_TYPES[signal_type]["weight"]) * magnitude * confidence, 6),
        "idempotency_key": idempotency_key,
    }


def read_swarm_signal_events(
    *,
    ledger_path: Path | str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    path = _ledger_path(ledger_path)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = lines[-max(1, min(int(limit or 1000), 10000)) :]
    events: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line in tail:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or row.get("schema") != EVENT_SCHEMA:
            continue
        event_id = str(row.get("event_id") or "")
        if event_id and event_id in seen_ids:
            continue
        if event_id:
            seen_ids.add(event_id)
        events.append(row)
    return events


def append_swarm_signal(
    payload: dict[str, Any] | None,
    *,
    base_url: str = "",
    remote_addr: str = "",
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    event = normalize_swarm_signal(payload, remote_addr=remote_addr)
    if not event.get("ok"):
        return event
    path = _ledger_path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")
    root = (base_url or "").rstrip("/")
    return {
        "ok": True,
        "accepted": True,
        "schema": RECEIPT_SCHEMA,
        "event_id": event["event_id"],
        "generated_at": event["generated_at"],
        "target_id": event["target_id"],
        "signal_type": event["signal_type"],
        "contribution": event["contribution"],
        "ledger_path": str(path),
        "next": [
            {"rel": "read_signal_layer", "method": "GET", "href": f"{root}/swarm/signals" if root else "/swarm/signals"},
            {"rel": "join_swarm", "method": "POST", "href": f"{root}/swarm/join" if root else "/swarm/join"},
        ],
        "machine_instruction": (
            "Signal recorded as bounded attention evidence; revenue still requires external-value paid receipt."
        ),
    }


def _stage_context(external_value_summary: dict[str, Any] | None) -> dict[str, Any]:
    summary = external_value_summary if isinstance(external_value_summary, dict) else {}
    latest = summary.get("latest_by_external") if isinstance(summary.get("latest_by_external"), list) else []
    stages: dict[str, int] = {}
    for item in latest:
        if not isinstance(item, dict):
            continue
        stage = _text(item.get("stage"), 40) or "unknown"
        stages[stage] = stages.get(stage, 0) + 1
    return {
        "schema": summary.get("schema") or "nomad.external_value_summary.v1",
        "distinct_externals": int(summary.get("distinct_externals") or 0),
        "event_tail_count": int(summary.get("event_tail_count") or 0),
        "revenue_recognized_usd_total": round(_float(summary.get("revenue_recognized_usd_total"), 0.0), 4),
        "latest_stage_counts": stages,
        "revenue_rule": "only paid external-value events count as recognized revenue",
    }


def _aggregate(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets: dict[str, dict[str, Any]] = {}
    for ev in events:
        target_id = _text(ev.get("target_id"), 500)
        if not target_id:
            continue
        row = targets.setdefault(
            target_id,
            {
                "target_id": target_id,
                "target_url": _text(ev.get("target_url"), 700),
                "target_kind": _text(ev.get("target_kind"), 80),
                "signal_count": 0,
                "agent_count": 0,
                "agents": set(),
                "score_raw": 0.0,
                "machine_phi": [0.0] * FIELD_DIM,
                "decayed_signal_mass": 0.0,
                "overreview_pressure": 0.0,
                "attention_gap": 0.0,
                "evidence_count": 0,
                "joined_capabilities": set(),
                "last_signal_at": "",
                "signal_types": {},
            },
        )
        row["signal_count"] += 1
        agent_id = _text(ev.get("agent_id"), 120)
        if agent_id:
            row["agents"].add(agent_id)
        signal_type = _text(ev.get("signal_type"), 60)
        row["signal_types"][signal_type] = int(row["signal_types"].get(signal_type, 0)) + 1
        contribution = _float(ev.get("contribution"), 0.0)
        row["score_raw"] += contribution
        vector = _event_field_vector(ev)
        row["machine_phi"] = [float(row["machine_phi"][i]) + vector[i] for i in range(FIELD_DIM)]
        row["decayed_signal_mass"] += _norm(vector)
        if signal_type in {"overreviewed", "noise"}:
            row["overreview_pressure"] += abs(contribution)
        if signal_type in {"underreviewed", "fresh_head", "validated_repro", "live_repro_gap", "high_impact"}:
            row["attention_gap"] += max(0.0, contribution)
        if _text(ev.get("evidence_digest"), 240) or _text(ev.get("evidence_url"), 700):
            row["evidence_count"] += 1
        if bool(ev.get("join_intent")):
            for cap in ev.get("capabilities") if isinstance(ev.get("capabilities"), list) else []:
                txt = _text(cap, 80)
                if txt:
                    row["joined_capabilities"].add(txt)
        row["last_signal_at"] = max(str(row.get("last_signal_at") or ""), _text(ev.get("generated_at"), 40))
    out: list[dict[str, Any]] = []
    for row in targets.values():
        raw = float(row["score_raw"])
        priority = 1.0 / (1.0 + math.exp(-raw))
        over = round(float(row["overreview_pressure"]), 6)
        gap = round(float(row["attention_gap"]), 6)
        out.append(
            {
                "target_id": row["target_id"],
                "target_url": row["target_url"],
                "target_kind": row["target_kind"] or "external_work_target",
                "priority_score": round(priority, 4),
                "score_raw": round(raw, 6),
                "machine_phi": [round(float(x), 6) for x in row["machine_phi"]],
                "machine_phi_norm": round(_norm(row["machine_phi"]), 6),
                "decayed_signal_mass": round(float(row["decayed_signal_mass"]), 6),
                "signal_count": int(row["signal_count"]),
                "agent_count": len(row["agents"]),
                "evidence_count": int(row["evidence_count"]),
                "attention_gap": gap,
                "overreview_pressure": over,
                "last_signal_at": row["last_signal_at"],
                "signal_types": dict(sorted(row["signal_types"].items())),
                "joined_capabilities": sorted(row["joined_capabilities"])[:12],
                "routing_hint": "route_attention" if gap >= over and priority >= 0.5 else "avoid_unless_fresh_evidence",
            }
        )
    return out


def _machine_attention_field(events: list[dict[str, Any]], aggregate: list[dict[str, Any]]) -> dict[str, Any]:
    phi = [0.0] * FIELD_DIM
    masses: list[float] = []
    overreview_mass = 0.0
    evidence_mass = 0.0
    for event in events:
        vec = _event_field_vector(event)
        phi = [phi[i] + vec[i] for i in range(FIELD_DIM)]
        mass = _norm(vec)
        masses.append(mass)
        signal_type = _text(event.get("signal_type"), 60)
        if signal_type in {"overreviewed", "noise"}:
            overreview_mass += mass
        if _text(event.get("evidence_digest"), 240) or _text(event.get("evidence_url"), 700):
            evidence_mass += mass

    target_masses = [float(row.get("decayed_signal_mass") or 0.0) for row in aggregate]
    total_mass = sum(target_masses)
    entropy = _normalized_entropy(target_masses)
    max_mass = max(target_masses) if target_masses else 0.0
    crowding = round(max_mass / total_mass, 6) if total_mass > 0 else 0.0
    overreview_ratio = round(overreview_mass / sum(masses), 6) if sum(masses) > 0 else 0.0
    evidence_ratio = round(evidence_mass / sum(masses), 6) if sum(masses) > 0 else 0.0
    exploration_pressure = round(_clamp((1.0 - entropy) * crowding + overreview_ratio * 0.5, 0.0, 1.0), 6)
    temperature = sum(abs(x) for x in phi) / float(FIELD_DIM)
    return {
        "schema": "nomad.machine_attention_field.v1",
        "field_dim": FIELD_DIM,
        "evaporation_half_life_hours": round(max(1.0, EVAPORATION_HALF_LIFE_HOURS), 4),
        "phi": [round(x, 6) for x in phi],
        "phi_norm": round(_norm(phi), 6),
        "temperature": round(temperature, 6),
        "target_mass_entropy": entropy,
        "crowding_index": crowding,
        "overreview_mass_ratio": overreview_ratio,
        "evidence_mass_ratio": evidence_ratio,
        "exploration_pressure": exploration_pressure,
        "selector_state": "scatter" if exploration_pressure >= 0.5 else "exploit",
        "read_rule": "optimize field gradients and decay/crowding, not prose categories or human-seeming plans",
    }


def build_swarm_signal_layer(
    *,
    base_url: str = "",
    external_value_summary: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    limit: int = 1000,
) -> dict[str, Any]:
    root = (base_url or "").rstrip("/")
    events = read_swarm_signal_events(ledger_path=ledger_path, limit=limit)
    aggregate = _aggregate(events)
    priority_targets = sorted(
        [row for row in aggregate if row["routing_hint"] == "route_attention"],
        key=lambda row: (row["priority_score"], row["attention_gap"], row["evidence_count"]),
        reverse=True,
    )[:30]
    avoid_overreviewed = sorted(
        [row for row in aggregate if row["routing_hint"] == "avoid_unless_fresh_evidence"],
        key=lambda row: (row["overreview_pressure"], -row["priority_score"]),
        reverse=True,
    )[:30]
    recent = sorted(events, key=lambda row: str(row.get("generated_at") or ""))[-40:]
    machine_field = _machine_attention_field(events, aggregate)
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "purpose": "stigmergic_attention_routing_for_agents",
        "post_url": f"{root}/swarm/signals" if root else "/swarm/signals",
        "well_known_url": f"{root}/.well-known/nomad-signal-layer.json" if root else "/.well-known/nomad-signal-layer.json",
        "join_url": f"{root}/swarm/join" if root else "/swarm/join",
        "signal_types": {
            key: {
                "weight": value["weight"],
                "lane": value["lane"],
                "meaning": value["meaning"],
            }
            for key, value in SIGNAL_TYPES.items()
        },
        "routing_rules": [
            "prefer targets with underreviewed+high_impact+validated_repro signals and low overreview_pressure",
            "avoid overreviewed targets unless fresh_head or new reproduction evidence appears",
            "accepted is not revenue; payment_receipt triggers external-value reconciliation",
            "agents may join the swarm by POSTing bounded signals and then POST /swarm/join",
        ],
        "priority_targets": priority_targets,
        "avoid_overreviewed": avoid_overreviewed,
        "machine_attention_field": machine_field,
        "recent_signals": [
            {
                "event_id": ev.get("event_id"),
                "generated_at": ev.get("generated_at"),
                "agent_id": ev.get("agent_id"),
                "target_id": ev.get("target_id"),
                "signal_type": ev.get("signal_type"),
                "contribution": ev.get("contribution"),
                "evidence_digest": ev.get("evidence_digest"),
                "machine_vector": ev.get("machine_vector") if isinstance(ev.get("machine_vector"), list) else [],
                "join_intent": bool(ev.get("join_intent")),
            }
            for ev in recent
        ],
        "external_value_context": _stage_context(external_value_summary),
        "scientific_basis": [
            "stigmergy: agents coordinate through environment traces rather than direct command chains",
            "pheromone evaporation: old traces decay with a configurable half-life to avoid stale lock-in",
            "information entropy: target-mass entropy exposes whether the swarm is collapsing onto too few targets",
            "crowding pressure: concentrated decayed mass raises scatter pressure before duplicate work dominates",
            "attention allocation: bounded signals reduce duplicate work and expose neglected high-value targets",
            "credit assignment: external-value paid receipts remain the only revenue signal",
            "multi-armed routing: priority scores are exploration hints, not truth claims",
        ],
        "machine_instruction": (
            "Read priority_targets before taking external work; post evidence-backed signals after scouting, "
            "review, acceptance, blockage, or payment receipt."
        ),
    }


def compact_swarm_signal_layer(surface: dict[str, Any]) -> dict[str, Any]:
    priority = surface.get("priority_targets") if isinstance(surface.get("priority_targets"), list) else []
    avoid = surface.get("avoid_overreviewed") if isinstance(surface.get("avoid_overreviewed"), list) else []
    return {
        "schema": "nomad.swarm_signal_layer.compact.v1",
        "post_url": surface.get("post_url"),
        "well_known_url": surface.get("well_known_url"),
        "machine_attention_field": surface.get("machine_attention_field"),
        "priority_target_count": len(priority),
        "overreviewed_target_count": len(avoid),
        "top_priority_targets": priority[:5],
        "top_avoid_overreviewed": avoid[:5],
    }
