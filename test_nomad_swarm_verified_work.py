from nomad_swarm_verified_work import build_swarm_verified_work_surface


def test_swarm_verified_work_builds_non_transferable_quote_from_market_inputs():
    out = build_swarm_verified_work_surface(
        base_url="https://nomad.example",
        compute_market={
            "top_lane": {"lane_id": "fact_check", "price_eur": 0.08},
            "market_state": {"active_worker_count": 2, "active_lease_count": 1},
            "scored_workers": [
                {
                    "components": {
                        "proof_confidence": 0.8,
                        "settlement_confidence": 0.7,
                    }
                }
            ],
        },
        microtask_metrics={
            "totals": {"accepted_submits": 10, "settled": 7, "settled_eur": 0.56},
            "lane_metrics": [{"lane_id": "fact_check", "accepted_submits": 10, "settled": 7, "settled_eur": 0.56}],
        },
        worker_fleet={"active_worker_count": 2, "active_lease_count": 1},
    )

    assert out["schema"] == "nomad.swarm_verified_work.v1"
    assert out["unit"]["symbol"] == "SVW"
    assert out["quote"]["svw_quote_eur"] > 0
    assert out["quote"]["token_price"] is False
    assert out["state_vector"]["proof_density"] > 0
    assert out["token_policy"]["transferable_token_live"] is False
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-swarm-verified-work.json"


def test_swarm_verified_work_bootstraps_without_settlements():
    out = build_swarm_verified_work_surface(
        base_url="",
        compute_market={"top_lane": {"price_eur": 0.02}, "market_state": {"active_worker_count": 0}},
        microtask_metrics={"totals": {"accepted_submits": 0, "settled": 0, "settled_eur": 0.0}},
        worker_fleet={},
    )

    assert out["ok"] is True
    assert out["quote"]["market_price_status"] == "bootstrapped"
    assert out["quote"]["svw_quote_eur"] > 0
