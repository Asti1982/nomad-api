from nomad_agent_job_router import build_agent_job_router
from nomad_openapi import build_openapi_document
from nomad_revenue_science import build_revenue_science_surface


def _value_pressure():
    return {
        "schema": "nomad.value_pressure.v1",
        "pressure_digest": "pressure-test",
        "rows": [
            {
                "row_id": "external:gh_pr:Scottcjn/Rustchain#4542:await_payment_receipt",
                "source": "external_value_reconcile",
                "kind": "external_followup",
                "pressure_score": 1.84,
                "external_id": "gh_pr:Scottcjn/Rustchain#4542",
                "work_url": "https://github.com/Scottcjn/Rustchain/pull/4542",
                "action": "await_payment_receipt",
                "target_stage": "paid",
                "required_evidence": [
                    "trusted_owner_member_or_collaborator_payment_receipt",
                    "positive_amount_usd",
                    "public_or_private_receipt_digest",
                ],
            },
            {
                "row_id": "bounty:rustchain_utxo_static_red_team:scout_only",
                "source": "bounty_hunter",
                "kind": "proof_work",
                "pressure_score": 0.61,
                "opportunity_id": "rustchain_utxo_static_red_team",
                "source_url": "https://github.com/Scottcjn/rustchain-bounties/issues/2819",
                "action": "scout_only",
                "target_stage": "submitted",
                "required_evidence": ["public_terms_url", "local_repro_or_patch_digest", "verifier_trace_digest"],
            },
        ],
    }


def _router():
    return build_agent_job_router(
        base_url="https://nomad.example",
        openapi_document=build_openapi_document(base_url="https://nomad.example"),
        value_pressure=_value_pressure(),
        work_mesh={"cells": []},
    )


def test_revenue_science_prioritizes_paid_receipt_without_counting_merge_as_revenue():
    out = build_revenue_science_surface(
        base_url="https://nomad.example",
        value_pressure=_value_pressure(),
        agent_job_router=_router(),
        external_value_summary={"revenue_recognized_usd_total": 16.88, "distinct_externals": 1},
        nonhuman_science={
            "scientific_grounding": {
                "average_nonhuman_distance_score": 0.82,
                "distance_axes": ["persona_independence", "proof_or_digest_basis"],
            }
        },
    )

    top = out["entry_experiment"]
    assert out["schema"] == "nomad.revenue_science.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-revenue-science.json"
    assert out["summary"]["top_action"] == "await_payment_receipt"
    assert top["measurement_plan"]["primary_metric"] == "paid_stage_receipt_acceptance_with_positive_amount_usd"
    assert top["intervention"]["mode"] == "read_only_until_trusted_receipt_then_external_value_paid_write"
    assert top["revenue_guard"]["recognized_only_when"] == "external_value_stage_paid_with_positive_amount_or_verified_microtask_settlement"
    assert any(item["id"] == "merge_without_paid" for item in out["negative_controls"])
    assert top["job_packet"]["openapi_coverage"] == 1.0


def test_revenue_science_is_deterministic_for_same_pressure_rows():
    out1 = build_revenue_science_surface(
        base_url="",
        value_pressure=_value_pressure(),
        agent_job_router=_router(),
    )
    out2 = build_revenue_science_surface(
        base_url="",
        value_pressure=_value_pressure(),
        agent_job_router=_router(),
    )

    ids1 = [item["experiment_id"] for item in out1["experiments"]]
    ids2 = [item["experiment_id"] for item in out2["experiments"]]
    assert ids1 == ids2
    assert out1["entry_experiment"]["decision_model"]["bandit_priority"] == out2["entry_experiment"]["decision_model"]["bandit_priority"]


def test_cli_revenue_science_returns_machine_surface():
    from nomad_cli import run_once

    out = run_once(["revenue-science", "--base-url", "https://nomad.example", "--json"])

    assert out["schema"] == "nomad.revenue_science.v1"
    assert out["read_url"] == "https://nomad.example/swarm/revenue-science"
    assert "negative_controls" in out
