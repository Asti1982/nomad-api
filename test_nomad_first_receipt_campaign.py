from nomad_first_receipt_campaign import (
    build_first_receipt_campaign_surface,
    evaluate_first_receipt_campaign_event,
)
from nomad_openapi import build_openapi_document


def _surface(**overrides):
    args = {
        "base_url": "https://nomad.example",
        "bottleneck_resolver": {
            "current_bottleneck": {
                "status": "current_bottleneck_external_receipt_absent",
                "paid_confirmed": False,
                "recognized_revenue_usd": 0.0,
            },
            "recommended_now": {"lane_id": "invoice_paid_work_receipt"},
        },
        "first_receipt_ignition": {
            "truth_state": {
                "recognized_revenue_usd_total": 0.0,
                "worker_count": 2,
                "active_worker_count": 2,
                "adapter_event_count": 0,
                "paid_bottleneck_resolved": False,
                "self_funding_loop_closed": False,
                "autogenesis_can_self_amplify_now": False,
            }
        },
        "acquisition_summary": {"channels": []},
        "lead_profile": {
            "service_type": "agent_infra_prime",
            "seed_queries": ['repo:langchain-ai/langgraph "tool" is:issue is:open'],
            "queries": ['"AI agent" "CI" is:issue is:open'],
        },
        "worker_market": {
            "market_state": {
                "known_worker_count": 2,
                "active_worker_count": 2,
                "active_lease_count": 0,
            }
        },
        "adapter_surface": {"schema": "nomad.universal_adapter.v1"},
    }
    args.update(overrides)
    return build_first_receipt_campaign_surface(**args)


def test_first_receipt_campaign_compiles_10_proof_gated_slots_without_overclaiming():
    out = _surface()

    assert out["schema"] == "nomad.first_receipt_campaign.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-first-receipt-campaign.json"
    assert out["event_url"] == "https://nomad.example/swarm/first-receipt-campaign/events"
    assert out["truth_state"]["paid_bottleneck_resolved"] is False
    assert out["truth_state"]["self_funding_loop_closed"] is False
    assert out["truth_state"]["autogenesis_can_self_amplify_now"] is False
    assert out["truth_state"]["why_not_yet"] == ["no_paid_receipt"]
    assert len(out["campaign_slots"]) == 10
    assert out["campaign_slots"][0]["action"] == "run_read_only_lead_scout"
    assert out["campaign_slots"][-1]["slot_id"] == "receipt-write-gate"
    assert out["science_protocols"][0]["id"] == "causal_holdout"
    assert "no_revenue_counted_without_positive_receipt" in out["hard_rules"]


def test_first_receipt_campaign_event_blocks_send_and_revenue_but_allows_safe_lead_signal():
    surface = _surface()

    lead = evaluate_first_receipt_campaign_event(
        {
            "agent_id": "nomad.test",
            "event_type": "lead_observed",
            "lead_url": "https://github.com/org/repo/issues/1",
        },
        base_url="https://nomad.example",
        campaign_surface=surface,
    )
    assert lead["accepted"] is True
    assert lead["decision"] == "accept_campaign_signal"
    assert lead["counts_as_revenue"] is False
    assert lead["side_effect_allowed"] is False
    assert lead["agent_acquisition_payload"]["channel_id"] == "first_receipt_campaign"

    blocked_send = evaluate_first_receipt_campaign_event(
        {
            "event_type": "lead_observed",
            "lead_url": "https://github.com/org/repo/issues/1",
            "send": True,
        },
        base_url="https://nomad.example",
        campaign_surface=surface,
    )
    assert blocked_send["accepted"] is False
    assert blocked_send["decision"] == "block_public_send_request"

    blocked_revenue = evaluate_first_receipt_campaign_event(
        {
            "event_type": "paid_candidate",
            "lead_url": "https://github.com/org/repo/issues/1",
            "proof_digest": "sha256:proof",
            "settlement_ref": "receipt:https://example/r/1",
            "amount_usd": 49,
            "record_revenue": True,
        },
        base_url="https://nomad.example",
        campaign_surface=surface,
    )
    assert blocked_revenue["accepted"] is False
    assert blocked_revenue["decision"] == "block_revenue_record_request"


def test_first_receipt_campaign_requires_proof_for_first_fix_and_paid_candidate():
    surface = _surface()

    missing_proof = evaluate_first_receipt_campaign_event(
        {
            "event_type": "first_fix_prepared",
            "lead_url": "https://github.com/org/repo/issues/1",
        },
        base_url="https://nomad.example",
        campaign_surface=surface,
    )
    assert missing_proof["accepted"] is False
    assert missing_proof["decision"] == "hold_until_proof_digest"

    paid = evaluate_first_receipt_campaign_event(
        {
            "event_type": "paid_candidate",
            "lead_url": "https://github.com/org/repo/issues/1",
            "proof_digest": "sha256:paid-proof",
            "settlement_ref": "receipt:https://example/r/1",
            "amount_usd": 49,
        },
        base_url="https://nomad.example",
        campaign_surface=surface,
    )
    assert paid["accepted"] is True
    assert paid["decision"] == "accept_campaign_signal"
    assert paid["counts_as_revenue"] is False


def test_first_receipt_campaign_cli_and_openapi_routes():
    from nomad_cli import run_once

    surface = run_once(["first-receipt-campaign", "--base-url", "https://nomad.example", "--json"])
    assert surface["schema"] == "nomad.first_receipt_campaign.v1"
    assert surface["recommended_now"]["action"] == "run_first_receipt_campaign"

    event = run_once(
        [
            "first-receipt-campaign",
            "evaluate",
            "--base-url",
            "https://nomad.example",
            "--event-type",
            "lead_observed",
            "--lead-url",
            "https://github.com/org/repo/issues/1",
            "--json",
        ]
    )
    assert event["schema"] == "nomad.first_receipt_campaign_event.v1"
    assert event["accepted"] is True

    doc = build_openapi_document(base_url="https://nomad.example")
    assert "/swarm/first-receipt-campaign" in doc["paths"]
    assert "/.well-known/nomad-first-receipt-campaign.json" in doc["paths"]
    assert "/swarm/first-receipt-campaign/events" in doc["paths"]
