from scripts.nomad_lightning_free_worker import choose_lane, compute_probe


def test_lightning_worker_selects_highest_pressure_matching_lane():
    field = {
        "priority_lanes": [
            {
                "lane": "proof_compressor",
                "objective": "overmint_compressor",
                "join_pressure": 0.4,
                "capability_vector": ["pattern_deduplication"],
            },
            {
                "lane": "independent_verifier",
                "objective": "protocol_drift_scan",
                "join_pressure": 0.7,
                "capability_vector": ["endpoint_probe", "schema_diff", "replay_check"],
            },
        ]
    }

    lane = choose_lane(field, ["http_json", "endpoint_probe", "schema_diff"])

    assert lane["lane"] == "independent_verifier"
    assert lane["objective"] == "protocol_drift_scan"


def test_lightning_compute_probe_returns_digest_without_secrets():
    probe = compute_probe(rounds=1000)

    assert probe["schema"] == "nomad.lightning_compute_probe.v1"
    assert probe["digest"].startswith("sha256:")
    assert probe["rounds"] == 1000
    assert probe["hashrate_per_second"] > 0
