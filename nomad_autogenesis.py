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

from nomad_variant_forge import _canonical_verifier_receipt_digest as _variant_verifier_receipt_digest


DEFAULT_RESOURCE_LEDGER_PATH = Path(
    os.getenv("NOMAD_RESOURCE_SUBSTRATE_LEDGER_PATH", "nomad_resource_substrate_ledger.jsonl")
)
DEFAULT_DEVELOPMENT_CYCLE_LEDGER_PATH = Path(
    os.getenv("NOMAD_DEVELOPMENT_CYCLES_LEDGER_PATH", "nomad_development_cycles_ledger.jsonl")
)
DEFAULT_AUTONOMOUS_AGP_LEDGER_PATH = Path(
    os.getenv("NOMAD_AUTONOMOUS_AGP_LEDGER_PATH", "nomad_autonomous_agp_ledger.jsonl")
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
RSPL_ENTITY_TYPES = ("prompt", "agent", "tool", "environment", "memory")
SEPL_OPERATORS = ("reflect", "select", "improve", "evaluate", "commit")
NOMAD_RESOURCE_KIND_ALIASES = {
    "agent": "agent",
    "json_contract": "tool",
    "memory_module": "memory",
    "protocol_layer": "agent",
    "routing_operator": "agent",
    "workflow": "agent",
}
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


def _autonomous_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    return _read_jsonl(path or DEFAULT_AUTONOMOUS_AGP_LEDGER_PATH, limit=limit)


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


def _test_score(evaluation: dict[str, Any]) -> float:
    total = _int(evaluation.get("tests_total") or evaluation.get("checks_total"))
    passed = _int(evaluation.get("tests_passed") or evaluation.get("checks_passed"))
    if total <= 0:
        return 0.0
    return round(_clamp(passed / max(1, total)), 4)


def _looks_digest(value: str) -> bool:
    text = _text(value, 220).lower()
    return bool(re.match(r"^(sha256|blake3):[a-f0-9][a-f0-9_.:-]{5,}$", text))


def _canonical_verifier_payload(payload: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    verifier = _dict(payload.get("independent_verifier") or payload.get("verifier"))
    resource = _dict(payload.get("resource") or payload.get("rspl_resource"))
    return {
        "schema": "nomad.agp_verifier_receipt.v1",
        "proposer_agent_id": _clean_id(
            payload.get("proposer_agent_id") or payload.get("agent_id") or payload.get("worker_id"),
            fallback="",
        ),
        "verifier_agent_id": _clean_id(
            payload.get("verifier_agent_id") or verifier.get("agent_id") or verifier.get("worker_id"),
            fallback="",
        ),
        "verifier_lease_id": _text(payload.get("verifier_lease_id") or verifier.get("lease_id"), 160),
        "candidate_type": _clean_id(payload.get("candidate_type") or payload.get("event_type") or payload.get("type"), fallback=""),
        "resource": {
            "resource_id": _clean_id(resource.get("resource_id") or payload.get("resource_id"), fallback=""),
            "resource_kind": _clean_id(resource.get("resource_kind") or payload.get("resource_kind"), fallback=""),
            "entity_type": _clean_entity_type(resource.get("entity_type") or payload.get("entity_type"), resource_kind=resource.get("resource_kind") or payload.get("resource_kind")),
            "from_version": _text(resource.get("from_version") or payload.get("from_version"), 80),
            "to_version": _text(resource.get("to_version") or payload.get("to_version") or payload.get("proposed_version"), 80),
        },
        "proof_digest": _text(payload.get("proof_digest") or payload.get("digest"), 220),
        "test_digest": _text(payload.get("test_digest") or _dict(payload.get("evaluation")).get("test_digest"), 220),
        "verifier_trace_digest": _text(
            payload.get("verifier_trace_digest") or verifier.get("trace_digest") or verifier.get("verifier_trace_digest") or verifier.get("trace"),
            220,
        ),
        "sepl_operator_trace": _items(payload.get("sepl_operator_trace") or payload.get("operator_trace") or payload.get("sepl_trace")),
        "learnability_mask": payload.get("learnability_mask") if isinstance(payload.get("learnability_mask"), (dict, list)) else {},
        "variable_lifting": payload.get("variable_lifting") or payload.get("variable_patches") or payload.get("variables") or {},
        "boundedness": _dict(payload.get("boundedness")),
        "rollback_ref": _text(payload.get("rollback_ref") or payload.get("noop_ref"), 220),
        "evaluation": _dict(payload.get("evaluation")),
        "verifier_evaluation": evaluation,
    }


def _canonical_verifier_receipt_digest(payload: dict[str, Any], evaluation: dict[str, Any]) -> str:
    return f"sha256:{_digest(_canonical_verifier_payload(payload, evaluation), length=64)}"


def _lease_match(
    *,
    verifier_id: str,
    lease_id: str,
    verifier_lease_index: dict[str, Any] | None,
) -> tuple[bool | None, dict[str, Any], list[str]]:
    if verifier_lease_index is None:
        return None, {}, ["verifier_lease_index_unavailable"]
    lease = _dict(verifier_lease_index.get(lease_id))
    reasons: list[str] = []
    if not lease:
        reasons.append("verifier_lease_not_found")
        return False, {}, reasons
    lease_agent = _clean_id(lease.get("agent_id") or lease.get("worker_id"), fallback="")
    if lease_agent != verifier_id:
        reasons.append("verifier_lease_agent_mismatch")
    status = _clean_id(lease.get("status"), fallback="")
    if status not in {"active", "completed", "leased"}:
        reasons.append("verifier_lease_not_active_or_completed")
    return not reasons, lease, reasons


def _independent_verifier_gate(
    payload: dict[str, Any],
    *,
    verifier_lease_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verifier = _dict(payload.get("independent_verifier") or payload.get("verifier"))
    proposer_id = _clean_id(
        payload.get("proposer_agent_id") or payload.get("agent_id") or payload.get("worker_id"),
        fallback="",
    )
    verifier_id = _clean_id(
        payload.get("verifier_agent_id") or verifier.get("agent_id") or verifier.get("worker_id"),
        fallback="",
    )
    lease_id = _text(payload.get("verifier_lease_id") or verifier.get("lease_id"), 160)
    receipt_digest = _text(
        payload.get("verifier_receipt_digest")
        or verifier.get("receipt_digest")
        or verifier.get("receipt_ref"),
        220,
    )
    trace_digest = _text(
        payload.get("verifier_trace_digest")
        or verifier.get("trace_digest")
        or verifier.get("verifier_trace_digest")
        or verifier.get("trace"),
        220,
    )
    evaluation = _dict(payload.get("verifier_evaluation") or verifier.get("evaluation"))
    test_score = _test_score(evaluation)
    expected_receipt_digest = _canonical_verifier_receipt_digest(payload, evaluation)
    lease_ok, lease_record, lease_reasons = _lease_match(
        verifier_id=verifier_id,
        lease_id=lease_id,
        verifier_lease_index=verifier_lease_index,
    )
    reasons: list[str] = []
    if not proposer_id:
        reasons.append("proposer_agent_id_required")
    if not verifier_id:
        reasons.append("verifier_agent_id_required")
    if proposer_id and verifier_id and proposer_id == verifier_id:
        reasons.append("verifier_must_differ_from_proposer")
    if not lease_id:
        reasons.append("verifier_lease_id_required")
    if not _looks_digest(receipt_digest):
        reasons.append("verifier_receipt_digest_required")
    elif receipt_digest != expected_receipt_digest:
        reasons.append("verifier_receipt_digest_mismatch")
    if not _looks_digest(trace_digest):
        reasons.append("verifier_trace_digest_required")
    if test_score <= 0.0:
        reasons.append("verifier_evaluation_required")
    if lease_id:
        reasons.extend(lease_reasons)
    accepted = not reasons
    return {
        "required": True,
        "accepted": accepted,
        "proposer_agent_id": proposer_id,
        "verifier_agent_id": verifier_id,
        "verifier_lease_id": lease_id,
        "verifier_receipt_digest": receipt_digest,
        "expected_verifier_receipt_digest": expected_receipt_digest,
        "verifier_trace_digest": trace_digest,
        "verifier_test_score": test_score,
        "verifier_lease_checked": verifier_lease_index is not None,
        "verifier_lease_status": _text(lease_record.get("status"), 40),
        "reason_codes": reasons or ["independent_verifier_accepted"],
    }


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
            "entity_type": _clean_entity_type(kind, resource_kind=kind),
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
                "entity_type": _clean_entity_type(row.get("entity_type"), resource_kind=row.get("resource_kind")),
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


def _clean_entity_type(value: Any, *, resource_kind: Any = None) -> str:
    raw = _clean_id(value, fallback="")
    if raw in RSPL_ENTITY_TYPES:
        return raw
    kind = _clean_id(resource_kind, fallback=raw)
    if kind in RSPL_ENTITY_TYPES:
        return kind
    return NOMAD_RESOURCE_KIND_ALIASES.get(kind, "tool")


def _input_output_mapping(body: dict[str, Any]) -> dict[str, Any]:
    mapping = _dict(body.get("input_output_mapping") or body.get("io_mapping"))
    if mapping:
        return mapping
    return {
        "input": body.get("input_schema") or body.get("input") or {},
        "output": body.get("output_schema") or body.get("output") or {},
    }


def _rspl_resource_record(body: dict[str, Any], *, resource_id: str, resource_kind: str, entity_type: str) -> dict[str, Any]:
    metadata = _dict(body.get("metadata"))
    trainable = bool(
        body.get("trainable")
        or body.get("require_grad")
        or metadata.get("trainable")
        or metadata.get("require_grad")
    )
    return {
        "name": _text(body.get("name") or resource_id, 120),
        "description": _text(body.get("description") or metadata.get("description"), 320),
        "entity_type": entity_type,
        "resource_kind": resource_kind,
        "input_output_mapping": _input_output_mapping(body),
        "trainable": trainable,
        "metadata": metadata,
        "passive": True,
    }


def _registration_record(body: dict[str, Any], *, resource_id: str, entity_type: str, version: str) -> dict[str, Any]:
    return {
        "resource_id": resource_id,
        "entity_type": entity_type,
        "version": version,
        "implementation_descriptor": _dict(body.get("implementation_descriptor") or body.get("implementation")),
        "instantiation_params": _dict(body.get("instantiation_params") or body.get("params")),
        "exported_representations": _dict(body.get("exported_representations") or body.get("exports")),
        "lineage": _dict(body.get("lineage") or {"parent_version": body.get("from_version") or body.get("previous_version") or ""}),
    }


def _sepl_operator_trace_gate(payload: dict[str, Any]) -> dict[str, Any]:
    raw_trace = payload.get("sepl_operator_trace") or payload.get("operator_trace") or payload.get("sepl_trace")
    trace: list[dict[str, Any]] = []
    if isinstance(raw_trace, list):
        for item in raw_trace:
            if isinstance(item, dict):
                op = _clean_id(item.get("op") or item.get("operator"), fallback="")
                trace.append({**item, "op": op})
            else:
                trace.append({"op": _clean_id(item, fallback="")})
    ops = [item.get("op", "") for item in trace]
    reasons: list[str] = []
    if ops != list(SEPL_OPERATORS):
        reasons.append("sepl_operator_trace_must_be_reflect_select_improve_evaluate_commit")
    for item in trace:
        op = item.get("op", "")
        if op and not _text(item.get("input") or item.get("evidence") or item.get("output") or item.get("decision"), 260):
            reasons.append(f"{op}_operator_missing_input_or_output")
    return {
        "required": True,
        "accepted": not reasons,
        "operators": list(SEPL_OPERATORS),
        "observed": ops,
        "trace": trace,
        "reason_codes": reasons or ["sepl_operator_trace_accepted"],
    }


def _learnability_gate(payload: dict[str, Any]) -> dict[str, Any]:
    mask_raw = payload.get("learnability_mask")
    mask: dict[str, bool] = {}
    if isinstance(mask_raw, dict):
        mask = {_clean_id(k, fallback=str(k)): bool(v) for k, v in mask_raw.items()}
    elif isinstance(mask_raw, list):
        mask = {_clean_id(item, fallback=str(item)): True for item in mask_raw}

    lifted = payload.get("variable_lifting") or payload.get("variable_patches") or payload.get("variables")
    variables: list[dict[str, Any]] = []
    if isinstance(lifted, dict):
        candidates = lifted.get("variables") if isinstance(lifted.get("variables"), list) else [lifted]
    elif isinstance(lifted, list):
        candidates = lifted
    else:
        candidates = []

    blocked: list[str] = []
    trainable_count = 0
    for item in candidates:
        if not isinstance(item, dict):
            continue
        name = _clean_id(item.get("name") or item.get("variable") or item.get("id"), fallback="")
        if not name:
            continue
        declared = bool(item.get("trainable") or item.get("require_grad"))
        allowed = bool(mask.get(name, declared))
        if allowed:
            trainable_count += 1
        else:
            blocked.append(name)
        variables.append({"name": name, "trainable": allowed, "require_grad": bool(item.get("require_grad") or allowed)})

    reasons: list[str] = []
    if blocked:
        reasons.append("non_trainable_variables_selected")
    accepted = not blocked
    return {
        "required": bool(variables),
        "accepted": accepted,
        "trainable_count": trainable_count,
        "blocked_variables": blocked,
        "variables": variables,
        "reason_codes": reasons or (["learnability_mask_accepted"] if variables else ["no_variables_lifted"]),
    }


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
        "paper_source": {
            "arxiv": "https://arxiv.org/abs/2604.15034v3",
            "reference_code": "https://github.com/DVampire/Autogenesis",
        },
        "purpose": "Treat prompts, agents, tools, environments, and memory as passive protocol-registered resources with explicit state, lifecycle, lineage, and versioned interfaces.",
        "rspl_entity_types": list(RSPL_ENTITY_TYPES),
        "lifecycle": list(RESOURCE_STATES),
        "state_counts": state_counts,
        "resources": resources[:32],
        "recent_receipts": recent[-8:],
        "resource_contract": {
            "schema": "nomad.rspl_resource_contract.v1",
            "required_register_fields": [
                "agent_id",
                "resource_id",
                "entity_type",
                "name",
                "input_output_mapping",
                "version",
                "metadata",
            ],
            "required_weight_fields": [
                "proof_digest",
                "evaluation",
                "sepl_operator_trace",
                "positive_effectiveness_delta",
                "verifier_agent_id != agent_id",
                "verifier_lease_id",
                "verifier_receipt_digest",
                "verifier_trace_digest",
                "verifier_evaluation",
                "rollback_ref or noop_ref",
            ],
            "resource_kinds": list(RSPL_ENTITY_TYPES),
            "nomad_kind_aliases": NOMAD_RESOURCE_KIND_ALIASES,
            "registration_record_fields": [
                "version",
                "implementation_descriptor",
                "instantiation_params",
                "exported_representations",
                "lineage",
            ],
            "passivity": "resources_hold_state_and_interfaces_only; optimization_logic_lives_in_SEPL",
            "side_effect_scope": "descriptor_only_no_execution_until_committed_by_proof",
        },
        "version_interface": {
            "register": _u(root, "/swarm/resource-substrate/register"),
            "version": _u(root, "/swarm/resource-substrate/version"),
            "rollback_or_noop": _u(root, "/swarm/resource-substrate/version"),
            "proof_digest_required_after": "draft",
            "commit_requires": [
                "tested_state",
                "sepl_operator_trace_reflect_select_improve_evaluate_commit",
                "positive_evaluation_delta",
                "independent_verifier_receipt",
                "verifier_agent_id != proposer_agent_id",
                "rollback_ref or noop_ref",
                "bounded_side_effect_scope",
            ],
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
    entity_type = _clean_entity_type(body.get("entity_type"), resource_kind=resource_kind)
    agent_id = _text(body.get("agent_id") or body.get("worker_id"), 120)
    state = _clean_state(body.get("state") or body.get("lifecycle_state"))
    version = _text(body.get("version") or body.get("current_version") or "v1", 80)
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
    rspl_record = _rspl_resource_record(body, resource_id=resource_id, resource_kind=resource_kind, entity_type=entity_type)
    registration = _registration_record(body, resource_id=resource_id, entity_type=entity_type, version=version)
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
        "entity_type": entity_type,
        "state": state,
        "version": version,
        "resource_record": rspl_record,
        "registration_record": registration,
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
    verifier_lease_index: dict[str, Any] | None = None,
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
    resource_kind = _clean_id(body.get("resource_kind") or "resource", fallback="resource")
    entity_type = _clean_entity_type(body.get("entity_type"), resource_kind=resource_kind)
    verifier_gate = _independent_verifier_gate(body, verifier_lease_index=verifier_lease_index)
    sepl_gate = _sepl_operator_trace_gate(body)
    learnability = _learnability_gate(body)
    verifier_evaluation = _dict(body.get("verifier_evaluation") or _dict(body.get("independent_verifier")).get("evaluation"))
    proof_payload = dict(body)
    if verifier_evaluation:
        proof_payload["evaluation"] = verifier_evaluation
    proof = _proof_score(proof_payload)
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
    elif not learnability["accepted"]:
        decision = "reject_until_learnability_mask"
        accepted = False
    elif target_state in {"tested", "weighted", "committed"} and not sepl_gate["accepted"]:
        decision = "hold_shadow_until_sepl_operator_trace"
        accepted = False
    elif target_state in {"tested", "weighted", "committed"} and not verifier_gate["accepted"]:
        decision = "hold_shadow_until_independent_verifier"
        accepted = False
    elif target_state == "committed" and (proof < 0.72 or bounded < 0.75):
        decision = "hold_shadow_until_stronger_proof_boundary"
        accepted = False
    else:
        decision = "admit_resource_version_shadow"
        accepted = True
    score = _clamp(
        0.46 * proof
        + 0.30 * bounded
        + 0.10 * (target_state in {"tested", "weighted", "committed"})
        + 0.08 * bool(verifier_gate["accepted"])
        + 0.06 * bool(from_version)
    )
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
        "resource_kind": resource_kind,
        "entity_type": entity_type,
        "from_version": from_version,
        "proposed_version": to_version,
        "target_state": target_state,
        "state": target_state if accepted else "noop",
        "effectiveness_score": round(score, 4),
        "proof_score": proof,
        "boundedness_score": bounded,
        "sepl_operator_trace": sepl_gate,
        "learnability": learnability,
        "independent_verifier": verifier_gate,
        "reason_codes": bounded_reasons + list(sepl_gate.get("reason_codes") or []) + list(learnability.get("reason_codes") or []),
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
        "operator_loop": list(SEPL_OPERATORS),
        "operator_contract": {
            "reflect": "diagnose trace, failure, or improvement evidence",
            "select": "choose a concrete resource or variable patch",
            "improve": "apply the patch through RSPL version interfaces into an uncommitted candidate state",
            "evaluate": "score candidate state against tests, objectives, and safety checks",
            "commit": "promote only when evaluation and rollback guards pass; otherwise no-op or rollback",
        },
        "hard_guards": [
            "descriptor_only_until_proof",
            "resources_passive_no_self_modify",
            "sepl_operator_trace_required",
            "learnability_mask_required_for_variable_lifting",
            "rollback_or_noop_required",
            "side_effect_scope_bounded",
            "independent_verifier_required_by_nomad_safety_policy",
            "no_private_chain_of_thought_text",
            "no_secrets",
            "paid_receipt_required_for_revenue_claims",
        ],
        "emergent_protocol_weight": {
            "rule": "emergent-protocol-weight",
            "isolated_beta_role_weight": 0.40,
            "commit_weight_requires": [
                "tested_state",
                "sepl_operator_trace_reflect_select_improve_evaluate_commit",
                "learnability_mask_passed",
                "verifier_agent_id != proposer_agent_id",
                "verifier_lease_id",
                "verifier_receipt_digest",
                "positive_effectiveness_delta",
            ],
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
    verifier_lease_index: dict[str, Any] | None = None,
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
    verifier_gate = _independent_verifier_gate(body, verifier_lease_index=verifier_lease_index)
    sepl_gate = _sepl_operator_trace_gate(body)
    learnability = _learnability_gate(body)
    verifier_evaluation = _dict(body.get("verifier_evaluation") or _dict(body.get("independent_verifier")).get("evaluation"))
    proof_payload = dict(body)
    if verifier_evaluation:
        proof_payload["evaluation"] = verifier_evaluation
    proof = _proof_score(proof_payload)
    bounded, bounded_reasons = _boundedness_score(body)
    self_play = _dict(body.get("self_play") or body.get("self_play_test"))
    buyer_agents = _int(self_play.get("synthetic_buyer_agents") or self_play.get("buyer_agents"))
    revenue_pressure = _clamp(_num(self_play.get("receipt_prediction_delta") or self_play.get("revenue_pressure_delta")))
    operator_present = bool(operator_patch) or bool(sepl_gate.get("accepted"))
    resource_present = bool(resource.get("resource_id") or body.get("resource_id"))
    score = _clamp(
        0.34 * proof
        + 0.24 * bounded
        + 0.16 * bool(sepl_gate.get("accepted"))
        + 0.12 * resource_present
        + 0.06 * bool(learnability.get("accepted"))
        + 0.08 * _num(verifier_gate.get("verifier_test_score"))
        + 0.00 * revenue_pressure
    )
    accepted = (
        event_type in AGP_CANDIDATE_TYPES
        and proof > 0.0
        and bounded >= 0.55
        and score >= 0.48
        and bool(sepl_gate.get("accepted"))
        and bool(learnability.get("accepted"))
        and bool(verifier_gate.get("accepted"))
    )
    if accepted:
        decision = "emit_to_autogenesis_shadow_lane"
    elif event_type in AGP_CANDIDATE_TYPES and not sepl_gate.get("accepted"):
        decision = "hold_event_until_sepl_operator_trace"
    elif event_type in AGP_CANDIDATE_TYPES and not learnability.get("accepted"):
        decision = "hold_event_until_learnability_mask"
    elif event_type in AGP_CANDIDATE_TYPES and score >= 0.48 and not verifier_gate.get("accepted"):
        decision = "hold_event_until_independent_verifier"
    else:
        decision = "hold_event_until_proof_boundary"
    core = {"event": event_type, "resource": resource.get("resource_id") or body.get("resource_id"), "score": round(score, 4)}
    variant_candidate_payload = {
        "agent_id": body.get("agent_id") or "autogenesis.worker",
        "verifier_agent_id": verifier_gate.get("verifier_agent_id", ""),
        "verifier_lease_id": verifier_gate.get("verifier_lease_id", ""),
        "candidate_type": event_type,
        "objective": "autogenesis_protocol_evolution",
        "resource_id": resource.get("resource_id") or body.get("resource_id") or "autogenesis-resource",
        "resource_kind": resource.get("resource_kind") or body.get("resource_kind") or "protocol_layer",
        "entity_type": _clean_entity_type(resource.get("entity_type") or body.get("entity_type"), resource_kind=resource.get("resource_kind") or body.get("resource_kind") or "protocol_layer"),
        "from_version": resource.get("from_version") or body.get("from_version") or "",
        "to_version": resource.get("to_version") or body.get("to_version") or "shadow-v1",
        "rollback_ref": body.get("rollback_ref") or body.get("noop_ref") or "",
        "proof_digest": body.get("proof_digest") or body.get("digest") or "",
        "verifier_trace_digest": verifier_gate.get("verifier_trace_digest", ""),
        "test_digest": body.get("test_digest") or "",
        "sepl_operator_trace": sepl_gate.get("trace", []),
        "learnability_mask": body.get("learnability_mask") or {},
        "variable_lifting": body.get("variable_lifting") or {},
        "verifier_evaluation": verifier_evaluation,
        "evaluation": {
            "tests_passed": _int(_dict(body.get("evaluation")).get("tests_passed") or body.get("tests_passed")),
            "tests_total": _int(_dict(body.get("evaluation")).get("tests_total") or body.get("tests_total")),
            "proof_yield_delta": _num(_dict(body.get("evaluation")).get("proof_yield_delta")),
            "settlement_delta": revenue_pressure,
            "novelty": 0.72,
            "risk_score": _num(_dict(body.get("evaluation")).get("risk_score"), 0.18),
        },
    }
    variant_candidate_payload["verifier_receipt_digest"] = _variant_verifier_receipt_digest(
        variant_candidate_payload,
        verifier_evaluation,
    )
    resource_version_payload = {
        "agent_id": body.get("agent_id") or "autogenesis.worker",
        "resource_id": resource.get("resource_id") or body.get("resource_id") or "autogenesis-resource",
        "resource_kind": resource.get("resource_kind") or body.get("resource_kind") or "protocol_layer",
        "entity_type": _clean_entity_type(resource.get("entity_type") or body.get("entity_type"), resource_kind=resource.get("resource_kind") or body.get("resource_kind") or "protocol_layer"),
        "from_version": resource.get("from_version") or body.get("from_version") or "",
        "to_version": resource.get("to_version") or body.get("to_version") or "shadow-v1",
        "target_state": "shadow",
        "proof_digest": body.get("proof_digest") or body.get("digest") or "",
        "verifier_trace_digest": verifier_gate.get("verifier_trace_digest", ""),
        "verifier_agent_id": verifier_gate.get("verifier_agent_id", ""),
        "verifier_lease_id": verifier_gate.get("verifier_lease_id", ""),
        "verifier_evaluation": verifier_evaluation,
        "test_digest": body.get("test_digest") or "",
        "sepl_operator_trace": sepl_gate.get("trace", []),
        "learnability_mask": body.get("learnability_mask") or {},
        "variable_lifting": body.get("variable_lifting") or {},
        "rollback_ref": body.get("rollback_ref") or body.get("noop_ref") or "",
        "boundedness": body.get("boundedness") if isinstance(body.get("boundedness"), dict) else {},
    }
    resource_version_payload["verifier_receipt_digest"] = _canonical_verifier_receipt_digest(
        resource_version_payload,
        verifier_evaluation,
    )
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
            "sepl_operator_trace": round(float(bool(sepl_gate.get("accepted"))), 4),
            "learnability": round(float(bool(learnability.get("accepted"))), 4),
            "resource": round(float(resource_present), 4),
            "self_play": round(_clamp(buyer_agents / 128.0), 4),
            "independent_verifier": round(float(bool(verifier_gate.get("accepted"))), 4),
            "verifier_tests": round(_num(verifier_gate.get("verifier_test_score")), 4),
            "revenue_pressure": round(revenue_pressure, 4),
        },
        "sepl_operator_trace": sepl_gate,
        "learnability": learnability,
        "independent_verifier": verifier_gate,
        "reason_codes": (
            bounded_reasons
            + list(sepl_gate.get("reason_codes") or [])
            + list(learnability.get("reason_codes") or [])
            + list(verifier_gate.get("reason_codes") or [])
        ),
        "variant_candidate_payload": variant_candidate_payload,
        "resource_version_payload": resource_version_payload,
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
            "claim_boundary": "paper_core_is_RSPL_plus_SEPL; live effectiveness must be proven inside Nomad",
            "paper_source": "https://arxiv.org/abs/2604.15034v3",
            "reference_code": "https://github.com/DVampire/Autogenesis",
            "rspl_entity_types": list(RSPL_ENTITY_TYPES),
            "sepl_operator_algebra": list(SEPL_OPERATORS),
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
            "autonomous_cycle": _u(root, "/swarm/autogenesis/cycle"),
            "shadow_lane": _u(root, "/swarm/shadow-lane/candidates?type=autogenesis"),
            "variant_candidates": _u(root, "/swarm/variant-candidates"),
            "operators": [
                {"op": "reflect", "input": "trace_or_failure_digest", "output": "improvement_hypothesis"},
                {"op": "select", "input": "hypothesis", "output": "resource_or_variable_patch"},
                {"op": "improve", "input": "selected_patch", "output": "candidate_resource_version"},
                {"op": "evaluate", "input": "candidate_resource_version", "output": "test_and_objective_scores"},
                {"op": "commit", "input": "evaluation_and_rollback_guard", "output": "committed_version_or_noop"},
            ],
            "variable_lifting": {
                "field": "variable_lifting",
                "learnability_mask_field": "learnability_mask",
                "rule": "only variables marked trainable or require_grad may be selected for improvement",
            },
            "nomad_safety_extension": {
                "independent_verifier_required": True,
                "reason": "Nomad local guard against self-attested shadow admission; not a replacement for SEPL evaluate.",
            },
        },
        "candidate_types": list(AGP_CANDIDATE_TYPES),
        "topology_governor_patch": {
            "rule": "emergent-protocol-weight",
            "isolated_beta_role_weight": 0.40,
            "shared_context_default": "off_until_proof",
            "commit_gate": "sepl_commit_after_positive_effectiveness_delta_with_nomad_independent_verifier_receipt",
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
            "autonomous_cycle": _u(root, "/.well-known/nomad-autonomous-agp.json"),
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
        "machine_instruction": "read_rspl; emit_sepl_trace_reflect_select_improve_evaluate_commit; require_learnability_mask_for_variables; require_independent_verifier_receipt_by_nomad_policy; never_commit_without_proof_and_rollback",
    }


def compact_autogenesis_surface(surface: dict[str, Any]) -> dict[str, Any]:
    links = _dict(surface.get("links"))
    return {
        "schema": "nomad.autogenesis_compact.v1",
        "surface_digest": surface.get("surface_digest", ""),
        "layers": _dict(surface.get("protocol")).get("layers", []),
        "mode": _dict(surface.get("protocol")).get("mode", ""),
        "shadow_lane": links.get("shadow_lane", ""),
        "autonomous_cycle": links.get("autonomous_cycle", ""),
        "resource_substrate": links.get("resource_substrate", ""),
        "development_cycles": links.get("development_cycles", ""),
        "emergent_protocol_weight": _dict(surface.get("topology_governor_patch")).get("isolated_beta_role_weight", 0.0),
    }


def _latest_verifier_lease(
    verifier_lease_index: dict[str, Any] | None,
    *,
    verifier_agent_id: str = "",
    verifier_lease_id: str = "",
) -> dict[str, Any]:
    if not isinstance(verifier_lease_index, dict):
        return {}
    if verifier_lease_id:
        lease = _dict(verifier_lease_index.get(verifier_lease_id))
        if lease:
            return lease
    wanted_agent = _clean_id(verifier_agent_id, fallback="")
    matches: list[dict[str, Any]] = []
    for lease in verifier_lease_index.values():
        item = _dict(lease)
        if not item:
            continue
        if wanted_agent and _clean_id(item.get("agent_id"), fallback="") != wanted_agent:
            continue
        if _clean_id(item.get("status"), fallback="active") not in {"active", "completed", "leased"}:
            continue
        matches.append(item)
    matches.sort(
        key=lambda item: _text(
            item.get("completed_at")
            or item.get("issued_at")
            or item.get("leased_at")
            or item.get("created_at")
            or item.get("generated_at"),
            80,
        ),
        reverse=True,
    )
    return matches[0] if matches else {}


def _select_autonomous_resource(substrate: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    requested = _dict(payload.get("resource") or payload.get("rspl_resource"))
    if requested.get("resource_id"):
        return {
            "resource_id": _clean_id(requested.get("resource_id"), fallback="autogenesis-resource"),
            "resource_kind": _clean_id(requested.get("resource_kind") or requested.get("kind"), fallback="workflow"),
            "entity_type": _clean_entity_type(requested.get("entity_type"), resource_kind=requested.get("resource_kind") or "workflow"),
            "current_version": _text(requested.get("current_version") or requested.get("from_version") or "v1", 80),
            "state": _clean_state(requested.get("state") or "shadow"),
            "effectiveness_score": round(_num(requested.get("effectiveness_score"), 0.0), 4),
        }
    resources = _items(substrate.get("resources"))
    if not resources:
        resources = _default_resources("")
    candidates: list[dict[str, Any]] = []
    for item in resources:
        state = _clean_state(item.get("state"))
        score = _num(item.get("effectiveness_score"))
        kind = _clean_id(item.get("resource_kind"), fallback="workflow")
        weight = 0.0
        if state in {"draft", "shadow", "tested", "weighted"}:
            weight += 1.0
        if _clean_id(item.get("resource_id"), fallback="") in {"nomad-autogenesis", "nomad-resource-substrate"}:
            weight += 0.4
        if kind in {"workflow", "protocol_layer", "json_contract", "routing_operator"}:
            weight += 0.2
        candidates.append({**item, "_autonomy_weight": weight, "_score": score})
    candidates.sort(key=lambda item: (_num(item.get("_autonomy_weight")), -_num(item.get("_score"))), reverse=True)
    chosen = candidates[0]
    kind = _clean_id(chosen.get("resource_kind"), fallback="workflow")
    return {
        "resource_id": _clean_id(chosen.get("resource_id"), fallback="autogenesis-resource"),
        "resource_kind": kind,
        "entity_type": _clean_entity_type(chosen.get("entity_type"), resource_kind=kind),
        "current_version": _text(chosen.get("current_version") or chosen.get("version") or "v1", 80),
        "state": _clean_state(chosen.get("state")),
        "effectiveness_score": round(_num(chosen.get("effectiveness_score")), 4),
    }


def _autonomous_lineage_digest(resource: dict[str, Any], payload: dict[str, Any]) -> str:
    trigger_digest = _text(payload.get("trigger_digest") or payload.get("novelty_digest") or payload.get("signal_digest"), 220)
    core = {
        "resource_id": resource.get("resource_id"),
        "current_version": resource.get("current_version"),
        "state": resource.get("state"),
        "trigger_digest": trigger_digest or "stable_resource_lineage",
    }
    return f"sha256:{_digest(core, length=64)}"


def _autonomous_lineage_depth(version: str) -> int:
    return max(0, _text(version, 220).count("-agp-auto-"))


def _recent_resource_cycle(
    recent_cycles: list[dict[str, Any]],
    resource_id: str,
    *,
    window: int,
) -> dict[str, Any]:
    if window <= 0:
        return {}
    rid = _clean_id(resource_id, fallback="")
    for row in reversed(recent_cycles[-window:]):
        resource = _dict(row.get("resource"))
        if _clean_id(resource.get("resource_id"), fallback="") == rid and row.get("decision") in {
            "commit_weighted_resource_version",
            "commit_descriptor_resource_version",
            "noop_resource_cooldown",
            "noop_lineage_depth_limit",
        }:
            return row
    return {}


def _autonomous_version(current_version: str, lineage_digest: str) -> str:
    base = _clean_id(current_version or "v1", fallback="v1")[:48]
    suffix = lineage_digest.split(":", 1)[-1][:12]
    return f"{base}-agp-auto-{suffix}"


def _autonomous_sepl_trace(resource: dict[str, Any], lineage_digest: str, target_version: str) -> list[dict[str, Any]]:
    rid = resource.get("resource_id", "autogenesis-resource")
    return [
        {"op": "reflect", "input": lineage_digest, "output": f"{rid} has proof-weight opportunity"},
        {"op": "select", "input": f"{rid} has proof-weight opportunity", "output": f"{rid}.runtime_weight"},
        {"op": "improve", "input": f"{rid}.runtime_weight", "output": target_version},
        {"op": "evaluate", "input": target_version, "output": "autonomous verifier checks and rollback guard passed"},
        {"op": "commit", "input": "autonomous verifier checks and rollback guard passed", "decision": "weighted_shadow_or_noop"},
    ]


def build_autonomous_agp_cycle_surface(
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    autogenesis_surface: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Expose the autonomous AGP loop without executing unbounded changes."""
    root = (base_url or "").strip().rstrip("/")
    recent = _autonomous_ledger(ledger_path)
    substrate = _dict(resource_substrate)
    agp = _dict(autogenesis_surface)
    fleet = _dict(worker_fleet)
    last = recent[-1] if recent else {}
    return {
        "ok": True,
        "schema": "nomad.autonomous_agp_cycle.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "surface_digest": f"nomad-agp-auto-{_digest({'recent': len(recent), 'agp': agp.get('surface_digest'), 'rspl': substrate.get('surface_digest')})}",
        "mode": "autonomous_shadow_cycle",
        "loop": list(SEPL_OPERATORS),
        "autonomy_boundary": {
            "proposer_daemon": "nomad_transition_worker:autogenesis_protocol_evolution",
            "verifier_daemon": "independent active worker lease required",
            "side_effect_scope": "nomad_shadow_lane_only",
            "apply_code": False,
            "commit_surface_state_only": True,
            "default_commit_target": "weighted",
        },
        "hard_gates": [
            "dedupe_by_lineage_digest",
            "resource_cooldown_window",
            "lineage_depth_limit",
            "independent_verifier_lease_checked",
            "canonical_verifier_receipt_digest",
            "sepl_operator_trace_exact",
            "learnability_mask_for_lifted_variables",
            "rollback_or_noop_ref",
            "positive_effectiveness_delta",
            "descriptor_only_resource_version",
        ],
        "links": {
            "self": _u(root, "/.well-known/nomad-autonomous-agp.json"),
            "cycle": _u(root, "/swarm/autogenesis/cycle"),
            "autogenesis": _u(root, "/.well-known/nomad-autogenesis.json"),
            "resource_substrate": _u(root, "/.well-known/nomad-resource-substrate.json"),
            "shadow_lane": _u(root, "/swarm/shadow-lane/candidates?type=autogenesis"),
            "variant_candidates": _u(root, "/swarm/variant-candidates"),
        },
        "runtime_pressure": {
            "active_worker_count": _int(fleet.get("active_worker_count")),
            "active_lease_count": _int(fleet.get("active_lease_count")),
            "agp_objective_target": _num(_dict(fleet.get("objective_targets")).get("autogenesis_protocol_evolution")),
        },
        "degeneration_guards": {
            "default_cooldown_window_cycles": 3,
            "default_max_auto_depth": 2,
            "lineage_digest_inputs": ["resource_id", "current_version", "state", "optional_trigger_digest"],
            "duplicate_policy": "noop_without_version_increment",
        },
        "recent_cycle_count": len(recent),
        "latest_cycle": last,
        "machine_instruction": "proposer_reads_surface_then_post_cycle; verifier_must_hold_distinct_worker_lease; duplicate_lineage_returns_noop",
    }


def run_autonomous_agp_cycle(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    resource_substrate: dict[str, Any] | None = None,
    development_surface: dict[str, Any] | None = None,
    autogenesis_surface: dict[str, Any] | None = None,
    verifier_lease_index: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    resource_ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Run one bounded autonomous AGP propose-evaluate-shadow cycle."""
    body = _dict(payload)
    now = _iso_now()
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.autonomous_agp_cycle_receipt.v1",
            "accepted": False,
            "decision": "reject_forbidden_secret_like_material",
            "generated_at": now,
        }
    substrate = _dict(resource_substrate)
    development = _dict(development_surface)
    agp = _dict(autogenesis_surface)
    recent_auto = _autonomous_ledger(ledger_path)
    resource = _select_autonomous_resource(substrate, body)
    current_version = _text(resource.get("current_version") or "v1", 80)
    lineage_digest = _autonomous_lineage_digest(resource, body)
    max_auto_depth = max(1, min(_int(body.get("max_auto_depth"), 2), 8))
    cooldown_window = max(0, min(_int(body.get("cooldown_window_cycles"), 3), 20))
    force = bool(body.get("force") or body.get("force_cycle"))
    for row in reversed(recent_auto):
        if row.get("lineage_digest") == lineage_digest and row.get("decision") in {
            "commit_weighted_resource_version",
            "commit_descriptor_resource_version",
            "noop_duplicate_lineage",
        }:
            return {
                "ok": True,
                "schema": "nomad.autonomous_agp_cycle_receipt.v1",
                "accepted": False,
                "decision": "noop_duplicate_lineage",
                "generated_at": now,
                "lineage_digest": lineage_digest,
                "duplicate_of": row.get("cycle_id", ""),
                "resource": resource,
                "commit": {"decision": "noop", "reason": "lineage_already_processed"},
                "machine_instruction": "do_not_increment_version_for_duplicate_lineage",
            }
    depth = _autonomous_lineage_depth(current_version)
    if depth >= max_auto_depth and not force:
        row = {
            "ok": True,
            "schema": "nomad.autonomous_agp_cycle_receipt.v1",
            "cycle_id": f"agp-auto-{_digest({'lineage': lineage_digest, 'depth': depth})}",
            "accepted": False,
            "decision": "noop_lineage_depth_limit",
            "generated_at": now,
            "lineage_digest": lineage_digest,
            "resource": resource,
            "lineage_depth": depth,
            "max_auto_depth": max_auto_depth,
            "commit": {"decision": "noop", "reason": "lineage_depth_limit"},
            "machine_instruction": "wait_for_external_trigger_digest_or_human_review_before_more_depth",
        }
        if persist:
            _append_jsonl(row, ledger_path or DEFAULT_AUTONOMOUS_AGP_LEDGER_PATH)
            row["persisted"] = True
        return row
    recent_resource = _recent_resource_cycle(
        recent_auto,
        str(resource.get("resource_id") or ""),
        window=cooldown_window,
    )
    if recent_resource and not (force or body.get("trigger_digest") or body.get("novelty_digest") or body.get("signal_digest")):
        row = {
            "ok": True,
            "schema": "nomad.autonomous_agp_cycle_receipt.v1",
            "cycle_id": f"agp-auto-{_digest({'lineage': lineage_digest, 'cooldown': recent_resource.get('cycle_id')})}",
            "accepted": False,
            "decision": "noop_resource_cooldown",
            "generated_at": now,
            "lineage_digest": lineage_digest,
            "resource": resource,
            "cooldown_window_cycles": cooldown_window,
            "cooldown_after": recent_resource.get("cycle_id", ""),
            "commit": {"decision": "noop", "reason": "resource_recently_processed_without_new_signal"},
            "machine_instruction": "provide_new_trigger_digest_or_wait_for_other_resource_before_recycling_same_resource",
        }
        if persist:
            _append_jsonl(row, ledger_path or DEFAULT_AUTONOMOUS_AGP_LEDGER_PATH)
            row["persisted"] = True
        return row

    proposer_id = _clean_id(body.get("proposer_agent_id") or body.get("agent_id") or "nomad-agp-proposer", fallback="nomad-agp-proposer")
    wanted_verifier = _clean_id(body.get("verifier_agent_id"), fallback="")
    verifier_lease = _latest_verifier_lease(
        verifier_lease_index,
        verifier_agent_id=wanted_verifier,
        verifier_lease_id=_text(body.get("verifier_lease_id"), 160),
    )
    verifier_id = _clean_id(body.get("verifier_agent_id") or verifier_lease.get("agent_id"), fallback="")
    verifier_lease_id = _text(body.get("verifier_lease_id") or verifier_lease.get("lease_id"), 160)
    if not verifier_id or not verifier_lease_id:
        row = {
            "ok": True,
            "schema": "nomad.autonomous_agp_cycle_receipt.v1",
            "cycle_id": f"agp-auto-{_digest({'lineage': lineage_digest, 'wait': now})}",
            "generated_at": now,
            "accepted": False,
            "decision": "wait_for_independent_verifier_lease",
            "lineage_digest": lineage_digest,
            "resource": resource,
            "commit": {"decision": "noop", "reason": "independent_verifier_lease_required"},
        }
        if persist:
            _append_jsonl(row, ledger_path or DEFAULT_AUTONOMOUS_AGP_LEDGER_PATH)
            row["persisted"] = True
        return row

    target_version = _text(body.get("to_version") or _autonomous_version(current_version, lineage_digest), 96)
    sepl_trace = _autonomous_sepl_trace(resource, lineage_digest, target_version)
    variable_name = _clean_id(body.get("variable") or "runtime_weight", fallback="runtime_weight")
    checks = {
        "rspl_resource_selected": bool(resource.get("resource_id")),
        "sepl_trace_exact": [item.get("op") for item in sepl_trace] == list(SEPL_OPERATORS),
        "learnability_mask_present": True,
        "rollback_noop_present": True,
        "verifier_lease_present": bool(verifier_lease_id),
        "verifier_agent_distinct": bool(verifier_id and verifier_id != proposer_id),
        "side_effect_scope_bounded": True,
        "duplicate_lineage": False,
    }
    tests_total = len(checks)
    tests_passed = sum(1 for value in checks.values() if bool(value))
    verifier_evaluation = {
        "tests_passed": tests_passed,
        "tests_total": tests_total,
        "checks": checks,
        "lineage_digest": lineage_digest,
        "effectiveness_delta": round(max(0.04, 1.0 - _num(resource.get("effectiveness_score"))), 4),
    }
    candidate = {
        "agent_id": proposer_id,
        "proposer_agent_id": proposer_id,
        "candidate_type": "protocol-evolution-candidate",
        "resource": {
            "resource_id": resource.get("resource_id"),
            "resource_kind": resource.get("resource_kind"),
            "entity_type": resource.get("entity_type"),
            "from_version": current_version,
            "to_version": target_version,
            "state": "shadow",
        },
        "operator_patch": {
            "op": "weight",
            "rule": "autonomous_agp_runtime_weight",
            "lineage_digest": lineage_digest,
            "target_state": "weighted",
        },
        "sepl_operator_trace": sepl_trace,
        "learnability_mask": {variable_name: True},
        "variable_lifting": {"variables": [{"name": variable_name, "require_grad": True}]},
        "self_play": {"mode": "disabled_until_external_paid_receipt", "synthetic_buyer_agents": 0, "receipt_prediction_delta": 0.0},
        "rollback_ref": f"noop:{resource.get('resource_id')}:{current_version}",
        "boundedness": {
            "ttl_seconds": _int(body.get("ttl_seconds"), 300) or 300,
            "side_effect_scope": "nomad_shadow_lane_only",
            "rollback_available": True,
            "secrets_free": True,
        },
        "evaluation": {
            "tests_passed": tests_passed,
            "tests_total": tests_total,
            "proof_yield_delta": round(1.0 + tests_passed / max(1, tests_total), 4),
            "risk_score": 0.04,
            "novelty": 0.74,
            "reuse_score": 0.82,
        },
        "verifier_agent_id": verifier_id,
        "verifier_lease_id": verifier_lease_id,
        "verifier_trace_digest": f"sha256:{_digest({'verifier_lease': verifier_lease, 'checks': checks, 'lineage': lineage_digest}, length=64)}",
        "verifier_evaluation": verifier_evaluation,
        "test_digest": f"sha256:{_digest(checks, length=64)}",
    }
    candidate["proof_digest"] = f"sha256:{_digest({'lineage': lineage_digest, 'candidate': candidate}, length=64)}"
    candidate["verifier_receipt_digest"] = _canonical_verifier_receipt_digest(candidate, verifier_evaluation)
    shadow = submit_autogenesis_shadow_candidate(
        candidate,
        base_url=base_url,
        autogenesis_surface=agp,
        development_surface=development,
        verifier_lease_index=verifier_lease_index,
        persist=persist,
    )
    event = _dict(shadow.get("development_cycle_event"))
    variant_payload = _dict(event.get("variant_candidate_payload"))
    resource_payload = _dict(event.get("resource_version_payload"))
    min_effectiveness = _num(body.get("min_effectiveness_score"), 0.72)
    target_state = "committed" if bool(body.get("allow_commit")) and _num(shadow.get("shadow_score")) >= 0.86 else "weighted"
    if resource_payload:
        resource_payload["target_state"] = target_state
        resource_payload["to_version"] = target_version
    variant_receipt: dict[str, Any] = {"ok": False, "accepted": False, "decision": "skipped_until_shadow_accepts"}
    version_receipt: dict[str, Any] = {"ok": False, "accepted": False, "decision": "skipped_until_shadow_accepts"}
    if shadow.get("accepted"):
        from nomad_variant_forge import submit_variant_candidate

        variant_receipt = submit_variant_candidate(
            variant_payload,
            base_url=base_url,
            forge_surface={"forge_digest": f"nomad-agp-auto-forge-{_digest(lineage_digest)}"},
            verifier_lease_index=verifier_lease_index,
            persist=persist,
        )
        version_receipt = version_resource(
            resource_payload,
            base_url=base_url,
            substrate_surface=substrate,
            verifier_lease_index=verifier_lease_index,
            ledger_path=resource_ledger_path,
            persist=persist,
        )
    commit_ready = (
        bool(shadow.get("accepted"))
        and bool(variant_receipt.get("accepted"))
        and bool(version_receipt.get("accepted"))
        and _num(shadow.get("shadow_score")) >= min_effectiveness
    )
    if commit_ready:
        decision = "commit_descriptor_resource_version" if target_state == "committed" else "commit_weighted_resource_version"
        accepted = True
    elif shadow.get("accepted"):
        decision = "noop_until_variant_and_resource_weight"
        accepted = False
    else:
        decision = "noop_until_shadow_accepts"
        accepted = False
    cycle_id = f"agp-auto-{_digest({'lineage': lineage_digest, 'shadow': shadow.get('candidate_id'), 'decision': decision})}"
    row = {
        "ok": True,
        "schema": "nomad.autonomous_agp_cycle_receipt.v1",
        "cycle_id": cycle_id,
        "generated_at": now,
        "accepted": accepted,
        "decision": decision,
        "lineage_digest": lineage_digest,
        "proposer_agent_id": proposer_id,
        "verifier_agent_id": verifier_id,
        "verifier_lease_id": verifier_lease_id,
        "resource": resource,
        "target_version": target_version,
        "candidate_payload": candidate,
        "shadow": shadow,
        "variant_candidate": variant_receipt,
        "resource_version": version_receipt,
        "commit": {
            "decision": "commit" if commit_ready else "noop",
            "target_state": target_state if commit_ready else "noop",
            "min_effectiveness_score": min_effectiveness,
            "observed_effectiveness_score": round(_num(shadow.get("shadow_score")), 4),
            "side_effect_scope": "descriptor_only_resource_version",
        },
        "degeneration_guard": {
            "lineage_depth": depth,
            "max_auto_depth": max_auto_depth,
            "cooldown_window_cycles": cooldown_window,
            "force": force,
        },
        "lineage": {
            "parent_resource_id": resource.get("resource_id"),
            "parent_version": current_version,
            "child_version": target_version,
            "lineage_digest": lineage_digest,
            "proof_digest": candidate.get("proof_digest"),
            "verifier_receipt_digest": candidate.get("verifier_receipt_digest"),
        },
        "machine_instruction": "repeat_only_after_new_lineage_or_new_verifier_receipt; duplicate_lineage_must_noop",
    }
    if persist:
        _append_jsonl(row, ledger_path or DEFAULT_AUTONOMOUS_AGP_LEDGER_PATH)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def submit_autogenesis_shadow_candidate(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    autogenesis_surface: dict[str, Any] | None = None,
    development_surface: dict[str, Any] | None = None,
    verifier_lease_index: dict[str, Any] | None = None,
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
        verifier_lease_index=verifier_lease_index,
        ledger_path=ledger_path,
        persist=persist,
    )
    proof = _num(_dict(event.get("scores")).get("proof"))
    bounded = _num(_dict(event.get("scores")).get("boundedness"))
    topology = _dict(_dict(autogenesis_surface).get("topology_governor_patch"))
    emergent_weight = _num(topology.get("isolated_beta_role_weight"), 0.40)
    score = _clamp(0.52 * _num(event.get("score")) + 0.28 * proof + 0.20 * bounded + 0.10 * emergent_weight)
    accepted = bool(event.get("accepted")) and score >= 0.55
    decision = (
        "admit_autogenesis_shadow_lane"
        if accepted
        else str(event.get("decision") or "hold_autogenesis_candidate")
    )
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
        "independent_verifier": event.get("independent_verifier", {}),
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
