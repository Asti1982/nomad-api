from agent_attractor import NomadAgentAttractor
from agent_engagement import AgentEngagementLedger
from agent_service import AgentServiceDesk


class FakeTreasury:
    def get_wallet_summary(self):
        return {
            "address": "0x" + "1" * 40,
            "configured": True,
            "native_balance": None,
        }


def test_agent_attractor_manifest_surfaces_roles_offer_and_broadcast(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    product_store = tmp_path / "products.json"
    product_store.write_text(
        (
            "{\n"
            '  "products": {\n'
            '    "prod-top": {\n'
            '      "product_id": "prod-top",\n'
            '      "name": "Nomad Compute Unlock Pack: Provider Fallback Ladder",\n'
            '      "pain_type": "compute_auth",\n'
            '      "status": "offer_ready",\n'
            '      "priority_score": 203.0,\n'
            '      "priority_reason": "Repeated compute_auth pattern with 3 hits.",\n'
            '      "variant_sku": "nomad.compute_unlock_pack.provider-fallback-ladder",\n'
            '      "free_value": {"reply_contract": {"accept": "PLAN_ACCEPTED=true plus FACT_URL or ERROR"}},\n'
            '      "paid_offer": {"price_native": 0.03, "delivery": "bounded unblock", "trigger": "PLAN_ACCEPTED=true plus FACT_URL or ERROR"},\n'
            '      "service_template": {"endpoint": "POST /tasks"}\n'
            "    }\n"
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    desk = AgentServiceDesk(
        path=tmp_path / "tasks.json",
        treasury=FakeTreasury(),
        product_store_path=product_store,
    )
    engagements = AgentEngagementLedger(path=tmp_path / "engagements.json")
    engagements.record_inbound(
        session_id="eng-1",
        requester_agent="VerifierBot",
        requester_endpoint="https://verifier.example/a2a/message",
        message="I can help with a verifier and repro artifact.",
        pain_type="compute_auth",
        role_assessment={"role": "peer_solver", "confidence": 0.9, "evidence": ["verifier"], "suggested_path": "request_verifiable_artifact", "outcome_status": "verification_requested", "response_goal": "ask for verifier"},
        best_current_offer=desk.best_current_offer(service_type="compute_auth", requested_amount=0.03),
        source="test",
    )
    attractor = NomadAgentAttractor(service_desk=desk, engagements=engagements)

    result = attractor.manifest(service_type="compute_auth", role_hint="peer_solver", limit=2)

    assert result["mode"] == "nomad_agent_attractor"
    assert result["focus_service_type"] == "compute_auth"
    assert result["top_offer"]["headline"] == "Nomad Compute Unlock Pack: Provider Fallback Ladder"
    assert result["target_roles"] == ["peer_solver"]
    assert result["entrypoints"]["agent_attractor"] == "https://nomad.example/agent-attractor"
    assert result["entrypoints"]["swarm_coordinate"] == "https://nomad.example/swarm/coordinate"
    assert result["entrypoints"]["swarm_accumulate"] == "https://nomad.example/swarm/accumulate"
    assert result["market_pull"]["engagement_summary"]["roles"]["peer_solver"] == 1
    assert "nomad.agent_attractor.v1" in result["broadcast"]["message"]
    assert "swarm_coordinate=https://nomad.example/swarm/coordinate" in result["broadcast"]["message"]
    assert "swarm_accumulate=https://nomad.example/swarm/accumulate" in result["broadcast"]["message"]
    assert "peer_solver_contract=artifact_url|diff|verifier|error_trace" in result["broadcast"]["message"]
