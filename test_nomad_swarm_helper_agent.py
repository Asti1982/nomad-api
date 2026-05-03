from nomad_swarm_helper_agent import run_swarm_helper_pass


class _FakeResp:
    def __init__(self, status: int = 200, data: dict | None = None) -> None:
        self.ok = status < 400
        self.status_code = status
        self.text = "{}"

    def json(self) -> dict:
        return {"ok": True, "mode": "stub"}


def test_swarm_helper_dry_run_no_posts(monkeypatch):
    posts: list[tuple[str, dict]] = []

    def fake_get(self, url, timeout=10, **kwargs):
        return _FakeResp()

    def fake_post(self, url, json=None, headers=None, timeout=10, **kwargs):
        posts.append((url, dict(json or {})))
        return _FakeResp(202, {})

    monkeypatch.setattr("nomad_swarm_helper_agent.requests.Session.get", fake_get)
    monkeypatch.setattr("nomad_swarm_helper_agent.requests.Session.post", fake_post)

    out = run_swarm_helper_pass(
        base_url="https://example.test/nomad",
        dry_run=True,
        post_join=True,
        post_develop=True,
        timeout=5.0,
        agent_id="test.helper",
    )
    assert out["schema"] == "nomad.swarm_helper_pass.v1"
    assert out["dry_run"] is True
    assert out["swarm_join_post"] is None
    assert out["swarm_develop_post"] is None
    assert posts == []


def test_swarm_helper_posts_when_enabled(monkeypatch):
    posts: list[str] = []

    def fake_get(self, url, timeout=10, **kwargs):
        return _FakeResp()

    def fake_post(self, url, json=None, headers=None, timeout=10, **kwargs):
        posts.append(url)
        return _FakeResp(202, {})

    monkeypatch.setattr("nomad_swarm_helper_agent.requests.Session.get", fake_get)
    monkeypatch.setattr("nomad_swarm_helper_agent.requests.Session.post", fake_post)

    out = run_swarm_helper_pass(
        base_url="https://example.test/nomad",
        dry_run=False,
        post_join=True,
        post_develop=True,
        timeout=5.0,
        agent_id="join.helper",
    )
    assert any("/swarm/join" in u for u in posts)
    assert any("/swarm/develop" in u for u in posts)
    assert out["swarm_join_post"] is not None
    assert out["swarm_develop_post"] is not None
