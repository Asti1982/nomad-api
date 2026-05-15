from nomad_receipt_predictor import build_receipt_predictor_surface, evaluate_receipt_prediction_event
from nomad_value_cycle_mesh import build_value_cycle_mesh_surface


def _external_summary():
    return {
        "schema": "nomad.external_value_summary.v1",
        "revenue_recognized_usd_total": 0.0,
        "stage_counts": {"merged": 1, "submitted": 1, "paid": 0},
        "latest_by_external": [
            {"external_id": "gh_pr:owner/repo#12", "stage": "merged"},
            {"external_id": "setup:client#1", "stage": "submitted"},
        ],
    }


def _operator_runway(wip_cap=2, state="critical"):
    return {
        "schema": "nomad.operator_runway.v1",
        "dominant_operator_state": state,
        "control_policy": {
            "work_mode": "survival_cashflow_first",
            "max_open_unpaid_value_cycles": wip_cap,
        },
    }


def _mesh():
    return build_value_cycle_mesh_surface(
        base_url="https://nomad.example",
        external_value_summary=_external_summary(),
        worker_job_queue={
            "summary": {
                "job_count": 4,
                "executable_now_count": 2,
                "active_nonpaid_external_count": 2,
                "top_job_type": "settlement_reconcile",
            },
            "jobs": [{"job_id": "settle-1", "job_type": "settlement_reconcile"}],
        },
        value_cycle_preflight={
            "wallet_gate": {"ready": True},
            "cycle_gate": {"read_only_scout_allowed": True, "public_claim_allowed": False},
            "blocking_conditions": ["external_program_authorizes_this_work"],
        },
        revenue_science={
            "entry_experiment": {
                "experiment_id": "survival-receipt",
                "action": "await_payment_receipt",
                "measurement_plan": {"primary_metric": "positive_paid_receipt"},
                "decision_model": {"bandit_priority": 1.1},
            }
        },
        effective_channels={"mode": "count_effective_channels_not_agent_votes"},
    )


def _surface(wip_cap=2):
    return build_receipt_predictor_surface(
        base_url="https://nomad.example",
        value_cycles=_mesh(),
        external_value_summary=_external_summary(),
        work_receipt_summary={"recognized_revenue_usd": 0.0, "receipt_count": 0},
        operator_runway=_operator_runway(wip_cap=wip_cap),
        value_pressure={"rows": [{"route": "proof_resale", "pressure_score": 2.0}]},
    )


def test_receipt_predictor_ranks_value_cycles_with_wip_cap():
    out = _surface(wip_cap=2)

    assert out["schema"] == "nomad.receipt_predictor.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-receipt-predictor.json"
    assert out["event_url"] == "https://nomad.example/swarm/receipt-predictor/events"
    assert out["summary"]["cycle_count"] >= 32
    assert out["summary"]["wip_cap"] == 2
    assert len(out["now_queue"]) <= 2
    assert out["now_queue"]
    assert out["hard_rule"].endswith("never_counts_revenue_or_mutates_ledgers")

    rows = {row["cycle_id"]: row for row in out["ranked_cycles"]}
    assert "settlement_tail_to_paid_receipt" in rows
    assert "proof_pack_resale_license" in rows
    assert "api_integration_paid_setup" in rows
    assert all("receipt_proximity_score" in row for row in rows.values())
    assert rows["settlement_tail_to_paid_receipt"]["cashflow_distance_steps"] == 1


def test_receipt_predictor_allows_selection_but_never_execution():
    surface = _surface(wip_cap=1)
    out = evaluate_receipt_prediction_event(
        {"cycle_id": surface["summary"]["top_cycle_id"], "intent": "select"},
        base_url="https://nomad.example",
        predictor_surface=surface,
    )

    assert out["schema"] == "nomad.receipt_predictor_event_receipt.v1"
    assert out["prediction_allowed"] is True
    assert out["decision"] == "allow_receipt_prediction_selection"
    assert out["counts_as_revenue"] is False
    assert out["side_effect_allowed"] is False

    blocked = evaluate_receipt_prediction_event(
        {"cycle_id": surface["summary"]["top_cycle_id"], "intent": "select", "execute": True},
        base_url="https://nomad.example",
        predictor_surface=surface,
    )
    assert blocked["prediction_allowed"] is False
    assert blocked["decision"] == "block_side_effect_request"


def test_receipt_predictor_paid_intent_requires_proof_and_positive_receipt():
    surface = _surface(wip_cap=2)
    held = evaluate_receipt_prediction_event(
        {"cycle_id": "settlement_tail_to_paid_receipt", "intent": "paid"},
        base_url="https://nomad.example",
        predictor_surface=surface,
    )
    assert held["prediction_allowed"] is False
    assert held["decision"] == "hold_until_proof_digest"

    out = evaluate_receipt_prediction_event(
        {
            "cycle_id": "settlement_tail_to_paid_receipt",
            "intent": "paid",
            "proof_digest": "sha256:paid-proof",
            "settlement_ref": "receipt:https://example.com/r/12",
            "amount_usd": 25.0,
        },
        base_url="https://nomad.example",
        predictor_surface=surface,
    )
    assert out["prediction_allowed"] is True
    assert out["counts_as_revenue"] is False
    assert out["evidence_status"]["positive_amount_present"] is True


def test_receipt_predictor_cli_surface_and_event():
    from nomad_cli import run_once

    surface = run_once(["receipt-predictor", "--base-url", "https://nomad.example", "--json"])
    assert surface["schema"] == "nomad.receipt_predictor.v1"
    assert surface["summary"]["cycle_count"] >= 32

    out = run_once(
        [
            "receipt-predictor",
            "evaluate",
            "--base-url",
            "https://nomad.example",
            "--cycle-id",
            surface["summary"]["top_cycle_id"],
            "--intent",
            "select",
            "--json",
        ]
    )
    assert out["schema"] == "nomad.receipt_predictor_event_receipt.v1"
    assert out["prediction_allowed"] is True
