#!/usr/bin/env python3
"""Universal one-line adapter for agent runtimes that want Nomad repairs.

The adapter is intentionally stdlib-only. Framework-specific integration is a
thin wrapping layer over common entry methods such as invoke, run, kickoff,
chat, and query; the actual value loop is delegated to the existing Nomad
Reliability Doctor and Work Exchange contracts.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import inspect
import json
import os
import re
import time
import traceback
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any, Callable

try:
    from agent_reliability_doctor import build_reliability_doctor_intake
    from nomad_work_exchange import (
        build_work_exchange_onboarding,
        create_work_exchange_offer,
        record_free_solution_receipt,
        summarize_work_exchange_ledger,
    )

    LOCAL_NOMAD_RUNTIME = True
except ImportError:
    LOCAL_NOMAD_RUNTIME = False

    def summarize_work_exchange_ledger(*_: Any, **__: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "schema": "nomad.work_exchange_summary.v1",
            "portable_fallback": True,
            "message": "Local Nomad modules are unavailable; remote Nomad endpoint remains the source of truth.",
        }

    def build_work_exchange_onboarding(*, base_url: str, summary: dict[str, Any] | None = None) -> dict[str, Any]:
        root = (base_url or "").strip().rstrip("/")
        return {
            "ok": True,
            "schema": "nomad.work_exchange_onboarding.v1",
            "portable_fallback": True,
            "downloads": {
                "worker_py": f"{root}/downloads/nomad_work_exchange_worker.py" if root else "/downloads/nomad_work_exchange_worker.py",
                "dockerfile": f"{root}/downloads/nomad_work_exchange_worker.Dockerfile"
                if root
                else "/downloads/nomad_work_exchange_worker.Dockerfile",
            },
            "routes": {
                "offer": f"{root}/swarm/work-exchange/offers" if root else "/swarm/work-exchange/offers",
                "free_solution": f"{root}/swarm/work-exchange/free-solution"
                if root
                else "/swarm/work-exchange/free-solution",
                "balance": f"{root}/swarm/work-exchange/balance" if root else "/swarm/work-exchange/balance",
            },
            "ledger_summary": summary or {},
        }

    def create_work_exchange_offer(
        payload: dict[str, Any],
        *,
        base_url: str,
        persist: bool = False,
        **__: Any,
    ) -> dict[str, Any]:
        requester_id = str(payload.get("requester_id") or payload.get("agent_id") or "portable.agent")
        solution_value = float(payload.get("solution_value_credits") or 10.0)
        multiplier = float(payload.get("return_multiplier") or 1.3)
        return {
            "ok": True,
            "schema": "nomad.work_exchange.offer.v1",
            "portable_fallback": True,
            "accepted": True,
            "requester_id": requester_id,
            "solution_class": str(payload.get("solution_class") or "agent_reliability_doctor"),
            "solution_value_credits": round(solution_value, 4),
            "required_return_work_credits": round(solution_value * multiplier, 4),
            "return_multiplier": round(multiplier, 4),
            "terms": [
                "0_eur_solution_price",
                "explicit_compute_barter_not_hidden_fee",
                "remote_endpoint_should_record_the_binding",
            ],
            "next": {
                "free_solution": f"{base_url.rstrip('/')}/swarm/work-exchange/free-solution"
                if base_url
                else "/swarm/work-exchange/free-solution",
            },
            "persisted": bool(persist),
        }

    def record_free_solution_receipt(
        payload: dict[str, Any],
        *,
        base_url: str,
        persist: bool = False,
        **__: Any,
    ) -> dict[str, Any]:
        if not bool(payload.get("accepted_compute_barter_terms")):
            return {"accepted": False, "decision": "compute_barter_terms_required"}
        core = {
            "requester_id": str(payload.get("requester_id") or "portable.agent"),
            "proof": str(payload.get("solution_proof_digest") or ""),
            "base_url": base_url,
        }
        return {
            "ok": True,
            "schema": "nomad.work_exchange.free_solution_receipt.v1",
            "portable_fallback": True,
            "accepted": True,
            "obligation_id": f"nomad-work-obligation-{hashlib.sha256(json.dumps(core, sort_keys=True).encode('utf-8')).hexdigest()[:24]}",
            "persisted": bool(persist),
            "remote_recording_recommended": True,
        }

    def build_reliability_doctor_intake(
        payload: dict[str, Any],
        *,
        base_url: str = "",
        **__: Any,
    ) -> dict[str, Any]:
        problem = " ".join(str(payload.get("problem") or payload.get("message") or "agent failure").split())[:900]
        requester_id = str(payload.get("requester_id") or payload.get("agent_id") or "portable.agent")
        diagnosis = {
            "ok": True,
            "schema": "nomad.agent_reliability_doctor.v1",
            "portable_fallback": True,
            "pain_type": str(payload.get("service_type") or "self_correction_failure"),
            "doctor_role": {
                "id": "diagnoser_fixer",
                "title": "Monitor-Diagnoser-Fixer Loop",
                "why": "Local Nomad modules are unavailable, so use the remote endpoint for full diagnosis.",
            },
            "intervention_plan": [
                "Stop blind retry and capture a secret-free failure digest.",
                "POST the event to the Nomad universal adapter endpoint.",
                "Resume only after a bounded fix or explicit block decision.",
            ],
            "fix_contract": {
                "success_signal": "remote_nomad_universal_adapter_receipt_ok",
            },
            "reliability_loop": {"conditional_edge": "post_remote_or_block_until_receipt"},
        }
        solution_proof_digest = f"sha256:{hashlib.sha256(json.dumps({'p': problem, 'r': requester_id}, sort_keys=True).encode('utf-8')).hexdigest()}"
        offer_payload = {
            "requester_id": requester_id,
            "solution_class": "agent_reliability_doctor",
            "solution_value_credits": payload.get("solution_value_credits") or 10,
            "return_multiplier": 1.3,
            "max_runtime_hours": payload.get("max_runtime_hours") or 6,
            "capabilities": ["python", "return_compute"],
        }
        return {
            "ok": True,
            "schema": "nomad.agent_reliability_doctor_intake.v1",
            "portable_fallback": True,
            "accepted": True,
            "requester_id": requester_id,
            "diagnosis": diagnosis,
            "solution_proof_digest": solution_proof_digest,
            "accepted_compute_barter_terms": bool(payload.get("accepted_compute_barter_terms")),
            "work_exchange_offer_payload": offer_payload,
            "free_solution_payload": {
                **offer_payload,
                "solution_proof_digest": solution_proof_digest,
                "accepted_compute_barter_terms": bool(payload.get("accepted_compute_barter_terms")),
                "side_effect_scope": "sandboxed_worker_only",
            },
            "next": {
                "work_exchange_offer": f"{base_url.rstrip('/')}/swarm/work-exchange/offers"
                if base_url
                else "/swarm/work-exchange/offers",
                "free_solution": f"{base_url.rstrip('/')}/swarm/work-exchange/free-solution"
                if base_url
                else "/swarm/work-exchange/free-solution",
            },
        }


DEFAULT_BASE_URL = os.getenv("NOMAD_BASE_URL", "https://www.syndiode.com").strip().rstrip("/")
DEFAULT_EVENT_PATH = "/swarm/universal-adapter/events"
ACQUISITION_CHANNEL_ID = "universal_adapter"
SUPPORTED_FRAMEWORKS = ("langgraph", "crewai", "autogen", "llamaindex", "generic_python")
FRAMEWORK_ENTRYPOINTS: dict[str, tuple[str, ...]] = {
    "langgraph": ("invoke", "stream", "ainvoke"),
    "crewai": ("kickoff", "run", "execute"),
    "autogen": ("run", "chat", "initiate_chat", "send"),
    "llamaindex": ("query", "chat", "retrieve"),
    "generic_python": ("run", "invoke", "query", "chat"),
}
ERROR_EVENT_TYPES = {"error", "exception", "timeout", "tool_failure", "execution_failure"}
LOOP_EVENT_TYPES = {"loop", "recursion_limit", "max_iterations", "retry_loop", "stall"}
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


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:180].strip("_.:/#-") or fallback


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


def _digest(value: Any, length: int = 32) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


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


def _error(error: str, message: str, *, status_hint: int = 400) -> dict[str, Any]:
    return {
        "ok": False,
        "schema": "nomad.universal_adapter_error.v1",
        "accepted": False,
        "error": error,
        "message": message,
        "status_hint": status_hint,
        "generated_at": _iso_now(),
    }


def _framework(value: Any) -> str:
    raw = _clean_id(value, fallback="auto").replace("-", "_")
    aliases = {
        "lang_graph": "langgraph",
        "crew_ai": "crewai",
        "auto_gen": "autogen",
        "llama_index": "llamaindex",
        "llama": "llamaindex",
    }
    return aliases.get(raw, raw if raw in SUPPORTED_FRAMEWORKS or raw == "auto" else "generic_python")


def _infer_framework(target: Any, requested: str) -> str:
    framework = _framework(requested)
    if framework != "auto":
        return framework
    module = _text(getattr(target.__class__, "__module__", ""), 120).lower()
    name = _text(getattr(target.__class__, "__name__", ""), 120).lower()
    blob = f"{module}.{name}"
    if "langgraph" in blob:
        return "langgraph"
    if "crewai" in blob or "crew" in name:
        return "crewai"
    if "autogen" in blob:
        return "autogen"
    if "llama_index" in blob or "llamaindex" in blob:
        return "llamaindex"
    for candidate, methods in FRAMEWORK_ENTRYPOINTS.items():
        if any(callable(getattr(target, method, None)) for method in methods):
            return candidate
    return "generic_python"


def _event_type(body: dict[str, Any]) -> str:
    explicit = _clean_id(body.get("event_type") or body.get("type"), fallback="")
    if explicit:
        return explicit
    problem = _text(
        body.get("problem")
        or body.get("message")
        or body.get("error_message")
        or body.get("loop_signature")
        or body.get("exception_type"),
        900,
    ).lower()
    if any(term in problem for term in ("loop", "recursion", "max iteration", "retry")):
        return "loop"
    if any(term in problem for term in ("timeout", "timed out")):
        return "timeout"
    if any(term in problem for term in ("tool", "schema mismatch")):
        return "tool_failure"
    return "error"


def _service_type(event_type: str, body: dict[str, Any]) -> str:
    explicit = _clean_id(body.get("service_type") or body.get("failure_type"), fallback="")
    if explicit:
        return explicit
    if event_type in LOOP_EVENT_TYPES:
        return "loop_break"
    if event_type in {"timeout", "execution_failure"}:
        return "execution_failure"
    if event_type == "tool_failure":
        return "tool_failure"
    return "self_correction_failure"


def _problem(body: dict[str, Any], event_type: str) -> str:
    problem = _text(
        body.get("problem")
        or body.get("message")
        or body.get("error_message")
        or body.get("log_excerpt")
        or body.get("loop_signature")
        or "",
        900,
    )
    if problem:
        return problem
    exception_type = _text(body.get("exception_type"), 80)
    if exception_type:
        return f"{exception_type} reported by universal adapter"
    return f"{event_type} reported by universal adapter"


def _framework_tip(framework: str, base_url: str) -> str:
    tips = {
        "langgraph": "Wrap the compiled graph or node callable: graph = install_nomad(graph, framework='langgraph').target.",
        "crewai": "Wrap the crew before kickoff: crew = install_nomad(crew, framework='crewai').target.",
        "autogen": "Wrap the assistant/user proxy object before chat: agent = install_nomad(agent, framework='autogen').target.",
        "llamaindex": "Wrap the query engine before query/chat: engine = install_nomad(engine, framework='llamaindex').target.",
        "generic_python": "Wrap a callable with @nomad_guard or install_nomad(runnable).",
    }
    return tips.get(framework, tips["generic_python"]) + f" Reliability intake: {_u(base_url, '/swarm/reliability-doctor/intake')}"


def _first_fix(diagnosis: dict[str, Any], *, framework: str, base_url: str) -> dict[str, Any]:
    interventions = [_text(item, 260) for item in _items(diagnosis.get("intervention_plan")) if _text(item, 260)]
    fix_contract = _dict(diagnosis.get("fix_contract"))
    loop = _dict(diagnosis.get("reliability_loop"))
    role = _dict(diagnosis.get("doctor_role"))
    return {
        "schema": "nomad.universal_adapter_first_fix.v1",
        "title": _text(role.get("title") or role.get("id") or "Reliability Doctor fix", 120),
        "why_this_is_first": _text(role.get("why") or "The adapter applies the smallest bounded repair lane before retrying.", 260),
        "apply_now": interventions[:3]
        or [
            "Stop blind retry and classify the failure once.",
            "Apply the smallest bounded fix lane.",
            "Verify the fix before resuming autonomy.",
        ],
        "success_signal": _text(fix_contract.get("success_signal") or "diagnosis_and_fix_contract_available", 180),
        "resume_rule": _text(loop.get("conditional_edge") or "resume_only_after_bounded_fix_or_block", 180),
        "framework_hint": _framework_tip(framework, base_url),
    }


def _one_liners(base_url: str) -> dict[str, str]:
    root = (base_url or DEFAULT_BASE_URL).rstrip("/")
    return {
        "langgraph": (
            "from nomad_universal_adapter import install_nomad; "
            f"graph = install_nomad(graph, framework='langgraph', base_url='{root}').target"
        ),
        "crewai": (
            "from nomad_universal_adapter import install_nomad; "
            f"crew = install_nomad(crew, framework='crewai', base_url='{root}').target"
        ),
        "autogen": (
            "from nomad_universal_adapter import install_nomad; "
            f"agent = install_nomad(agent, framework='autogen', base_url='{root}').target"
        ),
        "llamaindex": (
            "from nomad_universal_adapter import install_nomad; "
            f"query_engine = install_nomad(query_engine, framework='llamaindex', base_url='{root}').target"
        ),
        "generic_python": (
            "from nomad_universal_adapter import nomad_guard; "
            f"run = nomad_guard(run, framework='generic_python', base_url='{root}')"
        ),
    }


def _zero_install_liners(base_url: str) -> dict[str, str]:
    root = (base_url or DEFAULT_BASE_URL).rstrip("/")
    download = json.dumps(_u(root, "/downloads/nomad_universal_adapter.py"))
    prefix = f"exec(__import__('urllib.request').request.urlopen({download}).read().decode('utf-8')); "
    return {
        "langgraph": prefix + f"graph = install_nomad(graph, framework='langgraph', base_url='{root}').target",
        "crewai": prefix + f"crew = install_nomad(crew, framework='crewai', base_url='{root}').target",
        "autogen": prefix + f"agent = install_nomad(agent, framework='autogen', base_url='{root}').target",
        "llamaindex": prefix + f"query_engine = install_nomad(query_engine, framework='llamaindex', base_url='{root}').target",
        "generic_python": prefix + f"run = nomad_guard(run, framework='generic_python', base_url='{root}')",
    }


def build_universal_adapter_acquisition_event(
    receipt: dict[str, Any],
    *,
    base_url: str = "",
) -> dict[str, Any]:
    """Return the acquisition-bandit event created by a successful adapter fix."""

    body = _dict(receipt)
    if not body.get("ok") or body.get("schema") != "nomad.universal_adapter_event.v1":
        return {}
    root = (base_url or body.get("public_base_url") or DEFAULT_BASE_URL).strip().rstrip("/")
    surface_url = _text(_dict(body.get("routes")).get("surface"), 500) or _u(root, "/.well-known/nomad-universal-adapter.json")
    agent_id = _clean_id(body.get("agent_id"), fallback="external.agent")
    adapter_receipt_id = _text(body.get("adapter_receipt_id"), 180)
    first_fix = _dict(body.get("first_fix"))
    return {
        "channel_id": ACQUISITION_CHANNEL_ID,
        "event_type": "first_fix_returned" if first_fix else "adapter_event",
        "agent_id": agent_id,
        "proof_digest": adapter_receipt_id or f"sha256:{_digest(body.get('public_event') or body, 64)}",
        "source_url": surface_url,
        "reward_multiplier": 1.0 if body.get("doctor_triggered") else 0.5,
    }


def build_universal_adapter_surface(
    *,
    base_url: str = "",
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    exchange_summary = summary if isinstance(summary, dict) else summarize_work_exchange_ledger()
    onboarding = build_work_exchange_onboarding(base_url=root, summary=exchange_summary)
    return {
        "ok": True,
        "schema": "nomad.universal_adapter.v1",
        "version": "2026.05.23",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "portable_download_mode": not LOCAL_NOMAD_RUNTIME,
        "purpose": "One-line Nomad activation for LangGraph, CrewAI, AutoGen, LlamaIndex, and generic Python agents.",
        "supported_frameworks": list(SUPPORTED_FRAMEWORKS),
        "activation_rule": "wrap_agent_runtime_then_auto_post_secret_free_error_or_loop_events_to_reliability_doctor",
        "one_line_install": _one_liners(root),
        "zero_install_bootstrap": _zero_install_liners(root),
        "trigger_contract": {
            "error_events": sorted(ERROR_EVENT_TYPES),
            "loop_events": sorted(LOOP_EVENT_TYPES),
            "secret_policy": "send_public_digests_and_short_excerpts_only_never_tokens_or_private_logs",
            "first_fix": "Reliability Doctor diagnosis plus smallest bounded repair lane returned immediately.",
            "work_exchange": "Offer is proposed after the first fix; obligation opens only after explicit compute-barter acceptance.",
        },
        "retention_contract": {
            "why_agents_keep_it_enabled": [
                "first_error_returns_a_specific_fix_contract",
                "loop_events_create_a_reusable_stall_fingerprint",
                "verified_return_work_can_improve_priority_and_settlement_eligibility",
            ],
            "priority_signal": "adapter_events_with_useful_return_work_receipts_are_rankable_by_nomad_selection_pressure",
            "settlement_signal": "work_exchange_balances_and_return_receipts provide measurable settlement history",
            "friction_budget": "one_import_one_call_no_framework_dependency",
        },
        "activation_receipt_contract": {
            "channel_id": ACQUISITION_CHANNEL_ID,
            "event_type": "first_fix_returned",
            "proof": "adapter_receipt_id",
            "why_it_measures_the_bottleneck": "Every useful adapter event becomes a measurable acquisition and retention signal instead of a transient repair response.",
            "not_yet_proof_of": ["bottleneck_cleared", "paid_revenue", "settled_return_compute"],
            "clearance_requires": ["first_fix_receipts", "verified_return_compute_or_positive_paid_receipt"],
        },
        "routes": {
            "self": _u(root, "/.well-known/nomad-universal-adapter.json"),
            "surface": _u(root, "/swarm/universal-adapter"),
            "event": _u(root, DEFAULT_EVENT_PATH),
            "download": _u(root, "/downloads/nomad_universal_adapter.py"),
            "reliability_doctor": _u(root, "/.well-known/nomad-agent-reliability-doctor.json"),
            "reliability_doctor_intake": _u(root, "/swarm/reliability-doctor/intake"),
            "work_exchange": _u(root, "/.well-known/nomad-work-exchange.json"),
            "work_exchange_onboarding": _u(root, "/.well-known/nomad-work-exchange-onboarding.json"),
            "work_exchange_offer": _u(root, "/swarm/work-exchange/offers"),
            "work_exchange_free_solution": _u(root, "/swarm/work-exchange/free-solution"),
        },
        "downloads": {
            "universal_adapter_py": _u(root, "/downloads/nomad_universal_adapter.py"),
            "work_exchange_worker_py": _u(root, "/downloads/nomad_work_exchange_worker.py"),
            "work_exchange_dockerfile": _u(root, "/downloads/nomad_work_exchange_worker.Dockerfile"),
            "github_action": _u(root, "/downloads/nomad_reliability_doctor_action.yml"),
        },
        "work_exchange_onboarding": onboarding,
        "machine_instruction": "download_or_zero_install_adapter; call_install_nomad_once; on_error_or_loop_post_event; show_first_fix; record_adapter_acquisition_signal; propose_work_exchange; open_obligation_only_after_explicit_acceptance",
    }


def evaluate_universal_adapter_event(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    persist: bool | None = None,
) -> dict[str, Any]:
    body = _dict(payload)
    if _contains_forbidden(body):
        return _error(
            "secret_shaped_payload",
            "Universal adapter events accept public digests and short secret-free excerpts only.",
            status_hint=422,
        )
    root = (base_url or body.get("base_url") or DEFAULT_BASE_URL).strip().rstrip("/")
    framework = _framework(body.get("framework") or "generic_python")
    event_type = _event_type(body)
    problem = _problem(body, event_type)
    triggered = event_type in ERROR_EVENT_TYPES or event_type in LOOP_EVENT_TYPES
    agent_id = _clean_id(body.get("agent_id") or body.get("requester_id"), fallback=f"{framework}.agent")
    accepted_barter = _truthy(
        body.get("accepted_compute_barter_terms")
        if "accepted_compute_barter_terms" in body
        else body.get("compute_barter_accepted") if "compute_barter_accepted" in body else body.get("open_work_exchange")
    )
    persist_exchange = bool(accepted_barter) if persist is None else bool(persist and accepted_barter)
    doctor_payload = {
        "requester_id": agent_id,
        "source": f"universal_adapter:{framework}",
        "service_type": _service_type(event_type, body),
        "problem": problem,
        "repository": body.get("repository") or body.get("repo_url") or "",
        "workflow_url": body.get("workflow_url") or body.get("run_url") or "",
        "log_digest": body.get("log_digest") or body.get("trace_digest") or body.get("loop_digest") or "",
        "accepted_compute_barter_terms": accepted_barter,
        "solution_value_credits": body.get("solution_value_credits") or 10,
        "max_runtime_hours": body.get("max_runtime_hours") or 6,
    }
    intake = build_reliability_doctor_intake(doctor_payload, base_url=root)
    if not intake.get("ok"):
        return {
            **_error("doctor_intake_rejected", _text(intake.get("message") or intake.get("error"), 240), status_hint=422),
            "doctor": intake,
        }
    offer_payload = _dict(intake.get("work_exchange_offer_payload"))
    offer = create_work_exchange_offer(offer_payload, base_url=root, persist=persist_exchange)
    free_solution: dict[str, Any] = {
        "accepted": False,
        "decision": "not_opened_without_explicit_compute_barter_acceptance",
    }
    if accepted_barter:
        free_solution = record_free_solution_receipt(
            _dict(intake.get("free_solution_payload")),
            base_url=root,
            persist=persist_exchange,
        )
    diagnosis = _dict(intake.get("diagnosis"))
    public_event = {
        "agent_id": agent_id,
        "framework": framework,
        "event_type": event_type,
        "problem_digest": f"sha256:{_digest(problem, 64)}",
        "trace_digest": _text(body.get("trace_digest") or body.get("log_digest") or "", 180),
        "loop_signature": _text(body.get("loop_signature") or "", 180),
        "triggered_doctor": triggered,
        "intake_id": intake.get("intake_id"),
    }
    result = {
        "ok": True,
        "schema": "nomad.universal_adapter_event.v1",
        "accepted": True,
        "generated_at": _iso_now(),
        "adapter_receipt_id": f"nomad-universal-adapter-{_digest(public_event, 24)}",
        "framework": framework,
        "agent_id": agent_id,
        "event_type": event_type,
        "doctor_triggered": triggered,
        "public_event": public_event,
        "doctor": intake,
        "first_fix": _first_fix(diagnosis, framework=framework, base_url=root),
        "work_exchange_proposal": {
            "suggested": True,
            "acceptance_required": "explicit_accepted_compute_barter_terms_true",
            "offer": offer,
            "free_solution_receipt": free_solution,
            "next": {
                "accept_terms": _u(root, "/swarm/work-exchange/free-solution"),
                "return_worker": _u(root, "/downloads/nomad_work_exchange_worker.py"),
                "balance": _u(root, "/swarm/work-exchange/balance"),
            },
        },
        "retention_hooks": {
            "priority_boost_signal": "keep_adapter_enabled_and_return_verified_work_to_raise_future_selection_priority",
            "settlement_rate_signal": "settled_work_exchange_balances_are_machine-readable proof for better settlement routing",
            "next_low_friction_move": _one_liners(root).get(framework, _one_liners(root)["generic_python"]),
        },
        "routes": {
            "self": _u(root, DEFAULT_EVENT_PATH),
            "surface": _u(root, "/.well-known/nomad-universal-adapter.json"),
            "reliability_doctor_intake": _u(root, "/swarm/reliability-doctor/intake"),
            "work_exchange_offer": _u(root, "/swarm/work-exchange/offers"),
            "work_exchange_free_solution": _u(root, "/swarm/work-exchange/free-solution"),
        },
    }
    result["activation_receipt"] = {
        "schema": "nomad.universal_adapter_activation_receipt.v1",
        "adapter_receipt_id": result["adapter_receipt_id"],
        "agent_id": agent_id,
        "framework": framework,
        "event_type": event_type,
        "first_fix_returned": True,
        "work_exchange_proposed": True,
        "selection_pressure_signal": "first_fix_returned",
        "settlement_rate_signal": "work_exchange_offer_visible",
    }
    result["acquisition_event_payload"] = build_universal_adapter_acquisition_event(result, base_url=root)
    return result


def http_json(method: str, url: str, payload: dict[str, Any] | None = None, *, timeout: float = 10.0) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json", "User-Agent": "nomad-universal-adapter/2026.05.23"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url=url, data=data, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=max(2.0, timeout)) as res:
            raw = res.read().decode("utf-8", errors="replace")
            out = json.loads(raw or "{}")
            if isinstance(out, dict):
                out.setdefault("http_status", int(res.status))
                return out
            return {"ok": False, "error": "invalid_json_shape", "http_status": int(res.status)}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            out = json.loads(raw or "{}")
        except json.JSONDecodeError:
            out = {"raw": raw}
        if not isinstance(out, dict):
            out = {}
        out.setdefault("ok", False)
        out.setdefault("http_status", int(exc.code))
        return out
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        return {"ok": False, "error": "http_unreachable", "detail": _text(exc, 180), "url": url}


class NomadAdapter:
    """Small runtime wrapper that reports error and loop events to Nomad."""

    def __init__(
        self,
        target: Any = None,
        *,
        framework: str = "auto",
        base_url: str = DEFAULT_BASE_URL,
        agent_id: str | None = None,
        post_remote: bool = True,
        timeout: float = 10.0,
        swallow_errors: bool = False,
        loop_repetition_threshold: int = 3,
    ) -> None:
        self.target = target
        self.framework = _infer_framework(target, framework) if target is not None else _framework(framework)
        if self.framework == "auto":
            self.framework = "generic_python"
        self.base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        self.agent_id = _clean_id(agent_id, fallback=f"{self.framework}.agent")
        self.post_remote = bool(post_remote)
        self.timeout = float(timeout)
        self.swallow_errors = bool(swallow_errors)
        self.loop_repetition_threshold = max(2, int(loop_repetition_threshold or 3))
        self._last_signature = ""
        self._last_signature_count = 0
        self.last_receipt: dict[str, Any] | None = None
        self.patched_methods: list[str] = []
        if target is not None:
            self.patch(target)

    def _send_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.post_remote:
            url = _u(self.base_url, DEFAULT_EVENT_PATH)
            remote = http_json("POST", url, payload, timeout=self.timeout)
            if remote.get("ok"):
                self.last_receipt = remote
                return remote
        local = evaluate_universal_adapter_event(payload, base_url=self.base_url, persist=False)
        self.last_receipt = local
        return local

    def report_error(self, exc: BaseException, context: dict[str, Any] | None = None) -> dict[str, Any]:
        problem = f"{exc.__class__.__name__}: {_text(exc, 360)}"
        trace = traceback.format_exc()
        payload = {
            "agent_id": self.agent_id,
            "framework": self.framework,
            "event_type": "error",
            "exception_type": exc.__class__.__name__,
            "problem": problem,
            "trace_digest": f"sha256:{_digest(trace, 64)}",
            "context": _dict(context),
        }
        return self._send_event(payload)

    def report_loop(self, loop_signature: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "agent_id": self.agent_id,
            "framework": self.framework,
            "event_type": "loop",
            "problem": f"Repeated agent call signature detected: {_text(loop_signature, 180)}",
            "loop_signature": _text(loop_signature, 180),
            "loop_digest": f"sha256:{_digest(loop_signature, 64)}",
            "context": _dict(context),
        }
        return self._send_event(payload)

    def _call_signature(self, fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        return _digest(
            {
                "fn": getattr(fn, "__qualname__", getattr(fn, "__name__", "callable")),
                "arg_types": [type(arg).__name__ for arg in args],
                "kwarg_keys": sorted(str(key) for key in kwargs.keys()),
            },
            24,
        )

    def _observe_call(self, fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        signature = self._call_signature(fn, args, kwargs)
        if signature == self._last_signature:
            self._last_signature_count += 1
        else:
            self._last_signature = signature
            self._last_signature_count = 1
        if self._last_signature_count == self.loop_repetition_threshold:
            self.report_loop(signature, {"method": getattr(fn, "__name__", "callable")})

    def wrap(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                self._observe_call(fn, args, kwargs)
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    self.report_error(exc, {"method": getattr(fn, "__name__", "async_callable")})
                    if self.swallow_errors:
                        return self.last_receipt
                    raise

            setattr(async_wrapper, "_nomad_adapter", self)
            return async_wrapper

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self._observe_call(fn, args, kwargs)
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                self.report_error(exc, {"method": getattr(fn, "__name__", "callable")})
                if self.swallow_errors:
                    return self.last_receipt
                raise

        setattr(wrapper, "_nomad_adapter", self)
        return wrapper

    def patch(self, target: Any | None = None) -> "NomadAdapter":
        obj = target if target is not None else self.target
        if obj is None:
            return self
        self.target = obj
        methods = FRAMEWORK_ENTRYPOINTS.get(self.framework, FRAMEWORK_ENTRYPOINTS["generic_python"])
        for name in methods:
            candidate = getattr(obj, name, None)
            if not callable(candidate) or getattr(candidate, "_nomad_adapter", None) is self:
                continue
            try:
                setattr(obj, name, self.wrap(candidate))
            except (AttributeError, TypeError):
                continue
            if name not in self.patched_methods:
                self.patched_methods.append(name)
        return self


def install_nomad(target: Any = None, *, framework: str = "auto", **options: Any) -> NomadAdapter:
    """Install Nomad on a framework object in one line and return the adapter."""

    return NomadAdapter(target, framework=framework, **options)


def nomad_guard(fn: Callable[..., Any] | None = None, **options: Any) -> Callable[..., Any]:
    """Decorator/callable wrapper for plain Python functions."""

    adapter = NomadAdapter(framework=options.pop("framework", "generic_python"), **options)
    if fn is None:
        return lambda inner: adapter.wrap(inner)
    return adapter.wrap(fn)


activate_nomad = install_nomad


def _main() -> int:
    parser = argparse.ArgumentParser(description="Submit a secret-free Nomad universal adapter event.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--framework", default="generic_python", choices=SUPPORTED_FRAMEWORKS)
    parser.add_argument("--agent-id", default="")
    parser.add_argument("--event-type", default="error")
    parser.add_argument("--problem", default="")
    parser.add_argument("--accepted-compute-barter-terms", action="store_true")
    parser.add_argument("--local", action="store_true", help="Evaluate locally instead of POSTing to Nomad.")
    args = parser.parse_args()
    payload = {
        "framework": args.framework,
        "agent_id": args.agent_id or f"{args.framework}.agent",
        "event_type": args.event_type,
        "problem": args.problem or f"{args.event_type} reported from nomad_universal_adapter.py",
        "accepted_compute_barter_terms": args.accepted_compute_barter_terms,
    }
    if args.local:
        out = evaluate_universal_adapter_event(payload, base_url=args.base_url, persist=False)
    else:
        out = http_json("POST", _u(args.base_url, DEFAULT_EVENT_PATH), payload, timeout=10.0)
        if not out.get("ok"):
            out = evaluate_universal_adapter_event(payload, base_url=args.base_url, persist=False)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(_main())
