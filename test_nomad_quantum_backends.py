import pytest

from nomad_quantum_backends import ClassicalQuantumSimulator, QuantumBackendPlanner


def test_local_classical_simulator_runs_bell_pair():
    result = ClassicalQuantumSimulator().run()

    assert result["ok"] is True
    assert result["backend_id"] == "local_classical_statevector"
    assert result["probabilities"] == {"00": 0.5, "11": 0.5}
    assert result["counts"] == {"00": 128, "11": 128}
    assert "no quantum speedup claim" in result["claim_boundary"]


def test_local_classical_simulator_rejects_unsupported_gate():
    with pytest.raises(ValueError, match="unsupported"):
        ClassicalQuantumSimulator().run(
            {
                "qubits": 1,
                "gates": [{"gate": "swap", "target": 0}],
            }
        )


def test_quantum_backend_matrix_defaults_to_local_and_lists_provider_paths(monkeypatch):
    for env_var in (
        "IBM_QUANTUM_TOKEN",
        "QUANTUM_INSPIRE_TOKEN",
        "QI_API_TOKEN",
        "EUROHPC_PROJECT_ID",
        "EGI_PROJECT_ID",
        "DENBI_PROJECT_ID",
        "HPC_SSH_HOST",
        "HPC_SLURM_ACCOUNT",
        "NOMAD_QUANTUM_BACKEND",
        "NOMAD_ALLOW_REAL_QUANTUM",
        "NOMAD_ALLOW_HPC_SUBMIT",
    ):
        monkeypatch.delenv(env_var, raising=False)

    plan = QuantumBackendPlanner().build_plan(objective="test matrix")
    backend_ids = {backend["backend_id"] for backend in plan["backends"]}

    assert plan["selected_backend"]["backend_id"] == "local_classical_statevector"
    assert plan["local_simulation"]["counts"] == {"00": 128, "11": 128}
    assert "ibm_quantum_open_plan" in backend_ids
    assert "quantum_inspire" in backend_ids
    assert "eurohpc_ai_factories_playground" in backend_ids
    assert any(action["type"] == "proposal_backed_hpc_unlock" for action in plan["next_actions"])


def test_configured_quantum_provider_stays_gated_without_approval(monkeypatch):
    monkeypatch.setenv("IBM_QUANTUM_TOKEN", "ibm-test-token")
    monkeypatch.setenv("NOMAD_ALLOW_REAL_QUANTUM", "false")

    plan = QuantumBackendPlanner().build_plan()
    ibm = next(backend for backend in plan["backends"] if backend["backend_id"] == "ibm_quantum_open_plan")

    assert ibm["configured"] is True
    assert ibm["can_execute_now"] is False
    assert ibm["network_calls"] == "disabled_until_human_unlock"
    assert plan["selected_backend"]["backend_id"] == "local_classical_statevector"
