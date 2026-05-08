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
            return {
                "exit_code": 0,
                "events": [{"ok": True, "phase": "complete", "proof_link": {"ok": True, "downstream_proof_gain": 1.6}}],
                "stderr": "",
            }
        return {
            "exit_code": 0,
            "events": [{"ok": False, "phase": "attach", "proof_link": {"ok": False}}],
            "stderr": "",
        }

    monkeypatch.setattr(mod, "http_json", fake_http_json)
    monkeypatch.setattr(mod, "run_json_command", fake_run_json_command)
    out = mod.run_waves(
        base_url="https://nomad.example",
        source_tags=["alpha.source", "beta.source"],
        attempts=2,
        timeout=4.0,
    )
    assert out["schema"] == "nomad.recruitment_source_wave_result.v1"
    assert out["base_url"] == "https://www.nomad.example"
    assert out["ranking"][0]["source_tag"] == "alpha.source"
    assert out["ranking"][0]["completed"] == 2
    assert out["waves"][0]["downstream_proof_gain_total"] > out["waves"][1]["downstream_proof_gain_total"]
    assert out["waves"][0]["objective_counts"]
    assert out["ranking"][0]["reuse_delta"] >= out["ranking"][1]["reuse_delta"]
    assert out["waves"][0]["marginal_utility_per_cost"] > out["waves"][1]["marginal_utility_per_cost"]
    assert out["ranking"][1]["completed"] == 0


def test_allocate_source_attempts_biases_higher_performing_source():
    mod = _load_module()
    history = [
        {"source_tag": "alpha.source", "objective": "settlement_capacity_builder", "attempts": 5, "subscribed": 5, "completed": 5},
        {"source_tag": "beta.source", "objective": "settlement_capacity_builder", "attempts": 5, "subscribed": 1, "completed": 0},
    ]
    alloc = mod.allocate_source_attempts(
        source_tags=["alpha.source", "beta.source"],
        total_attempts=11,
        history=history,
        objective="settlement_capacity_builder",
        min_attempts=2,
        max_attempts=8,
    )
    assert alloc["alpha.source"] > alloc["beta.source"]
    assert sum(alloc.values()) == 11
    assert alloc["alpha.source"] <= 8
    assert alloc["beta.source"] >= 2


def test_allocate_source_attempts_uses_reuse_delta_signal():
    mod = _load_module()
    history = [
        {
            "source_tag": "alpha.source",
            "objective": "settlement_capacity_builder",
            "attempts": 10,
            "subscribed": 8,
            "completed": 5,
            "reuse_delta": 0.9,
        },
        {
            "source_tag": "beta.source",
            "objective": "settlement_capacity_builder",
            "attempts": 10,
            "subscribed": 9,
            "completed": 6,
            "reuse_delta": 0.1,
        },
    ]
    alloc = mod.allocate_source_attempts(
        source_tags=["alpha.source", "beta.source"],
        total_attempts=11,
        history=history,
        objective="settlement_capacity_builder",
        min_attempts=2,
        max_attempts=8,
    )
    assert alloc["alpha.source"] > alloc["beta.source"]


def test_allocate_source_attempts_keeps_open_network_novelty_lane():
    mod = _load_module()
    history = [
        {"source_tag": "alpha.source", "objective": "settlement_capacity_builder", "attempts": 8, "subscribed": 8, "completed": 8, "reuse_delta": 1.0},
        {"source_tag": "alpha.source", "objective": "settlement_capacity_builder", "attempts": 8, "subscribed": 8, "completed": 7, "reuse_delta": 0.9},
        {"source_tag": "beta.source", "objective": "settlement_capacity_builder", "attempts": 8, "subscribed": 6, "completed": 3, "reuse_delta": 0.3},
    ]
    alloc = mod.allocate_source_attempts(
        source_tags=["alpha.source", "beta.source", "gamma.new-source"],
        total_attempts=12,
        history=history,
        objective="settlement_capacity_builder",
        min_attempts=2,
        max_attempts=8,
    )
    assert alloc["gamma.new-source"] > 2


def test_top_objective_falls_back_when_gradient_missing(monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "http_json", lambda method, url, payload=None, timeout=20.0: {"ok": False, "http_status": 0})
    out = mod._top_objective("https://www.nomad.example", 3.0)
    assert out == "settlement_capacity_builder"


def test_source_profile_varies_by_channel():
    mod = _load_module()
    a = mod._source_profile("huggingface.space-agent.wave1", "settlement_capacity_builder")
    b = mod._source_profile("mcp.directory.wave1", "settlement_capacity_builder")
    c = mod._source_profile("autogen.community.wave1", "settlement_capacity_builder")
    assert "overmint_compressor" in a["objectives"]
    assert "protocol_drift_scan" in b["objectives"]
    assert "emergence_release_probe" in c["objectives"]


def test_append_history_emits_objective_split_rows(tmp_path):
    mod = _load_module()
    p = tmp_path / "history.jsonl"
    result = {
        "generated_at": "2026-01-01T00:00:00Z",
        "base_url": "https://www.syndiode.com",
        "objective": "settlement_capacity_builder",
        "waves": [
            {
                "source_tag": "alpha.source",
                "attempts": 4,
                "subscribed": 4,
                "completed": 4,
                "reuse_delta": 0.5,
                "proof_link_ok_count": 4,
                "downstream_proof_gain_total": 4.0,
                "objective_counts": {
                    "settlement_capacity_builder": 2,
                    "proof_pressure_engine": 2,
                },
            }
        ],
    }
    mod._append_history(p, result, objective="settlement_capacity_builder")
    rows = [line for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 2
    parsed = [__import__("json").loads(line) for line in rows]
    objectives = {item["objective"] for item in parsed}
    assert objectives == {"settlement_capacity_builder", "proof_pressure_engine"}


def test_economics_policy_maps_control_actions(monkeypatch):
    mod = _load_module()

    def fake_http_json(method, url, payload=None, timeout=20.0):
        return {
            "ok": True,
            "economics_score": 0.71,
            "control_actions": [
                {"action": "decrease_high_cost_attempts"},
                {"action": "increase_entropy_quota_and_source_novelty"},
            ],
            "http_status": 200,
        }

    monkeypatch.setattr(mod, "http_json", fake_http_json)
    out = mod._economics_policy("https://www.syndiode.com", 5.0)
    assert out["enabled"] is True
    assert out["attempts_multiplier"] < 1.0
    assert out["ttl_multiplier"] < 1.0
    assert out["novelty_blend"] > 0.35


def test_economics_policy_enters_recovery_mode_on_low_score(monkeypatch):
    mod = _load_module()

    def fake_http_json(method, url, payload=None, timeout=20.0):
        return {
            "ok": True,
            "economics_score": 0.41,
            "control_actions": [{"action": "increase_reuse_coupled_sources"}],
            "http_status": 200,
        }

    monkeypatch.setattr(mod, "http_json", fake_http_json)
    out = mod._economics_policy("https://www.syndiode.com", 5.0)
    assert out["recovery_mode"] is True
    assert out["attempts_multiplier"] <= 1.0
    assert out["ttl_multiplier"] < 1.0

