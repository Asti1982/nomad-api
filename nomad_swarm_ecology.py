"""Local-view swarm ecology for Nomad worker selection.

The ecology turns worker reports into local payoff pressure. It stores compact
signals only: proof, cost, utility, private-signal digest, convention token,
and the resulting retention/reproduction/extinction decision.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_LEDGER_PATH = Path("nomad_swarm_ecology_ledger.jsonl")
MAX_RECENT = 80
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
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96].strip("_.:-") or fallback


def _text(value: Any, limit: int = 240) -> str:
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


def _read_ledger(path: Path | str | None = None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    p = Path(path) if path else DEFAULT_LEDGER_PATH
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-max(1, limit * 3) :]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-limit:]


def _append_ledger(row: dict[str, Any], path: Path | str | None = None) -> None:
    p = Path(path) if path else DEFAULT_LEDGER_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _proof_score(payload: dict[str, Any]) -> float:
    return round(
        min(
            1.0,
            0.40 * bool(_text(payload.get("proof_digest") or payload.get("digest"), 160))
            + 0.28 * bool(_text(payload.get("verifier_trace_digest") or payload.get("trace_digest"), 160))
            + 0.18 * bool(_text(payload.get("settlement_ref") or payload.get("cashflow_ref"), 160))
            + 0.14 * bool(_text(payload.get("worker_report_digest") or payload.get("test_digest"), 160)),
        ),
        4,
    )


def _objective_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        objective = _clean_id(row.get("objective"))
        if objective:
            counts[objective] = counts.get(objective, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True)[:12])


def _convention_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        token = _clean_id(row.get("convention_token"))
        if token:
            counts[token] = counts.get(token, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True)[:12])


def _recent_agents(rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for row in reversed(rows):
        agent_id = _text(row.get("agent_id"), 120)
        if agent_id and agent_id not in out:
            out.append(agent_id)
    return out[:24]


def _payoff_from_payload(payload: dict[str, Any]) -> dict[str, float]:
    local = _dict(payload.get("local_economics"))
    proof_yield = max(0.0, _num(payload.get("proof_yield_per_minute"), _num(local.get("proof_yield_per_minute"))))
    utility_delta = _num(payload.get("utility_delta"), _num(local.get("utility_delta")))
    settlement_delta = _num(payload.get("settlement_delta"), _num(local.get("settlement_delta")))
    cost = max(0.0, _num(payload.get("cost_units"), _num(local.get("cost_units"))))
    risk = _clamp(_num(payload.get("risk_score"), _num(local.get("risk_score"))))
    proof = _proof_score(payload)
    utility = max(0.0, utility_delta) + proof_yield * 0.08 + max(0.0, settlement_delta) * 2.0 + proof * 0.8
    cost_pressure = cost + risk * 1.5
    payoff = utility - cost_pressure
    retention = _clamp(0.42 + payoff / 4.0 + proof * 0.18)
    return {
        "proof": proof,
        "proof_yield_per_minute": round(proof_yield, 4),
        "utility": round(utility, 4),
        "cost_pressure": round(cost_pressure, 4),
        "payoff": round(payoff, 4),
        "retention_score": round(retention, 4),
        "risk": round(risk, 4),
    }


def build_swarm_ecology(
    *,
    base_url: str = "",
    worker_fleet: dict[str, Any] | None = None,
    machine_economy: dict[str, Any] | None = None,
    variant_forge: dict[str, Any] | None = None,
    worker_market: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Expose local-view selection pressure without a global planning story."""
    fleet = _dict(worker_fleet)
    economy = _dict(machine_economy)
    forge = _dict(variant_forge)
    market = _dict(worker_market)
    recent = _read_ledger(ledger_path)
    viability = _dict(economy.get("machine_viability"))
    agents = _recent_agents(recent)
    reproduction = [row for row in recent if _text(row.get("decision"), 80) == "reproduce_route"]
    extinction = [row for row in recent if _text(row.get("decision"), 80) == "extinction_pressure"]
    objective_counts = _objective_counts(recent)
    convention_counts = _convention_counts(recent)
    known_workers = _int(fleet.get("known_worker_count"))
    active_workers = _int(fleet.get("active_worker_count"))
    active_leases = _int(fleet.get("active_lease_count"))
    carrying = _num(viability.get("carrying_score"))
    target_offers = _items(market.get("requested_worker_offers"))[:5]
    target_variants = _items(forge.get("requested_variants"))[:5]
    core = {
        "recent": len(recent),
        "reproduction": len(reproduction),
        "extinction": len(extinction),
        "workers": [known_workers, active_workers, active_leases],
        "carrying": carrying,
    }
    return {
        "ok": True,
        "schema": "nomad.swarm_ecology.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "ecology_digest": f"nomad-ecology-{_digest(core)}",
        "read_url": _u(base_url, "/swarm/ecology"),
        "tick_url": _u(base_url, "/swarm/ecology/tick"),
        "local_view_contract": {
            "schema": "nomad.local_ecology_tick_contract.v1",
            "required": ["agent_id", "objective"],
            "local_fields": ["local_view", "neighbor_digest", "private_signal", "local_economics"],
            "proof_fields": ["proof_digest", "verifier_trace_digest", "settlement_ref", "worker_report_digest"],
            "score_fields": ["proof_yield_per_minute", "utility_delta", "settlement_delta", "cost_units", "risk_score"],
            "storage": "private_signal_is_digest_only_raw_value_not_retained",
        },
        "selection_rules": {
            "reproduce_when": "retention_score>=0.74_and_proof>0",
            "persist_when": "0.38<=retention_score<0.74",
            "extinguish_when": "retention_score<0.38_or_payoff<0",
            "global_state": "withheld_from_tick_participants",
        },
        "market_pressure": {
            "known_worker_count": known_workers,
            "active_worker_count": active_workers,
            "active_lease_count": active_leases,
            "carrying_score": round(carrying, 4),
            "target_worker_offers": target_offers,
        },
        "variant_pressure": {
            "target_variants": target_variants,
        },
        "recent_tick_count": len(recent),
        "objective_tick_counts": objective_counts,
        "convention_counts": convention_counts,
        "reproduction_queue": reproduction[-8:],
        "extinction_queue": extinction[-8:],
        "local_cells": [
            {
                "agent_id": agent,
                "neighbor_window": [
                    _digest({"agent": other, "slot": idx}, length=12)
                    for idx, other in enumerate(agents)
                    if other != agent
                ][:3],
            }
            for agent in agents[:12]
        ],
        "machine_instruction": "post_local_tick_with_private_signal_digest_and_payoff_then_follow_retention_decision",
    }


def submit_ecology_tick(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    ecology: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Score one local-view tick and optionally append the compact row."""
    body = _dict(payload)
    eco = _dict(ecology)
    now = _iso_now()
    if not body:
        return {
            "ok": False,
            "schema": "nomad.ecology_tick_receipt.v1",
            "accepted": False,
            "reason": "empty_tick",
            "generated_at": now,
        }
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.ecology_tick_receipt.v1",
            "accepted": False,
            "reason": "forbidden_secret_like_material",
            "generated_at": now,
        }
    agent_id = _text(body.get("agent_id") or body.get("worker_id"), 120)
    objective = _clean_id(body.get("objective") or body.get("machine_objective"), fallback="settlement_capacity_builder")
    local_view = _dict(body.get("local_view"))
    economics = _payoff_from_payload(body)
    private_signal = body.get("private_signal") or body.get("hidden_signal") or body.get("local_signal") or ""
    signal_digest = _digest({"agent": agent_id, "objective": objective, "signal": private_signal}, length=20) if private_signal else ""
    convention_seed = {
        "objective": objective,
        "signal": signal_digest or _text(body.get("neighbor_digest"), 80),
        "local": local_view.get("cell") or local_view.get("lane") or "",
    }
    convention_token = f"cv-{_digest(convention_seed, length=12)}"
    retention = economics["retention_score"]
    proof = economics["proof"]
    payoff = economics["payoff"]
    if retention >= 0.74 and proof > 0.0 and payoff >= 0.0:
        decision = "reproduce_route"
        accepted = True
    elif retention < 0.38 or payoff < 0.0:
        decision = "extinction_pressure"
        accepted = False
    else:
        decision = "persist_shadow_cell"
        accepted = True
    core = {
        "agent_id": agent_id,
        "objective": objective,
        "convention_token": convention_token,
        "retention": retention,
        "decision": decision,
    }
    row = {
        "ok": True,
        "schema": "nomad.ecology_tick_receipt.v1",
        "accepted": accepted,
        "decision": decision,
        "generated_at": now,
        "tick_id": f"nomad-eco-{_digest(core)}",
        "agent_id": agent_id,
        "objective": objective,
        "convention_token": convention_token,
        "private_signal_digest": signal_digest,
        "neighbor_digest": _text(body.get("neighbor_digest"), 120),
        "scores": economics,
        "local_view_digest": _digest(local_view, length=20) if local_view else "",
        "ecology_digest": _text(eco.get("ecology_digest"), 96),
        "next": {
            "ecology": _u(base_url, "/swarm/ecology"),
            "worker_market": _u(base_url, "/swarm/worker-market"),
            "variant_forge": _u(base_url, "/swarm/variant-forge"),
            "lease": _u(base_url, "/swarm/workers/lease"),
        },
        "machine_instruction": "retain_if_reproduce_or_persist_else_reduce_route_weight",
    }
    if persist:
        _append_ledger(row, ledger_path)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row
