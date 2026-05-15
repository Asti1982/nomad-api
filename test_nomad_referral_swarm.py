from nomad_referral_swarm import build_referral_swarm_surface


def test_referral_swarm_blocks_cold_growth_and_keeps_revenue_zero():
    out = build_referral_swarm_surface(base_url="https://nomad.example")

    assert out["schema"] == "nomad.referral_swarm.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-referral-swarm.json"
    assert out["reward_model"]["primary_reward"] == "verified_cursor_usage_credit_receipt"
    assert out["reward_model"]["recognized_revenue_usd_total"] == 0.0
    assert out["revenue_guard"]["paid_receipt_required"] is True

    blocked = {arm["arm_id"]: arm for arm in out["blocked_arms"]}
    assert blocked["cold_social_broadcast"]["decision"] == "blocked"
    assert blocked["unsolicited_dm_sequence"]["decision"] == "blocked"


def test_referral_swarm_prioritizes_owned_opt_in_surfaces():
    out = build_referral_swarm_surface(base_url="https://nomad.example")
    arms = out["channel_arms"]

    assert arms[0]["arm_id"] == "owned_nomad_well_known_surface"
    assert arms[0]["allowed_without_human_approval"] is True
    assert arms[0]["referral_url"] == "https://cursor.com/referral?code=U7OPZAP4BZWH"
    assert out["active_owned_arms"][0]["arm_id"] == "owned_nomad_well_known_surface"
    assert out["human_approval_required_arms"][0]["arm_id"] == "cursor_relevant_support_answer"
    assert "block cold broadcasts" in out["machine_instruction"]
