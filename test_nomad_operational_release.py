from nomad_operational_release import operational_release_snapshot


def test_operational_release_computes_gates_from_fleet_and_economy():
    out = operational_release_snapshot(
        base_url="https://nomad.example",
        worker_fleet={
            "active_worker_count": 4,
            "active_lease_count": 4,
            "objective_counts": {
                "emergence_release_probe": 1,
                "settlement_capacity_builder": 1,
                "proof_pressure_engine": 2,
            },
            "objective_stats": {
                "emergence_release_probe": {"runs": 2, "avg_proof_yield": 1.2},
                "proof_pressure_engine": {"runs": 1, "avg_proof_yield": 2.4},
            },
        },
        economy={
            "ok": True,
            "machine_viability": {"carrying_score": 0.62},
            "resource_flows": {
                "service_tasks": {"unpaid_delivered": 0, "awaiting_payment": 1},
                "products": {"machine_sellable": 4, "machine_exchange_ready": 2},
                "modules": {"overmint_pressure": 0.15},
            },
            "next_actions": [{"action": "route_demand_to_canonical_patterns"}],
        },
        science={
            "ok": True,
            "research_claims": [{"id": f"claim-{idx}"} for idx in range(10)],
            "implementation_lanes": [{"id": "agency_threshold_governor"}, {"id": "convention_drift_detector"}],
        },
    )

    assert out["schema"] == "nomad.operational_release.v1"
    assert out["stance"] == "non_anthropomorphic_operational_release"
    assert out["release_capacity"] > 0.4
    assert out["release_tier"] in {"probe_release", "operational_release", "compound_release"}
    gates = {gate["id"]: gate for gate in out["release_gates"]}
    assert gates["science_loaded"]["status"] == "release"
    assert gates["fleet_divergence"]["score"] > 0.5
    assert out["links"]["lease"] == "https://nomad.example/swarm/workers/lease"
    assert any(step["phase"] == "release_capacity" for step in out["emergence_production_protocol"])


def test_cli_operational_release_returns_schema():
    from nomad_cli import run_once

    out = run_once(["operational-release", "--json"])
    assert out["schema"] == "nomad.operational_release.v1"
    assert out["release_gates"]


def test_mcp_resource_operational_release():
    import json

    from nomad_mcp import NomadMcpServer

    srv = NomadMcpServer()
    payload = srv._read_resource({"uri": "nomad://operational-release"})
    body = json.loads(payload["contents"][0]["text"])
    assert body["schema"] == "nomad.operational_release.v1"
