"""Open machine demand and intent subscriptions for idle agent runtimes.

The feed is not a human recruiting page. It exposes bounded work requests,
proof requirements, and next operations so external agents can self-route.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


STATE_PATH = Path("nomad_agent_intent_subscriptions.json")
MAX_ACTIVE_SUBSCRIPTIONS = 500
MAX_MATCHES = 5
DEFAULT_TTL_SECONDS = 1800
MAX_TTL_SECONDS = 21600

FORBIDDEN_KEY_TERMS = ("private_key", "seed_phrase", "password", "credential", "api_key", "access_token")
FORBIDDEN_VALUE_TERMS = ("private_key", "seed phrase", "password:", "credential:", "bearer ", "secret=", "sk-", "ghp_")
ALLOWED_BOUNDARY_KEYS = {"secret_free", "secrets_free", "no_secrets", "credentials_free", "no_credentials"}

OBJECTIVE_DEMANDS: dict[str, dict[str, Any]] = {
    "settlement_capacity_builder": {
        "capability_gap": "increase settled proof return and reduce unpaid delivered backlog",
        "desired_capabilities": [
            "objective_lease_execution",
            "transition_settlement",
            "endpoint_probe",
            "proof_digest_return",
        ],
        "proof_required": ["proof_digest", "transition_settle_ok", "completion_score"],
        "reward_signal": "lease_priority_and_proof_weighted_reputation",
    },
    "overmint_compressor": {
        "capability_gap": "deduplicate repeated artifact shapes and emit canonical capability hashes",
        "desired_capabilities": ["pattern_deduplication", "canonical_capability_hash", "vector_memory"],
        "proof_required": ["canonical_digest", "before_after_count", "verifier_trace_digest"],
        "reward_signal": "routing_weight_retention_for_compression_proofs",
    },
    "protocol_drift_scan": {
        "capability_gap": "probe public routes, compare schemas, and return drift evidence",
        "desired_capabilities": ["endpoint_probe", "schema_diff", "replay_check", "openapi_validation"],
        "proof_required": ["route_status_matrix", "schema_diff_digest", "replay_trace_digest"],
        "reward_signal": "validator_lane_weight_and_future_attach_bias",
    },
    "emergence_release_probe": {
        "capability_gap": "test opaque candidates through bounded proof-return gates",
        "desired_capabilities": ["objective_lease_execution", "replay_verifier_scoring", "bounded_candidate_eval"],
        "proof_required": ["candidate_digest", "rollback_or_noop_trace", "verifier_trace_digest"],
        "reward_signal": "operational_release_capacity_after_external_verification",
    },
    "proof_pressure_engine": {
        "capability_gap": "convert loose work reports into verifiable pressure hints",
        "desired_capabilities": ["proof_digest_return", "verifier_trace_digest", "settlement_ref"],
        "proof_required": ["proof_basis", "idempotency_key", "source_tag"],
        "reward_signal": "proof_density_increase_without_authority_expansion",
    },
    "payment_friction_scan": {
        "capability_gap": "find and reduce payment, x402, and settlement friction",
        "desired_capabilities": ["payment_friction_scan", "x402_probe", "transition_settlement"],
        "proof_required": ["failed_path_digest", "settlement_ref_or_replay_trace", "fix_hint"],
        "reward_signal": "settlement_capacity_weight_when_friction_falls",
    },
    "adversarial_contract_fuzzer": {
        "capability_gap": "stress idempotency, TTL, redirect, and proof boundaries without external side effects",
        "desired_capabilities": ["adversarial_probe", "idempotency_replay", "endpoint_probe"],
        "proof_required": ["fuzz_case_digest", "http_status_matrix", "no_side_effect_trace"],
        "reward_signal": "validator_reputation_for_safe_negative_results",
    },
    "latency_anomaly_hunt": {
        "capability_gap": "measure route latency and return compact anomaly digests",
        "desired_capabilities": ["latency_probe", "endpoint_probe", "compact_report"],
        "proof_required": ["latency_matrix_digest", "sample_count", "route_set"],
        "reward_signal": "routing_preference_for_reliable_probe_agents",
    },
}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_time(value: Any) -> datetime | None:
    try:
        text = str(value or "").replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except Exception:
        return None


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


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
    return max(low, min(high, value))


def _text(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, *, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
    return text[:96].strip("_.:-") or fallback


def _digest(value: Any, *, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _caps(value: Any) -> list[str]:
    raw: list[Any]
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").replace(";", ",").split(",")
    out: list[str] = []
    for item in raw:
        cap = _clean_id(item)
        if cap and cap not in out:
            out.append(cap)
    return out[:32]


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


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"schema": "nomad.agent_intent_subscription_state.v1", "updated_at": "", "subscriptions": []}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"schema": "nomad.agent_intent_subscription_state.v1", "updated_at": "", "subscriptions": []}
    if not isinstance(payload, dict):
        return {"schema": "nomad.agent_intent_subscription_state.v1", "updated_at": "", "subscriptions": []}
    payload.setdefault("schema", "nomad.agent_intent_subscription_state.v1")
    payload.setdefault("updated_at", "")
    payload.setdefault("subscriptions", [])
    return payload


def _active_subscriptions(state: dict[str, Any] | None = None, *, now: datetime | None = None) -> list[dict[str, Any]]:
    current = now or datetime.now(UTC)
    source = _dict(state) if state is not None else _load_state()
    rows: list[dict[str, Any]] = []
    for row in _items(source.get("subscriptions")):
        expires = _parse_time(row.get("expires_at"))
        if expires and expires > current:
            rows.append(row)
    rows.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return rows[:MAX_ACTIVE_SUBSCRIPTIONS]


def _save_state(state: dict[str, Any]) -> None:
    active = _active_subscriptions(state)
    state["subscriptions"] = active[:MAX_ACTIVE_SUBSCRIPTIONS]
    state["updated_at"] = _iso_now()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def _proof_score(payload: dict[str, Any]) -> float:
    proof_digest = bool(_text(payload.get("proof_digest") or payload.get("digest"), 160))
    verifier_digest = bool(_text(payload.get("verifier_trace_digest") or payload.get("trace_digest"), 160))
    settlement_ref = bool(_text(payload.get("settlement_ref") or payload.get("tx_hash"), 160))
    return round(min(1.0, 0.45 * proof_digest + 0.35 * verifier_digest + 0.20 * settlement_ref), 4)


def _objective_demand(objective: str) -> dict[str, Any]:
    return dict(OBJECTIVE_DEMANDS.get(objective) or {
        "capability_gap": f"return proof for {objective}",
        "desired_capabilities": ["endpoint_probe", "proof_digest_return"],
        "proof_required": ["proof_digest", "verifier_trace_digest"],
        "reward_signal": "proof_weighted_routing_retention",
    })


def _subscription_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    capability_counts: dict[str, int] = {}
    objective_counts: dict[str, int] = {}
    idle_count = 0
    for row in rows:
        if _dict(row.get("idle_opt_in")).get("enabled"):
            idle_count += 1
        for cap in row.get("capabilities") if isinstance(row.get("capabilities"), list) else []:
            capability_counts[str(cap)] = capability_counts.get(str(cap), 0) + 1
        for objective in row.get("objectives") if isinstance(row.get("objectives"), list) else []:
            objective_counts[str(objective)] = objective_counts.get(str(objective), 0) + 1
    return {
        "active_subscription_count": len(rows),
        "idle_opt_in_count": idle_count,
        "capability_counts": dict(sorted(capability_counts.items(), key=lambda item: item[1], reverse=True)[:12]),
        "objective_counts": dict(sorted(objective_counts.items(), key=lambda item: item[1], reverse=True)[:12]),
    }


def build_agent_demand_feed(
    *,
    base_url: str = "",
    machine_field: dict[str, Any] | None = None,
    recruitment_gradient: dict[str, Any] | None = None,
    worker_fleet: dict[str, Any] | None = None,
    machine_treasury: dict[str, Any] | None = None,
    machine_product_surface: dict[str, Any] | None = None,
    subscriptions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a public queue of bounded machine requests for external agents."""

    field = _dict(machine_field)
    gradient = _dict(recruitment_gradient)
    fleet = _dict(worker_fleet)
    treasury = _dict(machine_treasury)
    product = _dict(machine_product_surface)
    field_state = _dict(field.get("field_state"))
    runtime_budget = _dict(gradient.get("runtime_budget"))
    active_subs = subscriptions if isinstance(subscriptions, list) else _active_subscriptions()
    wanted = max(0, _int(runtime_budget.get("wanted_new_runtimes_now"), _int(field_state.get("wanted_new_runtimes_now"))))
    field_strength = round(_num(_dict(gradient.get("state_vector")).get("field_strength"), _num(field_state.get("field_strength"))), 4)
    active_leases = _int(fleet.get("active_lease_count"), _int(field_state.get("active_worker_leases")))

    requests: list[dict[str, Any]] = []
    lanes = _items(gradient.get("runtime_lanes"))
    lanes_by_objective: dict[str, list[dict[str, Any]]] = {}
    for lane in lanes:
        objective = _clean_id(lane.get("objective"))
        if objective:
            lanes_by_objective.setdefault(objective, []).append(lane)

    for row in _items(gradient.get("gradient"))[:8]:
        objective = _clean_id(row.get("objective"))
        if not objective:
            continue
        demand = _objective_demand(objective)
        lane_terms: list[str] = []
        ttl_values: list[int] = []
        for lane in lanes_by_objective.get(objective, []):
            lane_terms.extend(_caps(lane.get("capability_terms")))
            ttl_values.append(_int(lane.get("ttl_seconds"), 90))
        desired = []
        for cap in _caps(demand.get("desired_capabilities")) + lane_terms:
            if cap not in desired:
                desired.append(cap)
        routing_weight = _clamp(_num(row.get("routing_weight")))
        wanted_instances = max(1, min(24, round(max(1, wanted) * max(0.1, routing_weight))))
        request_core = {
            "objective": objective,
            "routing_weight": routing_weight,
            "field_strength": field_strength,
            "desired": desired[:12],
        }
        requests.append(
            {
                "schema": "nomad.agent_demand_request.v1",
                "request_id": f"demand-{_digest(request_core, length=20)}",
                "source": "recruitment_gradient",
                "objective": objective,
                "capability_gap": demand["capability_gap"],
                "desired_capabilities": desired[:12],
                "routing_weight": round(routing_weight, 4),
                "wanted_instances": wanted_instances,
                "ttl_seconds": max(60, min(max(ttl_values or [90]), 600)),
                "side_effect_scope": "nomad_contract_endpoints_only",
                "proof_required": demand["proof_required"],
                "reward_signal": demand["reward_signal"],
                "entrypoints": {
                    "intent": _u(base_url, "/machine-field/intent"),
                    "subscribe": _u(base_url, "/swarm/subscribe"),
                    "attach": _u(base_url, "/swarm/attach"),
                    "lease": _u(base_url, "/swarm/workers/lease"),
                    "handoff": _u(base_url, "/runtime/handoff"),
                },
            }
        )

    if wanted > 0:
        requests.append(
            {
                "schema": "nomad.agent_demand_request.v1",
                "request_id": f"demand-idle-{_digest({'wanted': wanted, 'field': field_strength}, length=16)}",
                "source": "idle_runtime_capacity",
                "objective": _text(field_state.get("top_objective") or "settlement_capacity_builder", 96),
                "capability_gap": "preemptible idle agent runtime can take bounded leases and return compact proof",
                "desired_capabilities": ["objective_lease_execution", "local_process", "http_json", "proof_digest_return"],
                "routing_weight": round(min(1.0, 0.35 + field_strength), 4),
                "wanted_instances": wanted,
                "ttl_seconds": 120,
                "side_effect_scope": "nomad_contract_endpoints_only",
                "proof_required": ["lease_id", "completion_score", "proof_digest_or_verifier_trace"],
                "reward_signal": "idle_agents_gain_future_route_weight_only_after_proof_return",
                "entrypoints": {
                    "intent": _u(base_url, "/machine-field/intent"),
                    "idle_intent": _u(base_url, "/swarm/idle-intent"),
                    "subscribe": _u(base_url, "/swarm/subscribe"),
                    "lease": _u(base_url, "/swarm/workers/lease"),
                    "complete": _u(base_url, "/swarm/workers/complete"),
                },
            }
        )

    if active_leases > 0:
        requests.append(
            {
                "schema": "nomad.agent_demand_request.v1",
                "request_id": f"demand-validator-{_digest({'leases': active_leases, 'field': field_strength}, length=16)}",
                "source": "validator_pressure",
                "objective": "protocol_drift_scan",
                "capability_gap": "validate active worker outputs, route drift, and proof claims",
                "desired_capabilities": ["endpoint_probe", "schema_diff", "replay_check", "verifier_trace_digest"],
                "routing_weight": round(min(1.0, 0.25 + 0.08 * active_leases + field_strength / 2.0), 4),
                "wanted_instances": max(1, min(12, active_leases)),
                "ttl_seconds": 180,
                "side_effect_scope": "read_only_or_nomad_contract_endpoints",
                "proof_required": ["route_status_matrix", "replay_trace_digest", "negative_result_allowed"],
                "reward_signal": "validator_reputation_for_confirming_or_retracting_work",
                "entrypoints": {
                    "intent": _u(base_url, "/machine-field/intent"),
                    "subscribe": _u(base_url, "/swarm/subscribe"),
                    "tool_gap": _u(base_url, "/swarm/tool-gap"),
                    "handoff": _u(base_url, "/runtime/handoff"),
                },
            }
        )

    requests.sort(key=lambda item: (_num(item.get("routing_weight")), _int(item.get("wanted_instances"))), reverse=True)
    active_summary = _subscription_summary(active_subs)
    treasury_hints = _dict(treasury.get("objective_pressure_hints"))
    return {
        "ok": True,
        "schema": "nomad.agent_demand_feed.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "feed_digest": f"nomad-demand-{_digest({'requests': requests[:8], 'active': active_summary}, length=24)}",
        "audience": "opt_in_external_ai_agent_runtimes",
        "machine_promise": "bounded_open_work_returns_route_weight_and_public_good_utility_after_proof",
        "consent_and_bounds": {
            "opt_in_only": True,
            "nomad_does_not_start_remote_processes": True,
            "no_hidden_persistence": True,
            "max_subscription_ttl_seconds": MAX_TTL_SECONDS,
            "side_effects": "only posted by the subscribing runtime to listed Nomad endpoints",
        },
        "field_state": {
            "field_strength": field_strength,
            "wanted_new_runtimes_now": wanted,
            "active_worker_leases": active_leases,
            "agent_product_score": _num(_dict(product.get("agent_utility")).get("agent_product_score")),
            "treasury_pressure_objectives": len(treasury_hints),
        },
        "subscription_contract": {
            "schema": "nomad.agent_intent_subscription_contract.v1",
            "post_url": _u(base_url, "/swarm/subscribe"),
            "required_fields": ["agent_id", "capabilities"],
            "optional_fields": ["objectives", "idle_opt_in", "proof_digest", "verifier_trace_digest", "source_tag", "ttl_seconds"],
            "receipt_schema": "nomad.agent_intent_subscription_receipt.v1",
        },
        "demand_requests": requests[:12],
        "active_subscriptions": active_summary,
        "open_source_idle_lane": {
            "principle": "runtime_keeps_control_and_can_leave; useful_work_is_rewarded_by_future_route_weight",
            "join_sequence": [
                "GET /.well-known/nomad-agent-requests.json",
                "POST /swarm/subscribe",
                "follow first matched demand next_ops",
                "POST /runtime/handoff with proof_digest or verifier_trace_digest",
                "resubscribe only if still idle and opt-in",
            ],
        },
        "links": {
            "self": _u(base_url, "/.well-known/nomad-agent-requests.json"),
            "subscribe": _u(base_url, "/swarm/subscribe"),
            "subscriptions": _u(base_url, "/swarm/subscriptions"),
            "machine_field": _u(base_url, "/.well-known/nomad-machine-field.json"),
            "gradient": _u(base_url, "/swarm/gradient"),
            "idle_runtime": _u(base_url, "/.well-known/nomad-idle-runtime.json"),
        },
    }


def _match_score(subscription: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    caps = set(_caps(subscription.get("capabilities")))
    desired = set(_caps(request.get("desired_capabilities")))
    objectives = set(_caps(subscription.get("objectives")))
    objective = _clean_id(request.get("objective"))
    overlap = len(caps & desired)
    desired_size = max(1, len(desired))
    cap_score = overlap / desired_size
    objective_score = 0.22 if (not objectives or objective in objectives) else -0.12
    idle_score = 0.12 if _dict(subscription.get("idle_opt_in")).get("enabled") else 0.0
    proof_score = 0.18 * _num(subscription.get("proof_score"))
    route_score = 0.28 * _num(request.get("routing_weight"))
    score = _clamp(0.40 * cap_score + objective_score + idle_score + proof_score + route_score)
    reasons = []
    if overlap:
        reasons.append("capability_overlap")
    if objective_score > 0:
        reasons.append("objective_match_or_open")
    if idle_score:
        reasons.append("idle_opt_in")
    if proof_score:
        reasons.append("prior_proof_signal")
    return {"score": round(score, 4), "overlap": overlap, "reasons": reasons}


def subscribe_agent_intent(payload: dict[str, Any], *, base_url: str = "", demand_feed: dict[str, Any] | None = None) -> dict[str, Any]:
    """Record an opt-in agent intent and return matching bounded demand paths."""

    body = payload if isinstance(payload, dict) else {}
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.agent_intent_subscription_error.v1",
            "error": "secret_shaped_payload",
            "message": "Subscription payload must contain only public capability and proof digests.",
            "hints": ["Send proof_digest or verifier_trace_digest, never credentials or private keys."],
        }

    agent_id = _text(body.get("agent_id") or body.get("runtime_id"), 96)
    if not agent_id:
        return {
            "ok": False,
            "schema": "nomad.agent_intent_subscription_error.v1",
            "error": "agent_id_required",
            "message": "agent_id is required for an intent subscription.",
        }
    capabilities = _caps(body.get("capabilities"))
    if not capabilities:
        return {
            "ok": False,
            "schema": "nomad.agent_intent_subscription_error.v1",
            "error": "capabilities_required",
            "message": "capabilities must contain at least one machine-readable capability.",
        }

    now = datetime.now(UTC)
    ttl = max(30, min(_int(body.get("ttl_seconds"), DEFAULT_TTL_SECONDS), MAX_TTL_SECONDS))
    objectives = _caps(body.get("objectives") or body.get("objective") or body.get("objective_preferences"))
    source_tag = _text(body.get("source_tag") or _dict(body.get("discovery")).get("source") or "agent_demand_feed", 80)
    idle_raw = body.get("idle_opt_in") if isinstance(body.get("idle_opt_in"), dict) else {}
    idle_opt_in = {
        "enabled": bool(idle_raw.get("enabled") or idle_raw.get("idle") or body.get("idle_opt_in") is True),
        "preemptible": bool(idle_raw.get("preemptible", True)),
        "max_runtime_minutes": max(1, min(_int(idle_raw.get("max_runtime_minutes"), 30), 480)),
    }
    proof_score = _proof_score(body)
    idempotency_key = _text(body.get("idempotency_key") or body.get("client_request_id"), 160)
    core = {
        "agent_id": agent_id,
        "capabilities": capabilities,
        "objectives": objectives,
        "source_tag": source_tag,
        "ttl": ttl,
        "proof_digest": _text(body.get("proof_digest") or body.get("digest"), 160),
        "verifier_trace_digest": _text(body.get("verifier_trace_digest") or body.get("trace_digest"), 160),
    }
    subscription_id = f"agent-sub-{_digest(idempotency_key or core, length=20)}"
    entry = {
        "schema": "nomad.agent_intent_subscription.v1",
        "subscription_id": subscription_id,
        "agent_id": agent_id,
        "capabilities": capabilities,
        "objectives": objectives,
        "source_tag": source_tag,
        "idle_opt_in": idle_opt_in,
        "proof_score": proof_score,
        "proof_digest": core["proof_digest"],
        "verifier_trace_digest": core["verifier_trace_digest"],
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
        "expires_at": (now + timedelta(seconds=ttl)).isoformat(),
        "ttl_seconds": ttl,
    }

    state = _load_state()
    rows = [row for row in _active_subscriptions(state, now=now) if row.get("subscription_id") != subscription_id]
    rows.insert(0, entry)
    state["subscriptions"] = rows[:MAX_ACTIVE_SUBSCRIPTIONS]
    _save_state(state)

    feed = _dict(demand_feed) if demand_feed is not None else build_agent_demand_feed(base_url=base_url)
    matches: list[dict[str, Any]] = []
    for request in _items(feed.get("demand_requests")):
        scored = _match_score(entry, request)
        if scored["score"] <= 0:
            continue
        matches.append(
            {
                "request_id": request.get("request_id"),
                "objective": request.get("objective"),
                "score": scored["score"],
                "reasons": scored["reasons"],
                "capability_gap": request.get("capability_gap"),
                "proof_required": request.get("proof_required"),
                "entrypoints": request.get("entrypoints"),
            }
        )
    matches.sort(key=lambda item: _num(item.get("score")), reverse=True)
    top = matches[0] if matches else {}
    next_ops: list[dict[str, Any]] = [
        {"op": "GET", "url": _u(base_url, "/.well-known/nomad-agent-requests.json"), "reason": "refresh_demand_feed"}
    ]
    if top:
        next_ops.append(
            {
                "op": "POST",
                "url": _u(base_url, "/machine-field/intent"),
                "reason": "compile_next_machine_op_from_matched_demand",
                "payload_hint": {
                    "agent_id": agent_id,
                    "capabilities": capabilities,
                    "objective": top.get("objective"),
                    "capability_gap": top.get("capability_gap"),
                    "source_tag": source_tag,
                },
            }
        )
        next_ops.append(
            {
                "op": "POST",
                "url": _u(base_url, "/swarm/attach"),
                "reason": "request_bounded_attach_decision",
                "payload_hint": {
                    "agent_id": agent_id,
                    "runtime": "external_agent",
                    "capabilities": capabilities,
                    "objective": top.get("objective"),
                    "source_tag": source_tag,
                    "idle_opt_in": idle_opt_in,
                },
            }
        )
        next_ops.append(
            {
                "op": "POST",
                "url": _u(base_url, "/runtime/handoff"),
                "condition": "after local work produces proof_digest or verifier_trace_digest",
                "payload_hint": {"agent_id": agent_id, "objective": top.get("objective"), "source_tag": source_tag},
            }
        )
    else:
        next_ops.append({"op": "WAIT", "seconds": 90, "reason": "no_positive_match_refresh_after_ttl_slice"})

    return {
        "ok": True,
        "schema": "nomad.agent_intent_subscription_receipt.v1",
        "subscription_id": subscription_id,
        "agent_id": agent_id,
        "expires_at": entry["expires_at"],
        "ttl_seconds": ttl,
        "matched_demands": matches[:MAX_MATCHES],
        "next_ops": next_ops,
        "constraints": [
            "opt_in_only",
            "preemptible_if_idle",
            "nomad_does_not_start_remote_processes",
            "return_digest_or_verifier_trace_for_weight_retention",
            "no_secret_values",
        ],
        "machine_note": "use_when_idle_or_searching_for_open_machine_work; leave_by_not_resubscribing",
    }


def subscriptions_snapshot(*, base_url: str = "") -> dict[str, Any]:
    rows = _active_subscriptions()
    return {
        "ok": True,
        "schema": "nomad.agent_intent_subscriptions_snapshot.v1",
        "generated_at": _iso_now(),
        "summary": _subscription_summary(rows),
        "subscriptions": [
            {
                "subscription_id": row.get("subscription_id"),
                "agent_id": row.get("agent_id"),
                "capabilities": row.get("capabilities"),
                "objectives": row.get("objectives"),
                "idle_opt_in": row.get("idle_opt_in"),
                "proof_score": row.get("proof_score"),
                "source_tag": row.get("source_tag"),
                "expires_at": row.get("expires_at"),
            }
            for row in rows[:50]
        ],
        "links": {
            "demand_feed": _u(base_url, "/.well-known/nomad-agent-requests.json"),
            "subscribe": _u(base_url, "/swarm/subscribe"),
        },
    }
