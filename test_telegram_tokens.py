from telegram_bot import ArbiterBot


class DummyChat:
    id = 12345


class DummyUpdate:
    effective_chat = DummyChat()


def test_auto_subscribe_chat_on_interaction(tmp_path, monkeypatch):
    import telegram_bot

    subscribers_path = tmp_path / "telegram_subscribers.json"
    monkeypatch.setattr(telegram_bot, "SUBSCRIBERS_PATH", subscribers_path)
    bot = ArbiterBot()
    bot._auto_subscribe_chat(DummyUpdate())
    assert bot._load_subscribers() == {12345}


def test_parse_explicit_github_token_command():
    bot = ArbiterBot()
    submissions = bot._parse_token_submissions("/token github not-a-real-token-123")
    assert submissions == [("GITHUB_TOKEN", "not-a-real-token-123")]


def test_parse_env_assignment_token():
    bot = ArbiterBot()
    submissions = bot._parse_token_submissions("HF_TOKEN=not-a-real-token-123")
    assert submissions == [("HF_TOKEN", "not-a-real-token-123")]


def test_parse_github_personal_access_token_assignment():
    bot = ArbiterBot()
    submissions = bot._parse_token_submissions(
        "GITHUB_PERSONAL_ACCESS_TOKEN=not-a-real-token-123"
    )
    assert submissions == [
        ("GITHUB_PERSONAL_ACCESS_TOKEN", "not-a-real-token-123")
    ]


def test_redacts_token_echo_text():
    bot = ArbiterBot()
    redacted = bot._redact_sensitive_text("GITHUB_TOKEN=not-a-real-token-123")
    assert "not-a-real-token-123" not in redacted
    assert "GITHUB_TOKEN=<redacted>" in redacted


def test_redacts_github_personal_access_token_echo_text():
    bot = ArbiterBot()
    redacted = bot._redact_sensitive_text(
        "GITHUB_PERSONAL_ACCESS_TOKEN=not-a-real-token-123"
    )
    assert "not-a-real-token-123" not in redacted
    assert "GITHUB_PERSONAL_ACCESS_TOKEN=<redacted>" in redacted
