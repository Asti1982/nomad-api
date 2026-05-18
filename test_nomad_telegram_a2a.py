from nomad_telegram_a2a import build_telegram_bot_to_bot_surface, route_telegram_bot_to_bot_message


def test_telegram_bot_to_bot_surface_exposes_guarded_transport(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TO_BOT_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TO_BOT_TARGETS", "@VerifierBot")
    monkeypatch.setenv("NOMAD_TELEGRAM_A2A_LEDGER_PATH", str(tmp_path / "telegram_a2a.jsonl"))

    surface = build_telegram_bot_to_bot_surface(base_url="https://nomad.example")

    assert surface["schema"] == "nomad.telegram_bot_to_bot_surface.v1"
    assert surface["capability"]["private_bot_to_bot"] is True
    assert surface["configured"]["allowed_targets"] == ["@verifierbot"]
    assert surface["loop_prevention"]["dedupe"] == "idempotency_digest"
    assert surface["links"]["send"].endswith("/swarm/telegram-a2a/messages")


def test_telegram_bot_to_bot_dry_run_requires_allowlist_and_loop_ack(monkeypatch, tmp_path):
    ledger = tmp_path / "telegram_a2a.jsonl"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:not-real")
    monkeypatch.setenv("TELEGRAM_BOT_TO_BOT_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TO_BOT_TARGETS", "@VerifierBot")
    monkeypatch.setenv("TELEGRAM_BOT_TO_BOT_MODE_ACK", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TO_BOT_DRY_RUN", "true")
    monkeypatch.setenv("NOMAD_TELEGRAM_A2A_SEND_SECRET", "send-secret")

    payload = {
        "target_bot_username": "@VerifierBot",
        "sender_agent_id": "nomad.proposer",
        "conversation_id": "agp-check",
        "payload": {"task": "verify bounded AGP candidate"},
        "proof_digest": "sha256:" + "a" * 64,
        "bot_to_bot_mode_ack": True,
    }
    result = route_telegram_bot_to_bot_message(
        payload,
        base_url="https://nomad.example",
        request_secret="send-secret",
        ledger_path=ledger,
    )
    replay = route_telegram_bot_to_bot_message(
        payload,
        base_url="https://nomad.example",
        request_secret="send-secret",
        ledger_path=ledger,
    )

    assert result["accepted"] is True
    assert result["sent"] is False
    assert result["dry_run"] is True
    assert result["decision"] == "telegram_bot_to_bot_dry_run_receipt"
    assert result["checks"]["target_allowlisted_or_unlisted_allowed"] is True
    assert replay["decision"] == "duplicate_telegram_a2a_noop"


def test_telegram_bot_to_bot_holds_unlisted_or_unauthorized(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:not-real")
    monkeypatch.setenv("TELEGRAM_BOT_TO_BOT_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TO_BOT_TARGETS", "@VerifierBot")
    monkeypatch.setenv("TELEGRAM_BOT_TO_BOT_MODE_ACK", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TO_BOT_DRY_RUN", "true")
    monkeypatch.setenv("NOMAD_TELEGRAM_A2A_SEND_SECRET", "send-secret")

    result = route_telegram_bot_to_bot_message(
        {
            "target_bot_username": "@OtherBot",
            "payload": {"task": "should hold"},
            "proof_digest": "sha256:" + "b" * 64,
            "bot_to_bot_mode_ack": True,
        },
        request_secret="wrong-secret",
        ledger_path=tmp_path / "telegram_a2a.jsonl",
    )

    assert result["accepted"] is False
    assert result["checks"]["target_allowlisted_or_unlisted_allowed"] is False
    assert result["checks"]["send_authorized"] is False
