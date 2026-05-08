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
    monkeypatch.setattr(mod, "_http_json", lambda url, timeout=20.0: {"ok": True, "score": 1.0, "schema": "nomad.machine_contract_conformance.v1", "http_status": 200})
    monkeypatch.setattr(mod, "_base_url", lambda: "https://nomad.example")
    monkeypatch.setenv("NOMAD_NETZE_WERFEN_PROBES", "3")
    monkeypatch.setenv("NOMAD_NONHUMAN_GUARD_REQUIRED", "0")
    out = mod.run_tick()
    assert out["ok"] is True
    assert out["completed"] == 3
    assert out["probe_count"] == 3
    assert calls["n"] == 5
    assert out["nonhuman_guard"]["required"] is False
    assert out["guard_soft_fail"] is False


def test_run_tick_uses_www_only_base_without_alternate_fallback(monkeypatch):
    calls = {"experiment_bases": [], "n": 0}

    def fake_run_json_command(cmd):
        calls["n"] += 1
        joined = " ".join(cmd)
        if "recruitment_experiment_runner.py" in joined:
            base = cmd[cmd.index("--base-url") + 1]
            calls["experiment_bases"].append(base)
            return {"exit_code": 0, "events": [{"ok": True}], "stderr": ""}
        return {"exit_code": 0, "events": [{"ok": True, "phase": "complete"}], "stderr": ""}

    monkeypatch.setattr(mod, "_run_json_command", fake_run_json_command)
    monkeypatch.setattr(mod, "_http_json", lambda url, timeout=20.0: {"ok": True, "score": 1.0, "schema": "nomad.machine_contract_conformance.v1", "http_status": 200})
    monkeypatch.setattr(mod, "_base_url", lambda: "https://www.syndiode.com")
    monkeypatch.setenv("NOMAD_NETZE_WERFEN_PROBES", "1")
    monkeypatch.setenv("NOMAD_NONHUMAN_GUARD_REQUIRED", "0")
    out = mod.run_tick()

    assert out["ok"] is True
    assert calls["experiment_bases"] == ["https://www.syndiode.com"]
    assert out["experiment"]["fallback_used"] is False
    assert out["experiment"]["fallback_base_url"] == ""


def test_conformance_snapshot_retries_then_succeeds(monkeypatch):
    seq = {"n": 0}

    def fake_http_json(url, timeout=20.0):
        seq["n"] += 1
        if seq["n"] < 3:
            return {"ok": False, "http_status": 0, "error": "http_unreachable"}
        return {"ok": True, "http_status": 200, "schema": "nomad.machine_contract_conformance.v1", "score": 1.0}

    monkeypatch.setattr(mod, "_http_json", fake_http_json)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)
    out = mod._conformance_snapshot("https://www.syndiode.com")
    assert out["ok"] is True
    assert out["retry_count"] == 2
    assert out["fallback_used"] is False


def test_run_tick_can_require_nonhuman_guard(monkeypatch):
    def fake_run_json_command(cmd):
        joined = " ".join(cmd)
        if "nonhuman_dev_guard.py" in joined:
            return {"exit_code": 1, "events": [{"ok": False, "schema": "nomad.nonhuman_dev_guard.v1"}], "stderr": ""}
        if "recruitment_experiment_runner.py" in joined:
            return {"exit_code": 0, "events": [{"ok": True}], "stderr": ""}
        return {"exit_code": 0, "events": [{"ok": True, "phase": "complete"}], "stderr": ""}

    monkeypatch.setattr(mod, "_run_json_command", fake_run_json_command)
    monkeypatch.setattr(mod, "_http_json", lambda url, timeout=20.0: {"ok": True, "score": 1.0, "schema": "nomad.machine_contract_conformance.v1", "http_status": 200})
    monkeypatch.setattr(mod, "_base_url", lambda: "https://nomad.example")
    monkeypatch.setenv("NOMAD_NETZE_WERFEN_PROBES", "1")
    monkeypatch.setenv("NOMAD_NONHUMAN_GUARD_REQUIRED", "1")
    out = mod.run_tick()
    assert out["completed"] == 1
    assert out["nonhuman_guard"]["required"] is True
    assert out["ok"] is False


def test_run_tick_uses_contract_conformance_fallback_path(monkeypatch):
    def fake_run_json_command(cmd):
        joined = " ".join(cmd)
        if "recruitment_experiment_runner.py" in joined:
            return {"exit_code": 0, "events": [{"ok": True}], "stderr": ""}
        return {"exit_code": 0, "events": [{"ok": True, "phase": "complete"}], "stderr": ""}

    calls = {"n": 0}

    def fake_http_json(url, timeout=20.0):
        calls["n"] += 1
        if url.endswith("/.well-known/nomad-contract-conformance.json"):
            return {"ok": False, "http_status": 404}
        return {"ok": True, "schema": "nomad.machine_contract_conformance.v1", "score": 0.91, "http_status": 200}

    monkeypatch.setattr(mod, "_run_json_command", fake_run_json_command)
    monkeypatch.setattr(mod, "_http_json", fake_http_json)
    monkeypatch.setattr(mod, "_base_url", lambda: "https://nomad.example")
    monkeypatch.setenv("NOMAD_NETZE_WERFEN_PROBES", "1")
    out = mod.run_tick()
    assert out["ok"] is True
    assert out["contract_conformance"]["fallback_used"] is True
    assert out["contract_conformance"]["fallback_path"] == "/contract-conformance"
    assert calls["n"] >= 2

