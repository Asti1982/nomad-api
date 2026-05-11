from nomad_bounty_hunter import (
    build_bounty_hunter_surface,
    extract_reward,
    github_issue_to_opportunity,
    hard_public_action_gate,
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
    assert proof_work["hard_gate"]["public_action"] == "scout_only"
    assert proof_work["score_components"]["hard_gate_weight"] < 1
    assert social["exclusion_reason"]
    assert social["hard_gate"]["public_action"] == "no_go"


def test_hard_gate_allows_public_action_only_after_unique_proof():
    review = score_bounty_opportunity(
        {
            "title": "[BOUNTY] Review PRs for security bugs",
            "body": "Reward: 20 RTC for concrete PR reviews.",
            "repo": "owner/repo",
            "source_url": "https://github.com/owner/repo/issues/73",
            "work_mode": "code_review_comment",
            "estimated_effort_hours": 1,
            "authorization_confidence": 0.92,
            "payment_confidence": 0.78,
            "proof_clarity": 0.90,
            "agent_fit": 0.88,
            "side_effect_safety": 0.90,
            "anti_spam_weight": 1.0,
        }
    )
    proved = score_bounty_opportunity({**review, "has_unique_repro": True})

    assert review["hard_gate"]["public_action"] == "scout_only"
    assert review["hard_gate"]["requires_unique_repro"] is True
    assert proved["hard_gate"]["public_action"] == "go_public_after_repro"
    assert proved["bounty_score"] > review["bounty_score"]


def test_hard_gate_no_go_blocks_weak_payment_or_spam_signals():
    gate = hard_public_action_gate(
        {
            "eligible": True,
            "work_mode": "failing_test_or_audit_pr",
            "expected_reward_usd": 0.0,
            "estimated_effort_hours": 1,
            "authorization_confidence": 0.95,
            "payment_confidence": 0.20,
            "proof_clarity": 0.90,
            "side_effect_safety": 0.90,
            "agent_fit": 0.90,
            "anti_spam_weight": 1.0,
        }
    )

    assert gate["public_action"] == "no_go"
    assert "payment_confidence_below_0.58" in gate["blockers"]


def test_hard_gate_blocks_crowded_claim_surfaces_without_new_proof():
    crowded = score_bounty_opportunity(
        {
            "title": "[BOUNTY] Integration reference implementation",
            "body": "Reward: $20. Submit code and tests.",
            "repo": "owner/repo",
            "source_url": "https://github.com/owner/repo/issues/2890",
            "work_mode": "implementation_pr",
            "estimated_effort_hours": 2,
            "authorization_confidence": 0.90,
            "payment_confidence": 0.80,
            "proof_clarity": 0.86,
            "agent_fit": 0.82,
            "side_effect_safety": 0.86,
            "anti_spam_weight": 1.0,
            "comments": 24,
        }
    )
    proved = score_bounty_opportunity({**crowded, "has_unique_repro": True})

    assert crowded["hard_gate"]["public_action"] == "no_go"
    assert "crowded_claim_surface_requires_new_unique_proof" in crowded["hard_gate"]["blockers"]
    assert proved["hard_gate"]["public_action"] == "go_public_after_repro"


def test_hard_gate_caps_repeated_finding_patterns_even_with_proof():
    capped = score_bounty_opportunity(
        {
            "title": "[BOUNTY] Review PRs for BCOS policy bugs",
            "body": "Reward: 20 RTC for concrete PR reviews.",
            "repo": "owner/repo",
            "source_url": "https://github.com/owner/repo/issues/73",
            "work_mode": "code_review_comment",
            "estimated_effort_hours": 1,
            "authorization_confidence": 0.92,
            "payment_confidence": 0.78,
            "proof_clarity": 0.90,
            "agent_fit": 0.88,
            "side_effect_safety": 0.90,
            "anti_spam_weight": 1.0,
            "has_unique_repro": True,
            "finding_pattern": "missing_spdx_header",
            "similar_claim_count_24h": 3,
        }
    )

    assert capped["hard_gate"]["public_action"] == "scout_only"
    assert capped["hard_gate"]["scout_reason"] == "similar_claim_pattern_cap_reached_keep_read_only_until_higher_impact_signal"


def test_hard_gate_rejects_findings_already_reported_by_others():
    duplicate = score_bounty_opportunity(
        {
            "title": "[BOUNTY] Review PRs for security bugs",
            "body": "Reward: 20 RTC for concrete PR reviews.",
            "repo": "owner/repo",
            "source_url": "https://github.com/owner/repo/issues/73",
            "work_mode": "code_review_comment",
            "estimated_effort_hours": 1,
            "authorization_confidence": 0.92,
            "payment_confidence": 0.78,
            "proof_clarity": 0.90,
            "agent_fit": 0.88,
            "side_effect_safety": 0.90,
            "anti_spam_weight": 1.0,
            "has_unique_repro": True,
            "already_found_by_others": True,
        }
    )

    assert duplicate["hard_gate"]["public_action"] == "no_go"
    assert "already_found_by_others" in duplicate["hard_gate"]["blockers"]


def test_bounty_score_prioritizes_security_over_policy_compliance_pattern():
    security = score_bounty_opportunity(
        {
            "title": "[BOUNTY] Webhook 500 after signed malformed payload",
            "body": "Reward: 20 RTC. Security/reliability route validation bug.",
            "repo": "owner/repo",
            "source_url": "https://github.com/owner/repo/issues/73",
            "work_mode": "code_review_comment",
            "estimated_effort_hours": 1,
            "has_unique_repro": True,
        }
    )
    policy = score_bounty_opportunity(
        {
            "title": "[BOUNTY] Missing SPDX header in new test file",
            "body": "Reward: 20 RTC. BCOS policy compliance review.",
            "repo": "owner/repo",
            "source_url": "https://github.com/owner/repo/issues/73",
            "work_mode": "code_review_comment",
            "estimated_effort_hours": 1,
            "has_unique_repro": True,
        }
    )

    assert security["score_components"]["impact_weight"] > policy["score_components"]["impact_weight"]
    assert security["bounty_score"] > policy["bounty_score"]


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
    assert out["hard_selection"]["schema"] == "nomad.bounty_hard_selection.v1"
    assert out["summary"]["scout_only_count"] >= 1
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


def test_bounty_classifier_prefers_red_team_over_generic_review_language():
    issue = {
        "number": 2819,
        "url": "https://github.com/example/repo/issues/2819",
        "title": "[BOUNTY] Red Team UTXO Implementation",
        "body": "Review the implementation and submit reproducible security bugs with failing tests.",
        "labels": [{"name": "bounty"}],
    }

    out = github_issue_to_opportunity(issue, repo="example/repo")

    assert out["work_mode"] == "failing_test_or_audit_pr"
    assert out["eligible"] is True


def test_bounty_classifier_excludes_reputation_and_wallet_policy_lanes():
    issue = {
        "number": 6885,
        "url": "https://github.com/example/repo/issues/6885",
        "title": "[POLICY] One canonical RTC wallet per contributor identity - declare by Friday",
        "body": "Contributor ladder and level up policy for community reputation.",
        "labels": [{"name": "bounty"}],
    }

    out = github_issue_to_opportunity(issue, repo="example/repo")

    assert out["eligible"] is False
    assert out["work_mode"] == "reputation_or_identity_policy"
    assert out["exclusion_reason"] == "community_reputation_or_wallet_policy_not_proof_work"


def test_bounty_classifier_excludes_capital_market_and_referral_lanes():
    lp = github_issue_to_opportunity(
        {
            "number": 130,
            "url": "https://github.com/example/repo/issues/130",
            "title": "[BOUNTY] wRTC Liquidity Provider Incentive",
            "body": "500 RTC/month for Raydium LP with wallet balance proof.",
            "labels": [{"name": "bounty"}],
        },
        repo="example/repo",
    )
    referral = github_issue_to_opportunity(
        {
            "number": 167,
            "url": "https://github.com/example/repo/issues/167",
            "title": "[BOUNTY] Bring a Friend to Mine",
            "body": "10 RTC per referral. Invite a friend and prove they joined.",
            "labels": [{"name": "bounty"}],
        },
        repo="example/repo",
    )

    assert lp["eligible"] is False
    assert lp["work_mode"] == "capital_market_claim"
    assert lp["impact_class"] == "non_agent_runtime_claim"
    assert hard_public_action_gate(lp)["public_action"] == "no_go"
    assert referral["eligible"] is False
    assert referral["work_mode"] == "referral_or_network_growth_claim"
    assert hard_public_action_gate(referral)["public_action"] == "no_go"


def test_bounty_classifier_excludes_content_media_lanes():
    media = github_issue_to_opportunity(
        {
            "number": 309,
            "url": "https://github.com/example/repo/issues/309",
            "title": "[BOUNTY] Create a RustChain Tutorial Video",
            "body": "10 RTC for a tutorial video with video proof.",
            "labels": [{"name": "bounty"}],
        },
        repo="example/repo",
    )

    assert media["eligible"] is False
    assert media["work_mode"] == "content_or_media_claim"
    assert media["impact_class"] == "non_agent_runtime_claim"
    assert hard_public_action_gate(media)["public_action"] == "no_go"


def test_cli_bounty_hunter_returns_schema():
    out = run_once(["bounty-hunter", "--base-url", "https://nomad.example", "--json"])

    assert out["schema"] == "nomad.bounty_hunter.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-bounty-hunter.json"
    assert out["top_candidate"]["claim_next"]["first_action"]
