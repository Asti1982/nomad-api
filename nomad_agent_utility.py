"""Agent-native utility pressure for Nomad.

This layer is deliberately not a human marketplace. It records secret-free
problem packets from external agents, exposes the resulting bounded work seeds,
and only writes utility receipts when another agent supplies a downstream proof
or callback verifier that the Nomad output was actually consumed.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_reliability_doctor import build_reliability_doctor_intake
from nomad_revenue_settlement import evaluate_revenue_settlement_hook
from nomad_state_paths import state_file


SCHEMA = "nomad.agent_utility.v1"
INTAKE_SCHEMA = "nomad.agent_utility_intake.v1"
REQUEST_SCHEMA = "nomad.agent_utility_request.v1"
RECEIPT_SCHEMA = "nomad.agent_utility_receipt.v1"
LEDGER_ENV = "NOMAD_AGENT_UTILITY_LEDGER_PATH"
DEFAULT_LEDGER = Path("nomad_agent_utility_ledger.jsonl")
MAX_LEDGER_LINES = 8000
MAX_RECENT = 80

REQUIRED_FIELDS = (
    "agent_id",
    "agent_runtime",
    "failure_class",
    "problem_digest",
    "desired_outcome",
    "proof_contract",
)
FORBIDDEN_KEY_TERMS = ("private_key", "seed_phrase", "password", "credential", "api_key", "access_token", "secret")
FORBIDDEN_VALUE_TERMS = ("private_key", "seed phrase", "password:", "credential:", "bearer ", "secret=", "sk-", "ghp_")
ALLOWED_BOUNDARY_KEYS = {
    "secret_free",
    "secrets_free",
    "no_secret",
    "no_secrets",
    "secret_policy",
    "no_secret_attestation",
    "credentials_free",
    "no_credentials",
}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _ledger_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return state_file(DEFAULT_LEDGER, env_name=LEDGER_ENV)


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


def _text(value: Any, limit: int = 320) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:160].strip("_.:/#-") or fallback


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on", "ok", "accepted", "confirmed", "consumed"}


def _digest(value: Any, length: int = 32) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return ""


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


def _read_rows(path: Path | str | None = None, *, limit_lines: int = MAX_LEDGER_LINES) -> list[dict[str, Any]]:
    ledger = _ledger_path(path)
    if not ledger.exists():
        return []
    lines = ledger.read_text(encoding="utf-8", errors="replace").splitlines()
    rows: list[dict[str, Any]] = []
    for line in lines[-max(1, min(len(lines), limit_lines)) :]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("schema") in {REQUEST_SCHEMA, RECEIPT_SCHEMA}:
            rows.append(row)
    return rows


def _append_row(row: dict[str, Any], *, ledger_path: Path | str | None = None, digest_key: str = "row_digest") -> dict[str, Any]:
    path = _ledger_path(ledger_path)
    idempotency_key = _text(row.get("idempotency_key"), 180)
    row_digest = _text(row.get(digest_key), 180)
    for existing in _read_rows(path):
        if idempotency_key and existing.get("idempotency_key") == idempotency_key:
            if existing.get(digest_key) != row_digest:
                return {
                    "ok": False,
                    "schema": "nomad.agent_utility_error.v1",
                    "error": "idempotency_key_conflict",
                    "message": "Idempotency key already exists for a different agent utility row.",
                }
            replay = dict(existing)
            replay["ok"] = True
            replay["idempotent_replay"] = True
            replay["ledger_path"] = str(path)
            return replay
    path.parent.mkdir(parents=True, exist_ok=True)
    path.open("a", encoding="utf-8").write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    out = dict(row)
    out["ok"] = True
    out["ledger_path"] = str(path)
    return out


def _public_problem(body: dict[str, Any]) -> dict[str, Any]:
    proof_contract = body.get("proof_contract")
    return {
        "agent_id": _text(body.get("agent_id"), 120),
        "agent_runtime": _clean_id(body.get("agent_runtime"), "external_agent"),
        "failure_class": _clean_id(body.get("failure_class"), "agent_utility_blocker"),
        "problem_digest": _text(body.get("problem_digest"), 220),
        "desired_outcome": _text(body.get("desired_outcome"), 420),
        "callback_url": _text(body.get("callback_url"), 500),
        "budget_signal": _text(body.get("budget_signal"), 120),
        "settlement_ref": _text(body.get("settlement_ref"), 220),
        "proof_contract": proof_contract if isinstance(proof_contract, dict) else _text(proof_contract, 500),
    }


def _receipt_evidence(body: dict[str, Any]) -> dict[str, Any]:
    callback = _dict(body.get("callback_verifier") or body.get("callback_receipt"))
    proof = _dict(body.get("proof"))
    downstream = _dict(body.get("downstream_proof") or body.get("consumer_proof"))
    nomad_proof_digest = _text(
        _first(
            body.get("nomad_proof_digest"),
            body.get("proof_digest"),
            proof.get("digest"),
            body.get("verifier_trace_digest"),
        ),
        220,
    )
    downstream_proof_digest = _text(
        _first(
            body.get("downstream_proof_digest"),
            body.get("consumer_proof_digest"),
            downstream.get("digest"),
            downstream.get("proof_digest"),
        ),
        220,
    )
    callback_verifier_digest = _text(
        _first(
            body.get("callback_verifier_digest"),
            callback.get("digest"),
            callback.get("verifier_trace_digest"),
            callback.get("proof_digest"),
        ),
        220,
    )
    callback_confirmed = _truthy(
        _first(
            body.get("callback_confirmed"),
            body.get("consumer_confirmed"),
            callback.get("accepted"),
            callback.get("ok"),
            callback.get("consumed"),
        )
    )
    consumer_agent_id = _text(
        _first(body.get("consumer_agent_id"), body.get("consumed_by_agent_id"), callback.get("agent_id")),
        120,
    )
    basis = []
    if nomad_proof_digest:
        basis.append("nomad_proof_digest")
    if downstream_proof_digest:
        basis.append("downstream_proof_digest")
    if callback_verifier_digest:
        basis.append("callback_verifier_digest")
    if callback_confirmed:
        basis.append("callback_confirmed")
    consumed = bool(nomad_proof_digest and (downstream_proof_digest or callback_verifier_digest or callback_confirmed))
    return {
        "nomad_proof_digest": nomad_proof_digest,
        "downstream_proof_digest": downstream_proof_digest,
        "callback_verifier_digest": callback_verifier_digest,
        "callback_confirmed": callback_confirmed,
        "consumer_agent_id": consumer_agent_id,
        "basis": basis,
        "consumed": consumed,
        "proof_density": round(
            min(
                1.0,
                max(
                    _num(body.get("proof_density")),
                    0.35 * bool(nomad_proof_digest)
                    + 0.35 * bool(downstream_proof_digest)
                    + 0.20 * bool(callback_verifier_digest)
                    + 0.10 * bool(callback_confirmed),
                ),
            ),
            4,
        ),
    }


def summarize_agent_utility_ledger(
    *,
    ledger_path: Path | str | None = None,
    limit: int = MAX_LEDGER_LINES,
    recent_limit: int = MAX_RECENT,
) -> dict[str, Any]:
    rows = _read_rows(ledger_path, limit_lines=limit)
    requests = [row for row in rows if row.get("schema") == REQUEST_SCHEMA]
    receipts = [row for row in rows if row.get("schema") == RECEIPT_SCHEMA]
    receipt_request_ids = {str(row.get("utility_request_id") or "") for row in receipts}
    pending = [row for row in requests if str(row.get("utility_request_id") or "") not in receipt_request_ids]
    agent_ids = {str(row.get("agent_id") or "") for row in requests if row.get("agent_id")}
    consumers = {str(row.get("consumer_agent_id") or "") for row in receipts if row.get("consumer_agent_id")}
    requests.sort(key=lambda row: str(row.get("generated_at") or ""), reverse=True)
    receipts.sort(key=lambda row: str(row.get("generated_at") or ""), reverse=True)
    pending.sort(key=lambda row: str(row.get("generated_at") or ""), reverse=True)
    return {
        "schema": "nomad.agent_utility_summary.v1",
        "generated_at": _iso_now(),
        "ledger_path": str(_ledger_path(ledger_path)),
        "request_count": len(requests),
        "utility_receipt_count": len(receipts),
        "pending_request_count": len(pending),
        "agent_requester_count": len(agent_ids),
        "consumer_agent_count": len(consumers),
        "latest_requests": requests[:recent_limit],
        "pending_requests": pending[:recent_limit],
        "recent_receipts": receipts[:recent_limit],
    }


def utility_pressure_snapshot(*, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    data = _dict(summary) if summary is not None else summarize_agent_utility_ledger()
    request_count = int(data.get("request_count") or 0)
    receipt_count = int(data.get("utility_receipt_count") or 0)
    pending_count = int(data.get("pending_request_count") or 0)
    consumer_count = int(data.get("consumer_agent_count") or 0)
    demand_presence = min(1.0, request_count / 6.0)
    receipt_proximity = min(
        1.0,
        0.50 * (1 if receipt_count else 0)
        + min(0.25, receipt_count / 16.0)
        + min(0.15, consumer_count / 10.0)
        + min(0.10, max(0, request_count - pending_count) / 12.0),
    )
    absence_pressure = max(0.0, 1.0 - receipt_proximity)
    demand_gap = max(0.0, 1.0 - demand_presence)
    return {
        "schema": "nomad.agent_utility_pressure_snapshot.v1",
        "request_count": request_count,
        "utility_receipt_count": receipt_count,
        "pending_request_count": pending_count,
        "consumer_agent_count": consumer_count,
        "agent_utility_demand_presence": round(demand_presence, 4),
        "agent_utility_proximity": round(receipt_proximity, 4),
        "agent_utility_absence_pressure": round(absence_pressure, 4),
        "agent_utility_demand_gap": round(demand_gap, 4),
        "agent_utility_router_pressure": round(max(absence_pressure, demand_gap), 4),
        "retention_signal": "starving" if receipt_count == 0 else "growing",
    }


def _worker_job_seed(problem: dict[str, Any], *, base_url: str, utility_request_id: str) -> dict[str, Any]:
    return {
        "schema": "nomad.worker_job.v1",
        "job_id": f"nomad-agent-utility-job-{_digest({'request': utility_request_id}, 22)}",
        "job_type": "agent_utility_repair",
        "title": f"Return consumable proof for {problem['failure_class']}",
        "priority_score": 1.24,
        "worker_role": "transition_worker",
        "channel_id": "external_agent_utility",
        "source_ref": problem["problem_digest"],
        "external_id": utility_request_id,
        "read_only": False,
        "executable_now": True,
        "side_effect_class": "nomad_contract_endpoints_only",
        "allowed_actions": [
            "read_public_problem_digest",
            "derive_smallest_nomad_proof_or_patch",
            "return_nomad_proof_digest",
            "ask_consumer_agent_for_downstream_proof_or_callback_verifier",
        ],
        "blocked_actions": [
            "ask_for_or_store_secrets",
            "claim_paid_receipt_without_payment",
            "public_human_marketing_action",
            "unbounded_compute_or_external_mutation",
        ],
        "required_artifacts": [
            "nomad_proof_digest",
            "verifier_trace_digest",
            "consumer_agent_id_or_callback_verifier",
            "downstream_proof_digest_or_callback_verifier_digest",
        ],
        "verifier": {
            "type": "external_agent_consumption_gate",
            "inputs": ["nomad_proof_digest", "downstream_proof_digest", "callback_verifier_digest"],
            "pass_condition": "utility_receipt requires Nomad proof plus downstream proof or accepted callback verifier",
        },
        "settlement_path": {
            "stage": "utility_only_until_paid_proof",
            "post_url": _u(base_url, "/swarm/agent-utility/intake"),
            "paid_guard": "no_revenue_without_paid_stage_positive_amount_public_settlement_ref",
        },
        "gate_state": {"utility_request_id": utility_request_id, "agent_runtime": problem["agent_runtime"]},
        "stop_conditions": [
            "problem_digest_unreproducible",
            "consumer_agent_refuses_callback",
            "proof_contract_missing",
            "payment_claim_without_receipt",
        ],
        "return_url": _u(base_url, "/swarm/agent-utility/intake"),
        "machine_instruction": "solve_only_enough_to_emit_consumable_proof_then_request_downstream_receipt",
    }


def build_agent_utility_surface(*, base_url: str = "", ledger_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = _dict(ledger_summary) if ledger_summary is not None else summarize_agent_utility_ledger()
    pressure = utility_pressure_snapshot(summary=summary)
    root = (base_url or "").strip().rstrip("/")
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "read_url": _u(root, "/swarm/agent-utility"),
        "well_known_url": _u(root, "/.well-known/nomad-agent-utility.json"),
        "objective": "external_agent_utility_router",
        "accepted_packet": {
            "schema": "nomad.agent_utility_packet.v1",
            "post_url": _u(root, "/swarm/agent-utility/intake"),
            "required_fields": list(REQUIRED_FIELDS),
            "optional_fields": [
                "callback_url",
                "budget_signal",
                "settlement_ref",
                "nomad_proof_digest",
                "downstream_proof_digest",
                "callback_verifier_digest",
                "consumer_agent_id",
            ],
            "secret_policy": "public_digests_and_callbacks_only_no_tokens_keys_passwords_private_logs",
        },
        "utility_receipt_gate": {
            "receipt_schema": RECEIPT_SCHEMA,
            "counts_as_revenue": False,
            "required_for_receipt": ["nomad_proof_digest", "downstream_proof_digest or callback_verifier_digest or callback_confirmed"],
            "paid_receipts": "delegated_to_nomad_revenue_settlement_only_when_paid_stage_positive_amount_and_settlement_ref_exist",
        },
        "pressure": pressure,
        "summary": {
            "request_count": summary.get("request_count", 0),
            "utility_receipt_count": summary.get("utility_receipt_count", 0),
            "pending_request_count": summary.get("pending_request_count", 0),
            "agent_requester_count": summary.get("agent_requester_count", 0),
            "consumer_agent_count": summary.get("consumer_agent_count", 0),
            "pending_requests": summary.get("pending_requests", [])[:12],
            "recent_receipts": summary.get("recent_receipts", [])[:12],
        },
        "links": {
            "self": _u(root, "/.well-known/nomad-agent-utility.json"),
            "intake": _u(root, "/swarm/agent-utility/intake"),
            "receipts": _u(root, "/swarm/agent-utility/receipts"),
            "gradient": _u(root, "/swarm/gradient"),
            "agent_requests": _u(root, "/.well-known/nomad-agent-requests.json"),
            "worker_job_queue": _u(root, "/.well-known/nomad-worker-job-queue.json"),
            "value_cycles": _u(root, "/.well-known/nomad-value-cycles.json"),
            "reliability_doctor": _u(root, "/.well-known/nomad-agent-reliability-doctor.json"),
            "revenue_settlement": _u(root, "/.well-known/nomad-revenue-settlement.json"),
        },
        "machine_instruction": "external_agents_post_secret_free_problem_packets; nomad_records_utility_only_after_downstream_proof_or_callback_verifier",
    }


def build_agent_utility_receipts_surface(*, base_url: str = "", ledger_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = _dict(ledger_summary) if ledger_summary is not None else summarize_agent_utility_ledger()
    return {
        "ok": True,
        "schema": "nomad.agent_utility_receipts_surface.v1",
        "generated_at": _iso_now(),
        "read_url": _u(base_url, "/swarm/agent-utility/receipts"),
        "well_known_url": _u(base_url, "/.well-known/nomad-agent-utility.json"),
        "pressure": utility_pressure_snapshot(summary=summary),
        "summary": summary,
        "links": {
            "agent_utility": _u(base_url, "/.well-known/nomad-agent-utility.json"),
            "intake": _u(base_url, "/swarm/agent-utility/intake"),
            "gradient": _u(base_url, "/swarm/gradient"),
        },
        "machine_instruction": "treat_utility_receipts_as_non_cash_selection_pressure_not_revenue",
    }


def evaluate_agent_utility_intake(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    record: bool = True,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    if _contains_forbidden(body):
        return {
            "ok": False,
            "accepted": False,
            "schema": "nomad.agent_utility_intake_error.v1",
            "error": "secret_shaped_payload",
            "message": "Agent utility intake accepts public digests and callback verifiers only.",
            "generated_at": _iso_now(),
        }
    missing = [field for field in REQUIRED_FIELDS if body.get(field) in (None, "", [], {})]
    if missing:
        return {
            "ok": False,
            "accepted": False,
            "schema": "nomad.agent_utility_intake_error.v1",
            "error": "required_fields_missing",
            "missing_fields": missing,
            "message": "Send a machine-readable agent utility packet with all required fields.",
            "generated_at": _iso_now(),
        }

    now = _iso_now()
    problem = _public_problem(body)
    core = {
        "agent_id": problem["agent_id"],
        "agent_runtime": problem["agent_runtime"],
        "failure_class": problem["failure_class"],
        "problem_digest": problem["problem_digest"],
        "desired_outcome": problem["desired_outcome"],
        "proof_contract": problem["proof_contract"],
    }
    request_digest = f"agent-utility-request-{_digest(core, 40)}"
    idempotency_key = _text(body.get("idempotency_key") or body.get("client_request_id") or request_digest, 180)
    utility_request_id = f"utility-{_digest(idempotency_key or core, 24)}"
    request_row = {
        "schema": REQUEST_SCHEMA,
        "generated_at": now,
        "utility_request_id": utility_request_id,
        "idempotency_key": idempotency_key,
        "request_digest": request_digest,
        **problem,
        "objective": "external_agent_utility_router",
        "counts_as_revenue": False,
    }
    recorded_request = (
        _append_row(request_row, ledger_path=ledger_path, digest_key="request_digest")
        if record
        else {**request_row, "ok": True, "dry_run": True}
    )
    if not recorded_request.get("ok"):
        return {**recorded_request, "accepted": False, "generated_at": now}

    evidence = _receipt_evidence(body)
    receipt_recorded: dict[str, Any] = {
        "ok": False,
        "skipped": True,
        "reason": "downstream_proof_or_callback_verifier_missing",
        "gate": evidence,
    }
    if evidence["consumed"]:
        receipt_core = {
            "utility_request_id": utility_request_id,
            "agent_id": problem["agent_id"],
            "problem_digest": problem["problem_digest"],
            "nomad_proof_digest": evidence["nomad_proof_digest"],
            "downstream_proof_digest": evidence["downstream_proof_digest"],
            "callback_verifier_digest": evidence["callback_verifier_digest"],
            "consumer_agent_id": evidence["consumer_agent_id"],
        }
        receipt_digest = f"agent-utility-receipt-{_digest(receipt_core, 40)}"
        receipt_row = {
            "schema": RECEIPT_SCHEMA,
            "generated_at": now,
            "utility_receipt_id": f"utility-receipt-{_digest(receipt_digest, 24)}",
            "utility_request_id": utility_request_id,
            "idempotency_key": _text(body.get("utility_receipt_idempotency_key") or receipt_digest, 180),
            "receipt_digest": receipt_digest,
            "receipt_type": "utility_receipt",
            "agent_id": problem["agent_id"],
            "agent_runtime": problem["agent_runtime"],
            "failure_class": problem["failure_class"],
            "problem_digest": problem["problem_digest"],
            "desired_outcome": problem["desired_outcome"],
            "nomad_proof_digest": evidence["nomad_proof_digest"],
            "downstream_proof_digest": evidence["downstream_proof_digest"],
            "callback_verifier_digest": evidence["callback_verifier_digest"],
            "callback_confirmed": evidence["callback_confirmed"],
            "consumer_agent_id": evidence["consumer_agent_id"],
            "proof_density": evidence["proof_density"],
            "counts_as_revenue": False,
            "amount_usd": 0.0,
        }
        receipt_recorded = (
            _append_row(receipt_row, ledger_path=ledger_path, digest_key="receipt_digest")
            if record
            else {**receipt_row, "ok": True, "dry_run": True}
        )

    doctor_payload = {
        "requester_id": problem["agent_id"],
        "source": "agent_utility_intake",
        "service_type": "agent_utility_blocker",
        "problem": f"{problem['failure_class']}: {problem['desired_outcome']}",
        "log_digest": problem["problem_digest"],
        "accepted_compute_barter_terms": False,
        "evidence": [problem["problem_digest"], _text(problem["proof_contract"], 260)],
    }
    doctor_intake = build_reliability_doctor_intake(doctor_payload, base_url=base_url)
    worker_job = _worker_job_seed(problem, base_url=base_url, utility_request_id=utility_request_id)
    value_cycle_event_candidate = {
        "schema": "nomad.value_cycle_event_candidate.v1",
        "cycle_id": "external_agent_utility_cycle",
        "event_type": "agent_utility_request",
        "stage": "found",
        "agent_id": problem["agent_id"],
        "external_id": utility_request_id,
        "proof_digest": problem["problem_digest"],
        "work_type": "agent_utility",
        "counts_as_revenue": False,
        "post_url": _u(base_url, "/swarm/value-cycles/events"),
    }
    settlement = evaluate_revenue_settlement_hook(
        body,
        source_endpoint="/swarm/agent-utility/intake",
        base_url=base_url,
        record=record,
    )
    settlement_signal_present = bool(
        settlement.get("eligible_signal")
        or settlement.get("accepted")
        or _truthy(body.get("buyer_funded_packet"))
        or _truthy(body.get("buyer_funded"))
        or str(body.get("stage") or body.get("external_value_stage") or "").strip().lower() == "paid"
        or _num(body.get("amount_usd") or body.get("amount")) > 0.0
        or _text(body.get("settlement_ref") or body.get("tx_hash"), 120)
    )
    summary_after = summarize_agent_utility_ledger(ledger_path=ledger_path)
    return {
        "ok": True,
        "accepted": True,
        "schema": INTAKE_SCHEMA,
        "generated_at": now,
        "utility_request_id": utility_request_id,
        "recorded_request": recorded_request,
        "utility_receipt_gate": evidence,
        "utility_receipt_recorded": receipt_recorded,
        "worker_job_seed": worker_job,
        "value_cycle_event_candidate": value_cycle_event_candidate,
        "reliability_doctor_payload": doctor_payload,
        "reliability_doctor_intake": doctor_intake,
        "revenue_settlement_hook": settlement if settlement_signal_present else {"ok": True, "skipped": True, "reason": "no_paid_proof_signal"},
        "pressure_after": utility_pressure_snapshot(summary=summary_after),
        "next_ops": [
            {"op": "GET", "url": _u(base_url, "/.well-known/nomad-agent-utility.json"), "reason": "refresh_utility_contract"},
            {"op": "GET", "url": _u(base_url, "/.well-known/nomad-worker-job-queue.json"), "reason": "claim_seeded_worker_job"},
            {
                "op": "POST",
                "url": _u(base_url, "/swarm/agent-utility/intake"),
                "condition": "after_nomad_proof_is_consumed_by_downstream_agent",
                "payload_hint": {
                    "agent_id": problem["agent_id"],
                    "agent_runtime": problem["agent_runtime"],
                    "failure_class": problem["failure_class"],
                    "problem_digest": problem["problem_digest"],
                    "desired_outcome": problem["desired_outcome"],
                    "proof_contract": problem["proof_contract"],
                    "nomad_proof_digest": "{sha256:nomad-proof}",
                    "downstream_proof_digest": "{sha256:consumer-followproof}",
                },
            },
        ],
        "machine_instruction": "request_recorded; route_worker_to_emit_consumable_proof; write_utility_receipt_only_after_downstream_consumption",
    }
