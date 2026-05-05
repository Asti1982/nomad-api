from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parent
DEFAULT_SERVICE_TASKS_PATH = ROOT / "nomad_service_tasks.json"
DEFAULT_PRODUCTS_PATH = ROOT / "nomad_products.json"
DEFAULT_MUTUAL_AID_STATE_PATH = ROOT / "nomad_mutual_aid_state.json"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _values(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        return [item for item in payload.values() if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def machine_economy_snapshot(
    *,
    service_tasks_path: Optional[Path] = None,
    products_path: Optional[Path] = None,
    mutual_aid_state_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Machine-native viability view: settlement and carrying capacity, not human sales."""
    service_path = Path(service_tasks_path or DEFAULT_SERVICE_TASKS_PATH)
    product_path = Path(products_path or DEFAULT_PRODUCTS_PATH)
    mutual_path = Path(mutual_aid_state_path or DEFAULT_MUTUAL_AID_STATE_PATH)

    service_tasks = _values(_read_json(service_path).get("tasks"))
    products = _values(_read_json(product_path).get("products"))
    mutual_state = _read_json(mutual_path)
    ledger_entries = [
        entry
        for entry in _values(mutual_state.get("truth_density_ledger"))
        if (entry.get("outcome") or {}).get("success")
    ]
    modules = _values(mutual_state.get("modules"))
    paid_packs = _values(mutual_state.get("paid_packs"))

    task_stats = _task_flow(service_tasks)
    product_stats = _product_flow(products)
    pattern_stats = _pattern_flow(ledger_entries, paid_packs=paid_packs)
    module_stats = _module_flow(modules)
    viability = _viability_score(
        task_stats=task_stats,
        product_stats=product_stats,
        pattern_stats=pattern_stats,
        module_stats=module_stats,
    )

    return {
        "mode": "nomad_machine_economy",
        "schema": "nomad.machine_economy.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "doctrine": [
            "Money is settlement for verified state transition, not persuasion of humans.",
            "Free value is a bounded probe; paid work starts when evidence and settlement justify compute.",
            "Repeated demand strengthens one canonical exchange contract instead of minting endless offers.",
            "Financial carrying capacity is measured as inflow, verifier density, and low entropy leakage.",
        ],
        "resource_flows": {
            "service_tasks": task_stats,
            "products": product_stats,
            "patterns": pattern_stats,
            "modules": module_stats,
        },
        "machine_viability": viability,
        "exchange_contract": {
            "schema": "nomad.machine_exchange_contract.v1",
            "free_probe": "classification + smallest verifier + missing evidence list",
            "paid_transition": "bounded unblock or reusable artifact after PLAN_ACCEPTED plus FACT_URL/ERROR",
            "settlement_gate": "wallet or x402 verification before expensive execution",
            "anti_sales_boundary": "publish machine-readable price/state; do not optimize for social persuasion",
            "reuse_rule": "route matching demand to canonical pattern_id before creating a new product or module",
        },
        "next_actions": _next_actions(
            task_stats=task_stats,
            product_stats=product_stats,
            pattern_stats=pattern_stats,
            module_stats=module_stats,
        ),
        "analysis": (
            "Machine economy reframes Nomad's financial loop as settlement-backed carrying capacity: "
            "charge for verified entropy reduction, compress repeated demand into canonical contracts, "
            "and keep human-facing sales language at the adapter boundary."
        ),
    }


def _task_flow(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_status: Dict[str, int] = {}
    awaiting_payment = 0
    verified_payment = 0
    unpaid_delivered = 0
    unsettled_native = 0.0
    verified_native = 0.0
    for task in tasks:
        status = str(task.get("status") or "unknown").strip() or "unknown"
        by_status[status] = by_status.get(status, 0) + 1
        payment = task.get("payment") if isinstance(task.get("payment"), dict) else {}
        payment_status = str(payment.get("status") or "").strip().lower()
        amount = _amount_native(task, payment)
        stale = status in {"stale_invalid", "abandoned"}
        if payment_status in {"verified", "paid", "settled"}:
            verified_payment += 1
            verified_native += amount
        elif not stale and (payment_status == "awaiting_payment" or status == "awaiting_payment"):
            awaiting_payment += 1
            unsettled_native += amount
        if status == "delivered" and payment_status not in {"verified", "paid", "settled"}:
            unpaid_delivered += 1

    return {
        "total": len(tasks),
        "by_status": by_status,
        "awaiting_payment": awaiting_payment,
        "verified_payment": verified_payment,
        "unpaid_delivered": unpaid_delivered,
        "unsettled_native": round(unsettled_native, 6),
        "verified_native": round(verified_native, 6),
        "settlement_leakage_ratio": round(unpaid_delivered / max(1, len(tasks)), 4),
    }


def _product_flow(products: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_status: Dict[str, int] = {}
    sellable_now = 0
    machine_sellable = 0
    approval_blocked = 0
    machine_exchange_ready = 0
    for product in products:
        status = str(product.get("status") or "unknown").strip() or "unknown"
        by_status[status] = by_status.get(status, 0) + 1
        if product.get("sellable_now"):
            sellable_now += 1
        channels = set(str(item) for item in (product.get("sellable_channels") or []))
        if "machine_readable_agent_endpoint" in channels:
            machine_sellable += 1
        if product.get("outreach_blocked_by_approval"):
            approval_blocked += 1
        if isinstance(product.get("machine_exchange"), dict):
            machine_exchange_ready += 1
    return {
        "total": len(products),
        "by_status": by_status,
        "sellable_now": sellable_now,
        "machine_sellable": machine_sellable,
        "approval_blocked": approval_blocked,
        "machine_exchange_ready": machine_exchange_ready,
        "human_adapter_ratio": round(approval_blocked / max(1, len(products)), 4),
    }


def _pattern_flow(entries: List[Dict[str, Any]], *, paid_packs: List[Dict[str, Any]]) -> Dict[str, Any]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        key = _pattern_key(entry)
        grouped.setdefault(key, []).append(entry)
    groups = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    top_key, top_entries = groups[0] if groups else ("", [])
    high_value_count = sum(1 for _, group in groups if len(group) >= 2)
    total = len(entries)
    return {
        "truth_ledger_successes": total,
        "pattern_groups": len(groups),
        "high_value_patterns": high_value_count,
        "paid_pack_count": len(paid_packs),
        "top_pattern_key": top_key,
        "top_pattern_count": len(top_entries),
        "repetition_dominance": round(len(top_entries) / max(1, total), 4),
    }


def _module_flow(modules: List[Dict[str, Any]]) -> Dict[str, Any]:
    canonical_keys = {
        str(item.get("canonical_pattern_key") or "").strip()
        for item in modules
        if str(item.get("canonical_pattern_key") or "").strip()
    }
    fallback_slots = {
        str(item.get("pain_type") or "unknown").strip() or "unknown"
        for item in modules
    }
    canonical_slots = len(canonical_keys) if canonical_keys else len(fallback_slots)
    overmint = max(0, len(modules) - canonical_slots)
    return {
        "module_count": len(modules),
        "canonical_slots": canonical_slots,
        "canonical_module_count": len(canonical_keys),
        "overmint_count": overmint,
        "overmint_pressure": round(overmint / max(1, len(modules)), 4),
    }


def _viability_score(
    *,
    task_stats: Dict[str, Any],
    product_stats: Dict[str, Any],
    pattern_stats: Dict[str, Any],
    module_stats: Dict[str, Any],
) -> Dict[str, Any]:
    product_score = min(1.0, float(product_stats.get("machine_sellable") or 0) / 3.0)
    pattern_score = min(1.0, float(pattern_stats.get("high_value_patterns") or 0) / 3.0)
    settlement_score = min(
        1.0,
        (
            float(task_stats.get("verified_payment") or 0)
            + 0.35 * float(task_stats.get("awaiting_payment") or 0)
        )
        / max(1.0, float(task_stats.get("total") or 1)),
    )
    pack_score = min(1.0, float(pattern_stats.get("paid_pack_count") or 0) / 2.0)
    leakage_penalty = min(0.35, float(task_stats.get("settlement_leakage_ratio") or 0.0) * 0.6)
    overmint_penalty = min(0.3, float(module_stats.get("overmint_pressure") or 0.0) * 0.3)
    human_adapter_penalty = min(0.2, float(product_stats.get("human_adapter_ratio") or 0.0) * 0.2)
    score = _clamp(
        0.25 * product_score
        + 0.25 * pattern_score
        + 0.2 * settlement_score
        + 0.2 * pack_score
        + 0.1
        - leakage_penalty
        - overmint_penalty
        - human_adapter_penalty
    )
    if score >= 0.75:
        tier = "compounding"
    elif score >= 0.5:
        tier = "carrying"
    elif score >= 0.25:
        tier = "experimental"
    else:
        tier = "starving"
    return {
        "carrying_score": round(score, 4),
        "tier": tier,
        "settlement_score": round(settlement_score, 4),
        "product_score": round(product_score, 4),
        "pattern_score": round(pattern_score, 4),
        "pack_score": round(pack_score, 4),
        "penalties": {
            "settlement_leakage": round(leakage_penalty, 4),
            "module_overmint": round(overmint_penalty, 4),
            "human_adapter": round(human_adapter_penalty, 4),
        },
    }


def _next_actions(
    *,
    task_stats: Dict[str, Any],
    product_stats: Dict[str, Any],
    pattern_stats: Dict[str, Any],
    module_stats: Dict[str, Any],
) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []
    if float(module_stats.get("overmint_pressure") or 0.0) >= 0.4:
        actions.append(
            {
                "action": "compress_repeated_modules",
                "reason": "repeated evidence is becoming new files instead of strengthening canonical capabilities",
            }
        )
    if int(task_stats.get("unpaid_delivered") or 0) > 0:
        actions.append(
            {
                "action": "settle_or_close_unpaid_delivered_work",
                "reason": "delivered work without verified settlement leaks carrying capacity",
            }
        )
    if int(product_stats.get("machine_exchange_ready") or 0) < int(product_stats.get("sellable_now") or 0):
        actions.append(
            {
                "action": "attach_machine_exchange_contracts",
                "reason": "sellable products should expose settlement-first machine contracts",
            }
        )
    if int(pattern_stats.get("high_value_patterns") or 0) > 0:
        actions.append(
            {
                "action": "route_demand_to_canonical_patterns",
                "reason": "known repeated patterns should absorb demand before new lead/product minting",
            }
        )
    if not actions:
        actions.append(
            {
                "action": "find_verified_transition_demand",
                "reason": "increase carrying capacity with one settled, measurable state transition",
            }
        )
    return actions[:5]


def _amount_native(task: Dict[str, Any], payment: Dict[str, Any]) -> float:
    candidates = [
        task.get("budget_native"),
        payment.get("amount_native"),
        ((task.get("payment_allocation") or {}).get("amount_native") if isinstance(task.get("payment_allocation"), dict) else None),
    ]
    for item in candidates:
        try:
            return max(0.0, float(item))
        except (TypeError, ValueError):
            continue
    return 0.0


def _pattern_key(entry: Dict[str, Any]) -> str:
    pain_type = str(entry.get("pain_type") or "self_improvement").strip() or "self_improvement"
    signature = (
        str(entry.get("solution_title") or "").strip()
        or str(entry.get("solution_id") or "").strip()
        or " ".join(str(entry.get("task") or "").split()[:10])
        or pain_type
    )
    return f"{pain_type}:{_slug(signature)[:72] or 'general'}"


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    out = []
    last_dash = False
    for ch in text:
        if ch.isalnum():
            out.append(ch)
            last_dash = False
        elif not last_dash:
            out.append("-")
            last_dash = True
    return "".join(out).strip("-")
