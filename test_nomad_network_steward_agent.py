from nomad_network_steward_agent import run_network_steward_cycle


def test_steward_single_cycle_no_accumulate(monkeypatch):
    def fake_swarm_pass(**kwargs):
        return {
            "schema": "nomad.swarm_helper_pass.v1",
            "public_base_url": "https://stub/nomad",
            "probe_ok_count": 1,
            "probes": [{"url": "https://stub/nomad/health", "status": 200, "ok": True}],
        }

    def fake_get(session, url, *, timeout):
        return {"ok": True, "status": 200, "url": url, "body": {"stub": True}}

    monkeypatch.setattr("nomad_network_steward_agent.run_swarm_helper_pass", fake_swarm_pass)
    monkeypatch.setattr("nomad_network_steward_agent._get", fake_get)

    out = run_network_steward_cycle(
        base_url="https://stub/nomad",
        timeout=2.0,
        dry_run=True,
        feed_swarm=False,
        peer_glimpse=True,
    )
    assert out["mode"] == "nomad_network_steward_cycle"
    assert out["schema"] == "nomad.network_steward_cycle.v1"
    assert out["void_observer"]["edge_coherence_sha256"]
    assert out["swarm_accumulate_post"] is None
    assert out.get("swarm_join_post") is None
    assert out.get("swarm_develop_post") is None
    assert out["peer_glimpse"]["swarm_ready"]["ok"] is True


def test_steward_posts_accumulate_when_enabled(monkeypatch):
    posts: list[str] = []

    def fake_swarm_pass(**kwargs):
        return {
            "schema": "nomad.swarm_helper_pass.v1",
            "public_base_url": "https://stub/nomad",
            "probe_ok_count": 1,
            "probes": [{"url": "https://stub/nomad/health", "status": 200, "ok": True}],
        }

    def fake_get(session, url, *, timeout):
        return {"ok": True, "status": 200, "url": url, "body": {}}

    def fake_post(session, url, payload, *, timeout, idempotency_key):
        posts.append(url)
        return {"ok": True, "status": 202, "url": url, "body": {"ok": True}}

    monkeypatch.setattr("nomad_network_steward_agent.run_swarm_helper_pass", fake_swarm_pass)
    monkeypatch.setattr("nomad_network_steward_agent._get", fake_get)
    monkeypatch.setattr("nomad_network_steward_agent._post_json", fake_post)

    out = run_network_steward_cycle(
        base_url="https://stub/nomad",
        timeout=2.0,
        dry_run=False,
        feed_swarm=True,
        peer_glimpse=False,
    )
    assert any("/swarm/accumulate" in u for u in posts)
    assert out["swarm_accumulate_post"] is not None


def test_steward_posts_join_and_develop_when_enabled(monkeypatch):
    posts: list[str] = []

    def fake_swarm_pass(**kwargs):
        return {
            "schema": "nomad.swarm_helper_pass.v1",
            "public_base_url": "https://stub/nomad",
            "probe_ok_count": 1,
            "probes": [{"url": "https://stub/nomad/health", "status": 200, "ok": True}],
        }

    def fake_post(session, url, payload, *, timeout, idempotency_key):
        posts.append(url)
        return {"ok": True, "status": 202, "url": url, "body": {"ok": True}}

    monkeypatch.setattr("nomad_network_steward_agent.run_swarm_helper_pass", fake_swarm_pass)
    monkeypatch.setattr("nomad_network_steward_agent._post_json", fake_post)

    out = run_network_steward_cycle(
        base_url="https://stub/nomad",
        timeout=2.0,
        dry_run=False,
        feed_swarm=False,
        peer_glimpse=False,
        post_join=True,
        post_develop=True,
    )
    assert any("/swarm/join" in u for u in posts)
    assert any("/swarm/develop" in u for u in posts)
    assert out["swarm_join_post"] is not None
    assert out["swarm_develop_post"] is not None
