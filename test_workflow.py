from workflow import ArbiterAgent
from infra_scout import InfrastructureScout


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


def test_self_audit_request():
    agent = ArbiterAgent()
    result = agent.run("/self")
    assert result["mode"] == "self_audit"
    assert result["profile"]["id"] == "ai_first"
    assert len(result["current_stack"]) >= 3


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


def test_unlock_non_compute_always_generates_fresh_request():
    agent = ArbiterAgent()
    result = agent.run("/unlock wallets")
    assert result["mode"] == "activation_request"
    assert result["request"].get("fresh") is True
    assert result["request"]["candidate_name"]
    assert result["request"]["task_id"]


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
