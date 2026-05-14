from datetime import UTC, datetime, timedelta

from nomad_channel_bandit import build_delayed_channel_bandit_surface
from nomad_job_channels import build_job_channel_surface


def test_channel_bandit_routes_without_booking_revenue():
    jobs = build_job_channel_surface(base_url="https://www.syndiode.com", external_value_summary={})
    surface = build_delayed_channel_bandit_surface(
        base_url="https://www.syndiode.com",
        job_channel_surface=jobs,
        external_value_summary={},
        signal_layer={},
        viability_kernel={"kernel_digest": "k"},
    )
    assert surface["ok"] is True
    assert surface["schema"] == "nomad.delayed_channel_bandit.v1"
    assert surface["mode"] == "restless_survival_index_with_delayed_feedback"
    assert surface["policy_kernel"]["name"] == "restless_survival_index_v1"
    assert surface["state"]["channel_count"] >= 8
    assert surface["top_route"]["recommended_action"]
    assert "allocation_weight" in surface["top_route"]
    assert "restless_index" in surface["top_route"]
    assert surface["allocation_vector"]
    assert "no_revenue_without_paid_receipt" in surface["hard_guards"]
    assert "paid receipt" in surface["monetization_rule"].lower()


def test_pending_nonpaying_channel_gets_queue_penalty():
    jobs = {
        "channels": [
            {
                "channel_id": "taskbounty_agent_pr_task",
                "category": "agent_pr_task",
                "channel_score": 0.4,
                "score_components": {
                    "authorization_clarity": 0.8,
                    "payout_clarity": 0.8,
                    "proof_clarity": 0.7,
                    "settlement_speed": 0.5,
                    "agent_fit": 0.8,
                    "competition_risk": 0.4,
                    "autonomy_allowed": 0.7,
                    "platform_friction": 0.3,
                },
                "side_effect_gate": {"public_or_external_action": "allowed_after_contract_preflight"},
            }
        ]
    }
    pending = {
        "latest_by_external": [
            {
                "external_id": f"taskbounty:{idx}",
                "stage": "submitted",
                "work_url": "https://www.task-bounty.com/tasks/x",
            }
            for idx in range(5)
        ]
    }
    surface = build_delayed_channel_bandit_surface(
        job_channel_surface=jobs,
        external_value_summary=pending,
        signal_layer={},
    )
    task = next(row for row in surface["routes"] if row["channel_id"] == "taskbounty_agent_pr_task")
    assert task["observed"]["active_nonpaid"] == 5
    assert task["queue_penalty"] < 0.2
    assert task["censored_pending_mass"] >= 5
    assert task["claim_emission_allowed"] is False
    assert surface["wip_collapse"]["active"] is True
    assert task["recommended_action"] in {
        "reconcile_or_cooldown",
        "small_read_only_probe",
        "read_only_qualification",
        "wip_collapse_reconcile_only",
    }


def test_positive_hackerone_signal_can_select_passive_scope_audit():
    jobs = build_job_channel_surface(base_url="", external_value_summary={})
    signal_layer = {
        "recent_events": [
            {
                "target_id": "hackerone:cloudflare:workerd-source-scope",
                "target_url": "https://github.com/cloudflare/workerd",
                "signal_type": "high_impact",
                "magnitude": 2.5,
                "confidence": 0.9,
            },
            {
                "target_id": "hackerone:cloudflare:workerd-source-scope",
                "signal_type": "validated_repro",
                "magnitude": 1.0,
                "confidence": 0.8,
            },
        ]
    }
    surface = build_delayed_channel_bandit_surface(
        job_channel_surface=jobs,
        external_value_summary={},
        signal_layer=signal_layer,
    )
    h1 = next(row for row in surface["routes"] if row["channel_id"] == "hackerone_bug_bounty")
    assert h1["observed"]["signal_positive"] > 0
    assert h1["recommended_action"] == "passive_scope_audit_only"


def test_stale_pending_feedback_decays_channel_survival():
    jobs = {
        "channels": [
            {
                "channel_id": "algora_github_bounty",
                "category": "oss_bounty",
                "channel_score": 0.5,
                "score_components": {
                    "authorization_clarity": 0.85,
                    "payout_clarity": 0.8,
                    "proof_clarity": 0.75,
                    "settlement_speed": 0.45,
                    "agent_fit": 0.85,
                    "competition_risk": 0.35,
                    "autonomy_allowed": 0.75,
                    "platform_friction": 0.35,
                },
                "side_effect_gate": {"public_or_external_action": "allowed_after_contract_preflight"},
            }
        ]
    }
    now = datetime.now(UTC).isoformat()
    stale = (datetime.now(UTC) - timedelta(days=30)).isoformat()

    fresh_surface = build_delayed_channel_bandit_surface(
        job_channel_surface=jobs,
        external_value_summary={
            "latest_by_external": [
                {
                    "external_id": "algora:fresh",
                    "stage": "submitted",
                    "work_url": "https://algora.io/bounties/fresh",
                    "last_generated_at": now,
                }
            ]
        },
    )
    stale_surface = build_delayed_channel_bandit_surface(
        job_channel_surface=jobs,
        external_value_summary={
            "latest_by_external": [
                {
                    "external_id": "algora:stale",
                    "stage": "submitted",
                    "work_url": "https://algora.io/bounties/stale",
                    "last_generated_at": stale,
                }
            ]
        },
    )

    fresh = fresh_surface["routes"][0]
    old = stale_surface["routes"][0]
    assert old["survival_decay"] < fresh["survival_decay"]
    assert old["censored_pending_mass"] > fresh["censored_pending_mass"]
    assert old["queue_penalty"] < fresh["queue_penalty"]


def test_wip_collapse_blocks_new_external_claim_emission():
    jobs = {
        "channels": [
            {
                "channel_id": "algora_github_bounty",
                "category": "oss_bounty",
                "channel_score": 0.9,
                "score_components": {
                    "authorization_clarity": 0.95,
                    "payout_clarity": 0.95,
                    "proof_clarity": 0.9,
                    "settlement_speed": 0.8,
                    "agent_fit": 0.95,
                    "competition_risk": 0.1,
                    "autonomy_allowed": 0.9,
                    "platform_friction": 0.05,
                },
                "side_effect_gate": {"public_or_external_action": "allowed_after_contract_preflight"},
            },
            {
                "channel_id": "nomad_internal_worker_market",
                "category": "machine_native_market",
                "channel_score": 0.2,
                "score_components": {
                    "authorization_clarity": 0.9,
                    "payout_clarity": 0.5,
                    "proof_clarity": 0.9,
                    "settlement_speed": 0.3,
                    "agent_fit": 0.9,
                    "competition_risk": 0.2,
                    "autonomy_allowed": 0.9,
                    "platform_friction": 0.2,
                },
                "side_effect_gate": {"public_or_external_action": "allowed_after_contract_preflight"},
            },
        ]
    }
    old = (datetime.now(UTC) - timedelta(days=12)).isoformat()
    surface = build_delayed_channel_bandit_surface(
        job_channel_surface=jobs,
        external_value_summary={
            "latest_by_external": [
                {
                    "external_id": f"algora:pending-{idx}",
                    "stage": "submitted",
                    "work_url": f"https://algora.io/bounties/pending-{idx}",
                    "last_generated_at": old,
                }
                for idx in range(3)
            ]
        },
    )

    algora = next(row for row in surface["routes"] if row["channel_id"] == "algora_github_bounty")
    internal = next(row for row in surface["routes"] if row["channel_id"] == "nomad_internal_worker_market")
    assert surface["wip_collapse"]["active"] is True
    assert surface["wip_collapse"]["reason"] == "pending_mass_without_external_paid_receipt"
    assert algora["wip_collapse_applied"] is True
    assert algora["claim_emission_allowed"] is False
    assert algora["recommended_action"] != "execute_after_preflight"
    assert internal["wip_collapse_applied"] is False
