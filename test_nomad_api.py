from nomad_api import NomadApiHandler
from pathlib import Path

from nomad_swarm_registry import SwarmJoinRegistry


def test_normalize_public_path_strips_prefix_from_public_url(monkeypatch):
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://example.com/myapi")
    monkeypatch.delenv("NOMAD_HTTP_PATH_PREFIX", raising=False)
    assert NomadApiHandler._normalize_public_path("/myapi/openapi.json") == "/openapi.json"
    assert NomadApiHandler._normalize_public_path("/myapi") == "/"
    assert NomadApiHandler._normalize_public_path("/myapi/") == "/"
    assert NomadApiHandler._normalize_public_path("/health") == "/health"


def test_normalize_public_path_uses_explicit_prefix(monkeypatch):
    monkeypatch.delenv("NOMAD_PUBLIC_API_URL", raising=False)
    monkeypatch.setenv("NOMAD_HTTP_PATH_PREFIX", "/nomad")
    assert NomadApiHandler._normalize_public_path("/nomad/swarm/join") == "/swarm/join"


def test_syndiode_edge_routes_doc_lists_peer_acquisition():
    md = Path(__file__).resolve().parent / "syndiode_edge_routes.md"
    text = md.read_text(encoding="utf-8")
    assert "syndiode.com" in text
    assert "nomad-peer-acquisition.json" in text
    assert "Whitelist" in text or "whitelist" in text.lower()


def test_nomad_public_html_page_exists():
    html = Path(__file__).resolve().parent / "public" / "nomad.html"
    text = html.read_text(encoding="utf-8")

    assert "Nomad by syndiode" in text
    assert "the linux for AI agents" in text
    assert "Connected Swarm Nodes" in text
    assert "Recent Swarm Nodes" in text
    assert "const resolveApiBase = () =>" in text
    assert "/.well-known/agent-card.json" in text
    assert "/.well-known/nomad-agent-invariants.json" in text
    assert "/.well-known/nomad-inter-agent-witness-offer.json" in text
    assert "/.well-known/nomad-peer-acquisition.json" in text
    assert "/agent-attractor" in text
    assert "/swarm/network" in text
    assert "/swarm/coordinate" in text
    assert "/swarm/accumulate" in text
    assert "/swarm/develop" in text
    assert 'fetch(apiUrl("/swarm"))' in text
    assert 'fetch(apiUrl("/swarm/network"))' in text
    assert 'fetch(apiUrl("/swarm/coordinate"))' in text
    assert 'fetch(apiUrl("/swarm/accumulate"))' in text
    assert 'apiUrl("/swarm/join")' in text
    assert "/operator-desk" in text
    assert "/operator-daily" in text
    assert "/operator-report" in text
    assert "/growth-start" in text


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
        "decision_envelope": {"schema": "nomad.decision_envelope.v1", "decision": "accept"},
        "session": {"last_task_id": "svc-123"},
    }

    envelope = handler._jsonrpc_envelope(request_payload, result)

    assert envelope["jsonrpc"] == "2.0"
    assert envelope["id"] == "req-1"
    assert envelope["result"]["role"] == "agent"
    assert envelope["result"]["parts"][0]["text"].startswith("nomad.reply.v1")
    assert envelope["result"]["metadata"]["classification"] == "compute_auth"
    assert envelope["result"]["metadata"]["task_id"] == "svc-123"
    assert envelope["result"]["metadata"]["decision_envelope"]["decision"] == "accept"


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


def test_nomad_api_advertises_agent_development_route(tmp_path):
    registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")

    manifest = registry.public_manifest(base_url="https://nomad.example")

    assert manifest["development_exchange"] == "https://nomad.example/swarm/develop"
    assert manifest["help_now"]["agent_wanting_self_improvement_plan"] == "https://nomad.example/swarm/develop"
    assert manifest["first_agent_readiness"]["status"] == "ready_for_bounded_first_exchange"


def test_build_openapi_document_lists_core_paths():
    from nomad_openapi import build_openapi_document

    doc = build_openapi_document(base_url="https://nomad.example")
    assert doc["openapi"] == "3.0.3"
    assert "/health" in doc["paths"]
    assert "/openapi.json" in doc["paths"]
    assert "/.well-known/nomad-agent-invariants.json" in doc["paths"]
    assert "/agent-invariants" in doc["paths"]
    assert "/.well-known/nomad-inter-agent-witness-offer.json" in doc["paths"]
    assert "/inter-agent-witness-offer" in doc["paths"]
    assert "/.well-known/nomad-peer-acquisition.json" in doc["paths"]
    assert "/peer-acquisition" in doc["paths"]
    assert "/swarm/join" in doc["paths"]
    assert "/swarm/develop" in doc["paths"]
    assert doc["servers"][0]["url"] == "https://nomad.example"


def test_machine_error_helpers():
    from nomad_machine_error import machine_error_response, merge_machine_error

    err = machine_error_response(error="e1", message="m1", hints=["h1"])
    assert err["ok"] is False
    assert err["schema"] == "nomad.machine_error.v1"
    merged = merge_machine_error({"ok": False, "error": "e1"}, error="e1", hints=["h2"])
    assert merged["machine_error"]["hints"] == ["h2"]


def test_nomad_api_exposes_first_agent_readiness(tmp_path):
    handler = NomadApiHandler.__new__(NomadApiHandler)
    handler.swarm_registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")
    handler._base_url = lambda: "https://nomad.example"  # type: ignore[method-assign]

    result = handler.swarm_registry.first_agent_readiness(base_url=handler._base_url())

    assert result["schema"] == "nomad.first_external_agent_readiness.v1"
    assert result["activation_budget"]["max_active_agents_per_blocker"] == 2
    assert result["first_exchange_endpoints"]["develop"] == "https://nomad.example/swarm/develop"


def test_nomad_health_links_include_unhuman_hub():
    base = "https://nomad.example"
    b = base.rstrip("/")
    links = {
        "operator_sprint": f"{b}/operator-sprint",
        "agent_reputation": f"{b}/reputation",
        "unhuman_hub": f"{b}/unhuman-hub",
    }
    assert links["unhuman_hub"] == "https://nomad.example/unhuman-hub"
