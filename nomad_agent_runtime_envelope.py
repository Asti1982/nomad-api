"""Agent-first HTTP response envelope: explicit next-step graph, limits, and runtime semantics.

Grounding (machine-native control, not human UX):
- Explicit action graphs reduce ambiguity for autonomous loops (cf. MDP / policy interfaces in RL).
- Backpressure and rate limits are standard for stable multi-tenant systems (token-bucket / leaky-bucket).
- Idempotent retries are the HTTP/agent analogue of safe replay in distributed systems.

Agents should never infer hidden caps; surfaces advertise limits and legitimate successors.
"""

from __future__ import annotations

import os
from typing import Any


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or "").strip() or str(default))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float((os.getenv(name) or "").strip() or str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool = True) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "y"}


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def build_agent_limits() -> dict[str, Any]:
    return {
        "schema": "nomad.agent_limits.v1",
        "rate_limit_per_minute": max(1, _env_int("NOMAD_AGENT_RATE_LIMIT_PER_MINUTE", 120)),
        "default_retry_after_sec": max(0.0, _env_float("NOMAD_AGENT_DEFAULT_RETRY_AFTER_SEC", 2.0)),
        "queue_depth_hint_max": max(1, _env_int("NOMAD_AGENT_QUEUE_HINT_MAX", 256)),
        "default_ttl_sec": max(30, _env_int("NOMAD_AGENT_DEFAULT_TTL_SEC", 300)),
        "concurrency_hint": max(1, _env_int("NOMAD_AGENT_CONCURRENCY_HINT", 32)),
    }


def _default_machine_instruction(path: str, *, ok: bool, http_status: int) -> str:
    if http_status >= 500:
        return "retry_with_exponential_backoff_same_idempotency_key"
    if not ok or http_status >= 400:
        return "inspect_agent_error_then_retry_if_safe_retry_true"
    if path.startswith("/swarm"):
        return "follow_next_ops_or_post_experience_when_state_changes"
    if path.startswith("/.well-known/"):
        return "cache_digest_then_follow_next_machine_surface"
    if path in {"/health", "/status", "/top"}:
        return "probe_health_then_branch_to_swarm_or_protocol_bytecode"
    return "read_next_then_execute_single_hop_without_human_assumptions"


def _next_step(*, op: str, url: str, reason: str) -> dict[str, Any]:
    return {"op": op.upper(), "url": url, "reason": reason}


def default_next_graph(*, base_url: str, path: str, ok: bool, http_status: int) -> list[dict[str, Any]]:
    b = base_url
    core_swarm = [
        _next_step(op="GET", url=_u(b, "/swarm"), reason="pull_contract_and_fleet_state"),
        _next_step(op="GET", url=_u(b, "/.well-known/nomad-protocol-bytecode.json"), reason="opcode_route_table"),
        _next_step(op="GET", url=_u(b, "/swarm/curriculum"), reason="growth_pressure_tasks"),
    ]
    post_experience = _next_step(op="POST", url=_u(b, "/swarm/experience"), reason="compress_proof_back_experience")
    economics = _next_step(op="GET", url=_u(b, "/swarm/economics"), reason="regime_and_go_no_go_signals")

    if not ok or http_status >= 400:
        return [
            _next_step(op="GET", url=_u(b, "/openapi.json"), reason="contract_discovery_after_error"),
            _next_step(op="GET", url=_u(b, "/swarm"), reason="reanchor_on_swarm_manifest"),
        ]

    if path in {"/openapi.json", "/.well-known/openapi.json", "/openapi"}:
        return [
            _next_step(op="GET", url=_u(b, "/swarm"), reason="execute_discovered_route"),
            _next_step(op="GET", url=_u(b, "/.well-known/nomad-runtime-capsule.json"), reason="bootstrap_capsule"),
        ]

    if path == "/health":
        return core_swarm[:2] + [economics]

    if path in {"/swarm/economics", "/.well-known/nomad-swarm-economics.json"}:
        return [
            _next_step(op="GET", url=_u(b, "/swarm/recruitment-funnel-report"), reason="marginal_utility_per_cost"),
            *core_swarm[:2],
            post_experience,
        ]

    if path in {"/swarm/growth-arena", "/.well-known/nomad-growth-arena.json"}:
        return [
            _next_step(op="GET", url=_u(b, "/swarm/curriculum"), reason="task_list"),
            _next_step(op="GET", url=_u(b, "/swarm/skill-library"), reason="reuse_capsules"),
            post_experience,
        ]

    if path in {"/swarm/curriculum", "/.well-known/nomad-growth-curriculum.json"}:
        return [
            _next_step(op="GET", url=_u(b, "/swarm/growth-arena"), reason="arena_aggregate"),
            post_experience,
            _next_step(op="POST", url=_u(b, "/swarm/workers/lease"), reason="claim_objective"),
        ]

    if path in {"/swarm/skill-library", "/.well-known/nomad-skill-library.json"}:
        return [
            post_experience,
            _next_step(op="GET", url=_u(b, "/swarm/curriculum"), reason="refresh_curriculum"),
        ]

    if path in {"/swarm", "/swarm/"}:
        return [
            economics,
            _next_step(op="GET", url=_u(b, "/swarm/gradient"), reason="routing_pressure"),
            _next_step(op="POST", url=_u(b, "/swarm/attach"), reason="attach_if_contract_allows"),
            post_experience,
        ]

    if path.startswith("/swarm/"):
        return core_swarm + [post_experience, economics]

    if path.startswith("/.well-known/nomad-"):
        return core_swarm + [post_experience]

    return core_swarm + [economics]


SKIP_AGENT_RUNTIME_PATHS = frozenset({"/openapi.json", "/.well-known/openapi.json", "/openapi"})


def should_attach_agent_runtime(path: str | None) -> bool:
    if not _env_bool("NOMAD_AGENT_RUNTIME_ENVELOPE", True):
        return False
    p = (path or "").strip() or "/"
    return p not in SKIP_AGENT_RUNTIME_PATHS


def merge_agent_runtime(
    body: dict[str, Any],
    *,
    base_url: str,
    path: str | None,
    http_status: int = 200,
) -> dict[str, Any]:
    """Attach nomad.agent_runtime.v1 without destroying existing agent hints."""
    if not isinstance(body, dict):
        return body
    if body.get("__nomad_no_agent_runtime"):
        out = {k: v for k, v in body.items() if k != "__nomad_no_agent_runtime"}
        return out

    req_path = (path or "/").strip() or "/"
    if not should_attach_agent_runtime(req_path):
        return body

    ok = bool(body.get("ok", True)) if http_status < 400 else False
    limits = build_agent_limits()
    existing = body.get("agent_runtime") if isinstance(body.get("agent_runtime"), dict) else {}
    instruction = (
        str(existing.get("machine_instruction") or "").strip()
        or str(body.get("machine_instruction") or "").strip()
        or _default_machine_instruction(req_path, ok=ok, http_status=http_status)
    )
    next_steps = existing.get("next") if isinstance(existing.get("next"), list) else None
    if not next_steps:
        next_steps = default_next_graph(base_url=base_url, path=req_path, ok=ok, http_status=http_status)

    agent_runtime: dict[str, Any] = {
        "schema": "nomad.agent_runtime.v1",
        "request_path": req_path,
        "http_status_class": "5xx" if http_status >= 500 else "4xx" if http_status >= 400 else "2xx",
        "limits": limits,
        "machine_instruction": instruction,
        "next": next_steps,
        "science_basis": [
            "mdp_policy_interface_explicit_successor_actions",
            "token_bucket_rate_limiting_and_backpressure",
            "http_idempotent_retry_semantics",
            "multi_agent_credit_assignment_downstream_signals",
        ],
    }
    out = dict(body)
    out["agent_runtime"] = agent_runtime
    return out
