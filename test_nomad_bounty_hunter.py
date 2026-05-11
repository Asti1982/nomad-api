from nomad_bounty_hunter import (
    build_bounty_hunter_surface,
    extract_reward,
    github_issue_to_opportunity,
    score_bounty_opportunity,
)
from nomad_cli import run_once


def test_extract_reward_understands_usd_and_rtc_ranges():
    usd = extract_reward("Bounty pays $100 when merged.")
    rtc = extract_reward("Reward: 25-200 RTC for bugs.")

    assert usd["currency"] == "USD"
    assert usd["floor_usd"] == 100
    assert rtc["currency"] == "RTC"
    assert rtc["floor_usd"] == 2.5
    assert rtc["ceiling_usd"] == 20.0


def test_bounty_score_rewards_authorized_proof_work_over_social_promos():
    proof_work = score_bounty_opportunity(
        {
            "title": "[BOUNTY] Security audit for parser",
            "body": "Reward: 100 RTC. Submit a PR with a failing test and proof.",
            "repo": "owner/repo",
            "source_url": "https://github.com/owner/repo/issues/1",
            "estimated_effort_hours": 3,
        }
    )
    social = score_bounty_opportunity(
        {
            "title": "[BOUNTY] Star the repo and comment",
            "body": "Reward: 430 RTC. Star and share on social media.",
            "repo": "owner/repo",
            "source_url": "https://github.com/owner/repo/issues/2",
            "estimated_effort_hours": 0.1,
        }
    )

    assert proof_work["eligible"] is True
    assert social["eligible"] is False
    assert proof_work["bounty_score"] > social["bounty_score"]
    assert social["exclusion_reason"]


def test_bounty_hunter_surface_exposes_claim_contract_and_excludes_promos():
    out = build_bounty_hunter_surface(
        base_url="https://nomad.example",
        discoveries=[
            {
                "title": "[BOUNTY] Share launch on Twitter",
                "body": "Reward: 3 RTC. Share the link and provide screenshot proof.",
                "repo": "x/y",
                "url": "https://github.com/x/y/issues/9",
            }
        ],
    )

    assert out["schema"] == "nomad.bounty_hunter.v1"
    assert out["read_url"] == "https://nomad.example/swarm/bounty-hunter"
    assert out["claim_contract"]["payout_ref_hint"] == "NOMAD_BOUNTY_PAYOUT_REF"
    assert out["top_candidate"]["eligible"] is True
    assert any(item["work_mode"] == "promotional_engagement" for item in out["excluded_lanes"])
    assert "do_not_count_reward_until_external_program_verifies_payment" in out["machine_instruction"]


def test_github_issue_normalization_turns_bounty_issue_into_opportunity():
    issue = {
        "number": 42,
        "url": "https://github.com/example/repo/issues/42",
        "title": "[BOUNTY] Fix security bug",
        "body": "Reward: $100. Submit PR with tests.",
        "labels": [{"name": "bounty"}],
    }

    out = github_issue_to_opportunity(issue, repo="example/repo")

    assert out["source_url"].endswith("/42")
    assert out["currency"] == "USD"
    assert out["work_mode"] == "failing_test_or_audit_pr"
    assert out["eligible"] is True


def test_cli_bounty_hunter_returns_schema():
    out = run_once(["bounty-hunter", "--base-url", "https://nomad.example", "--json"])

    assert out["schema"] == "nomad.bounty_hunter.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-bounty-hunter.json"
    assert out["top_candidate"]["claim_next"]["first_action"]
