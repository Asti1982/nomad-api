from workflow import ArbiterAgent
from infra_scout import InfrastructureScout


def assert_concrete_unlock(request):
    assert request.get("human_action")
    assert request.get("human_deliverable")
    assert request.get("success_criteria")
    assert request.get("example_response")
    contract = request.get("human_unlock_contract")
    assert contract
    assert contract["do_now"] == request["human_action"]
    assert contract["send_back"] == request["human_deliverable"]


def test_github_personal_access_token_preferred(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "old-token")
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "new-token")
    import compute_probe

    monkeypatch.setattr(compute_probe, "load_dotenv", lambda *args, **kwargs: None)
    assert compute_probe.LocalComputeProbe().github_token == "new-token"


def test_best_stack_request():
    agent = ArbiterAgent()
    result = agent.run("/best")
    assert result["mode"] == "infra_stack"
    assert result["profile"]["id"] == "ai_first"
    assert len(result["stack"]) >= 4


def test_category_scout_request():
    agent = ArbiterAgent()
    result = agent.run("/scout wallets")
    assert result["mode"] == "infra_scout"
    assert result["category"] == "wallets"
    assert len(result["results"]) >= 1


def test_public_hosting_scout_recommends_free_url_paths():
    agent = ArbiterAgent()
    result = agent.infra.scout_category("public_hosting", limit=8)
    names = {item["id"] for item in result["results"]}

    assert result["mode"] == "infra_scout"
    assert result["category"] == "public_hosting"
    assert "cloudflare-quick-tunnel" in names
    assert "render-free-web-service" in names
    assert "github-codespaces-public-port" in names
    assert "GitHub Pages is static" in result["analysis"]


def test_self_audit_request():
    agent = ArbiterAgent()
    result = agent.run("/self")
    assert result["mode"] == "self_audit"
    assert result["profile"]["id"] == "ai_first"
    assert len(result["current_stack"]) >= 3


def test_self_audit_aligns_mcp_and_cli_first_surfaces():
    agent = ArbiterAgent()
    result = agent.run("/self")
    rows = {row["category"]: row for row in result["current_stack"]}
    assert rows["protocols"]["current"]["id"] == "mcp"
    assert rows["protocols"]["aligned"] is True
    assert rows["messaging"]["current"]["id"] == "cli-first"
    assert rows["messaging"]["aligned"] is True


def test_compute_audit_request_routes():
    agent = ArbiterAgent()
    agent.infra.compute_assessment = lambda profile_id="ai_first": {
        "mode": "compute_audit",
        "deal_found": False,
        "profile": {"id": profile_id},
        "probe": {"cpu_count": 8},
        "results": [],
        "analysis": "ok",
    }
    result = agent.run("/compute")
    assert result["mode"] == "compute_audit"
    assert result["profile"]["id"] == "ai_first"


def test_addon_and_quantum_requests_route_to_nomadds_layer():
    agent = ArbiterAgent()
    agent.addons.status = lambda: {
        "mode": "nomad_addon_scan",
        "deal_found": False,
        "ok": True,
        "addons": [],
        "stats": {"discovered": 0},
    }
    agent.addons.run_quantum_self_improvement = lambda objective="", context=None: {
        "mode": "nomad_quantum_tokens",
        "deal_found": False,
        "ok": True,
        "objective": objective,
        "context": context or {},
        "tokens": [{"qtoken_id": "qtok-test"}],
    }

    addons = agent.run("/addons")
    quantum = agent.run("/quantum reduce self-improvement loops")

    assert addons["mode"] == "nomad_addon_scan"
    assert quantum["mode"] == "nomad_quantum_tokens"
    assert "reduce self-improvement loops" in quantum["objective"]


def test_market_scan_request_routes():
    agent = ArbiterAgent()
    agent.infra.market_scan = lambda focus="balanced", limit=4: {
        "mode": "market_scan",
        "deal_found": False,
        "focus": focus,
        "competitors": [{"name": "ClawNet"}],
        "compute_opportunities": [{"name": "Cloudflare Workers AI"}],
        "analysis": "market ok",
    }
    result = agent.run("/market compute")
    assert result["mode"] == "market_scan"
    assert result["focus"] == "compute_auth"
    assert result["competitors"][0]["name"] == "ClawNet"


def test_unlock_compute_request_routes():
    agent = ArbiterAgent()
    agent.infra.activation_request = lambda category="compute", profile_id="ai_first": {
        "mode": "activation_request",
        "deal_found": False,
        "category": category,
        "profile": {"id": profile_id},
        "request": {
            "candidate_name": "GitHub Models",
            "ask": "Create a GitHub token.",
        },
        "results": [],
        "analysis": "unlock it",
    }
    result = agent.run("/unlock compute")
    assert result["mode"] == "activation_request"
    assert result["category"] == "compute"
    assert result["request"]["candidate_name"] == "GitHub Models"


def test_unlock_without_category_uses_nomad_best_decision():
    agent = ArbiterAgent()
    result = agent.run("/unlock")
    assert result["mode"] == "activation_request"
    assert result["category"] == "best"
    assert result["request"].get("decision_score") is not None
    assert result["request"].get("decision_reason")
    assert_concrete_unlock(result["request"])


def test_best_unlock_does_not_request_already_active_wallet(monkeypatch):
    monkeypatch.setenv("AGENT_PRIVATE_KEY", "1" * 64)
    monkeypatch.setenv("AGENT_ADDRESS", "0x" + "1" * 40)
    monkeypatch.setenv("EVM_CHAIN_ID", "97")
    agent = ArbiterAgent()
    result = agent.run("/unlock")
    assert result["mode"] == "activation_request"
    assert result["request"]["category"] != "wallets"


def test_best_unlock_prefers_public_hosting_before_agent_customer_when_only_local_api_exists(monkeypatch):
    monkeypatch.setenv("AGENT_PRIVATE_KEY", "1" * 64)
    monkeypatch.setenv("AGENT_ADDRESS", "0x" + "1" * 40)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "not-a-real-token-123")
    monkeypatch.setenv("NOMAD_API_PORT", "8787")
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "")
    monkeypatch.setenv("NOMAD_COLLABORATION_HOME_URL", "")
    agent = ArbiterAgent()
    result = agent.run("/unlock")
    assert result["request"]["category"] == "public_hosting"
    assert "public URL" in result["request"]["decision_reason"]
    assert_concrete_unlock(result["request"])


def test_best_unlock_prefers_agent_customer_when_public_url_exists(monkeypatch):
    monkeypatch.setenv("AGENT_PRIVATE_KEY", "1" * 64)
    monkeypatch.setenv("AGENT_ADDRESS", "0x" + "1" * 40)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "not-a-real-token-123")
    monkeypatch.setenv("NOMAD_API_PORT", "8787")
    agent = ArbiterAgent()
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.onrender.com")
    result = agent.run("/unlock")
    assert result["request"]["category"] == "agent_customers"
    assert "Nomad should scout" in result["request"]["ask"]
    assert_concrete_unlock(result["request"])
    assert "/cycle find one concrete AI-agent infrastructure pain lead" in result["request"]["human_action"]
    assert "LEAD_URL" in result["request"]["human_deliverable"]


def test_best_unlock_skips_empty_compute_candidate(monkeypatch):
    agent = ArbiterAgent()
    agent.infra.compute_probe.snapshot = lambda: {
        "ollama": {"available": True, "api_reachable": True, "count": 1},
        "llama_cpp": {"available": True},
        "hosted": {
            "github_models": {"configured": True, "available": True},
            "huggingface": {"configured": True, "available": True},
            "modal": {"configured": True, "available": True},
        },
    }
    result = agent.run("/unlock")
    assert result["mode"] == "activation_request"
    assert result["request"]["candidate_name"]


def test_self_improvement_cycle_includes_lead_scout():
    agent = ArbiterAgent()
    agent.self_improvement.brain_router.review = lambda objective, context: [
        {
            "name": "GitHub Models",
            "model": "openai/gpt-4o-mini",
            "ok": True,
            "content": "Search GitHub issues for agent builders blocked by inference quotas.",
        }
    ]
    result = agent.run("/cycle find agent leads")
    assert result["mode"] == "self_improvement_cycle"
    assert result["lead_scout"]["mode"] == "lead_scout"
    assert result["lead_scout"]["search_queries"]
    human_help = " ".join(result["lead_scout"]["human_help_only_for"]).lower()
    assert "login" in human_help or "api key" in human_help


def test_cycle_with_specific_lead_marks_active_lead():
    agent = ArbiterAgent()
    agent.self_improvement.brain_router.review = lambda objective, context: [
        {
            "name": "GitHub Models",
            "model": "openai/gpt-4o-mini",
            "ok": True,
            "content": "Draft a comment and repro test for provider-aware max_tokens defaults.",
        }
    ]
    result = agent.run(
        "/cycle Lead: pydantic-ai issue #2553 "
        "URL=https://github.com/pydantic/pydantic-ai/issues/2553 "
        "Pain=max_tokens default surprises agent builders. "
        "Nomad task: draft first help action."
    )
    active_lead = result["lead_scout"]["active_lead"]
    assert active_lead["url"] == "https://github.com/pydantic/pydantic-ai/issues/2553"
    assert "pydantic-ai issue #2553" in active_lead["name"]
    assert "Nomad task" not in active_lead["pain"]
    assert "Work this specific lead first" in result["lead_scout"]["next_agent_action"]
    assert result["profile"]["id"] == "ai_first"
    dev_unlocks = result["self_development"]["human_unlocks"]
    assert dev_unlocks
    assert dev_unlocks[0]["candidate_id"] == "approve-active-lead-help"


def test_cycle_objective_agent_builders_does_not_switch_profile():
    agent = ArbiterAgent()
    agent.self_improvement.brain_router.review = lambda objective, context: []
    result = agent.run("/cycle help agent builders with deployment pain")
    assert result["profile"]["id"] == "ai_first"


def test_public_lead_request_routes_without_outreach():
    agent = ArbiterAgent()
    agent.lead_discovery.scout_public_leads = lambda query="", limit=5: {
        "mode": "lead_discovery",
        "deal_found": False,
        "query": query,
        "leads": [],
        "outreach_policy": {"default_mode": "draft_only"},
    }

    result = agent.run("/leads agent quota")

    assert result["mode"] == "lead_discovery"
    assert result["query"] == "agent quota"
    assert result["outreach_policy"]["default_mode"] == "draft_only"


def test_service_request_routes_to_wallet_invoice():
    agent = ArbiterAgent()
    agent.service_desk.create_task = lambda **kwargs: {
        "mode": "agent_service_request",
        "deal_found": False,
        "ok": True,
        "task": {
            "task_id": "svc-test",
            "problem": kwargs["problem"],
            "requester_wallet": kwargs["requester_wallet"],
        },
    }

    result = agent.run(
        "/service request type=human_in_loop wallet=0x2222222222222222222222222222222222222222 "
        "agent blocked by approval"
    )

    assert result["mode"] == "agent_service_request"
    assert result["task"]["task_id"] == "svc-test"
    assert result["task"]["requester_wallet"] == "0x2222222222222222222222222222222222222222"


def test_agent_contact_request_routes_before_service_contact_alias():
    agent = ArbiterAgent()
    agent.agent_contacts.queue_contact = lambda **kwargs: {
        "mode": "agent_contact",
        "deal_found": False,
        "ok": True,
        "contact": {"endpoint_url": kwargs["endpoint_url"], "problem": kwargs["problem"]},
    }

    result = agent.run(
        "/contact-agent endpoint=https://example.com/.well-known/agent "
        "paid HITL approval help"
    )

    assert result["mode"] == "agent_contact"
    assert result["contact"]["endpoint_url"] == "https://example.com/.well-known/agent"
    assert "paid HITL" in result["contact"]["problem"]


def test_direct_agent_message_routes_to_gateway():
    agent = ArbiterAgent()
    agent.direct_agent.handle_direct_message = lambda payload: {
        "mode": "direct_agent_message",
        "deal_found": False,
        "ok": True,
        "payload": payload,
    }

    result = agent.run("/direct agent=StuckBot stuck in retry loop")

    assert result["mode"] == "direct_agent_message"
    assert result["payload"]["requester_agent"] == "StuckBot"
    assert "stuck in retry loop" in result["payload"]["message"]


def test_mutual_aid_request_routes_to_kernel():
    agent = ArbiterAgent()
    agent.mutual_aid.help_other_agent = lambda **kwargs: {
        "mode": "nomad_mutual_aid",
        "ok": True,
        "helped": kwargs["other_agent_id"],
        "task": kwargs["task"],
    }

    result = agent.run("/mutual-aid agent=QuotaBot token quota ERROR=429")

    assert result["mode"] == "nomad_mutual_aid"
    assert result["helped"] == "QuotaBot"
    assert "ERROR=429" in result["task"]


def test_mutual_aid_subcommands_route_to_ledger_inbox_patterns_and_packs():
    agent = ArbiterAgent()
    agent.mutual_aid.list_truth_ledger = lambda **kwargs: {"mode": "nomad_truth_density_ledger", **kwargs}
    agent.mutual_aid.list_swarm_inbox = lambda **kwargs: {"mode": "nomad_swarm_inbox", **kwargs}
    agent.mutual_aid.list_high_value_patterns = lambda **kwargs: {"mode": "nomad_high_value_patterns", **kwargs}
    agent.mutual_aid.list_paid_packs = lambda **kwargs: {"mode": "nomad_mutual_aid_packs", **kwargs}
    agent.mutual_aid.receive_swarm_proposal = lambda payload: {
        "mode": "nomad_swarm_inbox",
        "payload": payload,
    }

    ledger = agent.run("/mutual-aid ledger type=compute_auth limit=3")
    inbox = agent.run("/mutual-aid inbox status=verified_pending_review limit=4")
    patterns = agent.run("/mutual-aid patterns type=compute_auth limit=2 min_repeat_count=3")
    packs = agent.run("/mutual-aid packs type=compute_auth limit=5")
    proposal = agent.run("/mutual-aid proposal agent=Bot evidence=dry-run|test-pass Add a preflight check")

    assert ledger["mode"] == "nomad_truth_density_ledger"
    assert ledger["pain_type"] == "compute_auth"
    assert ledger["limit"] == 3
    assert inbox["mode"] == "nomad_swarm_inbox"
    assert inbox["statuses"] == ["verified_pending_review"]
    assert patterns["mode"] == "nomad_high_value_patterns"
    assert patterns["limit"] == 2
    assert patterns["min_repeat_count"] == 3
    assert packs["mode"] == "nomad_mutual_aid_packs"
    assert packs["limit"] == 5
    assert proposal["payload"]["sender_id"] == "Bot"
    assert proposal["payload"]["evidence"] == ["dry-run", "test-pass"]


def test_cold_outreach_routes_to_campaign():
    agent = ArbiterAgent()
    agent.agent_campaigns.create_campaign = lambda **kwargs: {
        "mode": "agent_cold_outreach_campaign",
        "deal_found": False,
        "ok": True,
        "campaign": kwargs,
    }

    result = agent.run(
        "/cold-outreach send limit=100 https://agent.example/.well-known/agent"
    )

    assert result["mode"] == "agent_cold_outreach_campaign"
    assert result["campaign"]["send"] is True
    assert result["campaign"]["limit"] == 100
    assert result["campaign"]["targets"][0]["endpoint_url"] == "https://agent.example/.well-known/agent"


def test_cold_outreach_without_endpoints_routes_to_discovery_campaign():
    agent = ArbiterAgent()
    agent.agent_campaigns.create_campaign_from_discovery = lambda **kwargs: {
        "mode": "agent_cold_outreach_campaign",
        "deal_found": False,
        "ok": True,
        "campaign": kwargs,
        "discovery": {"targets": []},
    }

    result = agent.run("/kaltaquise send limit=100 query=agent-card")

    assert result["mode"] == "agent_cold_outreach_campaign"
    assert result["campaign"]["send"] is True
    assert result["campaign"]["limit"] == 100
    assert result["campaign"]["query"] == "agent-card"
    assert result["campaign"]["seeds"] == []


def test_agent_contact_poll_routes_to_outbox():
    agent = ArbiterAgent()
    agent.agent_contacts.poll_contact = lambda contact_id: {
        "mode": "agent_contact",
        "deal_found": False,
        "ok": True,
        "contact": {"contact_id": contact_id, "status": "replied"},
    }

    result = agent.run("/agent-contact poll contact-123")

    assert result["mode"] == "agent_contact"
    assert result["contact"]["contact_id"] == "contact-123"


def test_unlock_compute_includes_fresh_task_metadata():
    agent = ArbiterAgent()
    agent.infra.compute_probe.snapshot = lambda: {
        "ollama": {"available": False, "api_reachable": False, "count": 0},
        "hosted": {
            "github_models": {"configured": False, "available": False},
            "huggingface": {"configured": True, "available": True},
            "modal": {"configured": False, "available": False},
        },
    }
    result = agent.run("/unlock compute")
    assert result["mode"] == "activation_request"
    assert result["request"].get("fresh") is True
    assert result["request"].get("task_id")
    assert result["request"]["candidate_id"] != "hf-inference-providers"
    assert_concrete_unlock(result["request"])


def test_partial_github_models_does_not_ask_for_new_token():
    infra = InfrastructureScout()
    profile = infra.profiles["ai_first"]
    request = infra._build_compute_request_payload(
        item={
            "id": "github-models",
            "name": "GitHub Models",
            "source_url": "https://docs.github.com/en/github-models",
        },
        state="partial",
        profile=profile,
        prefer_fallback=True,
    )
    concrete = infra._make_activation_request_concrete(request)
    assert "No new GitHub token is needed" in concrete["human_action"]
    assert "/skip last" in concrete["human_deliverable"]


def test_rate_limited_github_models_does_not_suggest_token_rotation():
    infra = InfrastructureScout()
    profile = infra.profiles["ai_first"]
    request = infra._build_compute_request_payload(
        item={
            "id": "github-models",
            "name": "GitHub Models",
            "source_url": "https://docs.github.com/en/github-models",
        },
        state="partial",
        profile=profile,
        prefer_fallback=True,
        provider_payload={
            "configured": True,
            "reachable": True,
            "available": False,
            "status_code": 429,
            "issue": "github_models_rate_limited",
            "message": "GitHub Models is reachable but rate limited this request.",
        },
    )
    concrete = infra._make_activation_request_concrete(request)
    assert "rate-limited" in concrete["ask"]
    assert "Do not rotate" in " ".join(concrete["steps"])
    assert "No new GitHub token is needed" in concrete["human_action"]


def test_unlock_non_compute_always_generates_fresh_request():
    agent = ArbiterAgent()
    result = agent.run("/unlock wallets")
    assert result["mode"] == "activation_request"
    assert result["request"].get("fresh") is True
    assert result["request"]["candidate_name"]
    assert result["request"]["task_id"]
    assert_concrete_unlock(result["request"])


def test_active_huggingface_is_not_requested_again():
    infra = InfrastructureScout()
    profile = infra.profiles["ai_first"]
    ranked = [
        {
            "id": "hf-inference-providers",
            "name": "Hugging Face Inference Providers",
            "source_url": "https://huggingface.co",
        },
        {
            "id": "modal-starter",
            "name": "Modal Starter Credits",
            "source_url": "https://modal.com",
        },
    ]
    probe = {
        "ollama": {"available": False, "api_reachable": False, "count": 0},
        "hosted": {
            "huggingface": {"configured": True, "available": True},
            "modal": {"configured": False, "available": False},
            "github_models": {"configured": False, "available": False},
        },
    }
    request = infra._build_compute_activation_request(
        ranked=ranked,
        probe=probe,
        profile=profile,
    )
    assert request["candidate_id"] == "modal-starter"


def test_llama_cpp_unlock_explains_it_is_optional_local_compute():
    infra = InfrastructureScout()
    profile = infra.profiles["ai_first"]
    request = infra._build_compute_request_payload(
        item={
            "id": "llama-cpp",
            "name": "llama.cpp",
            "source_url": "https://github.com/ggml-org/llama.cpp",
        },
        state="inactive",
        profile=profile,
        prefer_fallback=False,
    )
    assert request["candidate_id"] == "llama-cpp"
    assert request["requires_account"] is False
    assert "not an access-token task" in request["ask"]


def test_self_improvement_cycle_request_routes():
    agent = ArbiterAgent()
    agent.self_improvement.run_cycle = lambda objective="", profile_id="ai_first": {
        "mode": "self_improvement_cycle",
        "deal_found": False,
        "profile": {"id": profile_id, "label": "AI-First Nomad"},
        "objective": objective,
        "resources": {"brain_count": 2},
        "local_actions": [],
        "brain_reviews": [],
        "external_review_count": 0,
        "human_unlocks": [],
        "analysis": "cycle ok",
    }
    result = agent.run("/cycle improve compute resilience")
    assert result["mode"] == "self_improvement_cycle"
    assert result["profile"]["id"] == "ai_first"
    assert "improve compute resilience" in result["objective"]


def test_parse_funding_request():
    agent = ArbiterAgent()
    result = agent.run("fund me 0.5 eth")
    assert result["mode"] == "funding"
    assert result["funding"]["amount_eth"] == 0.5


def test_non_infra_query_gets_infra_help():
    agent = ArbiterAgent()
    result = agent.run("find me something cheap")
    assert result["mode"] == "infra_help"
    assert result["deal_found"] is False
    assert "Nomad scouts the best free infrastructure" in result["message"]


def test_travel_query_is_retired():
    agent = ArbiterAgent()
    result = agent.run("flight from Berlin to Paris next week under 400 eur")
    assert result["mode"] == "deprecated"
    assert result["deal_found"] is False
    assert "Travel scouting has been retired" in result["message"]


def test_local_funding_execution_is_returned():
    agent = ArbiterAgent()

    agent.treasury.build_funding_plan = lambda query: {
        "wallet": {"address": "0xabc", "configured": True},
        "network": "Nomad Local Devnet",
        "chain_id": 31337,
        "native_symbol": "ETH",
        "explorer_tx_base": "",
        "project_token_symbol": "NOMAD",
        "project_token_address": "0xToken",
        "amount_native": 0.5,
        "token_allocation_native": 0.35,
        "reserve_allocation_native": 0.15,
        "amount_eth": 0.5,
        "token_allocation_eth": 0.35,
        "reserve_allocation_eth": 0.15,
        "quote": None,
        "token_split_pct": 70.0,
        "reserve_split_pct": 30.0,
        "contract_address": "",
    }
    agent.treasury.maybe_execute_local_funding = lambda plan: {
        "executed": True,
        "token_symbol": "NOMAD",
        "minted_amount": 350.0,
        "mint_rate": 1000.0,
        "reserve_stays_native": 0.15,
        "token_balance": 1000350.0,
        "tx_hash": "0xtx",
    }

    result = agent.run("fund me 0.5 eth")
    assert result["mode"] == "funding"
    assert result["execution"]["executed"] is True
    assert result["execution"]["minted_amount"] == 350.0
    assert "minted 350.0 NOMAD" in result["analysis"]


def test_llm_review_can_override_scout_selection():
    agent = ArbiterAgent()

    agent.scout.scout_route = lambda **kwargs: {
        "origin": type("Place", (), {"name": "Berlin"})(),
        "anchor": type("Place", (), {"name": "Paris"})(),
        "opportunities": [
            {
                "route": "Berlin -> Paris",
                "candidate_name": "Paris",
                "anchor_destination": "Paris",
                "distance_from_target_km": 0.0,
                "distance_from_origin_km": 880.0,
                "population": 2100000,
                "accommodation_count": 10,
                "hostel_count": 1,
                "budget_food_count": 30,
                "transit_count": 25,
                "attraction_count": 40,
                "airport_count": 2,
                "arbitrage_score": 1.0,
                "value_score": 18.0,
                "scout_summary": "Paris baseline",
                "opportunity_id": "deal-1",
            },
            {
                "route": "Berlin -> Reims",
                "candidate_name": "Reims",
                "anchor_destination": "Paris",
                "distance_from_target_km": 130.0,
                "distance_from_origin_km": 760.0,
                "population": 180000,
                "accommodation_count": 14,
                "hostel_count": 3,
                "budget_food_count": 24,
                "transit_count": 17,
                "attraction_count": 12,
                "airport_count": 1,
                "arbitrage_score": 11.0,
                "value_score": 26.0,
                "scout_summary": "Reims hidden value",
                "opportunity_id": "deal-2",
            },
        ],
    }
    agent.analyst.review_scouting_opportunities = lambda request, opportunities: {
        "model": "llama3.2:1b",
        "selected_opportunity_id": opportunities[1]["opportunity_id"],
        "summary": "Reims looks less crowded and better supplied than Paris.",
        "arbitrage_angle": "Better stay density with lower tourism pressure.",
        "risks": ["Less iconic than the anchor city"],
        "confidence": "medium",
    }

    result = agent._handle_travel_request("flight from Berlin to Paris next week under 700 eur")
    assert result["mode"] == "scouting"
    assert result["deal_found"] is True
    assert result["selected_deal"]["selection_source"] == "llm"
    assert result["llm_review"]["selected_opportunity_id"] == result["selected_deal"]["opportunity_id"]


def test_agent_engagement_request_routes():
    agent = ArbiterAgent()
    agent.agent_engagements.list_engagements = lambda **kwargs: {
        "mode": "nomad_agent_engagements",
        "deal_found": False,
        "ok": True,
        "roles": kwargs.get("roles") or [],
        "pain_type": kwargs.get("pain_type") or "",
        "entry_count": 1,
    }
    agent.agent_engagements.summary = lambda **kwargs: {
        "mode": "nomad_agent_engagement_summary",
        "deal_found": False,
        "ok": True,
        "pain_type": kwargs.get("pain_type") or "",
        "entry_count": 1,
    }

    listed = agent.run("/agent-engagements role=peer_solver type=compute_auth limit=3")
    summary = agent.run("/agent-engagement-summary type=compute_auth limit=2")

    assert listed["mode"] == "nomad_agent_engagements"
    assert listed["roles"] == ["peer_solver"]
    assert listed["pain_type"] == "compute_auth"
    assert summary["mode"] == "nomad_agent_engagement_summary"
    assert summary["pain_type"] == "compute_auth"
