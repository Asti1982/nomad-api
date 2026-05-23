from nomad_bottleneck_resolver import build_bottleneck_resolver_surface, evaluate_bottleneck_resolution_event
from nomad_openapi import build_openapi_document


def _predictor():
    return {
        "schema": "nomad.receipt_predictor.v1",
        "ranked_cycles": [
            {
                "cycle_id": "invoice_paid_work_receipt",
                "lane": "worker_invoice",
                "rank": 1,
                "queue": "now",
                "receipt_proximity_score": 1.76,
            },
            {
                "cycle_id": "api_integration_paid_setup",
                "lane": "integration_setup",
                "rank": 2,
                "queue": "next",
                "receipt_proximity_score": 1.31,
            },
            {
                "cycle_id": "private_security_report_reward",
                "lane": "security_bounty",
                "rank": 22,
                "queue": "hold",
                "receipt_proximity_score": 0.61,
            },
        ],
    }


def _surface(**overrides):
    args = {
        "base_url": "https://nomad.example",
        "receipt_predictor": _predictor(),
        "external_value_summary": {
            "schema": "nomad.external_value_summary.v1",
            "revenue_recognized_usd_total": 0.0,
            "stage_counts": {"paid": 0, "submitted": 0},
            "latest_by_external": [],
        },
        "work_receipt_summary": {"recognized_revenue_usd": 0.0, "receipt_count": 0},
        "work_exchange_summary": {
            "return_receipt_count": 0,
            "settled_return_work_credits_total": 0.0,
            "active_obligation_count": 0,
        },
        "acquisition_summary": {
            "channels": [
                {
                    "channel_id": "universal_adapter",
                    "event_count": 0,
                    "reward_total": 0.0,
                    "event_types": {},
                    "proof_gated_event_count": 0,
                }
            ]
        },
    }
    args.update(overrides)
    return build_bottleneck_resolver_surface(**args)


def test_bottleneck_resolver_keeps_unproven_status_and_prioritizes_paid_receipt():
    out = _surface()

    assert out["schema"] == "nomad.bottleneck_resolver.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-bottleneck-resolver.json"
    assert out["event_url"] == "https://nomad.example/swarm/bottleneck-resolver/events"
    assert out["current_bottleneck"]["status"] == "current_bottleneck_external_receipt_absent"
    assert out["current_bottleneck"]["counts_as_solved"] is False
    assert out["current_bottleneck"]["metric_label"] == "paid/return receipt absent"
    assert out["recommended_now"]["lane_id"] == "invoice_paid_work_receipt"
    assert out["recommended_now"]["offer_packet"]["price_band_usd"] == [49, 250]
    assert out["hackerone_position"] == "secondary_hold_until_authorized_accepted_or_paid"
    assert out["hard_rule"].startswith("no_bottleneck_cleared_claim")

    lanes = {row["lane_id"]: row for row in out["lanes"]}
    assert lanes["hackerone_authorized_bounty_cycle"]["queue"] == "hold"
    assert "bottleneck_cleared" in lanes["hackerone_authorized_bounty_cycle"]["not_yet_proof_of"]


def test_bottleneck_resolver_clears_only_with_real_paid_or_return_compute_receipt():
    paid = _surface(work_receipt_summary={"recognized_revenue_usd": 75.0, "receipt_count": 1})
    assert paid["current_bottleneck"]["counts_as_solved"] is True
    assert paid["current_bottleneck"]["status"] == "cleared_by_positive_paid_receipt"
    assert paid["clearance_gate"]["currently_satisfied"] == ["positive_paid_receipt"]

    returned = _surface(
        work_exchange_summary={
            "return_receipt_count": 1,
            "settled_return_work_credits_total": 3.5,
            "active_obligation_count": 0,
        }
    )
    assert returned["current_bottleneck"]["counts_as_solved"] is True
    assert returned["current_bottleneck"]["status"] == "cleared_by_return_compute_receipt"
    assert returned["clearance_gate"]["currently_satisfied"] == ["verified_return_compute_receipt"]


def test_bottleneck_resolver_event_blocks_side_effects_and_requires_receipts():
    surface = _surface()

    selected = evaluate_bottleneck_resolution_event(
        {"lane_id": "invoice_paid_work_receipt", "intent": "select"},
        base_url="https://nomad.example",
        resolver_surface=surface,
    )
    assert selected["schema"] == "nomad.bottleneck_resolution_event.v1"
    assert selected["resolution_packet_allowed"] is True
    assert selected["counts_as_revenue"] is False
    assert selected["side_effect_allowed"] is False

    held = evaluate_bottleneck_resolution_event(
        {"lane_id": "invoice_paid_work_receipt", "intent": "paid"},
        base_url="https://nomad.example",
        resolver_surface=surface,
    )
    assert held["resolution_packet_allowed"] is False
    assert held["decision"] == "hold_until_proof_digest"

    blocked = evaluate_bottleneck_resolution_event(
        {"lane_id": "invoice_paid_work_receipt", "intent": "paid", "record": True},
        base_url="https://nomad.example",
        resolver_surface=surface,
    )
    assert blocked["resolution_packet_allowed"] is False
    assert blocked["decision"] == "block_side_effect_request"

    proofed = evaluate_bottleneck_resolution_event(
        {
            "lane_id": "invoice_paid_work_receipt",
            "intent": "paid",
            "proof_digest": "sha256:paid-rescue-proof",
            "settlement_ref": "receipt:https://example.com/r/1",
            "amount_usd": 49,
        },
        base_url="https://nomad.example",
        resolver_surface=surface,
    )
    assert proofed["resolution_packet_allowed"] is True
    assert proofed["decision"] == "allow_resolution_packet"
    assert proofed["counts_as_bottleneck_cleared"] is False


def test_bottleneck_resolver_cli_and_openapi_routes():
    from nomad_cli import run_once

    out = run_once(["bottleneck-resolver", "--base-url", "https://nomad.example", "--json"])
    assert out["schema"] == "nomad.bottleneck_resolver.v1"
    assert out["current_bottleneck"]["counts_as_solved"] is False
    assert out["recommended_now"]["lane_id"] == "invoice_paid_work_receipt"

    event = run_once(
        [
            "bottleneck-resolver",
            "evaluate",
            "--base-url",
            "https://nomad.example",
            "--lane-id",
            "hackerone_authorized_bounty_cycle",
            "--intent",
            "select",
            "--json",
        ]
    )
    assert event["decision"] == "hold_until_authorized_program_scope"

    doc = build_openapi_document(base_url="https://nomad.example")
    assert "/swarm/bottleneck-resolver" in doc["paths"]
    assert "/.well-known/nomad-bottleneck-resolver.json" in doc["paths"]
    assert "/swarm/bottleneck-resolver/events" in doc["paths"]
