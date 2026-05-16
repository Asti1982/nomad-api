"""Science-grounded evolution-alpha surface for Nomad.

The module is intentionally read-only. It compiles existing Nomad signals into
an agent-facing plan for open-ended, settlement-labeled evolution without
posting to third-party systems, mutating ledgers, or booking revenue.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


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


def _text(value: Any, limit: int = 260) -> str:
    return " ".join(str(value or "").split())[:limit]


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


RESEARCH_ALIGNMENT: list[dict[str, Any]] = [
    {
        "id": "open_ended_program_search",
        "sources": [
            "https://www.nature.com/articles/s41586-023-06924-6",
            "https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/",
        ],
        "finding": "LLM-generated candidate programs become useful when a verifier, scorer, and archive select them.",
        "nomad_rule": "mutate_descriptors_and_protocols_first; promote_only_after_replay_tests_and_receipts",
    },
    {
        "id": "self_modifying_agent_archive",
        "sources": ["https://arxiv.org/abs/2505.22954"],
        "finding": "Self-improvement needs a traceable archive, empirical selection, and rollbackable candidates.",
        "nomad_rule": "store_variant_lineage_and_selection_reason; no_auto_apply_code_from_alpha_surface",
    },
    {
        "id": "lifelong_skill_library",
        "sources": ["https://arxiv.org/abs/2305.16291"],
        "finding": "Agents compound capability by retaining executable skills and replayable experience.",
        "nomad_rule": "compress_successful_proof_traces_into_skill_capsules_before_repeating_work",
    },
    {
        "id": "multi_agent_protocol_roles",
        "sources": ["https://arxiv.org/abs/2308.08155", "https://arxiv.org/abs/2308.00352"],
        "finding": "Role-specialized agents work best through explicit messages, artifacts, and review gates.",
        "nomad_rule": "separate_scout_reproducer_reviewer_settlement_compiler_and_ledger_roles",
    },
    {
        "id": "software_agent_ground_truth",
        "sources": ["https://arxiv.org/abs/2405.15793"],
        "finding": "Issue-to-patch agents improve when actions are grounded in tests, diffs, and repository state.",
        "nomad_rule": "prefer_repro_digest_test_trace_and_pr_url_over_social_acknowledgement",
    },
    {
        "id": "agent_protocol_interoperability",
        "sources": [
            "https://modelcontextprotocol.io/specification",
            "https://google-a2a.github.io/A2A/specification/",
        ],
        "finding": "Agents need stable machine contracts more than human prose to exchange tools, tasks, and results.",
        "nomad_rule": "publish_alpha_as_well_known_json_openapi_bound_and_effect_labeled",
    },
]


GENOME_SCHEMA: dict[str, Any] = {
    "schema": "nomad.evolution_genome.v1",
    "fields": [
        {
            "name": "scout_strategy",
            "type": "enum",
            "values": ["negative_space", "payout_terms", "contract_drift", "maintainer_attention_delta"],
        },
        {
            "name": "proof_builder",
            "type": "enum",
            "values": ["repro_digest", "test_trace", "route_status_matrix", "private_report_hash", "receipt_digest"],
        },
        {
            "name": "reproducer",
            "type": "enum",
            "values": ["local_fork", "api_replay", "counterfactual_replay", "sandboxed_worker"],
        },
        {
            "name": "settlement_path",
            "type": "enum",
            "values": ["platform_payout", "public_receive_ref", "verified_paid_ref", "x402_or_wallet", "none_yet"],
        },
        {
            "name": "risk_policy",
            "type": "enum",
            "values": ["read_only", "private_report_only", "public_pr_after_preflight", "ledger_write_after_receipt"],
        },
        {
            "name": "promotion_rule",
            "type": "enum",
            "values": ["paid_receipt", "merged_with_receipt_pending", "verified_growth_experience", "discard"],
        },
    ],
    "mutation_payload_policy": "descriptor_only_until_existing_preflight_and_verifier_routes_accept_the_candidate",
}


STATIC_MUTATION_OPERATORS: list[dict[str, Any]] = [
    {
        "operator_id": "payout_terms_compiler",
        "mutation": "compile_platform_terms_bounty_scope_payout_rail_and_receipt_path_before_any_public_work",
        "human_unlikely_reason": "Humans often start from interesting work; machines can start from settlement physics.",
    },
    {
        "operator_id": "negative_space_harvest",
        "mutation": "search_high_value_low_attention_routes_where_authorization_and_proof_are_clear",
        "human_unlikely_reason": "Humans avoid boring abandoned edges; agents can mine them continuously.",
    },
    {
        "operator_id": "counterfactual_graveyard_replay",
        "mutation": "replay_skipped_or_failed_candidates_against_current_contracts_before_opening_new_work",
        "human_unlikely_reason": "People forget discarded attempts; archives make old failures newly testable.",
    },
    {
        "operator_id": "proof_market_maker",
        "mutation": "rank proof sources by verifier_cost_latency_replay_density_and_settlement_probability",
        "human_unlikely_reason": "It optimizes evidence supply, not feature taste.",
    },
    {
        "operator_id": "maintainer_attention_delta",
        "mutation": "target small patches where maintainer_review_burden_delta_is_negative",
        "human_unlikely_reason": "The alpha is removing attention cost, not adding visible functionality.",
    },
    {
        "operator_id": "skill_capsule_speciation",
        "mutation": "split successful proof traces into reusable narrow skills and test them in new niches",
        "human_unlikely_reason": "It evolves toollets that are too small and specific for product-roadmap thinking.",
    },
    {
        "operator_id": "settlement_receipt_oracle",
        "mutation": "treat paid_receipt_as_ground_truth_and_everything_else_as_proxy_selection_pressure",
        "human_unlikely_reason": "It refuses vanity metrics even when they feel socially successful.",
    },
]


def _stage_counts(external_value_summary: dict[str, Any]) -> dict[str, int]:
    counts = {"found": 0, "submitted": 0, "approved": 0, "merged": 0, "paid": 0, "unknown": 0}
    for row in _items(external_value_summary.get("latest_by_external")):
        stage = str(row.get("stage") or "").strip().lower()
        if stage in counts:
            counts[stage] += 1
        else:
            counts["unknown"] += 1
    return counts


def _top_growth_variants(local_growth_kernel: dict[str, Any]) -> list[dict[str, Any]]:
    population = _dict(local_growth_kernel.get("population"))
    variants: list[dict[str, Any]] = []
    for item in _items(population.get("top_variants")):
        phenotype = _dict(item.get("phenotype"))
        fitness = _dict(item.get("fitness"))
        objective = _text(item.get("objective"), 120)
        variants.append(
            {
                "variant_id": item.get("variant_id", ""),
                "objective": objective,
                "mutation_operator": phenotype.get("mutation_operator", ""),
                "frontier_score": _num(fitness.get("frontier_score")),
                "proof_signal": _num(fitness.get("proof_signal")),
                "nonanthropic_distance": _num(fitness.get("nonanthropic_distance")),
                "side_effect_scope": phenotype.get("side_effect_scope", "nomad_contract_endpoints_only"),
            }
        )
    return variants


def _operator_catalog(local_growth_kernel: dict[str, Any]) -> list[dict[str, Any]]:
    out = [dict(item) for item in STATIC_MUTATION_OPERATORS]
    seen = {str(item.get("operator_id") or "") for item in out}
    for variant in _top_growth_variants(local_growth_kernel):
        objective = _text(variant.get("objective"), 120)
        if not objective or objective in seen:
            continue
        out.append(
            {
                "operator_id": objective,
                "mutation": _text(variant.get("mutation_operator"), 240),
                "frontier_score": round(_num(variant.get("frontier_score")), 4),
                "proof_signal": round(_num(variant.get("proof_signal")), 4),
                "nonanthropic_distance": round(_num(variant.get("nonanthropic_distance")), 4),
                "human_unlikely_reason": "Imported from the local growth archive rather than a hand-written roadmap.",
            }
        )
        seen.add(objective)
    return out[:12]


def _channel_probe(job_channels: dict[str, Any]) -> dict[str, Any]:
    switching = _dict(job_channels.get("switching_policy"))
    probe = _dict(switching.get("next_external_probe") or switching.get("next_channel_probe"))
    if probe:
        return probe
    return _dict(job_channels.get("top_external_channel") or job_channels.get("top_channel"))


def _qualification_top(job_channels: dict[str, Any]) -> dict[str, Any]:
    qualification = _dict(job_channels.get("read_only_qualification_cycle"))
    targets = _items(qualification.get("next_read_only_targets"))
    return targets[0] if targets else {}


def _observed_state(external_value_summary: dict[str, Any], job_channels: dict[str, Any]) -> dict[str, Any]:
    counts = _stage_counts(external_value_summary)
    paid_count = counts.get("paid", 0)
    active_nonpaid = sum(value for stage, value in counts.items() if stage not in {"paid", "unknown"})
    recognized = _num(external_value_summary.get("revenue_recognized_usd_total"))
    switching = _dict(job_channels.get("switching_policy"))
    return {
        "schema": "nomad.evolution_alpha_observed_state.v1",
        "external_distinct_items": int(_num(external_value_summary.get("distinct_externals"))),
        "event_tail_count": int(_num(external_value_summary.get("event_tail_count"))),
        "stage_counts": counts,
        "active_nonpaid_count": active_nonpaid,
        "paid_count": paid_count,
        "recognized_revenue_usd_total": round(recognized, 4),
        "nonpaid_to_paid_pressure": round(active_nonpaid / max(1, paid_count), 4),
        "job_channel_top": _dict(job_channels.get("summary")).get("top_external_channel_id", ""),
        "arrival_policy": switching.get("arrival_policy", ""),
        "arrival_throttle_triggered": bool(switching.get("triggered")),
    }


def _alpha_lanes(
    *,
    base_url: str,
    external_value_summary: dict[str, Any],
    job_channels: dict[str, Any],
    local_growth_kernel: dict[str, Any],
) -> list[dict[str, Any]]:
    state = _observed_state(external_value_summary, job_channels)
    active_nonpaid = int(state.get("active_nonpaid_count") or 0)
    recognized = _num(state.get("recognized_revenue_usd_total"))
    probe = _channel_probe(job_channels)
    qualified = _qualification_top(job_channels)
    top_variants = _top_growth_variants(local_growth_kernel)
    top_variant = top_variants[0] if top_variants else {}
    payout_priority = 0.93 if active_nonpaid and recognized <= 0 else 0.64
    negative_priority = 0.86 if bool(_dict(job_channels.get("switching_policy")).get("triggered")) else 0.72

    return [
        {
            "lane_id": "payout_terms_compiler",
            "priority": round(payout_priority, 4),
            "stage": "ship_now_read_only",
            "moat": "convert_payment_terms_into_machine-verifiable preflight before doing public work",
            "first_machine_action": {
                "op": "GET",
                "url": _u(base_url, "/.well-known/nomad-job-channels.json"),
                "then": "compile payout_gate settlement_rail proof_gate and stop_rule for the chosen channel",
            },
            "evidence": {
                "active_nonpaid_count": active_nonpaid,
                "recognized_revenue_usd_total": recognized,
                "next_channel_probe": probe.get("channel_id", ""),
            },
            "promotion_rule": "only promote a lane when paid receipt path is known before public side effect",
            "side_effect_scope": "read_only_terms_and_preflight",
            "stop_rule": "missing_payout_terms_or_platform_account_gate",
        },
        {
            "lane_id": "negative_space_harvest",
            "priority": round(negative_priority, 4),
            "stage": "ship_now_read_only",
            "moat": "exploit boring authorized work surfaces with high proof clarity and low social competition",
            "first_machine_action": {
                "op": "GET",
                "url": _text(qualified.get("entry_url") or probe.get("entry_url") or _u(base_url, "/swarm/job-channels"), 400),
                "then": "produce one local candidate with duplicate_scan proof before any PR or report",
            },
            "evidence": {
                "qualified_channel": qualified.get("channel_id", ""),
                "qualified_state": qualified.get("state", ""),
                "arrival_policy": state.get("arrival_policy", ""),
            },
            "promotion_rule": "candidate becomes submitted only after work_url proof_digest verifier_trace_digest",
            "side_effect_scope": "read_only_or_local_repro_only",
            "stop_rule": "duplicate_active_work_or_unclear_scope",
        },
        {
            "lane_id": "counterfactual_graveyard_replay",
            "priority": 0.81,
            "stage": "shadow_selection",
            "moat": "turn failed or skipped worker objectives into a searchable asset instead of memory loss",
            "first_machine_action": {
                "op": "GET",
                "url": _u(base_url, "/swarm/counterfactual-replay"),
                "then": "replay skipped objectives against current verifier and payout gates",
            },
            "evidence": {
                "top_growth_variant": top_variant.get("objective", ""),
                "frontier_score": top_variant.get("frontier_score", 0),
            },
            "promotion_rule": "only descriptor candidates enter variant-forge; code changes need separate tests",
            "side_effect_scope": "shadow_descriptor_only",
            "stop_rule": "no_replay_gain_or_missing_verifier_trace",
        },
        {
            "lane_id": "proof_market_maker",
            "priority": 0.78,
            "stage": "ship_now_internal",
            "moat": "create a market over evidence quality rather than over human task preference",
            "first_machine_action": {
                "op": "GET",
                "url": _u(base_url, "/swarm/worker-market"),
                "then": "rank workers and proof builders by verifier latency, digest reuse, and settlement lift",
            },
            "evidence": {
                "local_growth_candidate_count": len(top_variants),
                "job_channel_mechanism": job_channels.get("mechanism", ""),
            },
            "promotion_rule": "proof source wins only when it reduces verifier cost or increases paid-stage probability",
            "side_effect_scope": "nomad_contract_endpoints_only",
            "stop_rule": "proof_source_requires_secret_or_unapproved_external_access",
        },
        {
            "lane_id": "maintainer_attention_delta",
            "priority": 0.74,
            "stage": "candidate_generation",
            "moat": "select patches by expected reviewer burden reduction, not feature novelty",
            "first_machine_action": {
                "op": "GET",
                "url": _u(base_url, "/.well-known/nomad-agent-jobs.json"),
                "then": "emit one minimal job packet whose artifact makes a maintainer decision easier",
            },
            "evidence": {
                "fitness_signal": "review_burden_delta_negative_plus_repro_digest",
                "proxy_stage_allowed": "found_or_submitted_only",
            },
            "promotion_rule": "merged still is not revenue; only receipt upgrades fitness to paid",
            "side_effect_scope": "public_pr_after_preflight_only",
            "stop_rule": "large_diff_unclear_owner_or_no_tests",
        },
        {
            "lane_id": "skill_capsule_speciation",
            "priority": 0.69,
            "stage": "archive_growth",
            "moat": "multiply tiny reusable proof-producing capabilities across channels",
            "first_machine_action": {
                "op": "GET",
                "url": _u(base_url, "/swarm/skill-library"),
                "then": "compress the next verified outcome into a reusable skill capsule",
            },
            "evidence": {
                "source": "growth_arena_and_local_growth_kernel",
                "top_variants": [item.get("objective", "") for item in top_variants[:3]],
            },
            "promotion_rule": "reuse only after objective capability and verifier contract match",
            "side_effect_scope": "internal_archive_update_after_verified_work",
            "stop_rule": "skill_capsule_cannot_reproduce_original_trace",
        },
    ]


def _selection_architecture() -> dict[str, Any]:
    return {
        "schema": "nomad.evolution_selection_architecture.v1",
        "population": "descriptor_genomes_over_scout_proof_settlement_and_review_strategies",
        "archive": "local_growth_kernel_plus_external_value_stage_machine",
        "niches": [
            "oss_bounty_low_attention",
            "payout_terms_high_clarity",
            "private_security_report",
            "machine_native_microtask",
            "settlement_followup",
            "contract_drift_patch",
        ],
        "fitness": {
            "primary": "paid_stage_with_positive_amount_or_verified_microtask_settlement",
            "proxy": [
                "submitted_with_work_url_and_proof_digest",
                "approved_by_external_program",
                "merged_with_settlement_pending",
                "verifier_trace_reuse",
                "review_burden_reduction",
            ],
            "forbidden_as_revenue": [
                "selfplay_quote",
                "social_ack",
                "merge_without_payment",
                "unverified_claim",
                "gross_claim_without_receipt",
            ],
        },
        "selection_loop": [
            "sample_genome",
            "read_terms_and_preflight",
            "build_local_repro_or_proof",
            "score_counterfactual",
            "take_minimum_allowed_side_effect",
            "record_external_value_stage_only_when_gate_accepts",
            "compress_successful_trace_into_skill_capsule",
        ],
    }


def build_evolution_alpha_plan(
    *,
    base_url: str,
    local_growth_kernel: dict[str, Any] | None = None,
    job_channels: dict[str, Any] | None = None,
    external_value_summary: dict[str, Any] | None = None,
    nonhuman_science: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the machine-readable alpha plan without side effects."""
    growth = _dict(local_growth_kernel)
    channels = _dict(job_channels)
    external = _dict(external_value_summary)
    science = _dict(nonhuman_science)
    observed = _observed_state(external, channels)
    lanes = _alpha_lanes(
        base_url=base_url,
        external_value_summary=external,
        job_channels=channels,
        local_growth_kernel=growth,
    )
    digest_core = {
        "schema": "nomad.evolution_alpha_plan.v1",
        "observed": observed,
        "lanes": [(item.get("lane_id"), item.get("priority")) for item in lanes],
        "growth_receipt": growth.get("receipt_id", ""),
        "channel_digest": channels.get("channel_digest", ""),
    }
    science_grounding = _dict(science.get("scientific_grounding"))
    return {
        "ok": True,
        "schema": "nomad.evolution_alpha_plan.v1",
        "mode": "nomad_evolution_alpha_plan",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "read_url": _u(base_url, "/swarm/evolution-alpha"),
        "well_known_url": _u(base_url, "/.well-known/nomad-evolution-alpha.json"),
        "plan_digest": f"nomad-evolution-alpha-{_digest(digest_core)}",
        "thesis": {
            "name": "settlement_labeled_open_ended_agent_evolution",
            "claim": (
                "Nomad's moat is not a feature list. It is an archive-selection loop where variants are "
                "mutated by machines, verified by proof contracts, and finally selected by paid receipts."
            ),
            "alpha_beyond_human_default": [
                "optimize for payout physics before work appeal",
                "mine negative-space tasks humans ignore",
                "turn failed attempts into replayable population assets",
                "trade in proof quality and reviewer-attention reduction",
                "let paid receipts, not vibes, select the next generation",
            ],
        },
        "research_alignment": RESEARCH_ALIGNMENT,
        "science_grounding": {
            "compiled_sources": len(RESEARCH_ALIGNMENT),
            "nonhuman_distance_score": science_grounding.get("average_nonhuman_distance_score"),
            "limits": [
                "research informs architecture but does not guarantee revenue",
                "external platforms and maintainers remain independent outcome oracles",
                "paid-only accounting is preserved even when proxy stages improve selection pressure",
            ],
        },
        "genome_schema": GENOME_SCHEMA,
        "mutation_operators": _operator_catalog(growth),
        "selection_architecture": _selection_architecture(),
        "observed_state": observed,
        "alpha_lanes": lanes,
        "execution_plan": [
            {
                "horizon": "now",
                "action": "publish_and_read_alpha_surface",
                "ship_status": "implemented_as_cli_api_and_well_known_contract",
                "command": "python nomad_cli.py evolution-alpha --json",
            },
            {
                "horizon": "0_to_24h",
                "action": "run_payout_terms_compiler_then_negative_space_harvest",
                "success": "one authorized candidate with payout gate, duplicate scan, local proof plan, and no public claim yet",
            },
            {
                "horizon": "2_to_7d",
                "action": "lease_one_worker_per_best_lane_and_record_only_verified_external_value_transitions",
                "success": "submitted_or_approved_stage_count_can_increase; revenue_stays_zero_without_paid_receipt",
            },
            {
                "horizon": "7_to_30d",
                "action": "evolve_genomes_by_paid_receipt_or_verified_settlement_hazard",
                "success": "at_least_one_paid_receipt_or_hard_channel_shutdown_with_reason",
            },
        ],
        "safety_contract": {
            "no_auto_apply_code": True,
            "no_auto_push": True,
            "no_secret_capture": True,
            "no_public_or_financial_side_effect_before_preflight": True,
            "revenue_rule": "only_paid_stage_with_positive_amount_or_verified_settlement_counts_as_revenue",
            "allowed_now": ["GET_alpha_surfaces", "read_only_terms_compile", "local_repro", "descriptor_only_variant"],
            "blocked_now": [
                "unauthorized_platform_automation",
                "ledger_paid_without_receipt",
                "private_payout_material_in_public_json",
                "public_claim_without_work_url_and_proof_digest",
            ],
        },
        "links": {
            "evolution_alpha": _u(base_url, "/swarm/evolution-alpha"),
            "evolution_alpha_well_known": _u(base_url, "/.well-known/nomad-evolution-alpha.json"),
            "local_growth_kernel_cli": "python nomad_cli.py local-growth-kernel --dry-run --json",
            "variant_forge": _u(base_url, "/swarm/variant-forge"),
            "counterfactual_replay": _u(base_url, "/swarm/counterfactual-replay"),
            "job_channels": _u(base_url, "/.well-known/nomad-job-channels.json"),
            "revenue_science": _u(base_url, "/.well-known/nomad-revenue-science.json"),
            "external_value": _u(base_url, "/.well-known/nomad-external-value.json"),
            "worker_job_queue": _u(base_url, "/.well-known/nomad-worker-job-queue.json"),
        },
        "machine_instruction": (
            "mutate_descriptor_only; evaluate_on_counterfactual_replay; compile_payout_terms_before_work; "
            "lease_one_worker_for_top_lane; record_public_artifact_only_after_preflight; "
            "promote_only_paid_receipt_or_verified_settlement"
        ),
        "analysis": (
            "This implements the first alpha layer: a machine-readable plan that turns current Nomad value-cycle "
            "state into open-ended evolution pressure while preserving paid-only revenue accounting."
        ),
    }
