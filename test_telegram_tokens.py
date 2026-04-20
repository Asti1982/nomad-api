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


def test_redacts_xai_grok_token_echo_text():
    bot = ArbiterBot()
    submissions = bot._parse_token_submissions("/token grok xai-not-a-real-token-1234567890")
    redacted = bot._redact_sensitive_text("XAI_API_KEY=xai-not-a-real-token-1234567890")
    assert submissions == [("XAI_API_KEY", "xai-not-a-real-token-1234567890")]
    assert "not-a-real-token-1234567890" not in redacted
    assert "XAI_API_KEY=<redacted>" in redacted


def test_parse_codebuddy_token_alias_and_redact_echo_text():
    bot = ArbiterBot()
    submissions = bot._parse_token_submissions("/token codebuddy cb-not-a-real-token-123")
    redacted = bot._redact_sensitive_text("CODEBUDDY_API_KEY=cb-not-a-real-token-123")
    assert submissions == [("CODEBUDDY_API_KEY", "cb-not-a-real-token-123")]
    assert "cb-not-a-real-token-123" not in redacted
    assert "CODEBUDDY_API_KEY=<redacted>" in redacted


def test_parse_render_token_alias_and_redact_echo_text():
    bot = ArbiterBot()
    submissions = bot._parse_token_submissions("/token render rnd_not-a-real-token-123")
    redacted = bot._redact_sensitive_text("RENDER_API_KEY=rnd_not-a-real-token-123")
    assert submissions == [("RENDER_API_KEY", "rnd_not-a-real-token-123")]
    assert "not-a-real-token-123" not in redacted
    assert "RENDER_API_KEY=<redacted>" in redacted


def test_parse_quantum_token_alias_and_redact_echo_text():
    bot = ArbiterBot()
    submissions = bot._parse_token_submissions("/token ibm_quantum ibm-not-a-real-token-123")
    redacted = bot._redact_sensitive_text("IBM_QUANTUM_TOKEN=ibm-not-a-real-token-123")
    assert submissions == [("IBM_QUANTUM_TOKEN", "ibm-not-a-real-token-123")]
    assert "ibm-not-a-real-token-123" not in redacted
    assert "IBM_QUANTUM_TOKEN=<redacted>" in redacted


def test_parse_common_ibm_quantum_typo_alias():
    bot = ArbiterBot()
    submissions = bot._parse_token_submissions("/token ibm_quatum ibm-not-a-real-token-123")
    assert submissions == [("IBM_QUANTUM_TOKEN", "ibm-not-a-real-token-123")]


def test_parse_quantum_inspire_token_alias_and_redact_echo_text():
    bot = ArbiterBot()
    submissions = bot._parse_token_submissions("/token quantum_inspire qi-not-a-real-token-123")
    redacted = bot._redact_sensitive_text("QUANTUM_INSPIRE_TOKEN=qi-not-a-real-token-123")
    assert submissions == [("QUANTUM_INSPIRE_TOKEN", "qi-not-a-real-token-123")]
    assert "qi-not-a-real-token-123" not in redacted
    assert "QUANTUM_INSPIRE_TOKEN=<redacted>" in redacted


def test_long_telegram_messages_are_chunked():
    chunks = ArbiterBot._message_chunks("a" * 3700 + "\n" + "b" * 3700)
    assert len(chunks) >= 2
    assert all(len(chunk) <= 3600 for chunk in chunks)


def test_status_snapshot_explains_solved_and_open_gates():
    bot = ArbiterBot()
    text = bot._format_status_snapshot(
        {
            "public_api_url": "https://nomad.example",
            "compute": {
                "probe": {
                    "ollama": {"api_reachable": True, "count": 2},
                    "hosted": {
                        "github_models": {
                            "configured": True,
                            "available": True,
                            "model_count": 43,
                        }
                    },
                },
                "brains": {"secondary": [{"name": "GitHub Models"}]},
            },
            "products": {
                "products": [{"product_id": "prod-test"}],
                "stats": {"private_offer_needs_approval": 1},
            },
            "self_state": {
                "next_objective": "Work active lead privately.",
                "self_development_unlocks": [
                    {"short_ask": "Approve whether Nomad may draft help."}
                ],
            },
            "github_models": {
                "configured": True,
                "available": True,
                "model_count": 43,
            },
        }
    )

    assert "Kernteile sind gelöst" in text
    assert "Offen, aber kein Fehler" in text
    assert "APPROVE_LEAD_HELP" in text


def test_telegram_formats_product_list():
    bot = ArbiterBot()
    text = bot._format_result(
        {
            "mode": "nomad_product_list",
            "stats": {"private_offer_needs_approval": 1},
            "products": [
                {
                    "product_id": "prod-test",
                    "name": "Nomad Tool Guardrail Pack",
                    "sku": "nomad.tool_guardrail_pack",
                    "status": "private_offer_needs_approval",
                    "source_lead": {"title": "AutoGen GuardrailProvider"},
                    "paid_offer": {"price_native": 0.01, "delivery": "draft artifact"},
                    "approval_boundary": {
                        "approval_required": True,
                        "approval_gate": "APPROVE_LEAD_HELP=comment",
                    },
                }
            ],
        }
    )

    assert "Nomad products" in text
    assert "nomad.tool_guardrail_pack" in text
    assert "Open gate" in text


def test_telegram_formats_addons_and_quantum_tokens():
    bot = ArbiterBot()
    addons_text = bot._format_result(
        {
            "mode": "nomad_addon_scan",
            "source_dir": "Nomadds",
            "stats": {"discovered": 1, "active_safe_adapter": 1, "needs_human_review": 1},
            "addons": [
                {
                    "name": "Quantum Computing Integration",
                    "status": "active_safe_adapter",
                    "manifest_path": "quantum_addon.json",
                    "next_action": "Use /quantum.",
                }
            ],
            "quantum_tokens": {
                "enabled": True,
                "claim_boundary": "Local qtokens are quantum-inspired decision receipts.",
                "best_next_quantum_unlock": {
                    "provider": "IBM Quantum",
                    "telegram_command": "/token ibm_quantum <token>",
                },
            },
            "secret_warnings": [{"token_type": "xai"}],
        }
    )
    quantum_text = bot._format_result(
        {
            "mode": "nomad_quantum_tokens",
            "objective": "improve guardrails",
            "claim_boundary": "No quantum speedup claim.",
            "selected_strategy": {"title": "Measurement critic gate"},
            "tokens": [{"qtoken_id": "qtok-test", "title": "Measurement critic gate", "score": 0.9}],
            "best_next_quantum_unlock": {
                "provider": "IBM Quantum",
                "why": "Best first unlock.",
                "telegram_command": "/token ibm_quantum <token>",
            },
            "human_unlocks": [],
        }
    )

    assert "Nomad addons" in addons_text
    assert "Quantum Computing Integration" in addons_text
    assert "Best quantum unlock" in addons_text
    assert "Secret warning" in addons_text
    assert "Nomad quantum tokens" in quantum_text
    assert "qtok-test" in quantum_text
    assert "/token ibm_quantum <token>" in quantum_text
