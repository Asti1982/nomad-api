from nomad_idempotency_agent_map import build_idempotency_agent_map


def test_idempotency_map_contains_join_and_develop():
    out = build_idempotency_agent_map(public_base_hint="https://example/nomad")
    assert out["schema"] == "nomad.idempotency_agent_map.v1"
    paths = {p["path"] for p in out.get("post_surfaces", [])}
    assert "/swarm/join" in paths
    assert "/swarm/develop" in paths
    join = next(p for p in out["post_surfaces"] if p["path"] == "/swarm/join")
    assert join.get("conflict_http_status") == 409
