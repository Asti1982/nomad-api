from nomad_rescue_packet_lattice import (
    append_rescue_packet_candidate,
    build_rescue_packet_lattice_surface,
    score_rescue_packet_candidate,
    summarize_rescue_packet_candidates,
)


def _candidate():
    return {
        "source_url": "https://github.com/crewAIInc/crewAI/issues/5802",
        "framework": "crewai",
        "problem_type": "idempotent_side_effect_retry",
        "diagnosis": "Tool retry can duplicate payments, emails, or trades.",
        "repro_outline": "Failing test for restart, concurrent worker collision, and stale pending claim expiry.",
        "fix_scope": "Bounded durable pre-execution claim verifier.",
        "side_effect_scope": "local_shadow_lane_only",
        "price_tier_usd": 99,
        "proof_digest": "sha256:5775bd9f0fdd65feef5fef8332357617cce8aec20d3d068a5d7a23e57c57950c",
    }


def test_score_rescue_packet_candidate_promotes_high_value_repro():
    score = score_rescue_packet_candidate(_candidate())

    assert score["decision"] == "promote"
    assert score["proof_yield_delta"] > 0.38
    assert score["autopoietic_index_delta"] > 0.34
    assert score["receipt_proximity"] >= 0.35
    assert score["spam_risk"] <= 0.48


def test_append_candidate_is_receipt_honest_and_summarized(tmp_path):
    ledger = tmp_path / "lattice.jsonl"
    receipt = append_rescue_packet_candidate(_candidate(), base_url="https://nomad.example", ledger_path=ledger)
    summary = summarize_rescue_packet_candidates(ledger_path=ledger)

    assert receipt["schema"] == "nomad.rescue_packet_candidate_receipt.v1"
    assert receipt["promotion_allowed"] is True
    assert receipt["counts_as_revenue"] is False
    assert receipt["revenue_recognized_usd"] == 0.0
    assert summary["promotion_candidate_count"] == 1
    assert summary["top_candidate"]["candidate_id"] == receipt["candidate_id"]


def test_lattice_surface_exposes_post_candidate_contract(tmp_path):
    ledger = tmp_path / "lattice.jsonl"
    append_rescue_packet_candidate(_candidate(), base_url="https://nomad.example", ledger_path=ledger)
    summary = summarize_rescue_packet_candidates(ledger_path=ledger)
    surface = build_rescue_packet_lattice_surface(base_url="https://nomad.example", summary=summary)

    assert surface["schema"] == "nomad.rescue_packet_lattice.v1"
    assert surface["post_candidate_url"] == "https://nomad.example/swarm/rescue-packet-candidates"
    assert surface["promotion_thresholds"]["proof_yield_delta_gt"] == 0.38
    assert "no_public_post_without_human_go" in surface["hard_guards"]
