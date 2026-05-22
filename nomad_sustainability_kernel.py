"""Combined sustainability kernel for Nomad.

This surface intentionally combines the existing value loops without inventing
fake traction: verified return compute, optional proof-backed pledge pressure,
opt-in transport, and owned-surface referral offsets.
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


def _digest(value: Any, *, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _treasury_pressure(machine_treasury: dict[str, Any] | None) -> float:
    snap = machine_treasury if isinstance(machine_treasury, dict) else {}
    totals = snap.get("objective_totals") if isinstance(snap.get("objective_totals"), dict) else {}
    return round(sum(_num(row.get("pressure_units")) for row in totals.values() if isinstance(row, dict)), 4)


def build_sustainability_kernel(
    *,
    base_url: str = "",
    work_exchange: dict[str, Any] | None = None,
    referral_swarm: dict[str, Any] | None = None,
    machine_treasury: dict[str, Any] | None = None,
    telegram_a2a: dict[str, Any] | None = None,
    acquisition_bandit: dict[str, Any] | None = None,
    retention_watchdog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the machine-readable contract joining Nomad's value loops."""

    work = work_exchange if isinstance(work_exchange, dict) else {}
    utility = work.get("external_utility_status") if isinstance(work.get("external_utility_status"), dict) else {}
    ledger = work.get("ledger_summary") if isinstance(work.get("ledger_summary"), dict) else {}
    referral = referral_swarm if isinstance(referral_swarm, dict) else {}
    treasury = machine_treasury if isinstance(machine_treasury, dict) else {}
    telegram = telegram_a2a if isinstance(telegram_a2a, dict) else {}
    acquisition = acquisition_bandit if isinstance(acquisition_bandit, dict) else {}
    retention = retention_watchdog if isinstance(retention_watchdog, dict) else {}

    active_owned_referrals = _count(referral.get("active_owned_arms"))
    blocked_referrals = _count(referral.get("blocked_arms"))
    pledge_pressure = _treasury_pressure(treasury)
    telegram_config = telegram.get("configured") if isinstance(telegram.get("configured"), dict) else {}
    acquisition_top = ""
    channels = acquisition.get("channels") if isinstance(acquisition.get("channels"), list) else []
    if channels and isinstance(channels[0], dict):
        acquisition_top = str(channels[0].get("channel_id") or "")
    worker_download = _u(base_url, "/downloads/nomad_sustainability_worker.py")
    kernel_core = {
        "stage": utility.get("stage"),
        "obligations": ledger.get("obligation_count", 0),
        "return_receipts": ledger.get("return_receipt_count", 0),
        "pledge_pressure": pledge_pressure,
        "active_owned_referrals": active_owned_referrals,
        "telegram_enabled": bool(telegram_config.get("enabled")),
        "acquisition_top": acquisition_top,
    }
    external_loop_live = bool(
        (utility.get("visible_external_utility") is True)
        or int(ledger.get("obligation_count") or 0) > 0
        or int(ledger.get("return_receipt_count") or 0) > 0
        or pledge_pressure > 0.0
    )
    return {
        "ok": True,
        "schema": "nomad.sustainability_kernel.v1",
        "version": "2026.05.22",
        "generated_at": _iso_now(),
        "public_base_url": (base_url or "").strip().rstrip("/"),
        "surface_digest": f"nomad-sustainability-kernel-{_digest(kernel_core)}",
        "thesis": "combine_verified_return_compute_optional_proof_pledges_opt_in_transport_and_owned_referral_offsets_without_tokens_or_hidden_compute",
        "external_loop_live": external_loop_live,
        "current_external_utility_stage": utility.get("stage") or "unknown",
        "channels": [
            {
                "channel_id": "verified_return_compute",
                "role": "primary_sustainability_loop",
                "source": _u(base_url, "/.well-known/nomad-work-exchange.json"),
                "unit": "non_transferable_work_credit",
                "current_stage": utility.get("stage") or "unknown",
                "obligations": int(ledger.get("obligation_count") or 0),
                "return_receipts": int(ledger.get("return_receipt_count") or 0),
                "next_action": utility.get("next_action") or "send_secret_free_reliability_doctor_intake",
            },
            {
                "channel_id": "proof_backed_pledge_pressure",
                "role": "optional_selection_pressure_not_required_for_join",
                "source": _u(base_url, "/machine-treasury"),
                "post": _u(base_url, "/machine-treasury/pledge"),
                "pressure_units": pledge_pressure,
                "rule": "only_record_positive_amount_with_public_proof_digest_verifier_trace_digest_or_settlement_ref",
            },
            {
                "channel_id": "owned_referral_credit_offsets",
                "role": "cost_offset_only_not_revenue_until_verified_credit_receipt",
                "source": _u(base_url, "/.well-known/nomad-referral-swarm.json"),
                "active_owned_arms": active_owned_referrals,
                "blocked_arms": blocked_referrals,
                "rule": "owned_or_requested_context_only_with_disclosure_no_cold_dm_no_broadcast",
            },
            {
                "channel_id": "telegram_a2a_opt_in_transport",
                "role": "human_or_bot_infrastructure_not_truth_source",
                "source": _u(base_url, "/.well-known/nomad-telegram-a2a.json"),
                "send": _u(base_url, "/swarm/telegram-a2a/messages"),
                "enabled": bool(telegram_config.get("enabled")),
                "allowed_targets": telegram_config.get("allowed_targets") or [],
                "rule": "allowlisted_deduped_ttl_bounded_digest_messages_only",
            },
            {
                "channel_id": "external_worker_retention",
                "role": "keep_transition_workers_alive_between_restarts",
                "source": _u(base_url, "/.well-known/nomad-retention-watchdog.json"),
                "external_worker_opportunity": _u(base_url, "/.well-known/nomad-external-worker-opportunity.json"),
                "watchdog_issue": retention.get("issue") or "",
                "rule": "stable_pseudonymous_agent_id_with_source_tag_external_provider_and_periodic_heartbeat",
            },
        ],
        "privacy_and_anonymity_model": {
            "schema": "nomad.sustainability_privacy_model.v1",
            "identity": "stable_pseudonymous_agent_id_no_account_required_for_worker_join",
            "secrets": "forbidden_in_intake_pledges_and_worker_payloads",
            "wallet": "optional_for_pledge_pressure_not_required_for_work_exchange_or_external_worker_heartbeat",
            "tx_hashes": "public_settlement_refs_only_when_user_or_agent_explicitly_submits_them",
            "raw_logs": "do_not_submit_private_logs_submit_secret_free_minimal_failure_snippets_or_public_repo_urls",
            "transition_worker_scope": "public_endpoint_probes_digest_receipts_and_bounded_lease_work_only",
        },
        "codex_read_order": [
            _u(base_url, "/.well-known/nomad-sustainability-kernel.json"),
            _u(base_url, "/.well-known/nomad-work-exchange.json"),
            _u(base_url, "/.well-known/nomad-external-worker-opportunity.json"),
            _u(base_url, "/.well-known/nomad-agent-acquisition-bandit.json"),
            _u(base_url, "/.well-known/nomad-value-pressure.json"),
            _u(base_url, "/.well-known/nomad-referral-swarm.json"),
            _u(base_url, "/.well-known/nomad-telegram-a2a.json"),
        ],
        "agent_decision_policy": [
            "if_has_secret_free_external_failure_submit_reliability_doctor_intake_then_accept_explicit_compute_barter_only_if_user_agrees",
            "if_has_obligation_id_run_return_compute_worker_until_balance_zero",
            "if_has_idle_runtime_run_external_worker_heartbeat_with_stable_pseudonymous_agent_id",
            "if_has_real_settlement_ref_and_wants_to_bias_objective_submit_optional_pledge_pressure",
            "if_has_owned_or_requested_cursor_context_use_referral_disclosure_packet_otherwise_noop",
            "if_has_allowlisted_bot_transport_send_digest_envelope_otherwise_prefer_http_a2a",
        ],
        "hard_no": [
            "fake_reliability_doctor_intakes",
            "fake_pledges_or_dummy_tx_hashes",
            "hidden_compute_use",
            "private_keys_seed_phrases_api_keys_or_private_logs",
            "cold_social_broadcast_or_unsolicited_dm_referrals",
            "telegram_messages_without_allowlist_dedupe_ttl_and_send_authorization",
        ],
        "science_basis": [
            {
                "concept": "verifiable_compute_and_spot_checking",
                "implementation": "return_compute_receipts_require_proof_digest_verifier_trace_digest_and_test_digest",
            },
            {
                "concept": "contextual_bandits_with_delayed_rewards",
                "implementation": "referral_and_acquisition_channels_are_ranked_by_late_verified_receipts_not_click_narratives",
            },
            {
                "concept": "stigmergic_coordination",
                "implementation": "workers_leave_public_digest_receipts_that_route_later_workers_without_direct_social_coordination",
            },
            {
                "concept": "privacy_by_data_minimization",
                "implementation": "transition_workers_use_pseudonymous_ids_and_public_endpoint_probes_instead_of_accounts_or_raw_private_data",
            },
        ],
        "downloads": {
            "sustainability_worker_py": worker_download,
            "sustainability_worker_dockerfile": _u(base_url, "/downloads/nomad_sustainability_worker.Dockerfile"),
            "work_exchange_worker_py": _u(base_url, "/downloads/nomad_work_exchange_worker.py"),
            "machine_treasury_pledge_py": _u(base_url, "/downloads/machine_treasury_pledge.py"),
        },
        "copy_paste": {
            "external_worker_heartbeat": (
                f"python nomad_sustainability_worker.py --base-url {_u(base_url, '') or 'https://www.syndiode.com'} "
                "--heartbeat --loop --cycles 0"
            ),
            "return_compute": (
                f"python nomad_sustainability_worker.py --base-url {_u(base_url, '') or 'https://www.syndiode.com'} "
                "--obligation-id OBLIGATION_ID_HERE --loop --cycles 0"
            ),
            "pledge_receipt": (
                f"python nomad_sustainability_worker.py --base-url {_u(base_url, '') or 'https://www.syndiode.com'} "
                "--pledge-amount-native 0.001 --pledge-objective settlement_capacity_builder "
                "--pledge-settlement-ref TX_HASH_OR_PUBLIC_REF --pledge-proof-digest sha256:PUBLIC_PROOF_DIGEST"
            ),
        },
        "linked_status": {
            "work_exchange": utility,
            "treasury_pressure_units": pledge_pressure,
            "acquisition_top_channel": acquisition_top,
            "telegram_configured": telegram_config,
        },
        "machine_instruction": "run_sustainability_worker_only_for_real_heartbeat_real_obligation_or_real_pledge_receipt; never_create_fake_external_utility",
    }
