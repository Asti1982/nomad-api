from nomad_cli import run_once
from nomad_google_agentic_era import build_google_agentic_surface
from nomad_openapi import build_openapi_document


def test_google_agentic_surface_is_free_first(monkeypatch):
    monkeypatch.delenv("NOMAD_ALLOW_GEMINI_FREE_PROVIDER_CALL", raising=False)
    monkeypatch.delenv("NOMAD_ALLOW_PAID_MODEL_CALLS", raising=False)

    surface = build_google_agentic_surface(base_url="https://www.syndiode.com")

    assert surface["schema"] == "nomad.google_agentic_era.v1"
    assert surface["cost_policy"]["mode"] == "free_first_zero_surprise_spend"
    assert surface["routes"]["well_known"] == "https://www.syndiode.com/.well-known/nomad-google-agentic-era.json"
    assert surface["spend_guard"]["gemini_paid_call_decision"]["blocked"] is True
    assert surface["adoption_lanes"][0]["id"] == "gemini_3_5_flash_public_verifier"
    assert surface["adoption_lanes"][1]["implementation"]["store_default"] is False


def test_google_agentic_surface_openapi_routes_are_discoverable():
    doc = build_openapi_document(base_url="https://www.syndiode.com")

    assert "/swarm/google-agentic-era" in doc["paths"]
    assert "/.well-known/nomad-google-agentic-era.json" in doc["paths"]


def test_google_agentic_cli_surface():
    out = run_once(["google-agentic-era", "--base-url", "https://www.syndiode.com", "--json"])

    assert out["schema"] == "nomad.google_agentic_era.v1"
    assert out["routes"]["gemini_verifier"] == "https://www.syndiode.com/swarm/gemini-verifier"
    assert out["cost_policy"]["critical_runtime"] == "local_worker_and_local_ollama_first"
