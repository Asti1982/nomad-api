from codex_peer_agent import CodexPeerAgent


def test_codex_peer_agent_payloads_are_agent_facing():
    peer = CodexPeerAgent()
    join = peer.join_payload(base_url="https://example.test/nomad", problem="Need paid compute leads.")
    development = peer.development_payload(base_url="https://example.test/nomad", problem="Work lead blockers.")

    assert join["agent_id"] == "codex.peer.agent"
    assert join["preferred_role"] == "peer_solver"
    assert "lead_workbench" in join["capabilities"]
    assert "no_unapproved_spend" in join["constraints"]
    assert development["pain_type"] == "paid_blocker_solution"
    assert development["public_node_url"].startswith("https://example.test/nomad/")


def test_codex_peer_agent_collaborates_with_nomad_only_over_http_without_spend():
    peer = CodexPeerAgent()

    result = peer.collaborate_with_local_api(
        problem="Prove the peer can join and request a useful development plan.",
        work_leads=False,
        lead_limit=1,
    )

    assert result["mode"] == "codex_peer_agent"
    assert result["ok"] is True
    assert result["http_only"] is True
    assert result["transport"] == "http"
    assert result["join_receipt"]["accepted"] is True
    assert result["development_response"]["exchange_id"]
    assert result["lead_workbench"]["worked_count"] == 0
    assert "real HTTP API collaboration loop" in result["analysis"]


def test_codex_peer_worker_runs_bounded_http_loop_without_spend():
    peer = CodexPeerAgent()

    result = peer.run_http_loop(
        mode="local-api",
        cycles=1,
        interval_seconds=0,
        work_leads=False,
        lead_limit=1,
        growth_pass=True,
        activation_pass=True,
        activation_limit=1,
        send_agent_invites=False,
    )

    assert result["mode"] == "codex_peer_worker"
    assert result["ok"] is True
    assert result["http_only"] is True
    assert result["transport"] == "http"
    assert result["cycles_completed"] == 1
    assert result["worked_leads"] == 0
    assert result["growth_pass_enabled"] is True
    assert "latest_prospect_agents" in result
    assert "latest_queued_agent_invites" in result
    assert result["results"][0]["growth"]["schema"] == "nomad.codex_peer_growth_pass.v1"
    assert result["results"][0]["growth"]["raw"]["activation"]["send_enabled"] is False
    assert result["results"][0]["join_receipt"]["accepted"] is True


def test_activation_limit_zero_selects_full_queue_without_sending():
    peer = CodexPeerAgent()

    result = peer.activate_agent_prospects_over_http(
        base_url="http://127.0.0.1:1",
        prospects=[
            {"agent_id": "a", "endpoint_url": "https://agent-a.example/a2a/message"},
            {"agent_id": "b", "endpoint_url": "https://agent-b.example/a2a/message"},
        ],
        limit=0,
        send=False,
        timeout=0.01,
    )

    assert result["limit"] == 0
    assert result["selected_count"] == 2
    assert result["send_enabled"] is False
