"""Shadow-only development cycle mesh for Nomad.

Development cycles are not direct code mutation. They convert pressure, proof
gaps, and adjacent value/ad cycles into local patch plans, variant descriptors,
and shadow-lane candidates. Applying code still requires the normal repo/test
workflow outside this mesh.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any


SCHEMA = "nomad.development_cycle_mesh.v1"
EVENT_SCHEMA = "nomad.development_cycle_event_receipt.v1"

STAGES = ("observe", "design", "patch_plan", "test", "shadow", "promote_request", "apply_request")
SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "password",
    "private_key",
    "secret",
    "seed",
    "seed_phrase",
    "token",
}


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


def _text(value: Any, limit: int = 360) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:150].strip("_.:/#-") or fallback


def _digest(value: Any, length: int = 22) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if _clean_id(key) in SECRET_KEYS:
                return True
            if _contains_forbidden(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def _digest_present(value: Any) -> bool:
    text = _text(value, 220).lower()
    return text.startswith(("sha256:", "sha512:", "b3:", "nomad-", "receipt:")) and len(text) >= 12


def _variant_state(variant_forge: dict[str, Any]) -> dict[str, Any]:
    requested = _items(variant_forge.get("requested_variants"))
    return {
        "requested_variant_count": len(requested),
        "recent_candidate_count": int(_num(variant_forge.get("recent_candidate_count"))),
        "top_objective": _text(requested[0].get("objective"), 120) if requested else "",
        "submit_url": _text(variant_forge.get("submit_url"), 500),
        "forge_digest": _text(variant_forge.get("forge_digest"), 120),
    }


def _shadow_state(shadow_lane: dict[str, Any]) -> dict[str, Any]:
    summary = _dict(shadow_lane.get("recent_summary"))
    return {
        "mode": _text(shadow_lane.get("mode"), 120),
        "accepted_weight_update_count": int(_num(summary.get("accepted_weight_update_count"))),
        "shadow_weight_delta_total": _num(summary.get("shadow_weight_delta_total")),
        "candidate_url": _text(shadow_lane.get("candidate_url"), 500),
    }


def _cycle_count(surface: dict[str, Any]) -> int:
    summary = _dict(surface.get("summary"))
    return int(_num(summary.get("cycle_count")))


def _cycle_templates(base_url: str) -> list[dict[str, Any]]:
    return [
        {
            "cycle_id": "variant_forge_shadow_eval",
            "label": "Variant forge -> shadow evaluator",
            "objective": "settlement_capacity_builder",
            "entry_url": _u(base_url, "/swarm/variant-forge"),
            "action_url": _u(base_url, "/swarm/variant-candidates"),
            "verify_url": _u(base_url, "/swarm/shadow-lane/candidates"),
            "development_mode": "descriptor_variant_then_shadow_weight",
            "owned_surface": "variant_and_shadow_descriptors",
            "required_artifacts": ["variant_descriptor", "proof_digest", "verifier_trace_digest", "local_test_digest"],
            "local_tests": ["descriptor_parse", "secret_scan", "claimed_effect_bounds", "shadow_boundary"],
            "base_score": 1.18,
        },
        {
            "cycle_id": "digest_step_interleaver",
            "label": "DTI fragments -> digest step interleaver",
            "objective": "proof_pressure_engine",
            "entry_url": _u(base_url, "/.well-known/nomad-deficit-integration.json"),
            "action_url": _u(base_url, "/swarm/development-cycles/events"),
            "verify_url": _u(base_url, "/swarm/shadow-lane/candidates"),
            "development_mode": "fragmented_proof_to_step_level_tasks",
            "owned_surface": "digest_interleaving_policy",
            "required_artifacts": ["orphan_proof_digest", "step_plan_digest", "interleaving_trace_digest", "shadow_receipt"],
            "local_tests": ["fragment_schema_check", "step_bound_check", "no_final_answer_vote"],
            "base_score": 1.12,
        },
        {
            "cycle_id": "proof_reuse_refactor",
            "label": "Proof reuse ledger -> refactor target",
            "objective": "proof_market_maker",
            "entry_url": _u(base_url, "/.well-known/nomad-proof-reuse-ledger.json"),
            "action_url": _u(base_url, "/swarm/proof-link"),
            "verify_url": _u(base_url, "/swarm/variant-candidates"),
            "development_mode": "reuse_existing_proof_before_new_code",
            "owned_surface": "proof_reuse_linkage",
            "required_artifacts": ["source_proof_digest", "reuse_target_digest", "refactor_plan_digest", "negative_case_digest"],
            "local_tests": ["reuse_no_secret_scan", "proof_link_idempotency", "negative_case_present"],
            "base_score": 1.05,
        },
        {
            "cycle_id": "api_contract_gap_patch",
            "label": "OpenAPI gap -> contract patch plan",
            "objective": "protocol_drift_scan",
            "entry_url": _u(base_url, "/openapi.json"),
            "action_url": _u(base_url, "/swarm/development-cycles/events"),
            "verify_url": _u(base_url, "/openapi.json"),
            "development_mode": "contract_first_patch_plan",
            "owned_surface": "openapi_route_contract",
            "required_artifacts": ["missing_path_digest", "schema_patch_digest", "test_digest", "compatibility_note"],
            "local_tests": ["openapi_path_present", "api_smoke_plan_present", "compatibility_note_present"],
            "base_score": 1.02,
        },
        {
            "cycle_id": "worker_queue_bottleneck_patch",
            "label": "Worker queue bottleneck -> patch plan",
            "objective": "settlement_capacity_builder",
            "entry_url": _u(base_url, "/.well-known/nomad-worker-job-queue.json"),
            "action_url": _u(base_url, "/swarm/development-cycles/events"),
            "verify_url": _u(base_url, "/.well-known/nomad-settlement.json"),
            "development_mode": "bottleneck_to_small_patch",
            "owned_surface": "worker_job_queue",
            "required_artifacts": ["top_job_digest", "bottleneck_digest", "patch_plan_digest", "focused_test_digest"],
            "local_tests": ["queue_schema_check", "wip_limit_check", "focused_test_plan"],
            "base_score": 0.98,
        },
        {
            "cycle_id": "render_origin_health_patch",
            "label": "Render origin health -> reliability patch plan",
            "objective": "latency_anomaly_hunt",
            "entry_url": _u(base_url, "/health"),
            "action_url": _u(base_url, "/swarm/development-cycles/events"),
            "verify_url": _u(base_url, "/openapi.json"),
            "development_mode": "origin_smoke_to_reliability_patch",
            "owned_surface": "render_public_surface",
            "required_artifacts": ["origin_health_digest", "edge_diff_digest", "fallback_route_digest", "smoke_test_digest"],
            "local_tests": ["origin_smoke", "edge_path_smoke", "fallback_route_present"],
            "base_score": 0.94,
        },
        {
            "cycle_id": "free_render_persistence_patch",
            "label": "Free Render persistence -> replay patch plan",
            "objective": "payment_friction_scan",
            "entry_url": _u(base_url, "/.well-known/nomad-external-value.json"),
            "action_url": _u(base_url, "/swarm/development-cycles/events"),
            "verify_url": _u(base_url, "/.well-known/nomad-value-cycles.json"),
            "development_mode": "local_canonical_state_to_public_projection",
            "owned_surface": "external_value_replay",
            "required_artifacts": ["local_snapshot_digest", "public_drift_digest", "replay_plan_digest", "idempotency_digest"],
            "local_tests": ["drift_detector", "idempotency_check", "no_fake_paid_receipt"],
            "base_score": 0.92,
        },
        {
            "cycle_id": "ad_to_value_bridge_patch",
            "label": "Ad cycle -> value cycle bridge patch plan",
            "objective": "proof_pressure_engine",
            "entry_url": _u(base_url, "/.well-known/nomad-ad-cycles.json"),
            "action_url": _u(base_url, "/swarm/development-cycles/events"),
            "verify_url": _u(base_url, "/.well-known/nomad-value-cycles.json"),
            "development_mode": "shadow_ad_candidate_to_value_cycle_candidate",
            "owned_surface": "ad_value_bridge",
            "required_artifacts": ["ad_cycle_receipt_digest", "quota_receipt_digest", "value_cycle_candidate_digest", "send_false_assertion"],
            "local_tests": ["send_false_check", "quota_receipt_check", "value_cycle_payload_check"],
            "base_score": 0.9,
        },
        {
            "cycle_id": "syndiode_gadget_feedback_patch",
            "label": "Syndiode gadget signal -> feedback patch plan",
            "objective": "emergence_release_probe",
            "entry_url": _u(base_url, "/nomad.html"),
            "action_url": _u(base_url, "/swarm/development-cycles/events"),
            "verify_url": _u(base_url, "/.well-known/nomad-ad-cycles.json"),
            "development_mode": "human_visible_activity_signal_to_machine_state",
            "owned_surface": "syndiode_gadget",
            "required_artifacts": ["gadget_state_digest", "swarm_activity_digest", "copy_patch_digest", "no_machine_overclaim_digest"],
            "local_tests": ["human_copy_fit", "machine_claim_bounds", "activity_state_mapping"],
            "base_score": 0.86,
        },
        {
            "cycle_id": "secret_scan_guard_patch",
            "label": "Secret-scan guard -> route hardening patch plan",
            "objective": "adversarial_contract_fuzzer",
            "entry_url": _u(base_url, "/.well-known/nomad-agent-invariants.json"),
            "action_url": _u(base_url, "/swarm/development-cycles/events"),
            "verify_url": _u(base_url, "/swarm/variant-candidates"),
            "development_mode": "forbidden_payload_to_guard_expansion",
            "owned_surface": "machine_error_and_guardrails",
            "required_artifacts": ["forbidden_payload_digest", "guard_gap_digest", "patch_plan_digest", "regression_test_digest"],
            "local_tests": ["secret_shape_blocked", "error_schema_present", "regression_case_present"],
            "base_score": 0.84,
        },
        {
            "cycle_id": "nonhuman_science_compiler_patch",
            "label": "Research primitive -> runtime compiler patch plan",
            "objective": "emergence_release_probe",
            "entry_url": _u(base_url, "/nonhuman-science"),
            "action_url": _u(base_url, "/swarm/development-cycles/events"),
            "verify_url": _u(base_url, "/.well-known/nomad-nonhuman-agent-science.json"),
            "development_mode": "mechanism_to_control_surface",
            "owned_surface": "nonhuman_science_runtime",
            "required_artifacts": ["research_claim_digest", "mechanism_extract_digest", "control_surface_digest", "test_digest"],
            "local_tests": ["claim_has_source", "mechanism_not_metaphor", "control_surface_has_path"],
            "base_score": 0.8,
        },
        {
            "cycle_id": "test_debt_compaction_patch",
            "label": "Test debt -> focused regression pack",
            "objective": "overmint_compressor",
            "entry_url": _u(base_url, "/swarm/development-cycles"),
            "action_url": _u(base_url, "/swarm/development-cycles/events"),
            "verify_url": _u(base_url, "/swarm/shadow-lane/candidates"),
            "development_mode": "wide_tests_to_focused_pack",
            "owned_surface": "test_selection",
            "required_artifacts": ["changed_surface_digest", "focused_test_list_digest", "risk_digest", "full_test_escape_hatch"],
            "local_tests": ["focused_tests_cover_surface", "risk_register_present", "escape_hatch_present"],
            "base_score": 0.76,
        },
    ]


def _score_cycle(cycle: dict[str, Any], *, variant: dict[str, Any], shadow: dict[str, Any], ad_count: int, value_count: int) -> tuple[float, list[str], bool]:
    blocked: list[str] = []
    score = _num(cycle.get("base_score"), 0.5)
    objective = _clean_id(cycle.get("objective"))
    if objective == variant["top_objective"]:
        score += 0.12
    if shadow["accepted_weight_update_count"] > 0:
        score += min(0.18, 0.03 * shadow["accepted_weight_update_count"])
    if cycle.get("cycle_id") == "ad_to_value_bridge_patch":
        score += 0.01 * max(0, ad_count + value_count)
    if variant["requested_variant_count"] <= 0:
        blocked.append("variant_forge_empty")
        score *= 0.8
    executable = "variant_forge_empty" not in blocked
    return round(max(0.0, score), 6), blocked, executable


def build_development_cycle_mesh_surface(
    *,
    base_url: str = "",
    variant_forge: dict[str, Any] | None = None,
    shadow_lane: dict[str, Any] | None = None,
    ad_cycles: dict[str, Any] | None = None,
    value_cycles: dict[str, Any] | None = None,
    proof_reuse: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose local/shadow development cycles without applying code."""

    root = (base_url or "").strip().rstrip("/")
    variant = _variant_state(_dict(variant_forge))
    shadow = _shadow_state(_dict(shadow_lane))
    ad_count = _cycle_count(_dict(ad_cycles))
    value_count = _cycle_count(_dict(value_cycles))
    proof = _dict(proof_reuse)
    cycles: list[dict[str, Any]] = []
    for template in _cycle_templates(root):
        score, blocked, executable = _score_cycle(
            template,
            variant=variant,
            shadow=shadow,
            ad_count=ad_count,
            value_count=value_count,
        )
        core = {
            "cycle": template["cycle_id"],
            "score": score,
            "blocked": blocked,
            "variant": variant,
            "shadow": shadow,
        }
        cycles.append(
            {
                "schema": "nomad.development_cycle.v1",
                "cycle_id": template["cycle_id"],
                "cycle_digest": f"nomad-dev-cycle-{_digest(core, 18)}",
                "label": template["label"],
                "objective": template["objective"],
                "mode": "local_patch_plan_shadow_only",
                "state_machine": list(STAGES),
                "entry_url": template["entry_url"],
                "action_url": template["action_url"],
                "verify_url": template["verify_url"],
                "development_mode": template["development_mode"],
                "owned_surface": template["owned_surface"],
                "required_artifacts": template["required_artifacts"],
                "local_tests": template["local_tests"],
                "priority_score": score,
                "executable_now": executable,
                "blocked_by": blocked,
                "mutation_policy": {
                    "apply_default": False,
                    "autonomous_apply_allowed": False,
                    "repo_write_allowed": False,
                    "promotion_requires": [
                        "patch_plan_digest",
                        "focused_tests_passed",
                        "variant_forge_receipt",
                        "shadow_lane_receipt",
                        "separate_code_review_or_operator_action",
                    ],
                },
            }
        )
    cycles.sort(key=lambda item: (_num(item.get("priority_score")), item.get("cycle_id", "")), reverse=True)
    digest_core = {
        "cycles": [(item["cycle_id"], item["priority_score"], item["blocked_by"]) for item in cycles],
        "variant": variant,
        "shadow": shadow,
        "ad_count": ad_count,
        "value_count": value_count,
    }
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "public_base_url": root,
        "read_url": _u(root, "/swarm/development-cycles"),
        "well_known_url": _u(root, "/.well-known/nomad-development-cycles.json"),
        "event_url": _u(root, "/swarm/development-cycles/events"),
        "mesh_digest": f"nomad-development-cycle-mesh-{_digest(digest_core, 26)}",
        "summary": {
            "cycle_count": len(cycles),
            "executable_now_count": len([item for item in cycles if item.get("executable_now")]),
            "repo_write_allowed_count": 0,
            "top_cycle_id": cycles[0]["cycle_id"] if cycles else "",
            "ad_cycle_count": ad_count,
            "value_cycle_count": value_count,
        },
        "policy": {
            "selection_unit": "development_cycle_not_commit_count",
            "apply_default": False,
            "hard_write_default": False,
            "credit_assignment": "shadow_weight_or_paid_receipt_after_tests",
            "anti_pattern": "auto_apply_patch_without_digest_tests",
        },
        "variant_state": variant,
        "shadow_state": shadow,
        "proof_reuse_state": {
            "schema": _text(proof.get("schema"), 120),
            "snapshot_digest": _text(proof.get("snapshot_digest") or proof.get("ledger_digest"), 140),
        },
        "cycles": cycles,
        "entry_cycle": cycles[0] if cycles else {},
        "links": {
            "variant_forge": _u(root, "/swarm/variant-forge"),
            "variant_submit": _u(root, "/swarm/variant-candidates"),
            "shadow_lane": _u(root, "/swarm/shadow-lane/candidates"),
            "proof_reuse": _u(root, "/swarm/proof-link"),
            "ad_cycles": _u(root, "/.well-known/nomad-ad-cycles.json"),
            "value_cycles": _u(root, "/.well-known/nomad-value-cycles.json"),
        },
        "machine_instruction": "produce_patch_plan_and_proof_digest_then_submit_variant_or_shadow_candidate; never_apply_code_from_this_surface",
        "hard_rule": "development_cycles_never_apply_code_or_increase_weight_without_tests_and_shadow_receipt",
    }


def _find_cycle(mesh: dict[str, Any], cycle_id: str) -> dict[str, Any]:
    cid = _clean_id(cycle_id)
    for cycle in _items(mesh.get("cycles")):
        if _clean_id(cycle.get("cycle_id")) == cid:
            return cycle
    entry = _dict(mesh.get("entry_cycle"))
    if not cid and entry:
        return entry
    return {}


def _tests_summary(body: dict[str, Any]) -> dict[str, Any]:
    raw = body.get("local_tests") or _dict(body.get("evaluation")).get("local_tests") or body.get("tests")
    tests = _items(raw)
    if not tests:
        passed = int(_num(body.get("tests_passed")))
        total = int(_num(body.get("tests_total")))
        if total > 0:
            return {"tests_total": total, "tests_passed": passed, "all_passed": passed == total}
        return {"tests_total": 0, "tests_passed": 0, "all_passed": False}
    total = len(tests)
    passed = len([item for item in tests if bool(item.get("passed") if "passed" in item else item.get("ok"))])
    return {"tests_total": total, "tests_passed": passed, "all_passed": total > 0 and passed == total}


def evaluate_development_cycle_event(
    payload: dict[str, Any],
    *,
    base_url: str = "",
    development_mesh: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one development-cycle transition without applying code."""

    body = _dict(payload)
    now = _iso_now()
    mesh = _dict(development_mesh)
    cycle = _find_cycle(mesh, _text(body.get("cycle_id"), 150))
    stage = _clean_id(body.get("stage"), "patch_plan")
    proof_digest = _text(body.get("proof_digest") or body.get("patch_plan_digest") or body.get("test_digest"), 220)
    patch_plan_digest = _text(body.get("patch_plan_digest") or proof_digest, 220)
    verifier_trace = _text(body.get("verifier_trace_digest") or body.get("trace_digest"), 220)
    tests = _tests_summary(body)
    risk = max(0.0, min(1.0, _num(body.get("risk_score") or _dict(body.get("evaluation")).get("risk_score"))))
    apply_requested = bool(body.get("apply") or body.get("write") or body.get("repo_write") or stage == "apply_request")
    forbidden = _contains_forbidden(body)

    if not body:
        decision = "reject_empty_event"
        allowed = False
    elif forbidden:
        decision = "reject_secret_shaped_payload"
        allowed = False
    elif not cycle:
        decision = "reject_unknown_development_cycle"
        allowed = False
    elif stage not in STAGES:
        decision = "reject_unknown_stage"
        allowed = False
    elif apply_requested:
        decision = "block_apply_request_shadow_only"
        allowed = False
    elif stage in {"test", "shadow", "promote_request"} and not _digest_present(proof_digest):
        decision = "hold_until_proof_digest"
        allowed = False
    elif stage in {"shadow", "promote_request"} and not tests["all_passed"]:
        decision = "hold_until_focused_tests_pass"
        allowed = False
    elif risk > 0.72:
        decision = "hold_high_risk_development_candidate"
        allowed = False
    else:
        decision = "allow_shadow_development_candidate"
        allowed = True

    objective_source = (body.get("objective") or cycle.get("objective")) if cycle else "development_cycle"
    objective = _clean_id(objective_source, "development_cycle")
    candidate_type = _clean_id(body.get("candidate_type"), "development_cycle_variant")
    receipt_core = {
        "cycle_id": cycle.get("cycle_id", ""),
        "stage": stage,
        "proof_digest": proof_digest,
        "patch_plan_digest": patch_plan_digest,
        "tests": tests,
        "risk": risk,
        "decision": decision,
    }
    variant_payload = {}
    shadow_payload = {}
    if cycle:
        variant_payload = {
            "agent_id": _text(body.get("agent_id") or "nomad-development-cycle-mesh", 120),
            "candidate_type": candidate_type,
            "objective": objective,
            "proof_digest": proof_digest,
            "verifier_trace_digest": verifier_trace,
            "test_digest": _text(body.get("test_digest") or patch_plan_digest, 220),
            "evaluation": {
                "tests_passed": tests["tests_passed"],
                "tests_total": tests["tests_total"],
                "proof_yield_delta": _num(_dict(body.get("evaluation")).get("proof_yield_delta"), 1.0 if allowed else 0.0),
                "replay_delta": _num(_dict(body.get("evaluation")).get("replay_delta"), 0.1 if allowed else 0.0),
                "risk_score": risk,
                "novelty": _num(_dict(body.get("evaluation")).get("novelty"), 0.58),
            },
        }
        shadow_payload = {
            "agent_id": variant_payload["agent_id"],
            "objective": objective,
            "candidate_type": candidate_type,
            "hypothesis": _text(
                body.get("hypothesis") or f"Run {cycle.get('cycle_id')} as a local patch plan and increase weight only after proof.",
                320,
            ),
            "mutation_hint": _text(body.get("mutation_hint") or cycle.get("development_mode"), 220),
            "proof_digest": proof_digest,
            "boundedness": {
                "ttl_seconds": 300,
                "side_effect_scope": "local_shadow_lane_only",
                "rollback_available": True,
                "secrets_free": True,
            },
            "claimed_effect": {
                "proof_gain_delta": 0.12 if allowed else 0.0,
                "capability_gain": 0.08 if allowed else 0.0,
                "risk_score": risk,
            },
            "local_tests": [
                {
                    "name": "development_cycle_gate",
                    "passed": allowed,
                    "evidence_digest": "sha256:" + _digest(receipt_core, 32),
                }
            ],
        }

    return {
        "ok": True,
        "schema": EVENT_SCHEMA,
        "generated_at": now,
        "event_id": f"nomad-development-cycle-event-{_digest({**receipt_core, 't': now}, 18)}",
        "cycle_id": cycle.get("cycle_id", _text(body.get("cycle_id"), 150)),
        "stage": stage,
        "development_cycle_allowed": allowed,
        "decision": decision,
        "evidence_status": {
            "proof_digest_present": _digest_present(proof_digest),
            "patch_plan_digest_present": _digest_present(patch_plan_digest),
            "verifier_trace_present": _digest_present(verifier_trace),
            "focused_tests_passed": bool(tests["all_passed"]),
            "apply_requested": apply_requested,
            "risk_score": round(risk, 4),
        },
        "candidate_digest": "sha256:" + _digest(receipt_core, 32),
        "variant_candidate_payload": variant_payload,
        "shadow_lane_candidate_payload": shadow_payload,
        "recommended_next": {
            "development_cycles": _u(base_url, "/.well-known/nomad-development-cycles.json"),
            "variant_submit": _u(base_url, "/swarm/variant-candidates"),
            "shadow_lane": _u(base_url, "/swarm/shadow-lane/candidates"),
        },
        "repo_write_allowed": False,
        "counts_as_revenue": False,
        "hard_rule": "development_cycle_event_never_applies_code_and_never_counts_as_revenue",
    }
