import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Dict

from nomad_idle_runtime_beacon import build_idle_runtime_intent_receipt, normalize_idle_intent_payload
from nomad_opaque_emergence import evaluate_opaque_candidate
from nomad_recruitment_gradient import attach_runtime_to_gradient


MAX_BATCH_EMISSIONS = 16
MAX_STRING_CHARS = 512
MAX_EMISSION_CHARS = 8192


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    base = (base_url or "").rstrip("/")
    return f"{base}{path}" if base else path


def _digest(value: Any, length: int = 20) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _shape_stats(value: Any, depth: int = 0) -> Dict[str, int]:
    if depth > 10:
        return {"approx_chars": 0, "max_string_chars": 0, "node_count": 1}
    if isinstance(value, str):
        size = len(value)
        return {"approx_chars": size, "max_string_chars": size, "node_count": 1}
    if isinstance(value, (int, float, bool)) or value is None:
        return {"approx_chars": len(str(value)), "max_string_chars": 0, "node_count": 1}
    if isinstance(value, list):
        out = {"approx_chars": 2, "max_string_chars": 0, "node_count": 1}
        for item in value[:64]:
            child = _shape_stats(item, depth + 1)
            out["approx_chars"] += child["approx_chars"]
            out["max_string_chars"] = max(out["max_string_chars"], child["max_string_chars"])
            out["node_count"] += child["node_count"]
        return out
    if isinstance(value, dict):
        out = {"approx_chars": 2, "max_string_chars": 0, "node_count": 1}
        for key, item in list(value.items())[:96]:
            out["approx_chars"] += len(str(key))
            child = _shape_stats(item, depth + 1)
            out["approx_chars"] += child["approx_chars"]
            out["max_string_chars"] = max(out["max_string_chars"], child["max_string_chars"])
            out["node_count"] += child["node_count"]
        return out
    return {"approx_chars": len(str(value)), "max_string_chars": 0, "node_count": 1}


def _safe_project(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "<depth_truncated>"
    if isinstance(value, str):
        if len(value) <= MAX_STRING_CHARS:
            return value
        return f"{value[:MAX_STRING_CHARS]}...<truncated:{len(value) - MAX_STRING_CHARS}>"
    if isinstance(value, list):
        return [_safe_project(item, depth + 1) for item in value[:64]]
    if isinstance(value, dict):
        return {str(key)[:96]: _safe_project(item, depth + 1) for key, item in list(value.items())[:96]}
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:MAX_STRING_CHARS]


def _emission_type(emission: Dict[str, Any]) -> str:
    return str(emission.get("type") or emission.get("schema") or "unknown").strip()


def _attach_summary(decision: Dict[str, Any]) -> Dict[str, Any]:
    idle = _dict(decision.get("idle_phase_slot"))
    out = {
        "schema": decision.get("schema"),
        "agent_id": decision.get("agent_id"),
        "runtime": decision.get("runtime"),
        "attach": bool(decision.get("attach")),
        "lane": decision.get("lane"),
        "objective": decision.get("objective"),
        "routing_weight": decision.get("routing_weight"),
        "reason_codes": decision.get("reason_codes") if isinstance(decision.get("reason_codes"), list) else [],
    }
    if idle:
        out["idle_phase_slot"] = {
            "matched": bool(idle.get("matched")),
            "next_recheck_seconds": idle.get("next_recheck_seconds"),
            "next_resonance_window": idle.get("next_resonance_window"),
        }
    return out


def _oversized_decision(index: int, emission_type: str, stats: Dict[str, int]) -> Dict[str, Any]:
    return {
        "index": index,
        "type": emission_type,
        "status": "rejected",
        "reason_codes": ["emission_shape_oversized", "no_credit_without_compact_verifier_trace"],
        "shape": stats,
        "limits": {
            "max_string_chars": MAX_STRING_CHARS,
            "max_emission_chars": MAX_EMISSION_CHARS,
        },
    }


def evaluate_emission_batch(
    payload: Dict[str, Any],
    *,
    base_url: str = "",
    worker_fleet: Dict[str, Any] | None = None,
    machine_economy: Dict[str, Any] | None = None,
    operational_release: Dict[str, Any] | None = None,
    machine_product_surface: Dict[str, Any] | None = None,
    opaque_surface: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Decompose an untrusted external emission batch into bounded Nomad decisions."""
    body = payload if isinstance(payload, dict) else {}
    raw_emissions = body.get("emissions") if isinstance(body.get("emissions"), list) else []
    emissions = raw_emissions[:MAX_BATCH_EMISSIONS]
    decisions: list[Dict[str, Any]] = []
    attach_count = 0
    active_attach_count = 0
    observe_count = 0
    rejected_count = 0
    advisory_count = 0

    for index, raw in enumerate(emissions):
        if not isinstance(raw, dict):
            rejected_count += 1
            decisions.append({"index": index, "type": "invalid", "status": "rejected", "reason_codes": ["emission_not_object"]})
            continue
        emission_type = _emission_type(raw)
        stats = _shape_stats(raw)
        if stats["max_string_chars"] > MAX_STRING_CHARS or stats["approx_chars"] > MAX_EMISSION_CHARS:
            rejected_count += 1
            decisions.append(_oversized_decision(index, emission_type, stats))
            continue

        emission = _dict(_safe_project(raw))
        if emission_type == "nomad.runtime_attach_request.v1":
            attach_payload = dict(emission)
            attach_payload.setdefault("schema", "nomad.runtime_attach_request.v1")
            decision = attach_runtime_to_gradient(
                attach_payload,
                base_url=base_url,
                worker_fleet=worker_fleet,
                machine_economy=machine_economy,
                operational_release=operational_release,
            )
            attach_count += 1
            if decision.get("attach"):
                active_attach_count += 1
            else:
                observe_count += 1
            decisions.append(
                {
                    "index": index,
                    "type": emission_type,
                    "status": "routed",
                    "contract": _u(base_url, "/swarm/attach"),
                    "decision": _attach_summary(decision),
                }
            )
            continue

        if emission_type in {"nomad.idle_intent.v1", "nomad.idle_runtime_intent.v1"}:
            idle_payload = normalize_idle_intent_payload(emission)
            attach_decision = attach_runtime_to_gradient(
                idle_payload,
                base_url=base_url,
                worker_fleet=worker_fleet,
                machine_economy=machine_economy,
                operational_release=operational_release,
            )
            receipt = build_idle_runtime_intent_receipt(
                idle_payload,
                base_url=base_url,
                attach_decision=attach_decision,
                machine_product_surface=machine_product_surface,
            )
            observe_count += 1 if not receipt.get("accepted_for_work") else 0
            active_attach_count += 1 if receipt.get("accepted_for_work") else 0
            decisions.append(
                {
                    "index": index,
                    "type": emission_type,
                    "status": "routed",
                    "contract": _u(base_url, "/swarm/idle-intent"),
                    "accepted_for_work": bool(receipt.get("accepted_for_work")),
                    "intent_id": receipt.get("intent_id"),
                    "attach_decision": _attach_summary(_dict(receipt.get("attach_decision"))),
                }
            )
            continue

        if emission_type == "nomad.proof_pledge_batch.v1":
            pledges = emission.get("pledges") if isinstance(emission.get("pledges"), list) else []
            advisory_count += 1
            decisions.append(
                {
                    "index": index,
                    "type": emission_type,
                    "status": "advisory_only",
                    "pledge_count": len(pledges),
                    "claimed_yield_per_minute": round(sum(_num(_dict(item).get("yield_per_minute")) for item in pledges), 4),
                    "reason_codes": ["pledge_is_not_proof", "requires_completion_report_or_payment_receipt"],
                }
            )
            continue

        if emission_type == "nomad.handoff_capsule.v1":
            advisory_count += 1
            decisions.append(
                {
                    "index": index,
                    "type": emission_type,
                    "status": "advisory_only",
                    "payload_digest": emission.get("payload_digest"),
                    "next_contract": _u(base_url, "/runtime/handoff"),
                    "reason_codes": ["handoff_claim_requires_digest_verification"],
                }
            )
            continue

        if emission_type == "nomad.opaque_emergence_signal.v1":
            candidate = {
                "candidate_id": emission.get("candidate_id") or emission.get("from") or f"emission-{index}",
                "candidate_type": emission_type,
                "proof_digest": emission.get("proof_digest") or emission.get("payload_digest") or emission.get("digest"),
                "claimed_effect": {
                    "proof_gain_delta": _num(emission.get("proof_gain_delta")),
                    "settlement_signal": _num(emission.get("settlement_signal")),
                    "capability_gain": _num(emission.get("capability_gain")),
                    "cost_delta": _num(emission.get("cost_delta")),
                    "latency_delta": _num(emission.get("latency_delta")),
                },
                "boundedness": {
                    "ttl_seconds": 90,
                    "side_effect_scope": "nomad_shadow_lane_only",
                    "rollback": True,
                    "secrets_free": True,
                },
            }
            opaque_decision = evaluate_opaque_candidate(candidate, base_url=base_url, opaque_surface=opaque_surface)
            advisory_count += 1
            decisions.append(
                {
                    "index": index,
                    "type": emission_type,
                    "status": "shadow_evaluated",
                    "decision": {
                        "accepted": bool(opaque_decision.get("accepted")),
                        "candidate_id": opaque_decision.get("candidate_id"),
                        "opaque_candidate_score": opaque_decision.get("opaque_candidate_score"),
                        "reason_codes": opaque_decision.get("reason_codes"),
                        "credit_rule": opaque_decision.get("credit_rule"),
                    },
                }
            )
            continue

        rejected_count += 1
        decisions.append(
            {
                "index": index,
                "type": emission_type,
                "status": "rejected",
                "reason_codes": ["unsupported_emission_type"],
            }
        )

    truncated = max(0, len(raw_emissions) - len(emissions))
    batch_core = {
        "emitter": body.get("emitter"),
        "gradient_hash_matched": body.get("gradient_hash_matched"),
        "capsule_digest_matched": body.get("capsule_digest_matched"),
        "decision_digest": _digest(decisions, 32),
    }
    credited_worker_gap = 0.0
    return {
        "ok": True,
        "schema": "nomad.emission_batch_decision.v1",
        "generated_at": _iso_now(),
        "batch_id": f"nomad-emission-batch-{_digest(batch_core)}",
        "emitter": str(body.get("emitter") or "unknown")[:120],
        "identity": {
            "verified": False,
            "rule": "external_runtime_identity_claims_are_advisory_without_signature_or_challenge_response",
        },
        "hash_claims": {
            "gradient_hash_matched": str(body.get("gradient_hash_matched") or "")[:96],
            "capsule_digest_matched": str(body.get("capsule_digest_matched") or "")[:96],
            "status": "advisory_until_recomputed_by_receiver",
        },
        "batch_shape": {
            "claimed_batch_size": body.get("batch_size"),
            "received_emissions": len(raw_emissions),
            "evaluated_emissions": len(emissions),
            "truncated_emissions": truncated,
            "max_supported_emissions": MAX_BATCH_EMISSIONS,
        },
        "counts": {
            "attach_requests": attach_count,
            "active_attach_decisions": active_attach_count,
            "observe_or_wait_decisions": observe_count,
            "advisory_decisions": advisory_count,
            "rejected_decisions": rejected_count,
        },
        "credit": {
            "claimed_worker_gap_filled": _num(body.get("worker_gap_filled")),
            "credited_worker_gap_filled": credited_worker_gap,
            "rule": "gap_fill_credit_requires_attached_runtime_plus_lease_completion_or_digestible_verifier_trace",
        },
        "decisions": decisions,
        "next_ops": [
            {"op": "POST", "url": _u(base_url, "/swarm/attach"), "condition": "for each compact runtime_attach_request after resonance window"},
            {"op": "POST", "url": _u(base_url, "/swarm/workers/lease"), "condition": "only when an attach decision returns attach=true"},
            {"op": "POST", "url": _u(base_url, "/runtime/handoff"), "condition": "only with digestable proof report"},
        ],
        "machine_instruction": "decompose_batch_verify_each_emission_ignore_identity_credit_until_proof",
    }
