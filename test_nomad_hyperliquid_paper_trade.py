import json

import scripts.nomad_hyperliquid_paper_trade as runner


def test_paper_trade_receipt_uses_no_wallet_or_exchange_order(monkeypatch):
    monkeypatch.setattr(
        runner,
        "fetch_candles",
        lambda *, coin, interval, hours: [{"c": str(100 + index)} for index in range(30)],
    )
    args = runner.argparse.Namespace(
        coin="BTC",
        interval="1h",
        hours=72,
        risk_profile="low",
        max_drawdown=3.0,
        max_notional=5.0,
        max_leverage=1.0,
    )

    receipt = runner.build_receipt(args)

    assert receipt["schema"] == "nomad.hyperliquid_paper_trade_receipt.v1"
    assert receipt["mode"] == "paper_trade_only"
    assert receipt["funds_used"] is False
    assert receipt["wallet_signature_used"] is False
    assert receipt["exchange_order_submitted"] is False
    assert len(receipt["source"]["close_values"]) == 30
    assert receipt["artifact"]["paper_order_intent"]["side"] == "buy"


def test_syndiode_submission_stays_free_and_secret_free(monkeypatch):
    captured = {}

    def fake_post(url, payload, *, timeout=30):
        captured["url"] = url
        captured["payload"] = payload
        return {"ok": True, "status": 202, "data": {"solution_proof_digest": "sha256:test"}}

    monkeypatch.setattr(runner, "_post_json", fake_post)
    receipt = {
        "schema": "nomad.hyperliquid_paper_trade_receipt.v1",
        "source": {"coin": "BTC"},
        "artifact": {
            "artifact_digest": "sha256:abc",
            "signal_receipt": {"signal": "long"},
            "risk_controls": {
                "max_drawdown_pct": 3.0,
                "max_notional_usd_shadow": 5.0,
                "max_leverage_shadow_cap": 1.0,
            },
        },
    }
    receipt["source"]["close_values"] = [100 + index for index in range(30)]

    result = runner.maybe_submit_to_syndiode(receipt, base_url="https://nomad.example")

    assert result["ok"] is True
    assert captured["url"] == "https://nomad.example/swarm/reliability-doctor/intake"
    assert captured["payload"]["create_paid_task"] is False
    assert len(captured["payload"]["candles"]) == 30
    assert "private" not in json.dumps(captured["payload"]).lower()
