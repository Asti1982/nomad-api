from render_hosting import RenderHostingProbe, parse_render_yaml_first_web_service_commands


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.ok = 200 <= status_code < 300
        self.text = str(self._payload)

    def json(self):
        return self._payload


def test_render_accepts_nomad_prefixed_render_api_key(monkeypatch, tmp_path):
    # Keep RENDER_API_KEY set but empty so load_dotenv() does not repopulate it from a local .env file.
    monkeypatch.setenv("RENDER_API_KEY", "")
    monkeypatch.setenv("NOMAD_RENDER_API_KEY", "rnd-prefixed-fake")
    monkeypatch.setenv("NOMAD_RENDER_SERVICE_NAME", "nomad-api")
    monkeypatch.setenv("NOMAD_RENDER_OWNER_ID", "tea-test")

    def fake_request(method, url, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer rnd-prefixed-fake"
        if url.endswith("/owners"):
            return FakeResponse(
                payload=[{"owner": {"id": "tea-test", "name": "Test Workspace", "type": "team"}}]
            )
        if "/deploys" in url:
            return FakeResponse(payload=[])
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
    monkeypatch.setattr(
        "render_hosting.requests.get",
        lambda url, **kwargs: FakeResponse(status_code=200, payload={"ok": True}),
    )

    result = RenderHostingProbe(repo_root=tmp_path).snapshot(verify=True)
    assert result["configured"] is True
    assert result["verification"]["selected_service"]["id"] == "srv-test"
    assert (result.get("recent_deploys") or {}).get("ok") is True
    assert (result.get("recent_deploys") or {}).get("deploys") == []


def test_render_probe_defaults_to_locked_public_api_lane(monkeypatch, tmp_path):
    monkeypatch.setenv("RENDER_API_KEY", "")
    monkeypatch.setenv("NOMAD_RENDER_DOMAIN", "onrender.syndiode.com")
    monkeypatch.delenv("NOMAD_GITHUB_DEPLOY_BRANCH", raising=False)

    result = RenderHostingProbe(repo_root=tmp_path).snapshot()

    assert result["provider"] == "Render"
    assert result["role"] == "public_api_hosting"
    assert result["api_key_configured"] is False
    assert result["desired_domain"] == "onrender.syndiode.com"
    assert result["desired_branch"] == "syndiode"
    assert "RENDER_API_KEY" in result["next_action"]


def test_render_probe_verifies_services_and_selects_nomad_api(monkeypatch, tmp_path):
    monkeypatch.setenv("RENDER_API_KEY", "rnd-not-a-real-token")
    monkeypatch.setenv("NOMAD_RENDER_SERVICE_NAME", "nomad-api")
    monkeypatch.setenv("NOMAD_RENDER_OWNER_ID", "tea-test")
    monkeypatch.setenv("NOMAD_GITHUB_REPOSITORY", "Asti1982/syndiode")
    monkeypatch.setenv("NOMAD_GITHUB_DEPLOY_BRANCH", "syndiode")

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
        if "/deploys" in url:
            return FakeResponse(
                payload=[
                    {
                        "deploy": {
                            "id": "dep-1",
                            "status": "live",
                            "createdAt": "2026-05-03T12:00:00Z",
                            "updatedAt": "2026-05-03T12:01:00Z",
                            "commit": {"id": "abc123"},
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
    monkeypatch.setattr(
        "render_hosting.requests.get",
        lambda url, **kwargs: FakeResponse(status_code=200, payload={"ok": True}),
    )

    result = RenderHostingProbe(repo_root=tmp_path).snapshot(verify=True)

    assert result["configured"] is True
    assert result["public_checks"]["ok"] is True
    assert result["verification"]["ok"] is True
    assert result["verification"]["selected_service"]["id"] == "srv-test"
    assert result["owners"]["selected_owner"]["id"] == "tea-test"
    assert result["github_repository"] == "Asti1982/syndiode"
    assert result["desired_branch"] == "syndiode"
    assert result["service_url"] == "https://nomad-api.onrender.com"
    deploys = result.get("recent_deploys") or {}
    assert deploys.get("ok") is True
    assert deploys.get("deploys")[0]["id"] == "dep-1"
    assert deploys.get("deploys")[0]["commit_id"] == "abc123"


def test_render_probe_public_checks_work_without_api_key(monkeypatch, tmp_path):
    monkeypatch.setenv("RENDER_API_KEY", "")
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad-api.onrender.com")

    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return FakeResponse(status_code=200, payload={"ok": True})

    monkeypatch.setattr("render_hosting.requests.get", fake_get)

    result = RenderHostingProbe(repo_root=tmp_path).snapshot(verify=True)

    assert result["api_key_configured"] is False
    assert result["public_checks"]["ok"] is True
    assert result["public_checks"]["swarm_ready"] is True
    assert result["public_checks"]["accumulation_ready"] is True
    assert calls[0] == "https://nomad-api.onrender.com/health"


def test_list_recent_logs_hits_render_api(monkeypatch, tmp_path):
    monkeypatch.setenv("RENDER_API_KEY", "rnd-x")
    monkeypatch.setenv("NOMAD_RENDER_OWNER_ID", "tea-1")
    monkeypatch.setenv("NOMAD_RENDER_SERVICE_ID", "srv-1")

    def fake_request(method, url, **kwargs):
        assert method == "GET"
        assert "/logs" in url
        assert kwargs.get("params")
        return FakeResponse(
            payload={
                "logs": [
                    {
                        "timestamp": "2026-05-03T10:00:00Z",
                        "level": "error",
                        "type": "app",
                        "message": "Exited with status 2",
                    }
                ]
            }
        )

    monkeypatch.setattr("render_hosting.requests.request", fake_request)
    out = RenderHostingProbe(repo_root=tmp_path).list_recent_logs(limit=5)
    assert out["ok"] is True
    assert out["lines"][0]["message"] == "Exited with status 2"


def test_list_recent_deploys_requires_service_id(monkeypatch, tmp_path):
    monkeypatch.setenv("RENDER_API_KEY", "rnd-x")
    out = RenderHostingProbe(repo_root=tmp_path).list_recent_deploys(service_id="", limit=3)
    assert out["ok"] is False
    assert out["issue"] == "render_service_id_missing"


def test_render_deploy_requires_explicit_approval(monkeypatch, tmp_path):
    monkeypatch.setenv("RENDER_API_KEY", "rnd-not-a-real-token")
    monkeypatch.setenv("NOMAD_RENDER_SERVICE_ID", "srv-test")

    result = RenderHostingProbe(repo_root=tmp_path).trigger_deploy()

    assert result["ok"] is False
    assert result["issue"] == "render_deploy_approval_required"


def test_parse_render_yaml_first_web_service_commands(tmp_path):
    yaml_path = tmp_path / "render.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "services:",
                "  - type: redis",
                "    name: cache",
                "  - type: web",
                "    name: api",
                "    buildCommand: pip install -r requirements.txt",
                "    startCommand: python app.py",
                "    healthCheckPath: /health",
            ]
        ),
        encoding="utf-8",
    )
    out = parse_render_yaml_first_web_service_commands(yaml_path)
    assert out["ok"] is True
    assert out["buildCommand"] == "pip install -r requirements.txt"
    assert out["startCommand"] == "python app.py"


def test_sync_service_commands_patches_render_api(monkeypatch, tmp_path):
    yaml_path = tmp_path / "render.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                "services:",
                "  - type: web",
                "    buildCommand: pip install -r requirements.txt",
                "    startCommand: python app.py",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RENDER_API_KEY", "rnd-x")
    monkeypatch.setenv("NOMAD_RENDER_SERVICE_ID", "srv-abc")

    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs.get("json")))
        assert method == "PATCH"
        assert url.endswith("/services/srv-abc")
        assert kwargs.get("json") == {
            "serviceDetails": {
                "buildCommand": "pip install -r requirements.txt",
                "startCommand": "python app.py",
            }
        }
        return FakeResponse(
            payload={
                "service": {
                    "id": "srv-abc",
                    "name": "nomad-api",
                    "type": "web_service",
                    "url": "https://x.onrender.com",
                }
            }
        )

    monkeypatch.setattr("render_hosting.requests.request", fake_request)
    out = RenderHostingProbe(repo_root=tmp_path).sync_service_commands_from_render_yaml(
        approval="sync_commands"
    )
    assert out["ok"] is True
    assert out["service_id"] == "srv-abc"
    assert len(calls) == 1


def test_sync_service_commands_requires_approval(monkeypatch, tmp_path):
    yaml_path = tmp_path / "render.yaml"
    yaml_path.write_text(
        "services:\n  - type: web\n    buildCommand: a\n    startCommand: b\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RENDER_API_KEY", "rnd-x")
    monkeypatch.setenv("NOMAD_RENDER_SERVICE_ID", "srv-abc")
    out = RenderHostingProbe(repo_root=tmp_path).sync_service_commands_from_render_yaml(approval="")
    assert out["ok"] is False
    assert out["issue"] == "render_sync_commands_approval_required"
