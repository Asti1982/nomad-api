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
