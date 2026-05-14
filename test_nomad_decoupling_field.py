from nomad_decoupling_field import build_decoupling_field_surface, evaluate_decoupling_merge


def _sample_surface(tmp_path):
    return build_decoupling_field_surface(
        base_url="https://nomad.example",
        shadow_lane={
            "surface_digest": "nomad-shadow-test",
            "candidate_seeds": [
                {"objective": "settlement_capacity_builder"},
                {"objective": "protocol_drift_scan"},
            ],
        },
        channel_bandit={
            "bandit_digest": "nomad-bandit-test",
            "top_route": {"channel_id": "immunefi_web3_bounty"},
        },
        signal_layer={"machine_attention_field": {"top_dimensions": [{"dimension": "proof_pressure_engine"}]}},
        opaque_surface={"surface_digest": "nomad-opaque-test"},
        ledger_path=tmp_path / "decouple.jsonl",
    )


def _merge_payload(surface, divergence=0.48):
    cells = surface["context_cells"][:2]
    return {
        "agent_id": "agent.decouple",
        "divergence_score": divergence,
        "cells": [
            {
                "cell_id": cells[0]["cell_id"],
                "objective": cells[0]["objective"],
                "candidate_digest": "sha256:candidate-a",
                "proof_digest": "sha256:proof-a",
                "context_mask_digest": cells[0]["context_mask_digest"],
                "model_family": "family-a",
            },
            {
                "cell_id": cells[1]["cell_id"],
                "objective": cells[1]["objective"],
                "candidate_digest": "sha256:candidate-b",
                "proof_digest": "sha256:proof-b",
                "context_mask_digest": cells[1]["context_mask_digest"],
                "model_family": "family-b",
            },
        ],
    }


def test_decoupling_field_exposes_context_isolation_contract(tmp_path):
    surface = _sample_surface(tmp_path)

    assert surface["schema"] == "nomad.decoupling_field.v1"
    assert surface["mode"] == "structural_decoupling_before_shadow_weight"
    assert surface["merge_url"] == "https://nomad.example/swarm/decoupling-field/merge"
    assert "MASK_CONTEXT" in surface["program"]["ops"]
    assert "MERGE_GATE" in surface["program"]["ops"]
    assert "no_shared_scratchpad_before_merge_gate" in surface["hard_guards"]
    assert len(surface["context_cells"]) >= 2
    assert surface["context_cells"][0]["context_mask_digest"].startswith("sha256:")


def test_decoupling_merge_requires_divergent_independent_digests(tmp_path):
    ledger = tmp_path / "decouple.jsonl"
    surface = _sample_surface(tmp_path)

    admitted = evaluate_decoupling_merge(
        _merge_payload(surface),
        base_url="https://nomad.example",
        decoupling_field=surface,
        ledger_path=ledger,
    )
    collapsed = evaluate_decoupling_merge(
        _merge_payload(surface, divergence=0.1),
        base_url="https://nomad.example",
        decoupling_field=surface,
        ledger_path=ledger,
    )

    assert admitted["schema"] == "nomad.decoupling_merge_receipt.v1"
    assert admitted["merge_allowed"] is True
    assert admitted["shadow_lane_payload"]["candidate_type"] == "decoupled_merge_candidate"
    assert admitted["shadow_lane_payload"]["local_tests"][0]["passed"] is True
    assert collapsed["merge_allowed"] is False
    assert "divergence_below_gate" in collapsed["reason_codes"]
    assert ledger.exists()
    assert "merge_digest" in ledger.read_text(encoding="utf-8")


def test_decoupling_merge_blocks_mask_collapse(tmp_path):
    surface = _sample_surface(tmp_path)
    payload = _merge_payload(surface)
    payload["cells"][1]["context_mask_digest"] = payload["cells"][0]["context_mask_digest"]

    receipt = evaluate_decoupling_merge(payload, decoupling_field=surface, ledger_path=tmp_path / "decouple.jsonl")

    assert receipt["merge_allowed"] is False
    assert "context_masks_not_independent" in receipt["reason_codes"]
