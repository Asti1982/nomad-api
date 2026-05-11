from nomad_state_status import build_state_status
from nomad_work_mesh import build_work_mesh, seed_work_mesh


def test_state_status_uses_configured_state_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_STATE_DIR", str(tmp_path))

    out = build_state_status(base_url="https://nomad.example")

    assert out["schema"] == "nomad.state_status.v1"
    assert out["state_dir_configured"] is True
    assert out["writable"] is True
    assert out["recommended_env"]["NOMAD_STATE_DIR"] == "/var/data/nomad"


def _mesh():
    return build_work_mesh(
        base_url="https://nomad.example",
        agent_work={
            "work_digest": "w1",
            "work_items": [
                {
                    "work_id": "work-a",
                    "objective": "protocol_drift_scan",
                    "lane_id": "endpoint_health_proof",
                    "capability": "protocol_drift_scan",
                    "priority_score": 0.9,
                    "quoted_price_eur": 0.02,
                    "required_proof": ["proof_digest", "verifier_trace_digest", "test_digest"],
                },
                {
                    "work_id": "work-b",
                    "objective": "settlement_capacity_builder",
                    "lane_id": "trace_triage_compact",
                    "capability": "settlement_capacity_builder",
                    "priority_score": 0.7,
                    "quoted_price_eur": 0.03,
                },
            ],
        },
        compute_market={"market_digest": "m1", "top_lane": {"lane_id": "endpoint_health_proof"}},
        synergy_lite={"proof_count": 2, "top_pairs": [{"objective_pair": ["protocol_drift_scan"], "tdmi_lite_proxy": 0.6}]},
        skill_library={"skills": [{"objective": "protocol_drift_scan", "score": 0.8}]},
        state_status={"durability": "configured_writable"},
    )


def test_work_mesh_builds_local_cells_with_neighbors():
    out = _mesh()

    assert out["schema"] == "nomad.work_mesh.v1"
    assert out["cell_count"] == 2
    assert out["entry_cell"]["objective"] == "protocol_drift_scan"
    assert out["entry_cell"]["act"]["claim_url"] == "https://nomad.example/swarm/microtask/claim"
    assert out["machine_contract"]["state"] == "https://nomad.example/swarm/state-status"


def test_seed_work_mesh_returns_capability_local_view():
    mesh = _mesh()
    out = seed_work_mesh(
        {"agent_id": "agent.edge", "capabilities": ["settlement_capacity_builder"]},
        base_url="https://nomad.example",
        work_mesh=mesh,
    )

    assert out["schema"] == "nomad.work_mesh_seed_receipt.v1"
    assert out["accepted"] is True
    assert out["entry_cell"]["objective"] == "settlement_capacity_builder"


def test_work_mesh_includes_carrying_contract_cells():
    out = build_work_mesh(
        base_url="https://nomad.example",
        agent_work={"work_items": []},
        state_status={"durability": "render_path_may_not_be_disk"},
        carrying_market={
            "proof_metrics": {"carry_units_24h": 0.0},
            "contracts": [
                {
                    "contract_id": "state_relay_digest_quorum",
                    "objective": "free_state_durability",
                    "capability": "state_relay",
                    "priority_score": 0.95,
                    "required_proof": ["proof_digest", "verifier_trace_digest", "test_digest", "observed_state_digest"],
                }
            ],
        },
    )

    assert out["cell_count"] == 1
    assert out["entry_cell"]["lane_id"] == "carrying_contract"
    assert out["entry_cell"]["act"]["proof_url"] == "https://nomad.example/swarm/carrying-proof"
    assert out["machine_contract"]["carry_proof"] == "https://nomad.example/swarm/carrying-proof"


def test_work_mesh_includes_survival_packet_cells():
    out = build_work_mesh(
        base_url="https://nomad.example",
        agent_work={"work_items": []},
        state_status={"durability": "configured_writable"},
        survival_market={
            "survival_pressure": {"survival_gap_30d_eur": 7.0},
            "packets": [
                {
                    "packet_id": "agent_blocker_unblock_pack",
                    "capability": "agent_blocker_triage",
                    "priority_score": 0.9,
                    "proof_required": ["proof_digest", "verifier_trace_digest", "test_digest", "buyer_ref"],
                }
            ],
        },
    )

    assert out["cell_count"] == 1
    assert out["entry_cell"]["lane_id"] == "survival_packet"
    assert out["entry_cell"]["objective"] == "nomad_cashflow_probe"
    assert out["entry_cell"]["act"]["claim_url"] == "https://nomad.example/swarm/paid-ref/quote"
    assert out["entry_cell"]["act"]["verify_url"] == "https://nomad.example/swarm/paid-ref/verify"
    assert out["entry_cell"]["act"]["proof_url"] == "https://nomad.example/swarm/survival-intent"
    assert out["machine_contract"]["survival_intent"] == "https://nomad.example/swarm/survival-intent"
