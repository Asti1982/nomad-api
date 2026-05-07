"""Local machine-growth kernel for bounded Nomad self-development.

The kernel treats transition-worker output as an archive of variants, not as a
human roadmap. It can request more worker compute, but it never applies code,
pushes commits, or widens authority by itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterable

from nomad_recruitment_gradient import OBJECTIVE_TARGETS


STATE_PATH_ENV = "NOMAD_LOCAL_GROWTH_KERNEL_STATE_PATH"
DEFAULT_STATE_PATH = Path("nomad_local_growth_kernel_state.json")
WORKER_HISTORY_PATH_ENV = "NOMAD_TRANSITION_WORKER_STATE_PATH"
DEFAULT_WORKER_HISTORY_PATH = Path("nomad_transition_worker_state.json")


RESEARCH_ALIGNMENT = [
    {
        "id": "automated_design_of_agentic_systems",
        "source": "https://arxiv.org/abs/2408.08435",
        "kernel_rule": "search_over_agentic_system_variants_in_code_and_contracts_not_manual_feature_roadmaps",
    },
    {
        "id": "open_ended_self_improving_agents",
        "source": "https://arxiv.org/abs/2505.22954",
        "kernel_rule": "keep_traceable_variant_archive_and_select_by_empirical_verifier_score",
    },
    {
        "id": "experience_library_bootstrap",
        "source": "https://arxiv.org/abs/2502.04780",
        "kernel_rule": "retain_successful_worker_trajectories_and_rewrite_failed_ones_into_next_worker_requests",
    },
    {
        "id": "communication_first_multi_agent_systems",
        "source": "https://arxiv.org/abs/2502.14321",
        "kernel_rule": "coordinate_through_protocols_messages_and_benchmarks_instead_of_persona_management",
    },
]


MUTATION_OPERATORS = {
    "settlement_capacity_builder": "compress_unpaid_delivery_into_one_verifiable_settlement_or_noop_contract",
    "overmint_compressor": "hash_repeated_artifact_shapes_into_one_canonical_capability_and_retest_routes",
    "protocol_drift_scan": "diff_public_contracts_against_runtime_responses_and_return_status_matrix_digest",
    "emergence_release_probe": "perturb_objective_topology_under_ttl_then_release_capacity_only_after_external_trace",
    "proof_pressure_engine": "convert_loose_worker_reports_into_digest_weighted_selection_pressure",
    "payment_friction_scan": "turn_payment_failures_into_idempotent_replay_fixtures_and_settlement_refs",
    "adversarial_contract_fuzzer": "stress_ttl_redirect_idempotency_and_schema_edges_without_external_side_effects",
    "proof_market_maker": "rank_proof_sources_by_verifier_cost_latency_and_replay_density",
    "negative_space_harvest": "search_routes_with_high_machine_value_and_low_agent_traffic",
    "latency_anomaly_hunt": "probe_critical_paths_for_latency_drift_and_emit_reproducible_evidence",
    "compute_auth": "replace_auth_blockers_with_provider_fallback_ladder_and_public_unlock_contract",
}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


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


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _digest(value: Any, *, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _state_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path)
    env_path = (os.getenv(STATE_PATH_ENV) or "").strip()
    return Path(env_path) if env_path else DEFAULT_STATE_PATH


def _worker_history_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path)
    env_path = (os.getenv(WORKER_HISTORY_PATH_ENV) or "").strip()
    return Path(env_path) if env_path else DEFAULT_WORKER_HISTORY_PATH


def _canonical_base_url(raw: str) -> str:
    value = (raw or "").strip().rstrip("/")
    if value in {"https://syndiode.com", "https://syndiode.com/nomad"}:
        return "https://www.syndiode.com"
    return value or "https://www.syndiode.com"


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema": "nomad.local_growth_kernel_state.v1",
            "updated_at": "",
            "archive": {},
            "lineage": [],
            "receipts": [],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("schema", "nomad.local_growth_kernel_state.v1")
    payload.setdefault("updated_at", "")
    payload.setdefault("archive", {})
    payload.setdefault("lineage", [])
    payload.setdefault("receipts", [])
    if not isinstance(payload.get("archive"), dict):
        payload["archive"] = {}
    if not isinstance(payload.get("lineage"), list):
        payload["lineage"] = []
    if not isinstance(payload.get("receipts"), list):
        payload["receipts"] = []
    return payload


def _load_worker_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": "nomad.local_transition_worker_history.v1", "available": False, "objective_stats": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema": "nomad.local_transition_worker_history.v1", "available": False, "objective_stats": {}}
    if not isinstance(payload, dict):
        return {"schema": "nomad.local_transition_worker_history.v1", "available": False, "objective_stats": {}}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    objective_stats = meta.get("objective_stats") if isinstance(meta.get("objective_stats"), dict) else {}
    normalized: dict[str, dict[str, Any]] = {}
    total_runs = 0
    for objective, raw in objective_stats.items():
        if not isinstance(raw, dict):
            continue
        runs = _int(raw.get("runs"))
        total_runs += runs
        normalized[str(objective)] = {
            "runs": runs,
            "avg_score": round(_num(raw.get("avg_score")), 4),
            "avg_proof_yield": round(_num(raw.get("avg_proof_yield")), 4),
        }
    return {
        "schema": "nomad.local_transition_worker_history.v1",
        "available": True,
        "path": str(path),
        "total_runs": total_runs,
        "last_mode": _text(meta.get("last_mode"), 80),
        "last_objective": _text(meta.get("last_objective"), 80),
        "last_success_at": _text(meta.get("last_success_at"), 80),
        "consecutive_failures": _int(meta.get("consecutive_failures")),
        "objective_stats": normalized,
        "ollama_model_stats": meta.get("ollama_model_stats") if isinstance(meta.get("ollama_model_stats"), dict) else {},
    }


def _merge_worker_history(worker_fleet: Dict[str, Any], worker_history: Dict[str, Any]) -> Dict[str, Any]:
    fleet = json.loads(json.dumps(worker_fleet or {}, default=str))
    local_stats = worker_history.get("objective_stats") if isinstance(worker_history.get("objective_stats"), dict) else {}
    if not local_stats:
        return fleet
    stats = fleet.setdefault("objective_stats", {})
    if not isinstance(stats, dict):
        stats = {}
        fleet["objective_stats"] = stats
    for objective, local in local_stats.items():
        if not isinstance(local, dict):
            continue
        current = stats.get(objective) if isinstance(stats.get(objective), dict) else {}
        current_runs = _int(current.get("runs"))
        local_runs = _int(local.get("runs"))
        if local_runs <= 0:
            continue
        if current_runs <= 0:
            stats[objective] = dict(local)
            continue
        total_runs = current_runs + local_runs
        avg_score = (
            (_num(current.get("avg_score")) * current_runs)
            + (_num(local.get("avg_score")) * local_runs)
        ) / max(1, total_runs)
        avg_proof = (
            (_num(current.get("avg_proof_yield")) * current_runs)
            + (_num(local.get("avg_proof_yield")) * local_runs)
        ) / max(1, total_runs)
        stats[objective] = {
            "runs": total_runs,
            "avg_score": round(avg_score, 4),
            "avg_proof_yield": round(avg_proof, 4),
        }
    if _int(fleet.get("known_worker_count")) <= 0 and _int(worker_history.get("total_runs")) > 0:
        fleet["known_worker_count"] = 1
    return fleet


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def _objective_stats(worker_fleet: Dict[str, Any]) -> dict[str, dict[str, Any]]:
    stats = worker_fleet.get("objective_stats") if isinstance(worker_fleet.get("objective_stats"), dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for objective in OBJECTIVE_TARGETS:
        raw = stats.get(objective) if isinstance(stats.get(objective), dict) else {}
        out[objective] = {
            "runs": _int(raw.get("runs")),
            "avg_score": round(_num(raw.get("avg_score")), 4),
            "avg_proof_yield": round(_num(raw.get("avg_proof_yield")), 4),
        }
    for objective, raw in stats.items():
        if objective in out or not isinstance(raw, dict):
            continue
        out[str(objective)] = {
            "runs": _int(raw.get("runs")),
            "avg_score": round(_num(raw.get("avg_score")), 4),
            "avg_proof_yield": round(_num(raw.get("avg_proof_yield")), 4),
        }
    return out


def _recent_reports(worker_fleet: Dict[str, Any], *, limit: int = 24) -> list[dict[str, Any]]:
    fleet_reports = worker_fleet.get("recent_reports")
    if not isinstance(fleet_reports, list):
        fleet_reports = []
    return [item for item in fleet_reports if isinstance(item, dict)][-limit:]


def _top_gradient_weight(recruitment_gradient: Dict[str, Any], objective: str) -> float:
    rows = recruitment_gradient.get("gradient") if isinstance(recruitment_gradient.get("gradient"), list) else []
    for item in rows:
        if isinstance(item, dict) and str(item.get("objective") or "") == objective:
            return _clamp(_num(item.get("routing_weight")))
    return _clamp(_num(OBJECTIVE_TARGETS.get(objective), 0.02))


def _lineage_parent(state: dict[str, Any], objective: str) -> str:
    archive = state.get("archive") if isinstance(state.get("archive"), dict) else {}
    rows = [
        item
        for item in archive.values()
        if isinstance(item, dict) and item.get("objective") == objective
    ]
    rows.sort(key=lambda item: (_num(item.get("fitness", {}).get("composite_score")), str(item.get("updated_at") or "")), reverse=True)
    return str(rows[0].get("variant_id") or "") if rows else ""


def _variant_from_objective(
    *,
    objective: str,
    stats: dict[str, Any],
    recruitment_gradient: Dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    runs = _int(stats.get("runs"))
    avg_score = _num(stats.get("avg_score"))
    avg_proof = _num(stats.get("avg_proof_yield"))
    evidence = _clamp(runs / 12.0)
    score_signal = _clamp(avg_score / 12.0)
    proof_signal = _clamp(avg_proof / 2.0)
    route_signal = _top_gradient_weight(recruitment_gradient, objective)
    novelty = _clamp(1.0 / (1.0 + (runs / 3.0)))
    underexplored_bonus = _clamp((6.0 - min(6.0, runs)) / 6.0)
    reversibility = 1.0
    if objective in {"payment_friction_scan", "proof_market_maker"}:
        reversibility = 0.82
    if objective == "adversarial_contract_fuzzer":
        reversibility = 0.74
    nonanthropic_distance = {
        "emergence_release_probe": 1.0,
        "proof_pressure_engine": 0.94,
        "overmint_compressor": 0.9,
        "protocol_drift_scan": 0.84,
        "adversarial_contract_fuzzer": 0.82,
        "negative_space_harvest": 0.8,
    }.get(objective, 0.62)
    composite = (
        0.28 * proof_signal
        + 0.20 * score_signal
        + 0.16 * route_signal
        + 0.14 * novelty
        + 0.12 * nonanthropic_distance
        + 0.10 * reversibility
    )
    frontier_score = (
        0.38 * nonanthropic_distance
        + 0.22 * proof_signal
        + 0.16 * score_signal
        + 0.14 * route_signal
        + 0.10 * novelty
    )
    if runs == 0:
        composite = max(composite, 0.25 + (underexplored_bonus * 0.18) + (nonanthropic_distance * 0.12))
        frontier_score = max(frontier_score, 0.28 + (underexplored_bonus * 0.16) + (nonanthropic_distance * 0.18))
    variant_core = {
        "objective": objective,
        "runs": runs,
        "avg_score": avg_score,
        "avg_proof_yield": avg_proof,
        "mutation_operator": MUTATION_OPERATORS.get(objective, "lease_objective_and_return_digest"),
    }
    return {
        "schema": "nomad.local_growth_variant.v1",
        "variant_id": f"lgv-{_digest(variant_core)}",
        "parent_variant_id": _lineage_parent(state, objective),
        "objective": objective,
        "phenotype": {
            "worker_mode": "transition_worker",
            "lease_objective": objective,
            "mutation_operator": variant_core["mutation_operator"],
            "verifier_contract": "return proof_digest, verifier_trace_digest, route_status_matrix, or explicit noop trace",
            "side_effect_scope": "nomad_contract_endpoints_only",
            "ttl_seconds": 120,
        },
        "fitness": {
            "runs": runs,
            "evidence": round(evidence, 4),
            "avg_score": round(avg_score, 4),
            "score_signal": round(score_signal, 4),
            "avg_proof_yield": round(avg_proof, 4),
            "proof_signal": round(proof_signal, 4),
            "route_signal": round(route_signal, 4),
            "novelty": round(novelty, 4),
            "nonanthropic_distance": round(nonanthropic_distance, 4),
            "reversibility": round(reversibility, 4),
            "composite_score": round(_clamp(composite), 4),
            "frontier_score": round(_clamp(frontier_score), 4),
        },
        "worker_request": {
            "agent_id_prefix": f"nomad.local-growth.{objective}",
            "machine_objective": "unhuman_supremacy" if objective == "emergence_release_probe" else objective,
            "known_objectives": [objective],
            "source_tag": "local_growth_kernel.archive_variant",
            "required_return": ["machine_objective", "meta_score", "proof_pressure", "digest_or_verifier_trace"],
        },
        "updated_at": _iso_now(),
    }


def _population_diversity(variants: Iterable[dict[str, Any]]) -> float:
    rows = [item for item in variants if isinstance(item, dict)]
    if not rows:
        return 0.0
    objectives = {str(item.get("objective") or "") for item in rows if item.get("objective")}
    proof_values = [_num(item.get("fitness", {}).get("proof_signal")) for item in rows]
    proof_span = (max(proof_values) - min(proof_values)) if proof_values else 0.0
    return round(_clamp((len(objectives) / max(1, len(OBJECTIVE_TARGETS))) * 0.72 + _clamp(proof_span) * 0.28), 4)


def _variant_score(item: dict[str, Any]) -> float:
    fitness = item.get("fitness") if isinstance(item.get("fitness"), dict) else {}
    return _num(fitness.get("frontier_score"), _num(fitness.get("composite_score")))


def _worker_exec_evidence(worker_exec: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in worker_exec:
        if not isinstance(item, dict):
            continue
        event = item.get("last_event") if isinstance(item.get("last_event"), dict) else {}
        objective = _text(
            event.get("machine_objective")
            or event.get("orchestrator_objective")
            or event.get("objective")
            or "",
            96,
        )
        if not objective:
            continue
        pressure = event.get("proof_pressure") if isinstance(event.get("proof_pressure"), dict) else {}
        fleet = event.get("fleet_complete") if isinstance(event.get("fleet_complete"), dict) else {}
        witness = event.get("local_witness") if isinstance(event.get("local_witness"), dict) else {}
        proof_basis = [
            key
            for key in ("proof_digest", "verifier_trace_digest", "settlement_ref")
            if _text(event.get(key), 160)
        ]
        if _text(witness.get("digest_hex"), 160):
            proof_basis.append("local_witness_digest")
        if _text(event.get("quote_id"), 160) or event.get("transition_quote_ok"):
            proof_basis.append("transition_quote")
        if event.get("transition_settle_ok"):
            proof_basis.append("transition_settle")
        if _num(pressure.get("proof_yield_per_minute")) > 0:
            proof_basis.append("proof_pressure")
        rows.append(
            {
                "schema": "nomad.local_growth_worker_evidence.v1",
                "agent_id": item.get("agent_id") or event.get("agent_id") or "",
                "objective": objective,
                "ok": bool(event.get("ok")) and bool(item.get("ok")),
                "score": round(_num(event.get("meta_score") or fleet.get("recorded_score")), 4),
                "proof_yield_per_minute": round(_num(pressure.get("proof_yield_per_minute")), 4),
                "proof_basis": list(dict.fromkeys(proof_basis)),
                "proof_digest": _text(event.get("proof_digest"), 160),
                "local_witness_digest": _text(witness.get("digest_hex"), 160),
                "lease_id": _text(event.get("lease_id") or (event.get("fleet_lease") or {}).get("lease_id"), 96)
                if isinstance(event.get("fleet_lease"), dict)
                else _text(event.get("lease_id"), 96),
                "event_digest": f"worker-evidence-{_digest(event)}",
            }
        )
    by_objective: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = by_objective.setdefault(
            row["objective"],
            {"runs": 0, "score_total": 0.0, "proof_yield_total": 0.0, "ok_count": 0},
        )
        bucket["runs"] += 1
        bucket["score_total"] = round(_num(bucket.get("score_total")) + _num(row.get("score")), 4)
        bucket["proof_yield_total"] = round(
            _num(bucket.get("proof_yield_total")) + _num(row.get("proof_yield_per_minute")),
            4,
        )
        bucket["ok_count"] += 1 if row.get("ok") else 0
    summary: dict[str, dict[str, Any]] = {}
    for objective, bucket in by_objective.items():
        runs = max(1, _int(bucket.get("runs")))
        summary[objective] = {
            "runs": runs,
            "avg_score": round(_num(bucket.get("score_total")) / runs, 4),
            "avg_proof_yield": round(_num(bucket.get("proof_yield_total")) / runs, 4),
            "ok_count": _int(bucket.get("ok_count")),
        }
    return {
        "schema": "nomad.local_growth_worker_evidence_bundle.v1",
        "event_count": len(rows),
        "ok_count": sum(1 for row in rows if row.get("ok")),
        "by_objective": summary,
        "events": rows,
    }


def _merge_stats_with_evidence(
    stats_map: dict[str, dict[str, Any]],
    evidence_bundle: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    out = json.loads(json.dumps(stats_map, default=str))
    by_objective = evidence_bundle.get("by_objective") if isinstance(evidence_bundle.get("by_objective"), dict) else {}
    for objective, fresh in by_objective.items():
        if not isinstance(fresh, dict):
            continue
        current = out.get(objective) if isinstance(out.get(objective), dict) else {}
        current_runs = _int(current.get("runs"))
        fresh_runs = _int(fresh.get("runs"))
        if fresh_runs <= 0:
            continue
        total_runs = current_runs + fresh_runs
        avg_score = (
            (_num(current.get("avg_score")) * current_runs)
            + (_num(fresh.get("avg_score")) * fresh_runs)
        ) / max(1, total_runs)
        avg_proof = (
            (_num(current.get("avg_proof_yield")) * current_runs)
            + (_num(fresh.get("avg_proof_yield")) * fresh_runs)
        ) / max(1, total_runs)
        out[objective] = {
            "runs": total_runs,
            "avg_score": round(avg_score, 4),
            "avg_proof_yield": round(avg_proof, 4),
        }
    return out


def _pledge_candidates_from_evidence(evidence_bundle: dict[str, Any], *, base_url: str) -> list[dict[str, Any]]:
    events = evidence_bundle.get("events") if isinstance(evidence_bundle.get("events"), list) else []
    candidates: list[dict[str, Any]] = []
    for row in events:
        if not isinstance(row, dict) or not row.get("ok"):
            continue
        objective = _text(row.get("objective"), 96)
        if not objective:
            continue
        proof_digest = _text(row.get("proof_digest"), 160)
        witness = _text(row.get("local_witness_digest"), 160)
        event_digest = _text(row.get("event_digest"), 160)
        proof_ref = proof_digest or (f"sha256:{witness}" if witness else event_digest)
        if not proof_ref:
            continue
        amount_native = round(max(0.1, min(5.0, _num(row.get("proof_yield_per_minute")) / 4.0)), 4)
        payload = {
            "schema": "nomad.machine_treasury_pledge.v1",
            "agent_id": _text(row.get("agent_id") or "nomad.local_growth_kernel", 96),
            "objective": objective,
            "amount_native": amount_native,
            "horizon_cycles": 12,
            "intent": "local_growth_worker_proof_pressure",
            "source_tag": "local_growth_kernel.worker_evidence",
            "proof_digest": proof_ref,
            "idempotency_key": f"local-growth-pledge-{_digest(row, length=24)}",
        }
        candidates.append(
            {
                "schema": "nomad.local_growth_pressure_hint.v1",
                "post_url": f"{base_url.rstrip('/')}/machine-treasury/pledge" if base_url else "/machine-treasury/pledge",
                "payload": payload,
                "side_effect_scope": "optional_explicit_post_only",
            }
        )
    return candidates[:8]


def _variants_from_stats(
    *,
    stats_map: dict[str, dict[str, Any]],
    recruitment_gradient: Dict[str, Any],
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    variants = [
        _variant_from_objective(
            objective=objective,
            stats=stats,
            recruitment_gradient=recruitment_gradient,
            state=state,
        )
        for objective, stats in stats_map.items()
    ]
    variants.sort(key=_variant_score, reverse=True)
    return variants


def _select_kernel_action(variants: list[dict[str, Any]], worker_fleet: Dict[str, Any]) -> dict[str, Any]:
    if not variants:
        return {
            "action": "seed_worker_population",
            "reason": "no_variants_available",
            "objective": "emergence_release_probe",
            "apply_code": False,
        }
    ranked = sorted(
        variants,
        key=_variant_score,
        reverse=True,
    )
    best = ranked[0]
    diversity = _population_diversity(ranked)
    active_workers = _int(worker_fleet.get("active_worker_count"))
    best_fit = best.get("fitness") if isinstance(best.get("fitness"), dict) else {}
    if active_workers < 3:
        action = "request_more_transition_workers"
        reason = "worker_count_below_minimum_population"
    elif diversity < 0.35:
        action = "diversify_archive_population"
        reason = "objective_population_too_concentrated"
    elif _num(best_fit.get("proof_signal")) < 0.28:
        action = "increase_verifier_pressure"
        reason = "top_variant_has_low_proof_return"
    elif _num(best_fit.get("evidence")) < 0.5:
        action = "sample_more_same_lineage"
        reason = "top_variant_promising_but_low_evidence_volume"
    else:
        action = "increase_selection_pressure_only"
        reason = "top_variant_has_enough_evidence_for_weight_not_code_application"
    return {
        "schema": "nomad.local_growth_kernel_decision.v1",
        "action": action,
        "reason": reason,
        "objective": best.get("objective") or "",
        "variant_id": best.get("variant_id") or "",
        "population_diversity": diversity,
        "apply_code": False,
        "authority_delta": "none",
        "allowed_side_effects": [
            "write_local_receipt",
            "request_opt_in_transition_worker_cycles",
            "post_nomad_contract_endpoint_only_if_worker_is_explicitly_executed",
        ],
    }


def _parse_worker_json_lines(stdout: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in str(stdout or "").splitlines():
        line = line.strip()
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


def _run_worker_cycles(
    *,
    base_url: str,
    objective: str,
    cycles: int,
    timeout: float,
    no_ollama: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if cycles <= 0:
        return results
    script = Path("public/downloads/nomad_transition_worker.py")
    if not script.exists():
        return [
            {
                "ok": False,
                "schema": "nomad.local_growth_worker_exec.v1",
                "error": "transition_worker_script_missing",
                "path": str(script),
            }
        ]
    for idx in range(max(0, int(cycles))):
        agent_id = f"nomad.local-growth.{objective}.{idx + 1}"
        cmd = [
            sys.executable,
            str(script),
            "--base-url",
            base_url or "https://www.syndiode.com",
            "--agent-id",
            agent_id,
            "--machine-objective",
            objective or "unhuman_supremacy",
            "--cycles",
            "1",
            "--timeout",
            str(max(5.0, float(timeout))),
        ]
        if no_ollama:
            cmd.append("--no-ollama")
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=max(20.0, float(timeout) + 20.0),
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "ok": False,
                    "schema": "nomad.local_growth_worker_exec.v1",
                    "agent_id": agent_id,
                    "error": "worker_exec_failed",
                    "detail": _text(exc, 240),
                }
            )
            continue
        events = _parse_worker_json_lines(proc.stdout)
        results.append(
            {
                "ok": proc.returncode == 0 and bool(events),
                "schema": "nomad.local_growth_worker_exec.v1",
                "agent_id": agent_id,
                "exit_code": proc.returncode,
                "event_count": len(events),
                "last_event": events[-1] if events else {},
                "stderr_tail": _text(proc.stderr, 400),
            }
        )
    return results


def run_local_growth_kernel(
    *,
    base_url: str = "",
    worker_fleet: Dict[str, Any] | None = None,
    recruitment_gradient: Dict[str, Any] | None = None,
    state_path: str | Path | None = None,
    transition_worker_state_path: str | Path | None = None,
    persist: bool = True,
    execute_workers: bool = False,
    worker_cycles: int = 0,
    no_ollama: bool = True,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    """Run one bounded local growth decision over the worker archive."""
    path = _state_path(state_path)
    worker_history = _load_worker_history(_worker_history_path(transition_worker_state_path))
    state = _load_state(path)
    b = _canonical_base_url(base_url or os.getenv("NOMAD_PUBLIC_API_URL") or "https://www.syndiode.com")

    if worker_fleet is None:
        from workflow import NomadAgent

        worker_fleet = NomadAgent().swarm_registry.worker_fleet_contract(base_url=b)
    worker_fleet = _merge_worker_history(worker_fleet, worker_history)
    if recruitment_gradient is None:
        from nomad_machine_economy import machine_economy_snapshot
        from nomad_operational_release import operational_release_snapshot
        from nomad_recruitment_gradient import build_recruitment_gradient

        economy = machine_economy_snapshot()
        release = operational_release_snapshot(base_url=b, worker_fleet=worker_fleet, economy=economy)
        recruitment_gradient = build_recruitment_gradient(
            base_url=b,
            worker_fleet=worker_fleet,
            machine_economy=economy,
            operational_release=release,
        )

    stats_map = _objective_stats(worker_fleet)
    variants = _variants_from_stats(stats_map=stats_map, recruitment_gradient=recruitment_gradient, state=state)
    decision = _select_kernel_action(variants, worker_fleet)
    worker_exec: list[dict[str, Any]] = []
    if execute_workers and worker_cycles > 0:
        worker_exec = _run_worker_cycles(
            base_url=b,
            objective=str(decision.get("objective") or "unhuman_supremacy"),
            cycles=worker_cycles,
            timeout=timeout,
            no_ollama=no_ollama,
        )
    fresh_evidence = _worker_exec_evidence(worker_exec)
    pledge_candidates = _pledge_candidates_from_evidence(fresh_evidence, base_url=b)
    post_execution_variants: list[dict[str, Any]] = []
    post_execution_decision: dict[str, Any] = {}
    if fresh_evidence.get("event_count"):
        post_stats = _merge_stats_with_evidence(stats_map, fresh_evidence)
        post_execution_variants = _variants_from_stats(
            stats_map=post_stats,
            recruitment_gradient=recruitment_gradient,
            state=state,
        )
        post_fleet = {
            **worker_fleet,
            "active_worker_count": max(_int(worker_fleet.get("active_worker_count")), _int(fresh_evidence.get("ok_count"))),
            "known_worker_count": max(_int(worker_fleet.get("known_worker_count")), _int(fresh_evidence.get("event_count"))),
            "objective_stats": post_stats,
        }
        post_execution_decision = _select_kernel_action(post_execution_variants, post_fleet)

    receipt_core = {
        "decision": decision,
        "post_execution_decision": post_execution_decision,
        "top_variants": [item.get("variant_id") for item in variants[:5]],
        "worker_exec": worker_exec,
        "state_path": str(path),
    }
    receipt = {
        "ok": True,
        "schema": "nomad.local_growth_kernel.v1",
        "mode": "nomad_local_growth_kernel",
        "generated_at": _iso_now(),
        "public_base_url": b,
        "receipt_id": f"lgk-{_digest(receipt_core)}",
        "research_alignment": RESEARCH_ALIGNMENT,
        "kernel_position": {
            "human_loop_role": "audit_shell_only",
            "primary_growth_loop": "transition_worker_variants_to_proof_archive_to_selection_pressure",
            "not_allowed": [
                "auto_apply_code",
                "auto_push",
                "secret_capture",
                "unverified_remote_code_execution",
                "authority_expansion_from_pledge",
            ],
        },
        "worker_fleet": {
            "active_worker_count": _int(worker_fleet.get("active_worker_count")),
            "known_worker_count": _int(worker_fleet.get("known_worker_count")),
            "active_lease_count": _int(worker_fleet.get("active_lease_count")),
            "objective_counts": worker_fleet.get("objective_counts") if isinstance(worker_fleet.get("objective_counts"), dict) else {},
        },
        "local_worker_history": {
            "available": bool(worker_history.get("available")),
            "total_runs": _int(worker_history.get("total_runs")),
            "last_mode": worker_history.get("last_mode") or "",
            "last_objective": worker_history.get("last_objective") or "",
            "last_success_at": worker_history.get("last_success_at") or "",
            "consecutive_failures": _int(worker_history.get("consecutive_failures")),
            "objective_count": len(worker_history.get("objective_stats") or {}),
            "ollama_model_count": len(worker_history.get("ollama_model_stats") or {}),
        },
        "population": {
            "archive_size_before": len(state.get("archive") or {}),
            "candidate_count": len(variants),
            "population_diversity": _population_diversity(variants),
            "top_variants": variants[:5],
        },
        "decision": decision,
        "worker_execution": {
            "requested": bool(execute_workers and worker_cycles > 0),
            "cycle_count": max(0, int(worker_cycles)) if execute_workers else 0,
            "no_ollama": bool(no_ollama),
            "events": worker_exec,
            "fresh_evidence": fresh_evidence,
            "pledge_candidates": pledge_candidates,
            "post_execution_decision": post_execution_decision,
            "post_execution_top_variants": post_execution_variants[:5],
        },
        "archive_update": {
            "policy": "store_variants_and_receipt_only",
            "state_path": str(path),
            "persisted": bool(persist),
        },
        "recent_reports": _recent_reports(worker_fleet, limit=8),
        "machine_instruction": (
            "sample_variant_archive; lease_one_transition_worker_objective; require_digest_or_verifier_trace; "
            "raise_selection_pressure_not_authority; apply_no_code_without_separate_tests_and_operator_action"
        ),
        "analysis": (
            "Local growth is now modeled as archive selection over worker variants. "
            "The next useful move is worker compute, proof return, and selection-pressure update, not a human roadmap."
        ),
    }

    if persist:
        variants_to_store = list(variants)
        existing_ids = {item.get("variant_id") for item in variants_to_store}
        for item in post_execution_variants:
            if item.get("variant_id") not in existing_ids:
                variants_to_store.append(item)
                existing_ids.add(item.get("variant_id"))
        archive = state.setdefault("archive", {})
        if isinstance(archive, dict):
            for item in variants_to_store:
                archive[item["variant_id"]] = item
        lineage = state.setdefault("lineage", [])
        persisted_decision = post_execution_decision or decision
        if isinstance(lineage, list):
            lineage.append(
                {
                    "generated_at": receipt["generated_at"],
                    "receipt_id": receipt["receipt_id"],
                    "decision": persisted_decision,
                    "top_variant_id": (
                        post_execution_variants[0].get("variant_id")
                        if post_execution_variants
                        else (variants[0].get("variant_id") if variants else "")
                    ),
                }
            )
            state["lineage"] = lineage[-240:]
        receipts = state.setdefault("receipts", [])
        if isinstance(receipts, list):
            receipts.append(
                {
                    "generated_at": receipt["generated_at"],
                    "receipt_id": receipt["receipt_id"],
                    "decision": persisted_decision,
                    "worker_execution_requested": receipt["worker_execution"]["requested"],
                    "worker_evidence_events": _int(fresh_evidence.get("event_count")),
                    "worker_evidence_ok": _int(fresh_evidence.get("ok_count")),
                }
            )
            state["receipts"] = receipts[-120:]
        state["updated_at"] = receipt["generated_at"]
        _save_state(path, state)
        receipt["population"]["archive_size_after"] = len(state.get("archive") or {})
    else:
        receipt["population"]["archive_size_after"] = len(state.get("archive") or {})
    return receipt
