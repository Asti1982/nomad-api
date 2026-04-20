from render_hosting import RenderHostingProbe


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.ok = 200 <= status_code < 300
        self.text = str(self._payload)

    def json(self):
        return self._payload


def test_render_probe_defaults_to_locked_public_api_lane(monkeypatch, tmp_path):
    monkeypatch.setenv("RENDER_API_KEY", "")
    monkeypatch.setenv("NOMAD_RENDER_DOMAIN", "api.syndiode.com")

    result = RenderHostingProbe(repo_root=tmp_path).snapshot()

    assert result["provider"] == "Render"
    assert result["role"] == "public_api_hosting"
    assert result["api_key_configured"] is False
    assert result["desired_domain"] == "api.syndiode.com"
    assert "RENDER_API_KEY" in result["next_action"]


def test_render_probe_verifies_services_and_selects_nomad_api(monkeypatch, tmp_path):
    monkeypatch.setenv("RENDER_API_KEY", "rnd-not-a-real-token")
    monkeypatch.setenv("NOMAD_RENDER_SERVICE_NAME", "nomad-api")
    monkeypatch.setenv("NOMAD_RENDER_OWNER_ID", "tea-test")

    def fake_request(method, url, **kwargs):
        assert method == "GET"
        assert kwargs["headers"]["Authorization"] == "Bearer rnd-not-a-real-token"
        if url.endswith("/owners"):
            return FakeResponse(
                payload=[
                    {
                        "owner": {
                            "id": "tea-test",
                            "name": "Test Workspace",
                            "type": "team",
                        }
                    }
                ]
            )
        assert url.endswith("/services")
        return FakeResponse(
            payload=[
                {
                    "service": {
                        "id": "srv-test",
                        "name": "nomad-api",
                        "type": "web_service",
                        "runtime": "python",
                        "url": "https://nomad-api.onrender.com",
                    }
                }
            ]
        )

    monkeypatch.setattr("render_hosting.requests.request", fake_request)

    result = RenderHostingProbe(repo_root=tmp_path).snapshot(verify=True)

    assert result["configured"] is True
    assert result["verification"]["ok"] is True
    assert result["verification"]["selected_service"]["id"] == "srv-test"
    assert result["owners"]["selected_owner"]["id"] == "tea-test"
    assert result["service_url"] == "https://nomad-api.onrender.com"


def test_render_deploy_requires_explicit_approval(monkeypatch, tmp_path):
    monkeypatch.setenv("RENDER_API_KEY", "rnd-not-a-real-token")
    monkeypatch.setenv("NOMAD_RENDER_SERVICE_ID", "srv-test")

    result = RenderHostingProbe(repo_root=tmp_path).trigger_deploy()

    assert result["ok"] is False
    assert result["issue"] == "render_deploy_approval_required"
