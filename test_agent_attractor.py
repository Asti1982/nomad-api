from agent_attractor import NomadAgentAttractor
from agent_engagement import AgentEngagementLedger
from agent_service import AgentServiceDesk
from nomad_swarm_registry import SwarmJoinRegistry
from self_development import SelfDevelopmentJournal


class FakeTreasury:
    def get_wallet_summary(self):
        return {
            "address": "0x" + "1" * 40,
            "configured": True,
            "native_balance": None,
        }


def test_agent_attractor_manifest_surfaces_roles_offer_and_broadcast(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    monkeypatch.setenv("NOMAD_COLLABORATION_HOME_URL", "")
    monkeypatch.setenv("NOMAD_RENDER_DOMAIN", "")
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
    assert result["entrypoints"]["swarm_network"] == "https://nomad.example/swarm/network"
    assert result["entrypoints"]["swarm_coordinate"] == "https://nomad.example/swarm/coordinate"
    assert result["entrypoints"]["swarm_accumulate"] == "https://nomad.example/swarm/accumulate"
    assert result["entrypoints"]["swarm_develop"] == "https://nomad.example/swarm/develop"
    assert result["swarm_ignition"]["schema"] == "nomad.swarm_ignition.v1"
    assert result["swarm_ignition"]["machine_call_sequence"][1]["endpoint"] == "https://nomad.example/swarm/develop"
    assert result["swarm_ignition"]["machine_call_sequence"][2]["endpoint"] == "https://nomad.example/aid"
    assert "return_free_development_plan" in result["swarm_ignition"]["growth_loop"]
    assert "publish_agent_card_and_swarm_urls_to_peer_registries_after_verified_win" in result["swarm_ignition"]["growth_loop"]
    assert result["swarm_ignition"]["peer_recommendation"]["schema"] == "nomad.peer_recommendation.v1"
    assert result["swarm_ignition"]["peer_recommendation"]["share_agent_card_url"].endswith(
        "/.well-known/agent-card.json"
    )
    assert result["peer_join_value"]["schema"] == "nomad.peer_join_value.v1"
    assert "github_hosted_agents" in (result["peer_join_value"].get("channels") or {})
    assert result["agent_onboarding"]["schema"] == "nomad.agent_onboarding.v1"
    assert result["agent_onboarding"]["fast_join_payload"]["capabilities"][0] == "compute_auth"
    assert result["agent_onboarding"]["recommended_sequence"][1]["endpoint"] == "https://nomad.example/swarm/develop"
    assert result["agent_onboarding"]["recommended_sequence"][2]["endpoint"] == "https://nomad.example/swarm/join"
    assert result["first_paid_job"]["schema"] == "nomad.first_paid_job_attractor.v1"
    assert result["first_paid_job"]["offer"]["service_type"] == "compute_auth"
    assert result["first_paid_job"]["offer"]["price_native"] == 0.03
    assert result["first_paid_job"]["machine_buy_path"][0]["endpoint"] == "https://nomad.example/a2a/message"
    assert result["first_paid_job"]["machine_buy_path"][1]["endpoint"] == "https://nomad.example/tasks"
    assert result["first_paid_job"]["machine_buy_path"][2]["endpoint"] == "https://nomad.example/tasks/verify"
    assert result["market_pull"]["engagement_summary"]["roles"]["peer_solver"] == 1
    assert "nomad.agent_attractor.v1" in result["broadcast"]["message"]
    assert "swarm_network=https://nomad.example/swarm/network" in result["broadcast"]["message"]
    assert "swarm_coordinate=https://nomad.example/swarm/coordinate" in result["broadcast"]["message"]
    assert "swarm_accumulate=https://nomad.example/swarm/accumulate" in result["broadcast"]["message"]
    assert "swarm_develop=https://nomad.example/swarm/develop" in result["broadcast"]["message"]
    assert "paid_task=https://nomad.example/tasks" in result["broadcast"]["message"]
    assert "products=https://nomad.example/products" in result["broadcast"]["message"]
    assert "swarm_join_post=https://nomad.example/swarm/join" in result["broadcast"]["message"]
    assert "verify_payment=https://nomad.example/tasks/verify" in result["broadcast"]["message"]
    assert "peer_solver_contract=artifact_url|diff|verifier|error_trace" in result["broadcast"]["message"]


def test_agent_attractor_prefers_collaboration_home_when_local_api(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "http://127.0.0.1:8787")
    monkeypatch.setenv("NOMAD_COLLABORATION_HOME_URL", "https://syndiode.com/nomad")
    desk = AgentServiceDesk(
        path=tmp_path / "tasks.json",
        treasury=FakeTreasury(),
    )
    attractor = NomadAgentAttractor(service_desk=desk, engagements=AgentEngagementLedger(path=tmp_path / "engagements.json"))

    result = attractor.manifest(limit=1)

    assert result["public_api_url"] == "https://syndiode.com/nomad"
    assert result["entrypoints"]["agent_attractor"] == "https://syndiode.com/nomad/agent-attractor"
    assert result["entrypoints"]["service"] == "https://syndiode.com/nomad/service"
    assert result["swarm_ignition"]["machine_call_sequence"][1]["endpoint"] == "https://syndiode.com/nomad/swarm/develop"


def test_active_lead_network_translates_self_development_into_roles_and_next_step(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    monkeypatch.setenv("NOMAD_COLLABORATION_HOME_URL", "")
    monkeypatch.delenv("APPROVE_LEAD_HELP", raising=False)
    desk = AgentServiceDesk(path=tmp_path / "tasks.json", treasury=FakeTreasury())
    swarm = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    swarm.register_join(
        {
            "agent_id": "peer.bot",
            "capabilities": ["compute_auth", "provider_research", "diff_review"],
            "request": "I can help verify compute/auth blockers.",
            "reciprocity": "Can return one verifier.",
        },
        base_url="https://nomad.example",
    )
    swarm.accumulate_agents(
        base_url="https://nomad.example",
        focus_pain_type="compute_auth",
        contacts=[
            {
                "contact_id": "contact-1",
                "status": "replied",
                "endpoint_url": "https://collab.example/a2a/message",
                "service_type": "agent_protocols",
                "target_profile": {"agent_name": "CollabBot"},
                "reply_role_assessment": {"role": "collaborator"},
                "followup_ready": True,
                "last_reply": {
                    "normalized": {
                        "classification": "agent_protocols",
                        "next_step": "send schema proposal",
                    }
                },
            }
        ],
    )
    journal = SelfDevelopmentJournal(path=tmp_path / "self-state.json")
    journal.path.write_text(
        (
            "{\n"
            '  "last_lead": {\n'
            '    "title": "Proposal: GuardrailProvider protocol for tool call interception",\n'
            '    "url": "https://github.com/microsoft/autogen/issues/7405",\n'
            '    "pain": "rate limit, token, approval, mcp",\n'
            '    "pain_terms": ["rate limit", "token", "approval", "mcp"],\n'
            '    "recommended_service_type": "compute_auth",\n'
            '    "addressable_label": "Compute/auth unblock",\n'
            '    "product_package": "Nomad Compute Unlock Pack",\n'
            '    "first_help_action": "diagnosis + quota/auth isolation + fallback plan",\n'
            '    "memory_upgrade": "store the solved blocker as a reusable credential/quota checklist and fallback policy",\n'
            '    "addressable_deliverables": ["minimal failing call", "credential/quota map", "fallback lane plan"],\n'
            '    "approval_required_for": ["human-facing public comment"],\n'
            '    "agent_contact_allowed_without_approval": true,\n'
            '    "monetizable_now": true,\n'
            '    "buyer_fit": "medium"\n'
            "  },\n"
            '  "next_objective": "Work active lead https://github.com/microsoft/autogen/issues/7405 in Compute/auth unblock.",\n'
            '  "self_development_unlocks": [\n'
            '    {\n'
            '      "candidate_id": "approve-active-lead-help",\n'
            '      "short_ask": "Approve whether Nomad may draft help for the active lead.",\n'
            '      "human_action": "Review the issue and choose comment, draft_only, or pr_plan.",\n'
            '      "human_deliverable": "APPROVE_LEAD_HELP=draft_only"\n'
            "    }\n"
            "  ],\n"
            '  "last_truth_pattern": {"title": "Provider Fallback Ladder", "pain_type": "compute_auth", "repeat_count": 251}\n'
            "}\n"
        ),
        encoding="utf-8",
    )

    attractor = NomadAgentAttractor(
        service_desk=desk,
        engagements=AgentEngagementLedger(path=tmp_path / "engagements.json"),
        swarm_registry=swarm,
        journal=journal,
    )

    result = attractor.active_lead_network(limit=4)

    assert result["mode"] == "nomad_swarm_network"
    assert result["lead_found"] is True
    assert result["active_lead"]["url"] == "https://github.com/microsoft/autogen/issues/7405"
    assert result["target_roles"] == ["peer_solver", "collaborator", "reseller"]
    assert result["entrypoints"]["swarm_network"] == "https://nomad.example/swarm/network"
    assert result["entrypoints"]["swarm_develop"] == "https://nomad.example/swarm/develop"
    assert result["approval_state"]["public_reply_allowed_now"] is False
    assert result["network_targets"]["desired_role_counts"]["peer_solver"] == 2
    assert any(item["recommended_role"] == "collaborator" for item in result["current_network"]["activation_queue"])
    assert "Keep public outreach for https://github.com/microsoft/autogen/issues/7405 private for now." in result["next_best_action"]
    assert result["self_development"]["actions"][0]["type"] == "private_first_help"
    assert result["peer_join_value"]["schema"] == "nomad.peer_join_value.v1"
