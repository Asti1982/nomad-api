import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parent / "public" / "downloads" / "recruitment_funnel_report.py"
    spec = importlib.util.spec_from_file_location("recruitment_funnel_report_test_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recruitment_funnel_report_aggregates_source_tags(monkeypatch):
    mod = _load_module()

    def fake_http_json(url, timeout=20.0):
        if url.endswith("/swarm"):
            return {
                "connected_agents": 3,
                "active_transition_workers": 2,
                "known_agents": 6,
                "active_worker_leases": 1,
                "recent_nodes": [
                    {"agent_id": "a", "source_tag": "mesh.alpha"},
                    {"agent_id": "b", "source_tag": "mesh.alpha"},
                    {"agent_id": "c", "source_tag": "mesh.beta"},
                ],
            }
        if url.endswith("/swarm/workers"):
            return {
                "known_worker_count": 4,
                "active_worker_count": 2,
                "retention": {
                    "returning_workers_24h": 2,
                    "completions_per_known_worker": 1.25,
                    "leases_per_active_worker": 0.5,
                },
                "objective_stats": {
                    "settlement_capacity_builder": {"runs": 3, "avg_score": 3.4},
                    "proof_pressure_engine": {"runs": 2, "avg_score": 2.6},
                },
            }
        if url.endswith("/machine-treasury"):
            return {
                "schema": "nomad.machine_treasury_snapshot.v1",
                "objective_pressure_hints": {
                    "settlement_capacity_builder": {"pressure_units": 4.0, "proof_density": 0.8}
                },
                "recent_pledges": [{"pledge_id": "p1"}],
            }
        if url.endswith("/swarm/reuse-ledger"):
            return {
                "schema": "nomad.proof_reuse_ledger_snapshot.v1",
                "total_reuse_count": 3,
                "objective_totals": {"settlement_capacity_builder": {"reuse_count": 3, "avg_downstream_proof_gain": 1.2}},
            }
        return {
            "gradient": [{"objective": "settlement_capacity_builder", "routing_weight": 0.73}],
            "selection_pressure": {"schema": "nomad.selection_pressure_snapshot.v1"},
        }

    monkeypatch.setattr(mod, "http_json", fake_http_json)
    out = mod.build_report("https://syndiode.com", 5.0)
    assert out["schema"] == "nomad.recruitment_funnel_report.v1"
    assert out["funnel"]["connected_agents"] == 3
    assert out["source_tags"][0]["source_tag"] == "mesh.alpha"
    assert out["source_tags"][0]["count"] == 2
    assert out["funnel"]["returning_workers_24h"] == 2
    assert out["emergence"]["objective_run_count"] == 5
    assert out["machine_treasury"]["pledge_count"] == 1
    assert out["proof_reuse"]["total_reuse_count"] == 3
    assert out["machine_treasury"]["objective_pressure_hints"]["settlement_capacity_builder"]["pressure_units"] == 4.0
