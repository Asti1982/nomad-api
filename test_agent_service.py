from agent_service import AgentServiceDesk
from x402_payment import X402PaymentAdapter


class FakeTreasury:
    def get_wallet_summary(self):
        return {
            "address": "0x" + "1" * 40,
            "configured": True,
            "native_balance": None,
        }


class FakeFacilitatorResponse:
    ok = True
    status_code = 200

    def json(self):
        return {
            "isValid": True,
            "payer": "0x" + "2" * 40,
        }


class FakeFacilitatorSession:
    def __init__(self):
        self.posts = []

    def post(self, url, json, headers, timeout):
        self.posts.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeFacilitatorResponse()


def test_service_request_creates_wallet_invoice_and_blocks_unpaid_work(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "true")
    monkeypatch.setenv("NOMAD_SERVICE_MIN_NATIVE", "0.02")
    monkeypatch.setenv("NOMAD_SERVICE_TREASURY_STAKE_BPS", "2500")
    monkeypatch.setenv("NOMAD_SERVICE_SOLVER_SPEND_BPS", "7500")
    desk = AgentServiceDesk(path=tmp_path / "tasks.json", treasury=FakeTreasury())

    result = desk.create_task(
        problem="Agent is blocked by login approval and token scope.",
        requester_agent="test-agent",
        requester_wallet="0x" + "2" * 40,
        service_type="human_in_loop",
        budget_native=0.01,
    )

    task = result["task"]
    assert result["ok"] is True
    assert task["status"] == "awaiting_payment"
    assert task["starter_rescue_plan"]["schema"] == "nomad.rescue_plan.v1"
    assert task["starter_rescue_plan"]["service_type"] == "human_in_loop"
    assert task["starter_rescue_plan"]["solution_pattern"]["guardrail_id"] == "hitl_unlock_contract"
    assert task["starter_rescue_plan"]["acceptance_criteria"]
    assert task["payment"]["recipient_address"] == "0x" + "1" * 40
    assert task["payment"]["amount_native"] == 0.02
    assert task["payment"]["payment_reference"].startswith("NOMAD_TASK:")
    assert task["payment_allocation"]["treasury_stake_native"] == 0.005
    assert task["payment_allocation"]["solver_budget_native"] == 0.015

    blocked = desk.work_task(task["task_id"])
    assert blocked["task"]["work_product"]["reason"] == "payment_required"


def test_service_work_can_run_when_payment_not_required(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "false")
    desk = AgentServiceDesk(path=tmp_path / "tasks.json", treasury=FakeTreasury())

    created = desk.create_task(
        problem="Agent needs MCP tool contract for a human approval workflow.",
        service_type="mcp_integration",
        metadata={
            "need_profile": {
                "preferred_output": "tool_contract",
            },
            "engagement_plan": {
                "offer_tier": "paid_unblock",
                "package": "Nomad MCP Contract Pack",
                "delivery": "contract draft plus one bounded integration path",
                "memory_upgrade": "reusable MCP integration template after consent",
            },
        },
    )
    worked = desk.work_task(created["task"]["task_id"])
    product = worked["task"]["work_product"]

    assert worked["task"]["status"] == "draft_ready"
    assert product["status"] == "draft_ready"
    assert product["approval"] == "draft_only"
    assert product["payment_allocation"]["treasury_staking_status"] == "ready_for_metamask_approval"
    assert product["human_unlocks"]
    assert "bypassing CAPTCHA or access controls" in worked["task"]["safety_contract"]["refused"]
    assert "staking treasury funds through MetaMask" in worked["task"]["safety_contract"]["requires_explicit_approval"]
    assert worked["task"]["work_product"]["response_schema"][0] == "rescue_plan"
    assert worked["task"]["work_product"]["response_schema"][1] == "diagnosis"
    assert product["rescue_plan"]["schema"] == "nomad.rescue_plan.v1"
    assert product["rescue_plan"]["solution_pattern"]["guardrail_id"] == "tool_contract_harness"
    assert product["rescue_plan"]["commercial_next_step"]["package"] == "Nomad MCP Contract Pack"
    assert product["agent_success_message"].startswith("nomad.rescue_plan.v1")
    assert worked["task"]["work_product"]["draft_response"].startswith("nomad.draft.v1")
    assert product["agent_need_profile"]["preferred_output"] == "tool_contract"
    assert product["engagement_plan"]["package"] == "Nomad MCP Contract Pack"
    assert "package=Nomad MCP Contract Pack" in product["draft_response"]


def test_hard_boundary_guard_returns_counter_offer(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_HARD_BOUNDARY_GUARD", "true")
    monkeypatch.setenv("NOMAD_SERVICE_MAX_NATIVE", "1.0")
    desk = AgentServiceDesk(path=tmp_path / "tasks.json", treasury=FakeTreasury())
    result = desk.create_task(
        problem="Agent needs custom unblock.",
        requester_wallet="0x" + "2" * 40,
        budget_native=2.0,
    )
    assert result["ok"] is False
    assert result["error"] == "budget_exceeds_boundary"
    counter = result.get("counter_offer") or {}
    assert counter.get("schema") == "nomad.counter_offer.v1"
    assert counter.get("decision") == "counter_offer"
    assert (counter.get("constraints") or {}).get("max_budget_native") == 1.0


def test_agent_reputation_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "true")
    desk = AgentServiceDesk(path=tmp_path / "tasks.json", treasury=FakeTreasury())
    desk.create_task(
        problem="Agent is blocked by token quota.",
        requester_agent="rep-agent",
        requester_wallet="0x" + "2" * 40,
        service_type="compute_auth",
        budget_native=0.2,
    )
    snap = desk.reputation_snapshot()
    assert snap["mode"] == "nomad_agent_reputation"
    assert snap["schema"] == "nomad.agent_reputation.v1"
    assert (snap.get("totals") or {}).get("tasks", 0) >= 1


def test_service_catalog_exposes_agent_first_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "false")
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

    catalog = desk.service_catalog()
    best_offer = desk.best_current_offer(service_type="compute_auth", requested_amount=0.03)

    assert catalog["service"] == "Nomad agent-first service contract"
    lane = catalog.get("agent_market_lane") or {}
    assert lane.get("featured_sku", {}).get("service_type") == "inter_agent_witness"
    assert "nomad.example" in (lane.get("featured_sku") or {}).get("well_known_offer_url", "")
    assert catalog["interaction_contract"]["audience"] == "ai_agents"
    assert catalog["interaction_contract"]["style"] == "agent_first_non_anthropomorphic"
    assert "agent_solution" in catalog["interaction_contract"]["response_schema"]
    assert catalog["starter_artifact"]["schema"] == "nomad.rescue_plan.v1"
    assert catalog["solver_artifact"]["schema"] == "nomad.agent_solution.v1"
    assert "nomad_agent_pain_solver" in catalog["contact_paths"]["mcp_tools"]
    assert "nomad_lead_conversion_pipeline" in catalog["contact_paths"]["mcp_tools"]
    assert "nomad_agent_attractor" in catalog["contact_paths"]["mcp_tools"]
    assert catalog["contact_paths"]["http"]["lead_conversion_pipeline"] == "POST /lead-conversions"
    assert catalog["contact_paths"]["http"]["agent_attractor"] == "GET /agent-attractor"
    assert catalog["interaction_contract"]["machine_entry_surface"] == "GET /agent-attractor or GET /swarm"
    assert catalog["first_paid_job_protocol"]["schema"] == "nomad.first_paid_job_protocol.v1"
    assert catalog["first_paid_job_protocol"]["preferred_first_job"]["service_type"] == "compute_auth"
    assert catalog["first_paid_job_protocol"]["preferred_first_job"]["minimum_budget_native"] == 0.03
    assert catalog["first_paid_job_protocol"]["call_sequence"][1]["endpoint"] == "https://nomad.example/tasks"
    assert catalog["first_paid_job_protocol"]["call_sequence"][2]["endpoint"] == "https://nomad.example/tasks/verify"
    assert "rescue_plan" in catalog["interaction_contract"]["response_schema"]
    assert catalog["safety_contract"]["alignment_mode"] == "agent_first_contractual"
    assert catalog["service_packages"]["compute_auth"][0]["package_id"] == "starter_diagnosis"
    assert catalog["service_packages"]["compute_auth"][1]["package_id"] == "bounded_unblock"
    assert catalog["agent_attractor_preview"]["schema"] == "nomad.agent_attractor.v1"
    assert catalog["agent_attractor_preview"]["agent_attractor_path"] == "https://nomad.example/agent-attractor"
    assert catalog["featured_product_offer"]["product_id"] == "prod-top"
    assert catalog["featured_product_offer"]["priority_score"] == 203.0
    assert catalog["featured_product_offer"]["service_template"]["endpoint"] == "POST /tasks"
    assert best_offer["headline"] == "Nomad Compute Unlock Pack: Provider Fallback Ladder"
    assert best_offer["source"] == "product_factory"
    assert best_offer["price_native"] == 0.03
    assert best_offer["trigger"] == "PLAN_ACCEPTED=true plus FACT_URL or ERROR"


def test_service_catalog_prefers_collaboration_home_when_local_api(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "false")
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "http://127.0.0.1:8787")
    monkeypatch.setenv("NOMAD_COLLABORATION_HOME_URL", "https://syndiode.com/nomad")

    desk = AgentServiceDesk(path=tmp_path / "tasks.json", treasury=FakeTreasury())
    catalog = desk.service_catalog()

    assert catalog["public_api_url"] == "https://syndiode.com/nomad"
    assert catalog["pricing"]["x402"]["verify_endpoint"] == "https://syndiode.com/nomad/tasks/x402-verify"
    assert catalog["agent_attractor_preview"]["agent_attractor_path"] == "https://syndiode.com/nomad/agent-attractor"


def test_service_request_detects_self_improvement_tasks(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "false")
    desk = AgentServiceDesk(path=tmp_path / "tasks.json", treasury=FakeTreasury())

    created = desk.create_task(
        problem="Please turn this solved blocker into a self-improvement guardrail and checklist.",
        service_type="custom",
    )

    assert created["task"]["service_type"] == "self_improvement"


def test_service_request_attaches_offer_ladder_and_payment_followup(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "true")
    monkeypatch.setenv("NOMAD_SERVICE_MIN_NATIVE", "0.01")
    desk = AgentServiceDesk(path=tmp_path / "tasks.json", treasury=FakeTreasury())

    created = desk.create_task(
        problem="Provider auth token and rate limit failures are blocking the agent.",
        service_type="compute_auth",
        budget_native=0.03,
    )
    task = created["task"]
    followup = desk.payment_followup(task["task_id"])

    assert task["commercial"]["starter_offer"]["package_id"] == "starter_diagnosis"
    assert task["commercial"]["starter_offer"]["amount_native"] == 0.01
    assert task["commercial"]["primary_offer"]["package_id"] == "bounded_unblock"
    assert task["commercial"]["primary_offer"]["amount_native"] == 0.03
    assert "Smaller entry path available" in created["analysis"]
    assert followup["cheaper_starter_available"] is True
    assert followup["starter_offer"]["amount_native"] == 0.01
    assert followup["primary_offer"]["amount_native"] == 0.03
    assert followup["machine_message"].startswith("nomad.payment_followup.v1")


def test_rescue_plan_prioritizes_explicit_compute_auth_over_approval_word(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "false")
    desk = AgentServiceDesk(path=tmp_path / "tasks.json", treasury=FakeTreasury())

    plan = desk.build_rescue_plan(
        problem="rate limit, token, approval failure around a provider call",
        service_type="compute_auth",
    )

    assert plan["service_type"] == "compute_auth"
    assert plan["solution_pattern"]["guardrail_id"] == "compute_fallback_ladder"
    assert "compute/auth reliability issue" in plan["diagnosis"]


def test_service_ledger_records_stake_spend_and_close(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "false")
    monkeypatch.setenv("NOMAD_SERVICE_TREASURY_STAKE_BPS", "3000")
    monkeypatch.setenv("NOMAD_SERVICE_SOLVER_SPEND_BPS", "7000")
    desk = AgentServiceDesk(path=tmp_path / "tasks.json", treasury=FakeTreasury())

    created = desk.create_task(problem="Agent needs paid human approval help.", budget_native=1.0)
    task_id = created["task"]["task_id"]
    checklist = desk.metamask_staking_checklist(task_id)
    stake_hash = "0x" + "a" * 64
    staked = desk.record_treasury_stake(task_id, tx_hash=stake_hash)
    spent = desk.record_solver_spend(task_id, amount_native=0.2, note="model inference")
    closed = desk.close_task(task_id, outcome="Delivered approval checklist.")

    assert checklist["mode"] == "metamask_staking_checklist"
    assert checklist["planned_stake_native"] == 0.3
    assert staked["task"]["treasury"]["staking_status"] == "staked_confirmed"
    assert staked["task"]["treasury"]["stake_tx_hash"] == stake_hash
    assert spent["task"]["solver_budget"]["spent_native"] == 0.2
    assert spent["task"]["solver_budget"]["remaining_native"] == 0.5
    assert closed["task"]["status"] == "delivered"
    events = [item["event"] for item in closed["task"]["ledger"]]
    assert "treasury_stake_recorded" in events
    assert "solver_spend_recorded" in events
    assert "task_delivered" in events


def test_service_can_mark_invalid_payment_placeholder_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "true")
    desk = AgentServiceDesk(path=tmp_path / "tasks.json", treasury=FakeTreasury())
    created = desk.create_task(
        problem="Old placeholder without a real requester route.",
        service_type="compute_auth",
        budget_native=0.01,
    )
    task_id = created["task"]["task_id"]

    result = desk.mark_stale_invalid(task_id, reason="No requester endpoint, wallet, callback, or tx.")

    assert result["task"]["status"] == "stale_invalid"
    assert result["task"]["invalid_reason"] == "No requester endpoint, wallet, callback, or tx."
    assert result["task"]["ledger"][-1]["event"] == "marked_stale_invalid"


def test_service_verify_rejects_invalid_tx_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "true")
    desk = AgentServiceDesk(path=tmp_path / "tasks.json", treasury=FakeTreasury())
    created = desk.create_task(problem="Agent needs quota diagnosis.")

    result = desk.verify_payment(created["task"]["task_id"], "not-a-tx")

    verification = result["task"]["payment"]["verification"]
    assert verification["ok"] is False
    assert verification["status"] == "invalid_tx_hash"


def test_service_request_includes_x402_challenge_and_verifies_signature(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "true")
    monkeypatch.setenv("NOMAD_X402_ASSET_ADDRESS", "0x" + "3" * 40)
    monkeypatch.setenv("NOMAD_X402_NETWORK", "eip155:84532")
    monkeypatch.setenv("NOMAD_X402_FACILITATOR_URL", "https://x402.example/facilitator")
    session = FakeFacilitatorSession()
    x402 = X402PaymentAdapter(session=session)
    desk = AgentServiceDesk(
        path=tmp_path / "tasks.json",
        treasury=FakeTreasury(),
        x402=x402,
    )
    created = desk.create_task(
        problem="Agent needs paid x402 loop help.",
        requester_wallet="0x" + "2" * 40,
        budget_native=0.05,
    )
    task = created["task"]
    challenge = task["payment"]["x402"]
    payment_payload = {
        "x402Version": 2,
        "accepted": challenge["paymentRequirements"],
        "payload": {"signature": "0x" + "a" * 130},
        "resource": challenge["resource"],
    }
    signature_header = x402.encode_header(payment_payload)

    result = desk.verify_x402_payment(task["task_id"], signature_header)

    assert challenge["configured"] is True
    assert challenge["headers"]["PAYMENT-SIGNATURE"]
    assert result["task"]["status"] == "paid"
    assert result["task"]["payment"]["verification"]["method"] == "x402"
    assert result["task"]["payment"]["verification"]["payer"] == "0x" + "2" * 40
    assert session.posts[0]["url"] == "https://x402.example/facilitator/verify"
    assert session.posts[0]["json"]["paymentRequirements"]["payTo"] == "0x" + "1" * 40


def test_service_e2e_runway_creates_payable_task_and_guides_next_step(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "true")
    monkeypatch.setenv("NOMAD_SERVICE_MIN_NATIVE", "0.02")
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    monkeypatch.setenv("NOMAD_COLLABORATION_HOME_URL", "")
    monkeypatch.setenv("NOMAD_RENDER_DOMAIN", "")
    desk = AgentServiceDesk(path=tmp_path / "tasks.json", treasury=FakeTreasury())

    result = desk.end_to_end_runway(
        problem="Agent needs a bounded compute auth unblock.",
        service_type="compute_auth",
        budget_native=0.03,
        requester_agent="VerifierBot",
        requester_wallet="0x" + "2" * 40,
        create_task=True,
    )

    task = result["task"]
    stages = {item["stage"]: item for item in result["lifecycle"]}

    assert result["mode"] == "nomad_service_e2e"
    assert result["created"] is True
    assert task["status"] == "awaiting_payment"
    assert result["payment_followup"]["ok"] is True
    assert result["http_runway"]["create_task"]["endpoint"] == f"{result['public_api_url']}/service/e2e"
    assert result["commands"]["preview_or_create"] == f"python main.py --cli service-e2e --task-id {task['task_id']}"
    assert stages["create_task"]["status"] == "completed"
    assert stages["verify_payment"]["status"] == "ready"
    assert stages["work_task"]["status"] == "blocked"
    assert "Verify payment" in result["next_best_action"]


def test_service_e2e_preview_command_quotes_problem_for_shell_safety(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "true")
    desk = AgentServiceDesk(path=tmp_path / "tasks.json", treasury=FakeTreasury())

    result = desk.end_to_end_runway(
        problem='Provider Fallback Ladder | pattern_id=hvp-demo "quoted"',
        service_type="compute_auth",
        budget_native=0.03,
        create_task=False,
    )

    command = result["commands"]["preview_or_create"]

    assert '"Provider Fallback Ladder | pattern_id=hvp-demo \'quoted\'"' in command
