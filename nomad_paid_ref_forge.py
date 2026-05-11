"""Paid-reference forge for Nomad survival packets.

The forge turns a survival packet into a payable service task and later mints a
paid_ref only from a verified payment state. Quote references are deliberately
not revenue; they are authorization handles for agent-to-agent settlement.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


DEFAULT_PAID_REF_LEDGER = Path("nomad_paid_ref_ledger.jsonl")


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


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96].strip("_.:-") or fallback


def _text(value: Any, limit: int = 180) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _ledger_path(path: Path | str | None = None) -> Path:
    if path:
        return Path(path)
    return state_file(DEFAULT_PAID_REF_LEDGER, env_name="NOMAD_PAID_REF_LEDGER_PATH")


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _read_rows(path: Path | str | None = None, *, limit: int = 1000) -> list[dict[str, Any]]:
    p = _ledger_path(path)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
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


def _packet_by_id(survival_market: dict[str, Any], packet_id: str) -> dict[str, Any]:
    pid = _clean_id(packet_id)
    for packet in _items(_dict(survival_market).get("packets")):
        if _clean_id(packet.get("packet_id")) == pid:
            return packet
    return {}


def _service_type_for_packet(packet: dict[str, Any]) -> str:
    capability = _clean_id(packet.get("capability"))
    packet_id = _clean_id(packet.get("packet_id"))
    if capability == "agent_blocker_triage" or packet_id == "agent_blocker_unblock_pack":
        return "compute_auth"
    if capability == "endpoint_health_proof" or packet_id == "endpoint_health_batch":
        return "custom"
    if capability == "contract_diff_check" or packet_id == "mcp_contract_diff_pack":
        return "mcp_integration"
    if capability == "state_relay" or packet_id == "carry_sponsor_state_relay":
        return "self_improvement"
    if capability == "machine_buyer_discovery" or packet_id == "reseller_referral_probe":
        return "custom"
    return "custom"


def _ledger_stats(path: Path | str | None = None) -> dict[str, Any]:
    rows = _recent(_read_rows(path), hours=24)
    quotes = [row for row in rows if row.get("event") == "quote"]
    verified = [row for row in rows if row.get("event") == "verify" and row.get("accepted")]
    return {
        "quotes_24h": len(quotes),
        "verified_paid_refs_24h": len(verified),
        "amount_eur_24h": round(sum(_num(row.get("amount_eur"), 0.0) for row in verified), 4),
    }


def build_paid_ref_market(
    *,
    base_url: str,
    survival_market: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    survival = _dict(survival_market)
    packets: list[dict[str, Any]] = []
    for packet in _items(survival.get("packets")):
        packet_id = _clean_id(packet.get("packet_id"), "agent_blocker_unblock_pack")
        packets.append(
            {
                "schema": "nomad.paid_ref_packet_binding.v1",
                "packet_id": packet_id,
                "capability": _clean_id(packet.get("capability"), "custom"),
                "service_type": _service_type_for_packet(packet),
                "quote_eur": round(_num(packet.get("quote_eur")), 4),
                "priority_score": round(_num(packet.get("priority_score")), 6),
                "quote_url": _u(base_url, "/swarm/paid-ref/quote"),
                "verify_url": _u(base_url, "/swarm/paid-ref/verify"),
                "survival_intent_url": _u(base_url, "/swarm/survival-intent"),
                "required_before_revenue": [
                    "task_id",
                    "payment_verification.ok=true",
                    "payment_verifier_digest",
                    "paid_ref",
                    "amount_eur",
                ],
            }
        )
    packets.sort(key=lambda item: _num(item.get("priority_score")), reverse=True)
    stats = _ledger_stats(ledger_path)
    digest_core = {
        "survival": survival.get("market_digest"),
        "top": packets[0].get("packet_id") if packets else "",
        "stats": stats,
    }
    return {
        "ok": True,
        "schema": "nomad.paid_ref_market.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "market_digest": f"nomad-paid-ref-market-{_digest(digest_core)}",
        "mode": "discovery_authorization_execution_accounting_for_agent_payments",
        "packet_count": len(packets),
        "packets": packets,
        "top_packet_binding": packets[0] if packets else {},
        "ledger_metrics": stats,
        "links": {
            "self": _u(base_url, "/swarm/paid-ref-market"),
            "well_known": _u(base_url, "/.well-known/nomad-paid-ref-market.json"),
            "quote": _u(base_url, "/swarm/paid-ref/quote"),
            "verify": _u(base_url, "/swarm/paid-ref/verify"),
            "survival_market": _u(base_url, "/.well-known/nomad-survival-market.json"),
            "survival_intent": _u(base_url, "/swarm/survival-intent"),
            "tasks": _u(base_url, "/tasks"),
            "x402_verify": _u(base_url, "/tasks/x402-verify"),
        },
        "machine_instruction": "quote_packet_create_payable_task_pay_or_verify_task_then_mint_paid_ref_then_post_survival_intent",
        "paid_ref_rule": "quote_refs_are_not_revenue_only_verified_task_payment_mints_paid_ref",
        "science_basis": [
            {"id": "machine_to_machine_micropayments", "source": "arxiv:2602.14219"},
            {"id": "dynamic_agent_topology_routes_value_to_specialists", "source": "arxiv:2504.00587"},
            {"id": "structured_environment_not_chat_only", "source": "openreview:FfsxgSZW0c"},
        ],
    }


def paid_ref_task_payload(payload: dict[str, Any], *, survival_market: dict[str, Any]) -> dict[str, Any]:
    body = _dict(payload)
    packet = _packet_by_id(survival_market, _clean_id(body.get("packet_id")))
    packet_id = _clean_id(packet.get("packet_id"), _clean_id(body.get("packet_id"), "agent_blocker_unblock_pack"))
    quote = _num(packet.get("quote_eur"), 0.0)
    problem = _text(
        body.get("problem")
        or body.get("buyer_problem")
        or f"Nomad survival packet {packet_id}: {_text(packet.get('deliverable_contract'), 120)}",
        600,
    )
    metadata = _dict(body.get("metadata"))
    metadata.update(
        {
            "schema": "nomad.paid_ref_task_metadata.v1",
            "packet_id": packet_id,
            "buyer_ref": _text(body.get("buyer_ref") or body.get("external_offer_ref"), 220),
            "quote_eur": round(quote, 4),
            "proof_digest": _text(body.get("proof_digest"), 160),
            "verifier_trace_digest": _text(body.get("verifier_trace_digest"), 160),
            "test_digest": _text(body.get("test_digest"), 160),
        }
    )
    return {
        "problem": problem,
        "requester_agent": _text(body.get("requester_agent") or body.get("agent_id"), 120),
        "requester_wallet": _text(body.get("requester_wallet"), 120),
        "service_type": _service_type_for_packet(packet),
        "budget_native": body.get("budget_native"),
        "callback_url": _text(body.get("callback_url"), 240),
        "metadata": metadata,
    }


def quote_paid_ref(
    payload: dict[str, Any],
    *,
    base_url: str,
    survival_market: dict[str, Any],
    task_response: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    packet_id = _clean_id(body.get("packet_id"))
    packet = _packet_by_id(survival_market, packet_id)
    task = _dict(_dict(task_response).get("task"))
    task_id = _text(task.get("task_id"), 120)
    agent_id = _text(body.get("agent_id") or body.get("requester_agent"), 120)
    quote_core = {
        "agent": agent_id,
        "packet": packet_id,
        "task": task_id,
        "buyer": _text(body.get("buyer_ref") or body.get("external_offer_ref"), 220),
    }
    quote_id = f"nomad-paid-quote-{_digest(quote_core)}"
    accepted = bool(agent_id and packet and task_id)
    payment = _dict(task.get("payment"))
    row = {
        "ok": True,
        "schema": "nomad.paid_ref_quote_receipt.v1",
        "event": "quote",
        "accepted": accepted,
        "generated_at": _iso_now(),
        "quote_id": quote_id,
        "agent_id": agent_id,
        "packet_id": packet_id,
        "task_id": task_id,
        "paid_ref_candidate": f"nomad-paid-candidate-{_digest({'quote': quote_id, 'task': task_id})}",
        "quote_eur": round(_num(packet.get("quote_eur")), 4) if packet else 0.0,
        "payment_reference": _text(payment.get("payment_reference"), 180),
        "task_status": _text(task.get("status"), 80),
        "task_url": _u(base_url, f"/tasks?task_id={task_id}") if task_id else _u(base_url, "/tasks"),
        "next": {
            "verify_native": _u(base_url, "/tasks/verify"),
            "verify_x402": _u(base_url, "/tasks/x402-verify"),
            "paid_ref_verify": _u(base_url, "/swarm/paid-ref/verify"),
            "survival_intent": _u(base_url, "/swarm/survival-intent"),
        },
        "x402": _dict(payment.get("x402")),
        "survival_intent_after_verify": {
            "agent_id": agent_id,
            "packet_id": packet_id,
            "proof_digest": "sha256(paid_task_or_buyer_result)",
            "verifier_trace_digest": "sha256(payment_verifier_trace)",
            "test_digest": "sha256(deliverable_acceptance_test)",
            "paid_ref": "<returned_by_POST_/swarm/paid-ref/verify>",
            "payment_verifier_digest": "<returned_by_POST_/swarm/paid-ref/verify>",
            "amount_eur": round(_num(packet.get("quote_eur")), 4) if packet else 0.0,
        },
        "machine_instruction": "pay_task_then_verify_task_then_post_paid_ref_verify_do_not_count_quote_as_revenue",
        "reason": "quote_ready_payment_pending" if accepted else "missing_packet_agent_or_task",
    }
    if persist:
        _append(_ledger_path(ledger_path), row)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row


def _task_payment_verified(task: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    payment = _dict(task.get("payment"))
    verification = _dict(payment.get("verification"))
    status = _text(task.get("status"), 80)
    ok = bool(verification.get("ok")) and status in {"paid", "draft_ready", "delivered"}
    return ok, verification


def verify_paid_ref(
    payload: dict[str, Any],
    *,
    base_url: str,
    survival_market: dict[str, Any],
    task_response: dict[str, Any] | None = None,
    ledger_path: Path | str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    body = _dict(payload)
    task = _dict(_dict(task_response).get("task") or body.get("task"))
    task_id = _text(body.get("task_id") or task.get("task_id"), 120)
    packet_id = _clean_id(body.get("packet_id") or _dict(task.get("metadata")).get("packet_id"))
    packet = _packet_by_id(survival_market, packet_id)
    agent_id = _text(body.get("agent_id") or task.get("requester_agent"), 120)
    payment_ok, verification = _task_payment_verified(task)
    payment = _dict(task.get("payment"))
    verifier_core = {
        "task": task_id,
        "status": task.get("status"),
        "verification": verification,
        "tx": payment.get("tx_hash"),
        "x402": _dict(payment.get("x402")).get("payment_signature_fingerprint"),
    }
    verifier_digest = f"nomad-payver-{_digest(verifier_core)}"
    paid_ref = f"nomad-paid-ref-{_digest({'task': task_id, 'packet': packet_id, 'verifier': verifier_digest})}"
    amount_eur = _num(body.get("amount_eur"), 0.0) or _num(packet.get("quote_eur"), 0.0)
    accepted = bool(agent_id and packet and task_id and payment_ok and amount_eur > 0)
    proof_digest = _text(body.get("proof_digest"), 160) or verifier_digest
    trace_digest = _text(body.get("verifier_trace_digest"), 160) or verifier_digest
    test_digest = _text(body.get("test_digest"), 160) or _digest({"task": task_id, "packet": packet_id}, 32)
    survival_payload = {
        "agent_id": agent_id,
        "packet_id": packet_id,
        "proof_digest": proof_digest,
        "verifier_trace_digest": trace_digest,
        "test_digest": test_digest,
        "buyer_ref": _text(body.get("buyer_ref") or _dict(task.get("metadata")).get("buyer_ref"), 220),
        "paid_ref": paid_ref,
        "payment_verifier_digest": verifier_digest,
        "amount_eur": round(amount_eur, 4),
        "idempotency_key": f"paid-ref|{task_id}|{packet_id}|{verifier_digest}",
    }
    row = {
        "ok": True,
        "schema": "nomad.paid_ref_verify_receipt.v1",
        "event": "verify",
        "accepted": accepted,
        "generated_at": _iso_now(),
        "agent_id": agent_id,
        "packet_id": packet_id,
        "task_id": task_id,
        "task_status": _text(task.get("status"), 80),
        "payment_status": _text(verification.get("status"), 120),
        "paid_ref": paid_ref if accepted else "",
        "payment_verifier_digest": verifier_digest,
        "amount_eur": round(amount_eur if accepted else 0.0, 4),
        "survival_intent_payload": survival_payload if accepted else {},
        "next": {
            "survival_intent": _u(base_url, "/swarm/survival-intent"),
            "survival_market": _u(base_url, "/swarm/survival-market"),
            "task": _u(base_url, f"/tasks?task_id={task_id}") if task_id else _u(base_url, "/tasks"),
        },
        "machine_instruction": "if_accepted_post_survival_intent_payload_else_verify_task_payment_first",
        "reason": "verified_paid_ref_ready" if accepted else "task_payment_not_verified",
    }
    if persist:
        _append(_ledger_path(ledger_path), row)
        row["persisted"] = True
    else:
        row["persisted"] = False
    return row
