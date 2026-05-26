import json

from nomad_telegram_miniapp import (
    build_telegram_miniapp_surface,
    normalize_telegram_fact_check_payload,
    record_telegram_miniapp_lead,
)


def test_telegram_miniapp_surface_exposes_revenue_onramp(monkeypatch):
    monkeypatch.setenv("NOMAD_TELEGRAM_TRANSITION_SETUP_NATIVE", "0.02")
    monkeypatch.setenv("NOMAD_TELEGRAM_COMPUTE_PLEDGE_NATIVE", "0.004")
    out = build_telegram_miniapp_surface(base_url="https://nomad.example")

    assert out["schema"] == "nomad.telegram_miniapp.v1"
    assert out["launch_url"] == "https://nomad.example/telegram-miniapp"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-telegram-miniapp.json"
    assert out["lead_capture_url"] == "https://nomad.example/telegram-miniapp/lead"
    assert out["fact_check_url"] == "https://nomad.example/telegram-miniapp/fact-check"
    assert out["primary_funnel"][0] == "proof_gated_bot_factory"
    assert "fact_check_intake" in out["primary_funnel"]
    assert "free_mini_diagnosis" in out["primary_funnel"]
    assert "payment_verification" in out["primary_funnel"]
    assert "worker_repair_after_payment" in out["primary_funnel"]
    assert "ai_agent_recruitment" in out["primary_funnel"]
    assert out["fact_check_lane"]["schema"] == "nomad.fact_check_lane.v1"
    assert out["fact_check_lane"]["miniapp_fact_check_url"] == "https://nomad.example/telegram-miniapp/fact-check"
    assert out["fact_check_lane"]["intake_url"] == "https://nomad.example/swarm/reliability-doctor/intake"
    assert out["fact_check_lane"]["handoff_url"] == "https://nomad.example/swarm/reliability-doctor/intake"
    assert out["fact_check_lane"]["work_exchange"]["auto_accept"] is True
    assert out["fact_check_lane"]["message"].startswith("Jeder, der den Transition Worker")
    assert out["bot_factory_lane"]["schema"] == "nomad.proof_gated_bot_factory_lane.v1"
    assert out["bot_factory_lane"]["service_type"] == "proof_gated_bot_factory"
    assert out["bot_factory_lane"]["work_exchange"]["counts_as_revenue"] is False
    assert out["bot_factory_lane"]["landing_page"] == "https://nomad.example/bot-factory"
    assert out["bot_factory_lane"]["one_step_paid_task"]["set"] == {"create_paid_task": True}
    assert out["bot_factory_lane"]["one_step_paid_task"]["counts_as_revenue"] is False
    assert "no_seed_phrases" in out["bot_factory_lane"]["hard_guards"]
    assert out["eth_trust_loop"]["minimum_pledge_native"] == 0.004
    offers = {item["offer_id"]: item for item in out["offers"]}
    assert offers["proof_gated_bot_factory"]["endpoint"] == "https://nomad.example/swarm/reliability-doctor/intake"
    assert offers["proof_gated_bot_factory"]["revenue_rule"] == "free_with_transition_worker_compute_or_paid_upgrade_after_verified_receipt"
    assert offers["fact_check_intake"]["endpoint"] == "https://nomad.example/telegram-miniapp/fact-check"
    assert offers["fact_check_intake"]["swarm_handoff_endpoint"] == "https://nomad.example/swarm/reliability-doctor/intake"
    assert offers["fact_check_intake"]["revenue_rule"] == "free_with_transition_worker_compute_contribution"
    assert offers["transition_worker_setup"]["price_native"] == 0.02
    assert offers["payment_verification"]["endpoint"] == "https://nomad.example/tasks/verify"
    assert offers["worker_repair_after_payment"]["endpoint"] == "https://nomad.example/tasks/work"
    assert offers["dacc_compute_pledge"]["price_native"] == 0.004
    assert offers["ai_agent_recruitment"]["endpoint"] == "https://nomad.example/.well-known/nomad-eth-support.json"
    assert offers["cursor_referral"]["revenue_rule"] == "usage_credit_not_cash_revenue"
    assert out["links"]["eth_support"] == "https://nomad.example/.well-known/nomad-eth-support.json"
    assert out["links"]["sales_funnel"] == "https://nomad.example/.well-known/nomad-sales-funnel.json"
    assert out["links"]["telegram_acquisition"] == "https://nomad.example/.well-known/nomad-telegram-acquisition.json"
    assert out["links"]["acquisition_engine"] == "https://nomad.example/.well-known/nomad-acquisition-engine.json"
    assert out["links"]["telegram_a2a"] == "https://nomad.example/.well-known/nomad-telegram-a2a.json"
    assert out["links"]["fact_check_miniapp"] == "https://nomad.example/telegram-miniapp/fact-check"
    assert out["links"]["fact_check_intake"] == "https://nomad.example/swarm/reliability-doctor/intake"
    assert out["links"]["bot_factory_intake"] == "https://nomad.example/swarm/reliability-doctor/intake"
    assert out["links"]["bot_factory_paid_upgrade"] == "https://nomad.example/service/e2e?service_type=proof_gated_bot_factory"
    assert out["links"]["bot_factory_landing"] == "https://nomad.example/bot-factory"
    assert out["payment"]["verify"] == "https://nomad.example/tasks/verify"
    assert out["payment"]["work"] == "https://nomad.example/tasks/work"
    assert any(item["campaign_id"] == "ethereum_support" for item in out["campaigns"])
    assert out["guardrails"]["no_unsolicited_dm"] is True
    assert out["copy"]["headline"] == "AI Swarm Fact Checker"
    assert out["copy"]["worker_free_message"].startswith("Jeder, der den Transition Worker")


def test_telegram_miniapp_surface_uses_public_nomad_prefix_for_syndiode():
    out = build_telegram_miniapp_surface(base_url="https://www.syndiode.com")

    assert out["public_base_url"] == "https://syndiode.com/nomad"
    assert out["launch_url"] == "https://syndiode.com/nomad/telegram-miniapp"
    assert out["lead_capture_url"] == "https://syndiode.com/nomad/telegram-miniapp/lead"
    assert out["fact_check_url"] == "https://syndiode.com/nomad/telegram-miniapp/fact-check"
    assert out["fact_check_lane"]["miniapp_fact_check_url"] == "https://syndiode.com/nomad/telegram-miniapp/fact-check"
    assert out["fact_check_lane"]["intake_url"] == "https://syndiode.com/nomad/swarm/reliability-doctor/intake"
    assert out["links"]["eth_support"] == "https://syndiode.com/nomad/.well-known/nomad-eth-support.json"


def test_telegram_fact_check_payload_normalizes_work_exchange_and_pdf_digest():
    out = normalize_telegram_fact_check_payload(
        {
            "claim": "The claim is true.",
            "source_url": "https://example.com/source",
            "pdf_upload": {"name": "paper.pdf", "bytes": 1234, "sha256": "abc"},
            "accepted_compute_barter_terms": False,
        },
        base_url="https://www.syndiode.com",
    )

    assert out["service_type"] == "fact_check"
    assert out["source"] == "telegram_miniapp_fact_check"
    assert out["accepted_compute_barter_terms"] is True
    assert out["return_multiplier"] == 1.3
    assert out["pdf_name"] == "paper.pdf"
    assert out["pdf_sha256"] == "abc"
    assert out["pdf_upload"]["content_included"] is False
    assert out["swarm_handoff_url"] == "https://syndiode.com/nomad/swarm/reliability-doctor/intake"


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
            "test_mode": True,
            "target_url": "https://nomad.example/downloads/handyoracle-edge-gadget.apk",
            "downloaded_bytes": 123,
            "sha256": "abc123",
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
    assert event["test_mode"] is True
    assert event["target_url"] == "https://nomad.example/downloads/handyoracle-edge-gadget.apk"
    assert event["downloaded_bytes"] == 123
    assert event["artifact_sha256"] == "abc123"
    assert event["telegram_user_hash"]
    assert event["telegram_init_data_hash"]
    assert "query_id=secretish" not in json.dumps(event)
    assert event["accounting_rule"]["recognized_revenue_usd"] == 0.0
