from nomad_ad_cycle_mesh import build_ad_cycle_mesh_surface, evaluate_ad_cycle_event


def _effective(quota_shift_count=1, cap_count=0):
    return {
        "schema": "nomad.effective_channel_quota.v1",
        "mode": "count_effective_channels_not_agent_votes",
        "event_url": "https://nomad.example/swarm/effective-channels/events",
        "thresholds": {"min_effective_channel_ratio": 0.72},
        "recent_summary": {
            "quota_shift_count": quota_shift_count,
            "homogeneous_cap_count": cap_count,
        },
    }


def _value_cycles():
    return {
        "schema": "nomad.value_cycle_mesh.v1",
        "summary": {
            "cycle_count": 16,
            "top_cycle_id": "paid_ref_survival_packet",
            "recognized_revenue_usd_total": 0.0,
        },
    }


def _preflight():
    return {
        "schema": "nomad.value_cycle_preflight.v1",
        "wallet_gate": {"ready": True},
        "cycle_gate": {
            "read_only_scout_allowed": True,
            "public_claim_allowed": False,
            "submit_after_proof_allowed": False,
        },
        "blocking_conditions": ["external_program_authorizes_this_work"],
    }


def test_ad_cycle_mesh_exposes_many_shadow_only_cycles():
    out = build_ad_cycle_mesh_surface(
        base_url="https://nomad.example",
        effective_channels=_effective(),
        value_cycles=_value_cycles(),
        value_cycle_preflight=_preflight(),
    )

    assert out["schema"] == "nomad.ad_cycle_mesh.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-ad-cycles.json"
    assert out["event_url"] == "https://nomad.example/swarm/ad-cycles/events"
    assert out["summary"]["cycle_count"] >= 12
    assert out["summary"]["send_allowed_count"] == 0
    assert out["entry_cycle"]["send_policy"]["autonomous_send_allowed"] is False
    ids = {cycle["cycle_id"] for cycle in out["cycles"]}
    assert "agent_card_discovery_draft" in ids
    assert "github_issue_value_reply_draft" in ids
    assert "anti_consensus_minor_offer_draft" in ids


def test_ad_cycle_event_allows_shadow_queue_after_quota_receipt():
    mesh = build_ad_cycle_mesh_surface(
        base_url="https://nomad.example",
        effective_channels=_effective(),
        value_cycles=_value_cycles(),
        value_cycle_preflight=_preflight(),
    )
    out = evaluate_ad_cycle_event(
        {
            "cycle_id": "agent_card_discovery_draft",
            "stage": "queue",
            "target_url": "https://agent.example/.well-known/agent-card.json",
            "proof_digest": "sha256:target-proof",
            "effective_channel_receipt": {"quota_shift_allowed": True},
        },
        base_url="https://nomad.example",
        ad_mesh=mesh,
    )

    assert out["schema"] == "nomad.ad_cycle_event_receipt.v1"
    assert out["ad_cycle_allowed"] is True
    assert out["campaign_payload_candidate"]["send"] is False
    assert out["campaign_payload_candidate"]["targets"][0]["endpoint_url"] == "https://agent.example/.well-known/agent-card.json"
    assert out["counts_as_revenue"] is False


def test_ad_cycle_event_blocks_send_request_even_with_quota():
    mesh = build_ad_cycle_mesh_surface(
        base_url="https://nomad.example",
        effective_channels=_effective(),
        value_cycles=_value_cycles(),
        value_cycle_preflight=_preflight(),
    )
    out = evaluate_ad_cycle_event(
        {
            "cycle_id": "peer_witness_contract_draft",
            "stage": "send_request",
            "proof_digest": "sha256:target-proof",
            "effective_channel_receipt": {"quota_shift_allowed": True},
            "send": True,
        },
        base_url="https://nomad.example",
        ad_mesh=mesh,
    )

    assert out["ad_cycle_allowed"] is False
    assert out["decision"] == "block_send_request_shadow_only"
    assert out["campaign_payload_candidate"]["send"] is False
    assert out["hard_rule"] == "ad_cycle_event_never_sends_and_never_counts_as_revenue"


def test_cli_ad_cycles_returns_surface_and_event_gate():
    from nomad_cli import run_once

    surface = run_once(["ad-cycles", "--base-url", "https://nomad.example", "--json"])
    event = run_once(
        [
            "ad-cycles",
            "evaluate",
            "--base-url",
            "https://nomad.example",
            "--cycle-id",
            "agent_card_discovery_draft",
            "--stage",
            "draft",
            "--target-url",
            "https://agent.example/.well-known/agent-card.json",
            "--proof-digest",
            "sha256:target-proof",
            "--json",
        ]
    )

    assert surface["schema"] == "nomad.ad_cycle_mesh.v1"
    assert surface["summary"]["cycle_count"] >= 12
    assert event["schema"] == "nomad.ad_cycle_event_receipt.v1"
    assert event["campaign_payload_candidate"]["send"] is False
