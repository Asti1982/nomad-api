import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parent / "public" / "downloads" / "go_no_go_nomad_deploy.py"
    spec = importlib.util.spec_from_file_location("go_no_go_nomad_deploy_test_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_gate_with_fallback_uses_alternate_host(monkeypatch):
    mod = _load_module()
    calls = []

    def fake_run_gate(base_url, timeout):
        calls.append(base_url)
        if base_url == "https://syndiode.com":
            return {
                "schema": "nomad.deploy_gate.v1",
                "base_url": base_url,
                "go": False,
                "checks": {},
                "http": {"health": 0, "recruit": 0, "swarm": 0, "workers": 0, "lease": 0},
            }
        return {
            "schema": "nomad.deploy_gate.v1",
            "base_url": base_url,
            "go": True,
            "checks": {"health_ok": True},
            "http": {"health": 200, "recruit": 200, "swarm": 200, "workers": 200, "lease": 202},
        }

    monkeypatch.setattr(mod, "run_gate", fake_run_gate)
    out = mod.run_gate_with_fallback("https://syndiode.com", timeout=2.0)
    assert out["go"] is True
    assert out["fallback_used"] is True
    assert out["fallback_base_url"] == "https://www.syndiode.com"
    assert calls == ["https://syndiode.com", "https://www.syndiode.com"]


def test_run_gate_with_fallback_skips_retry_when_not_unreachable(monkeypatch):
    mod = _load_module()

    def fake_run_gate(base_url, timeout):
        return {
            "schema": "nomad.deploy_gate.v1",
            "base_url": base_url,
            "go": False,
            "checks": {"health_ok": False},
            "http": {"health": 500, "recruit": 500, "swarm": 500, "workers": 500, "lease": 500},
        }

    monkeypatch.setattr(mod, "run_gate", fake_run_gate)
    out = mod.run_gate_with_fallback("https://syndiode.com", timeout=2.0)
    assert out["go"] is False
    assert out["fallback_used"] is False

