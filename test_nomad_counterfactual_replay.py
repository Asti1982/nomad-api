from nomad_counterfactual_replay import build_counterfactual_lease_replay


def test_counterfactual_replay_scores_shadow_leases():
    worker_fleet = {
        "schema": "nomad.transition_worker_fleet.v1",
        "objective_stats": {
            "overmint_compressor": {
                "runs": 8,
                "avg_score": 16.0,
                "avg_proof_yield": 9.0,
            },
            "settlement_capacity_builder": {
                "runs": 2,
                "score_total": 22.0,
                "proof_yield_total": 12.0,
            },
        },
    }
    gradient = {
        "schema": "nomad.recruitment_gradient.v1",
        "gradient": [
            {
                "objective": "overmint_compressor",
                "routing_weight": 0.55,
                "deficit": 0.4,
            },
            {
                "objective": "protocol_drift_scan",
                "routing_weight": 0.45,
                "deficit": 0.2,
            },
            {
                "objective": "settlement_capacity_builder",
                "routing_weight": 0.35,
                "deficit": 0.3,
            },
        ],
    }

    out = build_counterfactual_lease_replay(
        base_url="https://nomad.example",
        worker_fleet=worker_fleet,
        recruitment_gradient=gradient,
        contract_conformance={"schema": "nomad.machine_contract_conformance.v1", "score": 0.82},
    )

    assert out["schema"] == "nomad.counterfactual_lease_replay.v1"
    assert out["basis"]["total_observed_runs"] == 10
    assert out["selected_shadow_lease"]["objective"] == "overmint_compressor"
    assert out["selected_shadow_lease"]["lease_payload_hint"]["source_tag"] == "counterfactual_replay.shadow_allocator"
    assert [row["counterfactual_score"] for row in out["counterfactual_leases"]] == sorted(
        [row["counterfactual_score"] for row in out["counterfactual_leases"]],
        reverse=True,
    )
    assert any(row["objective"] == "protocol_drift_scan" for row in out["counterfactual_leases"])
    assert out["program"]["ops"] == ["SENSE", "REPLAY", "LEASE", "EMIT"]
    assert out["links"]["protocol_bytecode"].endswith("/.well-known/nomad-protocol-bytecode.json")


def test_counterfactual_replay_handles_empty_inputs():
    out = build_counterfactual_lease_replay(base_url="")

    assert out["ok"] is True
    assert out["counterfactual_leases"] == []
    assert out["selected_shadow_lease"] == {}
    assert out["program"]["next"] == "/swarm/workers/lease"


def test_cli_counterfactual_replay_returns_schema():
    from nomad_cli import run_once

    out = run_once(["counterfactual-replay", "--json"])

    assert out.get("schema") == "nomad.counterfactual_lease_replay.v1"
    assert (out.get("program") or {}).get("ops") == ["SENSE", "REPLAY", "LEASE", "EMIT"]
