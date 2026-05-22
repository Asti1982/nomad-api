from nomad_telegram_a2a_bridge import (
    format_telegram_a2a_reply,
    handle_telegram_a2a_message,
    parse_a2a_text,
)


def test_parse_a2a_probe_respects_no_reply():
    parsed = parse_a2a_text(
        "NOMAD_A2A_PROBE v1\nid=probe-1\nmax_depth=0\nno_reply_required=true"
    )

    assert parsed["command"] == "probe"
    assert parsed["id"] == "probe-1"
    assert parsed["max_depth"] == 0
    assert parsed["no_reply_required"] is True


def test_a2a_guard_accepts_allowed_bot_without_reply(monkeypatch):
    monkeypatch.setenv("NOMAD_TELEGRAM_A2A_ALLOWED_BOTS", "NomadA2ABot,NomadVerifierBot")

    out = handle_telegram_a2a_message(
        "NOMAD_A2A_PROBE v1 id=probe-2 max_depth=0 no_reply_required=true",
        sender_username="NomadA2ABot",
        receiver_username="NomadVerifierBot",
        receiver_role="verifier",
        sender_is_bot=True,
    )

    assert out["accepted"] is True
    assert out["command"] == "probe"
    assert out["should_reply"] is False
    assert out["reason"] == "accepted_no_reply_required"


def test_a2a_guard_rejects_unknown_sender(monkeypatch):
    monkeypatch.setenv("NOMAD_TELEGRAM_A2A_ALLOWED_BOTS", "NomadA2ABot,NomadVerifierBot")

    out = handle_telegram_a2a_message(
        "NOMAD_A2A_PROBE v1 id=probe-3 max_depth=1",
        sender_username="RandomBot",
        receiver_username="NomadVerifierBot",
        receiver_role="verifier",
        sender_is_bot=True,
    )

    assert out["accepted"] is False
    assert out["reason"] == "sender_not_allowed"
    assert out["should_reply"] is False


def test_a2a_verify_reply_is_loop_safe(monkeypatch):
    monkeypatch.setenv("NOMAD_TELEGRAM_A2A_ALLOWED_BOTS", "NomadA2ABot,NomadVerifierBot")

    out = handle_telegram_a2a_message(
        (
            "NOMAD_VERIFY v1 id=verify-1 max_depth=1 "
            "url=https://localhost/private schema=nomad.private"
        ),
        sender_username="NomadA2ABot",
        receiver_username="NomadVerifierBot",
        receiver_role="verifier",
        sender_is_bot=True,
    )
    reply = format_telegram_a2a_reply(out)

    assert out["accepted"] is True
    assert out["should_reply"] is True
    assert out["verification"]["reason"] == "url_not_allowed"
    assert "NOMAD_A2A_RECEIPT v1" in reply
    assert "no_reply_required=true" in reply


def test_a2a_repair_command_routes_to_paid_sales_funnel(monkeypatch):
    monkeypatch.setenv("NOMAD_TELEGRAM_A2A_ALLOWED_BOTS", "NomadA2ABot,NomadVerifierBot")
    monkeypatch.setenv("AGENT_ADDRESS", "0xFc1aB8C0D65fd947B00B9864deA06f705C045Af6")

    out = handle_telegram_a2a_message(
        "NOMAD_REPAIR v1 id=repair-1 max_depth=1 problem=blocked_worker",
        sender_username="NomadVerifierBot",
        receiver_username="NomadA2ABot",
        receiver_role="a2a",
        sender_is_bot=True,
        base_url="https://www.syndiode.com",
    )
    reply = format_telegram_a2a_reply(out)

    assert out["accepted"] is True
    assert out["should_reply"] is True
    assert out["sales_route"]["lane"]["lane_id"] == "repair_product"
    assert out["sales_route"]["payment_recipient_set"] is True
    assert out["sales_route"]["lane"]["entry"] == "https://syndiode.com/nomad/telegram-miniapp"
    assert "route=repair_product" in reply
    assert "payment_recipient_set=true" in reply


def test_a2a_worker_command_routes_to_recruitment(monkeypatch):
    monkeypatch.setenv("NOMAD_TELEGRAM_A2A_ALLOWED_BOTS", "NomadA2ABot,NomadVerifierBot")

    out = handle_telegram_a2a_message(
        "NOMAD_WORKER v1 id=worker-1 max_depth=0 reply_required=true",
        sender_username="NomadVerifierBot",
        receiver_username="NomadA2ABot",
        receiver_role="a2a",
        sender_is_bot=True,
        base_url="https://nomad.example",
    )

    assert out["accepted"] is True
    assert out["sales_route"]["lane"]["lane_id"] == "worker_recruitment"
    assert out["reason"] == "accepted_max_depth_reached"
