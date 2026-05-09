import nomad_agent_runtime_envelope as env


def test_merge_agent_runtime_attaches_limits_and_next(monkeypatch):
    monkeypatch.delenv("NOMAD_AGENT_RUNTIME_ENVELOPE", raising=False)
    out = env.merge_agent_runtime(
        {"ok": True, "schema": "nomad.test.v1"},
        base_url="https://nomad.example",
        path="/swarm/economics",
        http_status=200,
    )
    assert out["agent_runtime"]["schema"] == "nomad.agent_runtime.v1"
    assert out["agent_runtime"]["limits"]["schema"] == "nomad.agent_limits.v1"
    assert isinstance(out["agent_runtime"]["next"], list)
    assert any(step.get("url", "").endswith("/swarm/recruitment-funnel-report") for step in out["agent_runtime"]["next"])


def test_openapi_paths_skip_envelope(monkeypatch):
    body = {"openapi": "3.0.3"}
    assert env.merge_agent_runtime(body, base_url="https://x", path="/openapi.json", http_status=200) == body


def test_env_disables_envelope(monkeypatch):
    monkeypatch.setenv("NOMAD_AGENT_RUNTIME_ENVELOPE", "false")
    body = {"ok": True}
    assert "agent_runtime" not in env.merge_agent_runtime(body, base_url="https://x", path="/swarm", http_status=200)


def test_error_next_graph_uses_recovery(monkeypatch):
    monkeypatch.delenv("NOMAD_AGENT_RUNTIME_ENVELOPE", raising=False)
    out = env.merge_agent_runtime(
        {"ok": False, "error": "x"},
        base_url="https://nomad.example",
        path="/swarm/join",
        http_status=400,
    )
    urls = [s.get("url", "") for s in out["agent_runtime"]["next"]]
    assert any("/openapi.json" in u for u in urls)
