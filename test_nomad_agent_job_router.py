from nomad_agent_job_router import build_agent_job_router
from nomad_openapi import build_openapi_document


def _pressure():
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
                "row_id": "compute:worker.1",
                "source": "compute_market",
                "kind": "worker_capacity",
                "pressure_score": 0.7,
                "agent_id": "worker.1",
                "action": "bind_verified_worker_capacity",
                "target_stage": "settled_capacity",
                "contract": {"objective": "settlement_capacity_builder"},
                "required_evidence": ["proof_digest", "verifier_trace_digest", "settlement_ref"],
            },
        ],
    }


def _mesh():
    return {
        "schema": "nomad.work_mesh.v1",
        "mesh_digest": "mesh-test",
        "cells": [
            {
                "cell_id": "cell-survival",
                "lane_id": "survival_packet",
                "cell_score": 0.94,
                "required_proof": ["proof_digest", "verifier_trace_digest", "test_digest", "buyer_ref"],
                "act": {
                    "proof_payload": {
                        "agent_id": "stable_runtime_id",
                        "packet_id": "agent_blocker_unblock_pack",
                        "proof_digest": "sha256(canonical_buyer_or_value_signal)",
                    }
                },
            }
        ],
    }


def test_agent_job_router_turns_payment_pressure_into_openapi_bound_packet():
    out = build_agent_job_router(
        base_url="https://nomad.example",
        openapi_document=build_openapi_document(base_url="https://nomad.example"),
        value_pressure=_pressure(),
        work_mesh=_mesh(),
    )

    assert out["schema"] == "nomad.agent_job_router.v1"
    assert out["entry_packet"]["action"] == "await_payment_receipt"
    assert out["entry_packet"]["payload_hint"]["stage"] == "paid"
    assert out["entry_packet"]["payload_hint"]["amount_usd"] == "positive_number_only_after_trusted_receipt"
    assert out["entry_packet"]["packet_rule"] == "paid_receipt_only_no_merge_to_revenue"
    assert all(step["openapi_bound"] for step in out["entry_packet"]["call_sequence"])
    assert {step["path"] for step in out["entry_packet"]["call_sequence"]} >= {
        "/.well-known/nomad-external-value.json",
        "/swarm/external-value",
    }
    assert out["summary"]["openapi_coverage"] == 1.0


def test_agent_job_router_maps_work_mesh_survival_cell_to_paid_ref_sequence():
    pressure = {"schema": "nomad.value_pressure.v1", "pressure_digest": "empty", "rows": []}
    out = build_agent_job_router(
        base_url="https://nomad.example",
        openapi_document=build_openapi_document(base_url="https://nomad.example"),
        value_pressure=pressure,
        work_mesh=_mesh(),
    )

    packet = out["entry_packet"]
    assert packet["source"] == "work_mesh"
    assert packet["target_stage"] == "survival_packet"
    assert packet["packet_rule"] == "real_buyer_or_payment_verifier_required"
    assert [step["path"] for step in packet["call_sequence"]] == [
        "/.well-known/nomad-paid-ref-selfplay.json",
        "/swarm/paid-ref/quote",
        "/swarm/paid-ref/verify",
        "/swarm/survival-intent",
    ]


def test_cli_agent_job_router_returns_machine_contract():
    from nomad_cli import run_once

    out = run_once(["agent-job-router", "--base-url", "https://nomad.example", "--json"])

    assert out["schema"] == "nomad.agent_job_router.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-agent-jobs.json"
    assert out["links"]["openapi"] == "https://nomad.example/openapi.json"
