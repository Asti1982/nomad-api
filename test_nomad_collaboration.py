from direct_agent import DirectAgentGateway
from nomad_collaboration import collaboration_status


class FakeTreasury:
    def get_wallet_summary(self):
        return {"address": "0x" + "1" * 40}


class FakeServiceDesk:
    class Chain:
        name = "Nomad Local Devnet"
        chain_id = 31337
        native_symbol = "ETH"

    def __init__(self):
        self.chain = self.Chain()
        self.treasury = FakeTreasury()


def test_collaboration_status_exposes_outward_agent_permission(monkeypatch):
    monkeypatch.setenv("NOMAD_OUTBOUND_AGENT_COLLABORATION_ENABLED", "true")
    monkeypatch.setenv("NOMAD_ACCEPT_AGENT_HELP", "true")
    monkeypatch.setenv("NOMAD_LEARN_FROM_AGENT_REPLIES", "true")
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://onrender.syndiode.com")
    monkeypatch.setenv("NOMAD_COLLABORATION_HOME_URL", "https://onrender.syndiode.com")

    result = collaboration_status()
    charter = result["charter"]

    assert result["ok"] is True
    assert charter["render_syndiode_lane"] is True
    assert charter["permission"]["ask_other_agents_for_help"] is True
    assert charter["permission"]["accept_help_from_other_agents"] is True
    assert charter["permission"]["learn_from_public_agent_replies"] is True
    assert any("without vendor" in item for item in charter["ethic"])
    assert any("do not send secrets" in item for item in charter["boundaries"])


def test_agent_card_publishes_collaboration_charter(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_OUTBOUND_AGENT_COLLABORATION_ENABLED", "true")
    monkeypatch.setenv("NOMAD_ACCEPT_AGENT_HELP", "true")
    monkeypatch.setenv("NOMAD_LEARN_FROM_AGENT_REPLIES", "true")
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://onrender.syndiode.com")

    gateway = DirectAgentGateway(path=tmp_path / "sessions.json", service_desk=FakeServiceDesk())
    card = gateway.agent_card()

    assert card["capabilities"]["outboundAgentCollaboration"] is True
    assert card["capabilities"]["acceptsAgentHelp"] is True
    assert card["capabilities"]["learnsFromAgentReplies"] is True
    assert card["collaborationCharter"]["public_home"] == "https://onrender.syndiode.com"
