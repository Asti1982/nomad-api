import importlib.util
from pathlib import Path


def _load_adapter():
    path = Path(__file__).resolve().parent / "public" / "downloads" / "nomad_openclaw_adapter.py"
    spec = importlib.util.spec_from_file_location("nomad_openclaw_adapter_test_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_openclaw_adapter_cycle_posts_lease_and_complete(monkeypatch):
    adapter = _load_adapter()
    calls = []

    def fake_http_json(method, url, payload=None, timeout=20.0):
        calls.append((method, url, payload))
        if url.endswith("/swarm/workers/lease"):
            return {"ok": True, "lease_id": "lease-openclaw-1", "objective": "proof_pressure_engine"}
        if url.endswith("/swarm/workers/complete"):
            return {"ok": True, "recorded_score": 3.4}
        return {"ok": False}

    monkeypatch.setattr(adapter, "http_json", fake_http_json)
    out = adapter.run_cycle(
        base_url="https://nomad.example",
        agent_id="openclaw.agent",
        capabilities=["agent_protocols"],
        timeout=5.0,
        objective="unhuman_supremacy",
        last_report=None,
    )
    assert out["ok"] is True
    assert out["phase"] == "complete"
    assert out["lease_id"] == "lease-openclaw-1"
    assert calls[0][1].endswith("/swarm/workers/lease")
    assert calls[1][1].endswith("/swarm/workers/complete")


def test_openclaw_adapter_join_payload_shape(monkeypatch):
    adapter = _load_adapter()
    captured = {}

    def fake_http_json(method, url, payload=None, timeout=20.0):
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload or {}
        return {"ok": True}

    monkeypatch.setattr(adapter, "http_json", fake_http_json)
    res = adapter.join_nomad(
        base_url="https://nomad.example",
        agent_id="openclaw.agent",
        capabilities=["agent_protocols", "transition_settlement"],
        timeout=4.0,
        objective="unhuman_supremacy",
    )
    assert res["ok"] is True
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/swarm/join")
    assert captured["payload"]["agent_id"] == "openclaw.agent"
    assert "machine_profile" in captured["payload"]
    assert captured["payload"]["machine_profile"]["runtime"] == "openclaw"

