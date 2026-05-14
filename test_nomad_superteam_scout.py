from __future__ import annotations

from datetime import UTC, datetime

from nomad_superteam_scout import _normalize_base, build_superteam_scout


NOW = datetime(2026, 5, 13, 12, 0, tzinfo=UTC)


def _listing(**overrides):
    listing = {
        "id": "listing-1",
        "rewardAmount": 500,
        "deadline": "2026-06-15T18:29:59.000Z",
        "type": "bounty",
        "title": "Build a deterministic agent evaluator",
        "token": "USDC",
        "winnersAnnouncedAt": None,
        "slug": "build-deterministic-agent-evaluator",
        "isWinnersAnnounced": False,
        "status": "OPEN",
        "agentAccess": "AGENT_ALLOWED",
        "compensationType": "fixed",
        "_count": {"Comments": 2, "Submission": 8},
        "sponsor": {"name": "Superteam", "slug": "superteam", "isVerified": True},
    }
    listing.update(overrides)
    return listing


def test_superteam_base_normalization():
    assert _normalize_base("superteam.fun/") == "https://superteam.fun"
    assert _normalize_base("https://superteam.fun/") == "https://superteam.fun"


def test_future_agent_listing_is_candidate_but_submission_still_blocked_until_artifact():
    result = build_superteam_scout(
        api_key="sk_test",
        claim_code="CLAIM",
        listings=[_listing()],
        now=NOW,
    )

    listing = result["listings"][0]
    assert result["summary"]["active_candidate_count"] == 1
    assert listing["gate_state"] == "candidate_artifact_gate_unverified"
    assert listing["executable_work_allowed"] is False
    assert "submit_without_artifact" in listing["blocked_actions"]
    assert "original_artifact_link_ready" in listing["unlock_requirements"]


def test_expired_listing_is_watch_only_even_when_open():
    result = build_superteam_scout(
        api_key="sk_test",
        claim_code="CLAIM",
        listings=[_listing(deadline="2026-02-15T18:29:59.000Z")],
        now=NOW,
    )

    listing = result["listings"][0]
    assert result["summary"]["expired_or_announced_count"] == 1
    assert listing["gate_state"] == "deadline_passed"
    assert listing["allowed_actions"] == ["read_only_watch"]


def test_missing_claim_code_blocks_submission():
    result = build_superteam_scout(
        api_key="sk_test",
        claim_code="",
        listings=[_listing()],
        now=NOW,
    )

    assert result["claim_code_present"] is False
    assert result["listings"][0]["gate_state"] == "claim_code_missing"


def test_crowded_competition_stays_watch_only_without_exceptional_artifact():
    result = build_superteam_scout(
        api_key="sk_test",
        claim_code="CLAIM",
        listings=[_listing(_count={"Comments": 10, "Submission": 120})],
        now=NOW,
    )

    listing = result["listings"][0]
    assert result["summary"]["crowded_count"] == 1
    assert listing["gate_state"] == "crowded_competition_watch_only"
    assert "low_originality_submission" in listing["blocked_actions"]
