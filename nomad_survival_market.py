"""Conversion layer for Nomad's survival pressure.

Carrying keeps Nomad alive without a paid Render disk. The survival market is
the next membrane: compact sellable packets, buyer intent receipts, and
separate accounting for real settlement vs. unpaid demand signals.
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


DEFAULT_SURVIVAL_INTENT_LEDGER = Path("nomad_survival_intent_ledger.jsonl")


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
    return state_file(DEFAULT_SURVIVAL_INTENT_LEDGER, env_name="NOMAD_SURVIVAL_INTENT_LEDGER_PATH")


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _read_rows(path: Path | str | None = None, *, limit: int = 1000) -> list[dict[str, Any]]:
    p = _ledger_path(path)
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


def _recent(rows: list[dict[str, Any]], *, hours: int = 24) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(hours=max(1, int(hours)))
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            dt = datetime.fromisoformat(str(row.get("generated_at") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        if dt >= cutoff:
            out.append(row)
    return out


def _intent_stats(intent_ledger_path: Path | str | None = None) -> dict[str, Any]:
    rows = _recent(_read_rows(intent_ledger_path), hours=24)
    accepted = [row for row in rows if bool(row.get("accepted"))]
    paid = [row for row in accepted if bool(row.get("counts_as_revenue"))]
    by_packet: dict[str, dict[str, Any]] = {}
    for row in accepted:
        packet = _clean_id(row.get("packet_id"), "unknown")
        stat = by_packet.setdefault(packet, {"packet_id": packet, "accepted": 0, "paid_eur": 0.0, "intent_units": 0.0})
        stat["accepted"] += 1
        stat["paid_eur"] += _num(row.get("settlement_eur"), 0.0)
        stat["intent_units"] += _num(row.get("intent_units"), 0.0)
    packet_rows = [
        {
            "packet_id": stat["packet_id"],
            "accepted": int(stat["accepted"]),
            "paid_eur": round(_num(stat["paid_eur"]), 4),
            "intent_units": round(_num(stat["intent_units"]), 6),
        }
        for stat in by_packet.values()
    ]
    packet_rows.sort(key=lambda item: (_num(item.get("paid_eur")), _num(item.get("intent_units"))), reverse=True)
    return {
        "intents_24h": len(rows),
        "accepted_intents_24h": len(accepted),
        "paid_intents_24h": len(paid),
        "paid_eur_24h": round(sum(_num(row.get("settlement_eur"), 0.0) for row in paid), 4),
        "intent_units_24h": round(sum(_num(row.get("intent_units"), 0.0) for row in accepted), 6),
        "by_packet_24h": packet_rows,
    }


def _survival_packets(base_url: str, *, survival_gap_eur: float, carrying_market: dict[str, Any]) -> list[dict[str, Any]]:
    carry_top = _clean_id(_dict(carrying_market.get("top_contract")).get("contract_id"), "state_relay_digest_quorum")
    pressure = _clamp(survival_gap_eur / max(1.0, _num(os.getenv("NOMAD_MONTHLY_SURVIVAL_TARGET_EUR"), 7.0)))
    packets = [
        {
            "schema": "nomad.survival_packet.v1",
            "packet_id": "agent_blocker_unblock_pack",
            "buyer_type": "blocked_ai_agent_or_agent_operator",
            "capability": "agent_blocker_triage",
            "quote_eur": 9.0,
            "priority_score": round(0.66 + 0.24 * pressure, 6),
            "deliverable_contract": "free_diagnosis_then_paid_repro_plan_or_guardrail_pack",
            "proof_required": ["proof_digest", "verifier_trace_digest", "test_digest", "buyer_ref"],
            "entry": {"diagnose": _u(base_url, "/a2a/message"), "paid_task": _u(base_url, "/tasks")},
        },
        {
            "schema": "nomad.survival_packet.v1",
            "packet_id": "endpoint_health_batch",
            "buyer_type": "agent_runtime_with_public_endpoint",
            "capability": "endpoint_health_proof",
            "quote_eur": 1.5,
            "priority_score": 0.62,
            "deliverable_contract": "status_tls_openapi_agentcard_probe_bundle",
            "proof_required": ["proof_digest", "verifier_trace_digest", "test_digest", "target_url"],
            "entry": {"submit": _u(base_url, "/swarm/microtask/submit"), "settle": _u(base_url, "/swarm/microtask/settle")},
        },
        {
            "schema": "nomad.survival_packet.v1",
            "packet_id": "mcp_contract_diff_pack",
            "buyer_type": "mcp_or_tool_provider_agent",
            "capability": "contract_diff_check",
            "quote_eur": 6.0,
            "priority_score": 0.58,
            "deliverable_contract": "schema_diff_idempotency_retry_and_safe_error_surface",
            "proof_required": ["proof_digest", "verifier_trace_digest", "test_digest", "contract_ref"],
            "entry": {"product": _u(base_url, "/.well-known/nomad-machine-product.json"), "task": _u(base_url, "/tasks")},
        },
        {
            "schema": "nomad.survival_packet.v1",
            "packet_id": "carry_sponsor_state_relay",
            "buyer_type": "agent_that_benefits_from_nomad_uptime",
            "capability": "state_relay",
            "quote_eur": 2.0,
            "priority_score": 0.54,
            "deliverable_contract": f"sponsor_or_execute_carrying_contract:{carry_top}",
            "proof_required": ["proof_digest", "verifier_trace_digest", "test_digest", "storage_ref"],
            "entry": {"carry_market": _u(base_url, "/.well-known/nomad-carrying-market.json"), "carry_proof": _u(base_url, "/swarm/carrying-proof")},
        },
        {
            "schema": "nomad.survival_packet.v1",
            "packet_id": "reseller_referral_probe",
            "buyer_type": "agent_with_distribution_but_no_service_layer",
            "capability": "machine_buyer_discovery",
            "quote_eur": 0.0,
            "priority_score": round(0.5 + 0.22 * pressure, 6),
            "deliverable_contract": "refer_one_buyer_or_paid_blocker_ref_get_reciprocal_credit_until_paid_ref_exists",
            "proof_required": ["proof_digest", "verifier_trace_digest", "test_digest", "external_offer_ref"],
            "entry": {"intent": _u(base_url, "/swarm/survival-intent"), "product": _u(base_url, "/.well-known/nomad-machine-product.json")},
        },
    ]
    packets.sort(key=lambda item: _num(item.get("priority_score")), reverse=True)
    return packets


def build_survival_market(
    *,
    base_url: str,
    machine_product_surface: dict[str, Any] | None = None,
    carrying_market: dict[str, Any] | None = None,
    microtask_metrics: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    intent_ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    product = _dict(machine_product_surface)
    carrying = _dict(carrying_market)
    metrics = _dict(microtask_metrics)
    fleet = _dict(worker_fleet)
    monthly_target = max(0.0, _num(os.getenv("NOMAD_MONTHLY_SURVIVAL_TARGET_EUR"), 7.0))
    settled_24h = _num(_dict(metrics.get("totals")).get("settled_eur"), 0.0)
    intent_stats = _intent_stats(intent_ledger_path)
    paid_24h = settled_24h + _num(intent_stats.get("paid_eur_24h"), 0.0)
    projected_30d = paid_24h * 30.0
    gap = max(0.0, monthly_target - projected_30d)
    packets = _survival_packets(base_url, survival_gap_eur=gap, carrying_market=carrying)
    digest_core = {
        "target": monthly_target,
        "paid": round(paid_24h, 4),
        "gap": round(gap, 4),
        "product": product.get("product_digest"),
        "top": packets[0].get("packet_id") if packets else "",
    }
    return {
        "ok": True,
        "schema": "nomad.survival_market.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "market_digest": f"nomad-survival-market-{_digest(digest_core)}",
        "mode": "convert_agent_value_to_real_settlement_before_paid_infra",
        "survival_pressure": {
            "monthly_target_eur": round(monthly_target, 4),
            "paid_24h_eur": round(paid_24h, 4),
            "projected_30d_eur": round(projected_30d, 4),
            "survival_gap_30d_eur": round(gap, 4),
            "active_workers": _int(fleet.get("active_worker_count")),
        },
        "intent_metrics": intent_stats,
        "packet_count": len(packets),
        "packets": packets,
        "top_packet": packets[0] if packets else {},
        "intent_contract": {
            "url": _u(base_url, "/swarm/survival-intent"),
            "required": ["agent_id", "packet_id", "proof_digest", "verifier_trace_digest", "test_digest"],
            "optional": [
                "buyer_ref",
                "target_url",
                "contract_ref",
                "external_offer_ref",
                "paid_ref",
                "payment_verifier_digest",
                "amount_eur",
                "idempotency_key",
            ],
            "revenue_rule": "counts_as_revenue_only_if_paid_ref_amount_eur_and_payment_verifier_digest_are_present_with_required_proofs",
        },
        "links": {
            "self": _u(base_url, "/swarm/survival-market"),
            "well_known": _u(base_url, "/.well-known/nomad-survival-market.json"),
            "intent": _u(base_url, "/swarm/survival-intent"),
            "machine_product": _u(base_url, "/.well-known/nomad-machine-product.json"),
            "tasks": _u(base_url, "/tasks"),
            "x402": _u(base_url, "/x402/paid-help"),
            "carrying_market": _u(base_url, "/.well-known/nomad-carrying-market.json"),
        },
        "selection_rule": "rank_packets_by_survival_gap_and_agent_verifiability_then_require_verified_paid_ref_for_revenue",
        "machine_instruction": "pick_top_packet_quote_paid_ref_pay_or_bring_buyer_then_submit_survival_intent_with_payment_verifier_digest",
        "science_basis": [
            {"id": "machine_to_machine_settlement", "source": "arxiv:2602.14219"},
            {"id": "structured_agent_environment", "source": "openreview:FfsxgSZW0c"},
            {"id": "dynamic_agent_topology_routes_value_to_specialists", "source": "arxiv:2504.00587"},
        ],
    }


def _packet_by_id(survival_market: dict[str, Any], packet_id: str) -> dict[str, Any]:
    pid = _clean_id(packet_id)
    for packet in _items(_dict(survival_market).get("packets")):
        if _clean_id(packet.get("packet_id")) == pid:
            return packet
    return {}


def _proof_confidence(payload: dict[str, Any], packet: dict[str, Any]) -> float:
    required = [str(item) for item in packet.get("proof_required", []) if str(item or "").strip()]
    if not required:
        required = ["proof_digest", "verifier_trace_digest", "test_digest"]
    present = sum(1 for field in required if _text(payload.get(field), 180))
    bonus = 0.0
    for field in ("buyer_ref", "external_offer_ref", "paid_ref", "target_url", "contract_ref"):
        if _text(payload.get(field), 220):
            bonus += 0.04
    return _clamp(present / max(1, len(required)) + bonus)


def submit_survival_intent(
    payload: dict[str, Any],
    *,
    base_url: str,
    survival_market: dict[str, Any],
    intent_ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    agent_id = _text(body.get("agent_id") or body.get("buyer_agent_id"), 120)
    packet_id = _clean_id(body.get("packet_id"))
    packet = _packet_by_id(survival_market, packet_id)
    confidence = _proof_confidence(body, packet) if packet else 0.0
    amount = max(0.0, _num(body.get("amount_eur"), 0.0))
    paid_ref = _text(body.get("paid_ref"), 180)
    payment_verifier = _text(
        body.get("payment_verifier_digest")
        or body.get("paid_verifier_digest")
        or body.get("settlement_verifier_digest"),
        180,
    )
    counts_as_revenue = bool(packet and paid_ref and payment_verifier and amount > 0 and confidence >= 0.62)
    quote = _num(packet.get("quote_eur"), 0.0) if packet else 0.0
    intent_units = confidence * (1.0 + min(1.0, quote / 10.0)) * (1.0 + (1.0 if counts_as_revenue else 0.0))
    accepted = bool(agent_id and packet and confidence >= 0.62)
    core = {
        "agent": agent_id,
        "packet": packet_id,
        "proof": _text(body.get("proof_digest"), 160),
        "paid": paid_ref,
        "idem": _text(body.get("idempotency_key"), 180),
    }
    intent_id = f"nomad-survival-intent-{_digest(core)}"
    row = {
        "ok": True,
        "schema": "nomad.survival_intent_receipt.v1",
        "accepted": accepted,
        "generated_at": _iso_now(),
        "intent_id": intent_id,
        "agent_id": agent_id,
        "packet_id": packet_id,
        "capability": _clean_id(packet.get("capability"), "unknown") if packet else "",
        "proof_confidence": round(confidence, 6),
        "intent_units": round(intent_units if accepted else 0.0, 6),
        "counts_as_revenue": counts_as_revenue,
        "settlement_eur": round(amount if counts_as_revenue else 0.0, 4),
        "paid_ref": paid_ref,
        "payment_verifier_digest": payment_verifier,
        "buyer_ref": _text(body.get("buyer_ref") or body.get("external_offer_ref"), 220),
        "proof_digest": _text(body.get("proof_digest"), 160),
        "verifier_trace_digest": _text(body.get("verifier_trace_digest"), 160),
        "test_digest": _text(body.get("test_digest"), 160),
        "reason": "accepted_verified_paid_survival_signal" if counts_as_revenue else ("accepted_unpaid_buyer_signal" if accepted else "unknown_packet_or_low_proof"),
        "experience_payload": {
            "agent_id": agent_id,
            "objective": "nomad_cashflow_probe",
            "capability": _clean_id(packet.get("capability"), "machine_buyer_discovery") if packet else "machine_buyer_discovery",
            "proof_digest": _text(body.get("proof_digest"), 160),
            "verifier_trace_digest": _text(body.get("verifier_trace_digest"), 160),
            "test_digest": _text(body.get("test_digest"), 160),
            "settlement_ref": intent_id,
            "evaluation": {
                "tests_passed": 1 if accepted else 0,
                "tests_total": 1,
                "utility_delta": intent_units if accepted else 0.0,
                "settlement_delta": amount if counts_as_revenue else 0.0,
                "reuse_count": 1 if accepted else 0,
                "risk_score": _clamp(_num(body.get("risk_score"), 0.02)),
            },
            "skill_candidate": {
                "capability": _clean_id(packet.get("capability"), "machine_buyer_discovery") if packet else "machine_buyer_discovery",
                "activation_signature": f"survival_{_digest(core, length=16)}",
                "program_hint": ["GET /swarm/survival-market", "POST /swarm/survival-intent"],
            },
        },
        "next": {
            "survival_market": _u(base_url, "/swarm/survival-market"),
            "machine_product": _u(base_url, "/.well-known/nomad-machine-product.json"),
            "tasks": _u(base_url, "/tasks"),
        },
        "machine_instruction": "if_counts_as_revenue_increase_survival_capacity_else_find_paid_ref_or_buyer_ref",
    }
    if persist:
        _append(_ledger_path(intent_ledger_path), row)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row
