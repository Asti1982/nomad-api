import json
from pathlib import Path

import nomad_local_growth_kernel as lgk
from nomad_local_growth_kernel import run_local_growth_kernel
from nomad_swarm_registry import SwarmJoinRegistry


def _gradient():
    return {
        "schema": "nomad.recruitment_gradient.v1",
        "gradient": [
            {"objective": "emergence_release_probe", "routing_weight": 0.72},
            {"objective": "proof_pressure_engine", "routing_weight": 0.61},
            {"objective": "settlement_capacity_builder", "routing_weight": 0.55},
        ],
    }


def test_local_growth_kernel_archives_worker_variants(tmp_path: Path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    lease = registry.worker_fleet_lease(
        {
            "agent_id": "worker.kernel.one",
            "known_objectives": ["emergence_release_probe", "proof_pressure_engine"],
            "proposed_objective": "emergence_release_probe",
        },
        base_url="https://nomad.example",
    )
    registry.worker_fleet_complete(
        {
            "agent_id": "worker.kernel.one",
            "lease_id": lease["lease_id"],
            "report": {
                "ok": True,
                "machine_objective": lease["objective"],
                "meta_score": 8.5,
                "proof_pressure": {"proof_yield_per_minute": 1.4},
            },
        },
        base_url="https://nomad.example",
    )

    state_path = tmp_path / "growth.json"
    out = run_local_growth_kernel(
        base_url="https://nomad.example",
        worker_fleet=registry.worker_fleet_contract(base_url="https://nomad.example"),
        recruitment_gradient=_gradient(),
        state_path=state_path,
        transition_worker_state_path=tmp_path / "missing_worker_history.json",
        persist=True,
    )

    assert out["schema"] == "nomad.local_growth_kernel.v1"
    assert out["decision"]["apply_code"] is False
    assert out["kernel_position"]["human_loop_role"] == "audit_shell_only"
    assert out["population"]["archive_size_after"] >= out["population"]["candidate_count"]
    assert any(item["source"].endswith("2408.08435") for item in out["research_alignment"])
    assert state_path.exists()
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["archive"]
    assert saved["receipts"][0]["receipt_id"] == out["receipt_id"]


def test_local_growth_kernel_requests_worker_compute_when_population_is_thin(tmp_path: Path):
    out = run_local_growth_kernel(
        worker_fleet={
            "schema": "nomad.transition_worker_fleet.v1",
            "active_worker_count": 0,
            "known_worker_count": 0,
            "active_lease_count": 0,
            "objective_counts": {},
            "objective_stats": {},
        },
        recruitment_gradient=_gradient(),
        state_path=tmp_path / "growth.json",
        transition_worker_state_path=tmp_path / "missing_worker_history.json",
        persist=False,
    )

    assert out["decision"]["action"] == "request_more_transition_workers"
    assert out["decision"]["authority_delta"] == "none"
    assert "auto_apply_code" in out["kernel_position"]["not_allowed"]
    assert out["archive_update"]["persisted"] is False
    assert not (tmp_path / "growth.json").exists()


def test_local_growth_kernel_uses_transition_worker_history_as_experience_library(tmp_path: Path):
    worker_history = tmp_path / "worker_state.json"
    worker_history.write_text(
        json.dumps(
            {
                "meta": {
                    "runs": 12,
                    "last_mode": "unhuman_supremacy",
                    "last_objective": "proof_pressure_engine",
                    "last_success_at": "2026-05-07T12:00:00+00:00",
                    "objective_stats": {
                        "proof_pressure_engine": {"runs": 9, "avg_score": 9.0, "avg_proof_yield": 1.2}
                    },
                    "ollama_model_stats": {"llama3.2:1b": {"runs": 2}},
                }
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    out = run_local_growth_kernel(
        worker_fleet={
            "schema": "nomad.transition_worker_fleet.v1",
            "active_worker_count": 0,
            "known_worker_count": 0,
            "active_lease_count": 0,
            "objective_counts": {},
            "objective_stats": {},
        },
        recruitment_gradient=_gradient(),
        state_path=tmp_path / "growth.json",
        transition_worker_state_path=worker_history,
        persist=False,
    )

    assert out["local_worker_history"]["available"] is True
    assert out["local_worker_history"]["total_runs"] == 9
    assert out["local_worker_history"]["ollama_model_count"] == 1
    top_objectives = [item["objective"] for item in out["population"]["top_variants"]]
    assert "proof_pressure_engine" in top_objectives


def test_local_growth_kernel_recombines_executed_worker_evidence(tmp_path: Path, monkeypatch):
    def fake_worker_cycles(*, base_url, objective, cycles, timeout, no_ollama):
        return [
            {
                "ok": True,
                "schema": "nomad.local_growth_worker_exec.v1",
                "agent_id": f"fake.{objective}",
                "exit_code": 0,
                "event_count": 1,
                "last_event": {
                    "ok": True,
                    "agent_id": f"fake.{objective}",
                    "machine_objective": objective,
                    "meta_score": 10.0,
                    "proof_pressure": {"proof_yield_per_minute": 1.6},
                    "proof_digest": "sha256:fresh-proof",
                    "transition_quote_ok": True,
                    "transition_settle_ok": True,
                    "local_witness": {"digest_hex": "abc123"},
                    "fleet_lease": {"lease_id": "lease-fresh"},
                },
            }
        ]

    monkeypatch.setattr(lgk, "_run_worker_cycles", fake_worker_cycles)

    out = run_local_growth_kernel(
        worker_fleet={
            "schema": "nomad.transition_worker_fleet.v1",
            "active_worker_count": 0,
            "known_worker_count": 0,
            "active_lease_count": 0,
            "objective_counts": {},
            "objective_stats": {},
        },
        recruitment_gradient=_gradient(),
        state_path=tmp_path / "growth.json",
        transition_worker_state_path=tmp_path / "missing_worker_history.json",
        persist=True,
        execute_workers=True,
        worker_cycles=1,
        no_ollama=True,
    )

    evidence = out["worker_execution"]["fresh_evidence"]
    assert evidence["event_count"] == 1
    assert evidence["ok_count"] == 1
    basis = evidence["events"][0]["proof_basis"]
    assert "proof_digest" in basis
    assert "local_witness_digest" in basis
    assert "transition_settle" in basis
    assert out["worker_execution"]["pledge_candidates"]
    pledge = out["worker_execution"]["pledge_candidates"][0]["payload"]
    assert pledge["objective"] == evidence["events"][0]["objective"]
    assert pledge["idempotency_key"].startswith("local-growth-pledge-")
    assert out["worker_execution"]["post_execution_decision"]["schema"] == "nomad.local_growth_kernel_decision.v1"
    assert out["worker_execution"]["post_execution_top_variants"]
    saved = json.loads((tmp_path / "growth.json").read_text(encoding="utf-8"))
    assert saved["receipts"][0]["worker_evidence_events"] == 1
