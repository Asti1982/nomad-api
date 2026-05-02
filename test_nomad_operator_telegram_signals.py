import pytest

from nomad_operator_telegram_signals import (
    format_human_auto_cycle_digest,
    format_human_status_snapshot,
    human_telegram_signals_enabled,
)


def test_human_status_avoids_schema_jargon():
    snap = {
        "compute": {"probe": {"ollama": {"api_reachable": True, "count": 1}}},
        "products": {"products": [], "stats": {}},
        "self_state": {"next_objective": "scout more"},
        "github_models": {"available": True, "model_count": 2},
        "xai_grok": {},
        "addons": {"quantum_tokens": {}},
        "public_api_url": "http://127.0.0.1:8787",
    }
    text = format_human_status_snapshot(snap, periodic=False)
    assert "nomad." not in text.lower()
    assert "schema" not in text.lower()
    assert "Nomad" in text
    assert "lokal" in text.lower() or "Lokal" in text


def test_human_status_quantum_local_no_nag():
    snap = {
        "compute": {"probe": {"ollama": {"api_reachable": True, "count": 1}}},
        "products": {"products": [], "stats": {}},
        "self_state": {},
        "github_models": {"available": True},
        "xai_grok": {},
        "addons": {
            "quantum_tokens": {
                "enabled": True,
                "best_next_quantum_unlock": {
                    "provider": "Local qtokens",
                    "env_var": "",
                    "telegram_command": "/quantum",
                },
            }
        },
        "public_api_url": "https://x.example",
    }
    text = format_human_status_snapshot(snap, periodic=True)
    low = text.lower()
    assert "quantum" in low and "lokal" in low and "provider-token" in low.replace("–", "-").lower()
    assert "freischalten" not in low


def test_human_auto_cycle_digest_short():
    result = {
        "objective": "grow",
        "self_development": {"next_objective": "next"},
        "autonomous_development": {"skipped": True, "reason": "cooldown"},
        "lead_scout": {},
    }
    text = format_human_auto_cycle_digest("scheduled", result)
    assert len(text) < 1200
    assert "Auto-Lauf" in text
    assert "API" in text


def test_human_signals_env_default(monkeypatch):
    monkeypatch.delenv("TELEGRAM_HUMAN_SIGNALS", raising=False)
    assert human_telegram_signals_enabled() is True

    monkeypatch.setenv("TELEGRAM_HUMAN_SIGNALS", "false")
    assert human_telegram_signals_enabled() is False
