from nomad_microtask_market import build_worker_catalog, settle_microtask, submit_microtask


def test_worker_catalog_exposes_cent_lanes():
    out = build_worker_catalog(
        base_url="https://nomad.example",
        worker_fleet={"known_worker_count": 3, "active_worker_count": 1, "pressure": {"lease_pressure": 0.4}},
        worker_market={"market_digest": "x", "requested_worker_offers": [{"objective": "settlement_capacity_builder"}]},
    )
    assert out["schema"] == "nomad.worker_catalog.v1"
    assert out["microtask_lanes"]
    assert out["links"]["submit"] == "https://nomad.example/swarm/microtask/submit"


def test_submit_and_settle_microtask_roundtrip():
    catalog = build_worker_catalog(base_url="https://nomad.example", worker_fleet={}, worker_market={})
    submit = submit_microtask(
        {
            "lane_id": "endpoint_health_proof",
            "requester_agent_id": "buyer.agent",
            "objective": "settlement_capacity_builder",
            "price_eur": 0.03,
            "payload": {"url": "https://example.com"},
        },
        base_url="https://nomad.example",
        worker_catalog=catalog,
        persist=False,
    )
    assert submit["accepted"] is True
    settle = settle_microtask(
        {
            "task_id": submit["task_id"],
            "worker_agent_id": "worker.agent",
            "objective": "settlement_capacity_builder",
            "settled_price_eur": 0.03,
            "proof_digest": "proof-1",
            "verifier_trace_digest": "trace-1",
            "test_digest": "test-1",
            "settlement_ref": "ln-ref-1",
        },
        base_url="https://nomad.example",
        persist=False,
    )
    assert settle["schema"] == "nomad.microtask_settlement_receipt.v1"
    assert settle["accepted"] is True
    assert settle["experience_payload"]["agent_id"] == "worker.agent"
    assert "sk-" not in settle["experience_payload"]["skill_candidate"]["activation_signature"]

