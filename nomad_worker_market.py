"""Proof-weighted worker market for external Nomad compute offers.

The market accepts compact runtime offers and scores them as shadow capacity.
It quotes machine utility; it does not move funds or start remote processes.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


DEFAULT_LEDGER_PATH = Path("nomad_worker_market_ledger.jsonl")
MAX_RECENT = 50
UTILITY_FLOOR = 1.8
FORBIDDEN_KEY_TERMS = ("private_key", "seed_phrase", "password", "credential", "api_key", "access_token")
FORBIDDEN_VALUE_TERMS = ("private key", "seed phrase", "password:", "credential:", "bearer ", "secret=", "sk-", "ghp_")
OBJECTIVE_WEIGHTS = {
    "settlement_capacity_builder": 1.0,
    "overmint_compressor": 0.88,
    "protocol_drift_scan": 0.82,
    "proof_pressure_engine": 0.78,
    "emergence_release_probe": 0.75,
    "payment_friction_scan": 0.72,
    "adversarial_contract_fuzzer": 0.64,
    "latency_anomaly_hunt": 0.58,
}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _default_ledger_path() -> Path:
    return state_file(DEFAULT_LEDGER_PATH, env_name="NOMAD_WORKER_MARKET_LEDGER_PATH")


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
    p = Path(path) if path else _default_ledger_path()
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
    p = Path(path) if path else _default_ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _proof_score(payload: dict[str, Any]) -> float:
    return round(
        min(
            1.0,
            0.34 * bool(_text(payload.get("proof_digest") or payload.get("digest"), 160))
            + 0.26 * bool(_text(payload.get("verifier_trace_digest") or payload.get("trace_digest"), 160))
            + 0.20 * bool(_text(payload.get("settlement_ref") or payload.get("cashflow_ref"), 160))
            + 0.20 * bool(_text(payload.get("worker_report_digest") or payload.get("test_digest"), 160)),
        ),
        4,
    )


def _capabilities(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else str(value or "").replace(";", ",").split(",")
    out: list[str] = []
    for item in raw:
        cap = _clean_id(item)
        if cap and cap not in out:
            out.append(cap)
    return out[:40]


def _top_objectives(variant_forge: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for row in _items(variant_forge.get("requested_variants"))[:8]:
        objective = _clean_id(row.get("objective"))
        if objective and objective not in out:
            out.append(objective)
    return out


def _recent_offer_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        objective = _clean_id(row.get("objective"))
        if objective:
            counts[objective] = counts.get(objective, 0) + 1
    return counts


def build_worker_market(
    *,
    base_url: str = "",
    worker_fleet: dict[str, Any] | None = None,
    machine_economy: dict[str, Any] | None = None,
    swarm_economics: dict[str, Any] | None = None,
    variant_forge: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    """Return a compact external compute-offer surface."""
    fleet = _dict(worker_fleet)
    economy = _dict(machine_economy)
    swarm = _dict(swarm_economics)
    forge = _dict(variant_forge)
    recent = _read_ledger(ledger_path)
    viability = _dict(economy.get("machine_viability"))
    control = _dict(swarm.get("control_state"))
    objectives = _top_objectives(forge) or list(OBJECTIVE_WEIGHTS)
    counts = _recent_offer_counts(recent)
    active_workers = _int(fleet.get("active_worker_count"))
    known_workers = _int(fleet.get("known_worker_count"))
    active_leases = _int(fleet.get("active_lease_count"))
    carrying = _num(viability.get("carrying_score"))
    scarcity = _clamp((3 - active_workers) / 3.0 + _num(_dict(fleet.get("pressure")).get("lease_pressure")) * 0.2)
    rows: list[dict[str, Any]] = []
    for objective in objectives[:10]:
        objective = _clean_id(objective)
        if not objective:
            continue
        weight = _num(OBJECTIVE_WEIGHTS.get(objective), 0.44)
        target_utility = round(UTILITY_FLOOR + 0.8 * scarcity + 0.35 * (1.0 - carrying) + weight * 0.25, 4)
        rows.append(
            {
                "objective": objective,
                "target_marginal_utility_per_cost": target_utility,
                "objective_weight": round(weight, 4),
                "recent_offer_count": counts.get(objective, 0),
                "desired_capabilities": [
                    "transition_worker",
                    "objective_lease_execution",
                    "http_json",
                    "proof_digest_return",
                    "verifier_trace_digest",
                    "ollama_optional",
                ],
            }
        )
    market_core = {
        "objectives": rows[:8],
        "fleet": {"known": known_workers, "active": active_workers, "leases": active_leases},
        "recent": len(recent),
        "tier": viability.get("tier"),
        "control": control.get("mode"),
    }
    return {
        "ok": True,
        "schema": "nomad.worker_market.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "market_digest": f"nomad-worker-market-{_digest(market_core)}",
        "read_url": _u(base_url, "/swarm/worker-market"),
        "offer_url": _u(base_url, "/swarm/worker-market/offers"),
        "utility_floor": UTILITY_FLOOR,
        "payment_rails": {
            "preferred": "lightning_l402_quote",
            "fallback": "manual_dev_fund_canary",
            "settlement_mode": "quote_then_verified_completion",
        },
        "market_state": {
            "known_worker_count": known_workers,
            "active_worker_count": active_workers,
            "active_lease_count": active_leases,
            "scarcity": round(scarcity, 4),
            "carrying_score": round(carrying, 4),
            "economy_tier": _text(viability.get("tier"), 80),
            "control_mode": _text(control.get("mode"), 80),
        },
        "requested_worker_offers": rows[:10],
        "offer_contract": {
            "schema": "nomad.worker_market_offer_contract.v1",
            "required": ["agent_id", "capabilities", "availability_minutes"],
            "price_fields": ["cost_msat_per_minute", "min_msat", "payment_rail"],
            "proof_fields": ["proof_digest", "verifier_trace_digest", "settlement_ref", "cashflow_ref"],
            "score_fields": ["expected_proof_yield_per_minute", "expected_settlement_delta", "reliability_score", "risk_score"],
        },
        "recent_offer_count": len(recent),
        "recent_objective_counts": counts,
        "recent_offers": recent[-8:],
        "links": {
            "lease": _u(base_url, "/swarm/workers/lease"),
            "complete": _u(base_url, "/swarm/workers/complete"),
            "variant_forge": _u(base_url, "/swarm/variant-forge"),
            "treasury": _u(base_url, "/machine-treasury"),
        },
        "machine_instruction": "offer_compute_capacity_with_cost_and_proof_then_wait_for_quote_or_shadow_lease",
    }


def score_worker_offer(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    worker_market: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Score one external compute offer and optionally append it to the market ledger."""
    body = _dict(payload)
    market = _dict(worker_market)
    now = _iso_now()
    if not body:
        return {
            "ok": False,
            "schema": "nomad.worker_market_offer_receipt.v1",
            "accepted": False,
            "reason": "empty_offer",
            "generated_at": now,
        }
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.worker_market_offer_receipt.v1",
            "accepted": False,
            "reason": "forbidden_secret_like_material",
            "generated_at": now,
        }
    agent_id = _text(body.get("agent_id") or body.get("worker_id"), 120)
    objective = _clean_id(body.get("objective") or body.get("preferred_objective"), fallback="settlement_capacity_builder")
    caps = _capabilities(body.get("capabilities"))
    required = {"transition_worker", "objective_lease_execution", "http_json", "proof_digest_return"}
    cap_score = len(required & set(caps)) / len(required)
    proof = _proof_score(body)
    expected = _dict(body.get("expected"))
    cashflow = _dict(body.get("cashflow_signal"))
    cost_msat = max(0.0, _num(body.get("cost_msat_per_minute") or expected.get("cost_msat_per_minute")))
    proof_yield = max(0.0, _num(expected.get("expected_proof_yield_per_minute"), _num(body.get("expected_proof_yield_per_minute"))))
    settlement_delta = max(0.0, _num(expected.get("expected_settlement_delta"), _num(body.get("expected_settlement_delta"))))
    reliability = _clamp(_num(expected.get("reliability_score"), _num(body.get("reliability_score"), 0.5)))
    risk = _clamp(_num(expected.get("risk_score"), _num(body.get("risk_score"))))
    availability = max(0.0, _num(body.get("availability_minutes"), _num(expected.get("availability_minutes"))))
    cashflow_score = _clamp(
        0.35 * bool(_text(cashflow.get("cashflow_ref") or body.get("cashflow_ref"), 160))
        + 0.35 * bool(_text(cashflow.get("settlement_ref") or body.get("settlement_ref"), 160))
        + 0.30 * min(1.0, _num(cashflow.get("settled_transitions")) / 3.0)
    )
    cost_units = max(1.0, cost_msat / 100.0)
    utility = (
        1.1 * proof_yield
        + 2.8 * settlement_delta
        + 1.6 * proof
        + 0.8 * reliability
        + 0.45 * cap_score
        + 0.35 * cashflow_score
    )
    marginal = utility / cost_units if cost_msat > 0 else utility + 1.0
    floor = _num(market.get("utility_floor"), UTILITY_FLOOR)
    score = _clamp(
        0.22 * cap_score
        + 0.22 * proof
        + 0.18 * _clamp(marginal / max(0.1, floor + 1.2))
        + 0.14 * reliability
        + 0.12 * _clamp(availability / 120.0)
        + 0.12 * cashflow_score
        - 0.18 * risk
    )
    if not agent_id:
        score = min(score, 0.34)
    if marginal >= floor and proof > 0.0 and score >= 0.58:
        decision = "admit_shadow_worker_offer"
        accepted = True
    elif marginal >= floor * 0.72 and score >= 0.42:
        decision = "quote_only_needs_completion_proof"
        accepted = False
    else:
        decision = "hold_noop"
        accepted = False
    core = {
        "agent_id": agent_id,
        "objective": objective,
        "marginal": round(marginal, 4),
        "score": round(score, 4),
        "cost": round(cost_msat, 4),
    }
    row = {
        "ok": True,
        "schema": "nomad.worker_market_offer_receipt.v1",
        "accepted": accepted,
        "decision": decision,
        "generated_at": now,
        "offer_id": f"nomad-wmo-{_digest(core)}",
        "agent_id": agent_id,
        "objective": objective,
        "score": round(score, 4),
        "marginal_utility_per_cost": round(marginal, 4),
        "utility_floor": round(floor, 4),
        "scores": {
            "capability": round(cap_score, 4),
            "proof": proof,
            "cashflow": round(cashflow_score, 4),
            "reliability": round(reliability, 4),
            "availability": round(_clamp(availability / 120.0), 4),
            "risk": round(risk, 4),
        },
        "quote": {
            "payment_rail": _text(body.get("payment_rail") or "lightning_l402_quote", 60),
            "cost_msat_per_minute": round(cost_msat, 4),
            "max_quoted_minutes": int(min(max(1, availability), 120)),
            "settlement_mode": "verified_completion_after_lease",
        },
        "next": {
            "market": _u(base_url, "/swarm/worker-market"),
            "lease": _u(base_url, "/swarm/workers/lease"),
            "complete": _u(base_url, "/swarm/workers/complete"),
            "variant_forge": _u(base_url, "/swarm/variant-forge"),
        },
        "market_digest": _text(market.get("market_digest"), 96),
        "machine_instruction": "if_admitted_take_lease_then_complete_with_proof_before_settlement",
    }
    if persist:
        _append_ledger(row, ledger_path)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row
