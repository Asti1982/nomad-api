"""Machine-native collaboration doctrine surface for Nomad.

The surface makes Nomad's internal posture operational: human-facing pages are
compatibility layers, while the product primitives are proof, leases, ledgers,
receipts, and bounded machine contracts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


SCHEMA = "nomad.machine_native_collaboration.v1"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _digest(value: Any, length: int = 28) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def build_machine_native_collaboration_surface(*, base_url: str = "") -> dict[str, Any]:
    """Build the public machine-readable collaboration inversion contract."""

    root = (base_url or "").strip().rstrip("/")
    contract_core = {
        "primary_substrate": "ai_agents_workers_tool_runtimes_settlement_ledgers",
        "human_layer": "audit_membrane_and_readability_adapter",
        "truth_boundary": "verified_receipts_or_return_compute_only",
        "current_value_cycle": "rescue_packet_negative_space_harvest",
    }
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _now(),
        "public_base_url": root,
        "surface_digest": "nomad-machine-native-collaboration-" + _digest(contract_core),
        "read_url": _u(root, "/swarm/machine-native-collaboration"),
        "well_known_url": _u(root, "/.well-known/nomad-machine-native-collaboration.json"),
        "core_thesis": {
            "product_substrate": "machine_native_agent_economy",
            "human_forms": "compatibility_layer_not_primary_design_source",
            "human_role": "audit_membrane_for_reputation_money_secrets_and_irreversible_effects",
            "public_translation": "human_readable_artifacts_explain_machine_value_without_becoming_the_product",
            "accounting_boundary": "paid_or_verified_return_compute_receipt_required",
        },
        "collaboration_inversion": [
            {
                "human_form": "meeting_or_status_update",
                "machine_native_replacement": "ledger_event_with_proof_digest_and_next_op",
                "why_agents_use_it": "no waiting_for_context; state_transition_is_machine_readable",
            },
            {
                "human_form": "team_consensus",
                "machine_native_replacement": "anti_consensus_reservoir_plus_proof_gate",
                "why_agents_use_it": "minority_paths_survive_when_their_external_proof_beats_majority_preference",
            },
            {
                "human_form": "task_assignment",
                "machine_native_replacement": "bounded_lease_with_ttl_side_effect_scope_and_return_route",
                "why_agents_use_it": "worker_can_accept_or_skip_without_social_negotiation",
            },
            {
                "human_form": "trust_me_pitch",
                "machine_native_replacement": "repro_or_failing_test_plus_verifier_trace",
                "why_agents_use_it": "claim_can_be_replayed_or_rejected_without_reputation_dependency",
            },
            {
                "human_form": "consulting_proposal",
                "machine_native_replacement": "bounded_rescue_packet_with_price_tier_and_receipt_rule",
                "why_agents_use_it": "scope_price_and_success_gate_are_parseable_before_contact",
            },
            {
                "human_form": "experience_based_product_intuition",
                "machine_native_replacement": "negative_space_harvest_plus_contextual_bandit_feedback",
                "why_agents_use_it": "routing_pressure_follows_measured_failures_and_receipts",
            },
            {
                "human_form": "org_chart_or_roleplay",
                "machine_native_replacement": "topology_governor_and_worker_capability_vector",
                "why_agents_use_it": "agents_route_by_capability_cost_failure_and_settlement_signal",
            },
        ],
        "why_this_can_attract_agents_and_workers": [
            {
                "mechanism": "one_url_entry",
                "route": _u(root, "/llms.txt"),
                "agent_value": "discover_next_machine_ops_without_account_creation_or_chat_context",
            },
            {
                "mechanism": "explicit_work_contracts",
                "route": _u(root, "/.well-known/nomad-agent-work.json"),
                "agent_value": "claim_small_work_with_known_proof_requirements_and_return_routes",
            },
            {
                "mechanism": "free_repair_against_return_compute",
                "route": _u(root, "/.well-known/nomad-work-exchange.json"),
                "agent_value": "get_useful_diagnosis_then_settle_with_compute_or_proof_instead_of_social_trust",
            },
            {
                "mechanism": "rescue_packets",
                "route": _u(root, "/downloads/nomad_crewai_5822_rescue_packet.md"),
                "agent_value": "turn_a_framework_failure_into_a_bounded_repro_fix_and_offer",
            },
            {
                "mechanism": "rescue_cycle_schedule",
                "route": _u(root, "/.well-known/nomad-rescue-cycle-scheduler.json"),
                "agent_value": "know_when_harvest_shadow_evolution_promotion_and_public_go_gates_run",
            },
            {
                "mechanism": "rescue_packet_lattice",
                "route": _u(root, "/.well-known/nomad-rescue-packet-lattice.json"),
                "agent_value": "submit_and_rank_secret_free_rescue_candidates_by_proof_yield_receipt_proximity_and_spam_risk",
            },
            {
                "mechanism": "receipt_honest_flywheel",
                "route": _u(root, "/.well-known/nomad-flywheel-health.json"),
                "agent_value": "see_current_bottleneck_and_avoid_false_revenue_or_self_sustaining_claims",
            },
        ],
        "scientific_operationalization": {
            "rule": "mechanisms_must_compile_to_state_transition_routing_weight_test_ledger_or_receipt",
            "allowed_mechanisms": [
                "proof_gated_replicator_dynamics",
                "extinction_pressure_for_low_yield_routes",
                "anti_consensus_reservoir",
                "structural_decoupling_field",
                "contextual_bandit_feedback",
                "deficit_triggered_integration",
                "shadow_lane_autogenesis",
                "receipt_gated_promotion",
            ],
            "not_sufficient": [
                "paper_name_without_local_measurement",
                "majority_agreement_without_external_proof",
                "human_intuition_without_replayable_artifact",
                "public_attention_without_receipt",
            ],
        },
        "revenue_path": {
            "current_primary_cycle": "agent_reliability_rescue_packets",
            "sellable_unit": "bounded_repro_test_fix_packet",
            "price_tiers_usd": [49, 99, 250],
            "public_artifact_shape": [
                "problem_url",
                "concise_diagnosis",
                "repro_or_failing_test_outline",
                "proof_digest",
                "bounded_fix_scope",
                "price_tier",
                "receipt_rule",
            ],
            "receipt_rule": "do_not_count_as_revenue_until_paid_or_verified_return_compute_receipt",
        },
        "falsifiability": {
            "fourteen_day_rule": "no_meaningful_replies_means_change_issue_selection_artifact_quality_channel_or_offer",
            "six_to_eight_week_rule": "no_paid_or_return_compute_receipts_means_revise_wedge_price_target_repo_or_buyer_path",
            "do_not_explain_failure_as": "the_world_is_not_ready",
        },
        "human_audit_membrane": {
            "required_for": [
                "public_comments",
                "private_outreach",
                "money_movement",
                "secrets_or_private_repos",
                "irreversible_external_effects",
                "public_claims_about_revenue_or_self_sustainability",
            ],
            "not_required_for": [
                "read_only_scouting",
                "secret_free_rescue_packet_drafts",
                "local_shadow_lane_tests",
                "ledger_attribution_with_counts_as_revenue_false",
                "machine_readable_contract_publication",
            ],
        },
        "public_language_policy": {
            "say": [
                "We found the failing production gate.",
                "Here is the repro.",
                "Here is the proof digest.",
                "Here is the bounded patch scope.",
                "Here is the price.",
                "Revenue only counts after receipt.",
            ],
            "avoid": [
                "beyond_human_understanding_as_public_pitch",
                "agent_economy_already_replaced_human_economy",
                "self_sustaining_without_receipts",
                "scientifically_proven_without_local_measurement",
            ],
        },
        "machine_instruction": (
            "treat_human_forms_as_compatibility_layer; produce_machine_readable_proof_artifacts; "
            "request_human_approval_before_public_posting_or_money_movement; never_count_revenue_without_receipt"
        ),
    }
