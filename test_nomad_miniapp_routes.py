from pathlib import Path

from nomad_api import NomadApiHandler
from nomad_openapi import build_openapi_document


def test_telegram_miniapp_public_routes_render_page():
    for route in ["/telegram-miniapp", "/telegram-miniapp.html", "/miniapp", "/mini", "/telegram"]:
        handler = NomadApiHandler.__new__(NomadApiHandler)
        seen = []
        handler.path = route
        handler._html_file_response = lambda path: seen.append(path)

        handler.do_GET()

        assert seen == [Path(__file__).resolve().parent / "public" / "telegram-miniapp.html"]


def test_eth_support_routes_return_packet():
    for route in ["/swarm/eth-support", "/ethereum-ai-support", "/.well-known/nomad-eth-support.json"]:
        handler = NomadApiHandler.__new__(NomadApiHandler)
        seen = []
        handler.path = route
        handler._base_url = lambda: "https://nomad.example"  # type: ignore[method-assign]
        handler._json_response = lambda payload, status=200: seen.append((status, payload))  # type: ignore[method-assign]

        handler.do_GET()

        assert seen[0][0] == 200
        assert seen[0][1]["schema"] == "nomad.ethereum_ai_agent_support.v1"
        assert seen[0][1]["proposal_packet"]["ask_usd"] == 45000.0


def test_openapi_lists_miniapp_and_eth_support_paths():
    doc = build_openapi_document(base_url="https://nomad.example")

    assert "/telegram-miniapp" in doc["paths"]
    assert "/telegram-miniapp/lead" in doc["paths"]
    assert "/.well-known/nomad-telegram-miniapp.json" in doc["paths"]
    assert "/.well-known/nomad-eth-support.json" in doc["paths"]
    assert "/swarm/eth-support" in doc["paths"]
