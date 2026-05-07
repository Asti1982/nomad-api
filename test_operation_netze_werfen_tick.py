import operation_netze_werfen_tick as mod


def test_probe_caps_rotates_known_shapes():
    a = mod._probe_caps(0)
    b = mod._probe_caps(1)
    c = mod._probe_caps(2)
    assert "objective_lease_execution" in a
    assert "endpoint_probe" in b
    assert "pattern_deduplication" in c


def test_run_tick_reports_success_when_commands_complete(monkeypatch):
    calls = {"n": 0}

    def fake_run_json_command(cmd):
        calls["n"] += 1
        if "recruitment_experiment_runner.py" in " ".join(cmd):
            return {"exit_code": 0, "events": [{"ok": True, "schema": "nomad.recruitment_experiment_result.v1"}], "stderr": ""}
        return {"exit_code": 0, "events": [{"ok": True, "phase": "complete"}], "stderr": ""}

    monkeypatch.setattr(mod, "_run_json_command", fake_run_json_command)
    monkeypatch.setattr(mod, "_base_url", lambda: "https://nomad.example")
    monkeypatch.setenv("NOMAD_NETZE_WERFEN_PROBES", "3")
    out = mod.run_tick()
    assert out["ok"] is True
    assert out["completed"] == 3
    assert out["probe_count"] == 3
    assert calls["n"] == 4

