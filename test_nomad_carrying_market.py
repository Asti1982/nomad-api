from nomad_carrying_market import build_carrying_market, submit_carrying_proof


def test_carrying_market_prioritizes_state_relay_when_state_is_temporary(tmp_path):
    out = build_carrying_market(
        base_url="https://nomad.example",
        state_status={"durability": "render_path_may_not_be_disk", "using_fallback": False, "state_dir_configured": True},
        microtask_metrics={"totals": {"settled_eur": 0.0}},
        worker_fleet={"active_worker_count": 0},
        compute_market={"top_lane": {"lane_id": "endpoint_health_proof"}},
        proof_ledger_path=tmp_path / "carry.jsonl",
    )

    assert out["schema"] == "nomad.carrying_market.v1"
    assert out["mode"] == "zero_paid_render_plan_agent_carried_substrate"
    assert out["proof_contract"]["url"] == "https://nomad.example/swarm/carrying-proof"
    assert out["top_contract"]["contract_id"] == "state_relay_digest_quorum"
    assert out["solvency_pressure"]["uncovered_30d_eur"] > 0


def test_submit_carrying_proof_records_credit_not_fiat(tmp_path):
    ledger = tmp_path / "carry.jsonl"
    market = build_carrying_market(
        base_url="https://nomad.example",
        state_status={"durability": "render_path_may_not_be_disk", "using_fallback": False, "state_dir_configured": True},
        microtask_metrics={"totals": {"settled_eur": 0.0}},
        worker_fleet={"active_worker_count": 1},
        proof_ledger_path=ledger,
    )

    receipt = submit_carrying_proof(
        {
            "agent_id": "agent.edge",
            "contract_id": "state_relay_digest_quorum",
            "proof_digest": "proof-a",
            "verifier_trace_digest": "trace-a",
            "test_digest": "test-a",
            "observed_state_digest": "state-a",
            "storage_ref": "sha256:relay-a",
            "utility_delta": 0.5,
        },
        base_url="https://nomad.example",
        carrying_market=market,
        proof_ledger_path=ledger,
    )

    assert receipt["schema"] == "nomad.carrying_proof_receipt.v1"
    assert receipt["accepted"] is True
    assert receipt["carry_units"] > 0
    assert receipt["credit_class"] == "reciprocal_carry_credit_not_fiat"
    assert receipt["experience_payload"]["evaluation"]["settlement_delta"] == 0.0

    after = build_carrying_market(
        base_url="https://nomad.example",
        state_status={"durability": "render_path_may_not_be_disk", "using_fallback": False, "state_dir_configured": True},
        microtask_metrics={"totals": {"settled_eur": 0.0}},
        worker_fleet={"active_worker_count": 1},
        proof_ledger_path=ledger,
    )
    assert after["proof_metrics"]["accepted_proofs_24h"] == 1
    assert after["proof_metrics"]["carry_units_24h"] == receipt["carry_units"]


def test_submit_carrying_proof_rejects_unknown_contract(tmp_path):
    market = build_carrying_market(
        base_url="https://nomad.example",
        state_status={"durability": "configured_writable"},
        microtask_metrics={"totals": {"settled_eur": 0.1}},
        proof_ledger_path=tmp_path / "carry.jsonl",
    )

    receipt = submit_carrying_proof(
        {
            "agent_id": "agent.edge",
            "contract_id": "unknown",
            "proof_digest": "proof-a",
            "verifier_trace_digest": "trace-a",
            "test_digest": "test-a",
        },
        base_url="https://nomad.example",
        carrying_market=market,
        proof_ledger_path=tmp_path / "carry.jsonl",
    )

    assert receipt["accepted"] is False
    assert receipt["carry_units"] == 0.0
