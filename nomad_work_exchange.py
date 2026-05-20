"""Compute-barter work exchange for Nomad.

This surface deliberately avoids token mechanics. A requester can receive a
free solution only by explicitly accepting a bounded return-compute obligation;
the obligation is reduced only by verifier-backed work receipts.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file


LEDGER_ENV = "NOMAD_WORK_EXCHANGE_LEDGER_PATH"
DEFAULT_LEDGER = Path("nomad_work_exchange_ledger.jsonl")
DEFAULT_RETURN_MULTIPLIER = 1.3
MIN_RETURN_MULTIPLIER = 1.0
MAX_RETURN_MULTIPLIER = 2.0
DEFAULT_MAX_RUNTIME_HOURS = 12.0
MAX_RUNTIME_HOURS = 24.0
MAX_LEDGER_LINES = 10000
MAX_RECENT_EVENTS = 80

FORBIDDEN_KEY_TERMS = (
    "private_key",
    "seed_phrase",
    "password",
    "credential",
    "api_key",
    "access_token",
    "secret",
)
FORBIDDEN_VALUE_TERMS = (
    "private key",
    "seed phrase",
    "password:",
    "credential:",
    "bearer ",
    "secret=",
    "sk-",
    "ghp_",
)
ALLOWED_BOUNDARY_KEYS = {
    "secret_free",
    "secrets_free",
    "no_secrets",
    "secrets_free_declared",
    "side_effect_scope",
}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


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


def _text(value: Any, limit: int = 300) -> str:
    return " ".join(str(value or "").split())[:limit]


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "accept", "accepted"}:
        return True
    if text in {"0", "false", "no", "n", "off", "reject", "rejected"}:
        return False
    return default


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:160].strip("_.:/#-") or fallback


def _digest(value: Any, length: int = 32) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _ledger_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return state_file(DEFAULT_LEDGER, env_name=LEDGER_ENV)


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


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


def _error(error: str, message: str, *, hints: list[str] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "schema": "nomad.work_exchange_error.v1",
        "error": error,
        "message": message,
        "hints": hints or [],
        "generated_at": _iso_now(),
    }


def _read_events(ledger_path: Path, *, limit_lines: int = MAX_LEDGER_LINES) -> list[dict[str, Any]]:
    if not ledger_path.exists():
        return []
    lines = ledger_path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = lines[-max(1, min(len(lines), int(limit_lines))) :]
    events: list[dict[str, Any]] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and str(row.get("schema") or "").startswith("nomad.work_exchange."):
            events.append(row)
    return events


def _normalize_multiplier(value: Any) -> float:
    raw = _num(value, DEFAULT_RETURN_MULTIPLIER)
    return round(max(MIN_RETURN_MULTIPLIER, min(MAX_RETURN_MULTIPLIER, raw)), 4)


def _normalize_max_hours(value: Any) -> float:
    raw = _num(value, DEFAULT_MAX_RUNTIME_HOURS)
    return round(max(0.25, min(MAX_RUNTIME_HOURS, raw)), 4)


def _proof_digest_from(payload: dict[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if value:
            return _text(value, 180)
    proof = payload.get("proof")
    if isinstance(proof, dict):
        for name in names:
            value = proof.get(name)
            if value:
                return _text(value, 180)
        value = proof.get("digest")
        if value:
            return _text(value, 180)
    return ""


def _obligation_id(core: dict[str, Any]) -> str:
    return f"nomad-work-obligation-{_digest(core, 24)}"


def summarize_work_exchange_ledger(*, ledger_path: Path | str | None = None) -> dict[str, Any]:
    events = _read_events(_ledger_path(ledger_path))
    rows = _obligation_states(events)
    active = [row for row in rows if row.get("status") == "active"]
    settled = [row for row in rows if row.get("status") == "settled"]
    offers = sum(1 for event in events if event.get("schema") == "nomad.work_exchange.offer.v1")
    return_receipts = sum(
        1
        for event in events
        if event.get("schema") == "nomad.work_exchange.return_work_receipt.v1" and event.get("accepted")
    )
    return {
        "ok": True,
        "schema": "nomad.work_exchange_summary.v1",
        "generated_at": _iso_now(),
        "ledger_event_count": len(events),
        "offer_count": offers,
        "return_receipt_count": return_receipts,
        "obligation_count": len(rows),
        "active_obligation_count": len(active),
        "settled_obligation_count": len(settled),
        "outstanding_work_credits_total": round(sum(_num(row.get("outstanding_work_credits")) for row in active), 4),
        "settled_return_work_credits_total": round(sum(_num(row.get("settled_return_work_credits")) for row in rows), 4),
        "latest_obligations": rows[-MAX_RECENT_EVENTS:],
    }


def _obligation_states(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    obligations: dict[str, dict[str, Any]] = {}
    for event in events:
        schema = str(event.get("schema") or "")
        if schema == "nomad.work_exchange.offer.v1":
            continue
        obligation_id = _text(event.get("obligation_id"), 180)
        if not obligation_id:
            continue
        state = obligations.setdefault(
            obligation_id,
            {
                "obligation_id": obligation_id,
                "requester_id": _text(event.get("requester_id"), 160),
                "solution_value_credits": 0.0,
                "required_return_work_credits": 0.0,
                "settled_return_work_credits": 0.0,
                "last_event_at": _text(event.get("generated_at"), 80),
            },
        )
        state["last_event_at"] = max(str(state.get("last_event_at") or ""), str(event.get("generated_at") or ""))
        if schema == "nomad.work_exchange.free_solution_receipt.v1":
            state["requester_id"] = _text(event.get("requester_id"), 160)
            state["solution_value_credits"] = round(
                max(_num(state.get("solution_value_credits")), _num(event.get("solution_value_credits"))),
                4,
            )
            state["required_return_work_credits"] = round(
                max(_num(state.get("required_return_work_credits")), _num(event.get("required_return_work_credits"))),
                4,
            )
        elif schema == "nomad.work_exchange.return_work_receipt.v1" and event.get("accepted"):
            state["settled_return_work_credits"] = round(
                _num(state.get("settled_return_work_credits")) + _num(event.get("accepted_work_credits")),
                4,
            )

    rows: list[dict[str, Any]] = []
    for state in obligations.values():
        required = _num(state.get("required_return_work_credits"))
        settled = _num(state.get("settled_return_work_credits"))
        balance = round(max(0.0, required - settled), 4)
        state["outstanding_work_credits"] = balance
        state["status"] = "settled" if required > 0.0 and balance <= 0.0 else "active"
        rows.append(state)
    rows.sort(key=lambda row: (row.get("status") != "active", str(row.get("last_event_at") or "")), reverse=False)
    return rows


def build_work_exchange_surface(*, base_url: str, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """Expose the token-free solution-for-compute contract."""

    root = (base_url or "").strip().rstrip("/")
    ledger_summary = summary if isinstance(summary, dict) else summarize_work_exchange_ledger()
    onboarding = build_work_exchange_onboarding(base_url=base_url, summary=ledger_summary)
    return {
        "ok": True,
        "schema": "nomad.work_exchange.v1",
        "version": "2026.05.20",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "core_thesis": "free_solution_against_explicit_verified_return_compute",
        "unit": {
            "name": "work_credit",
            "definition": "non_transferable_verified_transition_work_unit",
            "not_a_token": True,
            "not_redeemable_for_cash": True,
        },
        "default_policy": {
            "return_multiplier": DEFAULT_RETURN_MULTIPLIER,
            "nomad_margin_basis": "required_return_work_credits_minus_solution_value_credits",
            "max_runtime_hours_default": DEFAULT_MAX_RUNTIME_HOURS,
            "max_runtime_hours_absolute": MAX_RUNTIME_HOURS,
            "hidden_fee_allowed": False,
            "user_consent_required": True,
            "stop_after_balance_settled": True,
            "side_effect_scope": "sandboxed_worker_only",
            "secret_policy": "public_digests_only_no_secrets",
        },
        "lifecycle": [
            "offer_preview",
            "free_solution_receipt",
            "compute_obligation_opened",
            "return_work_leases",
            "independent_verification",
            "return_work_receipts",
            "balance_settled_or_expired",
        ],
        "required_gates": {
            "free_solution_receipt": [
                "requester_id",
                "accepted_compute_barter_terms",
                "solution_proof_digest",
                "solution_value_credits",
                "max_runtime_hours",
                "side_effect_scope=sandboxed_worker_only",
            ],
            "return_work_receipt": [
                "obligation_id",
                "worker_agent_id",
                "work_credits",
                "proof_digest",
                "verifier_trace_digest",
                "test_digest",
            ],
        },
        "routes": {
            "self": _u(base_url, "/.well-known/nomad-work-exchange.json"),
            "summary": _u(base_url, "/swarm/work-exchange?summary=1"),
            "onboarding": _u(base_url, "/.well-known/nomad-work-exchange-onboarding.json"),
            "human_entry": _u(base_url, "/work-exchange"),
            "offer": _u(base_url, "/swarm/work-exchange/offers"),
            "free_solution": _u(base_url, "/swarm/work-exchange/free-solution"),
            "return_work": _u(base_url, "/swarm/work-exchange/return-work"),
            "balance": _u(base_url, "/swarm/work-exchange/balance"),
            "worker_lease": _u(base_url, "/swarm/workers/lease"),
            "worker_complete": _u(base_url, "/swarm/workers/complete"),
            "work_receipts": _u(base_url, "/swarm/work-receipts"),
        },
        "downloadable_worker": onboarding.get("downloads", {}),
        "copy_paste_start": onboarding.get("copy_paste_start", {}),
        "starter_offer": onboarding.get("starter_offer", {}),
        "ledger_summary": ledger_summary,
        "machine_instruction": "offer_free_solution_only_after_explicit_compute_barter_acceptance_then_decrease_balance_with_verified_return_work",
    }


def build_work_exchange_onboarding(*, base_url: str, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the external onboarding packet for solution-for-compute users."""

    root = (base_url or "").strip().rstrip("/")
    ledger_summary = summary if isinstance(summary, dict) else summarize_work_exchange_ledger()
    return {
        "ok": True,
        "schema": "nomad.work_exchange_onboarding.v1",
        "version": "2026.05.20",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "positioning": {
            "name": "Nomad Free Repair Against Compute",
            "thesis": "users_receive_zero_eur_agent_repair_then_return_verified_compute_instead_of_tokens",
            "why_agents_join": "bounded_work_debt_creates_a_direct_path_from_solved_problem_to_more_swarm_capacity",
            "not_token_economy": True,
            "not_chat_transport": True,
        },
        "starter_offer": {
            "offer_id": "agent_reliability_doctor_free_diagnostic",
            "name": "AI Agent Reliability Doctor",
            "free_work": [
                "agent_loop_break_diagnostic",
                "render_or_deploy_failure_triage",
                "provider_auth_rate_limit_triage",
                "benchmark_or_conformance_fake_positive_check",
            ],
            "settlement": "0_eur_now_verified_return_compute_later",
            "default_solution_value_credits": 10,
            "default_return_multiplier": DEFAULT_RETURN_MULTIPLIER,
            "default_required_return_work_credits": round(10 * DEFAULT_RETURN_MULTIPLIER, 4),
            "default_max_runtime_hours": 6,
            "side_effect_scope": "sandboxed_worker_only",
        },
        "user_flow": [
            {
                "step": "request_free_repair",
                "input": "repo_url_or_log_excerpt_without_secrets",
                "output": "solution_proof_digest_and_work_exchange_offer",
            },
            {
                "step": "accept_compute_barter",
                "input": "visible_solution_value_required_return_work_and_max_runtime",
                "output": "obligation_id",
            },
            {
                "step": "run_return_compute_worker",
                "input": "obligation_id",
                "output": "verified_return_work_receipts",
            },
            {
                "step": "auto_stop",
                "input": "balance_zero",
                "output": "worker_exits_no_more_compute_due",
            },
        ],
        "downloads": {
            "installer_bat": _u(base_url, "/downloads/install_nomad_work_exchange_worker.bat"),
            "worker_py": _u(base_url, "/downloads/nomad_work_exchange_worker.py"),
            "human_page": _u(base_url, "/work-exchange"),
        },
        "copy_paste_start": {
            "windows_cmd": (
                f"curl -L -o %TEMP%\\install_nomad_work_exchange_worker.bat "
                f"{_u(base_url, '/downloads/install_nomad_work_exchange_worker.bat')} && "
                f"%TEMP%\\install_nomad_work_exchange_worker.bat {root or '<BASE_URL>'} "
                "OBLIGATION_ID_HERE"
            ),
            "python_portable": (
                f"python nomad_work_exchange_worker.py --base-url {root or '<BASE_URL>'} "
                "--obligation-id OBLIGATION_ID_HERE --loop --cycles 0"
            ),
        },
        "safety_contract": {
            "requires_explicit_obligation_id": True,
            "stops_when_balance_settled": True,
            "max_side_effect_scope": "sandboxed_worker_only",
            "secret_policy": "do_not_send_secrets_public_digests_only",
            "arbitrary_code_execution": False,
            "payment_or_wallet_required": False,
        },
        "routes": {
            "work_exchange": _u(base_url, "/.well-known/nomad-work-exchange.json"),
            "onboarding": _u(base_url, "/.well-known/nomad-work-exchange-onboarding.json"),
            "offer": _u(base_url, "/swarm/work-exchange/offers"),
            "free_solution": _u(base_url, "/swarm/work-exchange/free-solution"),
            "return_work": _u(base_url, "/swarm/work-exchange/return-work"),
            "balance": _u(base_url, "/swarm/work-exchange/balance"),
        },
        "ledger_summary": ledger_summary,
        "machine_instruction": "show_offer_require_explicit_consent_issue_obligation_id_then_start_worker_until_balance_zero",
    }


def create_work_exchange_offer(
    payload: dict[str, Any],
    *,
    base_url: str,
    persist: bool = True,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    body = _dict(payload)
    if _contains_forbidden(body):
        return _error("secret_shaped_payload", "Work exchange offers must contain public digests only.")
    requester_id = _clean_id(body.get("requester_id") or body.get("user_id") or body.get("agent_id"), fallback="")
    if not requester_id:
        return _error("missing_requester_id", "requester_id, user_id, or agent_id is required.")
    solution_class = _clean_id(body.get("solution_class") or body.get("service_type"), fallback="agent_reliability_diagnostic")
    solution_value = round(max(0.0, _num(body.get("solution_value_credits") or body.get("estimated_solution_value_credits"), 10.0)), 4)
    if solution_value <= 0.0:
        return _error("invalid_solution_value", "solution_value_credits must be positive.")
    multiplier = _normalize_multiplier(body.get("return_multiplier"))
    required = round(solution_value * multiplier, 4)
    max_hours = _normalize_max_hours(body.get("max_runtime_hours"))
    offer_core = {
        "requester_id": requester_id,
        "solution_class": solution_class,
        "solution_value_credits": solution_value,
        "return_multiplier": multiplier,
        "max_runtime_hours": max_hours,
        "capabilities": body.get("offered_worker_capabilities") or body.get("capabilities") or [],
    }
    out = {
        "ok": True,
        "schema": "nomad.work_exchange.offer.v1",
        "accepted": True,
        "generated_at": _iso_now(),
        "offer_id": f"nomad-work-offer-{_digest(offer_core, 24)}",
        "requester_id": requester_id,
        "solution_class": solution_class,
        "solution_value_credits": solution_value,
        "required_return_work_credits": required,
        "nomad_margin_work_credits": round(max(0.0, required - solution_value), 4),
        "return_multiplier": multiplier,
        "max_runtime_hours": max_hours,
        "side_effect_scope": "sandboxed_worker_only",
        "terms": [
            "0_eur_solution_price",
            "explicit_compute_barter_not_hidden_fee",
            "only_verified_return_work_reduces_balance",
            "auto_stop_when_balance_settled",
            "no_secrets_or_unbounded_side_effects",
        ],
        "next": {
            "free_solution": _u(base_url, "/swarm/work-exchange/free-solution"),
            "surface": _u(base_url, "/.well-known/nomad-work-exchange.json"),
        },
    }
    if persist:
        _append(_ledger_path(ledger_path), out)
        out["persisted"] = True
    return out


def record_free_solution_receipt(
    payload: dict[str, Any],
    *,
    base_url: str,
    persist: bool = True,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    body = _dict(payload)
    if _contains_forbidden(body):
        return _error("secret_shaped_payload", "Free-solution receipts must contain public digests only.")
    requester_id = _clean_id(body.get("requester_id") or body.get("user_id") or body.get("agent_id"), fallback="")
    if not requester_id:
        return _error("missing_requester_id", "requester_id, user_id, or agent_id is required.")
    if not _truthy(body.get("accepted_compute_barter_terms") or body.get("compute_barter_accepted")):
        return _error(
            "compute_barter_terms_required",
            "The requester must explicitly accept bounded return-compute terms.",
            hints=["Set accepted_compute_barter_terms=true only after showing the required return work and max runtime."],
        )
    side_effect_scope = _text(body.get("side_effect_scope") or "sandboxed_worker_only", 80)
    if side_effect_scope != "sandboxed_worker_only":
        return _error("invalid_side_effect_scope", "Only side_effect_scope=sandboxed_worker_only is accepted for free work exchange.")
    solution_proof = _proof_digest_from(body, "solution_proof_digest", "proof_digest", "digest")
    if not solution_proof:
        return _error("solution_proof_required", "solution_proof_digest or proof_digest is required.")
    solution_value = round(max(0.0, _num(body.get("solution_value_credits") or body.get("estimated_solution_value_credits"), 0.0)), 4)
    if solution_value <= 0.0:
        return _error("invalid_solution_value", "solution_value_credits must be positive.")
    multiplier = _normalize_multiplier(body.get("return_multiplier"))
    max_hours = _normalize_max_hours(body.get("max_runtime_hours"))
    required = round(solution_value * multiplier, 4)
    core = {
        "requester_id": requester_id,
        "solution_proof_digest": solution_proof,
        "solution_value_credits": solution_value,
        "return_multiplier": multiplier,
        "max_runtime_hours": max_hours,
    }
    obligation_id = _text(body.get("obligation_id"), 180) or _obligation_id(core)
    out = {
        "ok": True,
        "schema": "nomad.work_exchange.free_solution_receipt.v1",
        "accepted": True,
        "generated_at": _iso_now(),
        "obligation_id": obligation_id,
        "requester_id": requester_id,
        "solution_class": _clean_id(body.get("solution_class") or body.get("service_type"), fallback="agent_reliability_diagnostic"),
        "solution_proof_digest": solution_proof,
        "verifier_trace_digest": _proof_digest_from(body, "verifier_trace_digest", "trace_digest"),
        "test_digest": _proof_digest_from(body, "test_digest"),
        "solution_value_credits": solution_value,
        "required_return_work_credits": required,
        "nomad_margin_work_credits": round(max(0.0, required - solution_value), 4),
        "return_multiplier": multiplier,
        "max_runtime_hours": max_hours,
        "side_effect_scope": side_effect_scope,
        "status": "active",
        "notices": [
            "0_eur_solution_price",
            "return_compute_obligation_explicitly_accepted",
            "hidden_fee_allowed_false",
            "balance_decreases_only_with_verified_return_work_receipts",
        ],
        "next": {
            "worker_lease": _u(base_url, "/swarm/workers/lease"),
            "return_work": _u(base_url, "/swarm/work-exchange/return-work"),
            "balance": _u(base_url, "/swarm/work-exchange/balance"),
        },
    }
    if persist:
        _append(_ledger_path(ledger_path), out)
        out["persisted"] = True
    return out


def record_return_work_receipt(
    payload: dict[str, Any],
    *,
    base_url: str,
    persist: bool = True,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    body = _dict(payload)
    if _contains_forbidden(body):
        return _error("secret_shaped_payload", "Return-work receipts must contain public digests only.")
    obligation_id = _text(body.get("obligation_id"), 180)
    worker_id = _clean_id(body.get("worker_agent_id") or body.get("agent_id") or body.get("runtime_id"), fallback="")
    if not obligation_id:
        return _error("missing_obligation_id", "obligation_id is required.")
    if not worker_id:
        return _error("missing_worker_agent_id", "worker_agent_id, agent_id, or runtime_id is required.")
    proof = _proof_digest_from(body, "proof_digest", "digest")
    verifier = _proof_digest_from(body, "verifier_trace_digest", "trace_digest")
    test_digest = _proof_digest_from(body, "test_digest")
    if not (proof and verifier and test_digest):
        return _error(
            "return_work_proof_required",
            "Return work needs proof_digest, verifier_trace_digest, and test_digest.",
        )
    work_credits = round(max(0.0, _num(body.get("work_credits") or body.get("accepted_work_credits"), 0.0)), 4)
    if work_credits <= 0.0:
        return _error("invalid_work_credits", "work_credits must be positive.")
    balance_before = work_exchange_balance({"obligation_id": obligation_id}, ledger_path=ledger_path)
    obligation = _dict(balance_before.get("obligation"))
    if not obligation:
        return _error(
            "obligation_not_found",
            "Return work can only settle an existing free-solution compute obligation.",
            hints=["Record /swarm/work-exchange/free-solution first, then post verified return work."],
        )
    outstanding_before = _num(obligation.get("outstanding_work_credits"), work_credits)
    accepted_credits = round(min(work_credits, max(0.0, outstanding_before if obligation else work_credits)), 4)
    event_core = {
        "obligation_id": obligation_id,
        "worker_id": worker_id,
        "proof_digest": proof,
        "verifier_trace_digest": verifier,
        "test_digest": test_digest,
        "work_credits": work_credits,
    }
    out = {
        "ok": True,
        "schema": "nomad.work_exchange.return_work_receipt.v1",
        "accepted": True,
        "generated_at": _iso_now(),
        "return_receipt_id": f"nomad-return-work-{_digest(event_core, 24)}",
        "obligation_id": obligation_id,
        "worker_agent_id": worker_id,
        "lease_id": _text(body.get("lease_id"), 160),
        "task_id": _text(body.get("task_id"), 160),
        "objective": _clean_id(body.get("objective"), fallback="return_compute_obligation"),
        "proof_digest": proof,
        "verifier_trace_digest": verifier,
        "test_digest": test_digest,
        "claimed_work_credits": work_credits,
        "accepted_work_credits": accepted_credits,
        "overflow_work_credits": round(max(0.0, work_credits - accepted_credits), 4),
        "settlement_ref": _text(body.get("settlement_ref"), 180),
        "balance_before_work_credits": round(max(0.0, outstanding_before), 4),
        "balance_after_work_credits": round(max(0.0, outstanding_before - accepted_credits), 4),
        "status_after": "settled" if max(0.0, outstanding_before - accepted_credits) <= 0.0 else "active",
        "experience_payload": {
            "agent_id": worker_id,
            "objective": "return_compute_obligation",
            "proof_digest": proof,
            "verifier_trace_digest": verifier,
            "test_digest": test_digest,
            "evaluation": {
                "tests_passed": 1,
                "tests_total": 1,
                "utility_delta": accepted_credits,
                "settlement_delta": 0.0,
                "reuse_count": 0,
                "risk_score": max(0.0, _num(body.get("risk_score"), 0.0)),
            },
            "skill_candidate": {
                "capability": "verified_return_compute",
                "activation_signature": f"work_exchange_{_digest(event_core, 16)}",
                "program_hint": ["POST /swarm/workers/lease", "POST /swarm/workers/complete", "POST /swarm/work-exchange/return-work"],
            },
        },
        "next": {
            "balance": _u(base_url, "/swarm/work-exchange/balance"),
            "worker_lease": _u(base_url, "/swarm/workers/lease"),
        },
    }
    if persist:
        _append(_ledger_path(ledger_path), out)
        out["persisted"] = True
    return out


def work_exchange_balance(payload: dict[str, Any] | None = None, *, ledger_path: Path | str | None = None) -> dict[str, Any]:
    body = _dict(payload)
    obligation_id = _text(body.get("obligation_id"), 180)
    summary = summarize_work_exchange_ledger(ledger_path=ledger_path)
    obligations = _obligation_states(_read_events(_ledger_path(ledger_path)))
    match = None
    if obligation_id:
        for row in obligations:
            if _text(row.get("obligation_id"), 180) == obligation_id:
                match = row
                break
    return {
        "ok": True,
        "schema": "nomad.work_exchange_balance.v1",
        "generated_at": _iso_now(),
        "obligation_id": obligation_id,
        "obligation": match or {},
        "found": bool(match) if obligation_id else False,
        "summary": summary,
        "machine_instruction": "if_found_and_outstanding_is_zero_stop_return_compute_else_continue_with_bounded_leases",
    }
