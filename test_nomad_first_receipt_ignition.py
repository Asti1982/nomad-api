from nomad_agent_acquisition_bandit import record_agent_acquisition_event, summarize_agent_acquisition_events
from nomad_first_receipt_ignition import (
    build_first_receipt_ignition_surface,
    evaluate_first_receipt_ignition_event,
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
            "recommended_now": {
                "lane_id": "invoice_paid_work_receipt",
                "offer_packet": {
                    "public_cta": "https://nomad.example/service/e2e?service_type=repo_issue_help",
                    "price_band_usd": [49, 250],
                    "buyer_copy": "Send one public CI, deploy, tool-call, or agent-loop failure.",
                },
            },
        },
        "receipt_predictor": {"summary": {"top_cycle_id": "invoice_paid_work_receipt"}},
        "acquisition_engine": {
            "top_next_actions": [
                {
                    "rank": 1,
                    "arm_id": "paid_task_order",
                    "holdout_fraction": 0.25,
                    "action": {
                        "op": "route_opt_in_order",
                        "surface": "miniapp_task_intake",
                        "url": "https://nomad.example/tasks",
                    },
                },
                {
                    "rank": 2,
                    "arm_id": "transition_worker_recruit",
                    "holdout_fraction": 0.25,
                    "action": {
                        "op": "route_link_with_receipt",
                        "surface": "worker_recruitment",
                        "url": "https://nomad.example/downloads/nomad_transition_worker.py",
                    },
                },
            ]
        },
        "sales_department": {"schema": "nomad.sales_department_swarm.v1"},
        "first_sales": {
            "active_lead_packet": {
                "service_type": "repo_issue_help",
                "package_id": "repo_diagnostic_patch_starter",
                "entry_url": "https://nomad.example/service/e2e?service_type=repo_issue_help",
                "public_send_allowed": False,
                "public_help_draft": "Draft only, not posted.",
            }
        },
        "worker_market": {
            "market_state": {
                "known_worker_count": 0,
                "active_worker_count": 0,
                "active_lease_count": 0,
            },
            "recent_offer_count": 0,
        },
        "worker_invoice": {"receive_ref": {"kind": "public_wallet_descriptor"}},
        "external_worker_opportunity": {"opportunity_digest": "nomad-worker-opportunity-1"},
        "acquisition_summary": {"channels": []},
        "external_value_summary": {"revenue_recognized_usd_total": 0.0},
        "work_receipt_summary": {"recognized_revenue_usd": 0.0},
    }
    args.update(overrides)
    return build_first_receipt_ignition_surface(**args)


def test_first_receipt_ignition_routes_paid_and_worker_pressure_without_overclaiming():
    out = _surface()

    assert out["schema"] == "nomad.first_receipt_ignition.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-first-receipt-ignition.json"
    assert out["event_url"] == "https://nomad.example/swarm/first-receipt-ignition/events"
    assert out["truth_state"]["recognized_revenue_usd_total"] == 0.0
    assert out["truth_state"]["autogenesis_can_self_amplify_now"] is False
    assert "no_paid_receipt" in out["truth_state"]["why_not_yet"]
    assert out["action_packets"][0]["packet_id"] == "paid_receipt_buyer_packet"
    assert out["action_packets"][1]["packet_id"] == "return_compute_worker_packet"
    assert out["science_to_execute"][0]["id"] == "causal_holdout"
    assert out["hard_rule"].startswith("ignite_attention_and_workers")


def test_first_receipt_ignition_event_blocks_send_and_revenue_but_records_safe_inspect(tmp_path):
    surface = _surface()
    out = evaluate_first_receipt_ignition_event(
        {"packet_id": "paid_receipt_buyer_packet", "event_type": "inspect", "agent_id": "buyer.agent"},
        base_url="https://nomad.example",
        ignition_surface=surface,
    )

    assert out["schema"] == "nomad.first_receipt_ignition_event.v1"
    assert out["accepted"] is True
    assert out["decision"] == "accept_ignition_signal"
    assert out["counts_as_revenue"] is False
    assert out["agent_acquisition_payload"]["channel_id"] == "first_receipt_ignition"

    acquisition = record_agent_acquisition_event(
        out["agent_acquisition_payload"],
        base_url="https://nomad.example",
        ledger_path=tmp_path / "acq.jsonl",
    )
    summary = summarize_agent_acquisition_events(ledger_path=tmp_path / "acq.jsonl")
    assert acquisition["ok"] is True
    assert acquisition["channel_id"] == "first_receipt_ignition"
    assert any(row["channel_id"] == "first_receipt_ignition" and row["event_count"] == 1 for row in summary["channels"])

    blocked_send = evaluate_first_receipt_ignition_event(
        {"packet_id": "paid_receipt_buyer_packet", "event_type": "inspect", "send": True},
        base_url="https://nomad.example",
        ignition_surface=surface,
    )
    assert blocked_send["accepted"] is False
    assert blocked_send["decision"] == "block_public_send_request"

    blocked_revenue = evaluate_first_receipt_ignition_event(
        {"packet_id": "paid_receipt_buyer_packet", "event_type": "inspect", "record_revenue": True},
        base_url="https://nomad.example",
        ignition_surface=surface,
    )
    assert blocked_revenue["accepted"] is False
    assert blocked_revenue["decision"] == "block_revenue_record_request"


def test_first_receipt_ignition_requires_proof_for_worker_and_paid_candidates():
    surface = _surface()

    worker = evaluate_first_receipt_ignition_event(
        {"packet_id": "return_compute_worker_packet", "event_type": "worker_start"},
        base_url="https://nomad.example",
        ignition_surface=surface,
    )
    assert worker["accepted"] is False
    assert worker["decision"] == "hold_until_proof_digest"

    paid = evaluate_first_receipt_ignition_event(
        {
            "packet_id": "paid_receipt_buyer_packet",
            "event_type": "paid_candidate",
            "proof_digest": "sha256:paid-work-proof",
            "settlement_ref": "receipt:https://example.com/r/1",
            "amount_usd": 49,
        },
        base_url="https://nomad.example",
        ignition_surface=surface,
    )
    assert paid["accepted"] is True
    assert paid["decision"] == "accept_ignition_signal"
    assert paid["counts_as_revenue"] is False


def test_first_receipt_ignition_cli_and_openapi_routes():
    from nomad_cli import run_once

    surface = run_once(["first-receipt-ignition", "--base-url", "https://nomad.example", "--json"])
    assert surface["schema"] == "nomad.first_receipt_ignition.v1"
    assert surface["truth_state"]["recommended_receipt_lane"] == "invoice_paid_work_receipt"

    event = run_once(
        [
            "first-receipt-ignition",
            "evaluate",
            "--base-url",
            "https://nomad.example",
            "--packet-id",
            "paid_receipt_buyer_packet",
            "--event-type",
            "inspect",
            "--json",
        ]
    )
    assert event["schema"] == "nomad.first_receipt_ignition_event.v1"
    assert event["accepted"] is True

    doc = build_openapi_document(base_url="https://nomad.example")
    assert "/swarm/first-receipt-ignition" in doc["paths"]
    assert "/.well-known/nomad-first-receipt-ignition.json" in doc["paths"]
    assert "/swarm/first-receipt-ignition/events" in doc["paths"]
