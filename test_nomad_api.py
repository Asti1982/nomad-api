from nomad_api import NomadApiHandler
from pathlib import Path


def test_nomad_public_html_page_exists():
    html = Path(__file__).resolve().parent / "public" / "nomad.html"
    text = html.read_text(encoding="utf-8")

    assert "Nomad by syndiode" in text
    assert "the linux for AI agents" in text
    assert "/.well-known/agent-card.json" in text
    assert "/agent-attractor" in text


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
