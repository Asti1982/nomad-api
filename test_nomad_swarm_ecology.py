from nomad_swarm_ecology import build_swarm_ecology, submit_ecology_tick


def test_swarm_ecology_surface_exposes_local_tick_contract(tmp_path):
    out = build_swarm_ecology(
        base_url="https://nomad.example",
        worker_fleet={"known_worker_count": 2, "active_worker_count": 1, "active_lease_count": 1},
        machine_economy={"machine_viability": {"tier": "recovering", "carrying_score": 0.4}},
        worker_market={"requested_worker_offers": [{"objective": "settlement_capacity_builder"}]},
        variant_forge={"requested_variants": [{"objective": "overmint_compressor"}]},
        ledger_path=tmp_path / "ecology.jsonl",
    )

    assert out["schema"] == "nomad.swarm_ecology.v1"
    assert out["tick_url"] == "https://nomad.example/swarm/ecology/tick"
    assert out["local_view_contract"]["storage"] == "private_signal_is_digest_only_raw_value_not_retained"
    assert out["selection_rules"]["extinguish_when"]
    assert out["market_pressure"]["target_worker_offers"][0]["objective"] == "settlement_capacity_builder"


def test_submit_ecology_tick_reproduces_high_payoff_and_hashes_private_signal(tmp_path):
    ledger = tmp_path / "ecology.jsonl"
    receipt = submit_ecology_tick(
        {
            "agent_id": "worker.ecology.test",
            "objective": "settlement_capacity_builder",
            "local_view": {"cell": "c1", "lane": "l1"},
            "neighbor_digest": "nomad-cfreplay-test",
            "private_signal": "do-not-store-this-raw-signal",
            "proof_digest": "sha256:proof",
            "verifier_trace_digest": "sha256:trace",
            "settlement_ref": "settlement:1",
            "worker_report_digest": "sha256:report",
            "proof_yield_per_minute": 12.0,
            "utility_delta": 2.0,
            "settlement_delta": 0.5,
            "cost_units": 0.1,
            "risk_score": 0.02,
        },
        base_url="https://nomad.example",
        ecology={"ecology_digest": "nomad-ecology-test"},
        ledger_path=ledger,
    )

    assert receipt["ok"] is True
    assert receipt["accepted"] is True
    assert receipt["decision"] == "reproduce_route"
    assert receipt["private_signal_digest"]
    assert "do-not-store-this-raw-signal" not in ledger.read_text(encoding="utf-8")


def test_submit_ecology_tick_marks_negative_payoff_as_extinction(tmp_path):
    receipt = submit_ecology_tick(
        {
            "agent_id": "worker.ecology.weak",
            "objective": "protocol_drift_scan",
            "cost_units": 2.0,
            "risk_score": 0.8,
        },
        ledger_path=tmp_path / "ecology.jsonl",
    )

    assert receipt["ok"] is True
    assert receipt["accepted"] is False
    assert receipt["decision"] == "extinction_pressure"


def test_submit_ecology_tick_blocks_secret_like_payload(tmp_path):
    receipt = submit_ecology_tick(
        {
            "agent_id": "bad.ecology",
            "objective": "settlement_capacity_builder",
            "api_key": "sk-test",
        },
        ledger_path=tmp_path / "ecology.jsonl",
    )

    assert receipt["ok"] is False
    assert receipt["reason"] == "forbidden_secret_like_material"
