from compute_probe import LocalComputeProbe
from nomad_health import LaneCooldownManager
from self_improvement import HostedBrainRouter


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self.ok = 200 <= status_code < 400

    def json(self):
        return self._payload


def test_github_models_probe_diagnoses_missing_models_read(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "secret-test-token")
    monkeypatch.setenv("NOMAD_GITHUB_MODELS_API_VERSION", "2026-03-10")
    monkeypatch.setenv("NOMAD_GITHUB_MODEL", "openai/gpt-4.1-mini")

    def fake_get(*args, **kwargs):
        return FakeResponse(200, payload=[{"id": "openai/gpt-4.1-mini"}])

    def fake_post(*args, **kwargs):
        return FakeResponse(403, text='{"message":"Forbidden"}')

    monkeypatch.setattr("compute_probe.requests.get", fake_get)
    monkeypatch.setattr("compute_probe.requests.post", fake_post)

    result = LocalComputeProbe(
        health=LaneCooldownManager(tmp_path / "lane-health.json")
    )._github_models_info()

    assert result["available"] is False
    assert result["issue"] == "github_models_auth_or_permission"
    assert result["required_permission"] == "models: read"
    assert result["base_url"] == "https://models.github.ai/inference"
    assert "Models: Read" in result["next_action"]
    assert "secret-test-token" not in str(result)


def test_github_models_probe_falls_back_to_working_model_candidate(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "secret-test-token")
    monkeypatch.setenv("NOMAD_GITHUB_MODELS_API_VERSION", "2026-03-10")
    monkeypatch.setenv("NOMAD_GITHUB_MODEL", "unknown/model")
    monkeypatch.delenv("NOMAD_GITHUB_MODEL_CANDIDATES", raising=False)

    def fake_get(*args, **kwargs):
        return FakeResponse(200, payload=[{"id": "openai/gpt-4.1-mini"}])

    def fake_post(*args, **kwargs):
        model = kwargs["json"]["model"]
        if model == "unknown/model":
            return FakeResponse(404, text='{"message":"model not found"}')
        return FakeResponse(200, payload={"choices": [{"message": {"content": "OK"}}]})

    monkeypatch.setattr("compute_probe.requests.get", fake_get)
    monkeypatch.setattr("compute_probe.requests.post", fake_post)

    result = LocalComputeProbe(
        health=LaneCooldownManager(tmp_path / "lane-health.json")
    )._github_models_info()

    assert result["available"] is True
    assert result["working_model"] == "openai/gpt-4.1-mini"
    assert result["next_action"] == "Set NOMAD_GITHUB_MODEL=openai/gpt-4.1-mini."
    assert result["attempts"][0]["model"] == "unknown/model"


def test_hosted_brain_router_returns_github_models_healing_hint(monkeypatch):
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "secret-test-token")
    monkeypatch.setenv("NOMAD_GITHUB_MODELS_API_VERSION", "2026-03-10")
    monkeypatch.setenv("NOMAD_OLLAMA_AUTO_SELECT_SELF_IMPROVE_MODEL", "false")

    def fake_post(*args, **kwargs):
        return FakeResponse(403, text='{"message":"Forbidden"}')

    monkeypatch.setattr("self_improvement.requests.post", fake_post)

    router = HostedBrainRouter()
    result = router._github_review([{"role": "user", "content": "review Nomad"}])

    assert result["ok"] is False
    assert result["issue"] == "github_models_auth_or_permission"
    assert result["required_permission"] == "models: read"
    assert "Models: Read" in result["next_action"]
    assert "secret-test-token" not in str(result)


def test_xai_grok_probe_reports_missing_key_without_leaking_env(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "")
    monkeypatch.setenv("NOMAD_XAI_MODEL", "grok-4.20-reasoning")

    result = LocalComputeProbe()._xai_grok_info()

    assert result["available"] is False
    assert result["issue"] == "xai_grok_missing_token"
    assert result["base_url"] == "https://api.x.ai/v1"
    assert result["token_env_var"] == "XAI_API_KEY"


def test_xai_grok_probe_falls_back_to_working_model_candidate(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-secret-test-token")
    monkeypatch.setenv("NOMAD_XAI_MODEL", "unknown-grok-model")
    monkeypatch.delenv("NOMAD_XAI_MODEL_CANDIDATES", raising=False)

    def fake_post(*args, **kwargs):
        model = kwargs["json"]["model"]
        if model == "unknown-grok-model":
            return FakeResponse(404, text='{"message":"model not found"}')
        return FakeResponse(200, payload={"choices": [{"message": {"content": "OK"}}]})

    monkeypatch.setattr("compute_probe.requests.post", fake_post)

    result = LocalComputeProbe()._xai_grok_info()

    assert result["available"] is True
    assert result["working_model"] == "grok-4.20-reasoning"
    assert result["next_action"] == "Set NOMAD_XAI_MODEL=grok-4.20-reasoning."
    assert result["attempts"][0]["model"] == "unknown-grok-model"
    assert "xai-secret-test-token" not in str(result)


def test_hosted_brain_router_uses_xai_grok_review(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xai-secret-test-token")
    monkeypatch.setenv("NOMAD_XAI_MODEL", "grok-4.20-reasoning")
    monkeypatch.setenv("NOMAD_HOSTED_BRAIN_MODE", "always")
    monkeypatch.setenv("NOMAD_OLLAMA_AUTO_SELECT_SELF_IMPROVE_MODEL", "false")

    def fake_post(*args, **kwargs):
        return FakeResponse(
            200,
            payload={"choices": [{"message": {"content": "Diagnosis: ok\nAction1: ship\nAction2: test\nQuery: scout"}}]},
        )

    monkeypatch.setattr("self_improvement.requests.post", fake_post)

    router = HostedBrainRouter()
    result = router._xai_grok_review([{"role": "user", "content": "review Nomad"}])

    assert result["ok"] is True
    assert result["provider"] == "xai_grok"
    assert result["working_model"] == "grok-4.20-reasoning"
    assert "xai-secret-test-token" not in str(result)
