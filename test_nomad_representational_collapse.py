from nomad_cli import run_once
from nomad_representational_collapse import build_latent_consensus_surface, evaluate_latent_consensus


def test_collapsed_committee_switches_to_shadow_only_hetero():
    out = evaluate_latent_consensus(
        {
            "objective": "committee_patch",
            "proofs": [
                {"proof_id": "a", "proof_embedding": [1.0, 0.0, 0.0], "proof_digest": "sha256:a"},
                {"proof_id": "b", "proof_embedding": [0.999, 0.001, 0.0], "proof_digest": "sha256:b"},
                {"proof_id": "c", "proof_embedding": [0.998, 0.002, 0.0], "proof_digest": "sha256:c"},
            ],
        },
        base_url="https://nomad.example",
    )

    assert out["schema"] == "nomad.latent_consensus_decision.v1"
    assert out["collapse_detected"] is True
    assert out["collapse_score"] < 0.75
    assert out["routing_adjustment"]["topology"] == "shadow_only_hetero"
    assert out["routing_adjustment"]["settlement_pressure_penalty"] == 0.4
    assert abs(sum(item["weight"] for item in out["dalc_weights"]) - 1.0) < 0.00001


def test_dalc_weights_reward_verified_orthogonal_minority():
    out = evaluate_latent_consensus(
        {
            "objective": "proof_route",
            "proofs": [
                {"proof_id": "copy-1", "proof_embedding": [1.0, 0.0, 0.0], "proof_digest": "sha256:copy1"},
                {"proof_id": "copy-2", "proof_embedding": [0.999, 0.001, 0.0], "proof_digest": "sha256:copy2"},
                {
                    "proof_id": "minority-proof",
                    "proof_embedding": [0.0, 1.0, 0.0],
                    "proof_digest": "sha256:minority",
                    "verifier_status": "passed",
                    "utility_delta": 0.9,
                },
            ],
        }
    )
    weights = {item["record_id"]: item["weight"] for item in out["dalc_weights"]}

    assert out["collapse_detected"] is True
    assert weights["minority-proof"] > weights["copy-1"]
    assert weights["minority-proof"] > weights["copy-2"]


def test_orthogonal_embeddings_do_not_trigger_collapse():
    out = evaluate_latent_consensus(
        {
            "objective": "orthogonal_check",
            "proofs": [
                {"proof_id": "x", "proof_embedding": [1.0, 0.0, 0.0]},
                {"proof_id": "y", "proof_embedding": [0.0, 1.0, 0.0]},
                {"proof_id": "z", "proof_embedding": [0.0, 0.0, 1.0]},
            ],
        }
    )

    assert out["collapse_detected"] is False
    assert out["collapse_score"] >= 0.99
    assert out["routing_adjustment"]["topology"] == "latent_diversity_weighted"


def test_latent_consensus_surface_and_cli_are_machine_readable():
    surface = build_latent_consensus_surface(base_url="https://nomad.example")
    cli = run_once(["latent-consensus", "--base-url", "https://nomad.example", "--json"])

    assert surface["evaluate_url"] == "https://nomad.example/swarm/latent-consensus/evaluate"
    assert surface["protocol"]["vote_rule"] == "majority_vote_disabled_when_latent_collapse_detected"
    assert "do_not_store_private_chain_of_thought_text" in surface["hard_guards"]
    assert cli["schema"] == "nomad.latent_consensus_surface.v1"
