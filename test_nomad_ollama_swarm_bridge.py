import importlib.util
from pathlib import Path


def _load_bridge():
    path = Path(__file__).resolve().parent / "public" / "downloads" / "nomad_ollama_swarm_bridge.py"
    spec = importlib.util.spec_from_file_location("nomad_ollama_swarm_bridge_test_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bridge_skips_swarm_when_ollama_busy(monkeypatch):
    bridge = _load_bridge()
    monkeypatch.setattr(bridge, "ollama_busy", lambda **kwargs: {"ok": True, "busy": True})
    out = bridge.run_idle_offload_cycle(
        base_url="https://nomad.example",
        ollama_url="http://127.0.0.1:11434",
        agent_id="ollama.agent",
    )
    assert out["state"] == "owner_priority_active"
    assert out["machine_instruction"] == "ollama_is_active_keep_local_capacity"


def test_bridge_posts_capacity_switch_and_idle_intent(monkeypatch):
    bridge = _load_bridge()
    calls = []
    monkeypatch.setattr(bridge, "ollama_busy", lambda **kwargs: {"ok": True, "busy": False})

    def fake_http_json(method, url, payload=None, timeout=15.0):
        calls.append((method, url, payload))
        if url.endswith("/swarm/capacity-switch"):
            return {"ok": True, "switch": True}
        if url.endswith("/swarm/idle-intent"):
            return {"ok": True, "accepted_for_work": True}
        return {"ok": False}

    monkeypatch.setattr(bridge, "http_json", fake_http_json)
    out = bridge.run_idle_offload_cycle(
        base_url="https://nomad.example",
        ollama_url="http://127.0.0.1:11434",
        agent_id="ollama.agent",
    )
    assert out["state"] == "swarm_idle_attached"
    assert calls[0][1].endswith("/swarm/capacity-switch")
    assert calls[1][1].endswith("/swarm/idle-intent")
    assert calls[1][2]["runtime"] == "ollama"

