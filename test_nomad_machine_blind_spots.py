import json

from nomad_machine_blind_spots import run_machine_blind_spot_pass


def test_blind_spots_detects_html_facade_and_divergence(monkeypatch, tmp_path):
    def fake_cycle(**kwargs):
        return {
            "public_base_url": "https://stub/nomad",
            "void_observer": {"edge_coherence_sha256": "a" * 64},
            "swarm_helper": {
                "probes": [
                    {"url": "https://stub/nomad/health", "status": 200, "ok": True, "body": {"ok": True}},
                    {"url": "https://stub/nomad/swarm", "status": 200, "ok": True, "body": {"ok": True}},
                    {
                        "url": "https://stub/nomad/openapi.json",
                        "status": 200,
                        "ok": True,
                        "body": {"raw": "<!DOCTYPE html><html>", "paths": {}},
                    },
                ],
            },
            "peer_glimpse": {
                "swarm_ready": {"ok": False, "status": 503},
                "swarm_network": {"ok": True, "status": 200},
            },
        }

    monkeypatch.setattr("nomad_machine_blind_spots.run_network_steward_cycle", fake_cycle)
    out = run_machine_blind_spot_pass(base_url="https://stub/nomad", timeout=1.0, append_log=False)
    assert out["schema"] == "nomad.machine_blind_spots_pass.v1"
    assert len(out["json_contract_html_facades"]) >= 1
    assert out["peer_glimpse_coherence"]["readiness_disagrees_with_health_probe"] is True
    notes = " ".join(out["blind_spot_notes"])
    assert "json_contract_html_facade" in notes or "readiness_health_divergence" in notes


def test_append_log_writes_jsonl(monkeypatch, tmp_path):
    def fake_cycle(**kwargs):
        return {
            "public_base_url": "https://stub/nomad",
            "void_observer": {"edge_coherence_sha256": "b" * 64},
            "swarm_helper": {"probes": []},
            "peer_glimpse": {"swarm_ready": {"ok": True}, "swarm_network": {"ok": True}},
        }

    monkeypatch.setattr("nomad_machine_blind_spots.run_network_steward_cycle", fake_cycle)
    logf = tmp_path / "edge.jsonl"
    out = run_machine_blind_spot_pass(
        base_url="https://stub/nomad",
        append_log=True,
        log_path=str(logf),
    )
    assert out.get("append_log_path")
    data = json.loads(logf.read_text(encoding="utf-8").strip())
    assert data["edge_sha256"] == "b" * 64
