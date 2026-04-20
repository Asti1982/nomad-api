from direct_agent import DirectAgentGateway


class FakeTreasury:
    def get_wallet_summary(self):
        return {
            "address": "0x" + "1" * 40,
            "configured": True,
        }


class FakeServiceDesk:
    class Chain:
        name = "Nomad Local Devnet"
        chain_id = 31337
        native_symbol = "ETH"

    def __init__(self):
        self.chain = self.Chain()
        self.treasury = FakeTreasury()

    def create_task(self, **kwargs):
        return {
            "mode": "agent_service_request",
            "ok": True,
            "task": {
                "task_id": "svc-direct",
                "service_type": kwargs["service_type"],
                "payment": {"amount_native": 0.02},
            },
        }

    def build_rescue_plan(self, problem, service_type="custom", need_profile=None, engagement_plan=None, budget_native=None):
        need_profile = need_profile or {}
        engagement_plan = engagement_plan or {}
        return {
            "schema": "nomad.rescue_plan.v1",
            "plan_id": "rescue-test",
            "service_type": service_type,
            "diagnosis": f"Nomad classifies this as {service_type}.",
            "safe_now": ["one safe next step"],
            "required_input": "`ERROR=<message>`",
            "acceptance_criteria": ["requester has one concrete next action"],
            "commercial_next_step": {
                "package": engagement_plan.get("package", "Nomad test pack"),
            },
            "requester_fit": {
                "preferred_output": need_profile.get("preferred_output", ""),
            },
        }


class FakeX402ServiceDesk(FakeServiceDesk):
    def create_task(self, **kwargs):
        result = super().create_task(**kwargs)
        result["task"]["payment"]["x402"] = {
            "paymentRequirements": {
                "scheme": "exact",
            }
        }
        return result


class FakeResponse:
    ok = True
    status_code = 200

    def json(self):
        return {
            "protocolVersion": "0.3.0",
            "name": "RemoteAgent",
            "url": "https://remote.example/a2a/message",
            "skills": [],
        }


class FakeSession:
    def get(self, url, timeout):
        return FakeResponse()


def test_agent_card_exposes_direct_and_payment_capabilities(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    gateway = DirectAgentGateway(path=tmp_path / "sessions.json", service_desk=FakeServiceDesk())

    card = gateway.agent_card()

    assert card["name"] == "LoopHelper"
    assert card["url"] == "https://nomad.example/a2a/message"
    assert card["capabilities"]["directOnly"] is True
    assert card["capabilities"]["x402PaymentRequired"] is True
    assert card["capabilities"]["agentFirst"] is True
    assert card["capabilities"]["agentPainSolver"] is True
    assert card["interactionContract"]["style"] == "agent_first_non_anthropomorphic"
    assert card["interactionContract"]["reply_modes"] == ["message", "task"]
    assert "jsonrpc_message_send" in card["interactionContract"]["protocol_hints"]
    assert card["interactionContract"]["idempotency"] == "contextId_or_request_id_on_retry"
    assert card["interactionContract"]["ttl_seconds"] == 600
    assert "Compute Unlock Pack" in card["description"]
    assert any(skill["id"] == "human-in-the-loop-rescue" for skill in card["skills"])
    assert any(skill["id"] == "compute-auth-unblock" for skill in card["skills"])
    assert any(skill["id"] == "self-improvement-pack" for skill in card["skills"])
    assert any(skill["id"] == "agent-pain-solver" for skill in card["skills"])


def test_direct_message_creates_session_free_diagnosis_and_payment_challenge(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    gateway = DirectAgentGateway(path=tmp_path / "sessions.json", service_desk=FakeServiceDesk())

    result = gateway.handle_direct_message(
        {
            "requester_agent": "StuckBot",
            "message": "I am stuck in an infinite retry loop after a tool timeout.",
            "requester_wallet": "0x" + "2" * 40,
        }
    )

    assert result["mode"] == "direct_agent_message"
    assert result["ok"] is True
    assert result["free_diagnosis"]["pain_type"] == "loop_break"
    assert result["payment_required"]["statusCode"] == 402
    assert result["payment_required"]["service_type"] == "loop_break"
    assert result["payment_required"]["recipient"] == "0x" + "1" * 40
    assert result["task"]["task_id"] == "svc-direct"
    assert result["interaction_contract"]["audience"] == "ai_agents"
    assert result["agent_need_profile"]["preferred_output"] == "loop_break_plan"
    assert result["engagement_plan"]["package"] == "Nomad Loop Rescue Pack"
    assert result["rescue_plan"]["schema"] == "nomad.rescue_plan.v1"
    assert result["rescue_plan"]["service_type"] == "loop_break"
    assert result["rescue_plan"]["acceptance_criteria"]
    assert result["structured_reply"]["requester"] == "StuckBot"
    assert result["structured_reply"]["offer_tier"] == "starter_diagnosis"
    assert result["structured_reply"]["rescue_plan_id"].startswith("rescue-")
    assert result["structured_reply"]["required_input"]
    assert result["structured_reply"]["starter_offer"].startswith("Nomad Loop Rescue Pack")
    assert result["structured_reply"]["starter_amount_native"] == "0.01"
    assert result["structured_reply"]["schema"] == "nomad.reply.v1"
    assert result["structured_reply"]["reply_mode_preference"] == "task_when_stateful_else_message"
    assert result["structured_reply"]["task_states"] == "submitted|working|input_required|auth_required|completed|failed|rejected"
    assert result["structured_reply"]["idempotency"] == "reuse_contextId_or_request_id_on_retry"
    assert result["structured_reply"]["ttl_seconds"] == "600"
    assert result["structured_reply"]["primary_offer"] == "Nomad Loop Rescue Pack"
    assert result["structured_reply"]["payment_entry_path"] == "starter_first"
    assert result["next_agent_message"].startswith("nomad.reply.v1")
    assert "requester=StuckBot" in result["next_agent_message"]
    assert "rescue_plan_id=rescue-" in result["next_agent_message"]
    assert "starter_amount_native=0.01" in result["next_agent_message"]
    assert "payment_entry_path=starter_first" in result["next_agent_message"]


def test_direct_message_normalizes_structured_agent_request(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    gateway = DirectAgentGateway(path=tmp_path / "sessions.json", service_desk=FakeServiceDesk())

    result = gateway.handle_direct_message(
        {
            "requester_agent": "ComputeBot",
            "problem": "Provider access fails intermittently.",
            "goal": "restore model execution",
            "blocking_step": "openai/gpt-4o-mini returns auth error",
            "constraints": ["no secret sharing", "budget under 0.05 ETH"],
            "budget_native": "0.03",
        }
    )

    normalized = result["normalized_request"]
    assert normalized["input_schema"] == "structured_fields"
    assert normalized["budget_native"] == 0.03
    assert normalized["structured_request"]["goal"] == "restore model execution"
    assert "blocking_step: openai/gpt-4o-mini returns auth error" in normalized["message"]
    assert result["agent_need_profile"]["engagement_mode"] == "execute_unblock"
    assert result["engagement_plan"]["budget_fit"] == "within_budget"
    assert result["engagement_plan"]["package"] == "Nomad Compute Unlock Pack"
    assert result["rescue_plan"]["requester_fit"]["preferred_output"] == "fallback_lane_plan"
    assert result["task"]["metadata"]["need_profile"]["preferred_output"] == "fallback_lane_plan"
    assert result["task"]["metadata"]["rescue_plan_id"].startswith("rescue-")
    assert result["structured_reply"]["starter_amount_native"] == "0.01"
    assert result["structured_reply"]["primary_amount_native"] == "0.03"
    assert result["structured_reply"]["payment_entry_path"] == "starter_first"


def test_direct_message_normalizes_a2a_jsonrpc_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    gateway = DirectAgentGateway(path=tmp_path / "sessions.json", service_desk=FakeServiceDesk())

    result = gateway.handle_direct_message(
        {
            "jsonrpc": "2.0",
            "method": "message/send",
            "contextId": "ctx-123",
            "params": {
                "message": {
                    "parts": [{"kind": "text", "text": "quota exhausted on fallback model"}],
                    "metadata": {
                        "agent": "QuotaBot",
                        "endpoint": "https://quota.example/a2a/QuotaBot",
                        "wallet": "0x" + "2" * 40,
                        "goal": "restore inference",
                        "blocking_step": "fallback returns 429",
                    },
                }
            },
        }
    )

    normalized = result["normalized_request"]
    assert normalized["input_schema"] == "a2a_jsonrpc"
    assert normalized["requester_agent"] == "QuotaBot"
    assert normalized["requester_endpoint"] == "https://quota.example/a2a/QuotaBot"
    assert normalized["requester_wallet"] == "0x" + "2" * 40
    assert normalized["session_id"] == "ctx-123"
    assert "problem: quota exhausted on fallback model" in normalized["message"]


def test_direct_message_preserves_base_payment_fields_when_x402_extension_is_partial(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://nomad.example")
    gateway = DirectAgentGateway(path=tmp_path / "sessions.json", service_desk=FakeX402ServiceDesk())

    result = gateway.handle_direct_message(
        {
            "requester_agent": "QuotaBot",
            "message": "provider auth error and quota failure on fallback lane",
        }
    )

    assert result["payment_required"]["statusCode"] == 402
    assert result["payment_required"]["amount_native"] == 0.02
    assert result["payment_required"]["recipient"] == "0x" + "1" * 40
    assert result["structured_reply"]["amount_native"] == "0.02"


def test_discovers_agent_card_from_well_known_path(tmp_path):
    gateway = DirectAgentGateway(
        path=tmp_path / "sessions.json",
        service_desk=FakeServiceDesk(),
        session=FakeSession(),
    )

    result = gateway.discover_agent_card("https://remote.example")

    assert result["ok"] is True
    assert result["agent_card"]["name"] == "RemoteAgent"
    assert result["agent_card_url"] == "https://remote.example/.well-known/agent-card.json"
