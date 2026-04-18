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
    assert any(skill["id"] == "human-in-the-loop-rescue" for skill in card["skills"])


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
    assert "StuckBot" in result["next_agent_message"]


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
