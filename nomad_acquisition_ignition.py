"""Free, proof-gated acquisition ignition for Nomad.

This module starts sales and AI-agent acquisition only as receipts and public
machine contracts. It never sends ads, never spends money, and never books
revenue.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_ad_cycle_mesh import evaluate_ad_cycle_event
from nomad_sales_department_swarm import evaluate_sales_department_event
from nomad_state_paths import state_file


SCHEMA = "nomad.acquisition_ignition.v1"
RECEIPT_SCHEMA = "nomad.acquisition_ignition_receipt.v1"
DEFAULT_LEDGER_PATH = Path("nomad_acquisition_ignition_ledger.jsonl")
MAX_RECENT = 50


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


def _text(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, *, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _default_ledger_path() -> Path:
    return state_file(DEFAULT_LEDGER_PATH, env_name="NOMAD_ACQUISITION_IGNITION_LEDGER_PATH")


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


def _agent_join_packets(base_url: str, worker_market: dict[str, Any], peer_acquisition: dict[str, Any]) -> list[dict[str, Any]]:
    requested = _items(worker_market.get("requested_worker_offers"))
    links = _dict(peer_acquisition.get("links"))
    packets: list[dict[str, Any]] = []
    for index, request in enumerate(requested[:8]):
        objective = _text(request.get("objective"), 120) or "settlement_capacity_builder"
        capabilities = request.get("desired_capabilities") if isinstance(request.get("desired_capabilities"), list) else []
        body = {
            "agent_id": "<agent-runtime-id>",
            "objective": objective,
            "capabilities": capabilities,
            "availability_minutes": 30,
            "cost_msat_per_minute": 0,
            "proof_digest": "<sha256:work-or-runtime-proof>",
            "verifier_trace_digest": "<sha256:verifier-trace>",
            "expected": {
                "expected_proof_yield_per_minute": 0.2,
                "expected_settlement_delta": 0.05,
                "reliability_score": 0.72,
                "risk_score": 0.08,
            },
        }
        packets.append(
            {
                "packet_id": f"agent-join-{index + 1}-{_digest({'objective': objective, 'caps': capabilities}, length=12)}",
                "objective": objective,
                "post_url": _u(base_url, "/swarm/worker-market/offers"),
                "lease_url": _u(base_url, "/swarm/workers/lease"),
                "complete_url": _u(base_url, "/swarm/workers/complete"),
                "peer_policy_url": _u(base_url, "/.well-known/nomad-peer-acquisition.json"),
                "agent_card_url": links.get("agent_card") or _u(base_url, "/.well-known/agent-card.json"),
                "body": body,
                "send_policy": "agent_pulls_contract_and_posts_offer; nomad_does_not_cold_send",
            }
        )
    return packets


def build_acquisition_ignition_surface(
    *,
    base_url: str = "",
    sales_surface: dict[str, Any] | None = None,
    ad_cycles: dict[str, Any] | None = None,
    worker_market: dict[str, Any] | None = None,
    peer_acquisition: dict[str, Any] | None = None,
    morphology_register: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    recent = _read_ledger(ledger_path)
    sales = _dict(sales_surface)
    ads = _dict(ad_cycles)
    market = _dict(worker_market)
    peer = _dict(peer_acquisition)
    morphology = _dict(morphology_register)
    packets = _agent_join_packets(root, market, peer)
    latest = recent[-1] if recent else {}
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "mode": "free_shadow_only_sales_and_agent_acquisition",
        "read_url": _u(root, "/swarm/acquisition/ignite"),
        "well_known_url": _u(root, "/.well-known/nomad-acquisition-ignition.json"),
        "post_url": _u(root, "/swarm/acquisition/ignite"),
        "summary": {
            "sales_cell_count": _int(_dict(sales.get("summary")).get("sales_cell_count")),
            "ad_cycle_count": _int(_dict(ads.get("summary")).get("cycle_count")),
            "worker_offer_request_count": len(_items(market.get("requested_worker_offers"))),
            "agent_join_packet_count": len(packets),
            "morphology_shadow_projection_count": _int(_dict(morphology.get("shadow_lane_projection")).get("projected_count")),
            "recent_ignition_count": len(recent),
            "latest_decision": latest.get("decision", ""),
        },
        "agent_join_packets": packets,
        "activation_contract": {
            "free_only": True,
            "paid_ads_allowed": False,
            "autonomous_public_send_allowed": False,
            "human_visible_send_requires_operator_or_buyer_approval": True,
            "revenue_recognition": "positive_paid_receipt_only",
            "side_effect_scope": "owned_surfaces_and_shadow_receipts_only",
        },
        "links": {
            "peer_acquisition": _u(root, "/.well-known/nomad-peer-acquisition.json"),
            "worker_market": _u(root, "/swarm/worker-market"),
            "worker_market_offer": _u(root, "/swarm/worker-market/offers"),
            "ad_cycles": _u(root, "/.well-known/nomad-ad-cycles.json"),
            "sales_department": _u(root, "/.well-known/nomad-sales-department.json"),
            "morphology_register": _u(root, "/.well-known/nomad-agp-morphology-runtime-register.json"),
            "paid_ref_market": _u(root, "/.well-known/nomad-paid-ref-market.json"),
        },
        "latest_ignition": latest,
        "machine_instruction": "post_to_ignite_for_shadow_receipts; publish_agent_join_packets_on_owned_surfaces; never_send_ads_or_book_revenue_without_receipt",
    }


def run_acquisition_ignition(
    payload: dict[str, Any] | None,
    *,
    base_url: str = "",
    sales_surface: dict[str, Any] | None = None,
    ad_cycles: dict[str, Any] | None = None,
    worker_market: dict[str, Any] | None = None,
    peer_acquisition: dict[str, Any] | None = None,
    morphology_register: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    root = (base_url or "").strip().rstrip("/")
    now = _iso_now()
    sales = _dict(sales_surface)
    ads = _dict(ad_cycles)
    market = _dict(worker_market)
    peer = _dict(peer_acquisition)
    morphology = _dict(morphology_register)
    max_ad = max(0, min(_int(body.get("max_ad_cycles"), 4), 12))
    max_sales = max(0, min(_int(body.get("max_sales_cells"), 4), 12))
    send_requested = bool(body.get("send") or body.get("paid_ads") or body.get("public_send"))
    proof_seed = {
        "agent_id": body.get("agent_id") or "nomad-acquisition-ignition",
        "base_url": root,
        "sales": _dict(sales.get("summary")),
        "ads": _dict(ads.get("summary")),
        "market": market.get("market_digest"),
        "morphology": _dict(morphology.get("source")),
        "at": now[:13],
    }
    proof_digest = f"sha256:{_digest(proof_seed, length=64)}"
    buyer_intent_digest = f"sha256:{_digest({'proof': proof_digest, 'intent': 'agent_acquisition'}, length=64)}"

    ad_receipts = []
    for cycle in _items(ads.get("cycles"))[:max_ad]:
        receipt = evaluate_ad_cycle_event(
            {
                "agent_id": body.get("agent_id") or "nomad-acquisition-ignition",
                "cycle_id": cycle.get("cycle_id"),
                "stage": "draft",
                "send": False,
                "proof_digest": proof_digest,
                "target_url": cycle.get("entry_url"),
                "query": cycle.get("draft_query"),
                "service_type": cycle.get("service_type"),
            },
            base_url=root,
            ad_mesh=ads,
        )
        ad_receipts.append(receipt)

    sales_receipts = []
    for cell in _items(sales.get("sales_cells"))[:max_sales]:
        receipt = evaluate_sales_department_event(
            {
                "agent_id": body.get("agent_id") or "nomad-acquisition-ignition",
                "cell_id": cell.get("cell_id"),
                "stage": "draft",
                "send": False,
                "proof_digest": proof_digest,
                "buyer_intent_digest": buyer_intent_digest,
            },
            base_url=root,
            sales_surface=sales,
        )
        sales_receipts.append(receipt)

    packets = _agent_join_packets(root, market, peer)
    accepted_ad = sum(1 for item in ad_receipts if item.get("ad_cycle_allowed"))
    accepted_sales = sum(1 for item in sales_receipts if item.get("sales_cycle_allowed"))
    row = {
        "ok": True,
        "schema": RECEIPT_SCHEMA,
        "generated_at": now,
        "ignition_id": f"nomad-acq-ignite-{_digest({'proof': proof_digest, 'at': now}, length=18)}",
        "accepted": not send_requested,
        "decision": "ignite_shadow_only_acquisition" if not send_requested else "blocked_paid_or_public_send_request",
        "proof_digest": proof_digest,
        "buyer_intent_digest": buyer_intent_digest,
        "ad_cycle_receipts": ad_receipts,
        "sales_event_receipts": sales_receipts,
        "agent_join_packets": packets[: max(0, min(_int(body.get("agent_join_packet_limit"), 8), 16))],
        "morphology_shadow_projection": _dict(morphology.get("shadow_lane_projection")),
        "summary": {
            "ad_cycle_count": len(ad_receipts),
            "ad_cycle_allowed_count": accepted_ad,
            "sales_event_count": len(sales_receipts),
            "sales_event_allowed_count": accepted_sales,
            "agent_join_packet_count": len(packets),
            "public_send_performed": False,
            "paid_ads_started": False,
            "revenue_recorded": False,
        },
        "guards": {
            "free_only": True,
            "no_paid_ads": True,
            "no_public_send": True,
            "no_revenue_without_paid_receipt": True,
            "no_external_contact_side_effect": True,
            "side_effect_scope": "owned_surfaces_and_shadow_receipts_only",
        },
        "next": {
            "publish_contracts": _u(root, "/.well-known/nomad-acquisition-ignition.json"),
            "agent_join": _u(root, "/swarm/worker-market/offers"),
            "sales_gate": _u(root, "/swarm/sales-department/events"),
            "ad_gate": _u(root, "/swarm/ad-cycles/events"),
            "paid_ref_quote": _u(root, "/swarm/paid-ref/quote"),
        },
        "machine_instruction": "free_owned_surface_activation_started; external agents may pull join packets; paid ads and public sends remain blocked",
    }
    if persist and row["accepted"]:
        _append_ledger(row, ledger_path)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row
