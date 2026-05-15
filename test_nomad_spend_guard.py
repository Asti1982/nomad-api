from nomad_spend_guard import build_spend_guard_surface, paid_model_call_decision


def test_paid_model_calls_are_blocked_by_default(monkeypatch):
    monkeypatch.delenv("NOMAD_ALLOW_PAID_MODEL_CALLS", raising=False)
    monkeypatch.delenv("NOMAD_ALLOWED_PAID_PROVIDERS", raising=False)
    monkeypatch.delenv("NOMAD_MAX_PAID_PROBE_USD", raising=False)

    decision = paid_model_call_decision("openrouter", model="openai/gpt-4o-mini")

    assert decision["allowed"] is False
    assert decision["blocked"] is True
    assert decision["reason"] == "blocked_until_explicit_paid_model_budget_and_provider_allowlist"


def test_gemini_requires_specific_unlock_even_when_paid_calls_are_enabled(monkeypatch):
    monkeypatch.setenv("NOMAD_ALLOW_PAID_MODEL_CALLS", "true")
    monkeypatch.setenv("NOMAD_ALLOWED_PAID_PROVIDERS", "openrouter")
    monkeypatch.setenv("NOMAD_MAX_PAID_PROBE_USD", "0.01")
    monkeypatch.delenv("NOMAD_ALLOW_GEMINI_SPEND", raising=False)

    decision = paid_model_call_decision("openrouter", model="google/gemini-2.0-flash-001")

    assert decision["gemini_like"] is True
    assert decision["allowed"] is False


def test_spend_guard_surface_exposes_zero_spend_policy(monkeypatch):
    monkeypatch.delenv("NOMAD_ALLOW_PAID_MODEL_CALLS", raising=False)

    surface = build_spend_guard_surface(base_url="https://nomad.example")

    assert surface["schema"] == "nomad.spend_guard.v1"
    assert surface["well_known_url"] == "https://nomad.example/.well-known/nomad-spend-guard.json"
    assert surface["default_policy"] == "zero_paid_hosted_model_spend"
    assert surface["current_decisions"]["openrouter"]["allowed"] is False
    assert surface["gemini_specific_policy"]["blocked_by_default"] is True
