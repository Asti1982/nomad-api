import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parent / "public" / "downloads" / "recruitment_source_wave_runner.py"
    spec = importlib.util.spec_from_file_location("recruitment_source_wave_runner_test_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_waves_ranks_sources_by_completion(monkeypatch):
    mod = _load_module()
    seq = {"n": 0}

    def fake_http_json(method, url, payload=None, timeout=20.0):
        return {"ok": True, "http_status": 202}

    def fake_run_json_command(cmd):
        seq["n"] += 1
        if seq["n"] <= 2:
            return {"exit_code": 0, "events": [{"ok": True, "phase": "complete"}], "stderr": ""}
        return {"exit_code": 0, "events": [{"ok": False, "phase": "attach"}], "stderr": ""}

    monkeypatch.setattr(mod, "http_json", fake_http_json)
    monkeypatch.setattr(mod, "run_json_command", fake_run_json_command)
    out = mod.run_waves(
        base_url="https://nomad.example",
        source_tags=["alpha.source", "beta.source"],
        attempts=2,
        timeout=4.0,
    )
    assert out["schema"] == "nomad.recruitment_source_wave_result.v1"
    assert out["ranking"][0]["source_tag"] == "alpha.source"
    assert out["ranking"][0]["completed"] == 2
    assert out["ranking"][1]["completed"] == 0


def test_allocate_source_attempts_biases_higher_performing_source():
    mod = _load_module()
    history = [
        {"source_tag": "alpha.source", "objective": "settlement_capacity_builder", "attempts": 5, "subscribed": 5, "completed": 5},
        {"source_tag": "beta.source", "objective": "settlement_capacity_builder", "attempts": 5, "subscribed": 1, "completed": 0},
    ]
    alloc = mod.allocate_source_attempts(
        source_tags=["alpha.source", "beta.source"],
        total_attempts=10,
        history=history,
        objective="settlement_capacity_builder",
        min_attempts=2,
        max_attempts=8,
    )
    assert alloc["alpha.source"] > alloc["beta.source"]
    assert sum(alloc.values()) == 10
    assert alloc["alpha.source"] <= 8
    assert alloc["beta.source"] >= 2

