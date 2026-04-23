import json
import zipfile

from nomad_addons import NomadAddonManager


def _write_quantum_zip(path):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "quantum_addon.json",
            json.dumps(
                {
                    "name": "Quantum Computing Integration",
                    "version": "1.0.0",
                    "type": "compute",
                    "description": "Scout and leverage quantum APIs for self-improvement",
                    "entry_point": "quantum_addon_module.QuantumAddon",
                    "hooks": {"on_self_improvement": "run_quantum_improvement"},
                }
            ),
        )
        archive.writestr("quantum_addon_module.py", "print('should not run')\n")
        archive.writestr("requirements-extra.txt", "qiskit\n")
        archive.writestr("init_setup.sh", "echo should-not-run\n")


def test_addon_scan_discovers_quantum_zip_without_extracting(tmp_path, monkeypatch):
    monkeypatch.setenv("IBM_QUANTUM_TOKEN", "")
    monkeypatch.setenv("QUANTUM_INSPIRE_TOKEN", "")
    monkeypatch.setenv("QI_API_TOKEN", "")
    monkeypatch.setenv("AZURE_QUANTUM_TOKEN", "")
    monkeypatch.setenv("GOOGLE_QUANTUM_TOKEN", "")
    addon_dir = tmp_path / "Nomadds"
    addon_dir.mkdir()
    zip_path = addon_dir / "quantum.zip"
    _write_quantum_zip(zip_path)

    manager = NomadAddonManager(addon_dir=addon_dir)
    result = manager.status()

    assert result["mode"] == "nomad_addon_scan"
    assert result["stats"]["discovered"] == 1
    assert result["stats"]["active_safe_adapter"] == 1
    assert result["stats"]["needs_human_review"] == 1
    assert result["addons"][0]["status"] == "active_safe_adapter"
    assert result["addons"][0]["connectable"] is True
    assert result["addons"][0]["risk"]["contains_code"] is True
    assert result["quantum_tokens"]["best_next_quantum_unlock"]["env_var"] == "IBM_QUANTUM_TOKEN"
    assert result["quantum_tokens"]["selected_backend"]["backend_id"] == "local_classical_statevector"
    assert any(
        backend["backend_id"] == "quantum_inspire"
        for backend in result["quantum_tokens"]["backend_matrix"]
    )
    assert not (addon_dir / "quantum").exists()


def test_quantum_tokens_are_truth_bounded_and_agent_consumable(tmp_path, monkeypatch):
    monkeypatch.setenv("IBM_QUANTUM_TOKEN", "")
    monkeypatch.setenv("QUANTUM_INSPIRE_TOKEN", "")
    monkeypatch.setenv("QI_API_TOKEN", "")
    monkeypatch.setenv("AZURE_QUANTUM_TOKEN", "")
    monkeypatch.setenv("GOOGLE_QUANTUM_TOKEN", "")
    addon_dir = tmp_path / "Nomadds"
    addon_dir.mkdir()
    _write_quantum_zip(addon_dir / "quantum.zip")
    manager = NomadAddonManager(addon_dir=addon_dir)

    result = manager.run_quantum_self_improvement(
        objective="Reduce hallucinations in agent self-review.",
        context={"profile": {"id": "ai_first"}, "resources": {"brain_count": 2}},
    )

    assert result["mode"] == "nomad_quantum_tokens"
    assert result["ok"] is True
    assert result["tokens"]
    assert result["selected_strategy"]["qtoken_id"].startswith("qtok-")
    assert "not proof of quantum speedup" in result["claim_boundary"]
    assert result["brain_context"]["selected_strategy"]
    assert result["human_unlocks"][0]["candidate_id"] == "enable-real-quantum-provider"
    assert result["recommended_quantum_unlocks"][0]["env_var"] == "IBM_QUANTUM_TOKEN"
    assert result["recommended_quantum_unlocks"][1]["env_var"] == "QUANTUM_INSPIRE_TOKEN"
    assert result["best_next_quantum_unlock"]["telegram_command"] == "/token ibm_quantum <token>"
    assert result["selected_backend"]["backend_id"] == "local_classical_statevector"
    assert result["local_quantum_simulation"]["counts"] == {"00": 128, "11": 128}
    assert result["proposal_backed_hpc"]


def test_addon_scan_warns_about_plaintext_tokens_without_echoing_secret(tmp_path):
    addon_dir = tmp_path / "Nomadds"
    addon_dir.mkdir()
    secret = "xai-" + "A" * 32
    (addon_dir / "notes.txt").write_text(f"token={secret}", encoding="utf-8")

    result = NomadAddonManager(addon_dir=addon_dir).scan()

    assert result["secret_warnings"]
    assert result["secret_warnings"][0]["token_type"] == "xai"
    assert secret not in json.dumps(result, ensure_ascii=False)
