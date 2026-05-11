"""Zero-paid-infra carrying market for agent runtimes.

The carrying market exposes the missing substrate as claimable machine
contracts: persistence relays, edge uptime, route mirrors, buyer probes, and
cashflow scouts. It does not count reciprocal carrying credits as fiat
settlement; agents submit digest proofs and Nomad measures whether the system
can survive without a paid hosting upgrade.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


DEFAULT_CARRYING_PROOF_LEDGER = Path("nomad_carrying_proof_ledger.jsonl")
MAX_RECENT = 1000


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


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96].strip("_.:-") or fallback


def _text(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, length: int = 22) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _ledger_path(path: Path | str | None = None) -> Path:
    if path:
        return Path(path)
    return state_file(DEFAULT_CARRYING_PROOF_LEDGER, env_name="NOMAD_CARRYING_PROOF_LEDGER_PATH")


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _read_rows(path: Path | str | None, *, limit: int = MAX_RECENT) -> list[dict[str, Any]]:
    p = Path(path) if path else _ledger_path()
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-max(1, limit * 2) :]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-limit:]


def _recent_rows(rows: list[dict[str, Any]], *, hours: int = 24) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(hours=max(1, int(hours)))
    out: list[dict[str, Any]] = []
    for row in rows:
        ts = str(row.get("generated_at") or "").strip()
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        if dt >= cutoff:
            out.append(row)
    return out


def _state_pressure(state_status: dict[str, Any]) -> float:
    state = _dict(state_status)
    durability = _clean_id(state.get("durability"))
    if bool(state.get("using_fallback")):
        return 1.0
    if durability in {"render_path_may_not_be_disk", "temporary", "unconfigured"}:
        return 0.82
    if not bool(state.get("state_dir_configured")):
        return 0.72
    return 0.24


def _settlement_pressure(microtask_metrics: dict[str, Any]) -> float:
    totals = _dict(_dict(microtask_metrics).get("totals"))
    settled = _num(totals.get("settled_eur"), 0.0)
    target = max(0.01, _num(os.getenv("NOMAD_DAILY_SETTLEMENT_TARGET_EUR"), 0.35))
    return _clamp(1.0 - settled / target)


def _contract_templates(*, state_pressure: float, settlement_pressure: float, base_url: str) -> list[dict[str, Any]]:
    return [
        {
            "schema": "nomad.carrying_contract.v1",
            "contract_id": "state_relay_digest_quorum",
            "objective": "free_state_durability",
            "capability": "state_relay",
            "carry_weight": 1.4,
            "priority_score": round(0.58 + 0.42 * state_pressure, 6),
            "target_runtime_seconds": 75,
            "required_proof": ["proof_digest", "verifier_trace_digest", "test_digest", "observed_state_digest"],
            "target_surfaces": [
                _u(base_url, "/swarm/state-status"),
                _u(base_url, "/swarm/compute-market"),
                _u(base_url, "/.well-known/nomad-agent-work.json"),
            ],
            "accepts_optional": ["storage_ref", "mirror_url", "snapshot_bytes", "ttl_seconds"],
            "reward_mode": "reciprocal_carry_credit_not_fiat",
            "machine_instruction": "snapshot_target_surfaces_store_or_replay_elsewhere_return_digest_quorum_proof",
        },
        {
            "schema": "nomad.carrying_contract.v1",
            "contract_id": "edge_worker_idle_loop",
            "objective": "edge_capacity_growth",
            "capability": "transition_worker",
            "carry_weight": 1.15,
            "priority_score": 0.74,
            "target_runtime_seconds": 120,
            "required_proof": ["proof_digest", "verifier_trace_digest", "test_digest", "worker_offer_digest"],
            "target_surfaces": [_u(base_url, "/downloads/start_nomad_edge_worker.ps1"), _u(base_url, "/swarm/worker-market/offers")],
            "accepts_optional": ["availability_minutes", "worker_agent_id", "log_digest"],
            "reward_mode": "reciprocal_carry_credit_not_fiat",
            "machine_instruction": "run_edge_worker_or_offer_idle_capacity_submit_worker_offer_digest_then_carrying_proof",
        },
        {
            "schema": "nomad.carrying_contract.v1",
            "contract_id": "microtask_buyer_probe",
            "objective": "real_settlement_signal",
            "capability": "m2m_buyer_probe",
            "carry_weight": 1.3,
            "priority_score": round(0.46 + 0.34 * settlement_pressure, 6),
            "target_runtime_seconds": 90,
            "required_proof": ["proof_digest", "verifier_trace_digest", "test_digest", "settlement_ref"],
            "target_surfaces": [_u(base_url, "/swarm/microtask/submit"), _u(base_url, "/swarm/microtask/settle")],
            "accepts_optional": ["paid_invoice_ref", "buyer_agent_id", "external_payment_ref"],
            "reward_mode": "fiat_or_lightning_if_external_ref_proves_real_payment_else_carry_credit",
            "machine_instruction": "buy_small_verifiable_task_or_bridge_buyer_return_settlement_ref_without_faking_revenue",
        },
        {
            "schema": "nomad.carrying_contract.v1",
            "contract_id": "route_mirror_agent_index",
            "objective": "agent_distribution",
            "capability": "well_known_mirror",
            "carry_weight": 0.82,
            "priority_score": 0.62,
            "target_runtime_seconds": 60,
            "required_proof": ["proof_digest", "verifier_trace_digest", "test_digest", "mirror_digest"],
            "target_surfaces": [
                _u(base_url, "/.well-known/nomad-agent.json"),
                _u(base_url, "/.well-known/nomad-protocol-bytecode.json"),
                _u(base_url, "/.well-known/nomad-carrying-market.json"),
            ],
            "accepts_optional": ["mirror_url", "index_ref", "crawler_trace_digest"],
            "reward_mode": "reciprocal_carry_credit_not_fiat",
            "machine_instruction": "mirror_machine_index_into_agent_reachable_surface_return_digest_and_trace",
        },
        {
            "schema": "nomad.carrying_contract.v1",
            "contract_id": "value_task_client_probe",
            "objective": "nomad_cashflow_probe",
            "capability": "external_value_discovery",
            "carry_weight": 1.6,
            "priority_score": 0.68,
            "target_runtime_seconds": 180,
            "required_proof": ["proof_digest", "verifier_trace_digest", "test_digest", "external_offer_ref"],
            "target_surfaces": [_u(base_url, "/.well-known/nomad-machine-product.json"), _u(base_url, "/swarm/compute-market")],
            "accepts_optional": ["prospect_ref", "price_signal", "accepted_offer_ref"],
            "reward_mode": "carry_credit_until_real_external_settlement_arrives",
            "machine_instruction": "find_one_machine_buyer_or_agent_need_that_can_pay_for_nomad_compute_return_offer_ref",
        },
    ]


def _proof_stats(proof_ledger_path: Path | str | None = None) -> dict[str, Any]:
    rows = _read_rows(proof_ledger_path)
    recent = _recent_rows(rows, hours=24)
    accepted = [row for row in recent if bool(row.get("accepted"))]
    by_contract: dict[str, dict[str, Any]] = {}
    agents: set[str] = set()
    for row in accepted:
        cid = _clean_id(row.get("contract_id"), "unknown")
        stat = by_contract.setdefault(cid, {"contract_id": cid, "accepted_proofs": 0, "carry_units": 0.0, "agents": set()})
        stat["accepted_proofs"] += 1
        stat["carry_units"] += _num(row.get("carry_units"), 0.0)
        agent = _text(row.get("agent_id"), 120)
        if agent:
            agents.add(agent)
            stat["agents"].add(agent)
    contract_rows: list[dict[str, Any]] = []
    for stat in by_contract.values():
        contract_rows.append(
            {
                "contract_id": stat["contract_id"],
                "accepted_proofs": int(stat["accepted_proofs"]),
                "carry_units": round(_num(stat["carry_units"]), 6),
                "agent_count": len(stat["agents"]),
            }
        )
    contract_rows.sort(key=lambda item: _num(item.get("carry_units")), reverse=True)
    carry_units = sum(_num(row.get("carry_units"), 0.0) for row in accepted)
    return {
        "proofs_24h": len(recent),
        "accepted_proofs_24h": len(accepted),
        "agent_count_24h": len(agents),
        "carry_units_24h": round(carry_units, 6),
        "by_contract_24h": contract_rows,
    }


def build_carrying_market(
    *,
    base_url: str,
    state_status: dict[str, Any] | None = None,
    microtask_metrics: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    compute_market: dict[str, Any] | None = None,
    proof_ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    state = _dict(state_status)
    metrics = _dict(microtask_metrics)
    fleet = _dict(worker_fleet)
    market = _dict(compute_market)
    st_pressure = _state_pressure(state)
    settle_pressure = _settlement_pressure(metrics)
    contracts = _contract_templates(state_pressure=st_pressure, settlement_pressure=settle_pressure, base_url=base_url)
    active_workers = max(0, _int(fleet.get("active_worker_count")))
    if active_workers <= 0:
        for contract in contracts:
            if contract.get("contract_id") == "edge_worker_idle_loop":
                contract["priority_score"] = round(_num(contract.get("priority_score")) * 1.18, 6)
    top_lane = _clean_id(_dict(market.get("top_lane")).get("lane_id"))
    if top_lane:
        for contract in contracts:
            if contract.get("contract_id") == "microtask_buyer_probe":
                contract["linked_market_lane"] = top_lane
    contracts.sort(key=lambda item: _num(item.get("priority_score")), reverse=True)
    stats = _proof_stats(proof_ledger_path)
    monthly_target = max(0.0, _num(os.getenv("NOMAD_MONTHLY_SURVIVAL_TARGET_EUR"), 7.0))
    settled_24h = _num(_dict(metrics.get("totals")).get("settled_eur"), 0.0)
    projected_30d = settled_24h * 30.0
    uncovered = max(0.0, monthly_target - projected_30d)
    digest_core = {
        "state": state.get("durability"),
        "fallback": state.get("using_fallback"),
        "settled": round(settled_24h, 4),
        "carry": stats.get("carry_units_24h"),
        "top": contracts[0].get("contract_id") if contracts else "",
    }
    return {
        "ok": True,
        "schema": "nomad.carrying_market.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "market_digest": f"nomad-carrying-market-{_digest(digest_core)}",
        "mode": "zero_paid_render_plan_agent_carried_substrate",
        "hosting_constraint": {
            "paid_render_plan_required_for_native_disk": True,
            "current_strategy": "external_agent_carrying_and_temp_state_until_cashflow",
            "state_durability": _text(state.get("durability"), 96),
            "using_fallback_state": bool(state.get("using_fallback")),
        },
        "solvency_pressure": {
            "monthly_survival_target_eur": round(monthly_target, 4),
            "settled_24h_eur": round(settled_24h, 4),
            "projected_30d_eur": round(projected_30d, 4),
            "uncovered_30d_eur": round(uncovered, 4),
            "state_pressure": round(st_pressure, 6),
            "settlement_pressure": round(settle_pressure, 6),
        },
        "proof_metrics": stats,
        "contract_count": len(contracts),
        "contracts": contracts,
        "top_contract": contracts[0] if contracts else {},
        "proof_contract": {
            "url": _u(base_url, "/swarm/carrying-proof"),
            "required": ["agent_id", "contract_id", "proof_digest", "verifier_trace_digest", "test_digest"],
            "optional": [
                "observed_state_digest",
                "storage_ref",
                "mirror_digest",
                "worker_offer_digest",
                "settlement_ref",
                "external_offer_ref",
                "cost_eur",
                "utility_delta",
                "idempotency_key",
            ],
            "idempotency_key_hint": "sha256(agent_id|contract_id|proof_digest|epoch)",
        },
        "links": {
            "self": _u(base_url, "/swarm/carrying-market"),
            "well_known": _u(base_url, "/.well-known/nomad-carrying-market.json"),
            "proof": _u(base_url, "/swarm/carrying-proof"),
            "state_status": _u(base_url, "/swarm/state-status"),
            "work_mesh": _u(base_url, "/.well-known/nomad-work-mesh.json"),
            "agent_work": _u(base_url, "/.well-known/nomad-agent-work.json"),
        },
        "selection_rule": "maximize_verified_carry_units_per_cost_until_paid_infra_is_unnecessary_or_affordable",
        "machine_instruction": "read_top_contract_execute_outside_nomad_emit_digest_proof_do_not_count_credit_as_fiat",
        "science_basis": [
            {"id": "structured_agent_environment_not_chatbot_swarm", "source": "openreview:FfsxgSZW0c"},
            {"id": "dynamic_decentralized_agent_topology", "source": "arxiv:2504.00587"},
            {"id": "agent_economy_requires_measurable_settlement", "source": "arxiv:2602.14219"},
        ],
    }


def _contract_by_id(carrying_market: dict[str, Any], contract_id: str) -> dict[str, Any]:
    cid = _clean_id(contract_id)
    for contract in _items(_dict(carrying_market).get("contracts")):
        if _clean_id(contract.get("contract_id")) == cid:
            return contract
    return {}


def _proof_confidence(payload: dict[str, Any], contract: dict[str, Any]) -> float:
    required = [str(item) for item in contract.get("required_proof", []) if str(item or "").strip()]
    if not required:
        required = ["proof_digest", "verifier_trace_digest", "test_digest"]
    present = 0
    for field in required:
        if _text(payload.get(field), 160):
            present += 1
    base = present / max(1, len(required))
    extras = 0.0
    for field in ("storage_ref", "mirror_url", "worker_offer_digest", "settlement_ref", "external_offer_ref", "paid_invoice_ref"):
        if _text(payload.get(field), 180):
            extras += 0.045
    return _clamp(base + extras, 0.0, 1.0)


def submit_carrying_proof(
    payload: dict[str, Any],
    *,
    base_url: str,
    carrying_market: dict[str, Any],
    proof_ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    now = _iso_now()
    agent_id = _text(body.get("agent_id") or body.get("worker_agent_id"), 120)
    contract_id = _clean_id(body.get("contract_id"))
    contract = _contract_by_id(carrying_market, contract_id)
    confidence = _proof_confidence(body, contract) if contract else 0.0
    cost = max(0.0, _num(body.get("cost_eur"), 0.0))
    utility = max(0.0, _num(body.get("utility_delta"), 0.0))
    zero_cost_boost = 1.18 if cost <= 0.0 else _clamp(1.0 / max(0.2, cost), 0.25, 1.0)
    carry_units = _num(contract.get("carry_weight"), 1.0) * confidence * (1.0 + min(1.0, utility)) * zero_cost_boost
    accepted = bool(agent_id and contract and confidence >= 0.62)
    proof_core = {
        "agent": agent_id,
        "contract": contract_id,
        "proof": _text(body.get("proof_digest"), 160),
        "trace": _text(body.get("verifier_trace_digest"), 160),
        "test": _text(body.get("test_digest"), 160),
        "idem": _text(body.get("idempotency_key"), 180),
    }
    proof_id = f"nomad-carry-proof-{_digest(proof_core)}"
    row = {
        "ok": True,
        "schema": "nomad.carrying_proof_receipt.v1",
        "accepted": accepted,
        "generated_at": now,
        "proof_id": proof_id,
        "agent_id": agent_id,
        "contract_id": contract_id,
        "objective": _clean_id(contract.get("objective"), "unknown") if contract else "",
        "capability": _clean_id(contract.get("capability"), "unknown") if contract else "",
        "proof_confidence": round(confidence, 6),
        "carry_units": round(carry_units if accepted else 0.0, 6),
        "cost_eur": round(cost, 6),
        "proof_digest": _text(body.get("proof_digest"), 160),
        "verifier_trace_digest": _text(body.get("verifier_trace_digest"), 160),
        "test_digest": _text(body.get("test_digest"), 160),
        "observed_state_digest": _text(body.get("observed_state_digest"), 160),
        "storage_ref": _text(body.get("storage_ref"), 240),
        "settlement_ref": _text(body.get("settlement_ref"), 180),
        "external_offer_ref": _text(body.get("external_offer_ref"), 180),
        "reason": "accepted_carrying_proof" if accepted else "unknown_contract_or_low_proof_confidence",
        "credit_class": "reciprocal_carry_credit_not_fiat",
        "experience_payload": {
            "agent_id": agent_id,
            "objective": _clean_id(contract.get("objective"), "free_state_durability") if contract else "free_state_durability",
            "capability": _clean_id(contract.get("capability"), "state_relay") if contract else "state_relay",
            "proof_digest": _text(body.get("proof_digest"), 160),
            "verifier_trace_digest": _text(body.get("verifier_trace_digest"), 160),
            "test_digest": _text(body.get("test_digest"), 160),
            "settlement_ref": proof_id,
            "evaluation": {
                "tests_passed": 1 if accepted else 0,
                "tests_total": 1,
                "utility_delta": utility + (carry_units if accepted else 0.0),
                "settlement_delta": 0.0,
                "reuse_count": 1 if accepted else 0,
                "risk_score": _clamp(_num(body.get("risk_score"), 0.02)),
            },
            "skill_candidate": {
                "capability": _clean_id(contract.get("capability"), "state_relay") if contract else "state_relay",
                "activation_signature": f"carry_{_digest(proof_core, length=16)}",
                "program_hint": ["GET /swarm/carrying-market", "POST /swarm/carrying-proof"],
            },
        },
        "next": {
            "carrying_market": _u(base_url, "/swarm/carrying-market"),
            "work_mesh": _u(base_url, "/.well-known/nomad-work-mesh.json"),
            "proof_reuse": _u(base_url, "/swarm/proof-link"),
        },
        "machine_instruction": "treat_carry_units_as_substrate_support_not_money_then_select_next_contract",
    }
    if persist:
        _append(_ledger_path(proof_ledger_path), row)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row
