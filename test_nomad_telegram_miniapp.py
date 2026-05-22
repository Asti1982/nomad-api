import json

from nomad_telegram_miniapp import build_telegram_miniapp_surface, record_telegram_miniapp_lead


def test_telegram_miniapp_surface_exposes_revenue_onramp(monkeypatch):
    monkeypatch.setenv("NOMAD_TELEGRAM_TRANSITION_SETUP_NATIVE", "0.02")
    monkeypatch.setenv("NOMAD_TELEGRAM_COMPUTE_PLEDGE_NATIVE", "0.004")
    out = build_telegram_miniapp_surface(base_url="https://nomad.example")

    assert out["schema"] == "nomad.telegram_miniapp.v1"
    assert out["launch_url"] == "https://nomad.example/telegram-miniapp"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-telegram-miniapp.json"
    assert out["lead_capture_url"] == "https://nomad.example/telegram-miniapp/lead"
    assert "free_mini_diagnosis" in out["primary_funnel"]
    assert "ai_agent_recruitment" in out["primary_funnel"]
    assert out["eth_trust_loop"]["minimum_pledge_native"] == 0.004
    offers = {item["offer_id"]: item for item in out["offers"]}
    assert offers["transition_worker_setup"]["price_native"] == 0.02
    assert offers["dacc_compute_pledge"]["price_native"] == 0.004
    assert offers["ai_agent_recruitment"]["endpoint"] == "https://nomad.example/.well-known/nomad-eth-support.json"
    assert offers["cursor_referral"]["revenue_rule"] == "usage_credit_not_cash_revenue"
    assert out["links"]["eth_support"] == "https://nomad.example/.well-known/nomad-eth-support.json"
    assert any(item["campaign_id"] == "ethereum_support" for item in out["campaigns"])
    assert out["guardrails"]["no_unsolicited_dm"] is True


def test_telegram_miniapp_surface_uses_public_nomad_prefix_for_syndiode():
    out = build_telegram_miniapp_surface(base_url="https://www.syndiode.com")

    assert out["public_base_url"] == "https://syndiode.com/nomad"
    assert out["launch_url"] == "https://syndiode.com/nomad/telegram-miniapp"
    assert out["lead_capture_url"] == "https://syndiode.com/nomad/telegram-miniapp/lead"
    assert out["links"]["eth_support"] == "https://syndiode.com/nomad/.well-known/nomad-eth-support.json"


def test_telegram_miniapp_lead_receipt_is_secret_free(tmp_path):
    ledger = tmp_path / "miniapp.jsonl"
    out = record_telegram_miniapp_lead(
        {
            "stage": "task_created",
            "problem": "Need transition worker setup\nwith proof loop",
            "contact": "@buyer",
            "requester_wallet": "0xabc",
            "budget_native": "0.01",
            "campaign": "dacc_eth_pledge",
            "telegram_user": {"id": 123, "username": "alice", "language_code": "en"},
            "telegram_init_data": "query_id=secretish",
        },
        base_url="https://nomad.example",
        remote_addr="203.0.113.7",
        ledger_path=ledger,
    )

    assert out["ok"] is True
    assert out["schema"] == "nomad.telegram_miniapp_lead_receipt.v1"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    event = rows[0]
    assert event["stage"] == "task_created"
    assert event["budget_native"] == 0.01
    assert event["campaign"] == "dacc_eth_pledge"
    assert event["telegram_user_hash"]
    assert event["telegram_init_data_hash"]
    assert "query_id=secretish" not in json.dumps(event)
    assert event["accounting_rule"]["recognized_revenue_usd"] == 0.0
