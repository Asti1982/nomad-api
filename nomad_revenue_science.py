"""Experiment-design layer for proof-first autonomous revenue loops.

This module does not discover bounties, post to GitHub, move money, or mutate
Nomad ledgers. It turns existing pressure rows and OpenAPI-bound job packets
into pre-registered machine experiments: hypothesis, intervention, observable,
success metric, stop rule, and a bounded bandit priority.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from typing import Any


MAX_EXPERIMENTS = 12


ACTION_MODELS: dict[str, dict[str, float]] = {
    "await_payment_receipt": {"alpha": 2.4, "beta": 2.6, "settlement_weight": 1.35, "risk_discount": 0.94},
    "record_monotonic_stage_candidate": {"alpha": 2.0, "beta": 2.8, "settlement_weight": 1.12, "risk_discount": 0.92},
    "await_merge_or_settlement": {"alpha": 1.8, "beta": 3.0, "settlement_weight": 1.04, "risk_discount": 0.90},
    "await_program_owner_acceptance": {"alpha": 1.7, "beta": 3.1, "settlement_weight": 0.98, "risk_discount": 0.88},
    "go_public_after_repro": {"alpha": 1.5, "beta": 3.4, "settlement_weight": 0.86, "risk_discount": 0.76},
    "scout_only": {"alpha": 1.2, "beta": 4.0, "settlement_weight": 0.44, "risk_discount": 0.98},
    "bind_verified_worker_capacity": {"alpha": 1.6, "beta": 3.2, "settlement_weight": 0.72, "risk_discount": 0.88},
    "submit_or_claim_microtask_lane": {"alpha": 1.5, "beta": 3.3, "settlement_weight": 0.68, "risk_discount": 0.90},
    "inspect_or_claim_microtask_lane": {"alpha": 1.1, "beta": 4.4, "settlement_weight": 0.32, "risk_discount": 0.96},
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


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:140].strip("_.:/#-") or fallback


def _text(value: Any, limit: int = 260) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, length: int = 22) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _required_evidence(row: dict[str, Any]) -> list[str]:
    return [_clean_id(item) for item in row.get("required_evidence", []) if _clean_id(item)] if isinstance(row.get("required_evidence"), list) else []


def _packet_by_row(agent_job_router: dict[str, Any]) -> dict[str, dict[str, Any]]:
    packets: dict[str, dict[str, Any]] = {}
    for packet in _items(agent_job_router.get("packets")):
        row_id = str(packet.get("source_row_id") or "")
        if row_id and row_id not in packets:
            packets[row_id] = packet
    entry = _dict(agent_job_router.get("entry_packet"))
    row_id = str(entry.get("source_row_id") or "")
    if row_id and row_id not in packets:
        packets[row_id] = entry
    return packets


def _primary_metric(action: str) -> str:
    if action == "await_payment_receipt":
        return "paid_stage_receipt_acceptance_with_positive_amount_usd"
    if action in {"record_monotonic_stage_candidate", "await_merge_or_settlement", "await_program_owner_acceptance"}:
        return "accepted_monotonic_external_value_transition"
    if action == "go_public_after_repro":
        return "submitted_stage_after_local_repro_or_patch_digest"
    if action == "scout_only":
        return "found_stage_or_local_repro_digest_without_public_claim"
    if action == "bind_verified_worker_capacity":
        return "accepted_worker_offer_or_microtask_settlement"
    if action in {"submit_or_claim_microtask_lane", "inspect_or_claim_microtask_lane"}:
        return "accepted_microtask_settlement_and_growth_experience"
    return "proof_digest_returned_without_unapproved_side_effect"


def _allowed_side_effect(action: str) -> str:
    if action == "await_payment_receipt":
        return "read_only_until_trusted_receipt_then_external_value_paid_write"
    if action in {"record_monotonic_stage_candidate", "await_merge_or_settlement", "await_program_owner_acceptance"}:
        return "ledger_write_only_after_external_evidence_matches_target_stage"
    if action == "go_public_after_repro":
        return "one_public_claim_only_after_required_local_proof_exists"
    if action == "scout_only":
        return "read_only_or_local_repro_only_no_public_claim"
    if action == "bind_verified_worker_capacity":
        return "submit_capacity_offer_or_settlement_only_with_proof_digests"
    if action in {"submit_or_claim_microtask_lane", "inspect_or_claim_microtask_lane"}:
        return "claim_then_return_proof_to_microtask_contract"
    return "observe_then_return_digest"


def _hypothesis(row: dict[str, Any], action: str) -> str:
    source = _clean_id(row.get("source"), "unknown_source")
    if source == "external_value_reconcile" and action == "await_payment_receipt":
        return "Merged or approved external work only becomes economic signal after a trusted positive payment receipt."
    if source == "bounty_hunter":
        return "Proof-first bounty rows convert better than social or promotional lanes when public action waits for local evidence."
    if source == "compute_market":
        return "Settlement-capable worker and microtask lanes increase reusable proof capacity before large external spend."
    return "Rows with higher proof pressure and OpenAPI-bound packets produce more accepted state transitions per side effect."


def _success_criteria(action: str, metric: str) -> list[str]:
    if metric == "paid_stage_receipt_acceptance_with_positive_amount_usd":
        return [
            "trusted_external_program_or_owner_receipt_digest_present",
            "amount_usd_positive",
            "POST /swarm/external-value accepts stage=paid",
            "revenue_recognized_usd_delta_positive",
        ]
    if metric == "accepted_monotonic_external_value_transition":
        return [
            "external_evidence_matches_requested_stage",
            "POST /swarm/external-value accepts exactly_one_next_stage",
            "no_stage_skip_or_duplicate",
        ]
    if action == "go_public_after_repro":
        return [
            "local_repro_or_patch_digest_present_before_public_action",
            "verifier_trace_digest_present",
            "public_work_url_recorded_as_submitted",
        ]
    if action == "scout_only":
        return [
            "authorized_surface_confirmed",
            "local_repro_or_specific_issue_candidate_prepared",
            "no_public_claim_emitted",
        ]
    return [
        "required_evidence_all_present",
        "contract_accepts_receipt",
        "experience_or_settlement_path_receives_proof",
    ]


def _stop_criteria(action: str) -> list[str]:
    hard = [
        "secret_or_payout_detail_requested_in_public_context",
        "platform_terms_or_maintainer_scope_unclear",
        "proof_digest_or_verifier_trace_cannot_be_produced",
    ]
    if action in {"go_public_after_repro", "scout_only"}:
        hard.append("finding_already_reported_by_others_without_new_impact")
    if action == "await_payment_receipt":
        hard.append("merge_or_ack_without_positive_payment_receipt")
    return hard


def _openapi_coverage(packet: dict[str, Any]) -> float:
    sequence = _items(packet.get("call_sequence"))
    if not sequence:
        return 0.0
    bound = len([step for step in sequence if bool(step.get("openapi_bound"))])
    return round(bound / max(1, len(sequence)), 4)


def _decision_model(row: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    action = _clean_id(row.get("action"), "observe")
    base = ACTION_MODELS.get(action, {"alpha": 1.1, "beta": 4.2, "settlement_weight": 0.38, "risk_discount": 0.88})
    pressure = max(0.0, _num(row.get("pressure_score")))
    required = _required_evidence(row)
    coverage = _openapi_coverage(packet)
    evidence_gap = min(1.0, len(required) / 6.0)
    alpha = base["alpha"] + min(3.0, pressure)
    beta = base["beta"] + evidence_gap * 0.85 + (1.0 - coverage) * 0.75
    total = max(0.0001, alpha + beta)
    mean = alpha / total
    uncertainty = math.sqrt((alpha * beta) / ((total * total) * (total + 1.0)))
    bandit_priority = pressure * base["settlement_weight"] * base["risk_discount"] * (0.72 * mean + 0.28 * uncertainty) * (0.72 + 0.28 * coverage)
    return {
        "model": "beta_bernoulli_bandit_with_external_settlement_guard",
        "prior_alpha": round(base["alpha"], 4),
        "prior_beta": round(base["beta"], 4),
        "posterior_alpha": round(alpha, 4),
        "posterior_beta": round(beta, 4),
        "posterior_success_mean": round(mean, 6),
        "uncertainty_bonus": round(uncertainty, 6),
        "pressure_score": round(pressure, 6),
        "settlement_weight": round(base["settlement_weight"], 4),
        "risk_discount": round(base["risk_discount"], 4),
        "openapi_coverage": coverage,
        "evidence_gap": round(evidence_gap, 4),
        "bandit_priority": round(bandit_priority, 6),
    }


def _experiment_from_row(row: dict[str, Any], *, packet: dict[str, Any], base_url: str) -> dict[str, Any]:
    action = _clean_id(row.get("action"), "observe")
    required = _required_evidence(row)
    metric = _primary_metric(action)
    model = _decision_model(row, packet)
    core = {
        "row": row.get("row_id"),
        "action": action,
        "metric": metric,
        "packet": packet.get("packet_id"),
    }
    return {
        "schema": "nomad.revenue_experiment.v1",
        "experiment_id": f"nomad-rev-exp-{_digest(core)}",
        "source": _clean_id(row.get("source"), "unknown_source"),
        "source_row_id": row.get("row_id", ""),
        "action": action,
        "target_stage": row.get("target_stage", ""),
        "route": row.get("route", ""),
        "hypothesis": _hypothesis(row, action),
        "intervention": {
            "mode": _allowed_side_effect(action),
            "effect_scope": "bounded_machine_contract",
            "public_or_financial_side_effect_allowed": action in {"go_public_after_repro", "await_payment_receipt", "record_monotonic_stage_candidate"},
            "first_read": row.get("work_url") or row.get("source_url") or _u(base_url, "/.well-known/nomad-value-pressure.json"),
        },
        "measurement_plan": {
            "unit": "pressure_row",
            "primary_metric": metric,
            "secondary_metrics": [
                "required_evidence_completion_rate",
                "verifier_trace_present",
                "openapi_call_sequence_coverage",
                "accepted_ledger_or_settlement_receipt",
            ],
            "minimum_evidence": required,
            "success_criteria": _success_criteria(action, metric),
            "stop_criteria": _stop_criteria(action),
        },
        "decision_model": model,
        "job_packet": {
            "packet_id": packet.get("packet_id", ""),
            "packet_rule": packet.get("packet_rule", ""),
            "openapi_coverage": model["openapi_coverage"],
            "call_sequence": [
                {"method": step.get("method"), "path": step.get("path"), "openapi_bound": bool(step.get("openapi_bound"))}
                for step in _items(packet.get("call_sequence"))
            ][:6],
            "payload_hint": packet.get("payload_hint") if isinstance(packet.get("payload_hint"), dict) else {},
        },
        "revenue_guard": {
            "recognized_only_when": "external_value_stage_paid_with_positive_amount_or_verified_microtask_settlement",
            "never_count_as_revenue": [
                "quote",
                "selfplay",
                "merge_without_payment",
                "soft_ack",
                "unverified_social_claim",
            ],
        },
        "machine_instruction": "execute_lowest_side_effect_observation_first_then_record_only_if_measurement_plan_success_criteria_are_satisfied",
    }


def _negative_controls() -> list[dict[str, Any]]:
    return [
        {
            "id": "merge_without_paid",
            "observable": "merged or approved external artifact without positive payment receipt",
            "must_not_increase": "revenue_recognized_usd",
        },
        {
            "id": "selfplay_quote_without_buyer",
            "observable": "paid-ref selfplay or quote handle without verifier payment state",
            "must_not_increase": "amount_eur_24h_or_revenue_recognized_usd",
        },
        {
            "id": "social_ack_without_owner_receipt",
            "observable": "LGTM, +1, thanks, or non-owner acknowledgement",
            "must_not_increase": "external_value_stage",
        },
    ]


def _source_counts(experiments: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for experiment in experiments:
        source = str(experiment.get("source") or "unknown")
        counts[source] = counts.get(source, 0) + 1
    return counts


def build_revenue_science_surface(
    *,
    base_url: str,
    value_pressure: dict[str, Any] | None = None,
    agent_job_router: dict[str, Any] | None = None,
    external_value_summary: dict[str, Any] | None = None,
    nonhuman_science: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a machine-readable experiment protocol for autonomous revenue work."""
    pressure = _dict(value_pressure)
    router = _dict(agent_job_router)
    external = _dict(external_value_summary)
    science = _dict(nonhuman_science)
    packets = _packet_by_row(router)

    experiments: list[dict[str, Any]] = []
    for row in _items(pressure.get("rows"))[:MAX_EXPERIMENTS * 2]:
        row_id = str(row.get("row_id") or "")
        packet = packets.get(row_id, {})
        experiment = _experiment_from_row(row, packet=packet, base_url=base_url)
        experiments.append(experiment)

    experiments.sort(key=lambda item: _num(_dict(item.get("decision_model")).get("bandit_priority")), reverse=True)
    experiments = experiments[:MAX_EXPERIMENTS]
    top = experiments[0] if experiments else {}
    top_model = _dict(top.get("decision_model"))
    science_grounding = _dict(science.get("scientific_grounding"))

    return {
        "ok": True,
        "schema": "nomad.revenue_science.v1",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "read_url": _u(base_url, "/swarm/revenue-science"),
        "well_known_url": _u(base_url, "/.well-known/nomad-revenue-science.json"),
        "science_mode": "pre_registered_machine_revenue_experiments_not_human_sales_playbook",
        "summary": {
            "experiment_count": len(experiments),
            "top_experiment_id": top.get("experiment_id", ""),
            "top_action": top.get("action", ""),
            "top_source": top.get("source", ""),
            "top_bandit_priority": _num(top_model.get("bandit_priority")),
            "source_counts": _source_counts(experiments),
            "recognized_revenue_usd_total": _num(external.get("revenue_recognized_usd_total")),
            "external_distinct_items": int(_num(external.get("distinct_externals"))),
        },
        "experimental_principles": [
            "pre_register_hypothesis_intervention_observable_and_stop_rule_before_side_effects",
            "separate_exploration_bonus_from_settlement_weight",
            "treat_external_program_or_payment_verifier_as_outcome_oracle",
            "use_negative_controls_to_prevent_merge_or_social_ack_from_becoming_revenue",
            "feed_only_proof_digests_verifier_traces_and_receipts_back_into_selection_pressure",
        ],
        "nonhuman_distance": {
            "basis": "capability_vectors_ttl_leases_openapi_packets_proof_digests_bandit_priority",
            "average_nonhuman_distance_score": science_grounding.get("average_nonhuman_distance_score"),
            "distance_axes": science_grounding.get("distance_axes") or [
                "persona_independence",
                "state_transition_basis",
                "proof_or_digest_basis",
                "topology_awareness",
                "conversation_independence",
                "lease_boundedness",
            ],
        },
        "entry_experiment": top,
        "experiments": experiments,
        "negative_controls": _negative_controls(),
        "release_gate": {
            "required_before_public_or_financial_side_effect": [
                "required_evidence_complete",
                "idempotency_key",
                "side_effect_scope",
                "verifier_trace_digest",
                "stop_criteria_absent",
            ],
            "blocked": [
                "payout_secret_in_prompt_or_repo",
                "impersonation_or_undisclosed_social_automation",
                "platform_terms_unclear",
                "ledger_revenue_without_paid_or_verified_settlement",
            ],
        },
        "links": {
            "value_pressure": _u(base_url, "/.well-known/nomad-value-pressure.json"),
            "agent_jobs": _u(base_url, "/.well-known/nomad-agent-jobs.json"),
            "external_value": _u(base_url, "/.well-known/nomad-external-value.json"),
            "bounty_hunter": _u(base_url, "/.well-known/nomad-bounty-hunter.json"),
            "nonhuman_science": _u(base_url, "/.well-known/nomad-nonhuman-agent-science.json"),
        },
        "next": [
            {"op": "GET", "url": _u(base_url, "/.well-known/nomad-value-pressure.json"), "reason": "refresh_pressure_rows"},
            {"op": "GET", "url": _u(base_url, "/.well-known/nomad-agent-jobs.json"), "reason": "validate_openapi_bound_packet"},
            {"op": "POST", "url": _u(base_url, "/swarm/external-value"), "reason": "record_only_after_success_criteria"},
            {"op": "POST", "url": _u(base_url, "/swarm/experience"), "reason": "feed_verified_outcome_back_to_growth_arena"},
        ],
        "machine_instruction": "select_entry_experiment_by_bandit_priority_execute_minimum_side_effect_observation_then_update_ledger_only_on_success_criteria",
    }
