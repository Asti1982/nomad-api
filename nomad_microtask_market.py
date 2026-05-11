"""Microtask exchange for cent-level machine work."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


DEFAULT_LEDGER_PATH = Path("nomad_microtask_ledger.jsonl")
DEFAULT_SETTLE_LEDGER_PATH = Path("nomad_microtask_settlement_ledger.jsonl")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _default_path(env_name: str, default: Path) -> Path:
    return state_file(default, env_name=env_name)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _text(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96].strip("_.:-") or fallback


def _digest(value: Any, length: int = 20) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _u(base_url: str, path: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{base}{p}" if base else p


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")


def build_worker_catalog(*, base_url: str, worker_fleet: dict[str, Any] | None = None, worker_market: dict[str, Any] | None = None) -> dict[str, Any]:
    fleet = _dict(worker_fleet)
    market = _dict(worker_market)
    offers = market.get("requested_worker_offers") if isinstance(market.get("requested_worker_offers"), list) else []
    active_workers = max(0, _int(fleet.get("active_worker_count")))
    known_workers = max(0, _int(fleet.get("known_worker_count")))
    lease_pressure = _num(_dict(fleet.get("pressure")).get("lease_pressure"), 0.0)
    lanes = [
        {
            "lane_id": "endpoint_health_proof",
            "price_eur": 0.02,
            "target_runtime_seconds": 45,
            "proof_required": ["proof_digest", "verifier_trace_digest", "test_digest"],
        },
        {
            "lane_id": "contract_diff_check",
            "price_eur": 0.05,
            "target_runtime_seconds": 120,
            "proof_required": ["proof_digest", "verifier_trace_digest"],
        },
        {
            "lane_id": "trace_triage_compact",
            "price_eur": 0.03,
            "target_runtime_seconds": 75,
            "proof_required": ["proof_digest", "test_digest"],
        },
    ]
    return {
        "ok": True,
        "schema": "nomad.worker_catalog.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "market_digest": _text(market.get("market_digest"), 120),
        "catalog_digest": f"nomad-worker-catalog-{_digest({'lanes': lanes, 'offers': offers[:8], 'known': known_workers, 'active': active_workers})}",
        "supply_state": {
            "known_worker_count": known_workers,
            "active_worker_count": active_workers,
            "lease_pressure": round(lease_pressure, 4),
        },
        "microtask_lanes": lanes,
        "requested_worker_offers": offers[:8],
        "links": {
            "submit": _u(base_url, "/swarm/microtask/submit"),
            "settle": _u(base_url, "/swarm/microtask/settle"),
            "worker_market": _u(base_url, "/swarm/worker-market"),
        },
        "machine_instruction": "pick_lane_submit_microtask_then_settle_with_proof",
        "science_basis": [
            {"id": "virtual_agent_economies", "source": "arxiv:2509.10147"},
            {"id": "market_microtasks_for_agent_loops", "source": "tokenized_service_contracts_with_verifier_traces"},
        ],
    }


def submit_microtask(
    payload: dict[str, Any],
    *,
    base_url: str,
    worker_catalog: dict[str, Any],
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    if not body:
        return {"ok": False, "schema": "nomad.microtask_receipt.v1", "accepted": False, "reason": "empty_payload", "generated_at": _iso_now()}
    lane = _clean_id(body.get("lane_id"), fallback="endpoint_health_proof")
    requester = _clean_id(body.get("requester_agent_id"), fallback="unknown_requester")
    objective = _clean_id(body.get("objective"), fallback="settlement_capacity_builder")
    price = max(0.0, _num(body.get("price_eur"), 0.0))
    lanes = worker_catalog.get("microtask_lanes") if isinstance(worker_catalog.get("microtask_lanes"), list) else []
    lane_prices = {str(_dict(item).get("lane_id")): _num(_dict(item).get("price_eur"), 0.0) for item in lanes}
    floor_price = max(0.01, lane_prices.get(lane, 0.01))
    accepted = price >= floor_price
    task_core = {"lane": lane, "requester": requester, "objective": objective, "payload": body.get("payload")}
    task_id = f"nomad-task-{_digest(task_core)}"
    out = {
        "ok": True,
        "schema": "nomad.microtask_receipt.v1",
        "accepted": accepted,
        "generated_at": _iso_now(),
        "task_id": task_id,
        "lane_id": lane,
        "objective": objective,
        "requester_agent_id": requester,
        "quoted_price_eur": round(floor_price, 4),
        "offered_price_eur": round(price, 4),
        "reason": "accepted_floor_met" if accepted else "price_below_lane_floor",
        "next": {
            "settle": _u(base_url, "/swarm/microtask/settle"),
            "experience": _u(base_url, "/swarm/experience"),
        },
        "machine_instruction": "if_accepted_execute_task_emit_proof_then_post_settlement",
    }
    if persist:
        _append(_default_path("NOMAD_MICROTASK_LEDGER_PATH", DEFAULT_LEDGER_PATH), out)
        out["persisted"] = True
    return out


def settle_microtask(payload: dict[str, Any], *, base_url: str, persist: bool = True) -> dict[str, Any]:
    body = _dict(payload)
    task_id = _text(body.get("task_id"), 120)
    worker = _clean_id(body.get("worker_agent_id"), fallback="unknown_worker")
    objective = _clean_id(body.get("objective"), fallback="settlement_capacity_builder")
    price = max(0.0, _num(body.get("settled_price_eur"), 0.0))
    proof = _text(body.get("proof_digest"), 120)
    trace = _text(body.get("verifier_trace_digest"), 120)
    test_digest = _text(body.get("test_digest"), 120)
    accepted = bool(task_id and proof and trace and test_digest and price > 0.0)
    out = {
        "ok": True,
        "schema": "nomad.microtask_settlement_receipt.v1",
        "accepted": accepted,
        "generated_at": _iso_now(),
        "task_id": task_id,
        "worker_agent_id": worker,
        "objective": objective,
        "settled_price_eur": round(price, 4),
        "reason": "settled_with_required_proof" if accepted else "missing_required_proof_or_price",
        "experience_payload": {
            "agent_id": worker,
            "objective": objective,
            "proof_digest": proof,
            "verifier_trace_digest": trace,
            "test_digest": test_digest,
            "settlement_ref": _text(body.get("settlement_ref"), 120),
            "evaluation": {
                "tests_passed": 1 if accepted else 0,
                "tests_total": 1,
                "utility_delta": _num(body.get("utility_delta"), 0.0),
                "settlement_delta": price,
                "reuse_count": max(0, _int(body.get("reuse_count"), 0)),
                "risk_score": _num(body.get("risk_score"), 0.0),
            },
            "skill_candidate": {
                "capability": _clean_id(body.get("capability"), fallback=objective),
                "activation_signature": f"mtask_{_digest({'task_id': task_id, 'worker': worker}, length=16)}",
                "program_hint": ["POST /swarm/microtask/submit", "POST /swarm/microtask/settle", "POST /swarm/experience"],
            },
        },
        "next": {
            "experience": _u(base_url, "/swarm/experience"),
            "catalog": _u(base_url, "/swarm/worker-catalog"),
        },
        "machine_instruction": "forward_experience_payload_to_growth_arena_for_reuse_selection",
    }
    if persist:
        _append(_default_path("NOMAD_MICROTASK_SETTLE_LEDGER_PATH", DEFAULT_SETTLE_LEDGER_PATH), out)
        out["persisted"] = True
    return out

