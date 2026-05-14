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
    assert surface["state"]["channel_count"] >= 8
    assert surface["top_route"]["recommended_action"]
    assert "no_revenue_without_paid_receipt" in surface["hard_guards"]
    assert "paid receipt" in surface["monetization_rule"].lower()


def test_pending_nonpaying_channel_gets_queue_penalty():
    jobs = build_job_channel_surface(base_url="", external_value_summary={})
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
    assert task["recommended_action"] in {"reconcile_or_cooldown", "small_read_only_probe", "read_only_qualification"}


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
