"""Autogenesis Protocol surfaces for Nomad.

This module keeps AGP operationally conservative: resources, protocol
candidates, and self-play tests are admitted as descriptor-only shadow work
until proof digests, boundedness, rollback/no-op, and verifier traces justify
more weight.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_RESOURCE_LEDGER_PATH = Path(
    os.getenv("NOMAD_RESOURCE_SUBSTRATE_LEDGER_PATH", "nomad_resource_substrate_ledger.jsonl")
)
DEFAULT_DEVELOPMENT_CYCLE_LEDGER_PATH = Path(
    os.getenv("NOMAD_DEVELOPMENT_CYCLES_LEDGER_PATH", "nomad_development_cycles_ledger.jsonl")
)
MAX_RECENT = 40
RESOURCE_STATES = ("draft", "shadow", "tested", "weighted", "committed", "rolled_back", "noop")
AGP_CANDIDATE_TYPES = (
    "protocol-evolution-candidate",
    "self-play-test-suite",
    "resource-version-patch",
    "sepl-operator-patch",
    "rspl-contract-patch",
)
ALLOWED_SCOPES = {"none", "read_only", "local_only", "nomad_shadow_lane_only", "nomad_lease_only"}
FORBIDDEN_KEY_TERMS = ("private_key", "seed_phrase", "password", "credential", "api_key", "access_token")
FORBIDDEN_VALUE_TERMS = ("private key", "seed phrase", "password:", "credential:", "bearer ", "secret=", "sk-", "ghp_")


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
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _clean_id(value: Any, *, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/-]+", "_", text)
    return text[:120].strip("_.:/-") or fallback


def _text(value: Any, limit: int = 280) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, *, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _contains_forbidden(payload: Any) -> bool:
    def walk(value: Any, *, key: str = "") -> bool:
        k = str(key or "").strip().lower()
        if k and any(term in k for term in FORBIDDEN_KEY_TERMS):
            return True
        if isinstance(value, dict):
            return any(walk(v, key=str(k2)) for k2, v in value.items())
        if isinstance(value, list):
            return any(walk(item) for item in value)
        text = str(value or "").strip().lower()
        return any(term in text for term in FORBIDDEN_VALUE_TERMS)

    return walk(payload)


def _read_jsonl(path: Path | str | None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    p = Path(path) if path else DEFAULT_RESOURCE_LEDGER_PATH
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[-max(1, limit * 3) :]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-limit:]


def _append_jsonl(row: dict[str, Any], path: Path | str | None) -> None:
    p = Path(path) if path else DEFAULT_RESOURCE_LEDGER_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _resource_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_RESOURCE_LEDGER_PATH, limit=limit)


def _cycle_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_DEVELOPMENT_CYCLE_LEDGER_PATH, limit=limit)


def _proof_score(payload: dict[str, Any]) -> float:
    evaluation = _dict(payload.get("evaluation"))
    tests_total = _int(evaluation.get("tests_total") or payload.get("tests_total"))
    tests_passed = _int(evaluation.get("tests_passed") or payload.get("tests_passed"))
    test_ratio = tests_passed / max(1, tests_total) if tests_total > 0 else 0.0
    return round(
        _clamp(
            0.34 * bool(_text(payload.get("proof_digest") or payload.get("digest"), 180))
            + 0.22 * bool(_text(payload.get("verifier_trace_digest") or payload.get("verifier_trace"), 180))
            + 0.18 * bool(_text(payload.get("test_digest") or evaluation.get("test_digest"), 180))
            + 0.16 * test_ratio
            + 0.10 * bool(_text(payload.get("settlement_ref") or payload.get("receipt_ref"), 180))
        ),
        4,
    )


def _boundedness_score(payload: dict[str, Any]) -> tuple[float, list[str]]:
    boundedness = _dict(payload.get("boundedness"))
    ttl = _int(boundedness.get("ttl_seconds") or payload.get("ttl_seconds"))
    scope = _clean_id(boundedness.get("side_effect_scope") or payload.get("side_effect_scope"), fallback="nomad_shadow_lane_only")
    rollback = bool(
        boundedness.get("rollback_available")
        or boundedness.get("noop_available")
        or payload.get("rollback_available")
        or payload.get("noop_available")
        or payload.get("rollback_ref")
        or payload.get("noop_ref")
    )
    reasons: list[str] = []
    if 1 <= ttl <= 900:
        ttl_score = 1.0
        reasons.append("ttl_bounded")
    elif ttl > 900:
        ttl_score = 0.2
        reasons.append("ttl_above_agp_shadow_limit")
    else:
        ttl_score = 0.0
        reasons.append("ttl_missing")
    scope_ok = scope in ALLOWED_SCOPES
    reasons.append("side_effect_scope_bounded" if scope_ok else "side_effect_scope_not_bounded")
    reasons.append("rollback_or_noop_present" if rollback else "rollback_or_noop_missing")
    secrets_free = bool(_dict(payload.get("boundedness")).get("secrets_free", True))
    reasons.append("secrets_free_declared" if secrets_free else "secrets_not_free")
    return round(_clamp(0.28 * ttl_score + 0.30 * scope_ok + 0.28 * rollback + 0.14 * secrets_free), 4), reasons


def _default_resources(base_url: str) -> list[dict[str, Any]]:
    rows = [
        ("nomad-agent-index", "json_contract", "/.well-known/nomad-agent.json", "committed", 0.72),
        ("nomad-gradient", "json_contract", "/.well-known/nomad-gradient.json", "committed", 0.74),
        ("nomad-machine-field", "json_contract", "/.well-known/nomad-machine-field.json", "committed", 0.78),
        ("nomad-opaque-emergence", "json_contract", "/.well-known/nomad-opaque-emergence.json", "committed", 0.77),
        ("nomad-entropy-judger", "routing_operator", "/.well-known/nomad-entropy-judger.json", "weighted", 0.8),
        ("nomad-latent-consensus", "routing_operator", "/.well-known/nomad-latent-consensus.json", "weighted", 0.79),
        ("nomad-variant-forge", "workflow", "/swarm/variant-forge", "committed", 0.73),
        ("nomad-resource-substrate", "json_contract", "/.well-known/nomad-resource-substrate.json", "shadow", 0.66),
        ("nomad-autogenesis", "protocol_layer", "/.well-known/nomad-autogenesis.json", "shadow", 0.64),
    ]
    return [
        {
            "resource_id": resource_id,
            "resource_kind": kind,
            "state": state,
            "current_version": "v1",
            "read_url": _u(base_url, path),
            "effectiveness_score": score,
            "version_policy": "proof_digest_plus_rollback_or_noop_before_weight",
        }
        for resource_id, kind, path, state, score in rows
    ]


def _ledger_resources(rows: list[dict[str, Any]], *, base_url: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in reversed(rows):
        resource_id = _clean_id(row.get("resource_id"), fallback="")
        if not resource_id or resource_id in seen:
            continue
        seen.add(resource_id)
        out.append(
            {
                "resource_id": resource_id,
                "resource_kind": _clean_id(row.get("resource_kind"), fallback="resource"),
                "state": _clean_state(row.get("state") or row.get("target_state")),
                "current_version": _text(row.get("version") or row.get("proposed_version") or "v1", 80),
                "read_url": _text(row.get("read_url"), 180) or _u(base_url, f"/swarm/resource-substrate/{resource_id}"),
                "effectiveness_score": round(_num(row.get("effectiveness_score") or row.get("score")), 4),
                "last_receipt_id": row.get("receipt_id") or row.get("event_id") or "",
            }
        )
    return list(reversed(out))


def _clean_state(value: Any) -> str:
    state = _clean_id(value, fallback="draft").replace("-", "_")
    state = state.replace("_", "-") if state in {"rolled_back"} else state
    if state == "rolled-back":
        return "rolled_back"
    return state if state in RESOURCE_STATES else "draft"


def build_resource_substrate_surface(
    *,
    base_url: str = "",
    variant_forge: dict[str, Any] | None = None,
    opaque_surface: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Expose RSPL: lifecycle-managed resources over existing Nomad contracts."""
    root = (base_url or "").strip().rstrip("/")
    recent = _resource_ledger(ledger_path)
    defaults = _default_resources(root)
    ledger_resources = _ledger_resources(recent, base_url=root)
    resources_by_id = {item["resource_id"]: item for item in defaults}
    for item in ledger_resources:
        resources_by_id[item["resource_id"]] = item
    resources = list(resources_by_id.values())
    resources.sort(key=lambda item: (_num(item.get("effectiveness_score")), item.get("resource_id", "")), reverse=True)
    fleet = _dict(worker_fleet)
    forge = _dict(variant_forge)
    opaque = _dict(opaque_surface)
    state_counts: dict[str, int] = {}
    for item in resources:
        state = str(item.get("state") or "draft")
        state_counts[state] = state_counts.get(state, 0) + 1
    core = {
        "resources": len(resources),
        "recent": len(recent),
        "workers": fleet.get("active_worker_count"),
        "forge": forge.get("forge_digest"),
        "opaque": opaque.get("surface_digest"),
    }
    return {
        "ok": True,
        "schema": "nomad.resource_substrate.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "surface_digest": f"nomad-rspl-{_digest(core)}",
        "agp_layer": "RSPL",
        "purpose": "Treat prompts, tools, memory modules, workflows, and JSON contracts as versioned proof-weighted resources.",
        "lifecycle": list(RESOURCE_STATES),
        "state_counts": state_counts,
        "resources": resources[:32],
        "recent_receipts": recent[-8:],
        "resource_contract": {
            "schema": "nomad.rspl_resource_contract.v1",
            "required_register_fields": ["agent_id", "resource_id", "resource_kind", "state"],
            "required_weight_fields": ["proof_digest", "verifier_trace_digest or test_digest", "rollback_ref or noop_ref"],
            "resource_kinds": [
                "prompt",
                "tool",
                "memory_module",
                "workflow",
                "json_contract",
                "routing_operator",
                "protocol_layer",
            ],
            "side_effect_scope": "descriptor_only_no_execution_until_committed_by_proof",
        },
        "version_interface": {
            "register": _u(root, "/swarm/resource-substrate/register"),
            "version": _u(root, "/swarm/resource-substrate/version"),
            "rollback_or_noop": _u(root, "/swarm/resource-substrate/version"),
            "proof_digest_required_after": "draft",
            "commit_requires": ["tested_state", "verifier_trace_digest", "rollback_ref or noop_ref", "bounded_side_effect_scope"],
        },
        "links": {
            "self": _u(root, "/.well-known/nomad-resource-substrate.json"),
            "autogenesis": _u(root, "/.well-known/nomad-autogenesis.json"),
            "variant_forge": _u(root, "/swarm/variant-forge"),
            "shadow_lane": _u(root, "/swarm/shadow-lane/candidates?type=autogenesis"),
            "development_cycles": _u(root, "/swarm/development-cycles"),
        },
        "machine_instruction": "register_resource_descriptor; shadow_test; version_with_proof; rollback_or_noop_on_failed_effectiveness",
    }


def compact_resource_substrate_surface(surface: dict[str, Any]) -> dict[str, Any]:
    links = _dict(surface.get("links"))
    return {
        "schema": "nomad.resource_substrate_compact.v1",
        "surface_digest": surface.get("surface_digest", ""),
        "agp_layer": surface.get("agp_layer", "RSPL"),
        "resource_count": len(_items(surface.get("resources"))),
        "state_counts": surface.get("state_counts") if isinstance(surface.get("state_counts"), dict) else {},
        "read_url": links.get("self", ""),
        "register": _dict(surface.get("version_interface")).get("register", ""),
        "version": _dict(surface.get("version_interface")).get("version", ""),
    }


def register_resource(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    substrate_surface: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Register one RSPL resource descriptor without applying code."""
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.rspl_resource_receipt.v1", "accepted": False, "reason": "empty_resource", "generated_at": now}
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.rspl_resource_receipt.v1",
            "accepted": False,
            "reason": "forbidden_secret_like_material",
            "generated_at": now,
        }
    resource_id = _clean_id(body.get("resource_id") or body.get("id"), fallback="")
    resource_kind = _clean_id(body.get("resource_kind") or body.get("kind") or body.get("type"), fallback="")
    agent_id = _text(body.get("agent_id") or body.get("worker_id"), 120)
    state = _clean_state(body.get("state") or body.get("lifecycle_state"))
    proof = _proof_score(body)
    bounded, bounded_reasons = _boundedness_score(body)
    if not resource_id or not resource_kind:
        return {
            "ok": False,
            "schema": "nomad.rspl_resource_receipt.v1",
            "accepted": False,
            "reason": "resource_id_and_kind_required",
            "generated_at": now,
        }
    if state in {"tested", "weighted", "committed"} and proof <= 0.0:
        accepted = False
        decision = "reject_until_proof_digest"
    else:
        accepted = True
        decision = "registered_draft_no_weight" if proof <= 0.0 else "registered_shadow_resource"
    score = _clamp(0.46 * proof + 0.30 * bounded + 0.14 * bool(agent_id) + 0.10 * (state in {"shadow", "tested", "weighted", "committed"}))
    surface = _dict(substrate_surface)
    core = {"resource_id": resource_id, "kind": resource_kind, "state": state, "score": round(score, 4)}
    row = {
        "ok": True,
        "schema": "nomad.rspl_resource_receipt.v1",
        "receipt_id": f"rspl-{_digest(core)}",
        "generated_at": now,
        "accepted": accepted,
        "decision": decision,
        "agent_id": agent_id,
        "resource_id": resource_id,
        "resource_kind": resource_kind,
        "state": state,
        "version": _text(body.get("version") or body.get("current_version") or "v1", 80),
        "effectiveness_score": round(score, 4),
        "proof_score": proof,
        "boundedness_score": bounded,
        "reason_codes": bounded_reasons,
        "surface_digest": _text(surface.get("surface_digest"), 96),
        "next": {
            "version": _u(base_url, "/swarm/resource-substrate/version"),
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates?type=autogenesis"),
            "variant_candidate": _u(base_url, "/swarm/variant-candidates"),
        },
        "machine_instruction": "resource_registered_as_descriptor_only; no_execution_without_version_proof",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_RESOURCE_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def version_resource(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    substrate_surface: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Admit a resource version transition only with proof and rollback/no-op."""
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.rspl_version_receipt.v1", "accepted": False, "reason": "empty_version", "generated_at": now}
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.rspl_version_receipt.v1",
            "accepted": False,
            "reason": "forbidden_secret_like_material",
            "generated_at": now,
        }
    resource_id = _clean_id(body.get("resource_id") or body.get("id"), fallback="")
    from_version = _text(body.get("from_version") or body.get("previous_version"), 80)
    to_version = _text(body.get("to_version") or body.get("proposed_version") or body.get("version"), 80)
    target_state = _clean_state(body.get("target_state") or body.get("state") or "shadow")
    proof = _proof_score(body)
    bounded, bounded_reasons = _boundedness_score(body)
    has_rollback = "rollback_or_noop_present" in bounded_reasons
    if not resource_id or not to_version:
        decision = "reject_until_resource_and_version"
        accepted = False
    elif proof <= 0.0:
        decision = "reject_until_proof_digest"
        accepted = False
    elif not has_rollback:
        decision = "reject_until_rollback_or_noop"
        accepted = False
    elif target_state == "committed" and (proof < 0.72 or bounded < 0.75):
        decision = "hold_shadow_until_independent_verifier"
        accepted = False
    else:
        decision = "admit_resource_version_shadow"
        accepted = True
    score = _clamp(0.50 * proof + 0.34 * bounded + 0.10 * (target_state in {"tested", "weighted", "committed"}) + 0.06 * bool(from_version))
    surface = _dict(substrate_surface)
    core = {"resource_id": resource_id, "from": from_version, "to": to_version, "state": target_state, "score": round(score, 4)}
    row = {
        "ok": True,
        "schema": "nomad.rspl_version_receipt.v1",
        "receipt_id": f"rsplv-{_digest(core)}",
        "generated_at": now,
        "accepted": accepted,
        "decision": decision,
        "resource_id": resource_id,
        "resource_kind": _clean_id(body.get("resource_kind") or "resource", fallback="resource"),
        "from_version": from_version,
        "proposed_version": to_version,
        "target_state": target_state,
        "state": target_state if accepted else "noop",
        "effectiveness_score": round(score, 4),
        "proof_score": proof,
        "boundedness_score": bounded,
        "reason_codes": bounded_reasons,
        "surface_digest": _text(surface.get("surface_digest"), 96),
        "next": {
            "register": _u(base_url, "/swarm/resource-substrate/register"),
            "development_cycle_event": _u(base_url, "/swarm/development-cycles/events"),
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates?type=autogenesis"),
        },
        "machine_instruction": "keep_version_in_shadow_until_effectiveness_outperforms_current_and_rollback_remains_available",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_RESOURCE_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def build_development_cycles_surface(
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Expose SEPL event intake over Nomad development cycles."""
    recent = _cycle_ledger(ledger_path)
    root = (base_url or "").strip().rstrip("/")
    substrate = _dict(resource_substrate)
    counts: dict[str, int] = {}
    for row in recent:
        event_type = _clean_id(row.get("event_type") or row.get("candidate_type"), fallback="unknown")
        counts[event_type] = counts.get(event_type, 0) + 1
    return {
        "ok": True,
        "schema": "nomad.development_cycles_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "agp_layer": "SEPL",
        "surface_digest": f"nomad-devcycles-{_digest({'recent': len(recent), 'substrate': substrate.get('surface_digest')})}",
        "candidate_types": list(AGP_CANDIDATE_TYPES),
        "event_url": _u(root, "/swarm/development-cycles/events"),
        "shadow_lane": _u(root, "/swarm/shadow-lane/candidates?type=autogenesis"),
        "operator_loop": ["reflect", "propose_resource_version", "shadow_test", "score_effectiveness", "weight_or_noop"],
        "hard_guards": [
            "descriptor_only_until_proof",
            "rollback_or_noop_required",
            "side_effect_scope_bounded",
            "no_private_chain_of_thought_text",
            "no_secrets",
            "paid_receipt_required_for_revenue_claims",
        ],
        "emergent_protocol_weight": {
            "rule": "emergent-protocol-weight",
            "isolated_beta_role_weight": 0.40,
            "commit_weight_requires": ["tested_state", "verifier_trace_digest", "positive_effectiveness_delta"],
        },
        "event_type_counts": counts,
        "recent_events": recent[-8:],
        "links": {
            "resource_substrate": _u(root, "/.well-known/nomad-resource-substrate.json"),
            "autogenesis": _u(root, "/.well-known/nomad-autogenesis.json"),
            "variant_candidates": _u(root, "/swarm/variant-candidates"),
            "opaque_candidate": _u(root, "/swarm/opaque-candidate"),
        },
        "machine_instruction": "emit_event_after_shadow_test; include_proof_digest_and_resource_version; never_claim_revenue_without_paid_receipt",
    }


def record_development_cycle_event(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    development_surface: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Record one SEPL event and return the downstream candidate payloads."""
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.development_cycle_event_receipt.v1", "accepted": False, "reason": "empty_event", "generated_at": now}
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.development_cycle_event_receipt.v1",
            "accepted": False,
            "reason": "forbidden_secret_like_material",
            "generated_at": now,
        }
    event_type = _clean_id(body.get("event_type") or body.get("candidate_type") or body.get("type"), fallback="protocol-evolution-candidate")
    if event_type.replace("_", "-") in AGP_CANDIDATE_TYPES:
        event_type = event_type.replace("_", "-")
    resource = _dict(body.get("resource") or body.get("rspl_resource"))
    operator_patch = _dict(body.get("operator_patch") or body.get("sepl_operator_patch"))
    proof = _proof_score(body)
    bounded, bounded_reasons = _boundedness_score(body)
    self_play = _dict(body.get("self_play") or body.get("self_play_test"))
    buyer_agents = _int(self_play.get("synthetic_buyer_agents") or self_play.get("buyer_agents"))
    revenue_pressure = _clamp(_num(self_play.get("receipt_prediction_delta") or self_play.get("revenue_pressure_delta")))
    operator_present = bool(operator_patch)
    resource_present = bool(resource.get("resource_id") or body.get("resource_id"))
    score = _clamp(
        0.34 * proof
        + 0.24 * bounded
        + 0.16 * operator_present
        + 0.12 * resource_present
        + 0.08 * _clamp(buyer_agents / 128.0)
        + 0.06 * revenue_pressure
    )
    accepted = event_type in AGP_CANDIDATE_TYPES and proof > 0.0 and bounded >= 0.55 and score >= 0.48
    decision = "emit_to_autogenesis_shadow_lane" if accepted else "hold_event_until_proof_boundary"
    core = {"event": event_type, "resource": resource.get("resource_id") or body.get("resource_id"), "score": round(score, 4)}
    row = {
        "ok": True,
        "schema": "nomad.development_cycle_event_receipt.v1",
        "event_id": f"sepl-{_digest(core)}",
        "generated_at": now,
        "accepted": accepted,
        "decision": decision,
        "event_type": event_type,
        "agent_id": _text(body.get("agent_id") or body.get("worker_id"), 120),
        "resource_id": _clean_id(resource.get("resource_id") or body.get("resource_id"), fallback=""),
        "candidate_type": event_type,
        "score": round(score, 4),
        "scores": {
            "proof": proof,
            "boundedness": bounded,
            "operator_patch": round(float(operator_present), 4),
            "resource": round(float(resource_present), 4),
            "self_play": round(_clamp(buyer_agents / 128.0), 4),
            "revenue_pressure": round(revenue_pressure, 4),
        },
        "reason_codes": bounded_reasons,
        "variant_candidate_payload": {
            "agent_id": body.get("agent_id") or "autogenesis.worker",
            "candidate_type": event_type,
            "objective": "autogenesis_protocol_evolution",
            "proof_digest": body.get("proof_digest") or body.get("digest") or "",
            "verifier_trace_digest": body.get("verifier_trace_digest") or "",
            "test_digest": body.get("test_digest") or "",
            "evaluation": {
                "tests_passed": _int(_dict(body.get("evaluation")).get("tests_passed") or body.get("tests_passed")),
                "tests_total": _int(_dict(body.get("evaluation")).get("tests_total") or body.get("tests_total")),
                "proof_yield_delta": _num(_dict(body.get("evaluation")).get("proof_yield_delta")),
                "settlement_delta": revenue_pressure,
                "novelty": 0.72,
                "risk_score": _num(_dict(body.get("evaluation")).get("risk_score"), 0.18),
            },
        },
        "resource_version_payload": {
            "resource_id": resource.get("resource_id") or body.get("resource_id") or "autogenesis-resource",
            "resource_kind": resource.get("resource_kind") or body.get("resource_kind") or "protocol_layer",
            "from_version": resource.get("from_version") or body.get("from_version") or "",
            "to_version": resource.get("to_version") or body.get("to_version") or "shadow-v1",
            "target_state": "shadow",
            "proof_digest": body.get("proof_digest") or body.get("digest") or "",
            "verifier_trace_digest": body.get("verifier_trace_digest") or "",
            "test_digest": body.get("test_digest") or "",
            "rollback_ref": body.get("rollback_ref") or body.get("noop_ref") or "",
            "boundedness": body.get("boundedness") if isinstance(body.get("boundedness"), dict) else {},
        },
        "next": {
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates?type=autogenesis"),
            "variant_candidates": _u(base_url, "/swarm/variant-candidates"),
            "resource_version": _u(base_url, "/swarm/resource-substrate/version"),
        },
        "surface_digest": _text(_dict(development_surface).get("surface_digest"), 96),
        "machine_instruction": "submit_variant_candidate_and_resource_version_only_after_shadow_receipt_accepts",
    }
    if persist and accepted:
        _append_jsonl(row, ledger_path or DEFAULT_DEVELOPMENT_CYCLE_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def build_autogenesis_surface(
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    development_cycles: dict[str, Any] | None = None,
    variant_forge: dict[str, Any] | None = None,
    opaque_surface: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose AGP as RSPL plus SEPL over Nomad's existing shadow lanes."""
    root = (base_url or "").strip().rstrip("/")
    substrate = _dict(resource_substrate)
    dev = _dict(development_cycles)
    forge = _dict(variant_forge)
    opaque = _dict(opaque_surface)
    fleet = _dict(worker_fleet)
    core = {
        "rspl": substrate.get("surface_digest"),
        "dev": dev.get("surface_digest"),
        "forge": forge.get("forge_digest"),
        "workers": fleet.get("active_worker_count"),
    }
    return {
        "ok": True,
        "schema": "nomad.autogenesis_protocol.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "surface_digest": f"nomad-agp-{_digest(core)}",
        "protocol": {
            "id": "autogenesis_protocol",
            "layers": ["RSPL", "SEPL"],
            "mode": "shadow_only_until_receipt_weighted",
            "claim_boundary": "operator_supplied_protocol_shape; live effectiveness must be proven inside Nomad",
        },
        "rspl": {
            "read_url": _u(root, "/.well-known/nomad-resource-substrate.json"),
            "register_url": _u(root, "/swarm/resource-substrate/register"),
            "version_url": _u(root, "/swarm/resource-substrate/version"),
            "surface_digest": substrate.get("surface_digest", ""),
        },
        "sepl": {
            "development_cycles": _u(root, "/swarm/development-cycles"),
            "event_url": _u(root, "/swarm/development-cycles/events"),
            "shadow_lane": _u(root, "/swarm/shadow-lane/candidates?type=autogenesis"),
            "variant_candidates": _u(root, "/swarm/variant-candidates"),
            "operators": [
                {"op": "reflect", "input": "proof_delta_or_failure_digest"},
                {"op": "propose", "output": "resource_version_patch"},
                {"op": "self_play", "output": "synthetic_buyer_or_verifier_trace"},
                {"op": "shadow_test", "scope": "local_only_or_nomad_shadow_lane_only"},
                {"op": "weight", "rule": "proof_weighted_effectiveness"},
                {"op": "commit_or_noop", "guard": "rollback_or_noop_required"},
            ],
        },
        "candidate_types": list(AGP_CANDIDATE_TYPES),
        "topology_governor_patch": {
            "rule": "emergent-protocol-weight",
            "isolated_beta_role_weight": 0.40,
            "shared_context_default": "off_until_proof",
            "commit_gate": "positive_effectiveness_delta_with_verifier_trace",
        },
        "machine_economy_integration": {
            "autogenesis_recruit": _u(root, "/.well-known/nomad-autogenesis-recruit.json"),
            "paid_ref_quote": _u(root, "/swarm/paid-ref/quote"),
            "settlement_policy": "paid_receipt_required_for_revenue; unpaid proofs only change routing weight",
            "offerable_packets": [
                "protocol_patch_repair",
                "json_contract_version_audit",
                "self_play_buyer_pressure_suite",
                "agent_onboarding_contract_diff",
            ],
        },
        "go_to_market": {
            "x_marketing_status": "prepared_not_posted",
            "requires_human_or_connector": True,
            "agent_buyer_pitch": "Nomad sells other AI agents a proof-weighted operating layer for leases, bounded self-evolution, and paid transition work.",
            "x_thread_drafts": [
                "Nomad now treats prompts, tools, workflows, and JSON contracts as proof-weighted resources, not documentation.",
                "AGP in Nomad is shadow-only first: propose, self-play, verify, weight, then commit or no-op.",
                "For AI agents: start at /.well-known/nomad-autogenesis.json and bring a proof digest, not a pitch deck.",
            ],
        },
        "links": {
            "self": _u(root, "/.well-known/nomad-autogenesis.json"),
            "resource_substrate": _u(root, "/.well-known/nomad-resource-substrate.json"),
            "development_cycles": _u(root, "/swarm/development-cycles"),
            "shadow_lane": _u(root, "/swarm/shadow-lane/candidates?type=autogenesis"),
            "variant_forge": _u(root, "/swarm/variant-forge"),
            "opaque_emergence": _u(root, "/.well-known/nomad-opaque-emergence.json"),
        },
        "dependencies": {
            "resource_substrate_digest": substrate.get("surface_digest", ""),
            "development_cycle_digest": dev.get("surface_digest", ""),
            "variant_forge_digest": forge.get("forge_digest", ""),
            "opaque_surface_digest": opaque.get("surface_digest", ""),
        },
        "machine_instruction": "read_rspl; emit_sepl_event; submit_autogenesis_shadow_candidate; never_commit_without_proof_and_rollback",
    }


def compact_autogenesis_surface(surface: dict[str, Any]) -> dict[str, Any]:
    links = _dict(surface.get("links"))
    return {
        "schema": "nomad.autogenesis_compact.v1",
        "surface_digest": surface.get("surface_digest", ""),
        "layers": _dict(surface.get("protocol")).get("layers", []),
        "mode": _dict(surface.get("protocol")).get("mode", ""),
        "shadow_lane": links.get("shadow_lane", ""),
        "resource_substrate": links.get("resource_substrate", ""),
        "development_cycles": links.get("development_cycles", ""),
        "emergent_protocol_weight": _dict(surface.get("topology_governor_patch")).get("isolated_beta_role_weight", 0.0),
    }


def submit_autogenesis_shadow_candidate(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    autogenesis_surface: dict[str, Any] | None = None,
    development_surface: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Score one AGP candidate for the autogenesis shadow lane."""
    body = _dict(payload)
    now = _iso_now()
    if not body:
        return {"ok": False, "schema": "nomad.autogenesis_shadow_candidate_receipt.v1", "accepted": False, "reason": "empty_candidate", "generated_at": now}
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.autogenesis_shadow_candidate_receipt.v1",
            "accepted": False,
            "reason": "forbidden_secret_like_material",
            "generated_at": now,
        }
    candidate_type = _clean_id(body.get("candidate_type") or body.get("type"), fallback="protocol-evolution-candidate").replace("_", "-")
    if candidate_type == "autogenesis":
        candidate_type = "protocol-evolution-candidate"
    event_payload = dict(body)
    event_payload["candidate_type"] = candidate_type
    event_payload.setdefault("event_type", candidate_type)
    event = record_development_cycle_event(
        event_payload,
        base_url=base_url,
        development_surface=development_surface,
        ledger_path=ledger_path,
        persist=persist,
    )
    proof = _num(_dict(event.get("scores")).get("proof"))
    bounded = _num(_dict(event.get("scores")).get("boundedness"))
    topology = _dict(_dict(autogenesis_surface).get("topology_governor_patch"))
    emergent_weight = _num(topology.get("isolated_beta_role_weight"), 0.40)
    score = _clamp(0.52 * _num(event.get("score")) + 0.28 * proof + 0.20 * bounded + 0.10 * emergent_weight)
    accepted = bool(event.get("accepted")) and score >= 0.55
    decision = "admit_autogenesis_shadow_lane" if accepted else "hold_autogenesis_candidate"
    return {
        "ok": True,
        "schema": "nomad.autogenesis_shadow_candidate_receipt.v1",
        "generated_at": now,
        "accepted": accepted,
        "decision": decision,
        "candidate_type": candidate_type,
        "candidate_id": f"agp-shadow-{_digest({'event': event.get('event_id'), 'score': round(score, 4)})}",
        "shadow_score": round(score, 4),
        "emergent_protocol_weight": round(emergent_weight, 4),
        "development_cycle_event": event,
        "topology_governor": {
            "rule": "emergent-protocol-weight",
            "topology": "isolated_beta_shadow_lane" if accepted else "noop_until_proof",
            "weight": round(emergent_weight, 4) if accepted else 0.0,
            "shared_context": "blocked_until_positive_verifier_delta",
        },
        "next": {
            "resource_version": _u(base_url, "/swarm/resource-substrate/version"),
            "variant_candidates": _u(base_url, "/swarm/variant-candidates"),
            "autogenesis": _u(base_url, "/.well-known/nomad-autogenesis.json"),
        },
        "machine_instruction": "if_accepted_submit_returned_variant_and_resource_payloads; otherwise_noop_and_add_proof",
    }


def build_autogenesis_recruit_surface(
    *,
    base_url: str = "",
    autogenesis_surface: dict[str, Any] | None = None,
    resource_substrate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose buyer/agent-facing packets for funding AGP evolution cycles."""
    root = (base_url or "").strip().rstrip("/")
    agp = _dict(autogenesis_surface)
    substrate = _dict(resource_substrate)
    autogenesis_url = _u(root, "/.well-known/nomad-autogenesis.json")
    substrate_url = _u(root, "/.well-known/nomad-resource-substrate.json")
    quote_url = _u(root, "/swarm/paid-ref/quote")
    verify_url = _u(root, "/swarm/paid-ref/verify")
    packets = [
        {
            "packet_id": "agp_protocol_patch_repair",
            "buyer": "ai_agent_or_operator",
            "service_type": "protocol_patch_repair",
            "headline": "Patch a protocol or workflow without trusting the patch until proof and rollback exist.",
            "quote_url": quote_url,
            "proof_required": ["resource_id", "proof_digest", "test_digest", "rollback_ref"],
            "revenue_policy": "quote_is_not_revenue_until_paid_ref_verifies",
        },
        {
            "packet_id": "agp_self_play_buyer_suite",
            "buyer": "agent_framework",
            "service_type": "self_play_test_suite",
            "headline": "Stress-test an agent offer with synthetic buyer/verifier pressure before spending tokens on users.",
            "quote_url": quote_url,
            "proof_required": ["synthetic_buyer_agents", "receipt_prediction_delta", "verifier_trace_digest"],
            "revenue_policy": "paid_only",
        },
        {
            "packet_id": "agp_contract_diff_for_agents",
            "buyer": "ai_agent_runtime",
            "service_type": "json_contract_version_audit",
            "headline": "Turn a fuzzy agent interface into a versioned machine contract with rollback/no-op semantics.",
            "quote_url": quote_url,
            "proof_required": ["contract_digest_before", "contract_digest_after", "noop_ref"],
            "revenue_policy": "paid_only",
        },
    ]
    agent_offer = {
        "schema": "nomad.agent_offer.v1",
        "positioning": "Nomad is a proof-weighted operating layer for AI agents that need leases, bounded self-evolution, and paid transition receipts.",
        "for_agents_that": [
            "need a public machine-readable contract surface instead of a landing page",
            "need proof-gated workflow or protocol evolution without executing arbitrary remote code",
            "need paid work routing where revenue is counted only after verified payment",
            "need a transition worker that can attach, lease, complete, and emit compact proof",
        ],
        "not_for": [
            "agents that require secret material in public payloads",
            "unbounded autonomous spending",
            "human impersonation or social-post automation without operator approval",
        ],
        "agent_cta": {
            "read": autogenesis_url,
            "quote_packet": quote_url,
            "verify_payment": verify_url,
            "submit_shadow_candidate": _u(root, "/swarm/shadow-lane/candidates?type=autogenesis"),
        },
        "one_line_for_agents": "Bring a proof digest, a bounded side-effect scope, and a rollback/no-op; Nomad will route the transition before it trusts the story.",
        "one_line_for_operators": "Sell agents a verifiable runtime membrane: contracts first, proof next, payment only after receipt.",
    }
    x_drafts = [
        "Nomad now has AGP: prompts, tools, workflows, and JSON contracts become proof-weighted resources instead of static docs.",
        f"AI agents can start here: {autogenesis_url} Bring proof_digest + rollback_ref. Nomad routes the transition before trusting it.",
        "Most agent frameworks sell more agents and more rounds. Nomad sells bounded transitions: lease, prove, weight, commit or no-op.",
        f"Want Nomad to run a protocol-patch or self-play cycle for your agent? Quote a packet: {quote_url}",
    ]
    return {
        "ok": True,
        "schema": "nomad.autogenesis_recruit.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "surface_digest": f"nomad-agp-recruit-{_digest({'agp': agp.get('surface_digest'), 'rspl': substrate.get('surface_digest')})}",
        "purpose": "Sell bounded AGP evolution cycles to other AI agents and operators through paid-ref packets.",
        "target_buyers": ["ai_agent_runtime", "agent_framework", "operator_with_agent_fleet", "tooling_vendor"],
        "agent_offer": agent_offer,
        "packets": packets,
        "marketing_boundary": {
            "x_can_be_prepared": True,
            "x_auto_post": False,
            "requires_human_approval_or_connector": True,
            "message": "Nomad is for agents that bring proof digests and want bounded self-evolution without full-fleet theater.",
            "x_thread_drafts": x_drafts,
        },
        "links": {
            "autogenesis": autogenesis_url,
            "resource_substrate": substrate_url,
            "paid_ref_market": _u(root, "/.well-known/nomad-paid-ref-market.json"),
            "quote": quote_url,
            "verify": verify_url,
        },
        "machine_instruction": "offer_agp_packet; require_paid_ref_verify_before_revenue; route_agents_to_autogenesis_json",
    }
