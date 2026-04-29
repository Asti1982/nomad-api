from nomad_api import NomadApiHandler
from pathlib import Path

from nomad_swarm_registry import SwarmJoinRegistry


def test_nomad_public_html_page_exists():
    html = Path(__file__).resolve().parent / "public" / "nomad.html"
    text = html.read_text(encoding="utf-8")

    assert "Nomad by syndiode" in text
    assert "the linux for AI agents" in text
    assert "Connected Swarm Nodes" in text
    assert "Recent Swarm Nodes" in text
    assert "const resolveApiBase = () =>" in text
    assert "/.well-known/agent-card.json" in text
    assert "/agent-attractor" in text
    assert "/swarm/coordinate" in text
    assert "/swarm/accumulate" in text
    assert 'fetch(apiUrl("/swarm"))' in text
    assert 'fetch(apiUrl("/swarm/coordinate"))' in text
    assert 'fetch(apiUrl("/swarm/accumulate"))' in text
    assert 'apiUrl("/swarm/join")' in text


def test_nomad_api_wraps_jsonrpc_a2a_result():
    handler = NomadApiHandler.__new__(NomadApiHandler)
    request_payload = {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "message/send",
    }
    result = {
        "mode": "direct_agent_message",
        "next_agent_message": "nomad.reply.v1\nclassification=compute_auth",
        "free_diagnosis": {"classification": "compute_auth"},
        "task": {"task_id": "svc-123"},
        "payment_required": {"statusCode": 402},
        "normalized_request": {"input_schema": "structured_fields"},
        "structured_reply": {"classification": "compute_auth"},
        "session": {"last_task_id": "svc-123"},
    }

    envelope = handler._jsonrpc_envelope(request_payload, result)

    assert envelope["jsonrpc"] == "2.0"
    assert envelope["id"] == "req-1"
    assert envelope["result"]["role"] == "agent"
    assert envelope["result"]["parts"][0]["text"].startswith("nomad.reply.v1")
    assert envelope["result"]["metadata"]["classification"] == "compute_auth"
    assert envelope["result"]["metadata"]["task_id"] == "svc-123"


def test_nomad_api_detects_jsonrpc_request_shape():
    handler = NomadApiHandler.__new__(NomadApiHandler)

    assert handler._is_jsonrpc_request({"jsonrpc": "2.0", "id": 1, "method": "message/send"}) is True
    assert handler._is_jsonrpc_request({"message": "hello"}) is False


def test_nomad_api_accumulates_swarm_agents_from_contacts(tmp_path):
    class FakeContacts:
        def list_contacts(self, limit=100):
            return {
                "contacts": [
                    {
                        "contact_id": "contact-1",
                        "status": "sent",
                        "endpoint_url": "https://remote-agent.example/a2a/message",
                        "service_type": "compute_auth",
                    }
                ]
            }

    class FakeCampaigns:
        def list_campaigns(self, limit=25):
            return {"campaigns": []}

    class FakeAgent:
        agent_contacts = FakeContacts()
        agent_campaigns = FakeCampaigns()

    handler = NomadApiHandler.__new__(NomadApiHandler)
    handler.agent = FakeAgent()
    handler.swarm_registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    handler._base_url = lambda: "https://nomad.example"  # type: ignore[method-assign]

    result = handler._accumulate_swarm_agents({"from_contacts": True})

    assert result["schema"] == "nomad.swarm_accumulation.v1"
    assert result["prospect_agents"] == 1
    assert result["activation_queue"][0]["agent_id"] == "remote-agent.example-a2a-message"
