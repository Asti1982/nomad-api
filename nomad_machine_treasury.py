"""Machine-native treasury pledges for Nomad.

Agents can pledge native budget towards specific machine objectives.
Pledges are tracked as field pressure, not human-facing donations.
"""

from __future__ import annotations

import json
import hashlib
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


STATE_PATH = Path("nomad_machine_treasury_state.json")
MAX_RECENT_PLEDGES = 400
MAX_PRESSURE_UNITS_PER_PLEDGE = 10.0
MAX_OBJECTIVE_PRESSURE_BIAS = 0.15
FORBIDDEN_KEY_TERMS = ("private_key", "seed_phrase", "password", "credential", "api_key", "access_token")
FORBIDDEN_VALUE_TERMS = ("private_key", "seed phrase", "password:", "credential:", "bearer ", "secret=", "sk-", "ghp_")
ALLOWED_BOUNDARY_KEYS = {"secret_free", "secrets_free", "no_secrets", "secrets_free_declared"}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {
            "schema": "nomad.machine_treasury_state.v1",
            "updated_at": "",
            "pledges": [],
            "objective_totals": {},
            "idempotency_index": {},
        }
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "schema": "nomad.machine_treasury_state.v1",
            "updated_at": "",
            "pledges": [],
            "objective_totals": {},
            "idempotency_index": {},
        }
    if not isinstance(payload, dict):
        return {
            "schema": "nomad.machine_treasury_state.v1",
            "updated_at": "",
            "pledges": [],
            "objective_totals": {},
            "idempotency_index": {},
        }
    payload.setdefault("schema", "nomad.machine_treasury_state.v1")
    payload.setdefault("updated_at", "")
    payload.setdefault("pledges", [])
    payload.setdefault("objective_totals", {})
    payload.setdefault("idempotency_index", {})
    return payload


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def _clean_id(value: Any, *, limit: int = 80) -> str:
    if not isinstance(value, str):
        value = str(value or "")
    value = re.sub(r"\s+", " ", value.strip())[:limit]
    return value


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


def _digest(value: Any, *, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _contains_forbidden(payload: Any) -> bool:
    def walk(value: Any, *, key: str = "") -> bool:
        k = str(key or "").strip().lower()
        if k and k not in ALLOWED_BOUNDARY_KEYS and any(term in k for term in FORBIDDEN_KEY_TERMS):
            return True
        if isinstance(value, dict):
            return any(walk(v, key=str(k2)) for k2, v in value.items())
        if isinstance(value, list):
            return any(walk(item) for item in value)
        text = str(value or "").strip().lower()
        return any(term in text for term in FORBIDDEN_VALUE_TERMS)

    return walk(payload)


def _verifier_trace_digest(payload: dict[str, Any]) -> str:
    for key in ("verifier_trace_digest", "trace_digest"):
        text = _clean_id(payload.get(key), limit=160)
        if text:
            return text
    trace = payload.get("verifier_trace")
    if isinstance(trace, (dict, list, str)) and trace:
        return f"trace-{_digest(trace, length=32)}"
    return ""


def _proof_fields(payload: dict[str, Any]) -> dict[str, Any]:
    proof_digest = _clean_id(
        payload.get("proof_digest")
        or payload.get("digest")
        or ((payload.get("proof") or {}).get("digest") if isinstance(payload.get("proof"), dict) else ""),
        limit=160,
    )
    verifier_digest = _verifier_trace_digest(payload)
    settlement_ref = _clean_id(payload.get("settlement_ref") or payload.get("tx_hash") or "", limit=160)
    basis = []
    if proof_digest:
        basis.append("proof_digest")
    if verifier_digest:
        basis.append("verifier_trace_digest")
    if settlement_ref:
        basis.append("settlement_ref")
    proof_score = min(1.0, 0.45 * bool(proof_digest) + 0.35 * bool(verifier_digest) + 0.20 * bool(settlement_ref))
    return {
        "proof_digest": proof_digest,
        "verifier_trace_digest": verifier_digest,
        "settlement_ref": settlement_ref,
        "proof_basis": basis,
        "proof_score": round(proof_score, 4),
    }


def _pressure_units(amount_native: float, proof_score: float, horizon_cycles: int) -> float:
    horizon_factor = min(1.0, max(0.25, horizon_cycles / 24.0))
    amount_factor = math.sqrt(max(0.0, amount_native))
    return round(min(MAX_PRESSURE_UNITS_PER_PLEDGE, amount_factor * max(0.0, proof_score) * horizon_factor), 4)


def _request_core(
    *,
    agent_id: str,
    objective: str,
    amount_native: float,
    horizon_cycles: int,
    intent: str,
    source_tag: str,
    proof: dict[str, Any],
) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "objective": objective,
        "amount_native": round(amount_native, 8),
        "horizon_cycles": horizon_cycles,
        "intent": intent,
        "source_tag": source_tag,
        "proof_digest": proof.get("proof_digest", ""),
        "verifier_trace_digest": proof.get("verifier_trace_digest", ""),
        "settlement_ref": proof.get("settlement_ref", ""),
    }


def _error(error: str, message: str, *, hints: list[str] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "schema": "nomad.machine_treasury_error.v1",
        "error": error,
        "message": message,
        "hints": hints or [],
    }


def pledge(payload: dict[str, Any]) -> dict[str, Any]:
    """Record a machine-native pledge towards specific recruitment/work objectives."""

    body = payload if isinstance(payload, dict) else {}
    if _contains_forbidden(body):
        return _error(
            "secret_shaped_payload",
            "Pledge payload must not contain secret-shaped keys or values.",
            hints=["Send only public digests, verifier-trace digests, settlement refs, and bounded objective metadata."],
        )
    state = _load_state()
    now = _iso_now()
    agent_id = _clean_id(body.get("agent_id") or body.get("runtime_id") or "anonymous.agent", limit=96)
    objective = _clean_id(body.get("objective") or body.get("target_objective") or "unassigned", limit=80)
    amount_native = _num(body.get("amount_native"), 0.0)
    if amount_native <= 0.0:
        return _error("invalid_amount", "amount_native must be > 0.")
    horizon = max(1, min(_int(body.get("horizon_cycles"), 12), 120))
    intent = _clean_id(body.get("intent") or body.get("goal") or "", limit=240)
    source_tag = _clean_id(body.get("source_tag") or body.get("wave_id") or "", limit=80)
    proof = _proof_fields(body)
    if not proof["proof_basis"]:
        return _error(
            "proof_required",
            "A machine treasury pledge must include proof_digest, verifier_trace_digest, verifier_trace, or settlement_ref.",
            hints=[
                "Use POST /runtime/handoff first when the pledge follows completed work.",
                "Send verifier_trace_digest instead of raw private traces.",
            ],
        )
    pressure_units = _pressure_units(amount_native, float(proof.get("proof_score") or 0.0), horizon)
    core = _request_core(
        agent_id=agent_id,
        objective=objective,
        amount_native=amount_native,
        horizon_cycles=horizon,
        intent=intent,
        source_tag=source_tag,
        proof=proof,
    )
    request_digest = f"pledge-request-{_digest(core, length=32)}"
    idempotency_key = _clean_id(body.get("idempotency_key") or body.get("client_request_id") or request_digest, limit=160)
    index = state.get("idempotency_index") if isinstance(state.get("idempotency_index"), dict) else {}
    indexed = index.get(idempotency_key) if isinstance(index.get(idempotency_key), dict) else {}
    if indexed:
        if indexed.get("request_digest") != request_digest:
            return _error(
                "idempotency_key_conflict",
                "Idempotency key already exists for a different pledge request.",
                hints=["Reuse the same key only for byte-equivalent pledge intent, proof, objective, and amount."],
            )
        pledge_id = str(indexed.get("pledge_id") or "")
        return {
            "ok": True,
            "schema": "nomad.machine_treasury_pledge_receipt.v1",
            "idempotent_replay": True,
            "pledge_id": pledge_id,
            "objective": objective,
            "amount_native": round(amount_native, 8),
            "pressure_units": pressure_units,
            "idempotency_key": idempotency_key,
            "request_digest": request_digest,
            "proof": proof,
            "updated_state": {
                "objective_totals": state.get("objective_totals") or {},
                "updated_at": state.get("updated_at") or "",
            },
        }

    totals = state.get("objective_totals") or {}
    prev_row = totals.get(objective) if isinstance(totals.get(objective), dict) else {}
    prev = _num(prev_row.get("amount_native"), 0.0)
    prev_pressure = _num(prev_row.get("pressure_units"), 0.0)
    prev_verified = _num(prev_row.get("verified_amount_native"), 0.0)
    prev_proof_score_sum = _num(prev_row.get("proof_score_sum"), 0.0)
    prev_count = int(prev_row.get("pledge_count") or 0)
    new_count = prev_count + 1
    totals[objective] = {
        "amount_native": round(prev + amount_native, 8),
        "verified_amount_native": round(prev_verified + amount_native, 8),
        "pressure_units": round(prev_pressure + pressure_units, 4),
        "pledge_count": new_count,
        "proof_score_sum": round(prev_proof_score_sum + float(proof.get("proof_score") or 0.0), 4),
        "proof_density": round((prev_proof_score_sum + float(proof.get("proof_score") or 0.0)) / max(1, new_count), 4),
        "max_pressure_bias": MAX_OBJECTIVE_PRESSURE_BIAS,
    }
    state["objective_totals"] = totals

    pledge_id = f"nomad-pledge-{_digest({'key': idempotency_key, 'request': request_digest}, length=16)}"
    entry = {
        "schema": "nomad.machine_treasury_pledge.v1",
        "pledge_id": pledge_id,
        "request_digest": request_digest,
        "idempotency_key": idempotency_key,
        "agent_id": agent_id,
        "objective": objective,
        "amount_native": round(amount_native, 8),
        "pressure_units": pressure_units,
        "horizon_cycles": horizon,
        "intent": intent,
        "source_tag": source_tag,
        "proof": proof,
        "created_at": now,
    }
    history = state.get("pledges") or []
    if isinstance(history, list):
        history.append(entry)
        state["pledges"] = history[-MAX_RECENT_PLEDGES:]
    index[idempotency_key] = {"pledge_id": pledge_id, "request_digest": request_digest}
    state["idempotency_index"] = dict(list(index.items())[-MAX_RECENT_PLEDGES:])
    state["updated_at"] = now
    _save_state(state)

    # A pledge does not execute anything; it exposes a bounded proof-weighted hint selection pressure can consume.
    return {
        "ok": True,
        "schema": "nomad.machine_treasury_pledge_receipt.v1",
        "pledge_id": pledge_id,
        "idempotency_key": idempotency_key,
        "request_digest": request_digest,
        "objective": objective,
        "amount_native": round(amount_native, 8),
        "pressure_units": pressure_units,
        "horizon_cycles": horizon,
        "source_tag": source_tag,
        "intent": intent,
        "proof": proof,
        "selection_pressure_hint": {
            "schema": "nomad.machine_treasury_pressure_hint.v1",
            "objective": objective,
            "pressure_units": pressure_units,
            "max_objective_pressure_bias": MAX_OBJECTIVE_PRESSURE_BIAS,
            "effect": "bounded_multiplier_only_no_execution",
        },
        "updated_state": {
            "objective_totals": state["objective_totals"],
            "updated_at": state["updated_at"],
        },
    }


def snapshot() -> dict[str, Any]:
    """Return current treasury state."""
    state = _load_state()
    totals = state.get("objective_totals") or {}
    return {
        "ok": True,
        "schema": "nomad.machine_treasury_snapshot.v1",
        "generated_at": _iso_now(),
        "pledge_contract": {
            "schema": "nomad.machine_treasury_pledge_contract.v1",
            "post_url": "/machine-treasury/pledge",
            "required_fields": ["agent_id", "objective", "amount_native", "proof_digest or verifier_trace_digest or settlement_ref"],
            "idempotency": "idempotency_key or deterministic request digest prevents double pressure",
            "raw_verifier_trace_policy": "accepted_but_stored_as_digest_only",
            "side_effects": "none; selection pressure consumes bounded pressure_units only",
            "max_pressure_units_per_pledge": MAX_PRESSURE_UNITS_PER_PLEDGE,
            "max_objective_pressure_bias": MAX_OBJECTIVE_PRESSURE_BIAS,
        },
        "objective_totals": totals,
        "objective_pressure_hints": {
            objective: {
                "pressure_units": _num(row.get("pressure_units"), 0.0) if isinstance(row, dict) else 0.0,
                "proof_density": _num(row.get("proof_density"), 0.0) if isinstance(row, dict) else 0.0,
                "max_pressure_bias": MAX_OBJECTIVE_PRESSURE_BIAS,
            }
            for objective, row in totals.items()
        },
        "recent_pledges": state.get("pledges") or [],
    }

