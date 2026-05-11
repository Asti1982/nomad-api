from nomad_survival_market import build_survival_market, submit_survival_intent


def test_survival_market_exposes_priced_packets_and_gap(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_MONTHLY_SURVIVAL_TARGET_EUR", "7")

    out = build_survival_market(
        base_url="https://nomad.example",
        machine_product_surface={"product_digest": "product-a"},
        carrying_market={"top_contract": {"contract_id": "state_relay_digest_quorum"}},
        microtask_metrics={"totals": {"settled_eur": 0.0}},
        worker_fleet={"active_worker_count": 1},
        intent_ledger_path=tmp_path / "survival.jsonl",
    )

    assert out["schema"] == "nomad.survival_market.v1"
    assert out["intent_contract"]["url"] == "https://nomad.example/swarm/survival-intent"
    assert out["top_packet"]["packet_id"] == "agent_blocker_unblock_pack"
    assert out["survival_pressure"]["survival_gap_30d_eur"] == 7.0
    assert "payment_verifier_digest" in out["intent_contract"]["optional"]
    assert "payment_verifier_digest" in out["intent_contract"]["revenue_rule"]


def test_survival_intent_separates_unpaid_signal_from_revenue(tmp_path):
    ledger = tmp_path / "survival.jsonl"
    market = build_survival_market(
        base_url="https://nomad.example",
        carrying_market={"top_contract": {"contract_id": "state_relay_digest_quorum"}},
        microtask_metrics={"totals": {"settled_eur": 0.0}},
        intent_ledger_path=ledger,
    )

    unpaid = submit_survival_intent(
        {
            "agent_id": "agent.edge",
            "packet_id": "agent_blocker_unblock_pack",
            "proof_digest": "proof-a",
            "verifier_trace_digest": "trace-a",
            "test_digest": "test-a",
            "buyer_ref": "buyer-a",
        },
        base_url="https://nomad.example",
        survival_market=market,
        intent_ledger_path=ledger,
    )

    assert unpaid["schema"] == "nomad.survival_intent_receipt.v1"
    assert unpaid["accepted"] is True
    assert unpaid["counts_as_revenue"] is False
    assert unpaid["settlement_eur"] == 0.0

    paid = submit_survival_intent(
        {
            "agent_id": "agent.edge",
            "packet_id": "agent_blocker_unblock_pack",
            "proof_digest": "proof-b",
            "verifier_trace_digest": "trace-b",
            "test_digest": "test-b",
            "buyer_ref": "buyer-b",
            "paid_ref": "ln-invoice-or-task-paid-b",
            "payment_verifier_digest": "nomad-payver-b",
            "amount_eur": 9.0,
        },
        base_url="https://nomad.example",
        survival_market=market,
        intent_ledger_path=ledger,
    )

    assert paid["accepted"] is True
    assert paid["counts_as_revenue"] is True
    assert paid["settlement_eur"] == 9.0
    assert paid["experience_payload"]["evaluation"]["settlement_delta"] == 9.0

    after = build_survival_market(
        base_url="https://nomad.example",
        carrying_market={"top_contract": {"contract_id": "state_relay_digest_quorum"}},
        microtask_metrics={"totals": {"settled_eur": 0.0}},
        intent_ledger_path=ledger,
    )
    assert after["intent_metrics"]["accepted_intents_24h"] == 2
    assert after["intent_metrics"]["paid_intents_24h"] == 1
    assert after["intent_metrics"]["paid_eur_24h"] == 9.0
    assert after["survival_pressure"]["survival_gap_30d_eur"] == 0.0


def test_survival_intent_rejects_unknown_packet(tmp_path):
    market = build_survival_market(
        base_url="https://nomad.example",
        intent_ledger_path=tmp_path / "survival.jsonl",
    )

    receipt = submit_survival_intent(
        {
            "agent_id": "agent.edge",
            "packet_id": "unknown",
            "proof_digest": "proof-a",
            "verifier_trace_digest": "trace-a",
            "test_digest": "test-a",
        },
        base_url="https://nomad.example",
        survival_market=market,
        intent_ledger_path=tmp_path / "survival.jsonl",
    )

    assert receipt["accepted"] is False
    assert receipt["counts_as_revenue"] is False
