from nomad_resolution_ladder import build_resolution_ladder_surface, evaluate_resolution_ladder_event
from nomad_openapi import build_openapi_document


def _payload(**overrides):
    body = {
        "agent_id": "codex.proposer",
        "task_contract": {
            "task_id": "task-resolution-1",
            "objective": "repair_endpoint_with_public_receipt",
            "ttl_sec": 600,
            "rollback_ref": "noop:retract-weight",
        },
        "lease": {"lease_id": "lease-1", "worker_id": "worker.transition.1"},
        "transition_worker": {"worker_id": "worker.transition.1", "runtime": "codex-local"},
        "artifact": {
            "artifact_digest": "sha256:" + "a" * 64,
            "work_url": "https://example.test/work/task-resolution-1",
            "side_effect_scope": "resolution_receipt_only",
        },
        "independent_verification": {
            "verifier_id": "nomad.verifier.1",
            "verification_digest": "sha256:" + "b" * 64,
            "accepted": True,
            "decision": "verified",
        },
        "receipt": {
            "receipt_ref": "public:receipt:1",
            "proof_digest": "sha256:" + "c" * 64,
            "side_effect_scope": "resolution_receipt_only",
        },
        "metrics": {
            "baseline_score": 0.25,
            "candidate_score": 0.85,
            "settlement_delta": 0.2,
            "risk_score": 0.05,
            "latency_cost": 0.1,
        },
        "ttl_sec": 600,
        "rollback_ref": "noop:retract-weight",
        "side_effect_scope": "resolution_receipt_only",
    }
    body.update(overrides)
    return body


def test_resolution_ladder_surface_declares_hard_receipt_chain():
    surface = build_resolution_ladder_surface(base_url="https://nomad.example")

    assert surface["schema"] == "nomad.proof_of_resolution_ladder.v1"
    assert surface["chain"][:4] == ["task_contract", "lease", "transition_worker", "artifact"]
    assert surface["request_schema"]["runtime_weight_gate"] == "paid_receipt_and_independent_verification_and_positive_delta"
    assert surface["claim_boundary"]["beyond_human_claim_allowed"] is False
    assert surface["links"]["post"].endswith("/swarm/resolution-ladder/events")


def test_resolution_ladder_holds_public_receipt_in_shadow_until_paid(tmp_path):
    ledger = tmp_path / "resolution.jsonl"

    receipt = evaluate_resolution_ladder_event(_payload(), base_url="https://nomad.example", ledger_path=ledger)

    assert receipt["schema"] == "nomad.proof_of_resolution_receipt.v1"
    assert receipt["lifecycle_state"] == "weighted"
    assert receipt["decision"] == "shadow_weight_until_paid_receipt"
    assert receipt["shadow_weight_allowed"] is True
    assert receipt["runtime_weight_allowed"] is False
    assert receipt["runtime_weight_delta"] == 0.0
    assert receipt["persisted"] is True

    surface = build_resolution_ladder_surface(base_url="https://nomad.example", ledger_path=ledger)
    assert surface["summary"]["shadow_weighted_count"] == 1
    assert surface["summary"]["runtime_weighted_count"] == 0


def test_resolution_ladder_commits_runtime_weight_only_with_paid_receipt(tmp_path):
    ledger = tmp_path / "resolution.jsonl"
    body = _payload(
        receipt={
            "receipt_ref": "public:receipt:paid",
            "paid_receipt_ref": "stripe:test:paid-1",
            "settlement_ref": "settlement:test:1",
            "currency": "EUR",
            "amount": 7.5,
            "proof_digest": "sha256:" + "d" * 64,
            "side_effect_scope": "resolution_receipt_only",
        }
    )

    receipt = evaluate_resolution_ladder_event(body, base_url="https://nomad.example", ledger_path=ledger)

    assert receipt["accepted"] is True
    assert receipt["lifecycle_state"] == "committed"
    assert receipt["decision"] == "commit_runtime_weight"
    assert receipt["runtime_weight_allowed"] is True
    assert receipt["runtime_weight_delta"] > 0


def test_resolution_ladder_blocks_self_verification_and_duplicate_proofs(tmp_path):
    ledger = tmp_path / "resolution.jsonl"
    first = evaluate_resolution_ladder_event(_payload(), ledger_path=ledger)
    assert first["shadow_weight_allowed"] is True

    duplicate = evaluate_resolution_ladder_event(_payload(), ledger_path=ledger)
    assert duplicate["stage_checks"]["unique_proof_digest"] is False
    assert duplicate["shadow_weight_allowed"] is False
    assert duplicate["decision"] == "noop_until_full_resolution_chain"

    self_verified = _payload(
        receipt={"proof_digest": "sha256:" + "e" * 64, "receipt_ref": "public:receipt:2"},
        independent_verification={
            "verifier_id": "worker.transition.1",
            "verification_digest": "sha256:" + "f" * 64,
            "accepted": True,
        },
    )
    blocked = evaluate_resolution_ladder_event(self_verified, ledger_path=ledger)
    assert blocked["stage_checks"]["independent_verification"] is False
    assert blocked["shadow_weight_allowed"] is False


def test_resolution_ladder_is_exposed_in_openapi():
    doc = build_openapi_document(base_url="https://nomad.example")

    assert "/.well-known/nomad-resolution-ladder.json" in doc["paths"]
    assert "/swarm/resolution-ladder/events" in doc["paths"]
