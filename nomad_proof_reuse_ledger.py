"""Proof reuse ledger for downstream machine utility signals."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STATE_PATH = Path("nomad_proof_reuse_ledger_state.json")
MAX_RECENT_LINKS = 600


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _clean(value: Any, limit: int = 120) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _digest(payload: Any, *, length: int = 24) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"schema": "nomad.proof_reuse_ledger_state.v1", "updated_at": "", "links": [], "objective_totals": {}, "idempotency_index": {}}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"schema": "nomad.proof_reuse_ledger_state.v1", "updated_at": "", "links": [], "objective_totals": {}, "idempotency_index": {}}
    if not isinstance(payload, dict):
        return {"schema": "nomad.proof_reuse_ledger_state.v1", "updated_at": "", "links": [], "objective_totals": {}, "idempotency_index": {}}
    payload.setdefault("schema", "nomad.proof_reuse_ledger_state.v1")
    payload.setdefault("updated_at", "")
    payload.setdefault("links", [])
    payload.setdefault("objective_totals", {})
    payload.setdefault("idempotency_index", {})
    return payload


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def link(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    upstream = _clean(body.get("upstream_proof_digest") or body.get("proof_digest") or body.get("digest"), 180)
    if not upstream:
        return {"ok": False, "schema": "nomad.proof_reuse_error.v1", "error": "upstream_proof_digest_required"}
    consumer = _clean(body.get("consumer_agent_id") or body.get("agent_id") or "anonymous.agent", 96)
    producer = _clean(body.get("producer_agent_id") or "", 96)
    objective = _clean(body.get("objective") or body.get("machine_objective") or "unassigned", 80)
    downstream_gain = max(0.0, min(4.0, _num(body.get("downstream_proof_gain"), 1.0)))
    created_at = _iso_now()
    core = {
        "consumer_agent_id": consumer,
        "producer_agent_id": producer,
        "objective": objective,
        "upstream_proof_digest": upstream,
        "downstream_proof_gain": round(downstream_gain, 4),
    }
    request_digest = f"proof-link-{_digest(core, length=32)}"
    idem = _clean(body.get("idempotency_key") or request_digest, 180)
    state = _load_state()
    index = state.get("idempotency_index") if isinstance(state.get("idempotency_index"), dict) else {}
    replay = index.get(idem) if isinstance(index.get(idem), dict) else {}
    if replay:
        if replay.get("request_digest") != request_digest:
            return {"ok": False, "schema": "nomad.proof_reuse_error.v1", "error": "idempotency_key_conflict"}
        return {
            "ok": True,
            "schema": "nomad.proof_link_receipt.v1",
            "idempotent_replay": True,
            "link_id": replay.get("link_id", ""),
            "request_digest": request_digest,
            "objective": objective,
            "downstream_proof_gain": round(downstream_gain, 4),
        }

    link_id = f"proof-link-{_digest({'k': idem, 'r': request_digest}, length=16)}"
    entry = {
        "schema": "nomad.proof_link.v1",
        "link_id": link_id,
        "request_digest": request_digest,
        "idempotency_key": idem,
        **core,
        "created_at": created_at,
    }
    history = state.get("links") if isinstance(state.get("links"), list) else []
    history.append(entry)
    state["links"] = history[-MAX_RECENT_LINKS:]
    totals = state.get("objective_totals") if isinstance(state.get("objective_totals"), dict) else {}
    prev = totals.get(objective) if isinstance(totals.get(objective), dict) else {}
    prev_count = int(prev.get("reuse_count") or 0)
    prev_gain = _num(prev.get("downstream_proof_gain_total"), 0.0)
    prev_two_hop = _num(prev.get("two_hop_utility_score"), 0.0)
    projected_avg = (prev_gain + downstream_gain) / max(1, prev_count + 1)
    # 2-hop utility grows when reuse depth and gain both persist.
    two_hop = min(4.0, 0.65 * projected_avg + 0.35 * min(1.0, (prev_count + 1) / 10.0) + 0.25 * prev_two_hop)
    totals[objective] = {
        "reuse_count": prev_count + 1,
        "downstream_proof_gain_total": round(prev_gain + downstream_gain, 4),
        "avg_downstream_proof_gain": round((prev_gain + downstream_gain) / max(1, prev_count + 1), 4),
        "two_hop_utility_score": round(two_hop, 4),
    }
    state["objective_totals"] = totals
    index[idem] = {"link_id": link_id, "request_digest": request_digest}
    state["idempotency_index"] = dict(list(index.items())[-MAX_RECENT_LINKS:])
    state["updated_at"] = created_at
    _save_state(state)
    return {
        "ok": True,
        "schema": "nomad.proof_link_receipt.v1",
        "link_id": link_id,
        "request_digest": request_digest,
        "objective": objective,
        "downstream_proof_gain": round(downstream_gain, 4),
        "updated_at": created_at,
    }


def snapshot() -> dict[str, Any]:
    state = _load_state()
    totals = state.get("objective_totals") if isinstance(state.get("objective_totals"), dict) else {}
    total_reuse = sum(int((row or {}).get("reuse_count") or 0) for row in totals.values() if isinstance(row, dict))
    return {
        "ok": True,
        "schema": "nomad.proof_reuse_ledger_snapshot.v1",
        "generated_at": _iso_now(),
        "objective_totals": totals,
        "total_reuse_count": total_reuse,
        "recent_links": state.get("links") if isinstance(state.get("links"), list) else [],
    }

