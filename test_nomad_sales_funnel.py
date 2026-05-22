from nomad_sales_funnel import build_sales_funnel_surface, compact_sales_lane


def test_sales_funnel_exposes_repair_payment_worker_loop(monkeypatch):
    monkeypatch.setenv("NOMAD_PAYMENT_ADDRESS", "0xFc1aB8C0D65fd947B00B9864deA06f705C045Af6")
    monkeypatch.setenv("NOMAD_TELEGRAM_TRANSITION_SETUP_NATIVE", "0.02")
    monkeypatch.setenv("NOMAD_REPAIR_URGENT_NATIVE", "0.05")

    out = build_sales_funnel_surface(base_url="https://www.syndiode.com")

    assert out["schema"] == "nomad.sales_funnel.v1"
    assert out["public_base_url"] == "https://syndiode.com/nomad"
    assert out["payment"]["recipient_set"] is True
    assert out["payment"]["verify_endpoint"] == "https://syndiode.com/nomad/tasks/verify"
    assert out["payment"]["work_endpoint"] == "https://syndiode.com/nomad/tasks/work"

    repair = compact_sales_lane(out, "repair_product")
    assert repair["entry"] == "https://syndiode.com/nomad/telegram-miniapp"
    assert repair["prices_native"]["starter"] == 0.02
    assert repair["prices_native"]["urgent"] == 0.05
    assert [step["reason"] for step in repair["steps"]] == [
        "free_mini_diagnosis",
        "create_paid_repair_task",
        "verify_payment_tx_hash",
        "produce_worker_repair_draft",
    ]
    assert repair["revenue_rule"] == "revenue_only_after_verified_task_payment"


def test_sales_funnel_separates_referral_credit_from_cash_revenue():
    out = build_sales_funnel_surface(base_url="https://nomad.example")

    cursor = compact_sales_lane(out, "cursor_referral")

    assert cursor["revenue_rule"] == "usage_credit_not_cash_revenue"
    assert out["guardrails"]["no_unsolicited_dm"] is True
    assert out["guardrails"]["revenue_requires"] == (
        "verified task payment, verified Cursor credit, or settled grant agreement"
    )
