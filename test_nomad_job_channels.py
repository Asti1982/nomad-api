from nomad_cli import run_once
from nomad_job_channels import build_job_channel_surface, score_job_channel


def test_job_channel_surface_ranks_external_channels_with_receipt_gate():
    out = build_job_channel_surface(base_url="https://nomad.example")

    assert out["schema"] == "nomad.job_channels.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-job-channels.json"
    assert out["summary"]["external_channel_count"] >= 8
    assert out["summary"]["security_channel_count"] >= 3
    assert out["top_external_channel"]["channel_id"] == "github_oss_bounty_pr"
    assert out["channel_contract"]["no_revenue_claim_rule"] == "accepted_merged_or_thanked_is_not_paid"
    assert "never_book_revenue_without_paid_receipt" in out["machine_instruction"]
    assert out["switching_policy"]["schema"] == "nomad.channel_switching_policy.v1"
    assert out["next"][2]["url"].startswith("https://github.com/")


def test_job_channel_side_effect_gates_block_marketplace_autoposting():
    out = build_job_channel_surface(base_url="https://nomad.example")
    freelance = next(item for item in out["channels"] if item["channel_id"] == "freelance_marketplace_draft_only")

    assert freelance["side_effect_gate"]["public_or_external_action"] == "blocked_until_operator_gate"
    assert "unauthorized_marketplace_automation" in freelance["side_effect_gate"]["hard_stops"]
    assert "no_auto_apply" in freelance["autonomy_policy"]


def test_job_channel_scoring_rewards_proof_and_authorization():
    weak = score_job_channel(
        {
            "channel_id": "weak",
            "score": {
                "agent_fit": 0.8,
                "authorization_clarity": 0.3,
                "payout_clarity": 0.8,
                "proof_clarity": 0.3,
                "autonomy_allowed": 0.8,
                "settlement_speed": 0.8,
                "competition_risk": 0.2,
                "platform_friction": 0.2,
            },
        }
    )
    strong = score_job_channel(
        {
            "channel_id": "strong",
            "score": {
                "agent_fit": 0.8,
                "authorization_clarity": 0.9,
                "payout_clarity": 0.8,
                "proof_clarity": 0.9,
                "autonomy_allowed": 0.8,
                "settlement_speed": 0.8,
                "competition_risk": 0.2,
                "platform_friction": 0.2,
            },
        }
    )

    assert strong["channel_score"] > weak["channel_score"]


def test_cli_job_channels_returns_schema():
    out = run_once(["job-channels", "--base-url", "https://nomad.example", "--json"])

    assert out["schema"] == "nomad.job_channels.v1"
    assert out["read_url"] == "https://nomad.example/swarm/job-channels"
    assert out["top_external_channel"]["side_effect_gate"]["must_verify_before_work"]


def test_channel_switching_freezes_nonpaying_github_arrivals():
    external_summary = {
        "schema": "nomad.external_value_summary.v1",
        "distinct_externals": 13,
        "revenue_recognized_usd_total": 0.0,
        "latest_by_external": [
            {
                "external_id": f"gh_pr:owner/repo#{idx}",
                "stage": "submitted",
                "work_url": f"https://github.com/owner/repo/pull/{idx}",
                "last_generated_at": "2026-05-12T00:00:00+00:00",
                "revenue_recognized_usd": 0.0,
            }
            for idx in range(13)
        ],
    }

    out = build_job_channel_surface(
        base_url="https://nomad.example",
        external_value_summary=external_summary,
    )
    policy = out["switching_policy"]
    github = next(item for item in policy["allocation"] if item["channel_id"] == "github_oss_bounty_pr")

    assert policy["triggered"] is True
    assert policy["arrival_policy"] == "suppress_new_public_claims_on_nonpaying_channel"
    assert github["recommended_action"] == "freeze_new_public_claims_reconcile_only"
    assert github["arrival_weight"] == 0.0
    assert policy["next_channel_probe"]["channel_id"] != "github_oss_bounty_pr"
    assert policy["next_external_probe"]["channel_id"] != "github_oss_bounty_pr"
