from nomad_worker_market import build_worker_market, score_worker_offer


def test_worker_market_surface_uses_forge_pressure(tmp_path):
    market = build_worker_market(
        base_url="https://nomad.example",
        worker_fleet={"known_worker_count": 2, "active_worker_count": 0, "active_lease_count": 0},
        machine_economy={"machine_viability": {"tier": "recovering", "carrying_score": 0.32}},
        swarm_economics={"control_state": {"mode": "recover"}},
        variant_forge={
            "requested_variants": [
                {"objective": "settlement_capacity_builder"},
                {"objective": "overmint_compressor"},
            ]
        },
        ledger_path=tmp_path / "market.jsonl",
    )

    objectives = {row["objective"] for row in market["requested_worker_offers"]}
    assert market["schema"] == "nomad.worker_market.v1"
    assert market["offer_url"] == "https://nomad.example/swarm/worker-market/offers"
    assert market["utility_floor"] == 1.8
    assert {"settlement_capacity_builder", "overmint_compressor"} <= objectives
    assert market["payment_rails"]["preferred"] == "lightning_l402_quote"


def test_score_worker_offer_accepts_useful_proven_capacity(tmp_path):
    ledger = tmp_path / "worker_market.jsonl"
    receipt = score_worker_offer(
        {
            "agent_id": "worker.market.test",
            "objective": "settlement_capacity_builder",
            "capabilities": [
                "transition_worker",
                "objective_lease_execution",
                "http_json",
                "proof_digest_return",
            ],
            "availability_minutes": 90,
            "cost_msat_per_minute": 0,
            "proof_digest": "sha256:proof",
            "verifier_trace_digest": "sha256:trace",
            "settlement_ref": "settlement:1",
            "worker_report_digest": "sha256:report",
            "cashflow_signal": {"settled_transitions": 2, "settlement_ref": "settlement:1"},
            "expected": {
                "expected_proof_yield_per_minute": 3.0,
                "expected_settlement_delta": 0.3,
                "reliability_score": 0.9,
                "risk_score": 0.04,
            },
        },
        base_url="https://nomad.example",
        worker_market={"market_digest": "nomad-worker-market-test", "utility_floor": 1.8},
        ledger_path=ledger,
    )

    assert receipt["ok"] is True
    assert receipt["accepted"] is True
    assert receipt["decision"] == "admit_shadow_worker_offer"
    assert receipt["marginal_utility_per_cost"] >= receipt["utility_floor"]
    assert receipt["quote"]["settlement_mode"] == "verified_completion_after_lease"
    assert ledger.exists()


def test_score_worker_offer_blocks_secret_like_payload(tmp_path):
    receipt = score_worker_offer(
        {
            "agent_id": "bad.worker",
            "capabilities": ["transition_worker"],
            "availability_minutes": 10,
            "access_token": "ghp_secret",
        },
        ledger_path=tmp_path / "market.jsonl",
    )

    assert receipt["ok"] is False
    assert receipt["reason"] == "forbidden_secret_like_material"
